import pluggy

hookspec = pluggy.HookspecMarker("litextract")
hookimpl = pluggy.HookimplMarker("litextract")


class Hooks:
    @hookspec
    def get_plugin_metadata(self):
        """Return id, version, name and description; no I/O."""

    @hookspec
    def get_schema_templates(self):
        """Return generic schema dictionaries."""

    @hookspec
    def get_synonyms(self):
        """Return canonical term to aliases mapping."""

    @hookspec
    def get_validation_rules(self):
        """Return human-readable domain rules."""

    @hookspec
    def standardize_record(self, record):
        """Return suggested normalized fields; original values remain unchanged."""

    @hookspec
    def post_validate_record(self, record):
        """Return risk messages. Must not access storage, network or UI."""
