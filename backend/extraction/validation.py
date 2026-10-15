import json
import math
from copy import deepcopy

from backend.core.errors import DomainError
from backend.core.extraction import ExtractedField, ExtractionOutput
from backend.extraction.metadata import metadata_kind


def is_document_id_field(field):
    """Only explicit system document identifiers, never scientific sample IDs."""
    return metadata_kind(field) == "document"


def validate_records(output, plan, sources, document_id=None):
    output = deepcopy(output)
    derived = [field for field in plan.fields if metadata_kind(field)]
    for record in output.get("records", []):
        for field in derived:
            record.setdefault("fields", {})[field.key] = {
                "value": None,
                "missing_reason": "由系统生成",
            }
    parsed = ExtractionOutput.model_validate(output)
    if not parsed.records and not parsed.warnings:
        raise DomainError("模型未返回记录，也未说明无记录的原因。")
    by_id = {item.id: item for item in sources}
    expected = {field.key for field in plan.fields}
    assembled, keys = [], set()
    for record in parsed.records:
        if set(record.fields) != expected:
            raise DomainError("提取记录字段与确认方案不一致。")
        risks = list(record.risks)
        used = set()
        for field in plan.fields:
            if is_document_id_field(field):
                source_documents = {item.document_id for item in sources}
                trusted_id = document_id or (
                    next(iter(source_documents)) if len(source_documents) == 1 else None
                )
                if not trusted_id or source_documents - {trusted_id}:
                    raise DomainError("无法唯一确定源文档 ID，拒绝使用模型生成的标识。")
                record.fields[field.key] = ExtractedField(value=trusted_id)
                risks.append(f"{field.label} 由系统文献索引填充，不是论文原文数据")
                continue
            if metadata_kind(field):
                continue
            value = record.fields[field.key]
            if any(item not in by_id for item in value.evidence_ids):
                raise DomainError(f"字段 {field.label} 引用不存在的原文。")
            if value.value is None:
                if not value.missing_reason:
                    raise DomainError(f"字段 {field.label} 缺失但没有原因。")
            else:
                if not value.evidence_ids or any(item not in by_id for item in value.evidence_ids):
                    raise DomainError(f"字段 {field.label} 没有有效原文证据。")
                if field.type == "number" and (
                    isinstance(value.value, bool)
                    or not isinstance(value.value, (int, float))
                    or not math.isfinite(value.value)
                ):
                    raise DomainError(f"字段 {field.label} 不是有限数值。")
                if field.type == "string" and not isinstance(value.value, str):
                    raise DomainError(f"字段 {field.label} 类型应为文本。")
                if field.type == "boolean" and not isinstance(value.value, bool):
                    raise DomainError(f"字段 {field.label} 类型应为布尔值。")
                if field.unit and value.unit != field.unit:
                    risks.append(f"{field.label} 单位与目标单位不一致：{value.unit or '未注明'}")
                if field.type == "number":
                    if field.minimum is not None and value.value < field.minimum:
                        risks.append(f"{field.label} 小于允许最小值")
                    if field.maximum is not None and value.value > field.maximum:
                        risks.append(f"{field.label} 大于允许最大值")
                if (
                    str(value.value).casefold()
                    not in " ".join(by_id[item].quote for item in value.evidence_ids).casefold()
                ):
                    risks.append(f"{field.label} 的值未在引文中逐字出现，需要复核")
            used.update(item for item in value.evidence_ids if item in by_id)
        identity = json.dumps(
            [record.fields[key].value for key in plan.record_key], ensure_ascii=False
        )
        if identity in keys:
            risks.append("记录标识重复或存在冲突，保留独立记录待复核")
        keys.add(identity)
        if any(record.fields[key].value is None for key in plan.record_key):
            risks.append("记录标识字段缺失，粒度需要复核")
        research = [field for field in plan.fields if not metadata_kind(field)]
        for field in derived:
            kind = metadata_kind(field)
            if kind == "document":
                continue
            ids = []
            if kind == "missing":
                text = (
                    "；".join(
                        f"{f.label}：{record.fields[f.key].missing_reason}"
                        for f in research
                        if record.fields[f.key].value is None
                    )
                    or "无缺失字段"
                )
            elif kind == "risk":
                text = "；".join(dict.fromkeys(risks)) or "未标记风险（不代表已人工核实）"
            else:
                stem = field.label.removesuffix("原文片段").removesuffix("证据").strip()
                key_stem = field.key.removesuffix("_evidence").removesuffix("_quote")
                targets = [f for f in research if ((stem and stem in f.label) or f.key == key_stem)]
                selected = {item for f in targets for item in record.fields[f.key].evidence_ids}
                if not stem or stem in {"原文", "来源"}:
                    selected = used
                ids = [item.id for item in sources if item.id in selected][:30]
                text = "\n".join(by_id[item].quote for item in ids)
            record.fields[field.key] = ExtractedField(
                value=text or None,
                evidence_ids=ids[:30],
                missing_reason="当前记录没有可引用证据" if not text else "",
            )
        assembled.append(
            {
                "values_json": {key: value.model_dump() for key, value in record.fields.items()},
                "evidence_json": [item.model_dump() for item in sources if item.id in used],
                "risks": risks,
            }
        )
    return assembled, parsed.warnings
