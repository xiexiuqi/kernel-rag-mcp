import re
import hashlib
import numpy as np
from typing import List, Optional, Union


class CodeEmbedder:
    """Code embedder with multiple backend support."""
    
    def __init__(self, model_name: str = "jina-code-0.5b", dim: int = 896, 
                 model_path: Optional[str] = None):
        """
        Initialize embedder.
        
        Args:
            model_name: "jina-code-0.5b" | "local" | "simple"
            dim: embedding dimension (896 for jina, 768 for local)
            model_path: path to GGUF model file (for jina)
        """
        self._model_name = model_name
        self._dim = dim
        self._model_path = model_path
        self._llm = None
        self._vocab = None
        self._semantic_groups = None
        
        if model_name == "jina-code-0.5b":
            self._init_jina()
        elif model_name == "local":
            self._init_local()
        else:
            self._init_simple()
    
    def _init_jina(self):
        """Initialize Jina-code-embeddings via llama-cpp."""
        try:
            from llama_cpp import Llama
            
            if self._model_path is None:
                # Default path
                self._model_path = "/home/xiexiuqi/models/jinaai/jina-code-embeddings-0___5b-GGUF/jina-code-embeddings-0.5b-IQ2_XS.gguf"
            
            self._llm = Llama(
                model_path=self._model_path,
                embedding=True,
                n_ctx=8192,
                verbose=False
            )
            self._dim = self._llm.n_embd()
            print(f"Jina-code-embeddings loaded: {self._dim} dim")
        except ImportError:
            print("Warning: llama-cpp-python not installed, falling back to local")
            self._init_local()
        except Exception as e:
            print(f"Warning: Failed to load Jina model: {e}, falling back to local")
            self._init_local()
    
    def _init_local(self):
        """Initialize local semantic embedder."""
        self._model_name = "local"
        self._dim = 768
        self._vocab = self._build_vocab()
        self._semantic_groups = self._build_semantic_groups()
        print("Local embedder initialized")
    
    def _init_simple(self):
        """Initialize simple keyword-based embedder."""
        self._model_name = "simple"
        self._dim = 768
        self._vocab = self._build_vocab()
        print("Simple embedder initialized")
    
    def _build_vocab(self) -> dict:
        """Build comprehensive vocabulary for code understanding."""
        keywords = [
            # Data types
            "struct", "int", "void", "static", "inline", "const", "unsigned", "long",
            "char", "bool", "u32", "u64", "s32", "s64", "atomic_t", "spinlock_t",
            
            # Control flow
            "if", "else", "for", "while", "return", "switch", "case", "break",
            "continue", "goto", "do", "default",
            
            # Concurrency
            "spin_lock", "spin_unlock", "mutex", "rcu", "irq", "preempt",
            "smp", "barrier", "lock", "unlock", "read_lock", "write_lock",
            
            # Scheduling
            "sched", "task", "rq", "cpu", "vruntime", "cfs", "fair", "deadline",
            "rt", "idle", "wake_up", "schedule", "pick_next", "enqueue", "dequeue",
            
            # Memory management
            "mm", "page", "slab", "vm", "pte", "pud", "pmd", "folio", "kmem",
            "alloc", "free", "kmalloc", "kfree", "mmap", "unmap",
            
            # Networking
            "tcp", "udp", "ip", "skb", "socket", "net", "packet", "flow",
            "congestion", "rto", "ack", "seq", "window",
            
            # Filesystem
            "inode", "dentry", "superblock", "vfs", "file", "path", "mount",
            
            # Device/Driver
            "device", "driver", "irq", "dma", "pci", "usb", "block",
            
            # Performance
            "cache", "cacheline", "prefetch", "optimize", "performance",
            "latency", "throughput", "bandwidth", "contention", "false_sharing",
            "align", "padding", "hot", "cold",
            
            # Operations
            "read", "write", "open", "close", "init", "exit", "start", "stop",
            "enable", "disable", "register", "unregister", "create", "destroy",
            
            # Error handling
            "error", "err", "warn", "bug", "panic", "oops", "fix", "workaround",
        ]
        return {kw: i for i, kw in enumerate(keywords)}
    
    def _build_semantic_groups(self) -> dict:
        """Build semantic concept groups for better understanding."""
        return {
            "cache_optimization": [
                "cache", "cacheline", "align", "padding", "false_sharing",
                "contention", "bounce", "ping_pong", "hot", "cold",
            ],
            "performance": [
                "performance", "optimize", "improve", "speed", "latency",
                "throughput", "bandwidth", "efficiency", "fast", "slow",
                "bottleneck", "scalability", "concurrent", "parallel",
            ],
            "memory": [
                "memory", "mm", "page", "slab", "alloc", "free", "kmalloc",
                "kfree", "vmalloc", "mmap", "unmap", "pte", "pud", "pmd",
                "folio", "kmem", "cache", "buffer", "pool",
            ],
            "concurrency": [
                "lock", "unlock", "spin_lock", "mutex", "rcu", "irq",
                "preempt", "smp", "atomic", "barrier", "race", "deadlock",
                "contention", "critical_section", "semaphore",
            ],
            "scheduling": [
                "sched", "schedule", "task", "rq", "cpu", "vruntime",
                "cfs", "fair", "deadline", "rt", "idle", "wake_up",
                "pick_next", "enqueue", "dequeue", "migrate", "balance",
            ],
        }
    
    def encode(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """
        Encode texts to embeddings.
        
        Args:
            texts: single text or list of texts
            
        Returns:
            List of embedding vectors
        """
        if isinstance(texts, str):
            texts = [texts]
        
        if self._llm is not None:
            # Use Jina model
            return self._encode_jina(texts)
        else:
            # Use local embedder
            return [self._encode_local(text) for text in texts]
    
    def _encode_jina(self, texts: List[str]) -> List[List[float]]:
        """Encode using Jina-code-embeddings."""
        embeddings = []
        for text in texts:
            emb = self._llm.create_embedding(text)
            vec = emb["data"][0]["embedding"]
            
            # Handle different output formats
            if isinstance(vec, list) and len(vec) > 0 and isinstance(vec[0], list):
                # 2D: tokens x dim, apply mean pooling
                vec = np.array(vec).mean(axis=0).tolist()
            
            embeddings.append(vec)
        
        return embeddings
    
    def _encode_local(self, text: str) -> List[float]:
        """Encode using local semantic method."""
        embedding = [0.0] * self._dim
        
        # Extract tokens
        tokens = re.findall(r"\b\w+\b", text.lower())
        
        # Weight by token importance and semantic groups
        for token in tokens:
            # Check if token is in vocabulary
            if token in self._vocab:
                idx = self._vocab[token] % self._dim
                embedding[idx] += 2.0
            
            # Check semantic groups
            if self._semantic_groups:
                for group_name, group_tokens in self._semantic_groups.items():
                    if token in group_tokens:
                        group_idx = int(hashlib.md5(group_name.encode()).hexdigest(), 16) % self._dim
                        embedding[group_idx] += 1.5
            
            # Hash unknown tokens with lower weight
            hash_val = int(hashlib.md5(token.encode()).hexdigest(), 16) % self._dim
            embedding[hash_val] += 0.3
        
        # Add n-gram features
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]}_{tokens[i+1]}"
            hash_val = int(hashlib.md5(bigram.encode()).hexdigest(), 16) % self._dim
            embedding[hash_val] += 0.5
        
        # Normalize
        import math
        norm = math.sqrt(sum(x * x for x in embedding))
        if norm > 0:
            embedding = [x / norm for x in embedding]
        
        return embedding
    
    def encode_commit(self, title: str, body: Optional[str] = None) -> List[float]:
        """Encode Git commit message for semantic search."""
        text = title
        if body:
            # Extract key sentences from body
            sentences = re.split(r'[.\n]+', body)
            key_sentences = [s.strip() for s in sentences if len(s.strip()) > 20][:3]
            text += " " + " ".join(key_sentences)
        
        return self.encode(text)[0]
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    @property
    def dim(self) -> int:
        return self._dim
