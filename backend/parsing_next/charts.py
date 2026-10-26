"""Explicit user-calibrated digitization. No inferred axes, units, or series."""

import math

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.core.errors import DomainError


class Point(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    category: str = ""
    label_value: float | None = None
    rgb: tuple[int, int, int] | None = None


class ChartInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    resource: str
    panel: str = Field(min_length=1, max_length=100)
    series: str = Field(min_length=1, max_length=100)
    kind: str
    x_unit: str = ""
    y_unit: str = ""
    origin: Point
    x_reference: Point
    y_reference: Point
    x_min: float = 0
    x_max: float = 1
    y_min: float = 0
    y_max: float = 1
    x_log: bool = False
    y_log: bool = False
    points: list[Point] = Field(max_length=10000)
    color_scale: list[Point] = Field(default_factory=list, max_length=32)
    confirmed: bool = False
    calibrated: bool = False
    reason: str = Field(default="", max_length=1000)
    base_revision: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_chart(self):
        if self.kind not in {
            "curve",
            "scatter",
            "bar",
            "pie",
            "heatmap",
            "manual",
            "not_applicable",
        }:
            raise ValueError("Unsupported chart type")
        for log, low, high in [
            (self.x_log, self.x_min, self.x_max),
            (self.y_log, self.y_min, self.y_max),
        ]:
            if log and min(low, high) <= 0:
                raise ValueError("Log axis requires positive bounds")
        return self


def calibrated(point, specification):
    origin, xr, yr = specification.origin, specification.x_reference, specification.y_reference
    a, b, c, d = xr.x - origin.x, yr.x - origin.x, xr.y - origin.y, yr.y - origin.y
    determinant = a * d - b * c
    if abs(determinant) < 1e-8:
        raise DomainError("坐标标定点重合或共线，请重新选择原点、X 参考点和 Y 参考点。")
    dx, dy = point.x - origin.x, point.y - origin.y
    u, v = (d * dx - b * dy) / determinant, (a * dy - c * dx) / determinant

    def scale(value, low, high, logarithmic):
        if low == high:
            raise DomainError("标定数值范围不能相同。")
        if logarithmic:
            return math.exp(math.log(low) + value * (math.log(high) - math.log(low)))
        return low + value * (high - low)

    return scale(u, specification.x_min, specification.x_max, specification.x_log), scale(
        v, specification.y_min, specification.y_max, specification.y_log
    )


def color_value(rgb, stops):
    if rgb is None or len(stops) < 2 or any(s.rgb is None or s.label_value is None for s in stops):
        raise DomainError("热力图需要至少两个带数值和颜色的色标点，以及采样点颜色。")
    candidates = []
    for left, right in zip(stops, stops[1:], strict=False):
        delta = [b - a for a, b in zip(left.rgb, right.rgb, strict=True)]
        norm = sum(v * v for v in delta)
        if norm == 0:
            continue
        t = max(
            0.0,
            min(1.0, sum((v - a) * d for v, a, d in zip(rgb, left.rgb, delta, strict=True)) / norm),
        )
        distance = math.sqrt(
            sum((v - (a + t * d)) ** 2 for v, a, d in zip(rgb, left.rgb, delta, strict=True))
        )
        candidates.append((distance, left.label_value + t * (right.label_value - left.label_value)))
    if not candidates:
        raise DomainError("色标颜色无法区分，请重新标定。")
    residual, value = min(candidates)
    return {
        "value": value,
        "color_residual": residual,
        "warning": "颜色偏离色标，不能可靠读数" if residual > 30 else "颜色插值估计，需人工核对",
    }


def digitize(specification: ChartInput):
    if specification.kind not in {"manual", "not_applicable"} and not specification.calibrated:
        raise DomainError("请先核对坐标轴／圆心／色标，并确认已完成标定。")
    output = []
    if specification.kind == "not_applicable":
        if not specification.reason.strip():
            raise DomainError("请填写无法提取或不适用的原因。")
        return []
    for index, point in enumerate(specification.points):
        row = {
            "pixel": [point.x, point.y],
            "category": point.category,
            "series": specification.series,
            "panel": specification.panel,
            "data_origin": "image_estimate",
        }
        if specification.kind == "manual":
            if point.label_value is None:
                raise DomainError("人工标注值不能为空。")
            row.update(value=point.label_value, data_origin="chart_label")
        elif specification.kind == "pie":
            if point.label_value is not None:
                row.update(value=point.label_value, data_origin="chart_label")
            else:
                if len(specification.points) < 2:
                    raise DomainError("饼图几何估计至少需要两个顺时针边界点。")
                following = specification.points[(index + 1) % len(specification.points)]
                center = specification.origin
                start = math.atan2(point.y - center.y, point.x - center.x)
                end = math.atan2(following.y - center.y, following.x - center.x)
                row.update(
                    value=((end - start) % (2 * math.pi)) / (2 * math.pi) * 100,
                    assumption="平面圆形、无透视；点按顺时针扇区边界排列，单位 %",
                )
        else:
            x, y = calibrated(point, specification)
            row.update(x=x, y=y, x_unit=specification.x_unit, y_unit=specification.y_unit)
            if specification.kind == "bar":
                if not point.category.strip():
                    raise DomainError("柱状图的每个点必须填写类别。")
                row["value"] = y
            if specification.kind == "heatmap":
                row.update(color_value(point.rgb, specification.color_scale))
        output.append(row)
    if specification.kind == "pie" and output:
        total = sum(row["value"] for row in output)
        if abs(total - 100) > 1:
            raise DomainError("饼图比例总和不接近 100%，请检查扇区顺序或标注值。")
    return output
