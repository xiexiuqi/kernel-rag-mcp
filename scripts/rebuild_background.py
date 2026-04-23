#!/usr/bin/env python3
import sys
import time
import shutil
from pathlib import Path

sys.path.insert(0, '/mnt/data1/git/kernel-rag-mcp/src')

from kernel_rag_mcp.indexer.main import Indexer

def main():
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting background rebuild...")
    
    repo_path = Path('/mnt/data1/git/linux')
    index_root = Path('/home/xiexiuqi/.kernel-rag/repos/linux')
    
    old_qdrant = index_root / 'v7.0-rc6' / 'base' / 'qdrant'
    if old_qdrant.exists():
        shutil.rmtree(old_qdrant)
        print("Cleared old Qdrant index")
    
    indexer = Indexer(
        repo_path=repo_path,
        index_root=index_root,
        model_name='jina-code-0.5b'
    )
    
    subsystems = ['kernel/sched', 'mm', 'net']
    
    print(f"Indexing: {subsystems}")
    start = time.time()
    
    try:
        result = indexer.build_index(
            base='v7.0-11782-gc1f49dea2b8f',
            target='HEAD',
            subsystems=subsystems
        )
        
        elapsed = time.time() - start
        print(f"Rebuild complete in {elapsed/60:.1f} minutes")
        print(f"Result: {result}")
        
        # Verify
        import json
        with open(index_root / 'v7.0-rc6' / 'base' / 'metadata.json') as f:
            meta = json.load(f)
        print(f"Model: {meta['embedding_model']}")
        print(f"Chunks: {meta['chunk_count']}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
