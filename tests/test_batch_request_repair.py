"""Explicit aggregate amendment tests; all transports are synthetic."""
import copy
import json
import unittest
from unittest.mock import patch

import test_batch_provider as fixtures
from turbo.agents import batch_provider as provider, batch_execution_v2 as ledger
from turbo.agents import batch_release_recovery as prior, batch_request_repair as repair


class RequestRepairTest(unittest.TestCase):
    setUpClass=classmethod(fixtures.BatchProviderTest.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.BatchProviderTest.tearDownClass.__func__)
    payload=fixtures.BatchProviderTest.payload
    transport_for=fixtures.BatchProviderTest.transport_for
    run_role=fixtures.BatchProviderTest.run_role
    verifier_document=fixtures.BatchProviderTest.verifier_document
    compiled_preview=fixtures.BatchProviderTest.compiled_preview
    review_document=fixtures.BatchProviderTest.review_document

    def setUp(self):
        fixtures.BatchProviderTest.setUp(self)
        # Synthetic historical implementations use this test tree. Production
        # constants remain pinned to the real released predecessor contracts.
        for module,name in ((prior,'PREDECESSOR_CONTRACT'),(repair,'PINNED_PROVIDER_CONTRACT')):
            mocked=patch.object(module,name,provider.execution_contract_hashes());mocked.start();self.addCleanup(mocked.stop)

    def chain(self):
        self.assertEqual(self.run_role('primary',{'payload':self.payload()})['status'],'succeeded')
        self.assertEqual(self.run_role('verifier',self.verifier_document())['status'],'succeeded')
        self.preview=self.compiled_preview()
        reject=lambda *args:(400,{},b'{"error":{"message":"controlled"}}')
        options=dict(input_root=self.input_root,api_key='synthetic-secret',clock=lambda:fixtures.NOW,transport=reject)
        self.assertEqual(provider.run_batch_role(self.directory,self.registry,self.authorization,'release_reviewer','old-release',**options)['status'],'unresolved')
        first,cp=prior.prepare_successor(self.registry,self.authorization,workflow_dir=self.directory,input_root=self.input_root,
            replacement_attempt_id='first-replacement',authorized_by='first explicit',valid_from_utc='2026-11-09T16:00:00Z',expires_at_utc='2026-11-09T18:00:00Z')
        claim=prior.claim_successor(self.registry,first,cp)
        self.assertEqual(provider.run_batch_role(self.directory,self.registry,first,'release_reviewer','first-replacement',recovery_checkpoint=claim,**options)['status'],'unresolved')
        auths=[self.authorization,first]
        engines=[ledger.BatchExecutionV2(self.registry,a) for a in auths]
        for ordinal,name in enumerate(repair.DIAGNOSTIC_CLAIMS):
            states=[e.status() for e in engines];paid,held,calls=repair._totals(states)
            plan=dict(purpose='diagnostic_only_never_release',source_authorizations=[ledger._hash(a) for a in auths],
                source_event_hashes=[repair._tip(e) for e in engines],carried_exposure_microusd=paid+held,
                carried_calls=calls,request_sha256='1'*64,max_probe_cost_microusd=200)
            if ordinal:plan['adaptation']='omit_only_findings_maxItems_google_probe'
            auth=ledger.build_authorization(workflow_plan_sha256=ledger._hash(plan),roles=self.authorization['roles'],
                authorized_by='controlled diagnostic',valid_from_utc='2026-11-09T16:00:00Z',expires_at_utc='2026-11-09T18:00:00Z',
                max_calls=1,max_cost_microusd=200,execution_contract_hashes=provider.execution_contract_hashes())
            ledger._write(self.registry/name,{'plan':plan,'authorization_sha256':ledger._hash(auth)})
            engine=ledger.BatchExecutionV2(self.registry,auth,clock=lambda:fixtures.NOW)
            result=engine.run('release_reviewer','probe-'+str(ordinal),lambda _: {'invalid':'unresolved'},input_sha256=ledger._hash(plan))
            self.assertEqual(result['status'],'unresolved')
            auths.append(auth);engines.append(engine)
        self.engines=engines

    def prepare(self,replacement='corrected-review',cap=1200,calls=7):
        return repair.prepare_successor(self.registry,self.authorization,workflow_dir=self.directory,input_root=self.input_root,
            replacement_attempt_id=replacement,authorized_by='explicit aggregate amendment',valid_from_utc='2026-11-09T16:00:00Z',
            expires_at_utc='2026-11-09T18:00:00Z',aggregate_max_cost_microusd=cap,aggregate_max_calls=calls)

    def test_full_chain_preserved_and_one_corrected_review_replays(self):
        self.chain();before=[(e.journal_path/'events.jsonl').read_bytes() for e in self.engines]
        documents={name:(self.directory/name).read_bytes() for name in ('primary.json','verifier.json','release-preview.json')}
        auth,cp=self.prepare()
        self.assertEqual(auth['max_cost_microusd'],360)
        self.assertEqual(auth['max_calls'],1)
        self.assertEqual((cp['carried_paid_microusd'],cp['retained_unknown_microusd'],cp['carried_physical_calls']),(40,800,6))
        path=repair.claim_successor(self.registry,auth,cp)
        self.assertEqual(repair.claim_successor(self.registry,auth,cp),path)
        options=dict(input_root=self.input_root,api_key='synthetic-secret',clock=lambda:fixtures.NOW,
            recovery_checkpoint=path,transport=self.transport_for(self.review_document(self.preview)))
        result=provider.run_batch_role(self.directory,self.registry,auth,'release_reviewer','corrected-review',**options)
        self.assertEqual(result['status'],'succeeded');count=len(self.calls)
        self.assertEqual(provider.run_batch_role(self.directory,self.registry,auth,'release_reviewer','corrected-review',**options),result)
        self.assertEqual(len(self.calls),count)
        self.assertEqual(before,[(e.journal_path/'events.jsonl').read_bytes() for e in self.engines])
        self.assertEqual(documents,{name:(self.directory/name).read_bytes() for name in documents})

    def test_no_unaccounted_authority_or_diagnostic_omission(self):
        self.chain();path=self.registry/repair.DIAGNOSTIC_CLAIMS[1];claim=json.loads(path.read_text())
        bad=copy.deepcopy(claim);bad['plan']['carried_calls']-=1;path.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError,'preceding exposure'):self.prepare()
        path.write_text(json.dumps(claim))
        with self.assertRaisesRegex(ValueError,'exactly one'):self.prepare(calls=6)
        with self.assertRaisesRegex(ValueError,'cannot reserve'):self.prepare(cap=900)
        with self.assertRaisesRegex(ValueError,'already used'):self.prepare(replacement='probe-0')
        extra=self.registry/'claims'/('f'*64+'.json');extra.write_text('{}')
        with self.assertRaisesRegex(ValueError,'unaccounted authority'):self.prepare()

    def test_no_fork_changed_cap_or_upstream_redispatch(self):
        self.chain();auth,cp=self.prepare()
        extra=self.registry/'claims'/('f'*64+'.json')
        real_expected=repair._expected
        def insert_after_prepare(*args,**kwargs):
            result=real_expected(*args,**kwargs);extra.write_text('{}');return result
        with patch.object(repair,'_expected',side_effect=insert_after_prepare):
            with self.assertRaisesRegex(ValueError,'unaccounted authority'):
                repair.claim_successor(self.registry,auth,cp)
        extra.unlink()
        path=repair.claim_successor(self.registry,auth,cp)
        other_auth,other_cp=self.prepare(replacement='other-review')
        with self.assertRaisesRegex(ValueError,'already claimed'):repair.claim_successor(self.registry,other_auth,other_cp)
        changed=copy.deepcopy(auth);changed['max_cost_microusd']+=1
        with self.assertRaisesRegex(ValueError,'bound'):repair.claim_successor(self.registry,changed,cp)
        engine=repair.RequestRepairExecution(self.registry,auth,path,clock=lambda:fixtures.NOW)
        extra=self.registry/'claims'/('f'*64+'.json');extra.write_text('{}')
        with self.assertRaisesRegex(ValueError,'unaccounted authority'):
            engine.run('release_reviewer','corrected-review',lambda _:self.fail('must not dispatch'),input_sha256='0'*64)
        extra.unlink()
        for role,attempt in [('primary','another'),('verifier','another'),('release_reviewer','wrong')]:
            with self.assertRaises(ValueError):engine.run(role,attempt,lambda _:self.fail('must not dispatch'),input_sha256='0'*64)
        bad=copy.deepcopy(cp);bad['input_root']='/changed';path.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError,'bound'):repair.RequestRepairExecution(self.registry,auth,path)


class ProductionContractTest(unittest.TestCase):
    def test_unrecognized_original_contract_rejected_before_paths(self):
        self.assertNotEqual(prior.PREDECESSOR_CONTRACT, {'unrecognized': '0'*64})
        with self.assertRaisesRegex(ValueError, 'unsupported original execution contract'):
            repair._sources('/nonexistent-registry',
                {'execution_contract_hashes': {'unrecognized': '0'*64}},
                '/nonexistent-workflow', '/nonexistent-input')


if __name__=='__main__':unittest.main()
