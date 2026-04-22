# Kconfig 索引测试设计

> 本文档描述 Kconfig 解析、形式化建模和索引的测试策略和用例设计。
> 版本：v0.1.0-draft | 最后更新：2026-04-22

---

## 1. 测试范围

- Kconfig 解析（kconfiglib）
- 形式化建模（kextract → kclause → Z3）
- 可满足性验证
- 配置-源文件映射（kmax）

---

## 2. Kconfig 解析测试

### 2.1 符号类型测试

| 测试用例 | 输入 | 预期输出 |
|----------|------|----------|
| bool 类型 | `config SMP bool` | type=bool |
| tristate 类型 | `config MODULES tristate` | type=tristate |
| string 类型 | `config LOCALVERSION string` | type=string |
| hex 类型 | `config PHYSICAL_START hex` | type=hex |
| int 类型 | `config LOG_BUF_SHIFT int` | type=int |

### 2.2 依赖表达式测试

| 测试用例 | 输入 | 预期输出 |
|----------|------|----------|
| 简单依赖 | `depends on X86` | deps=[X86] |
| 否定依赖 | `depends on !UML` | deps=[!UML] |
| 组合依赖 | `depends on X86 && SMP` | deps=[X86, SMP] |
| 或依赖 | `depends on X86 || ARM` | deps=[X86 || ARM] |
| 嵌套依赖 | `depends on (X86 && SMP) || ARM` | 正确解析嵌套 |

### 2.3 select/imply 测试

| 测试用例 | 输入 | 预期输出 |
|----------|------|----------|
| select | `select IRQ_DOMAIN` | selects=[IRQ_DOMAIN] |
| 条件 select | `select X86_LOCAL_APIC if X86` | conditional_selects=[(X86_LOCAL_APIC, X86)] |
| imply | `imply SMP` | implies=[SMP] |

### 2.4 菜单树测试

| 测试用例 | 输入 | 预期输出 |
|----------|------|----------|
| menu | `menu "Processor type and features"` | 菜单节点 |
| choice | `choice` ... `endchoice` | 选择节点 |
| if | `if X86` ... `endif` | 条件节点 |
| 嵌套结构 | menu → if → choice | 层级正确 |

---

## 3. 形式化建模测试

### 3.1 kextract 测试

| 测试用例 | 输入 | 预期输出 |
|----------|------|----------|
| 简单配置 | `config SMP bool default y` | 去糖化后的约束 |
| 依赖配置 | `config NUMA depends on SMP` | 包含依赖约束 |
| 选择结构 | `choice` ... `endchoice` | 互斥约束 |

### 3.2 kclause 测试

| 测试用例 | 输入 | 预期输出 |
|----------|------|----------|
| DIMACS 生成 | 去糖化后的 Kconfig | 有效的 DIMACS 格式 |
| Z3 公式生成 | 去糖化后的 Kconfig | 有效的 Z3 Python 公式 |
| 公式等价性 | 同一 Kconfig 两次生成 | 公式逻辑等价 |

---

## 4. 可满足性验证测试

### 4.1 SAT 测试（可满足）

| 配置组合 | 预期结果 |
|----------|----------|
| `CONFIG_SMP=y` | SAT |
| `CONFIG_SMP=y ∧ CONFIG_NUMA=y` | SAT（如果 NUMA 依赖 SMP） |
| `CONFIG_X86=y ∧ CONFIG_ARM=n` | SAT |

### 4.2 UNSAT 测试（不可满足）

| 配置组合 | 预期结果 |
|----------|----------|
| `CONFIG_SMP=y ∧ CONFIG_SMP=n` | UNSAT |
| `CONFIG_NUMA=y ∧ CONFIG_SMP=n` | UNSAT（如果 NUMA 依赖 SMP） |
| `CONFIG_X86=y ∧ CONFIG_ARM=y` | UNSAT（互斥架构） |

### 4.3 依赖闭包测试

| 查询 | 预期输出 |
|------|----------|
| `CONFIG_NUMA` 的依赖闭包 | [SMP, X86_64, ...] |
| `CONFIG_SCHED_MC` 的依赖闭包 | [SMP, ...] |
| 反向依赖 | 哪些配置 select/imply 了 SMP |

---

## 5. kmax 配置-源文件映射测试

| 测试用例 | 输入 | 预期输出 |
|----------|------|----------|
| obj-y 映射 | `obj-y += sched.o` | CONFIG 无关，总是编译 |
| obj-$(CONFIG_SMP) | `obj-$(CONFIG_SMP) += smp.o` | SMP=y 时编译 smp.o |
| 多配置映射 | `obj-$(CONFIG_X86) += x86/` | X86=y 时编译 x86/ 下所有文件 |
| ccflags-y | `ccflags-y += -DCONFIG_DEBUG` | 编译标志映射 |

---

## 6. 集成测试

| 测试用例 | 场景 | 验证点 |
|----------|------|--------|
| 完整 Kconfig 解析 | Linux 顶层 Kconfig | 所有符号被解析 |
| 形式化验证 | 生成 Z3 公式 | 公式可被 Z3 求解 |
| 配置组合验证 | 100 个随机组合 | 所有组合结果正确 |
| 源文件映射 | 分析 Kbuild Makefile | 映射关系正确 |

---

## 7. 性能测试

| 测试用例 | 目标 |
|----------|------|
| Kconfig 解析速度 | ≤ 10 秒（完整内核） |
| 形式化公式生成 | ≤ 30 秒 |
| Z3 求解延迟 | ≤ 100ms/查询 |
| 配置-源文件映射 | ≤ 5 分钟 |
