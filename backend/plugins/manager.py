from copy import deepcopy
from importlib import import_module
from importlib.metadata import entry_points

import pluggy

from backend.core.errors import DomainError
from backend.plugins.hooks import Hooks


class PluginCatalog:
    def __init__(self, builtins=("backend.plugins.microplastics",)):
        self.plugins = {}
        for module in builtins:
            try:
                self._register(import_module(module).Microplastics())
            except ModuleNotFoundError as error:
                if error.name != module:
                    raise
        # Installed entry points are trusted executable extensions, never loaded from papers.
        for entry in entry_points(group="litextract.plugins"):
            self._register(entry.load()())

    def _register(self, plugin):
        manager = pluggy.PluginManager("litextract")
        manager.add_hookspecs(Hooks)
        manager.register(plugin)
        manager.check_pending()
        metadata = manager.hook.get_plugin_metadata()[0]
        if metadata["id"] in self.plugins:
            raise DomainError("插件标识重复。")
        self.plugins[metadata["id"]] = (metadata, manager)

    def metadata(self):
        return [deepcopy(value[0]) for value in self.plugins.values()]

    def resolve(self, pins):
        managers = []
        for pin in pins:
            found = self.plugins.get(pin["id"])
            if not found or found[0]["version"] != pin["version"]:
                raise DomainError("方案依赖的插件版本不可用，请恢复该版本或重新设计方案。")
            managers.append(found[1])
        return managers

    def context(self, pins):
        result = []
        for manager in self.resolve(pins):
            result.append(
                dict(
                    metadata=manager.hook.get_plugin_metadata()[0],
                    templates=sum(manager.hook.get_schema_templates(), []),
                    synonyms=manager.hook.get_synonyms(),
                    rules=sum(manager.hook.get_validation_rules(), []),
                )
            )
        return result

    def apply(self, records, pins):
        for row in records:
            for field in row["values_json"].values():
                field["standardized"] = None
        for manager in self.resolve(pins):
            for row in records:
                values = row["values_json"]
                for suggestions in manager.hook.standardize_record(record=deepcopy(values)):
                    for key, suggestion in suggestions.items():
                        if key in values:
                            values[key]["standardized"] = suggestion
                for risks in manager.hook.post_validate_record(record=deepcopy(values)):
                    row["risks"].extend(risks)
        return records
