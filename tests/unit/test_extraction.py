import pytest

from backend.agent.router import route
from backend.core.chat import Evidence
from backend.core.errors import DomainError
from backend.core.extraction import ExtractionPlan
from backend.extraction.validation import validate_records


def plan():
    return ExtractionPlan.model_validate(
        {
            "name": "Sites",
            "granularity": "One site per row",
            "record_key": ["site"],
            "fields": [
                {"key": "site", "label": "Site", "type": "string"},
                {"key": "value", "label": "Value", "type": "number", "unit": "mg/L", "minimum": 0},
            ],
        }
    )


def sources():
    return [
        Evidence(
            id="E1",
            document_id="doc",
            asset_id="asset",
            filename="data.csv",
            source_sha256="hash",
            block_id="table",
            quote="Alpha 12.5 mg/L; Beta 8.2 mg/L",
        )
    ]


def output():
    return {
        "records": [
            {
                "fields": {
                    "site": {"value": "Alpha", "evidence_ids": ["E1"]},
                    "value": {"value": 12.5, "unit": "mg/L", "evidence_ids": ["E1"]},
                }
            }
        ],
        "warnings": [],
    }


def test_routes_regular_question_without_design_side_effects():
    assert route("请说明研究问题、方法、结果和局限", None, None, None) == "QA"
    assert route("提取各站点浓度", None, None, None) == "DESIGN"
    assert route("请说明这篇文献的提取方法与局限", None, None, None) == "QA"


def test_valid_records_and_missing_reasons():
    rows, warnings = validate_records(output(), plan(), sources())
    assert rows[0]["values_json"]["value"]["value"] == 12.5
    assert rows[0]["risks"] == []
    raw = output()
    raw["records"][0]["fields"]["value"] = {"value": None, "missing_reason": "未报告"}
    assert (
        validate_records(raw, plan(), sources())[0][0]["values_json"]["value"]["missing_reason"]
        == "未报告"
    )


@pytest.mark.parametrize(
    "replacement",
    [
        {"value": 12.5, "evidence_ids": []},
        {"value": 12.5, "evidence_ids": ["made-up"]},
        {"value": None},
        {"value": "twelve", "evidence_ids": ["E1"]},
    ],
)
def test_rejects_ungrounded_or_wrong_type_values(replacement):
    raw = output()
    raw["records"][0]["fields"]["value"] = replacement
    with pytest.raises(DomainError):
        validate_records(raw, plan(), sources())


def test_duplicate_grain_and_unit_conflicts_stay_visible():
    raw = output()
    raw["records"].append(raw["records"][0].copy())
    raw["records"][0]["fields"]["value"]["unit"] = "ug/L"
    rows, _ = validate_records(raw, plan(), sources())
    assert len(rows) == 2
    assert any("单位" in risk for risk in rows[0]["risks"])
    assert any("重复" in risk for risk in rows[1]["risks"])


def test_document_id_is_filled_from_trusted_context_not_model():
    from backend.core.extraction import FieldDefinition

    schema = plan()
    schema.fields.append(FieldDefinition(key="source_document_id", label="源文档 ID"))
    raw = output()
    raw["records"][0]["fields"]["source_document_id"] = {
        "value": "invented-document",
        "evidence_ids": ["invented-citation"],
    }
    rows, _ = validate_records(raw, schema, sources())
    value = rows[0]["values_json"]["source_document_id"]
    assert value["value"] == "doc"
    assert value["evidence_ids"] == []
    assert any("系统文献索引" in risk for risk in rows[0]["risks"])
    with pytest.raises(DomainError, match="唯一确定"):
        validate_records(raw, schema, sources(), document_id="other-doc")
    other = sources()[0].model_copy(update={"id": "E2", "document_id": "other-doc"})
    with pytest.raises(DomainError, match="唯一确定"):
        validate_records(raw, schema, sources() + [other])
    raw["records"][0]["fields"]["value"]["evidence_ids"] = []
    with pytest.raises(DomainError, match="没有有效原文证据"):
        validate_records(raw, schema, sources())


def test_sample_identifier_still_requires_evidence():
    from backend.core.extraction import FieldDefinition

    schema = plan()
    schema.fields.append(FieldDefinition(key="sample_id", label="样本ID"))
    raw = output()
    raw["records"][0]["fields"]["sample_id"] = {"value": "sample-one"}
    with pytest.raises(DomainError, match="没有有效原文证据"):
        validate_records(raw, schema, sources())
