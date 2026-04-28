#!/usr/bin/env python3
"""
Kernel-RAG-MCP HTTP Server (SSE mode)
用于远程客户端（如 Cherry Studio、Claude Desktop 等）连接

启动方式：
  # 本地访问（默认）
  python mcp_server_http.py
  
  # 远程访问（监听所有网络接口）
  MCP_HOST=0.0.0.0 MCP_PORT=8000 python mcp_server_http.py
"""
import os
import sys
from pathlib import Path

# 确保模块路径正确
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kernel_rag_mcp.server.mcp_server_internal import mcp
from mcp.server.transport_security import TransportSecuritySettings

# 禁用 DNS 重绑定保护，允许通过 IP 地址访问
mcp.settings.transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=False
)

if __name__ == "__main__":
    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "8000"))
    
    print(f"Starting Kernel-RAG-MCP SSE server on http://{host}:{port}")
    print(f"SSE endpoint: http://{host}:{port}/sse")
    print(f"Health check: http://{host}:{port}/health")
    
    if host == "127.0.0.1":
        print("\nNote: Only accessible from localhost.")
        print("For remote access, set MCP_HOST=0.0.0.0")
    else:
        print("\nWarning: DNS rebinding protection disabled. Only use in trusted networks.")
    
    import uvicorn
    uvicorn.run(mcp.sse_app(), host=host, port=port, loop="asyncio")
