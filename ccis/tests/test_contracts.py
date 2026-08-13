from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any


CCIS = Path(__file__).resolve().parents[1]
CONTRACTS = CCIS / "contracts"
EXAMPLES = CONTRACTS / "examples"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_local(schema: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise AssertionError(f"external schema reference is not contract-local: {reference}")
    value: Any = schema
    for part in reference[2:].split("/"):
        value = value[part.replace("~1", "/").replace("~0", "~")]
    if not isinstance(value, dict):
        raise AssertionError(f"schema reference does not resolve to an object: {reference}")
    return value


def type_matches(value: Any, expected: str) -> bool:
    mapping = {
        "object": dict,
        "array": list,
        "string": str,
        "boolean": bool,
        "null": type(None),
    }
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, mapping[expected])


def validate(value: Any, node: dict[str, Any], root: dict[str, Any], path: str = "$") -> list[str]:
    if "$ref" in node:
        return validate(value, resolve_local(root, node["$ref"]), root, path)

    errors: list[str] = []
    if "const" in node and value != node["const"]:
        errors.append(f"{path}: expected const {node['const']!r}")
    if "enum" in node and value not in node["enum"]:
        errors.append(f"{path}: {value!r} is outside enum")

    expected = node.get("type")
    if expected:
        expected_types = [expected] if isinstance(expected, str) else expected
        if not any(type_matches(value, item) for item in expected_types):
            return errors + [f"{path}: expected type {expected_types}, got {type(value).__name__}"]

    if "oneOf" in node:
        branches = [validate(value, branch, root, path) for branch in node["oneOf"]]
        passing = sum(not branch_errors for branch_errors in branches)
        if passing != 1:
            errors.append(f"{path}: expected exactly one oneOf branch, got {passing}")

    if isinstance(value, dict):
        required = node.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required property {key}")
        properties = node.get("properties", {})
        if node.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}: unexpected property {key}")
        for key, child in properties.items():
            if key in value:
                errors.extend(validate(value[key], child, root, f"{path}.{key}"))

    if isinstance(value, list):
        if len(value) < node.get("minItems", 0):
            errors.append(f"{path}: too few items")
        if "maxItems" in node and len(value) > node["maxItems"]:
            errors.append(f"{path}: too many items")
        if node.get("uniqueItems"):
            normalized = [json.dumps(item, sort_keys=True) for item in value]
            if len(set(normalized)) != len(normalized):
                errors.append(f"{path}: items are not unique")
        item_schema = node.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(validate(item, item_schema, root, f"{path}[{index}]"))

    if isinstance(value, str):
        if len(value) < node.get("minLength", 0):
            errors.append(f"{path}: string is too short")
        if "maxLength" in node and len(value) > node["maxLength"]:
            errors.append(f"{path}: string is too long")
        if "pattern" in node and not re.search(node["pattern"], value):
            errors.append(f"{path}: does not match {node['pattern']}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in node and value < node["minimum"]:
            errors.append(f"{path}: below minimum")
        if "maximum" in node and value > node["maximum"]:
            errors.append(f"{path}: above maximum")

    for child in node.get("allOf", []):
        if "if" in child:
            if not validate(value, child["if"], root, path):
                errors.extend(validate(value, child.get("then", {}), root, path))
            elif "else" in child:
                errors.extend(validate(value, child["else"], root, path))
        else:
            errors.extend(validate(value, child, root, path))
    return errors


class CCISContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = load(CONTRACTS / "registry.json")
        cls.schemas = {
            entry["object"]: load(CONTRACTS / entry["path"])
            for entry in cls.registry["contracts"]
        }
        cls.examples = {
            load(path)["ccis_object"]: load(path)
            for path in EXAMPLES.glob("*.json")
        }

    def test_registry_has_unique_object_and_path_authorities(self) -> None:
        entries = self.registry["contracts"]
        self.assertEqual(7, len(entries))
        self.assertEqual(len(entries), len({entry["object"] for entry in entries}))
        self.assertEqual(len(entries), len({entry["path"] for entry in entries}))

    def test_schemas_are_strict_draft_2020_12_contracts(self) -> None:
        ids = set()
        for object_name, schema in self.schemas.items():
            with self.subTest(object_name=object_name):
                self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
                self.assertTrue(schema["$id"].startswith("https://leafos.local/ccis/contracts/"))
                self.assertNotIn(schema["$id"], ids)
                ids.add(schema["$id"])
                self.assertFalse(schema["additionalProperties"])
                self.assertEqual(object_name, schema["properties"]["ccis_object"]["const"])

    def test_every_schema_has_a_valid_example(self) -> None:
        self.assertEqual(set(self.schemas), set(self.examples))
        for object_name, example in self.examples.items():
            with self.subTest(object_name=object_name):
                self.assertEqual([], validate(example, self.schemas[object_name], self.schemas[object_name]))

    def test_task_envelope_carries_complete_authority_boundary(self) -> None:
        envelope = self.examples["ccis.task_envelope"]
        self.assertTrue(envelope["objective"]["invariants"])
        self.assertTrue(envelope["objective"]["tolerances"])
        self.assertTrue(envelope["objective"]["stopping_conditions"])
        self.assertTrue(envelope["validators"])
        self.assertEqual("once", envelope["mode"])
        self.assertFalse(envelope["authority"]["may_merge"])
        self.assertEqual("explicit_operator", envelope["authority"]["acceptance_mode"])
        self.assertFalse(envelope["authority"]["automatic_working_tree_merge"])

    def test_gate_and_outcome_vocabulary_is_exact(self) -> None:
        outcomes = ["ACCEPTED", "REVISE", "REJECTED", "BLOCKED", "ESCALATED"]
        self.assertEqual(outcomes, self.schemas["ccis.decision"]["properties"]["outcome"]["enum"])
        self.assertIn("GATED", self.schemas["ccis.transition"]["$defs"]["state"]["enum"])
        evaluation = self.examples["ccis.evaluation"]
        self.assertEqual("GATED", evaluation["gate_state"])
        self.assertEqual(
            [f"constitutional.q{index}" for index in range(1, 5)],
            [item["question_id"] for item in evaluation["constitutional_questions"]],
        )
        self.assertEqual(
            [
                "Is the proposed transition bounded?",
                "Is there sufficient evidence?",
                "Is the new state better, or at least defensibly safer?",
                "What is the only legal next action?",
            ],
            [item["question"] for item in evaluation["constitutional_questions"]],
        )

    def test_candidate_and_accepted_decision_do_not_touch_working_tree(self) -> None:
        self.assertFalse(self.examples["ccis.candidate"]["working_tree_applied"])
        decision = self.examples["ccis.decision"]
        self.assertTrue(decision["staging_required"])
        self.assertFalse(decision["working_tree_merged"])

    def test_event_and_evidence_contracts_preserve_authority(self) -> None:
        event = self.examples["ccis.event"]
        self.assertGreater(event["sequence"], 0)
        self.assertTrue(event["previous_event_hash"].startswith("sha256:"))
        bundle = self.examples["ccis.evidence_bundle"]
        self.assertEqual(18, len(bundle["artifacts"]))
        self.assertIn("candidate.diff", {artifact["path"] for artifact in bundle["artifacts"].values()})

    def test_canonical_principle_projection_and_bindings_are_hash_locked(self) -> None:
        principles = CCIS / "principles"
        manifest = load(principles / "manifest.json")
        import hashlib

        projected = hashlib.sha256((principles / manifest["canonical_source"]["path"]).read_bytes()).hexdigest()
        self.assertEqual(f"sha256:{projected}", manifest["canonical_source"]["projection_sha256"])
        self.assertEqual(4, len(manifest["questions"]))
        self.assertEqual(
            [item["question_ref"] for item in manifest["questions"]],
            [item["question_ref"] for item in self.examples["ccis.evaluation"]["constitutional_questions"]],
        )


if __name__ == "__main__":
    unittest.main()
