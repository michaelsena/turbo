"""No-model tests for the local issue dispatcher and its durable safety boundary."""
from __future__ import annotations

import copy
import fcntl
import importlib.util
import json
import multiprocessing
import os
import signal
import time
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "app_dispatcher.py"
spec = importlib.util.spec_from_file_location("turbo_app_dispatcher_tested", SCRIPT)
dispatcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = dispatcher
spec.loader.exec_module(dispatcher)


class FakeRunner:
    """Record argv and replace every GitHub, git, and worker invocation."""
    def __init__(self, issues=None, events=None, comments=None):
        self.issues = [] if issues is None else issues
        self.events = [] if events is None else events
        self.comments = [] if comments is None else comments
        self.calls = []
        self.failures = {}
        self.malformed = {}
        self.worker_callback = None
        self.login_output = "Logged in using ChatGPT"

    def __call__(self, argv, *, cwd=None, input_text=None, timeout=60,
                 stdout_path=None, lock_fd=None):
        self.calls.append({"argv": list(argv), "cwd": cwd, "input_text": input_text,
                           "timeout": timeout, "stdout_path": stdout_path, "lock_fd": lock_fd})
        if not isinstance(argv, list) or not all(isinstance(arg, str) for arg in argv):
            raise AssertionError("all child commands must use a string argv list")
        program = Path(argv[0]).name
        key = "worker" if program == "codex" and "exec" in argv else program
        if (program == "git" or program == "gh" and "repo" in argv) and "clone" in argv:
            key = "clone"
        if program == "gh" and "gh" in self.failures:
            failure = self.failures["gh"]
            if isinstance(failure, BaseException):
                raise failure
            return subprocess.CompletedProcess(argv, failure, "", "simulated authentication failure")
        if program == "gh" and "api" in argv:
            route = next((arg for arg in argv if arg.lstrip("/").startswith("repos/")), "")
            if "/events" in route:
                key = "events"
                response = [self.events]
            elif "/comments" in route:
                key = "comments"
                response = [self.comments]
            elif route.rstrip("/").split("/")[-1].split("?")[0].isdigit():
                key = "issue"
                response = self.issues[0] if self.issues else {}
            elif route.lstrip("/").count("/") == 2 and "/issues" not in route:
                key = "repository"
                response = {"default_branch": "main"}
            else:
                key = "issues"
                response = [self.issues]
            if key in self.malformed:
                response = self.malformed[key]
            if key in self.failures:
                failure = self.failures[key]
                if isinstance(failure, BaseException):
                    raise failure
                return subprocess.CompletedProcess(argv, failure, "", "simulated GitHub failure")
            return subprocess.CompletedProcess(argv, 0, json.dumps(response), "")
        if key in self.failures:
            failure = self.failures[key]
            if isinstance(failure, BaseException):
                raise failure
            return subprocess.CompletedProcess(argv, failure, "", "simulated command failure")
        if (program == "git" or program == "gh" and "repo" in argv) and "clone" in argv:
            destination = argv[4] if program == "gh" else argv[-1]
            Path(destination).mkdir(parents=True, exist_ok=True)
        if program == "codex" and "exec" in argv and self.worker_callback:
            return self.worker_callback(argv, self.calls[-1])
        stdout = self.login_output if argv[:3] == ["codex", "login", "status"] else "fake command succeeded"
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    @property
    def workers(self):
        return [call for call in self.calls if Path(call["argv"][0]).name == "codex" and "exec" in call["argv"]]

    @property
    def clones(self):
        return [call for call in self.calls if "clone" in call["argv"] and Path(call["argv"][0]).name in {"git", "gh"}]


def eligible_issue(number=7, **overrides):
    value = {"number": number, "state": "open", "title": "Improve the app table",
             "body": "App-only change. Keep research artifacts unchanged.",
             "html_url": f"https://github.com/michaelsena/turbo/issues/{number}",
             "labels": [{"name": "area:app"}, {"name": "status:ready"}]}
    value.update(overrides)
    return value


def ready_event(event_id=101, *, actor="michaelsena", event="labeled", minute=0):
    return {"id": event_id, "event": event, "label": {"name": "status:ready"},
            "actor": {"login": actor}, "created_at": f"2026-11-09T12:{minute:02d}:00Z"}


def stop_process(process):
    if process.is_alive():
        process.terminate()
    process.join(timeout=5)


def hold_dispatcher_lock(config, entered, release, results):
    runner = FakeRunner()
    def blocked_runner(argv, **kwargs):
        entered.set()
        if not release.wait(30):
            raise RuntimeError("test release timeout")
        return runner(argv, **kwargs)
    try:
        results.put(dispatcher.dispatch_once(config, execute=True, runner=blocked_runner))
    except Exception as error:
        results.put({"exception": repr(error)})


def pause_inside_worker(config, entered, release):
    runner = FakeRunner([eligible_issue()], [ready_event()])
    def worker(argv, call):
        entered.set()
        release.wait(30)
        return subprocess.CompletedProcess(argv, 0, "done", "")
    runner.worker_callback = worker
    dispatcher.dispatch_once(config, execute=True, runner=runner)


class AppDispatcherTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="turbo-dispatcher-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.charter = self.base / "charter.md"
        self.charter.write_text("Work only on the app. Never alter research, spend, or merge automatically.\n")
        self.config = dispatcher.Config(repo="michaelsena/turbo", state_dir=self.base / "state",
            workspace_root=self.base / "checkouts", ready_actor="michaelsena",
            timeout_seconds=60, poll_seconds=60, charter_path=self.charter)
        self.runner = FakeRunner([eligible_issue()], [ready_event()])

    def dispatch(self, *, execute=True, runner=None):
        return dispatcher.dispatch_once(self.config, execute=execute, runner=runner or self.runner)

    def attempts(self):
        path = self.config.state_dir / "state.json"
        return json.loads(path.read_text())["attempts"] if path.exists() else {}

    def test_idle_and_dry_run_never_launch_worker_or_clone(self):
        idle = FakeRunner()
        result = self.dispatch(runner=idle)
        self.assertEqual(result["status"], "idle", result)
        self.assertEqual(idle.workers, [])
        self.assertEqual(idle.clones, [])
        result = self.dispatch(execute=False)
        self.assertEqual(result["status"], "dry_run", result)
        self.assertEqual(result["eligible"], [{"issue": 7, "event_id": 101}])
        self.assertEqual(self.runner.workers, [])
        self.assertEqual(self.runner.clones, [])
        self.assertFalse(self.attempts())

    def test_only_open_app_ready_non_pr_issue_with_authorized_event_runs(self):
        cases = [eligible_issue(state="closed"), eligible_issue(labels=[{"name": "status:ready"}]),
                 eligible_issue(labels=[{"name": "area:app"}]), eligible_issue(pull_request={"url": "example"})]
        for index, issue in enumerate(cases):
            runner = FakeRunner([issue], [ready_event()])
            result = self.dispatch(runner=runner)
            with self.subTest(index=index):
                self.assertFalse(runner.workers, result)
                self.assertFalse(runner.clones, result)
        runner = FakeRunner([eligible_issue()], [ready_event(actor="somebody-else")])
        result = self.dispatch(runner=runner)
        self.assertFalse(runner.workers, result)
        self.assertFalse(self.attempts())

    def test_latest_ready_event_must_be_authorized_not_an_older_event(self):
        self.runner.events = [ready_event(), ready_event(102, event="unlabeled", minute=1),
                              ready_event(103, actor="somebody-else", minute=2)]
        result = self.dispatch()
        self.assertFalse(self.runner.workers, result)
        self.assertFalse(self.attempts())

    def test_all_pages_are_consumed_before_dispatch_and_bad_later_page_fails_closed(self):
        self.runner.malformed["issues"] = [[], [eligible_issue()]]
        self.runner.malformed["events"] = [[], [ready_event()]]
        self.runner.malformed["comments"] = [[], [{"id": 1, "body": "App scope clarification.",
            "user": {"login": "michaelsena"}, "created_at": "2026-11-09T12:00:00Z"}]]
        result = self.dispatch(execute=False)
        self.assertEqual(result["status"], "dry_run", result)
        self.assertEqual(result["eligible"], [{"issue": 7, "event_id": 101}])
        paginated_calls = [call["argv"] for call in self.runner.calls if "api" in call["argv"] and "--paginate" in call["argv"]]
        self.assertTrue(paginated_calls)
        self.assertTrue(all("--slurp" in argv for argv in paginated_calls))
        self.runner.malformed["issues"] = [[eligible_issue()], "not-a-page"]
        result = self.dispatch()
        self.assertEqual(result["status"], "error", result)
        self.assertEqual(self.runner.workers, [])
        self.assertEqual(self.runner.clones, [])

    def test_github_errors_timeouts_and_malformed_payloads_fail_closed(self):
        for key, failure in (("gh", 1), ("issues", 1), ("events", 1), ("comments", 1),
                             ("issues", subprocess.TimeoutExpired(["gh"], 10))):
            runner = FakeRunner([eligible_issue()], [ready_event()])
            runner.failures[key] = failure
            result = self.dispatch(runner=runner)
            with self.subTest(key=key, failure=repr(failure)):
                self.assertEqual(result["status"], "error", result)
                self.assertFalse(runner.workers)
                self.assertFalse(runner.clones)
        for key, payload in (("issues", {}), ("issues", [[None]]),
                             ("events", [[{"id": True, "event": "labeled", "label": {"name": "status:ready"}}]]),
                             ("comments", [["not-an-object"]])):
            runner = FakeRunner([eligible_issue()], [ready_event()])
            runner.malformed[key] = payload
            result = self.dispatch(runner=runner)
            with self.subTest(key=key, payload=payload):
                self.assertEqual(result["status"], "error", result)
                self.assertFalse(runner.workers)
                self.assertFalse(runner.clones)
        self.assertFalse(self.attempts())

    def test_malformed_issue_fields_do_not_launch_partial_work(self):
        malformed = [eligible_issue(number=True), eligible_issue(number=-1), eligible_issue(title=[]),
                     eligible_issue(labels=None), eligible_issue(labels=[{"name": []}]),
                     eligible_issue(body={}), eligible_issue(html_url="javascript:bad")]
        for index, issue in enumerate(malformed):
            runner = FakeRunner([eligible_issue(6), issue], [ready_event()])
            config = dispatcher.Config(repo=self.config.repo, state_dir=self.base / f"malformed-state-{index}",
                workspace_root=self.base / f"malformed-work-{index}", ready_actor="michaelsena",
                charter_path=self.charter)
            result = dispatcher.dispatch_once(config, execute=True, runner=runner)
            with self.subTest(issue=issue):
                self.assertEqual(result["status"], "error", result)
                self.assertFalse(runner.workers, result)
                self.assertFalse(runner.clones, result)
                state_path = config.state_dir / "state.json"
                self.assertFalse(json.loads(state_path.read_text())["attempts"] if state_path.exists() else {})

    def test_event_is_persisted_before_worker_and_success_is_only_returned(self):
        observed = []
        def worker(argv, call):
            observed.append(copy.deepcopy(self.attempts()))
            return subprocess.CompletedProcess(argv, 0, "worker exited normally", "")
        self.runner.worker_callback = worker
        result = self.dispatch()
        self.assertEqual(result["status"], "returned", result)
        self.assertEqual(len(self.runner.workers), 1)
        self.assertEqual(len(observed), 1)
        self.assertIn("7:101", observed[0])
        self.assertIn(observed[0]["7:101"]["status"], {"reserved", "running"})
        self.assertEqual(self.attempts()["7:101"]["status"], "returned")
        self.assertFalse(any("close" in call["argv"] or "merge" in call["argv"] for call in self.runner.calls))
        self.assertNotIn("completed", self.attempts()["7:101"]["status"])

    def test_same_event_is_deduplicated_across_restarts_and_explicit_requeue_is_new_event(self):
        self.dispatch()
        first_checkout = self.attempts()["7:101"]["checkout"]
        self.runner.issues[0]["body"] += " Body edit is not a fresh authorization event."
        self.dispatch()
        self.assertEqual(len(self.runner.workers), 1)
        self.runner.events += [ready_event(102, event="unlabeled", minute=1), ready_event(103, minute=2)]
        result = self.dispatch()
        self.assertEqual(result["status"], "returned", result)
        self.assertEqual(len(self.runner.workers), 2)
        self.assertEqual(set(self.attempts()), {"7:101", "7:103"})
        self.assertNotEqual(self.attempts()["7:103"]["checkout"], first_checkout)

    def test_worker_timeout_or_failure_never_automatically_retries_same_event(self):
        for failure in (1, subprocess.TimeoutExpired(["codex", "exec"], 60)):
            with tempfile.TemporaryDirectory(dir=self.base) as raw:
                config = dispatcher.Config(repo=self.config.repo, state_dir=Path(raw) / "state",
                    workspace_root=Path(raw) / "work", ready_actor="michaelsena", charter_path=self.charter)
                runner = FakeRunner([eligible_issue()], [ready_event()])
                runner.failures["worker"] = failure
                result = dispatcher.dispatch_once(config, execute=True, runner=runner)
                with self.subTest(failure=repr(failure)):
                    self.assertIn(result["status"], {"failed", "uncertain"}, result)
                    count = len(runner.workers)
                    runner.failures.clear()
                    dispatcher.dispatch_once(config, execute=True, runner=runner)
                    self.assertEqual(len(runner.workers), count)

    def test_api_key_login_does_not_authorize_subscription_worker(self):
        self.runner.login_output = "Logged in using an API key"
        result = self.dispatch()
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(self.runner.workers, [])
        self.assertEqual(self.runner.clones, [])
        self.assertEqual(self.attempts()["7:101"]["status"], "failed")
        self.runner.login_output = "Logged in using ChatGPT"
        self.dispatch()
        self.assertEqual(self.runner.workers, [])

    def test_preflight_timeout_is_uncertain_and_never_automatically_retried(self):
        self.runner.failures["codex"] = subprocess.TimeoutExpired(["codex", "login", "status"], 30)
        result = self.dispatch()
        self.assertEqual(result["status"], "uncertain", result)
        self.assertEqual(result["reason"], "preflight_timeout")
        self.assertEqual(self.runner.workers, [])
        self.assertEqual(self.runner.clones, [])
        self.runner.failures.clear()
        self.dispatch()
        self.assertEqual(self.runner.workers, [])
        self.assertEqual(self.attempts()["7:101"]["status"], "uncertain")

    def test_clone_failure_consumes_event_without_worker_or_automatic_retry(self):
        self.runner.failures["clone"] = 1
        result = self.dispatch()
        self.assertIn(result["status"], {"failed", "uncertain"}, result)
        self.assertEqual(self.runner.workers, [])
        self.assertEqual(len(self.runner.clones), 1)
        self.assertIn("7:101", self.attempts())
        self.runner.failures.clear()
        self.dispatch()
        self.assertEqual(len(self.runner.clones), 1)
        self.assertEqual(self.runner.workers, [])

    def test_authorization_is_rechecked_before_claim(self):
        self.runner.malformed["issue"] = eligible_issue(labels=[{"name": "area:app"}])
        result = self.dispatch()
        self.assertEqual(self.runner.workers, [], result)
        self.assertEqual(self.runner.clones, [], result)
        self.assertFalse(self.attempts())

    def test_process_crash_leaves_durable_pending_attempt_and_blocks_duplicate_worker(self):
        context = multiprocessing.get_context("fork")
        entered, release = context.Event(), context.Event()
        process = context.Process(target=pause_inside_worker, args=(self.config, entered, release))
        process.start()
        self.addCleanup(stop_process, process)
        self.assertTrue(entered.wait(10))
        process.terminate()
        process.join(timeout=10)
        self.assertNotEqual(process.exitcode, 0)
        self.assertIn(self.attempts()["7:101"]["status"], {"reserved", "running", "uncertain"})
        result = self.dispatch()
        self.assertIn(result["status"], {"blocked", "error", "idle"}, result)
        self.assertEqual(self.runner.workers, [])
        self.assertEqual(self.runner.clones, [])
        acknowledged = dispatcher.acknowledge(self.config, 7, 101)
        self.assertNotEqual(acknowledged["status"], "error", acknowledged)
        self.assertEqual(self.attempts()["7:101"]["status"], "uncertain")
        self.dispatch()
        self.assertEqual(self.runner.workers, [])
        self.runner.events += [ready_event(102, event="unlabeled", minute=1), ready_event(103, minute=2)]
        result = self.dispatch()
        self.assertEqual(result["status"], "returned", result)
        self.assertEqual(len(self.runner.workers), 1)
        self.assertEqual(set(self.attempts()), {"7:101", "7:103"})

    def test_existing_state_cannot_be_rebound_to_another_repository_or_actor(self):
        self.dispatch()
        before = (self.config.state_dir / "state.json").read_bytes()
        for repo, actor in (("different/repository", "michaelsena"), (self.config.repo, "different-user")):
            changed = dispatcher.Config(repo=repo, state_dir=self.config.state_dir,
                workspace_root=self.config.workspace_root, ready_actor=actor, charter_path=self.charter)
            runner = FakeRunner([eligible_issue()], [ready_event()])
            result = dispatcher.dispatch_once(changed, execute=True, runner=runner)
            with self.subTest(repo=repo, actor=actor):
                self.assertEqual(result["status"], "error", result)
                self.assertFalse(runner.workers)
                self.assertEqual((self.config.state_dir / "state.json").read_bytes(), before)

    def test_state_corruption_is_not_reset(self):
        self.dispatch(execute=False)
        state_path = self.config.state_dir / "state.json"
        corrupt = ["not-json", "[]", '{"schema_version":1,"schema_version":1}',
                   '{"schema_version":NaN}', '{"attempts":[]}']
        for raw in corrupt:
            state_path.write_text(raw)
            result = self.dispatch()
            with self.subTest(raw=raw):
                self.assertEqual(result["status"], "error", result)
                self.assertEqual(state_path.read_text(), raw)
                self.assertEqual(self.runner.workers, [])

    def test_subprocess_singleton_blocks_second_poller(self):
        context = multiprocessing.get_context("fork")
        entered, release, results = context.Event(), context.Event(), context.Queue()
        process = context.Process(target=hold_dispatcher_lock, args=(self.config, entered, release, results))
        process.start()
        self.addCleanup(stop_process, process)
        self.assertTrue(entered.wait(10))
        try:
            result = self.dispatch()
            self.assertIn(result["status"], {"blocked", "error"}, result)
            self.assertEqual(self.runner.workers, [])
            self.assertEqual(self.runner.clones, [])
        finally:
            release.set()
        process.join(timeout=10)
        self.assertEqual(process.exitcode, 0)
        self.assertEqual(results.get(timeout=5)["status"], "idle")

    def test_production_runner_preserves_literal_argv_and_stdin(self):
        sentinel = self.base / "shell-must-not-run"
        payload = "literal; touch " + str(sentinel) + " $(echo substituted)"
        code = "import json,sys; print(json.dumps([sys.argv[1], sys.stdin.read()]))"
        result = dispatcher.run_command([sys.executable, "-c", code, payload],
            input_text="untrusted stdin remains data", timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), [payload, "untrusted stdin remains data"])
        self.assertFalse(sentinel.exists())

    def test_production_worker_subprocess_inherits_the_singleton_descriptor(self):
        lock = self.base / "descriptor.lock"
        with lock.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            descriptor = handle.fileno()
            code = "import os,sys; print(os.fstat(int(sys.argv[1])).st_ino)"
            result = dispatcher.run_command([sys.executable, "-c", code, str(descriptor)],
                                            timeout=10, lock_fd=descriptor)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(int(result.stdout.strip()), lock.stat().st_ino)

    def test_timeout_kills_descendant_even_after_process_group_leader_exits(self):
        pid_file = self.base / "descendant.pid"
        held_lock = self.base / "descendant.lock"
        child = ("import fcntl,os,signal,sys,time; from pathlib import Path; "
                 "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                 "handle=open(sys.argv[2], 'a+b'); fcntl.flock(handle.fileno(), fcntl.LOCK_EX); "
                 "Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)")
        leader = ("import subprocess,sys,time; from pathlib import Path; "
                  "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2], sys.argv[3]]); "
                  "p=Path(sys.argv[2]); exec('while not p.exists(): time.sleep(0.01)')")
        with self.assertRaises(subprocess.TimeoutExpired):
            dispatcher.run_command([sys.executable, "-c", leader, child, str(pid_file), str(held_lock)], timeout=1)
        self.assertTrue(pid_file.exists())
        pid = int(pid_file.read_text())
        # A terminated descendant releases descriptors even if its PID briefly
        # remains a zombie. This avoids platform-specific process-table access.
        with held_lock.open("a+b") as handle:
            deadline = time.monotonic() + 1
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() < deadline:
                        time.sleep(0.01)
                        continue
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    self.fail("worker descendant retained its lock after timeout cleanup")

    def test_status_is_read_only_and_does_not_expose_task_content(self):
        absent = self.base / "missing-state"
        result = dispatcher.read_status(absent)
        self.assertEqual(result["status"], "empty")
        self.assertFalse(absent.exists())
        self.runner.issues[0]["body"] = "PRIVATE TASK BODY SENTINEL"
        self.dispatch()
        before = (self.config.state_dir / "state.json").read_bytes()
        result = dispatcher.read_status(self.config.state_dir)
        self.assertNotIn("PRIVATE TASK BODY SENTINEL", json.dumps(result))
        self.assertEqual(result["attempts"][0]["status"], "returned")
        self.assertEqual((self.config.state_dir / "state.json").read_bytes(), before)

    def test_argv_and_checkout_do_not_interpret_issue_text_as_shell_code(self):
        sentinel = self.base / "must-not-exist"
        dangerous = '$(touch ' + str(sentinel) + '); `echo injected`; --dangerously-bypass-approvals-and-sandbox'
        self.runner.issues[0].update(title=dangerous, body=dangerous)
        result = self.dispatch()
        self.assertEqual(result["status"], "returned", result)
        self.assertEqual(len(self.runner.workers), 1)
        worker = self.runner.workers[0]
        self.assertNotIn(dangerous, worker["argv"])
        self.assertIn(dangerous, worker["input_text"])
        self.assertFalse(any(arg in {"sh", "bash", "--dangerously-bypass-approvals-and-sandbox"} for arg in worker["argv"]))
        checkout = Path(self.attempts()["7:101"]["checkout"])
        self.assertTrue(checkout.is_relative_to(self.config.workspace_root))
        self.assertNotEqual(checkout, SCRIPT.parents[1])
        self.assertIsNotNone(worker["lock_fd"])
        self.assertFalse(sentinel.exists())


if __name__ == "__main__":
    unittest.main()
