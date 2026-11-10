"""Offline request admission diagnostics. No authority, inference, or cap mutation."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal

from turbo.agents.batch_execution_v2 import _reservation
from turbo.agents.openrouter_attempt import routing_request_fields


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode()


def _positive(value, label):
    if type(value) is not int or value <= 0:
        raise ValueError(label + ' must be a positive integer')
    return value


def assess_primary(capture, metadata, *, metadata_observed_at=None, include_private_budget=False):
    """Assess an exact captured plain primary request against supplied snapshots.

    Metadata is never promoted to verified provider limits. A passing snapshot
    comparison does not validate authority, live endpoint availability, or quality.
    """
    if metadata_observed_at is not None:
        stamp = datetime.fromisoformat(metadata_observed_at.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('metadata observation time must include timezone')
    request = capture['request']; config = capture['role_config']
    if capture['role'] != 'primary' or capture['representation'] != 'plain':
        raise ValueError('only exact plain primary capture is supported')
    if (request['model'] != config['model']
            or request['max_completion_tokens'] != config['max_output_tokens']
            or request['reasoning']['effort'] != config['reasoning_effort']
            or config['allow_fallbacks'] is not False):
        raise ValueError('request does not match supplied role configuration')
    for key, value in routing_request_fields(config['routing']).items():
        if request.get(key) != value:
            raise ValueError('request routing differs from supplied role configuration')
    input_limit = _positive(config['max_input_tokens'], 'input limit')
    output_limit = _positive(config['max_output_tokens'], 'output limit')
    for key in ('input_microusd_per_token', 'output_microusd_per_token'):
        if type(config[key]) is not int or config[key] < 0:
            raise ValueError('reservation price must be a nonnegative integer')
    caps = config['routing']['provider']['max_price']
    if (Decimal(caps['prompt']) > config['input_microusd_per_token']
            or Decimal(caps['completion']) > config['output_microusd_per_token']):
        raise ValueError('reservation price ceilings do not cover routing max_price')
    matches = [row for row in metadata if row['id'] == config['model']]
    if len(matches) != 1:
        raise ValueError('metadata must identify exactly one requested model')
    model = matches[0]
    context_values = [model.get('context_length'), model.get('top_provider', {}).get('context_length')]
    known_contexts = [_positive(v, 'context length') for v in context_values if v is not None]
    context_limit = min(known_contexts) if len(known_contexts) == 2 else None
    output_max = model.get('top_provider', {}).get('max_completion_tokens')
    if output_max is not None:
        output_max = _positive(output_max, 'model output limit')
    raw = canonical(request); bound = len(raw) + 4096
    fits_admission = bound <= input_limit
    output_fits = output_limit <= output_max if output_max is not None else None
    context_fits = bound + output_limit <= context_limit if context_limit is not None else None
    blockers = ['live routed model constraints and snapshot provenance are unverified',
                'fresh exact workflow execution authority has not been assessed']
    if not fits_admission:
        blockers.append('exact request exceeds supplied primary admission ceiling')
    if output_fits is not True:
        blockers.append('configured output limit is unsupported or unproven by snapshot')
    if context_fits is not True:
        blockers.append('conservative request-plus-output context fit is unproven; actual overflow is not established')
    report = {
        'schema_version': 1, 'status': 'offline_no_calls_no_authority',
        'recommendation': 'blocked', 'dispatch_authorized': False,
        'scope': 'exact captured primary request; supplied role configuration is not an authorization',
        'bindings': {**capture['bindings'], 'request_sha256': hashlib.sha256(raw).hexdigest(),
                     'role_config_sha256': hashlib.sha256(canonical(config)).hexdigest(),
                     'metadata_sha256': hashlib.sha256(canonical(metadata)).hexdigest()},
        'subjects': capture['subjects'],
        'metadata': {'model': config['model'], 'provenance': 'supplied_snapshot_unverified',
                     'observed_at': metadata_observed_at, 'retrieved_at': None,
                     'reported_context_limit': context_limit, 'reported_output_limit': output_max,
                     'routed_endpoint_limits_verified': False},
        'admission': {'wire_bytes': len(raw), 'wrapper_allowance': 4096, 'conservative_input_bound': bound,
                      'supplied_input_ceiling': input_limit, 'fits_supplied_ceiling': fits_admission,
                      'required_ceiling_without_changing_admission_rule': bound, 'cap_changed': False},
        'output': {'configured_max_tokens': output_limit, 'fits_reported_maximum': output_fits},
        'context': {'conservative_input_plus_output': bound + output_limit,
                    'fits_reported_context_by_conservative_bound': context_fits,
                    'actual_context_overflow_established': False},
        'actual_usage': {'input_tokens': None, 'output_tokens': None, 'cost': None},
        'tokenizer_estimate': None,
        'downstream': {'request_sizes': 'unknown_until_validated_outputs_exist',
                       'whole_workflow_cost': 'unknown', 'publication_ready': False},
        'blocking_conditions': blockers,
        'staged_options': {
            'one_call_diagnostic': {'recommendation': 'not_recommended_as_coverage_path',
                'max_calls': 1, 'max_attempts': 1, 'max_concurrency': 1,
                'automatic_retry': False, 'downstream_dispatch': False, 'publication': False,
                'continuation': 'not_automatically_resumable_under_fresh_authorization'},
            'same_journal_pause_after_primary': {'recommendation': 'blocked_pending_fit_and_authority',
                'proposed_max_calls': 6, 'proposed_max_attempts_per_role': 1,
                'proposed_max_concurrency': 1, 'automatic_retry': False,
                'stop_after_primary': True, 'publication_before_review': False,
                'continuation': 'existing_authorization_and_journal_only_if_remaining_roles_fit_bound_caps',
                'downstream_fit': 'unknown_until_validated_upstream_outputs_exist',
                'changed_authorization': 'not_created_or_applied'},
        },
    }
    if include_private_budget:
        minimum = {**config, 'max_input_tokens': bound}
        report['private_reservation_arithmetic'] = {
            'classification': 'hypothetical_ceiling_not_cost_estimate_or_authority',
            'formula': 'max_input_tokens * input_microusd_per_token + max_output_tokens * output_microusd_per_token',
            'supplied_primary_reservation_microusd': _reservation({'roles': {'primary': config}}, 'primary'),
            'minimum_admitting_primary_reservation_microusd': _reservation({'roles': {'primary': minimum}}, 'primary'),
            'whole_workflow_reservation': None,
        }
    return report
