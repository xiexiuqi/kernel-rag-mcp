# Kconfig 索引设计

> 本文档描述 Kconfig 解析、形式化建模和索引的设计。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 设计原则

Kconfig 不是简单的键值对，而是包含 `depends on`、`select`、`imply`、`choice`、`if` 等复杂语义的配置语言。本项目**不自行手写 Kconfig 解析器**，而是复用成熟工具链分层处理。

---

## 2. 分层工具链

| 层级 | 工具 | 作用 |
|------|------|------|
| **解析层** | **kconfiglib** | Python 原生解析 Kconfig 语法，提取符号属性（类型、默认值、依赖、help text）、生成菜单树结构 |
| **形式化层** | **kclause 系列**（kextract → kclause → Z3） | 将 Kconfig 编译为命题逻辑公式（DIMACS/Z3），精确求解配置组合的可满足性 |
| **验证层** | **Kismet** + **KconfigDetector** | 检测 unmet dependency bugs、反向依赖风险、配置值错误 |
| **关联层** | **kmax** | 分析 Kbuild Makefile，建立 `obj-$(CONFIG_X)` 与源文件的精确编译映射 |

**收益**：RAG 索引中的每个代码 chunk 都附带精确的 Kconfig 条件向量；查询时可用 Z3 验证 "CONFIG_SMP=y ∧ CONFIG_NUMA=n" 是否合法，并召回对应条件分支。

---

## 3. 解析层（kconfiglib）

- 读取内核顶层 `Kconfig` 及所有子目录 `Kconfig` 文件
- 提取每个 `config` 符号的属性：
  - 类型（bool/tristate/string/hex/int）
  - 默认值
  - `depends on`
  - `select`
  - `imply`
  - `help text`
- 生成菜单树结构，理解 `menu`、`choice`、`if` 的层级关系
- 读取 `.config` 文件，建立符号-值映射

---

## 4. 形式化层（kclause 系列）

- 调用 `kextract` 对内核 Kconfig 做去糖化（desugaring）
- 调用 `kclause` 生成 Z3 / DIMACS 逻辑公式
- 对每个代码 chunk 的 Kconfig 条件，计算其**可满足性**和**依赖闭包**

---

## 5. 验证层（KconfigDetector + Kismet）

- 导入 KconfigDetector 的 JSON 输出，标注高风险配置项（依赖未满足、反向依赖风险）
- 导入 Kismet 的 bug 模式库，在 RAG 中提示 "unmet dependency" 风险

---

## 6. 关联层（kmax）

- 分析 Kbuild Makefile 的 `obj-$(CONFIG_X)`、`ccflags-y` 等规则
- 建立 "配置项 ↔ 源文件集合" 的精确映射

---

## 7. MCP 工具

| Tool | 功能 | 触发场景 |
|------|------|----------|
| `kconfig_describe(config_name)` | 查询配置项的 help、类型、默认值 | "CONFIG_SMP 是什么" |
| `kconfig_deps(config_name)` | 查询直接和间接依赖 | "开启这个需要什么前置条件" |
| `kconfig_check(combo_dict)` | 验证配置组合的可满足性 | "A=y 且 B=n 是否合法" |
| `kconfig_impact(config_name)` | 查询修改某配置影响的源文件 | "关闭这个会少编译哪些文件" |

---

## 8. 数据一致性保证

| 检查点 | 机制 | 目的 |
|--------|------|------|
| **Kconfig 公式校验** | 每次索引后随机抽样 100 个配置组合，用 Z3 验证可满足性 | 确保形式化层无逻辑错误 |
