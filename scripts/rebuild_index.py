#!/usr/bin/env python3
import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, '/mnt/data1/git/kernel-rag-mcp/src')

from kernel_rag_mcp.indexer.incremental_indexer import IncrementalIndexer

def main():
    parser = argparse.ArgumentParser(description='Rebuild or update kernel-rag index')
    parser.add_argument('--force', action='store_true', help='Force full rebuild')
    args = parser.parse_args()
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting index update...")
    print("Model: jina-code-embeddings-0.5b")
    
    repo_path = Path('/mnt/data1/git/linux')
    index_root = Path('/home/xiexiuqi/.kernel-rag/repos/linux')
    
    indexer = IncrementalIndexer(
        repo_path=repo_path,
        index_root=index_root,
        model_name='jina-code-0.5b'
    )
    
    subsystems = ['kernel/sched', 'mm', 'net', 'fs', 'block', 'crypto', 'ipc', 'security']
    
    print(f"Indexing subsystems: {subsystems}")
    start = time.time()
    
    import json
    metadata_file = index_root / 'v7.0-rc6' / 'base' / 'metadata.json'
    last_commit = None
    
    if not args.force and metadata_file.exists():
        with open(metadata_file) as f:
            meta = json.load(f)
        # Check if model changed
        if meta.get('embedding_model') == 'jina-code-0.5b':
            last_commit = meta.get('target')
            print(f"Last indexed commit: {last_commit}")
        else:
            print(f"Model changed from {meta.get('embedding_model')} to jina-code-0.5b, forcing rebuild")
            args.force = True
    else:
        args.force = True
    
    if args.force:
        print("Force rebuild requested")
        last_commit = None
    
    result = indexer.update_index(
        base='v7.0-11782-gc1f49dea2b8f',
        target='HEAD',
        subsystems=subsystems,
        last_indexed_commit=last_commit
    )
    
    elapsed = time.time() - start
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Index update complete!")
    print(f"Time: {elapsed/60:.1f} minutes")
    print(f"Result: {result}")

if __name__ == '__main__':
    main()
