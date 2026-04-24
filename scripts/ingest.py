#!/usr/bin/env python3
"""Batch indexing script for kernel-rag-mcp using SiliconFlow API."""
import os
import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kernel_rag_mcp.indexer.code_indexer import CodeIndexer
from kernel_rag_mcp.indexer.embedders.siliconflow_embedder import SiliconFlowEmbedder
from kernel_rag_mcp.indexer.symbol_indexer import SymbolIndexBuilder
from kernel_rag_mcp.storage.vector_store import VectorStore
from kernel_rag_mcp.storage.metadata_store import MetadataStore
from kernel_rag_mcp.config import Config


def print_progress(current, total, prefix="Progress", suffix=""):
    bar_length = 40
    filled = int(bar_length * current / total)
    bar = "█" * filled + "░" * (bar_length - filled)
    percent = 100 * current / total
    print(f"\r{prefix}: [{bar}] {percent:.1f}% ({current}/{total}) {suffix}", end="", flush=True)


def main():
    api_key = os.environ.get("SILICONFLOW_API_KEY")
    if not api_key:
        print("ERROR: SILICONFLOW_API_KEY environment variable not set")
        print("Set it with: export SILICONFLOW_API_KEY=your_key_here")
        sys.exit(1)
    
    config = Config()
    config.embedding_model = "siliconflow-bge-m3"
    config.embedding_dim = 1024
    
    repo_path = Path.home() / "linux"
    index_root = Path.home() / ".kernel-rag" / "repos" / "linux"
    version = "v7.0"
    
    index_dir = index_root / version / "base"
    index_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = index_dir / "checkpoint.json"
    
    print(f"Indexing {repo_path} -> {index_dir}")
    
    code_indexer = CodeIndexer()
    embedder = SiliconFlowEmbedder(api_key=api_key)
    vector_store = VectorStore(backend="qdrant", path=index_dir / "qdrant")
    metadata_store = MetadataStore(index_dir)
    symbol_builder = SymbolIndexBuilder(repo_path)
    
    subsystems = ["kernel/sched", "mm", "net"]
    all_chunks = []
    
    print("\nPhase 1: Parsing source files...")
    for subsys in subsystems:
        subsys_path = repo_path / subsys
        if not subsys_path.exists():
            continue
        
        results = code_indexer.index_directory(subsys_path)
        for result in results:
            for chunk in result.chunks:
                chunk.set_subsystem(subsys)
            all_chunks.extend(result.chunks)
        print(f"  {subsys}: {len(result.chunks)} chunks")
    
    print(f"\nTotal chunks to index: {len(all_chunks)}")
    
    print("\nPhase 1b: Building symbol index...")
    total_symbols = 0
    for subsys in subsystems:
        subsys_path = repo_path / subsys
        if not subsys_path.exists():
            continue
        symbols = symbol_builder.index_subsystem(subsys_path)
        metadata_store.save_symbols(symbols)
        total_symbols += len(symbols)
        print(f"  {subsys}: {len(symbols)} symbols")
    print(f"  Total symbols: {total_symbols}")
    
    vector_store.create_collection("code_chunks", embedder.dim)
    
    batch_size = 10
    total = len(all_chunks)
    
    start_idx = 0
    if checkpoint_file.exists():
        with open(checkpoint_file) as f:
            checkpoint = json.load(f)
            start_idx = checkpoint.get("last_processed", 0)
        print(f"Resuming from checkpoint: {start_idx}/{total}")
    
    print(f"\nPhase 2: Embedding and indexing (starting from {start_idx})...")
    total_start = time.time()
    
    for i in range(start_idx, total, batch_size):
        batch_end = min(i + batch_size, total)
        batch_chunks = all_chunks[i:batch_end]
        
        texts = [f"{c.name} {c.code[:200]}" for c in batch_chunks]
        
        batch_start = time.time()
        try:
            embeddings = embedder.encode(texts)
        except Exception as e:
            print(f"\nError embedding batch {i}-{batch_end}: {e}")
            print("Saving checkpoint and retrying in 5s...")
            with open(checkpoint_file, "w") as f:
                json.dump({"last_processed": i, "total": total}, f)
            time.sleep(5)
            embeddings = embedder.encode(texts)
        
        batch_elapsed = time.time() - batch_start
        
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
        
        with open(checkpoint_file, "w") as f:
            json.dump({"last_processed": batch_end, "total": total}, f)
        
        eta = (total - batch_end) * (time.time() - total_start) / (batch_end - start_idx + 1) if batch_end > start_idx else 0
        print_progress(batch_end, total, "Indexing", f"ETA: {eta/60:.1f}min")
    
    total_elapsed = time.time() - total_start
    print(f"\n\nIndexing complete: {total - start_idx} chunks in {total_elapsed/60:.1f} minutes")
    print(f"Average: {total_elapsed/(total - start_idx):.2f}s per chunk")
    
    metadata_store.save_metadata({
        "repo_path": str(repo_path),
        "version": version,
        "chunk_count": total,
        "embedding_model": embedder.model,
        "embedding_dim": embedder.dim,
    })
    
    if checkpoint_file.exists():
        checkpoint_file.unlink()
    
    if vector_store._qdrant_client:
        vector_store._qdrant_client.close()


if __name__ == "__main__":
    main()
