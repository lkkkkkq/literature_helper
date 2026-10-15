import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    api_token: str

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.environ.get("LITEXTRACT_API_TOKEN", "")
        if not token:
            raise RuntimeError("LITEXTRACT_API_TOKEN is required; start via npm run dev")
        return cls(Path(os.environ["LITEXTRACT_DATA_DIR"]).resolve(), token)
