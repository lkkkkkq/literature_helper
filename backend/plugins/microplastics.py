from backend.plugins.hooks import hookimpl


class Microplastics:
    @hookimpl
    def get_plugin_metadata(self):
        return dict(
            id="microplastics",
            version="1.0.0",
            name="微塑料",
            description="采样站点模板、聚合物术语、粒子数单位与非负校验",
        )

    @hookimpl
    def get_schema_templates(self):
        return [
            {
                "name": "微塑料站点数据",
                "granularity": "每个站点、采样时间、介质与聚合物组合一行",
                "record_key": ["site", "sample_date", "matrix", "polymer"],
                "fields": [
                    {"key": "site", "label": "采样站点"},
                    {"key": "sample_date", "label": "采样时间"},
                    {"key": "matrix", "label": "样品介质"},
                    {"key": "polymer", "label": "聚合物类型"},
                    {
                        "key": "concentration",
                        "label": "丰度",
                        "type": "number",
                        "minimum": 0,
                        "description": "保留原文丰度单位；质量浓度与粒子数丰度不能互换",
                    },
                    {
                        "key": "particle_size",
                        "label": "粒径",
                        "type": "number",
                        "minimum": 0,
                        "unit": "µm",
                    },
                ],
            }
        ]

    @hookimpl
    def get_synonyms(self):
        return {
            "PE": ["polyethylene", "聚乙烯"],
            "PP": ["polypropylene", "聚丙烯"],
            "PS": ["polystyrene", "聚苯乙烯"],
            "PET": ["polyethylene terephthalate", "聚对苯二甲酸乙二醇酯"],
        }

    @hookimpl
    def get_validation_rules(self):
        return [
            "丰度和粒径不能为负",
            "质量浓度不能自动换算为粒子数丰度",
            "水体体积单位不能自动换算为沉积物质量单位",
            "归一化建议保留原始数值和单位",
        ]

    @hookimpl
    def standardize_record(self, record):
        suggestions = {}
        polymer = record.get("polymer", {}).get("value")
        if isinstance(polymer, str):
            for canonical, aliases in self.get_synonyms().items():
                if polymer.casefold() in {text.casefold() for text in [canonical, *aliases]}:
                    suggestions["polymer"] = {
                        "value": canonical,
                        "unit": "",
                        "note": "聚合物同义词归一化",
                    }
        concentration = record.get("concentration", {})
        value, unit = concentration.get("value"), concentration.get("unit", "")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if unit.casefold().replace(" ", "") in {
                "items/m3",
                "items/m³",
                "particles/m3",
                "particles/m³",
            }:
                suggestions["concentration"] = {
                    "value": value / 1000,
                    "unit": "items/L",
                    "note": "1 m³ = 1000 L，仅粒子数/体积单位换算",
                }
        return suggestions

    @hookimpl
    def post_validate_record(self, record):
        risks = []
        for key in ["concentration", "particle_size"]:
            value = record.get(key, {}).get("value")
            if isinstance(value, (float, int)) and value < 0:
                risks.append(f"微塑料规则：{key} 为负值")
        unit = record.get("concentration", {}).get("unit", "").casefold()
        if unit.startswith(("mg/", "µg/", "ug/", "g/")):
            risks.append("微塑料规则：当前为质量浓度，不能直接当作粒子数丰度")
        return risks
