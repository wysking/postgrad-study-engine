"""Fictional normal-mobile-path controls for existing release blockers.

No learner data is read; every request is processed in a temporary Vault.
"""
import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--core', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
core = args.core.resolve()
sys.path.insert(0, str(core))
from scripts.contracts import load_json, load_jsonl, validate_learning_event
from scripts.process_inbox import process_file
from scripts.reducer import rebuild_state

UNIT = 'math.fictional.trace_skill'
START = '2026-08-10T09:00:00Z'
LATER = '2026-08-10T09:10:00Z'
NEXT = '2026-08-11T09:00:00Z'

class Vault:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/'config/personal').mkdir(parents=True)
        config = load_json(core/'config/scheduler.json')
        config['phase_subjects'] = ['math','english','math_contest']
        config['subject_activation'] = {'math_contest':'2026-10-01T00:00:00Z'}
        (self.root/'config/personal/scheduler.json').write_text(json.dumps(config))
        return self
    def __exit__(self,*exc): self.tmp.cleanup()
    def call(self, operation, payload):
        count = len(list((self.root/'inbox').glob('*.json'))) if (self.root/'inbox').exists() else 0
        rid = f'fictional-request-{count:03}'
        request = {'schema_version':'1.0','request_id':rid,'created_at':NEXT,'operation':operation,'payload':payload}
        path = self.root/'inbox'/f'{rid}.json';path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(request))
        response = process_file(self.root,path)
        if response['status'] != 'succeeded': raise AssertionError(response)
        return response
    def unit(self, targets, subject='math', unit_id=UNIT):
        self.call('register_unit',{'unit':{'schema_version':'1.0','unit_id':unit_id,'subject':subject,
                  'title':'Fictional trace fixture','evidence_targets':targets,'estimated_minutes':10}})
    def state(self): return load_json(self.root/'state/derived_state.json')

def attempt(activity='solve', mode='independent', level=0, measured=True):
    e = {'schema_version':'1.0','event_id':'fictional-answer','timestamp':LATER,'event_type':'attempt',
         'subject':'math','unit_ids':[UNIT],'activity':activity,'attempt':{
         'question_id':'fictional-question','result':'correct','answer_mode':mode,'process_check':'clean',
         'assistance_level':level,'evidence':'Fictional observed answer.'}}
    if measured:e['attempt']['time_minutes']=8
    return e

def closure(targets, activity, mode, measured=True):
    with Vault() as v:
        v.unit(targets)
        diagnosis = {'schema_version':'1.0','event_id':'fictional-diagnosis','timestamp':START,
             'event_type':'diagnosis','subject':'math','unit_ids':[UNIT],'diagnosis':{
             'diagnosis_id':'fictional-diagnostic-episode','question_id':'fictional-question',
             'status':'confirmed','generated_by':'joint','first_divergence':'Fictional missing condition.',
             'learner_verdict':'Fictional learner checked the draft.','confirmation_method':'draft_check'}}
        v.call('record_diagnosis',{'event':diagnosis})
        e=attempt(activity,mode,measured=measured);e['attempt']['parent_diagnosis_id']='fictional-diagnostic-episode'
        v.call('record_attempt',{'event':e})
        return any(t['task_type']=='targeted_variant' for t in v.state()['review_queue'])

def confirmation(as_of):
    with Vault() as v:
        v.unit(['independent'])
        e=attempt(mode='assisted',level=1);e['timestamp']=START
        v.call('record_attempt',{'event':e})
        diagnostic=[t for t in v.state()['review_queue'] if t['task_type']=='diagnostic'][0]
        response=v.call('request_schedule',{'request':{'schema_version':'1.0','available_minutes':20,
                'as_of':as_of,'phase_subjects':['math'],'max_subject_share':1}})
        return diagnostic['task_id'] in [t['task_id'] for t in response['result']['schedule']['selected_tasks']]

def subject_candidate(registered,label,phase):
    with Vault() as v:
        uid=registered+'.fictional.trace_skill'
        v.unit(['independent'],registered,uid)
        c={'task_id':'fictional-external','unit_id':uid,'subject':label,'estimated_minutes':10,'task_type':'practice',
           'activity':'solve','expected_score_gain':1,'fatigue_cost':0}
        r=v.call('request_schedule',{'request':{'schema_version':'1.0','available_minutes':20,'as_of':START,
                  'phase_subjects':phase,'max_subject_share':1,'candidates':[c]}})
        return c['task_id'] in [t['task_id'] for t in r['result']['schedule']['selected_tasks']]

cases=[
 ('R1_transfer_recall_must_stay_open',lambda:closure(['transfer'],'recall','recalled'),True),
 ('R1_timed_recall_must_stay_open',lambda:closure(['timed'],'recall','recalled'),True),
 ('R1_unmeasured_timed_must_stay_open',lambda:closure(['timed'],'timed_practice','independent',False),True),
 ('C1_recall_only_can_close',lambda:closure(['recall'],'recall','recalled'),False),
 ('C2_independent_variant_can_close',lambda:closure(['independent','transfer'],'variant','independent'),False),
 ('C3_measured_timed_can_close',lambda:closure(['timed'],'timed_practice','independent'),False),
 ('R2_confirmation_not_before_due',lambda:confirmation(START),False),
 ('C4_confirmation_at_due',lambda:confirmation(NEXT),True),
 ('R3_math_cannot_count_as_english',lambda:subject_candidate('math','english',['english']),False),
 ('R3_contest_label_cannot_bypass_activation',lambda:subject_candidate('math_contest','math',['math']),False),
 ('C5_matching_subject_allowed',lambda:subject_candidate('math','math',['math']),True),
]
results=[]
for name,fn,expected in cases:
    try:
        observed=fn();results.append({'case':name,'expected':expected,'observed':observed,'passed':observed==expected})
    except Exception as exc:
        results.append({'case':name,'error':type(exc).__name__+': '+str(exc),'passed':False})
output={'fixtures':'fictional','engine_version':(core/'VERSION').read_text().strip(),'cases':results,
        'passed':sum(c['passed'] for c in results),'failed':sum(not c['passed'] and 'error' not in c for c in results),
        'execution_errors':sum('error' in c for c in results)}
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(output,indent=2))
