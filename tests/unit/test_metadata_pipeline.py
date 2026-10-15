import json

import pytest
from test_extraction import output, plan, sources

from backend.agent.extract_graph import extract
from backend.core.errors import DomainError
from backend.core.extraction import FieldDefinition
from backend.extraction.validation import validate_records


def legacy_plan():
    schema = plan()
    for key, label in [
        ("source_document_id", "源文档 ID"),
        ("missing_reason", "缺失原因"),
        ("risk_notes", "风险提示"),
        ("site_evidence", "Site证据"),
        ("value_quote", "Value原文片段"),
    ]:
        schema.fields.append(FieldDefinition(key=key, label=label))
    return schema


def test_complete_graph_with_legacy_metadata_columns():
    class Model:
        def complete(self, profile, key, messages):
            sent = json.loads(messages[-1]["content"])
            assert [f["key"] for f in sent["plan"]["fields"]] == ["site", "value"]
            result = output()
            result["records"][0]["risks"] = ["需要人工核对"]
            # Old providers may still send invented display-column values.
            result["records"][0]["fields"]["missing_reason"] = {"value": "invented"}
            return result

    rows, _ = extract(Model(), {}, "unused", legacy_plan(), sources())
    values = rows[0]["values_json"]
    assert values["missing_reason"]["value"] == "无缺失字段"
    assert values["source_document_id"]["value"] == "doc"
    assert "需要人工核对" in values["risk_notes"]["value"]
    assert values["value_quote"]["value"] == sources()[0].quote
    assert values["site_evidence"]["evidence_ids"] == ["E1"]


def test_missing_metadata_derived_without_weakening_scientific_evidence():
    raw = output()
    raw["records"][0]["fields"]["value"] = {"value": None, "missing_reason": "未报告"}
    rows, _ = validate_records(raw, legacy_plan(), sources())
    assert rows[0]["values_json"]["missing_reason"]["value"] == "Value：未报告"
    assert rows[0]["values_json"]["value_quote"]["value"] is None
    raw["records"][0]["fields"]["value"] = {"value": 12.5}
    with pytest.raises(DomainError, match="没有有效原文证据"):
        validate_records(raw, legacy_plan(), sources())
