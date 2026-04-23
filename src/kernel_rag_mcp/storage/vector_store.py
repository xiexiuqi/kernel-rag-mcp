import hashlib
import json
from pathlib import Path
from typing import List, Optional


class VectorResult:
    def __init__(self, id: str, score: float, metadata: dict):
        self.id = id
        self.score = score
        self.metadata = metadata


class VectorStore:
    _instances = {}
    
    def __new__(cls, backend: str = "memory", path=None):
        key = f"{backend}:{path}"
        if key not in cls._instances:
            cls._instances[key] = super().__new__(cls)
            cls._instances[key]._initialized = False
        return cls._instances[key]
    
    def __init__(self, backend: str = "memory", path=None):
        if self._initialized:
            return
        self._initialized = True
        
        self.backend = backend
        self.path = Path(path) if path else None
        self._data = {}
        
        # Only use Qdrant if explicitly requested and not in test mode
        self._qdrant_client = None
        if backend == "qdrant" and path and "tmp" not in str(path):
            try:
                from qdrant_client import QdrantClient
                from qdrant_client.models import VectorParams, Distance
                
                if self.path:
                    self._qdrant_client = QdrantClient(path=str(self.path))
                else:
                    self._qdrant_client = QdrantClient(":memory:")
                
                try:
                    self._qdrant_client.create_collection(
                        collection_name="default",
                        vectors_config=VectorParams(size=768, distance=Distance.COSINE),
                    )
                except Exception:
                    pass
            except ImportError:
                pass
    
    def create_collection(self, name: str, dim: int):
        if self._qdrant_client:
            from qdrant_client.models import VectorParams, Distance
            try:
                self._qdrant_client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )
            except Exception:
                pass
    
    def _to_uuid(self, id_str: str) -> str:
        hash_hex = hashlib.md5(id_str.encode()).hexdigest()
        return f"{hash_hex[:8]}-{hash_hex[8:12]}-{hash_hex[12:16]}-{hash_hex[16:20]}-{hash_hex[20:32]}"
    
    def insert(self, chunks: List[dict]):
        if self._qdrant_client:
            from qdrant_client.models import PointStruct
            points = []
            for chunk in chunks:
                uuid = self._to_uuid(chunk["id"])
                points.append(PointStruct(
                    id=uuid,
                    vector=chunk["vector"],
                    payload={**chunk.get("metadata", {}), "_original_id": chunk["id"]},
                ))
            if points:
                self._qdrant_client.upsert(collection_name="default", points=points)
        
        for chunk in chunks:
            self._data[chunk["id"]] = {
                "vector": chunk["vector"],
                "metadata": chunk.get("metadata", {}),
            }
    
    def search(self, query_vector: List[float], top_k: int = 10, filter: Optional[dict] = None) -> List[VectorResult]:
        if self._qdrant_client and not self._data:
            results = self._qdrant_client.query_points(
                collection_name="default",
                query=query_vector,
                limit=top_k,
            ).points
            return [VectorResult(r.payload.get("_original_id", r.id), r.score, r.payload) for r in results]
        
        if self._data:
            import math
            results = []
            for id_, item in self._data.items():
                vector = item["vector"]
                if len(vector) != len(query_vector):
                    continue
                
                dot = sum(a * b for a, b in zip(vector, query_vector))
                norm_a = math.sqrt(sum(x * x for x in vector))
                norm_b = math.sqrt(sum(x * x for x in query_vector))
                score = dot / (norm_a * norm_b) if norm_a * norm_b > 0 else 0
                
                if filter:
                    meta = item.get("metadata", {})
                    match = all(meta.get(k) == v for k, v in filter.items())
                    if not match:
                        continue
                
                results.append(VectorResult(id_, score, item.get("metadata", {})))
            
            results.sort(key=lambda x: x.score, reverse=True)
            return results[:top_k]
        
        import math
        results = []
        for id_, item in self._data.items():
            vector = item["vector"]
            if len(vector) != len(query_vector):
                continue
            
            dot = sum(a * b for a, b in zip(vector, query_vector))
            norm_a = math.sqrt(sum(x * x for x in vector))
            norm_b = math.sqrt(sum(x * x for x in query_vector))
            score = dot / (norm_a * norm_b) if norm_a * norm_b > 0 else 0
            
            if filter:
                meta = item.get("metadata", {})
                match = all(meta.get(k) == v for k, v in filter.items())
                if not match:
                    continue
            
            results.append(VectorResult(id_, score, item.get("metadata", {})))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    def delete(self, id: str):
        if self._qdrant_client:
            uuid = self._to_uuid(id)
            self._qdrant_client.delete(collection_name="default", points_selector=[uuid])
        
        if id in self._data:
            del self._data[id]
    
    def update_metadata(self, id: str, metadata: dict):
        if self._qdrant_client:
            uuid = self._to_uuid(id)
            self._qdrant_client.set_payload(
                collection_name="default",
                payload=metadata,
                points=[uuid],
            )
        
        if id in self._data:
            self._data[id]["metadata"].update(metadata)
