"""
Local Code Embedder - 纯本地计算，无需预训练模型
基于统计和规则的代码语义嵌入
"""
import re
import hashlib
import numpy as np
from collections import Counter
from typing import List, Optional


class LocalCodeEmbedder:
    """
    基于统计和规则的代码嵌入器
    
    策略:
    1. TF-IDF 加权关键词
    2. n-gram 特征
    3. 代码结构特征
    4. 语义组信号
    """
    
    def __init__(self, dim: int = 768):
        self.dim = dim
        self.keywords = self._load_keywords()
        self.semantic_groups = self._build_semantic_groups()
        self.idf = self._compute_idf()
    
    def _load_keywords(self) -> set:
        """加载代码关键词库"""
        return {
            # 性能相关
            'performance', 'optimize', 'optimization', 'cache', 'cacheline', 
            'latency', 'throughput', 'bandwidth', 'contention', 'false_sharing',
            'prefetch', 'align', 'alignment', 'padding', 'hot', 'cold', 'fast', 'slow',
            
            # 并发相关
            'lock', 'mutex', 'spinlock', 'rcu', 'atomic', 'barrier',
            'race', 'deadlock', 'smp', 'irq', 'preempt', 'concurrent', 'parallel',
            
            # 内存相关
            'alloc', 'allocate', 'free', 'kmalloc', 'kfree', 'page', 'slab',
            'mm', 'vm', 'mmap', 'unmap', 'pte', 'pmd', 'pud', 'folio', 'kmem',
            'memory', 'buffer', 'pool', 'heap', 'stack',
            
            # 调度相关
            'sched', 'schedule', 'scheduler', 'task', 'rq', 'vruntime', 'cfs', 
            'fair', 'deadline', 'rt', 'idle', 'wake_up', 'wakeup', 'enqueue', 
            'dequeue', 'migrate', 'balance', 'pick_next',
            
            # 网络相关
            'tcp', 'udp', 'ip', 'skb', 'socket', 'net', 'network', 'packet',
            'congestion', 'rto', 'ack', 'seq', 'window', 'flow', 'route',
            
            # 数据结构
            'list', 'tree', 'rb_tree', 'rbtree', 'hash', 'map', 'queue', 'stack',
            'array', 'linked_list', 'hashtable',
            
            # 操作
            'read', 'write', 'open', 'close', 'init', 'exit', 'start', 'stop',
            'enable', 'disable', 'register', 'unregister', 'create', 'destroy',
            'get', 'set', 'put', 'add', 'del', 'remove', 'insert', 'append',
            
            # 错误处理
            'error', 'err', 'warn', 'warning', 'bug', 'panic', 'oops', 'fix', 
            'workaround', 'fallback', 'retry',
            
            # 文件系统
            'inode', 'dentry', 'superblock', 'vfs', 'file', 'path', 'mount',
            'fs', 'filesystem', 'ext4', 'xfs', 'btrfs',
            
            # 设备
            'device', 'driver', 'dev', 'dma', 'pci', 'usb', 'block', 'scsi',
        }
    
    def _build_semantic_groups(self) -> dict:
        """构建语义概念组"""
        return {
            'cache_optimization': [
                'cache', 'cacheline', 'align', 'alignment', 'padding', 
                'false_sharing', 'contention', 'bounce', 'hot', 'cold',
                '____cacheline_aligned', '____cacheline_aligned_in_smp',
            ],
            'performance': [
                'performance', 'optimize', 'optimization', 'improve', 'speed', 
                'latency', 'throughput', 'bandwidth', 'efficiency', 'fast', 'slow',
                'bottleneck', 'scalability', 'concurrent', 'parallel',
            ],
            'memory_management': [
                'memory', 'mm', 'page', 'slab', 'alloc', 'allocate', 'free', 
                'kmalloc', 'kfree', 'vmalloc', 'mmap', 'unmap', 'pte', 'pud', 'pmd',
                'folio', 'kmem', 'cache', 'buffer', 'pool', 'heap',
            ],
            'concurrency': [
                'lock', 'unlock', 'spin_lock', 'spin_unlock', 'mutex', 'rcu', 'irq',
                'preempt', 'smp', 'atomic', 'barrier', 'race', 'deadlock',
                'contention', 'semaphore', 'critical_section',
            ],
            'scheduling': [
                'sched', 'schedule', 'scheduler', 'task', 'rq', 'cpu', 'vruntime',
                'cfs', 'fair', 'deadline', 'rt', 'idle', 'wake_up', 'wakeup',
                'pick_next', 'enqueue', 'dequeue', 'migrate', 'balance',
            ],
            'networking': [
                'tcp', 'udp', 'ip', 'skb', 'socket', 'net', 'network', 'packet',
                'congestion', 'rto', 'ack', 'seq', 'window', 'flow', 'route',
            ],
        }
    
    def _compute_idf(self) -> dict:
        """计算简化版 IDF"""
        return {kw: 1.0 for kw in self.keywords}
    
    def encode(self, texts: List[str]) -> List[np.ndarray]:
        """编码文本列表"""
        if isinstance(texts, str):
            texts = [texts]
        return [self._encode_single(text) for text in texts]
    
    def _encode_single(self, text: str) -> np.ndarray:
        """编码单个文本"""
        embedding = np.zeros(self.dim, dtype=np.float32)
        
        # 1. 关键词 TF-IDF
        tokens = self._tokenize(text)
        token_counts = Counter(tokens)
        total = len(tokens) if tokens else 1
        
        for token, count in token_counts.items():
            if token in self.keywords:
                idx = int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dim
                tf = count / total
                idf = self.idf.get(token, 1.0)
                embedding[idx] += tf * idf * 2.0
        
        # 2. n-gram 特征
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]}_{tokens[i+1]}"
            idx = int(hashlib.md5(bigram.encode()).hexdigest(), 16) % self.dim
            embedding[idx] += 0.5
        
        # 3. 代码结构特征
        embedding = self._add_structure_features(text, embedding)
        
        # 4. 语义组信号
        embedding = self._add_semantic_groups(text, embedding)
        
        # 归一化
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        
        return embedding
    
    def _tokenize(self, text: str) -> List[str]:
        """代码分词"""
        # 提取标识符
        tokens = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', text.lower())
        return tokens
    
    def _add_structure_features(self, text: str, embedding: np.ndarray) -> np.ndarray:
        """添加代码结构特征"""
        # 函数定义数量
        func_count = text.count('(') + text.count('{')
        idx = int(hashlib.md5(b'__func_count__').hexdigest(), 16) % self.dim
        embedding[idx] += min(func_count / 10, 1.0)
        
        # 注释比例
        comment_lines = text.count('//') + text.count('/*')
        total_lines = text.count('\n') + 1
        idx = int(hashlib.md5(b'__comment_ratio__').hexdigest(), 16) % self.dim
        embedding[idx] += comment_lines / total_lines if total_lines > 0 else 0
        
        # 缩进层次（表示代码复杂度）
        indent_levels = [len(line) - len(line.lstrip()) for line in text.split('\n') if line.strip()]
        if indent_levels:
            avg_indent = sum(indent_levels) / len(indent_levels)
            idx = int(hashlib.md5(b'__avg_indent__').hexdigest(), 16) % self.dim
            embedding[idx] += min(avg_indent / 40, 1.0)
        
        return embedding
    
    def _add_semantic_groups(self, text: str, embedding: np.ndarray) -> np.ndarray:
        """添加语义组信号"""
        text_lower = text.lower()
        
        for group_name, keywords in self.semantic_groups.items():
            score = sum(1 for kw in keywords if kw in text_lower) / len(keywords)
            if score > 0:
                idx = int(hashlib.md5(group_name.encode()).hexdigest(), 16) % self.dim
                embedding[idx] += score * 1.5
        
        return embedding
    
    def encode_commit(self, title: str, body: Optional[str] = None) -> np.ndarray:
        """编码 Git commit message"""
        text = title
        if body:
            # 提取关键句子
            sentences = re.split(r'[.\n]+', body)
            key_sentences = [s.strip() for s in sentences if len(s.strip()) > 20][:3]
            text += " " + " ".join(key_sentences)
        
        return self._encode_single(text)
    
    @property
    def model_name(self) -> str:
        return "local_semantic"
    
    @property
    def dim(self) -> int:
        return self._dim
    
    @dim.setter
    def dim(self, value: int):
        self._dim = value
