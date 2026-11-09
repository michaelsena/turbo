"""Narrow operational runner tests: no model or network calls."""
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from turbo.agents.batch_authorization import canonical_bytes
from turbo.agents.batch_output import DEFAULT_MAX_CONTEXT_BYTES, DEFAULT_MAX_OUTPUT_BYTES, PROMPT_PATH, SCHEMA_PATH
from turbo.pipeline_paths import ROOT
import hashlib

spec = importlib.util.spec_from_file_location('live_batch_runner', ROOT / 'scripts/run-codex-batch.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LiveBatchRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.context = {'request_id':'real-batch-1','invocation_id':'invocation:'+'1'*24,
            'context_sha256':'a'*64,'input_bindings':[],'families':[],
            'prompt_sha256':hashlib.sha256((ROOT/PROMPT_PATH).read_bytes()).hexdigest(),
            'output_schema_sha256':hashlib.sha256((ROOT/SCHEMA_PATH).read_bytes()).hexdigest(),
            'limits':{'max_output_bytes':DEFAULT_MAX_OUTPUT_BYTES,'max_context_bytes':DEFAULT_MAX_CONTEXT_BYTES}}
        self.path=self.base/'context.json'
        self.path.write_bytes(canonical_bytes(self.context))

    def invoke(self, runner):
        with patch.object(module,'build_batch_context',return_value=self.context), patch.object(module,'validate_batch_output_file',return_value={'valid':True,'errors':[]}):
            def wrapped(argv, **kwargs):
                if argv == ['codex', '--version']:
                    return subprocess.CompletedProcess(argv,0,'codex-cli 0.147.0\n','')
                return runner(argv, **kwargs)
            return module.run_batch(self.path,[],self.base/'runs',root=ROOT,runner=wrapped)

    def test_durable_receipt_and_single_dispatch(self):
        calls=[]
        def fake(argv,**kwargs):
            calls.append(argv)
            receipt=json.loads(next((self.base/'runs').glob('*/run-receipt.json')).read_text())
            self.assertEqual(receipt['status'],'in_progress')
            self.assertIn('--ephemeral',argv); self.assertIn('read-only',argv); self.assertNotIn('-m',argv)
            Path(argv[argv.index('--output-last-message')+1]).write_text('{}')
            return subprocess.CompletedProcess(argv,0,'{"type":"turn.completed","usage":{"input_tokens":3,"output_tokens":4}}\n','secret-do-not-persist')
        result=self.invoke(fake)
        self.assertEqual(result['status'],'valid')
        self.assertEqual(result['usage']['output_tokens'],4)
        with self.assertRaises(FileExistsError): self.invoke(fake)
        self.assertEqual(len(calls),1)
        self.assertNotIn('secret-do-not-persist',Path(result['receipt_path']).read_text())

    def test_timeout_is_durable_and_never_retried(self):
        def fake(argv,**kwargs): raise subprocess.TimeoutExpired(argv,1)
        result=self.invoke(fake)
        self.assertEqual(result['status'],'uncertain')
        with self.assertRaises(FileExistsError): self.invoke(fake)

    def test_context_mismatch_never_invokes(self):
        tampered={**self.context,'context_sha256':'b'*64}
        self.path.write_bytes(canonical_bytes(tampered))
        with patch.object(module,'build_batch_context',return_value=self.context):
            with self.assertRaises(ValueError):
                module.run_batch(self.path,[],self.base/'runs',runner=lambda *_a,**_kw:self.fail('invoked'))
        self.assertFalse((self.base/'runs').exists())

    def test_failed_cli_retains_only_sanitized_failure(self):
        result=self.invoke(lambda argv,**kwargs:subprocess.CompletedProcess(argv,1,'private reasoning','secret'))
        self.assertEqual(result['status'],'failed')
        text=Path(result['receipt_path']).read_text()
        self.assertNotIn('private reasoning',text);self.assertNotIn('secret',text)


if __name__=='__main__':unittest.main()
