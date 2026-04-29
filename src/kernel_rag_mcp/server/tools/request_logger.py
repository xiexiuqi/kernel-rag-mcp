import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

class RequestLogger:
    """请求日志记录器
    
    记录所有 MCP 工具调用的请求和响应，用于后续分析：
    - 查询频率统计
    - 响应时间分析
    - 错误率统计
    - 用户行为分析
    """
    
    def __init__(self, log_dir: Optional[Path] = None):
        if log_dir is None:
            log_dir = Path.home() / ".kernel-rag" / "logs"
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 按日期分文件
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.log_file = self.log_dir / f"requests_{self.current_date}.jsonl"
    
    def log(self, tool_name: str, arguments: Dict[str, Any], 
            response: Dict[str, Any], duration_ms: float,
            client_info: str = ""):
        """记录一次工具调用
        
        Args:
            tool_name: 工具名（如 kernel_search, git_changelog）
            arguments: 请求参数
            response: 响应结果
            duration_ms: 处理耗时（毫秒）
            client_info: 客户端信息
        """
        # 检查是否需要切换日志文件（跨天时）
        current_date = datetime.now().strftime("%Y-%m-%d")
        if current_date != self.current_date:
            self.current_date = current_date
            self.log_file = self.log_dir / f"requests_{self.current_date}.jsonl"
        
        # 提取关键信息用于分析
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "arguments": arguments,
            "response_summary": self._summarize_response(response),
            "duration_ms": round(duration_ms, 2),
            "client": client_info,
            "success": response.get("found", True) if isinstance(response, dict) else True
        }
        
        # 追加写入 JSON Lines 格式
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def _summarize_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """提取响应摘要（不存完整代码，避免日志过大）"""
        summary = {}
        
        if isinstance(response, dict):
            # 通用字段
            if "found" in response:
                summary["found"] = response["found"]
            if "total" in response:
                summary["total"] = response["total"]
            if "version" in response:
                summary["version"] = response["version"]
            
            # 错误信息
            if "error" in response:
                summary["error"] = response["error"]
            
            # 结果摘要（只存文件路径和行号，不存代码）
            if "results" in response and isinstance(response["results"], list):
                summary["result_count"] = len(response["results"])
                summary["files"] = [
                    f"{r.get('file_path')}:{r.get('line')}"
                    for r in response["results"][:5]  # 只记前5个
                    if isinstance(r, dict)
                ]
            
            # 提交记录摘要
            if "commits" in response and isinstance(response["commits"], list):
                summary["commit_count"] = len(response["commits"])
            
            # 变更日志摘要
            if "entries" in response and isinstance(response["entries"], list):
                summary["entry_count"] = len(response["entries"])
        
        return summary
    
    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """获取最近 N 天的统计信息"""
        stats = {
            "total_requests": 0,
            "tool_usage": {},
            "avg_duration_ms": 0,
            "error_rate": 0,
            "top_queries": []
        }
        
        total_duration = 0
        error_count = 0
        query_counter = {}
        
        # 读取最近 N 天的日志
        for i in range(days):
            date_str = (datetime.now() - __import__('datetime').timedelta(days=i)).strftime("%Y-%m-%d")
            log_file = self.log_dir / f"requests_{date_str}.jsonl"
            
            if not log_file.exists():
                continue
            
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        stats["total_requests"] += 1
                        
                        # 工具使用统计
                        tool = entry.get("tool", "unknown")
                        stats["tool_usage"][tool] = stats["tool_usage"].get(tool, 0) + 1
                        
                        # 耗时统计
                        total_duration += entry.get("duration_ms", 0)
                        
                        # 错误统计
                        if not entry.get("success", True):
                            error_count += 1
                        
                        # 查询统计
                        args = entry.get("arguments", {})
                        if "query" in args:
                            query = args["query"]
                            query_counter[query] = query_counter.get(query, 0) + 1
                        
                    except json.JSONDecodeError:
                        continue
        
        # 计算平均值
        if stats["total_requests"] > 0:
            stats["avg_duration_ms"] = round(total_duration / stats["total_requests"], 2)
            stats["error_rate"] = round(error_count / stats["total_requests"] * 100, 2)
        
        # Top 查询
        stats["top_queries"] = sorted(
            query_counter.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10]
        
        return stats


# 全局日志实例
_logger = None

def get_logger() -> RequestLogger:
    global _logger
    if _logger is None:
        _logger = RequestLogger()
    return _logger

def set_logger(logger: RequestLogger):
    global _logger
    _logger = logger
