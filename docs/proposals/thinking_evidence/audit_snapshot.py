"""Read-only audit of an explicitly supplied Core and Vault snapshot."""
import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--core', type=Path, required=True)
parser.add_argument('--vault', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.core.resolve()))
from scripts.contracts import load_jsonl, load_json, validate_event_sequence
from scripts.reducer import load_units, rebuild_state

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

before = {str(p.relative_to(args.vault)): digest(p) for p in args.vault.rglob('*') if p.is_file()}
events = load_jsonl(args.vault / 'events/learning_events.jsonl')
registry = load_units(load_json(args.vault / 'state/knowledge_units.json'))
state = rebuild_state(events, registry)
repeat = rebuild_state(events, registry)
attempts = [e for e in events if e['event_type'] == 'attempt']
receipts = []
for path in sorted((args.vault / 'inbox').glob('*.json')):
    request = load_json(path)
    receipt_path = args.vault / 'outbox' / path.name
    receipt = load_json(receipt_path) if receipt_path.exists() else {}
    canonical = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    receipts.append({'request_id': request['request_id'], 'status': receipt.get('status'),
                     'identity_valid': receipt.get('request_id') == request['request_id'] and receipt.get('operation') == request['operation'],
                     'hash_valid': receipt.get('request_hash') == hashlib.sha256(canonical).hexdigest()})
after = {str(p.relative_to(args.vault)): digest(p) for p in args.vault.rglob('*') if p.is_file()}
result = {
    'engine_version_file': (args.core / 'VERSION').read_text().strip(),
    'model_version': state['model_version'],
    'event_count': len(events), 'attempt_count': len(attempts), 'unit_count': len(registry),
    'event_types': dict(collections.Counter(e['event_type'] for e in events)),
    'diagnosis_statuses': dict(collections.Counter(e['diagnosis']['status'] for e in events if e['event_type'] == 'diagnosis')),
    'attempt_results': dict(collections.Counter(e['attempt']['result'] for e in attempts)),
    'answer_modes': dict(collections.Counter(e['attempt']['answer_mode'] for e in attempts)),
    'measured_fields': {k: sum(k in e['attempt'] for e in attempts) for k in ['time_minutes','confidence_before','confidence_after','delayed_days','variant_level','parent_diagnosis_id']},
    'clean_independent_correct': sum(u['clean_independent_correct'] for u in state['units'].values()),
    'unknown_overall_units': [k for k,u in state['units'].items() if u.get('mastery_overall') is None],
    'qualified_positive_counts': {k:u.get('qualified_positive_counts') for k,u in state['units'].items()},
    'queue_types': dict(collections.Counter(t['task_type'] for t in state['review_queue'])),
    'matches_production_derived_state': state == load_json(args.vault / 'state/derived_state.json'),
    'matches_production_export_state': state == load_json(args.vault / 'exports/latest.json')['state'],
    'deterministic_replay': state == repeat,
    'input_files_unchanged': before == after,
    'input_sha256': {p:before[p] for p in ['events/learning_events.jsonl','state/knowledge_units.json','engine.lock.json']},
    'request_receipts': receipts,
    'state': state,
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
summary = {k:v for k,v in result.items() if k not in {'state','request_receipts','qualified_positive_counts'}}
summary['request_receipts'] = {'count':len(receipts), 'statuses':dict(collections.Counter(r['status'] for r in receipts)),
                               'all_identity_hash_valid':all(r['identity_valid'] and r['hash_valid'] for r in receipts)}
print(json.dumps(summary,ensure_ascii=False,indent=2))
