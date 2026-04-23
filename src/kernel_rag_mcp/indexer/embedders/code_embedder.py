import re
import hashlib
from typing import List, Optional


class CodeEmbedder:
    """Semantic-aware code embedder with concept grouping."""
    
    def __init__(self, model_name: str = "semantic", dim: int = 768):
        self.model_name = model_name
        self.dim = dim
        self._vocab = self._build_vocab()
        self._semantic_groups = self._build_semantic_groups()
    
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
    
    def encode(self, texts: List[str]) -> List[List[float]]:
        if isinstance(texts, str):
            texts = [texts]
        
        embeddings = []
        for text in texts:
            emb = self._semantic_embedding(text)
            embeddings.append(emb)
        
        return embeddings
    
    def _semantic_embedding(self, text: str) -> List[float]:
        """Generate semantic-aware embedding."""
        embedding = [0.0] * self.dim
        
        # Extract tokens
        tokens = re.findall(r"\b\w+\b", text.lower())
        
        # Weight by token importance and semantic groups
        for token in tokens:
            # Check if token is in vocabulary
            if token in self._vocab:
                idx = self._vocab[token] % self.dim
                embedding[idx] += 2.0  # Higher weight for known keywords
            
            # Check semantic groups
            for group_name, group_tokens in self._semantic_groups.items():
                if token in group_tokens:
                    # Add group-specific semantic signal
                    group_idx = int(hashlib.md5(group_name.encode()).hexdigest(), 16) % self.dim
                    embedding[group_idx] += 1.5
            
            # Hash unknown tokens with lower weight
            hash_val = int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dim
            embedding[hash_val] += 0.3
        
        # Add n-gram features for better context understanding
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]}_{tokens[i+1]}"
            hash_val = int(hashlib.md5(bigram.encode()).hexdigest(), 16) % self.dim
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
        
        return self._semantic_embedding(text)
