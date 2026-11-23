"""Review-only draft checker. Not imported by Core scripts or mobile processing.

Requires jsonschema==4.26.0 in an isolated review environment. Passing this
checker does not establish source authenticity, teaching benefit or deployment.
"""
import argparse
import copy
import json
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parent
SCHEMA = json.loads((ROOT / 'observation.schema.json').read_text())
Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())

def instant(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('timezone required')
    return result

def require(condition, message):
    if not condition:raise ValueError(message)

def validate(event, history):
    VALIDATOR.validate(event)
    seen={}
    latest={}
    for record in history:
        require(record['event_id'] not in seen,'duplicate historical event identity')
        seen[record['event_id']]=record
        if record['event_type']=='process_observation':
            trace=record['observation']
            prior=latest.get(trace['trace_id'])
            require(trace.get('supersedes_event_id') == (prior['event_id'] if prior else None),'invalid historical trace chain')
            latest[trace['trace_id']]=record
    require(event['event_id'] not in seen,'new event ID already exists')
    observation=event['observation']
    anchor=seen.get(observation['anchor_event_id'])
    require(anchor is not None and anchor['event_type']=='attempt','anchor must be an existing attempt')
    require(event['subject']==anchor['subject'],'subject must match anchor')
    require(set(event['unit_ids']) <= set(anchor['unit_ids']),'scope must be a subset of anchor units')
    require(observation['question_id']==anchor['attempt']['question_id'],'question must match anchor')
    require(instant(event['timestamp'])>=instant(anchor['timestamp']),'recording precedes anchor')
    if observation['observed_at'] is not None:
        require(instant(observation['observed_at'])<=instant(event['timestamp']),'observed_at is in the future')
    prior=latest.get(observation['trace_id'])
    require(observation.get('supersedes_event_id') == (prior['event_id'] if prior else None),'must supersede latest same-trace revision')
    if prior:
        require(prior['observation']['anchor_event_id']==observation['anchor_event_id'],'revision changes anchor')
        require(instant(event['timestamp'])>=instant(prior['timestamp']),'revision precedes predecessor')
    for ref in observation['exposure_event_ids']:
        require(ref in seen,'unresolved exposure reference')
    step_ids=[s['step_id'] for s in observation['steps']]
    require(len(step_ids)==len(set(step_ids)),'duplicate step ID')
    interventions={h['intervention_id']:h for h in observation['interventions']}
    require(len(interventions)==len(observation['interventions']),'duplicate intervention ID')
    for hint in interventions.values():
        if 'before_step_id' in hint:require(hint['before_step_id'] in step_ids,'unknown before_step_id')
    for step in observation['steps']:
        require(set(step['unit_ids'])<=set(event['unit_ids']),'step scope outside event')
        if 'intervention_id' in step:require(step['intervention_id'] in interventions,'unresolved intervention')
        for ref in step['basis_event_ids']+step['verification']['evidence_event_ids']:
            require(ref in seen,'unresolved evidence reference')
        origin=step['source']['kind']; status=step['verification']['status']
        if origin in {'system_inference','unsupported_hypothesis','legacy_summary'}:
            require(status not in {'source_checked','learner_report_confirmed'},'inference or summary is not a directly checked learner source')
        if origin=='system_inference':require(bool(step['basis_event_ids']),'inference needs a basis')
        if step['source']['uncertainty']:
            require(status in {'unverified','contradicted'},'unresolved transcription cannot confirm a claim')
        if status=='learner_report_confirmed':
            require(origin in {'concurrent_self_report','retrospective_self_report'},'report confirmation preserves report origin')
        if status=='behavior_supported':
            refs=step['verification']['evidence_event_ids']
            require(bool(refs),'behavior support needs a separate attempt')
            for ref in refs:
                support=seen[ref]
                require(support['event_type']=='attempt' and ref!=anchor['event_id'],'behavior support needs a different attempt')
                a=support.get('attempt',{})
                require(set(step['unit_ids'])<=set(support['unit_ids']),'behavior support outside tested scope')
                require(a.get('result')=='correct' and a.get('assistance_level')==0 and a.get('process_check')=='clean'
                        and a.get('answer_mode') in {'independent','recalled'},'behavior support must be qualified')
                require(instant(support['timestamp'])>instant(anchor['timestamp']),'behavior confirmation precedes observation target')
    for link in observation['links']:
        target=seen.get(link['target_event_id'])
        require(target is not None,'unresolved link target')
        require(set(link['unit_ids'])<=set(event['unit_ids']),'link scope outside event')
        if link['relation']=='tests_diagnosis':require(target['event_type']=='diagnosis','diagnosis link targets wrong event type')
        if link['relation']=='retest_of' and link['status']=='verified':
            require(target['event_type']=='attempt' and set(link['unit_ids'])<=set(target['unit_ids']),'unrelated retest')
            require(instant(target['timestamp'])<instant(anchor['timestamp']),'retest baseline must precede anchor')
        if link['relation']=='transfer_from' and link['status']=='verified':
            require(target['event_type']=='attempt' and target['event_id']!=anchor['event_id'],'transfer needs a distinct prior attempt')
            require(bool(link.get('changed_features')),'transfer needs reviewed changed features')
            require(link.get('transfer_distance') not in {None,'unknown','far_candidate'},'verified transfer distance is unresolved')
    return event

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    fixtures=json.loads((ROOT/'fictional_cases.json').read_text())
    cases=fixtures['cases']
    result=[]
    for case in cases:
        event=copy.deepcopy(fixtures['base_observation'])
        for change in case['changes']:
            parent=event
            for key in change['path'][:-1]:parent=parent[key]
            key=change['path'][-1]
            if change.get('remove'):parent.pop(key)
            else:parent[key]=copy.deepcopy(change['value'])
        history=copy.deepcopy(case.get('history',[fixtures['anchor']]))
        error=None
        try:validate(event,history); accepted=True
        except (ValueError, KeyError, TypeError) as exc:error=str(exc);accepted=False
        except Exception as exc:
            # jsonschema's ValidationError is kept distinct from an execution error.
            from jsonschema import ValidationError
            if not isinstance(exc,ValidationError):raise
            error=exc.message;accepted=False
        result.append({'name':case['name'],'expected_valid':case['valid'],'accepted':accepted,
                       'passed':accepted==case['valid'],'validation_error':error})
    payload={'contract_status':'draft-review-only','cases':result,'passed':sum(r['passed'] for r in result),'total':len(result)}
    if args.output:args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'contract_status':payload['contract_status'],'passed':payload['passed'],'total':len(result),
                      'failed':[r['name'] for r in result if not r['passed']]}))
    return 0 if all(r['passed'] for r in result) else 1

if __name__=='__main__':raise SystemExit(main())
