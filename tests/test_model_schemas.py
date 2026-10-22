"""Optional independent JSON Schema verification of generated fictional data."""

import json
import unittest
from importlib.util import find_spec
from pathlib import Path

from scripts.learning_models import fit_models
from tests.test_learning_models import AS_OF, COURSE, EVENTS


@unittest.skipUnless(find_spec("jsonschema"), "optional jsonschema is not installed")
class ModelSchemaTests(unittest.TestCase):
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
