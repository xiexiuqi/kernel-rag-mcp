import os
from typing import List, Optional


class SiliconFlowEmbedder:
    def __init__(self, api_key: Optional[str] = None, model: str = "BAAI/bge-m3"):
        self.api_key = api_key or os.environ.get("SILICONFLOW_API_KEY")
        if not self.api_key:
            from ...config import get_config
            cfg = get_config()
            self.api_key = cfg.siliconflow_api_key
        self.model = model
        self.model_name = model
        self.dim = 1024
        self.base_url = "https://api.siliconflow.cn/v1"
    
    def encode(self, texts: List[str]) -> List[List[float]]:
        import requests
        
        if isinstance(texts, str):
            texts = [texts]
        

        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "input": texts,
            "encoding_format": "float"
        }
        
        response = requests.post(
            f"{self.base_url}/embeddings",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        
        data = response.json()
        embeddings = [item["embedding"] for item in data["data"]]
        
        return embeddings
