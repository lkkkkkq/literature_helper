from copy import deepcopy

import pytest

from backend.core.errors import DomainError
from backend.core.extraction import ExtractionPlan
from backend.plugins.manager import PluginCatalog


def test_no_plugins_keeps_generic_core_usable():
    catalog = PluginCatalog(builtins=())
    assert catalog.metadata() == []
    assert catalog.context([]) == []
    assert catalog.apply([], []) == []


def test_microplastics_preserves_raw_and_normalizes_only_supported_units():
    catalog = PluginCatalog()
    pins = [{"id": "microplastics", "version": "1.0.0"}]
    context = catalog.context(pins)[0]
    assert ExtractionPlan.model_validate(context["templates"][0]).record_key
    raw = {
        "polymer": {"value": "polyethylene", "unit": ""},
        "concentration": {"value": 2000, "unit": "particles/m³"},
    }
    row = {"values_json": deepcopy(raw), "risks": []}
    catalog.apply([row], pins)
    assert row["values_json"]["polymer"]["standardized"]["value"] == "PE"
    assert row["values_json"]["concentration"]["standardized"]["value"] == 2
    assert row["values_json"]["concentration"]["value"] == 2000
    row["values_json"]["concentration"] = {"value": -1, "unit": "mg/L"}
    catalog.apply([row], pins)
    assert row["values_json"]["concentration"]["standardized"] is None
    assert len(row["risks"]) == 2
    with pytest.raises(DomainError, match="版本"):
        catalog.resolve([{"id": "microplastics", "version": "missing"}])


def test_disabled_plugin_does_not_apply_domain_changes():
    row = {"values_json": {"polymer": {"value": "polyethylene", "unit": ""}}, "risks": []}
    PluginCatalog().apply([row], [])
    assert row["values_json"]["polymer"]["standardized"] is None
