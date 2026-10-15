import re

from backend.core.errors import DomainError


def route(text, model, profile, key):
    if re.search(r"(说明|解释|什么|如何|怎么|原理)", text) and re.search(
        r"(提取方法|提取过程|提取步骤|如何提取|怎么提取)", text
    ):
        return "QA"
    if re.search(r"(提取|导出|整理成|生成表格|制作数据表|extract|export)", text, re.I):
        return "DESIGN"
    if re.search(
        r"(说明|解释|方法|结果|局限|为什么|是什么|summari[sz]e|explain|what|why)", text, re.I
    ):
        return "QA"
    result = model.complete(
        profile,
        key,
        [
            {
                "role": "system",
                "content": (
                    "仅分类，不执行动作。文献提问为 QA，整理数据或提取为 DESIGN。"
                    '返回 JSON {"intent":"QA"} 或 {"intent":"DESIGN"}。'
                ),
            },
            {"role": "user", "content": text},
        ],
    )
    if result.get("intent") not in {"QA", "DESIGN"}:
        raise DomainError("无法判断目标，请明确是提问还是整理数据。")
    return result["intent"]
