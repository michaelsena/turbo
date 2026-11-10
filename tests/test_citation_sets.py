"""Prospective citation policy: exact duplicates only, full managed replay."""
import base64
import copy
import hashlib
import json
import unittest
from jsonschema import Draft202012Validator
from turbo.agents import batch_provider as provider, citation_sets as citations
from turbo.agents import batch_output
from turbo.agents.openrouter_runner import openrouter_role_schema
from turbo.pipeline_paths import ROOT
import test_single_family_batch as single_family


class CitationSetTest(unittest.TestCase):
    def test_schema_and_exact_path_boundary(self):
        schema = provider.role_schema('primary', input_root=ROOT)
        wire = citations.provider_schema(schema)
        self.assertNotEqual(schema, wire)
        self.assertTrue(schema['$defs']['proposal']['properties']['supporting_evidence_ids']['uniqueItems'])
        self.assertNotIn('uniqueItems', wire['$defs']['proposal']['properties']['supporting_evidence_ids'])
        doc = {'payload': {'families': [{'proposed_markets': [{'dimensions': {'job': {
            'supporting_evidence_ids': ['evidence:a', 'evidence:b', 'evidence:a']}},
            'proposal_ids': ['x', 'x']}], 'required_identity_ids': ['x', 'x']}]},
            'supporting_evidence_ids': ['outside', 'outside']}
        normalized, trace = citations.normalize(doc, schema)
        self.assertEqual(normalized['payload']['families'][0]['proposed_markets'][0]['dimensions']['job']['supporting_evidence_ids'], ['evidence:a','evidence:b'])
        self.assertEqual(trace['changes'], [{'path': '/payload/families/0/proposed_markets/0/dimensions/job/supporting_evidence_ids', 'removed_indices': [2]}])
        self.assertEqual(normalized['supporting_evidence_ids'], ['outside','outside'])
        self.assertEqual(normalized['payload']['families'][0]['required_identity_ids'], ['x','x'])
        self.assertEqual(citations.normalize(normalized, schema)[0], normalized)
        self.assertEqual(len(doc['payload']['families'][0]['proposed_markets'][0]['dimensions']['job']['supporting_evidence_ids']), 3)
        drift = copy.deepcopy(schema); drift['$defs']['proposal']['properties']['supporting_evidence_ids']['uniqueItems'] = False
        with self.assertRaises(ValueError): citations.provider_schema(drift)

    def test_artifact_trace_raw_policy_and_legacy_integrity(self):
        document = {'payload': {'families': [{'identity_dispositions': [{'supporting_evidence_ids': ['evidence:a','evidence:a']}]}]}}
        raw = json.dumps(document).encode()
        canonical, trace = citations.normalize(document, provider.role_schema('primary', input_root=ROOT))
        wire = provider.role_schema('primary', input_root=ROOT, citation_sets=True)
        auth = {'execution_contract_hashes': provider.execution_contract_hashes(citation_sets=True),
                'roles': {'primary': {'model': 'test/primary', 'schema_sha256': provider._hash(wire)}}}
        artifact = {'role': 'primary', 'output_base64': base64.b64encode(raw).decode(),
                    'provider': {'body_sha256': hashlib.sha256(raw).hexdigest(), 'schema_sha256': provider._hash(wire),
                                 'provider_schema_sha256': provider._hash(openrouter_role_schema(wire, role_id='primary', model='test/primary'))},
                    'document': canonical, 'citation_normalization': trace}
        self.assertTrue(provider.verify_artifact_document(artifact, auth, input_root=ROOT))
        for change in ('trace', 'raw', 'canonical', 'policy'):
            a = copy.deepcopy(artifact); authority = copy.deepcopy(auth)
            if change == 'trace': a['citation_normalization']['changes'] = []
            elif change == 'raw': a['output_base64'] = base64.b64encode(raw+b' ').decode()
            elif change == 'canonical': a['document'] = document
            else: authority['execution_contract_hashes'][citations.CONTRACT_KEY] = '0'*64
            self.assertFalse(provider.verify_artifact_document(a, authority, input_root=ROOT), change)
        legacy = {'execution_contract_hashes': provider.execution_contract_hashes()}
        artifact.pop('citation_normalization')
        self.assertFalse(provider.verify_artifact_document(artifact, legacy, input_root=ROOT))
        artifact['document'] = document
        self.assertTrue(provider.verify_artifact_document(artifact, legacy, input_root=ROOT))


class CitationManagedTest(single_family.SingleFamilyManagedTest):
    def setUp(self):
        super().setUp()
        self.authorization['execution_contract_hashes'] = provider.execution_contract_hashes(citation_sets=True)
        for role, binding in provider.contract_bindings(input_root=self.input_root, citation_sets=True).items():
            self.authorization['roles'][role].update(binding)

    def payload(self):
        value = super().payload()
        for family in value['families']:
            for disposition in family['identity_dispositions']:
                disposition['supporting_evidence_ids'] += disposition['supporting_evidence_ids'][:1]
        return value

    def test_invalid_citations_and_semantic_omissions_remain_invalid(self):
        canonical_schema = provider.role_schema('primary', input_root=self.input_root)
        wire_schema = provider.role_schema('primary', input_root=self.input_root, citation_sets=True)
        doc = {'payload': self.payload()}
        self.assertFalse(Draft202012Validator(canonical_schema).is_valid(doc))
        self.assertTrue(Draft202012Validator(wire_schema).is_valid(doc))
        normalized, trace = citations.normalize(doc, canonical_schema)
        self.assertTrue(trace['changes'])
        self.assertFalse(batch_output._validate_against_context(normalized['payload'], self.context, root=ROOT))
        for kind in ('invented', 'wrong_subject', 'omission', 'duplicate_subject', 'wrong_type'):
            mutated = copy.deepcopy(doc)
            family = mutated['payload']['families'][0]
            item = family['identity_dispositions'][0]
            if kind == 'invented': item['supporting_evidence_ids'] = ['evidence:'+'0'*64]*2
            elif kind == 'wrong_subject':
                item['supporting_evidence_ids'] = [next(e['evidence_id'] for e in self.context['families'][0]['evidence_catalog'] if e['subject_ids'] and item['identity_id'] not in e['subject_ids'])]*2
            elif kind == 'omission': family['research_gaps'] = []
            elif kind == 'duplicate_subject': family['identity_dispositions'].append(copy.deepcopy(item))
            else: item['supporting_evidence_ids'] = [1, 1]
            canonical, _ = citations.normalize(mutated, canonical_schema)
            self.assertTrue(batch_output._validate_against_context(canonical['payload'], self.context, root=ROOT), kind)
