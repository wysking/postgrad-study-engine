"""Optional independent JSON Schema verification of generated fictional data."""

import json
import unittest
from importlib.util import find_spec
from pathlib import Path

from scripts.learning_models import fit_models
from tests.test_learning_models import AS_OF, COURSE, EVENTS


@unittest.skipUnless(find_spec("jsonschema"), "optional jsonschema is not installed")
class ModelSchemaTests(unittest.TestCase):
    def test_study_subject_alias_is_input_only_in_independent_schema(self):
        import jsonschema
        schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas/study_record.schema.json').read_text())
        payload_schema = {'$schema': schema['$schema'], '$defs': schema['$defs'], '$ref': '#/$defs/payload'}
        for fields in ({}, {'subject': 'Fictional subject'}, {'subject_label': 'Fictional subject'},
                       {'subject': 'Fictional subject', 'subject_label': 'Fictional subject'}):
            jsonschema.Draft202012Validator(payload_schema).validate({'summary': 'Fictional observation.', **fields})
        for subject in (None, False, [], ' ', 'x' * 12001):
            with self.assertRaises(jsonschema.ValidationError):
                jsonschema.Draft202012Validator(payload_schema).validate({'summary': 'Fictional', 'subject': subject})
        record = {'schema_version': '1.0', 'record_id': 'fictional-schema', 'request_hash': 'a' * 64,
                  'request_created_at': '2026-01-01T00:00:00Z', 'received_at': '2026-01-01T00:00:01Z',
                  'summary': 'Fictional observation.', 'subject_label': 'Fictional subject'}
        self.validate('study_record.schema.json', record)
        record['subject'] = record['subject_label']
        with self.assertRaises(jsonschema.ValidationError):
            self.validate('study_record.schema.json', record)

    def validate(self, filename, payload):
        import jsonschema
        from referencing import Registry, Resource
        folder = Path(__file__).resolve().parents[1] / "schemas"
        resources = []
        for path in folder.glob("*.json"):
            schema = json.loads(path.read_text(encoding="utf-8"))
            resources.append((schema["$id"], Resource.from_contents(schema)))
        schema = json.loads((folder / filename).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema, registry=Registry().with_resources(resources),
                                       format_checker=jsonschema.FormatChecker()).validate(payload)

    def test_fictional_course(self):
        self.validate("course_package.schema.json", COURSE)

    def test_empty_and_fitted_model_reports(self):
        for events in ([], EVENTS):
            self.validate("learning_model.schema.json", fit_models(events, COURSE["units"], AS_OF, "fictional-a"))

    def test_learner_identity_and_observed_ratings(self):
        self.validate("learner_identity.schema.json", {"schema_version": "1.0", "learner_id": "fictional-a", "mode": "demo"})
        self.validate("fsrs_ratings.schema.json", {"schema_version": "1.0", "learner_id": "fictional-a", "ratings": [
            {"event_id": "fictional-1", "rating": 3, "source": "observed"}]})

    def test_synthetic_calibration_report(self):
        from scripts.calibration_check import run_check
        self.validate("calibration_check.schema.json", run_check(learners=2, trials=8, training_trials=4))
