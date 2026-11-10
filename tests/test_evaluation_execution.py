"""Real ledger/transport/replay, synthetic evidence only; no live credentials."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from turbo.agents import evaluation_execution as runtime, evaluation_scores as scores
from turbo.agents import governed_eligibility as eligibility, batch_execution_v2 as ledger

NOW='2026-11-10T12:00:00Z'

class ExecutionTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve();self.root=self.base/'canonical';(self.root/'config').mkdir(parents=True)
        self.mid='market-version:synthetic-reviewed';self.mids=[self.mid];self.calls=[];self.amounts={'evaluator_a':3,'evaluator_b':3.2,'adjudicator':3.5}
        self.strategy=json.loads((runtime.ROOT/'config/strategy.json').read_text())
        (self.root/'config/strategy.json').write_bytes(runtime._bytes(self.strategy))
        projection={'as_of':'2026-11-09T00:00:00Z','markets':[{'market_version_id':self.mid,'canonical_name':'Synthetic reviewed fixture'}]}
        self.mock=patch.object(eligibility,'_canonical_graph',return_value=(self.root,projection));self.canonical=self.mock.start();self.addCleanup(self.mock.stop)
        self.eligible=self.make_unit('eligibility',runtime.ELIGIBILITY_KIND)

    def artifact(self,directory,plan,key,document):
        name=key+'.json';path=directory/name;path.write_bytes(runtime._bytes(document));plan[key]=name;plan['files'][name]=runtime.packaging._file_sha(path)

    def make_unit(self,name,kind,descriptor=None):
        directory=self.base/name;directory.mkdir();registry=self.base/(name+'-registry');ledger.initialize_registry(registry)
        plan={'schema_version':1,'kind':kind,'market_version_ids':list(self.mids),'evidence_cutoff':NOW,
              'tasks':{},'task_slots':{'eligibility':'primary'} if kind==runtime.ELIGIBILITY_KIND else runtime.EVALUATION_SLOTS,
              'files':{},'code':runtime.contracts(),'registry_path':str(registry)}
        self.artifact(directory,plan,'graph',{'private_test_verifier':'only patched in this test'})
        self.artifact(directory,plan,'strategy',self.strategy)
        source=directory/'source.txt';source.write_text('Synthetic source supports testing governed market research.\n')
        plan['files']['source.txt']=runtime.packaging._file_sha(source)
        evidence={'schema_version':1,'items':[{'evidence_id':'evidence:one','market_version_ids':list(self.mids),
            'source_path':'source.txt','source_sha256':plan['files']['source.txt'],'source_url':'https://example.test/source',
            'retrieved_at':'2026-11-09T00:00:00Z','statement':'Synthetic source supports testing governed market research.'}],
            'claims':[{'claim_id':'claim:one','market_version_ids':list(self.mids),'label':'inference',
                       'statement':'Synthetic test inference.','evidence_ids':['evidence:one'],'gap_ids':['gap:one']}],
            'gaps':[{'gap_id':'gap:one','market_version_ids':list(self.mids),'question':'What evidence would change the result?'}]}
        self.artifact(directory,plan,'evidence',evidence)
        if kind==runtime.EVALUATION_KIND:
            plan['submodel_version_id']='submodel:synthetic:v1';self.artifact(directory,plan,'eligibility',descriptor)
            factor={'submodel_version_id':plan['submodel_version_id'],'comparison_max_delta':.2,'policy':scores.POLICY,
                    'factors':[{'factor_version_id':'factor:synthetic:v1','minimum':1,'maximum':5,'weight':1,
                      'tolerance':.5,'anchors':{'1':'low','5':'high'},'evidence_expectations':['Frozen source'],
                      'model_policy':{'tasks':{t:{'model':'test/'+t,'reasoning_effort':'high'} for t in runtime.EVALUATION_SLOTS}}}]}
            self.artifact(directory,plan,'factors',factor)
        for task in plan['task_slots']:
            prompt=task+'-prompt.json';schema=task+'-schema.json'
            for filename,document in [(prompt,{'text':'Synthetic fixture; use exact frozen evidence, no real market judgments.'}),
                                      (schema,runtime.output_schema(task))]:
                (directory/filename).write_bytes(runtime._bytes(document));plan['files'][filename]=runtime.packaging._file_sha(directory/filename)
            plan['tasks'][task]={'actor_id':'synthetic-'+task,'prompt':prompt,'schema':schema,'config':{
                'model':'test/'+task,'reasoning_effort':'high','max_input_tokens':500000,'max_output_tokens':4000,
                'max_attempts':1,'allow_fallbacks':False,'timeout_seconds':30,'input_microusd_per_token':1,'output_microusd_per_token':1}}
        (directory/'plan.json').write_bytes(runtime._bytes(plan))
        auth=ledger.build_authorization(workflow_plan_sha256=runtime._sha(plan),roles=runtime.role_bindings(directory,plan),
            authorized_by='synthetic test only',valid_from_utc='2026-11-10T00:00:00Z',expires_at_utc='2026-11-11T00:00:00Z',
            max_calls=len(plan['task_slots']),max_cost_microusd=3000000,execution_contract_hashes=runtime.authority_contracts(plan))
        runtime.initialize(directory,auth,clock=lambda:NOW)
        return directory

    def document(self,task,assignment):
        inputs=assignment['frozen_input']
        if task=='eligibility':
            gate={'status':'pass','evidence_label':'inference','confidence':.6,'rationale':'Synthetic inference only.',
                  'supporting_evidence_ids':['evidence:one'],'counterevidence_ids':[],'research_gaps':['Test uncertainty.']}
            return {'schema_version':1,**{k:inputs[k] for k in ('graph_sha256','strategy_sha256','evidence_sha256','evidence_cutoff')},
                    'markets':[{'market_version_id':m,'gates':{g:copy.deepcopy(gate) for g in eligibility.GATES}} for m in self.mids]}
        if task=='comparator':
            pairs=assignment['dependencies']['comparison_pairs']
            return {'pairs':[{**p,'preferred_market_version_id':p['market_version_ids'][0],'confidence':.6,
                'rationale':'Synthetic pair comparison.','claim_ids':['claim:one'],'counterevidence_ids':[],'gap_ids':['gap:one']} for p in pairs],
                'adjustments':[{'market_version_id':m,'delta':(.1 if i==0 else -.1) if pairs else 0,
                    'pair_ids':[p['pair_id'] for p in pairs if m in p['market_version_ids']],
                    'rationale':'Synthetic bounded calibration.'} for i,m in enumerate(self.mids)]}
        return {'scores':[{'market_version_id':m,'factor_version_id':'factor:synthetic:v1','raw':self.amounts[task],
            'confidence':.6,'evidence_quality':.7,'downside':.1,'label':'inference','rationale':'Synthetic evidence-backed inference.',
            'claim_ids':['claim:one'],'counterevidence_ids':[],'gap_ids':['gap:one'],'alternatives':[2.5]} for m in self.mids]}

    def transport(self,url,headers,raw,timeout):
        request=json.loads(raw);task=request['model'].split('/')[-1]
        assignment=json.loads(request['messages'][-1]['content'].split('# Frozen assignment\n')[1])
        self.calls.append((task,request,assignment))
        doc=self.document(task,assignment)
        return 200,{},json.dumps({'id':'synthetic-generation','model':request['model'],'provider':'Synthetic',
            'choices':[{'message':{'content':json.dumps(doc)}}],
            'usage':{'prompt_tokens':1000,'completion_tokens':100,'cost':.001}}).encode()

    def run_one(self,directory,task,transport=None):
        return runtime.run_task(directory,task,execute=True,api_key='SYNTHETIC_SECRET_ONLY',
                                transport=transport or self.transport,clock=lambda:NOW)

    def evaluation(self):
        self.assertEqual(self.run_one(self.eligible,'eligibility')['status'],'succeeded')
        p=runtime.load_plan(self.eligible);auth=runtime._read(self.eligible/'execution-authority.json')
        owner=runtime._owner(self.eligible,p,auth);_,_,out=runtime._replay(self.eligible,p,auth,owner,runtime._validated_input(self.eligible,p))
        descriptor={'work_unit_dir':str(self.eligible),'plan_sha256':runtime._sha(p),
                    'authorization_sha256':ledger._hash(auth),'task':'eligibility','output_sha256':out['eligibility']['output_sha256']}
        return self.make_unit('evaluation',runtime.EVALUATION_KIND,descriptor)

    def test_eligibility_citation_guidance_reaches_wire_and_overlap_fails_without_repair(self):
        original = self.document
        def overlapping(task, assignment):
            doc = original(task, assignment)
            gate = doc['markets'][0]['gates']['unionized_workforces']
            gate.update(status='unknown', evidence_label='unknown',
                        counterevidence_ids=list(gate['supporting_evidence_ids']))
            return doc
        self.document = overlapping
        result = self.run_one(self.eligible, 'eligibility')
        self.assertEqual(result['status'], 'failed')
        _, request, assignment = self.calls[0]
        self.assertIn('must be disjoint', assignment['frozen_input']['gate_instructions'])
        self.assertIn('unknowns remain holds', assignment['frozen_input']['gate_instructions'])
        gate_schemas = request['response_format']['json_schema']['schema']['properties']['markets']['items']['properties']['gates']['properties']
        self.assertEqual(set(gate_schemas), set(eligibility.GATES))
        for gate in gate_schemas.values():
            for field, opposite in [('supporting_evidence_ids', 'counterevidence_ids'),
                                    ('counterevidence_ids', 'supporting_evidence_ids')]:
                description = gate['properties'][field]['description']
                self.assertIn('disjoint from ' + opposite, description)
                self.assertIn('unknown judgments', description)
        registry = Path(runtime.load_plan(self.eligible)['registry_path'])
        artifact = runtime._read(next(registry.glob('journals/*/governed-*.json')))
        self.assertFalse(artifact['valid'])
        self.assertIsNone(artifact['document'])
        raw = json.loads(base64.b64decode(artifact['output_base64']))
        gate = raw['markets'][0]['gates']['unionized_workforces']
        self.assertEqual(gate['counterevidence_ids'], gate['supporting_evidence_ids'])
        self.assertEqual(gate['status'], 'unknown')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            runtime.projection(self.eligible)
        self.assertFalse(self.run_one(self.eligible, 'eligibility')['dispatch'])
        self.assertEqual(len(self.calls), 1)
        plan = runtime.load_plan(self.eligible)
        state, _ = runtime._state(self.eligible, plan, runtime._read(self.eligible/'execution-authority.json'))
        self.assertEqual(state['calls_reserved'], 1)
        self.assertGreater(state['committed_microusd'], 0)
        self.assertEqual(state['outstanding_microusd'], 0)

    def test_freeze_is_explicit_preserves_source_bytes_and_creates_no_registry(self):
        original=runtime.load_plan(self.eligible);directory=self.base/'freeze';directory.mkdir()
        for name in ['graph.json','strategy.json','evidence.json','source.txt']:
            (directory/name).write_bytes((self.eligible/name).read_bytes())
        configs={task:{'actor_id':spec['actor_id'],'config':spec['config'],
                 'prompt':runtime._read(self.eligible/spec['prompt'])['text']} for task,spec in original['tasks'].items()}
        registry=self.base/'not-created-registry'
        plan=runtime.freeze_plan(directory,kind=runtime.ELIGIBILITY_KIND,market_version_ids=[self.mid],
            artifacts={k:original[k] for k in ('graph','strategy','evidence')},evidence_cutoff=NOW,
            task_configs=configs,registry_path=registry)
        self.assertEqual(plan['files']['source.txt'],original['files']['source.txt'])
        self.assertEqual(runtime.preflight(directory)['status'],'READY_FOR_INITIALIZATION')
        self.assertFalse(registry.exists());self.assertFalse((directory/'execution-owner.json').exists())
        with self.assertRaisesRegex(ValueError,'already exists'):
            runtime.freeze_plan(directory,kind=runtime.ELIGIBILITY_KIND,market_version_ids=[self.mid],
                artifacts={k:original[k] for k in ('graph','strategy','evidence')},evidence_cutoff=NOW,
                task_configs=configs,registry_path=registry)

    def test_real_journal_gates_blind_evaluations_and_projection(self):
        unit=self.evaluation()
        self.assertEqual(self.run_one(unit,'evaluator_a')['status'],'succeeded')
        self.assertEqual(self.run_one(unit,'evaluator_b')['status'],'succeeded')
        a,b=[c[2] for c in self.calls if c[0] in ('evaluator_a','evaluator_b')]
        self.assertEqual(a['frozen_input'],b['frozen_input']);self.assertEqual(a['dependencies'],{});self.assertEqual(b['dependencies'],{})
        with self.assertRaisesRegex(ValueError,'not eligible'):self.run_one(unit,'adjudicator')
        with self.assertRaisesRegex(ValueError,'incomplete'):runtime.projection(unit)
        self.assertEqual(self.run_one(unit,'comparator')['status'],'succeeded')
        result=runtime.projection(unit);self.assertAlmostEqual(result['scores'][0]['raw'],3.1)
        self.assertFalse(result['accepted_global_ranking']);self.assertEqual(len(self.calls),4)
        self.assertFalse(self.run_one(unit,'comparator')['dispatch']);self.assertEqual(len(self.calls),4)
        self.assertEqual(runtime.projection(self.eligible)['markets'][0]['status'],'eligible')

    def test_two_market_comparator_has_result_confidence_and_attributed_effects(self):
        self.mids.append('market-version:synthetic-second')
        projection=self.canonical.return_value[1]
        projection['markets'].append({'market_version_id':self.mids[1],'canonical_name':'Second synthetic fixture'})
        self.eligible=self.make_unit('eligibility-two',runtime.ELIGIBILITY_KIND)
        unit=self.evaluation()
        for task in ('evaluator_a','evaluator_b','comparator'):
            self.assertEqual(self.run_one(unit,task)['status'],'succeeded')
        result=runtime.projection(unit);pair=result['comparison']['pairs'][0]
        self.assertEqual(pair['preferred_market_version_id'],self.mid);self.assertEqual(pair['confidence'],.6)
        self.assertEqual(len(result['comparison']['pairs']),1)
        self.assertEqual(result['comparison']['adjustments'][0]['pair_ids'],[pair['pair_id']])
        inputs=runtime._validated_input(unit,runtime.load_plan(unit))
        bad=copy.deepcopy(result['comparison']);bad['adjustments'][0]['pair_ids']=[]
        with self.assertRaisesRegex(ValueError,'attributed comparison'):
            scores.validate(bad,'comparator',self.mids,inputs['factors'],inputs['evidence'],{})
        evidence=copy.deepcopy(inputs['evidence'])
        for row in [*evidence['claims'],*evidence['gaps']]:row['market_version_ids']=[self.mid]
        with self.assertRaisesRegex(ValueError,'each comparison market'):
            scores.validate(result['comparison'],'comparator',self.mids,inputs['factors'],evidence,{})

    def test_policy_structure_and_transitive_code_hashes_are_mandatory(self):
        unit=self.evaluation();plan=runtime.load_plan(unit);factors=runtime._artifact(unit,plan,'factors')
        for field,value in [('anchors',True),('evidence_expectations','anything'),('model_policy',True)]:
            bad=copy.deepcopy(factors);bad['factors'][0][field]=value
            with self.assertRaises(ValueError):scores.policy(bad,plan['submodel_version_id'])
        original=runtime.packaging._file_sha
        def changed(path):
            return '0'*64 if str(path).endswith('/src/turbo/universe/graph.py') else original(path)
        with patch.object(runtime.packaging,'_file_sha',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'contract changed'):runtime.preflight(unit)

    def test_material_disagreement_requires_adjudication_and_retains_gap(self):
        unit=self.evaluation();self.amounts['evaluator_b']=5
        self.run_one(unit,'evaluator_a');self.run_one(unit,'evaluator_b')
        with self.assertRaisesRegex(ValueError,'requires adjudication'):self.run_one(unit,'comparator')
        self.run_one(unit,'adjudicator');self.run_one(unit,'comparator')
        result=runtime.projection(unit);self.assertEqual(result['scores'][0]['raw'],3.5)
        self.assertTrue(result['scores'][0]['provisional']);self.assertEqual(result['scores'][0]['gap_ids'],['gap:one'])

    def test_timeout_never_resends_and_blocks_other_tasks(self):
        unit=self.evaluation();count=len(self.calls)
        def timeout(*args):self.calls.append(('timeout',));raise TimeoutError()
        self.assertEqual(self.run_one(unit,'evaluator_a',timeout)['status'],'unresolved')
        self.assertFalse(self.run_one(unit,'evaluator_a',timeout)['dispatch']);self.assertEqual(len(self.calls),count+1)
        with self.assertRaisesRegex(ValueError,'unresolved'):self.run_one(unit,'evaluator_b')

    def test_real_held_eligibility_receipt_does_not_enable_evaluation(self):
        original=self.document
        def held(task,assignment):
            doc=original(task,assignment)
            if task=='eligibility':
                doc['markets'][0]['gates']['unionized_workforces'].update(status='unknown',evidence_label='unknown')
            return doc
        self.document=held
        with self.assertRaisesRegex(ValueError,'held or excluded'):self.evaluation()
        self.assertEqual(len(self.calls),1)
        self.assertEqual(runtime.projection(self.eligible)['markets'][0]['status'],'hold')

    def test_output_tampering_and_caller_receipt_cannot_grant_eligibility(self):
        unit=self.evaluation();plan=runtime.load_plan(unit)
        descriptor=runtime._artifact(unit,plan,'eligibility');descriptor['output_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'provider output'):runtime.validate_eligibility_provider(unit,descriptor)
        registry=Path(runtime.load_plan(self.eligible)['registry_path'])
        artifact=next(registry.glob('journals/*/governed-*.json'));doc=json.loads(artifact.read_text());doc['valid']=False;artifact.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError,'artifact changed'):runtime.preflight(unit)

    def test_unregistered_policy_missing_cells_and_other_market_claims_rejected(self):
        unit=self.evaluation();plan=runtime.load_plan(unit);inp=runtime._validated_input(unit,plan)
        bad=copy.deepcopy(inp['factors']);bad['policy'].pop('confidence_adjustment')
        with self.assertRaisesRegex(ValueError,'explicit score policy'):scores.policy(bad,plan['submodel_version_id'])
        with self.assertRaisesRegex(ValueError,'nonblank'):scores.validate({'scores':[]},'evaluator_a',[self.mid],inp['factors'],inp['evidence'],{})
        doc=self.document('evaluator_a',{'frozen_input':inp});evidence=copy.deepcopy(inp['evidence']);evidence['claims'][0]['market_version_ids']=['market-version:other']
        with self.assertRaisesRegex(ValueError,'other-market'):scores.validate(doc,'evaluator_a',[self.mid],inp['factors'],evidence,{})

    def test_source_change_after_initialization_blocks_before_call(self):
        before=len(self.calls);(self.eligible/'source.txt').write_text('Changed source')
        with self.assertRaisesRegex(ValueError,'artifact changed'):self.run_one(self.eligible,'eligibility')
        self.assertEqual(len(self.calls),before)

    def test_failed_semantic_output_cannot_continue_or_be_repaired(self):
        unit=self.evaluation();original=self.document
        def malformed(task,assignment):
            doc=original(task,assignment)
            if task=='evaluator_a':doc['scores'][0]['claim_ids']=['claim:absent']
            return doc
        self.document=malformed
        self.assertEqual(self.run_one(unit,'evaluator_a')['status'],'failed')
        self.assertFalse(self.run_one(unit,'evaluator_a')['dispatch'])
        with self.assertRaisesRegex(ValueError,'failed'):self.run_one(unit,'evaluator_b')

if __name__=='__main__':unittest.main()
