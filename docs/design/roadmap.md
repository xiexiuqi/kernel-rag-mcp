# 里程碑规划

> 本文档描述 Kernel-RAG-MCP 的分阶段开发计划。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## Phase 1：单系统 MVP（4 周）

- [ ] 项目仓库结构搭建（`src/`、`tests/`、`docs/`）
- [ ] 支持 `kernel/sched/` 单个子系统的完整索引与检索
- [ ] CLI：`kernel-rag init`、`kernel-rag index --base ~/linux`
- [ ] 索引存放：`~/.kernel-rag/repos/linux/v6.12/base/` 基础结构
- [ ] MCP Server：暴露 `kernel_search` 和 `kernel_define`
- [ ] 接入 Claude Code，验证端到端体验

---

## Phase 2：完整内核 + Kconfig 感知 + 大版本粒度（4 周）

- [ ] 支持完整内核索引（`kernel-rag index --base ~/linux`）
- [ ] 大版本命名空间：`v6.12/base/`、`v6.13/base/`
- [ ] 增量 delta 结构：`delta-v6.12.1/`、`delta-v6.12.2`
- [ ] 手动合并命令：`kernel-rag merge v6.12 --target v6.12.5`
- [ ] 集成 **kconfiglib** 解析 Kconfig 符号属性
- [ ] 集成 **kclause** 生成 Z3 公式，支持 Kconfig 可满足性查询
- [ ] 集成 **Git 历史索引**（commit 卡片 + diff 上下文）
- [ ] Git 范围构建：`--range v6.12..v6.18`
- [ ] 增量更新（`kernel-rag update`）
- [ ] 接入 Cursor / OpenCode MCP

---

## Phase 3：Patch 类型 + 变更因果图谱 + Rust-for-Linux（4 周）

- [ ] 集成 **Patch 类型分类器**（性能/bugfix/重构/特性/回归）
- [ ] 暴露 `git_search_by_type`、`git_type_stats` 工具
- [ ] 集成 **Git 标签解析器**（Fixes:/Introduced-by:/Cc: stable 等）
- [ ] 构建 **变更因果图谱**（Change Causal Graph）
- [ ] 暴露 `git_causal_chain`、`git_bug_origin`、`git_backport_status` 工具
- [ ] 集成 **KconfigDetector** 风险标注
- [ ] 集成 **kmax** 建立配置-源文件映射
- [ ] 集成 **Git blame 行级溯源**
- [ ] Rust-for-Linux 模块解析与索引（`rust/` 目录）
- [ ] 子系统规则模板社区贡献机制
- [ ] 预生成基线索引分发（LTS 版本）

---

## Phase 4：CI 与生态集成（持续）

- [ ] 版本差异对比（`kernel_diff`）
- [ ] Kconfig 依赖推理（"开启 X 需要哪些前置配置"）
- [ ] CI/CD 集成（自动索引 PR 变更）
- [ ] 性能优化（更快的增量更新、更低的查询延迟）
- [ ] 变更因果图谱可视化（Web 预览）
- [ ] 团队索引导出/导入（`kernel-rag export/import`）
