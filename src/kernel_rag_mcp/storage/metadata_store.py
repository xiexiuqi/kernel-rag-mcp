import json
from pathlib import Path
from typing import Optional, List


class MetadataStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.metadata_file = self.path / "metadata.json"
    
    def save(self, metadata: dict):
        self.path.mkdir(parents=True, exist_ok=True)
        with open(self.metadata_file, "w") as f:
            json.dump(metadata, f, indent=2)
    
    def load(self) -> Optional[dict]:
        if not self.metadata_file.exists():
            return None
        
        with open(self.metadata_file) as f:
            data = json.load(f)
        
        class Metadata:
            def __init__(self, data):
                self.__dict__.update(data)
        
        return Metadata(data)
    
    def is_fresh(self, commit: str) -> bool:
        meta = self.load()
        if not meta:
            return False
        return getattr(meta, "base_commit", None) == commit or getattr(meta, "target", None) == commit
    
    def has_delta(self, delta_name: str) -> bool:
        # Check metadata deltas list first
        meta = self.load()
        if meta:
            deltas = getattr(meta, "deltas", [])
            if delta_name in deltas:
                return True
        
        # Check filesystem
        delta_dir = self.path.parent / delta_name
        return delta_dir.exists()
    
    def check_consistency(self) -> bool:
        meta = self.load()
        if not meta:
            return False
        return getattr(meta, "base_commit", None) is not None or getattr(meta, "target", None) is not None
    
    def list_deltas(self) -> List[str]:
        version_dir = self.path.parent
        deltas = []
        if version_dir.exists():
            for item in version_dir.iterdir():
                if item.is_dir() and item.name.startswith("delta-"):
                    deltas.append(item.name)
        return sorted(deltas)
    
    def get_current_version(self) -> str:
        current_link = self.path.parent / "current"
        if current_link.exists() and current_link.is_symlink():
            return str(current_link.resolve().name)
        return "base"
    
    def set_current_version(self, version: str):
        current_link = self.path.parent / "current"
        target = self.path.parent / version
        
        if current_link.exists() or current_link.is_symlink():
            current_link.unlink()
        
        current_link.symlink_to(target, target_is_directory=True)
