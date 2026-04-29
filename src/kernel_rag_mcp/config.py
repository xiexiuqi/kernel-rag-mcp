import json
from pathlib import Path
from typing import Optional
import os


class Config:
    CONFIG_DIR = Path.home() / ".kernel-rag"
    CONFIG_FILE = CONFIG_DIR / "config.json"

    def __init__(self):
        self._file_config = self._load_file()

        self.kernel_repo = Path(self._get("kernel_repo", Path.home() / "linux"))
        self.index_root = Path(self._get("index_root", Path.home() / ".kernel-rag" / "repos" / "linux"))
        self.embedding_model = self._get("embedding_model", "jina-code-0.5b")
        self.embedding_dim = int(self._get("embedding_dim", "896"))
        self.model_path = self._get("model_path")
        self.vector_backend = self._get("vector_backend", "qdrant")
        self.batch_size = int(self._get("batch_size", "50"))
        self.siliconflow_api_key = self._get("siliconflow_api_key")

    def _load_file(self) -> dict:
        if self.CONFIG_FILE.exists():
            with open(self.CONFIG_FILE, "r") as f:
                return json.load(f)
        return {}

    def _get(self, key: str, default=None):
        env_key = key.upper()
        if env_key in os.environ:
            return os.environ[env_key]
        return self._file_config.get(key, default)

    def save(self):
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "kernel_repo": str(self.kernel_repo),
            "index_root": str(self.index_root),
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
            "model_path": self.model_path,
            "vector_backend": self.vector_backend,
            "batch_size": self.batch_size,
        }
        if self.siliconflow_api_key:
            data["siliconflow_api_key"] = self.siliconflow_api_key
        with open(self.CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def index_dir(self, version: str) -> Path:
        return Path(self.index_root) / version / "base"

    def delta_dir(self, version: str, delta_name: str) -> Path:
        return Path(self.index_root) / version / f"delta-{delta_name}"

    def get_version_ns(self, target: str) -> str:
        if target.startswith("v"):
            parts = target.split(".")
            if len(parts) >= 2:
                major = parts[0][1:]
                minor = parts[1].split("-")[0]
                return f"v{major}.{minor}"
        return target

    def detect_current_version(self) -> str:
        """自动检测内核仓库当前版本"""
        import subprocess
        try:
            result = subprocess.run(
                ["git", "-C", str(self.kernel_repo), "describe", "--tags", "--abbrev=0"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                tag = result.stdout.strip()
                # v7.0-rc6 -> v7.0
                return self.get_version_ns(tag)
        except Exception:
            pass
        
        # 回退：尝试读取 Makefile
        try:
            makefile = self.kernel_repo / "Makefile"
            if makefile.exists():
                with open(makefile) as f:
                    lines = f.readlines()
                version = patch = sublevel = ""
                for line in lines[:20]:
                    if line.startswith("VERSION ="):
                        version = line.split("=")[1].strip()
                    elif line.startswith("PATCHLEVEL ="):
                        patch = line.split("=")[1].strip()
                    elif line.startswith("SUBLEVEL ="):
                        sublevel = line.split("=")[1].strip()
                if version and patch:
                    return f"v{version}.{patch}"
        except Exception:
            pass
        
        return "v7.0"  # 默认回退


_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(config: Config):
    global _config
    _config = config
