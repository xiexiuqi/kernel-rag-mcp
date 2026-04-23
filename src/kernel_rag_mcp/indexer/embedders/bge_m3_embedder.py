"""
BGE-M3 Embedder for kernel-rag-mcp
Supports Dense + Sparse + ColBERT vectors
"""
import numpy as np
from typing import List, Dict, Union, Optional


class BGEM3Embedder:
    """
    BGE-M3 嵌入器 - 支持多种向量类型
    
    特点:
    - Dense: 1024维语义向量
    - Sparse: Lexical向量 (BM25-like)
    - ColBERT: 多向量表示
    """
    
    def __init__(self, model_name: str = "BAAI/bge-m3", use_fp16: bool = True):
        self._model_name = model_name
        self.use_fp16 = use_fp16
        self._model = None
        self._load_model()
    
    def _load_model(self):
        """加载 BGE-M3 模型"""
        try:
            from FlagEmbedding import BGEM3FlagModel
            self._model = BGEM3FlagModel(
                self.model_name,
                use_fp16=self.use_fp16,
                device="cpu"  # 强制使用CPU
            )
            print(f"BGE-M3 loaded: {self.model_name}")
        except ImportError:
            raise ImportError(
                "FlagEmbedding not installed. "
                "Run: pip install FlagEmbedding"
            )
    
    def encode(
        self,
        texts: Union[str, List[str]],
        return_dense: bool = True,
        return_sparse: bool = True,
        return_colbert: bool = False,
        batch_size: int = 8
    ) -> Dict[str, Union[np.ndarray, List[dict], List[np.ndarray]]]:
        """
        编码文本
        
        Args:
            texts: 文本或文本列表
            return_dense: 是否返回稠密向量
            return_sparse: 是否返回稀疏向量
            return_colbert: 是否返回ColBERT向量
            batch_size: 批处理大小
        
        Returns:
            包含各种向量的字典
        """
        if isinstance(texts, str):
            texts = [texts]
        
        # 使用 BGE-M3 编码
        result = self._model.encode(
            texts,
            batch_size=batch_size,
            max_length=8192,
            return_dense=return_dense,
            return_sparse=return_sparse,
            return_colbert_vecs=return_colbert
        )
        
        return result
    
    def encode_code(
        self,
        code: str,
        language: str = "c"
    ) -> Dict[str, Union[np.ndarray, dict]]:
        """
        专门编码代码片段
        
        添加代码特定的前缀和格式化
        """
        # 添加代码类型前缀 (帮助模型理解)
        formatted = f"{language} code: {code}"
        
        return self.encode(
            formatted,
            return_dense=True,
            return_sparse=True,
            return_colbert=False
        )
    
    def encode_commit(
        self,
        title: str,
        body: Optional[str] = None
    ) -> Dict[str, Union[np.ndarray, dict]]:
        """
        编码 Git commit message
        
        合并 title 和 body，提取关键信息
        """
        text = title
        if body:
            # 清理 body，提取关键句子
            import re
            sentences = re.split(r'[.\n]+', body)
            key_sentences = [
                s.strip() for s in sentences 
                if len(s.strip()) > 20 and len(s.strip()) < 200
            ][:3]
            text += " " + " ".join(key_sentences)
        
        return self.encode(
            text,
            return_dense=True,
            return_sparse=True,
            return_colbert=False
        )
    
    def compute_similarity(
        self,
        query_result: Dict,
        doc_result: Dict,
        weights: Dict[str, float] = None
    ) -> float:
        """
        计算查询和文档的相似度
        
        支持 Dense + Sparse + ColBERT 混合评分
        """
        if weights is None:
            weights = {"dense": 0.5, "sparse": 0.3, "colbert": 0.2}
        
        score = 0.0
        
        # Dense similarity (cosine)
        if "dense" in weights and "dense_vecs" in query_result and "dense_vecs" in doc_result:
            q_dense = query_result["dense_vecs"]
            d_dense = doc_result["dense_vecs"]
            
            # 处理 batch 维度
            if len(q_dense.shape) == 1:
                q_dense = q_dense.reshape(1, -1)
            if len(d_dense.shape) == 1:
                d_dense = d_dense.reshape(1, -1)
            
            sim = np.dot(q_dense, d_dense.T) / (
                np.linalg.norm(q_dense, axis=1, keepdims=True) * 
                np.linalg.norm(d_dense, axis=1, keepdims=True).T
            )
            score += weights["dense"] * float(sim[0, 0])
        
        # Sparse similarity (dot product of lexical weights)
        if "sparse" in weights and "lexical_weights" in query_result and "lexical_weights" in doc_result:
            q_sparse = query_result["lexical_weights"]
            d_sparse = doc_result["lexical_weights"]
            
            # 计算稀疏向量点积
            sim = 0.0
            for token, weight in q_sparse.items():
                if token in d_sparse:
                    sim += weight * d_sparse[token]
            
            # 归一化
            q_norm = sum(w * w for w in q_sparse.values()) ** 0.5
            d_norm = sum(w * w for w in d_sparse.values()) ** 0.5
            if q_norm > 0 and d_norm > 0:
                sim = sim / (q_norm * d_norm)
            
            score += weights["sparse"] * sim
        
        # ColBERT similarity (MaxSim)
        if "colbert" in weights and "colbert_vecs" in query_result and "colbert_vecs" in doc_result:
            q_colbert = query_result["colbert_vecs"]
            d_colbert = doc_result["colbert_vecs"]
            
            # 简化版 MaxSim
            sim = 0.0
            for q_vec in q_colbert:
                max_sim = max(
                    np.dot(q_vec, d_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(d_vec))
                    for d_vec in d_colbert
                )
                sim += max_sim
            score += weights["colbert"] * (sim / len(q_colbert))
        
        return score
    
    @property
    def dim(self) -> int:
        """返回稠密向量维度"""
        return 1024  # BGE-M3 dense dimension
    
    @property
    def model_name(self) -> str:
        return self._model_name


# 兼容性包装器，保持与旧版 CodeEmbedder 相同的接口
class CodeEmbedder(BGEM3Embedder):
    """
    兼容旧版接口的包装器
    """
    def __init__(self, model_name: str = "BAAI/bge-m3", **kwargs):
        super().__init__(model_name=model_name, **kwargs)
    
    def encode(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """兼容旧接口，只返回稠密向量"""
        result = super().encode(texts, return_dense=True, return_sparse=False, return_colbert=False)
        dense = result["dense_vecs"]
        
        # 转换为列表格式
        if len(dense.shape) == 1:
            return [dense.tolist()]
        return dense.tolist()
    
    def encode_commit(self, title: str, body: Optional[str] = None) -> List[float]:
        """兼容旧接口"""
        result = super().encode_commit(title, body)
        return result["dense_vecs"].tolist()
