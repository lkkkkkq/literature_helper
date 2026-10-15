"""Legacy schema display columns derived from validated record metadata."""


def metadata_kind(field):
    if field.type != "string":
        return None
    label = field.label.replace(" ", "").casefold()
    if field.key in {"document_id", "source_document_id"} or label in {
        "源文档id",
        "来源文档id",
        "文档id",
    }:
        return "document"
    if field.key in {"missing_reason", "missing_reasons"} or label in {
        "缺失原因",
        "缺失说明",
        "数据缺失原因",
    }:
        return "missing"
    if field.key in {"risk", "risks", "risk_notes", "risk_flags"} or label in {
        "风险提示",
        "风险说明",
        "风险标记",
    }:
        return "risk"
    if label.endswith(("证据", "原文片段")) or field.key.endswith(("_evidence", "_quote")):
        return "evidence"
    return None


def research_plan(plan):
    result = plan.model_dump()
    result["fields"] = [f.model_dump() for f in plan.fields if not metadata_kind(f)]
    keys = {f["key"] for f in result["fields"]}
    result["record_key"] = [key for key in plan.record_key if key in keys]
    return result
