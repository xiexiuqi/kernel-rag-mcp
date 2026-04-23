import json
import subprocess
from pathlib import Path
from typing import List, Set, Optional
from .main import Indexer


class IncrementalIndexer(Indexer):
    """增量索引器 - 只更新变更的文件"""
    
    def update_index(
        self,
        base: str,
        target: str,
        subsystems: List[str],
        last_indexed_commit: Optional[str] = None
    ):
        """
        增量更新索引
        
        Args:
            base: 基线 commit
            target: 目标 commit
            subsystems: 子系统列表
            last_indexed_commit: 上次索引的 commit (None 表示全量重建)
        """
        version_ns = self._get_version_namespace(target)
        index_dir = self.index_root / version_ns / "base"
        
        if last_indexed_commit is None or not index_dir.exists():
            print("No existing index found, doing full rebuild...")
            return self.build_index(base, target, subsystems)
        
        # 1. 检测变更文件
        changed_files = self._get_changed_files(last_indexed_commit, target)
        if not changed_files:
            print("No changes detected, skipping index update")
            return index_dir
        
        print(f"Detected {len(changed_files)} changed files")
        
        # 2. 加载现有索引
        existing_chunks = self._load_existing_chunks(index_dir)
        print(f"Existing chunks: {len(existing_chunks)}")
        
        # 3. 移除变更文件相关的旧 chunks
        updated_chunks = [
            c for c in existing_chunks 
            if c.file_path not in changed_files
        ]
        removed_count = len(existing_chunks) - len(updated_chunks)
        print(f"Removed {removed_count} outdated chunks")
        
        # 4. 重新解析变更文件
        new_chunks = []
        for file_path in changed_files:
            # 检查文件是否属于指定子系统
            if any(str(file_path).startswith(subsys) for subsys in subsystems):
                file_chunks = self._parse_file(file_path)
                new_chunks.extend(file_chunks)
        
        print(f"Added {len(new_chunks)} new chunks")
        
        # 5. 合并 chunks
        all_chunks = updated_chunks + new_chunks
        
        # 6. 重新生成 embedding（只对新 chunks）
        if new_chunks:
            texts = [f"{c.name} {c.code[:200]}" for c in new_chunks]
            embeddings = self.embedder.encode(texts)
            
            # 7. 更新向量数据库
            self._update_vector_store(index_dir, new_chunks, embeddings, removed_count)
        
        # 8. 保存更新后的索引
        self._save_chunks(index_dir, all_chunks)
        
        # 9. 更新元数据
        self._update_metadata(index_dir, target, all_chunks)
        
        print(f"Incremental update complete: {len(all_chunks)} total chunks")
        return index_dir
    
    def _get_changed_files(self, old_commit: str, new_commit: str) -> Set[str]:
        """获取两个 commit 之间变更的文件列表"""
        try:
            result = subprocess.run(
                ['git', 'diff', '--name-only', f'{old_commit}..{new_commit}'],
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return set(line.strip() for line in result.stdout.split('\n') if line.strip())
        except Exception as e:
            print(f"Warning: Failed to get changed files: {e}")
        
        return set()
    
    def _load_existing_chunks(self, index_dir: Path) -> List:
        """加载现有 chunks"""
        chunks_file = index_dir / "chunks.json"
        if not chunks_file.exists():
            return []
        
        from .parsers.tree_sitter_c import CodeChunk
        with open(chunks_file) as f:
            data = json.load(f)
        
        return [CodeChunk(**item) for item in data]
    
    def _parse_file(self, file_path: str) -> List:
        """解析单个文件"""
        from .parsers.tree_sitter_c import CodeChunk
        full_path = self.repo_path / file_path
        if not full_path.exists():
            return []
        
        try:
            with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            # 使用 code_indexer 解析
            result = self.code_indexer.index_file(full_path, content)
            return result.chunks if result else []
        except Exception as e:
            print(f"Warning: Failed to parse {file_path}: {e}")
            return []
    
    def _update_vector_store(self, index_dir, new_chunks, embeddings, removed_count):
        """更新向量数据库"""
        from ..storage.vector_store import VectorStore
        
        vector_store = VectorStore(backend="qdrant", path=index_dir / "qdrant")
        collection_name = "code_chunks"
        
        # 删除旧向量（简化实现：重建集合）
        if removed_count > 100:  # 如果变更太多，重建更高效
            print("Too many changes, rebuilding vector store...")
            return self._rebuild_vector_store(index_dir, new_chunks, embeddings)
        
        # 插入新向量
        vector_chunks = []
        for i, chunk in enumerate(new_chunks):
            chunk_id = f"{chunk.file_path}:{chunk.name}"
            vector_chunks.append({
                "id": chunk_id,
                "vector": embeddings[i],
                "metadata": {
                    "name": chunk.name,
                    "file_path": chunk.file_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "subsys": chunk.subsys,
                }
            })
        
        vector_store.insert(vector_chunks)
        print(f"Inserted {len(vector_chunks)} new vectors")
    
    def _rebuild_vector_store(self, index_dir, chunks, embeddings):
        """重建向量存储"""
        import shutil
        from ..storage.vector_store import VectorStore
        
        # 清除旧 Qdrant
        qdrant_dir = index_dir / "qdrant"
        if qdrant_dir.exists():
            shutil.rmtree(qdrant_dir)
        
        vector_store = VectorStore(backend="qdrant", path=qdrant_dir)
        collection_name = "code_chunks"
        vector_store.create_collection(collection_name, self.embedder.dim)
        
        vector_chunks = []
        for i, chunk in enumerate(chunks):
            chunk_id = f"{chunk.file_path}:{chunk.name}"
            vector_chunks.append({
                "id": chunk_id,
                "vector": embeddings[i],
                "metadata": {
                    "name": chunk.name,
                    "file_path": chunk.file_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "subsys": chunk.subsys,
                }
            })
        
        vector_store.insert(vector_chunks)
    
    def _update_metadata(self, index_dir, target, chunks):
        """更新元数据"""
        metadata_file = index_dir / "metadata.json"
        metadata = {
            "repo_path": str(self.repo_path),
            "target": target,
            "chunk_count": len(chunks),
            "embedding_model": self.embedder.model_name,
            "embedding_dim": self.embedder.dim,
            "last_updated": str(Path().stat().st_mtime),
        }
        
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
