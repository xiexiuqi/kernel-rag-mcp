#!/usr/bin/env python3
"""Batch indexing script for kernel-rag-mcp using SiliconFlow API."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kernel_rag_mcp.indexer.code_indexer import CodeIndexer
from kernel_rag_mcp.indexer.embedders.siliconflow_embedder import SiliconFlowEmbedder
from kernel_rag_mcp.storage.vector_store import VectorStore
from kernel_rag_mcp.storage.metadata_store import MetadataStore
from kernel_rag_mcp.config import Config


def main():
    config = Config()
    config.embedding_model = "siliconflow-bge-m3"
    config.embedding_dim = 1024
    
    repo_path = Path.home() / "linux"
    index_root = Path.home() / ".kernel-rag" / "repos" / "linux"
    version = "v7.0"
    
    index_dir = index_root / version / "base"
    index_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Indexing {repo_path} -> {index_dir}")
    
    code_indexer = CodeIndexer()
    embedder = SiliconFlowEmbedder()
    vector_store = VectorStore(backend="qdrant", path=index_dir / "qdrant")
    metadata_store = MetadataStore(index_dir)
    
    subsystems = ["kernel/sched"]
    all_chunks = []
    
    for subsys in subsystems:
        subsys_path = repo_path / subsys
        if not subsys_path.exists():
            continue
        
        results = code_indexer.index_directory(subsys_path)
        for result in results:
            for chunk in result.chunks:
                chunk.set_subsystem(subsys)
            all_chunks.extend(result.chunks)
    
    print(f"Total chunks: {len(all_chunks)}")
    
    vector_store.create_collection("code_chunks", embedder.dim)
    
    batch_size = 10
    total = len(all_chunks)
    
    for i in range(0, total, batch_size):
        batch_end = min(i + batch_size, total)
        batch_chunks = all_chunks[i:batch_end]
        
        texts = [f"{c.name} {c.code[:200]}" for c in batch_chunks]
        
        print(f"Embedding batch {i}-{batch_end}...", flush=True)
        start = time.time()
        embeddings = embedder.encode(texts)
        elapsed = time.time() - start
        print(f"  Done in {elapsed:.1f}s ({elapsed/len(texts):.1f}s per chunk)", flush=True)
        
        vector_chunks = []
        sqlite_chunks = []
        
        for j, chunk in enumerate(batch_chunks):
            rel_path = str(chunk.file_path).replace(str(repo_path) + "/", "")
            chunk_id = f"{rel_path}:{chunk.name}"
            
            vector_chunks.append({
                "id": chunk_id,
                "vector": embeddings[j],
                "metadata": {
                    "name": chunk.name,
                    "file_path": rel_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "subsys": chunk.subsys,
                }
            })
            
            sqlite_chunks.append({
                "id": chunk_id,
                "name": chunk.name,
                "file_path": rel_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "chunk_type": chunk.chunk_type,
                "subsys": chunk.subsys,
                "code_snippet": chunk.code[:500],
            })
        
        vector_store.insert(vector_chunks)
        metadata_store.save_chunks(sqlite_chunks)
        
        print(f"  Indexed {batch_end}/{total} ({100*batch_end//total}%)", flush=True)
    
    metadata_store.save_metadata({
        "repo_path": str(repo_path),
        "version": version,
        "chunk_count": total,
        "embedding_model": embedder.model,
        "embedding_dim": embedder.dim,
    })
    
    if vector_store._qdrant_client:
        vector_store._qdrant_client.close()
    
    print(f"Indexing complete: {total} chunks")


if __name__ == "__main__":
    main()
