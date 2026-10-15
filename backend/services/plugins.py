from backend.core.errors import DomainError


class PluginService:
    def __init__(self, repository, catalog):
        self.repository, self.catalog = repository, catalog

    def pins(self, project_id):
        return [
            {"id": row["plugin_id"], "version": row["version"]}
            for row in self.repository.list(project_id)
            if row["enabled"]
        ]

    def list(self, project_id):
        settings = {row["plugin_id"]: row for row in self.repository.list(project_id)}
        return [
            {
                **metadata,
                "enabled": settings.get(metadata["id"], {}).get("enabled", False),
                "configured_version": settings.get(metadata["id"], {}).get("version"),
                "context": self.catalog.context([metadata])[0],
            }
            for metadata in self.catalog.metadata()
        ]

    def set(self, project_id, plugin_id, enabled):
        metadata = next((row for row in self.catalog.metadata() if row["id"] == plugin_id), None)
        if not metadata:
            raise DomainError("插件未安装。", "not_found")
        self.repository.set(project_id, plugin_id, metadata["version"], enabled)
        return self.list(project_id)
