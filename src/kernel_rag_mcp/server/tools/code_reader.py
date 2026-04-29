import subprocess
from pathlib import Path
from typing import Optional

class CodeReader:
    """代码读取器 - 支持多版本读取
    
    设计原则（符合文档 3.2 指针式索引）：
    - 索引不存储代码原文
    - 查询时通过 Git 现场读取特定版本
    - 支持 git show <version>:<file> 读取历史版本
    """
    
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
    
    def read_code(self, file_path: str, start_line: int, end_line: int, 
                  version: Optional[str] = None) -> str:
        """读取代码片段
        
        Args:
            file_path: 文件路径（如 kernel/sched/core.c）
            start_line: 起始行号（1-based）
            end_line: 结束行号（1-based）
            version: 版本标签（如 v6.19, v7.0），None 表示当前工作区
        
        Returns:
            代码片段字符串
        """
        try:
            if version:
                # 通过 Git 读取特定版本
                return self._read_from_git(file_path, start_line, end_line, version)
            else:
                # 读取当前工作区文件
                return self._read_from_disk(file_path, start_line, end_line)
        except Exception as e:
            return f"# Error reading code: {e}"
    
    def _read_from_disk(self, file_path: str, start_line: int, end_line: int) -> str:
        """从磁盘读取当前文件"""
        full_path = self.repo_path / file_path
        
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
            start_idx = max(0, start_line - 1)
            end_idx = min(len(lines), end_line)
            return ''.join(lines[start_idx:end_idx])
    
    def _read_from_git(self, file_path: str, start_line: int, end_line: int,
                       version: str) -> str:
        """通过 Git 读取特定版本的文件内容"""
        # 使用 git show 读取特定版本文件
        result = subprocess.run(
            ['git', '-C', str(self.repo_path), 'show', f'{version}:{file_path}'],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"git show failed: {result.stderr}")
        
        lines = result.stdout.split('\n')
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        return '\n'.join(lines[start_idx:end_idx])
    
    def read_function(self, file_path: str, func_name: str, 
                      version: Optional[str] = None) -> str:
        """读取完整函数 - 使用 tree-sitter 精确边界
        
        这比手动花括号计数更可靠。
        """
        from ...indexer.parsers.tree_sitter_c import TreeSitterCParser
        
        # 读取完整文件
        if version:
            code = self._read_from_git(file_path, 1, 100000, version)
        else:
            code = self._read_from_disk(file_path, 1, 100000)
        
        # 用 tree-sitter 解析找到函数边界
        parser = TreeSitterCParser()
        chunks = parser.parse_functions(code, file_path)
        
        for chunk in chunks:
            if chunk.name == func_name:
                return chunk.code
        
        return f"# Function '{func_name}' not found in {file_path}"


class VersionManager:
    """版本管理器 - 支持多版本索引切换"""
    
    def __init__(self, index_root: Path, repo_path: Path):
        self.index_root = index_root
        self.repo_path = repo_path
    
    def get_index_path(self, version: str) -> Path:
        """获取指定版本的索引路径"""
        # 版本命名空间：v7.0 -> v7.0/base/
        version_ns = self._get_version_ns(version)
        return self.index_root / version_ns / "base"
    
    def _get_version_ns(self, version: str) -> str:
        """获取版本命名空间"""
        if version.startswith("v"):
            parts = version.split(".")
            if len(parts) >= 2:
                major = parts[0][1:]  # "v7" -> "7"
                minor = parts[1].split("-")[0]  # "0-rc6" -> "0"
                return f"v{major}.{minor}"
        return version
    
    def list_available_versions(self) -> list:
        """列出可用的索引版本"""
        versions = []
        if self.index_root.exists():
            for item in self.index_root.iterdir():
                if item.is_dir() and (item / "base").exists():
                    versions.append(item.name)
        return sorted(versions)
    
    def detect_current_version(self) -> str:
        """检测当前 Git 仓库版本"""
        try:
            result = subprocess.run(
                ['git', '-C', str(self.repo_path), 'describe', '--tags', '--abbrev=0'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                tag = result.stdout.strip()
                return self._get_version_ns(tag)
        except Exception:
            pass
        return "v7.0"  # 默认回退
