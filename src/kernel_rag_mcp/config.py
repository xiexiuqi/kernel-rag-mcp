from pathlib import Path
from typing import Optional
import os


class Config:
    def __init__(self):
        self.kernel_repo = Path(os.environ.get("KERNEL_REPO", Path.home() / "linux"))
        self.index_root = Path(os.environ.get(
            "INDEX_PATH",
            Path.home() / ".kernel-rag" / "repos" / "linux"
        ))
        self.embedding_model = os.environ.get("EMBEDDING_MODEL", "jina-code-0.5b")
        self.embedding_dim = int(os.environ.get("EMBEDDING_DIM", "896"))
        self.model_path = os.environ.get("MODEL_PATH")
        self.vector_backend = os.environ.get("VECTOR_BACKEND", "qdrant")
        self.batch_size = int(os.environ.get("BATCH_SIZE", "50"))

    def index_dir(self, version: str) -> Path:
        return self.index_root / version / "base"

    def get_version_ns(self, target: str) -> str:
        if target.startswith("v"):
            parts = target.split(".")
            if len(parts) >= 2:
                major = parts[0][1:]
                minor = parts[1].split("-")[0]
                return f"v{major}.{minor}"
        return target


_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(config: Config):
    global _config
    _config = config
