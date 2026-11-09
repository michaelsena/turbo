"""Compiler tests use a validated-stage seam; workflow integration tests exercise real V2 inputs."""
import copy
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from turbo.universe import batch_closure as bc
from turbo.agents.boundary_harness import canonical_sha256
from turbo.pipeline_paths import ROOT

ORIGINAL_BASE = bc._base
ORIGINAL_SOURCE_DATA = bc._source_data


class BatchClosureTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.temp = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.base = {'as_of': '2026-01-01T00:00:00Z', 'markets': [], 'mappings': []}
        self.pointer = {'projection_sha256': 'a'*64, 'source_universe_run_id': 'run-'+'b'*20}
        self.stack.enter_context(patch.object(bc, '_base', side_effect=lambda s, **kw:(self.pointer,self.base,[])))
        self.stack.enter_context(patch.object(bc, '_source_data', return_value=({'source:1'},{'candidate:1'},{})))
        self.stack.enter_context(patch.object(bc, '_contract', return_value={'compiler':'fixed'}))
        dimensions = {k:{'statement':'Evidence remains limited', 'confidence':0.4, 'evidence_label':'unknown'} for k in bc.DIMENSIONS}
        proposal = {'proposal_id':'p1','canonical_name':'Example manufacturing','definition':'Produces example equipment',
                    'boundary':'Production only','explicit_exclusions':['Installation services'],'dimensions':dimensions,
                    'supporting_evidence_ids':['e1'],'counterevidence_ids':[], 'related_graph_market_ids':[]}
        disp = {'identity_id':'i1','proposal_ids':['p1'],'disposition':'provisional_map','gap_id':'g1',
                'supporting_evidence_ids':['e1'],'counterevidence_ids':[]}
        family = {'family_id':'f1','proposed_markets':[proposal], 'identity_dispositions':[disp],
                  'candidate_dispositions':[{'candidate_market_id':'candidate:1','proposal_ids':[],
                                             'disposition':'reject','gap_id':None}],
                  'research_gaps':[{'gap_id':'g1','description':'Missing economics evidence'}]}
        frozen = {'family_id':'f1','required_identity_ids':['i1'],'required_candidate_ids':['candidate:1'],
                  'evidence_catalog':[{'evidence_id':'e1','value':{'source_record_ids':['source:1']},
                                       'subject_ids':['i1'],'json_pointer':'/identities/0'}]}
        self.stage={'plan':{'input_root':str(self.temp),'plan_sha256':'c'*64,
                            'actors':{'primary':'primary-worker','adjudicator':'escalation-worker','release_reviewer':'independent'}},
                    'context':{'families':[frozen]}, 'submissions':{}, 'final_role':'primary',
                    'final_submission_sha256':'d'*64,'final_payload':{'families':[family]}}
        self.config={'schema_version':1,'recorded_at_utc':'2026-11-09T00:00:00Z', 'execution_commit':'e'*40,
                     'graph_base_sha256':'a'*64,'families':[{'family_id':'f1','outcome':'activate','reason':'Reviewed boundaries',
                     'proposals':[{'proposal_id':'p1','activation_status':'provisional'}],
                     'mappings':[{'identity_id':'i1','proposal_id':'p1','relationship_type':'partial_overlap'}]}]}

    def compile(self):
        return bc._compile(self.stage,self.config,root=ROOT)

    def approve(self, preview):
        wrapper={'plan_sha256':self.stage['plan']['plan_sha256'],
                 'final_submission_sha256':self.stage['final_submission_sha256'],
                 'preview':preview,'preview_sha256':bc.workflow._hash(preview)}
        (self.temp/'release-preview.json').write_text(json.dumps(wrapper))
        self.stage['submissions']['release_reviewer']={'submission_sha256':'f'*64,'document':{
            'verdict':'approve','approved_plan_sha256':wrapper['preview_sha256']}}
        self.stack.enter_context(patch.object(bc.workflow,'verified_stage',return_value=self.stage))
        return wrapper

    def test_explicit_relationship_provisional_status_and_full_lineage_survive(self):
        preview=self.compile()
        self.assertEqual(preview['status'],'planned_not_activated')
        self.assertEqual([e['event_type'] for e in preview['movements']],['create_market','map'])
        self.assertEqual(preview['movements'][1]['relationship_type'],'partial_overlap')
        self.assertEqual(preview['projection']['markets'][0]['activation_status'],'provisional')
        self.assertEqual(preview['family_lineage'],self.stage['final_payload']['families'])
        self.assertFalse(any(e['event_type']=='reject_candidate' for e in preview['movements']))
        self.assertEqual(preview['movements'][0]['review']['proposer'],'primary-worker')
        self.assertEqual(len(preview['cumulative_projection']['markets']),1)

    def test_escalation_uses_effective_actor_and_submission(self):
        self.stage['final_role']='adjudicator'
        self.assertEqual(self.compile()['movements'][0]['review']['proposer'],'escalation-worker')

    def test_mapping_relationship_required_no_inferred_equivalence(self):
        del self.config['families'][0]['mappings'][0]['relationship_type']
        with self.assertRaises(ValueError): self.compile()

    def test_cannot_upgrade_provisional_mapping(self):
        self.config['families'][0]['proposals'][0]['activation_status']='accepted_with_gaps'
        with self.assertRaisesRegex(ValueError,'promote'): self.compile()

    def test_existing_graph_conflicts_block(self):
        for field,value in [('markets',[{'canonical_name':'Example manufacturing'}]),('mappings',[{'identity_id':'i1'}])]:
            with self.subTest(field=field):
                self.base[field]=value
                with self.assertRaisesRegex(ValueError,'conflict'):self.compile()
                self.base[field]=[]
        self.stage['final_payload']['families'][0]['proposed_markets'][0]['related_graph_market_ids']=['market:existing']
        with self.assertRaisesRegex(ValueError,'conflict'):self.compile()

    def test_missing_or_duplicate_family_and_mapping_block(self):
        original=copy.deepcopy(self.config)
        for mutate in [lambda c:c['families'].clear(), lambda c:c['families'].append(copy.deepcopy(c['families'][0])),
                       lambda c:c['families'][0]['mappings'].clear()]:
            self.config=copy.deepcopy(original);mutate(self.config)
            with self.assertRaises(ValueError):self.compile()

    def test_zero_proposals_cannot_activate(self):
        self.stage['final_payload']['families'][0]['proposed_markets']=[]
        self.config['families'][0]['proposals']=[]
        with self.assertRaises(ValueError):self.compile()

    def test_pending_proposals_must_retry_not_no_movement(self):
        row=self.config['families'][0];row.update(outcome='reviewed_no_graph_movement',proposals=[],mappings=[])
        with self.assertRaises(ValueError):self.compile()
        row['outcome']='retry_required'
        self.assertEqual(self.compile()['movements'],[])

    def test_no_movement_closure_replays_and_tamper_fails(self):
        family=self.stage['final_payload']['families'][0]
        family['proposed_markets']=[];family['identity_dispositions'][0].update(proposal_ids=[],disposition='unresolved')
        self.config['families'][0].update(outcome='reviewed_no_graph_movement',proposals=[],mappings=[])
        self.approve(self.compile())
        result=bc.finalize_batch_closure(self.temp,output_root=self.temp/'closures',root=ROOT)
        self.assertEqual(result['families'][0]['status'],'reviewed_no_graph_movement')
        self.assertIsNone(result['graph_release'])
        dest=Path(result['closure_dir'])
        self.assertTrue(bc.validate_batch_closure(dest,self.temp,root=ROOT)['valid'])
        (dest/'closure.json').write_text('{}')
        self.assertFalse(bc.validate_batch_closure(dest,self.temp,root=ROOT)['valid'])

    def test_movement_not_activated_without_persisted_release(self):
        self.approve(self.compile())
        with self.assertRaisesRegex(ValueError,'persisted cumulative'):
            bc.finalize_batch_closure(self.temp,output_root=self.temp/'closures',root=ROOT)
        self.assertFalse((self.temp/'closures').exists())

    def test_approval_and_compiler_preview_tampering_rejected(self):
        self.approve(self.compile())
        self.stage['submissions']['release_reviewer']['document']['approved_plan_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'exact independent'):bc._approved(self.temp,root=ROOT)
        self.stage['submissions']['release_reviewer']['document']['approved_plan_sha256']=bc.workflow._hash(self.compile())
        self.config['families'][0]['reason']='mutated'
        wrapper=json.loads((self.temp/'release-preview.json').read_text());wrapper['preview']['movements'][0]['activation_status']='accepted'
        wrapper['preview_sha256']=bc.workflow._hash(wrapper['preview'])
        (self.temp/'release-preview.json').write_text(json.dumps(wrapper))
        with self.assertRaisesRegex(ValueError,'cannot replay'):bc._approved(self.temp,root=ROOT)

    def test_persistence_requires_clean_reviewed_commit(self):
        self.approve(self.compile())
        with patch('turbo.universe.graph_release._git_worktree_clean',return_value=False):
            with self.assertRaisesRegex(ValueError,'exact clean'):
                bc.persist_batch_activation(self.temp,output_root=self.temp/'events',root=ROOT)

    def test_persisted_activation_replays_exact_approval_and_detects_tamper(self):
        self.approve(self.compile())
        with patch('turbo.universe.graph_release._git_worktree_clean',return_value=True), \
             patch('turbo.universe.graph_release._git_head',return_value='e'*40), \
             patch('turbo.universe.graph_release._git_commit_exists',return_value=True):
            result=bc.persist_batch_activation(self.temp,output_root=self.temp/'events',root=ROOT)
        dest=Path(result['activation_dir']);config=dest/'activation-config.json'
        self.assertTrue(bc.validate_batch_activation(dest,config,root=ROOT)['valid'])
        self.assertEqual(result['status'],'persisted_approved_batch_events')
        rows=json.loads((dest/'events.json').read_text());rows[1]['relationship_type']='equivalent_label_candidate'
        (dest/'events.json').write_text(json.dumps(rows))
        self.assertFalse(bc.validate_batch_activation(dest,config,root=ROOT)['valid'])

    def test_relocated_input_reads_and_workflow_overrides_preserve_plan(self):
        import gzip
        import hashlib
        relocated=self.temp/'relocated-input';preps=[relocated/'prep']
        run=relocated/'data/runs'/self.pointer['source_universe_run_id'];run.mkdir(parents=True)
        raw=gzip.compress(json.dumps({'source_records':[{'record_id':'source:1'}],
            'candidate_markets':[{'candidate_market_id':'candidate:1'}]}).encode())
        (run/'multisource-reconciliation.json.gz').write_bytes(raw)
        (run/'run-receipt.json').write_text(json.dumps({'run_id':self.pointer['source_universe_run_id'],
            'output_hashes':{'multisource-reconciliation.json.gz':hashlib.sha256(raw).hexdigest()}}))
        self.stage['context']['families'][0]['pack_metadata']={'graph_projection_sha256':'a'*64}
        family=self.stage['final_payload']['families'][0]
        family['proposed_markets']=[];family['identity_dispositions'][0].update(proposal_ids=[],disposition='unresolved')
        self.config['families'][0].update(outcome='reviewed_no_graph_movement',proposals=[],mappings=[])
        recorded_plan=copy.deepcopy(self.stage['plan'])
        def graph(*,root):
            self.assertEqual(root,relocated)
            return self.pointer,{'activation_bindings':[]},self.base
        def verified(directory,**kw):
            self.assertEqual(kw,{'input_root':relocated,'preparation_dirs':preps})
            return self.stage
        def bind(directory,preview,**kw):
            self.assertEqual(kw,{'input_root':relocated,'preparation_dirs':preps})
            return {'plan_sha256':self.stage['plan']['plan_sha256'],
                    'final_submission_sha256':self.stage['final_submission_sha256'],
                    'preview':preview,'preview_sha256':bc.workflow._hash(preview)}
        with patch.object(bc,'_base',wraps=ORIGINAL_BASE), \
             patch.object(bc,'_source_data',wraps=ORIGINAL_SOURCE_DATA), \
             patch.object(bc,'_verified_graph',side_effect=graph), \
             patch.object(bc.workflow,'verified_stage',side_effect=verified), \
             patch.object(bc.workflow,'bind_release_preview',side_effect=bind):
            wrapper=bc.prepare_batch_release(self.temp,self.config,root=ROOT,input_root=relocated,preparation_dirs=preps)
            (self.temp/'release-preview.json').write_text(json.dumps(wrapper))
            self.stage['submissions']['release_reviewer']={'submission_sha256':'f'*64,'document':{
                'verdict':'approve','approved_plan_sha256':wrapper['preview_sha256']}}
            result=bc.finalize_batch_closure(self.temp,output_root=self.temp/'closures',root=ROOT,
                input_root=relocated,preparation_dirs=preps)
            self.assertTrue(bc.validate_batch_closure(Path(result['closure_dir']),self.temp,root=ROOT,
                input_root=relocated,preparation_dirs=preps)['valid'])
        self.assertEqual(self.stage['plan'],recorded_plan)

    def test_additive_cumulative_adapter_binds_exact_prior_events(self):
        import gzip
        import hashlib
        from turbo.universe.graph_release import compile_graph_release
        preview=self.compile()
        root=self.temp/'release-root';(root/'schemas').mkdir(parents=True)
        (root/'schemas/graph-release-config.schema.json').write_bytes((ROOT/'schemas/graph-release-config.schema.json').read_bytes())
        run=root/'data/runs'/self.pointer['source_universe_run_id'];run.mkdir(parents=True)
        raw=gzip.compress(json.dumps({'source_records':[{'record_id':'source:1'}],
            'candidate_markets':[{'candidate_market_id':'candidate:1'}]}).encode())
        (run/'multisource-reconciliation.json.gz').write_bytes(raw)
        (run/'run-receipt.json').write_text(json.dumps({'run_id':self.pointer['source_universe_run_id'],
            'output_hashes':{'multisource-reconciliation.json.gz':hashlib.sha256(raw).hexdigest()}}))
        activation=root/'activation';activation.mkdir()
        receipt={'activation_id':preview['activation_id'],'events_sha256':canonical_sha256(preview['movements']),
            'projection_sha256':canonical_sha256(preview['projection']),'activation_config_sha256':'f'*64,
            'source_universe_run_id':self.pointer['source_universe_run_id'],
            'required_base_event_ids':[],'required_base_events_sha256':canonical_sha256([])}
        (activation/'events.json').write_text(json.dumps(preview['movements']))
        (activation/'activation-receipt.json').write_text(json.dumps(receipt))
        config={'schema_version':1,'release_name':'batch-test','source_universe_run_id':receipt['source_universe_run_id'],
            'as_of_utc':self.config['recorded_at_utc'],'activations':[{'kind':'batch',
            **{k:receipt[k] for k in ['activation_id','events_sha256','projection_sha256','activation_config_sha256']},
            'activation_dir':'activation','activation_config':'activation/config.json'}],
            'prohibited_actions':['target-universe filtering','market evaluation or scoring',
            'company discovery or evaluation','model invocation']}
        path=root/'release.json';path.write_text(json.dumps(config))
        with patch.object(bc,'validate_batch_activation',return_value={'valid':True}) as replay:
            compiled=compile_graph_release(path,execution_commit='e'*40,root=root,
                input_root=self.temp/'relocated',preparation_dirs=[self.temp/'prep'])
            replay.assert_called_once_with(activation,activation/'config.json',root=root,
                input_root=self.temp/'relocated',preparation_dirs=[self.temp/'prep'])
            self.assertEqual(compiled['activation_bindings'][0]['kind'],'batch')
            self.assertEqual(len(compiled['projection']['markets']),1)
            receipt['required_base_event_ids']=['missing-prior-event']
            (activation/'activation-receipt.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'exact reviewed cumulative base'):
                compile_graph_release(path,execution_commit='e'*40,root=root)
        with patch.object(bc,'validate_batch_activation',return_value={'valid':False,'errors':['bad approval']}):
            with self.assertRaisesRegex(ValueError,'failed replay'):
                compile_graph_release(path,execution_commit='e'*40,root=root)


if __name__=='__main__':unittest.main()
