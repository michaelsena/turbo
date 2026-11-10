"""Literal navigation is a projection, never new evidence or output repair."""
import copy
import json
import unittest

from turbo.agents import batch_provider as provider, batch_output, model_view
from turbo.pipeline_paths import ROOT
from test_batch_output import unresolved_output


class AssignmentNavigationTest(unittest.TestCase):
    def setUp(self):
        self.context = {'schema_version':1,'contract_version':'batch-primary-v1','role_id':'batch_primary',
            'request_id':'exact-request','invocation_id':'invocation:'+'a'*24,
            'context_sha256':'b'*64,'output_schema_sha256':'c'*64,'prompt_sha256':'d'*64,
            'limits':{'max_output_bytes':1000000},'families':[]}
        for n in range(2):
            subject='identity:required-'+str(n); context_id='identity:context-'+str(n)
            namespace=str(n)*16
            self.context['families'].append({'family_id':'family:'+str(n),'preparation_id':'prep:'+str(n),
                'input_pack_sha256':str(n)*64,'required_identity_ids':[subject],'required_candidate_ids':[],
                'context_identity_ids':[context_id],'context_candidate_ids':[],
                'proposal_id_prefix':'proposal:'+namespace+':','gap_id_prefix':'gap:'+namespace+':',
                'graph_market_ids':[], 'evidence_catalog':[
                    {'evidence_id':'evidence:'+str(n)*64,'json_pointer':'/identity_cards/0',
                     'subject_ids':[subject], 'value':{'identity_id':subject,'labels':['Securities underwriting'],
                         'analysis_labels':['Original label'], 'assignment_role':'required_review',
                         'owner_family_id':'family:'+str(n)}},
                    {'evidence_id':'evidence:'+str(n+2)*64,'json_pointer':'/identity_cards/1',
                     'subject_ids':[context_id], 'value':{'identity_id':context_id,'labels':['Context only'],
                         'assignment_role':'required_review','owner_family_id':'family:other'}}]})
        self.task={'role':'primary','actor_id':'actor-never-a-request','role_invocation_id':'workflow-role:not-payload',
                   'context':self.context,'inputs':{}}

    def test_release_reviewer_literal_is_exact_preview_not_nested_base_hash(self):
        self.task.update(role='release_reviewer',
            release_preview={'preview_sha256':'e'*64, 'plan_sha256':'f'*64,
                'preview':{'base_events_sha256':'1'*64, 'config':{'value':'unchanged'}}})
        before = copy.deepcopy(self.task)
        navigation = provider.assignment_navigation(self.task)
        self.assertEqual(navigation['approved_plan_sha256'], 'e'*64)
        self.assertIn('release_preview.preview_sha256', navigation['approval_binding_instruction'])
        self.assertIn('base_events_sha256', navigation['approval_binding_instruction'])
        rendered = provider.render_assignment(self.task, input_root=ROOT, model_view=model_view.VERSION)
        literal, encoded = rendered.split('\n# Literal assignment navigation\n', 1)[1].split('\n# Frozen assignment\n', 1)
        self.assertEqual(json.loads(literal), navigation)
        self.assertEqual(model_view.decode(json.loads(encoded)), before)
        self.assertEqual(self.task, before)
        # Changing only a misleading neighboring hash cannot change the copied binding.
        self.task['release_preview']['preview']['base_events_sha256'] = '2'*64
        self.assertEqual(provider.assignment_navigation(self.task)['approved_plan_sha256'], 'e'*64)
        self.task['release_preview']['preview_sha256'] = '3'*64
        changed = provider.render_assignment(self.task, input_root=ROOT, model_view=model_view.VERSION)
        self.assertEqual(provider.assignment_navigation(self.task)['approved_plan_sha256'], '3'*64)
        self.assertNotEqual(provider._hash(rendered), provider._hash(changed))

    def test_release_binding_is_reviewer_only_and_missing_hash_fails_closed(self):
        for role in ('primary', 'verifier', 'escalation_a', 'escalation_b', 'adjudicator'):
            with self.subTest(role=role):
                task = dict(self.task, role=role, release_preview={'preview_sha256':'e'*64})
                navigation = provider.assignment_navigation(task)
                self.assertNotIn('approved_plan_sha256', navigation)
                self.assertNotIn('approval_binding_instruction', navigation)
        for malformed in (None, {}, {'preview_sha256':'short'}, {'preview_sha256':'G'*64}):
            with self.subTest(preview=malformed), self.assertRaises((KeyError, TypeError, ValueError)):
                provider.assignment_navigation(dict(self.task, role='release_reviewer', release_preview=malformed))

    def test_exact_payload_bindings_not_actor_or_global_card_scope(self):
        navigation=provider.assignment_navigation(self.task)
        bindings=navigation['payload_bindings']
        self.assertEqual(bindings['request_id'],'exact-request')
        self.assertEqual(bindings['invocation_id'],self.context['invocation_id'])
        self.assertEqual(bindings['role_id'],'batch_primary')
        family=navigation['families'][0]
        self.assertEqual(family['required_identity_ids'],['identity:required-0'])
        self.assertEqual(family['context_identity_ids'],['identity:context-0'])
        self.assertEqual(len(family['required_subject_cards']),1)
        self.assertEqual(family['required_subject_cards'][0]['original_fields']['labels'],['Securities underwriting'])
        self.assertEqual(family['required_subject_cards'][0]['evidence_id'],'evidence:'+'0'*64)
        self.assertIn('GLOBAL',provider.NAVIGATION_INSTRUCTIONS)
        self.assertIn('LOCAL',provider.NAVIGATION_INSTRUCTIONS)

    def test_literal_block_and_full_encoded_assignment_are_lossless_and_independent(self):
        before=copy.deepcopy(self.task)
        runtime=provider.render_assignment(self.task,input_root=ROOT,model_view=model_view.VERSION)
        literal,encoded=runtime.split('\n# Literal assignment navigation\n',1)[1].split('\n# Frozen assignment\n',1)
        self.assertEqual(json.loads(literal),provider.assignment_navigation(self.task))
        self.assertEqual(model_view.decode(json.loads(encoded)),self.task)
        self.assertEqual(self.task,before)
        self.assertEqual(model_view.decode(json.loads(encoded))['inputs'],{})
        self.assertNotIn('actor-never-a-request',literal)
        navigation=provider.assignment_navigation(self.task)
        navigation['families'][0]['required_subject_cards'][0]['original_fields']['labels'].append('fabricated')
        self.assertEqual(self.task,before)

    def test_plain_default_unchanged_and_navigation_prompt_bound(self):
        plain=provider.render_assignment(self.task,input_root=ROOT)
        self.assertEqual(plain,provider.role_prompt(input_root=ROOT)+'\n# Frozen assignment\n'+provider._bytes(self.task).decode())
        self.assertNotIn('Literal assignment navigation',plain)
        self.assertIn(provider.NAVIGATION_INSTRUCTIONS,provider.role_prompt(input_root=ROOT,model_view=model_view.VERSION))
        self.assertNotEqual(provider.contract_bindings(input_root=ROOT)['primary']['prompt_sha256'],
                            provider.contract_bindings(input_root=ROOT,model_view=model_view.VERSION)['primary']['prompt_sha256'])
        self.assertIn('src/turbo/agents/batch_provider.py',provider.execution_contract_hashes())

    def test_missing_ambiguous_or_wrong_subject_anchor_fails_closed(self):
        for change in ('missing','duplicate','wrong-subject'):
            task=copy.deepcopy(self.task); catalog=task['context']['families'][0]['evidence_catalog']
            if change=='missing':catalog.pop(0)
            elif change=='duplicate':catalog.append(copy.deepcopy(catalog[0]))
            else:catalog[0]['subject_ids']=[]
            with self.assertRaises(ValueError):provider.assignment_navigation(task)

    def test_exact_candidate_label_and_anchor_preserved(self):
        family=self.context['families'][0]; family['required_candidate_ids']=['candidate-market:original']
        family['evidence_catalog'].append({'evidence_id':'evidence:'+'e'*64,
            'json_pointer':'/required_candidate_cards/0','subject_ids':['candidate-market:original'],
            'value':{'candidate_market_id':'candidate-market:original','name':'Deposit brokerage',
                     'primary_family_id':'family:0','status':'unvalidated_prior_model_seed'}})
        card=provider.assignment_navigation(self.task)['families'][0]['required_subject_cards'][1]
        self.assertEqual(card['subject_id'],'candidate-market:original')
        self.assertEqual(card['original_fields']['name'],'Deposit brokerage')
        self.assertEqual(card['original_fields']['status'],'unvalidated_prior_model_seed')

    def test_existing_validator_still_rejects_actor_request_and_extra_context_subject(self):
        payload=unresolved_output(self.context)
        self.assertEqual(batch_output._validate_against_context(payload,self.context,root=ROOT),[])
        bad=copy.deepcopy(payload);bad['request_id']=self.task['actor_id']
        self.assertIn('request_id does not match the expected request context',
                      batch_output._validate_against_context(bad,self.context,root=ROOT))
        bad=copy.deepcopy(payload); extra=copy.deepcopy(bad['families'][0]['identity_dispositions'][0])
        extra['identity_id']='identity:context-0';bad['families'][0]['identity_dispositions'].append(extra)
        self.assertTrue(batch_output._validate_against_context(bad,self.context,root=ROOT))
        self.assertEqual(extra['identity_id'],'identity:context-0')  # No ID repair.


if __name__=='__main__':unittest.main()
