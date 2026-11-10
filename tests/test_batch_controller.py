"""Controller tests use synthetic HTTP only; no provider credentials or spend."""
import copy
import json
import subprocess
import shutil
import unittest
from unittest.mock import patch
from pathlib import Path
from turbo.agents import batch_controller as controller, batch_workflow as workflow
from turbo.agents import batch_execution_v2 as ledger
from turbo.pipeline_paths import ROOT
import test_batch_provider as fixtures

NOW=fixtures.NOW

class ControllerTest(unittest.TestCase):
    setUpClass=classmethod(fixtures.BatchProviderTest.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.BatchProviderTest.tearDownClass.__func__)
    def setUp(self):
        fixtures.BatchProviderTest.setUp(self)
        self.publication_root=self.base/'publication-root'
        for name in ('src/turbo/universe/batch_closure.py','src/turbo/universe/graph_release.py',
                     'schemas/graph-release-config.schema.json','data/generated/latest-graph.json'):
            source=self.input_root if name.startswith('data/') else ROOT
            target=self.publication_root/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source/name,target)

    payload=fixtures.BatchProviderTest.payload
    transport_for=fixtures.BatchProviderTest.transport_for
    verifier_document=fixtures.BatchProviderTest.verifier_document
    review_document=fixtures.BatchProviderTest.review_document

    def initialize(self):
        self.control=self.base/'controller'
        self.manifest=controller.initialize(self.control,workflow_dir=self.directory,
            registry_dir=self.registry,authorization=self.authorization,input_root=self.input_root.resolve(),
            preparation_dirs=[Path(p).resolve() for p in self.preparations],root=self.publication_root)

    def transport(self,url,headers,raw,timeout):
        role=json.loads(raw)['model'].split('/')[-1]
        if role=='primary': document={'payload':self.payload()}
        elif role=='verifier': document=self.verifier_document()
        else:document=self.review_document(ledger._read(self.directory/'release-preview.json'))
        return self.transport_for(document)(url,headers,raw,timeout)

    def execute(self,**kwargs):
        return controller.execute(self.control,api_key='synthetic-only',clock=lambda:NOW,
                                  transport=self.transport,**kwargs)

    def config(self):
        return {'schema_version':1,'recorded_at_utc':NOW,
            'execution_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'graph_base_sha256':self.context['families'][0]['pack_metadata']['graph_projection_sha256'],
            'families':[{'family_id':f['family_id'],'outcome':'reviewed_no_graph_movement',
                'reason':'Controlled integration preserves explicit unresolved research gaps.',
                'proposals':[],'mappings':[]} for f in self.context['families']]}

    def test_serial_wait_review_repeat_and_provenance(self):
        self.initialize()
        before=sorted(str(p) for p in self.base.rglob('*'))
        self.assertEqual(controller.status(self.control,clock=lambda:NOW)['role'],'primary')
        self.assertEqual(before,sorted(str(p) for p in self.base.rglob('*')))
        self.assertEqual(self.execute()['state'],'WAITING_RELEASE_CONFIG')
        self.assertEqual(len(self.calls),2)
        config=self.base/'config.json';ledger._write(config,self.config())
        result=self.execute(release_config=config)
        self.assertEqual(result['state'],'APPROVED_PENDING_PUBLICATION',result)
        self.assertFalse(result['canonical_published']);self.assertEqual(len(self.calls),3)
        self.assertEqual(self.execute()['state'],'APPROVED_PENDING_PUBLICATION')
        self.assertEqual(len(self.calls),3)
        envelope=ledger._read(self.directory/'release_reviewer.json')
        envelope['document']['findings']=[{'finding_id':'synthetic','status':'resolved','rationale':'Altered valid review.'}]
        envelope['submission_sha256']=workflow._hash({k:v for k,v in envelope.items() if k!='submission_sha256'})
        (self.directory/'release_reviewer.json').write_text(json.dumps(envelope))
        with self.assertRaisesRegex(ValueError,'provenance'):controller.status(self.control,clock=lambda:NOW)
        self.assertEqual(len(self.calls),3)

    def test_crash_after_settlement_replays_without_resend(self):
        self.initialize(); real=workflow.submit
        def crash(directory,role,*args,**kwargs):
            if directory==self.directory and role=='primary':raise RuntimeError('sensitive failure detail')
            return real(directory,role,*args,**kwargs)
        with patch.object(workflow,'submit',side_effect=crash):
            stopped=self.execute()
        self.assertEqual(stopped['state'],'STOPPED');self.assertNotIn('sensitive',json.dumps(stopped))
        self.assertEqual(len(self.calls),1)
        self.assertTrue(controller.status(self.control,clock=lambda:NOW)['replay_only'])
        self.assertEqual(self.execute()['state'],'WAITING_RELEASE_CONFIG')
        self.assertEqual(len(self.calls),2)

    def test_manifest_owner_and_release_config_bindings(self):
        self.initialize()
        with self.assertRaisesRegex(ValueError,'already has controller'):
            controller.initialize(self.base/'other',workflow_dir=self.directory,registry_dir=self.registry,
                authorization=self.authorization,input_root=self.input_root.resolve(),preparation_dirs=[Path(p).resolve() for p in self.preparations],root=self.publication_root)
        fresh=copy.deepcopy(self.authorization);fresh['authorized_by']='another-controlled-authority'
        with self.assertRaisesRegex(ValueError,'workflow already has controller'):
            controller.initialize(self.base/'other',workflow_dir=self.directory,registry_dir=self.registry,
                authorization=fresh,input_root=self.input_root.resolve(),
                preparation_dirs=[Path(p).resolve() for p in self.preparations],root=self.publication_root)
        altered=copy.deepcopy(self.manifest);altered['base_pointer_sha256']='a'*64
        altered['manifest_sha256']=ledger._hash({k:v for k,v in altered.items() if k!='manifest_sha256'})
        (self.control/'manifest.json').write_text(json.dumps(altered))
        with self.assertRaisesRegex(ValueError,'claim changed'):controller.status(self.control,clock=lambda:NOW)
        (self.control/'manifest.json').write_text(json.dumps(self.manifest))
        config=self.base/'config.json';ledger._write(config,self.config())
        with patch.object(controller,'_state',return_value={'state':'WAITING_RELEASE_CONFIG'}):self.execute(release_config=config)
        value=ledger._read(self.control/'release-config.json');value['config']['recorded_at_utc']='2026-11-09T17:01:00Z'
        value['config_sha256']=ledger._hash(value['config'])
        (self.control/'release-config.json').write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'binding changed'):controller.status(self.control,clock=lambda:NOW)

    def test_stops_for_attempt_boundaries_expiry_and_base(self):
        self.initialize()
        for state in ('reserved','dispatched','unresolved','failed'):
            with self.subTest(state=state),patch.object(controller,'_journal',return_value={'requests':{
                self.manifest['attempt_ids']['primary']:{'role':'primary','status':state}}}):
                self.assertEqual(controller.status(self.control,clock=lambda:NOW)['reason'],'attempt_'+state)
        self.assertEqual(controller.status(self.control,clock=lambda:'2026-11-09T19:00:00Z')['reason'],'authorization_outside_interval')
        with patch.object(controller,'_base',return_value='changed'):
            self.assertEqual(controller.status(self.control,clock=lambda:NOW)['reason'],'canonical_base_changed')
        with patch.object(controller,'_journal',return_value={'requests':{},'calls_reserved':6,'committed_microusd':0}):
            self.assertEqual(controller.status(self.control,clock=lambda:NOW)['reason'],'authorization_exhausted')
        self.assertEqual(self.calls,[])

    def test_conditional_blind_pair_routing(self):
        self.initialize()
        for completed,expected in ((['primary','verifier'],'escalation_a'),
                                   (['primary','verifier','escalation_a'],'escalation_b')):
            records={self.manifest['attempt_ids'][r]:{'role':r,'status':'succeeded'} for r in completed}
            with patch.object(controller,'_journal',return_value={'requests':records,'calls_reserved':len(records),'committed_microusd':0}), \
                 patch.object(controller,'_verify_submissions'), \
                 patch.object(workflow,'inspect_workflow',return_value={'status':'escalation_pending','completed_roles':completed}):
                self.assertEqual(controller.status(self.control,clock=lambda:NOW)['role'],expected)

    def test_initialize_rejects_stale_canonical_base_before_writes(self):
        with patch.object(controller,'_base',side_effect=['current','frozen']):
            with self.assertRaisesRegex(ValueError,'frozen canonical base'):
                self.initialize()
        self.assertFalse(self.control.exists())
        self.assertEqual(self.calls,[])
