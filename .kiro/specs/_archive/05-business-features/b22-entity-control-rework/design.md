# Design Document

## Overview

本设计将 B22 三项结构性缺陷（B22B 职能错位 / 财务报告过程缺失 / IT 详细压平）落地为可执行的组件与后端改造，同时零回归保全 A9 缺陷函联动与既有数据。默认采用**方案 A（源对齐 + 迁移）**，并保留方案 B 回退路径。

前序快赢（双模式 / 版本链 / 复核 / 字号 / B22C 判断矩阵）已在 `GtB22AControlMatrix.vue`、`GtB22BDeficiencyEvaluation.vue`、`GtB22CDesignEffectiveness.vue`、`useB22CDesignEffectiveness.ts` 落地，本设计仅将其纳入回归。

## 架构决策

### 决策 1：B22B 职能——方案 A（默认）vs 方案 B

| 维度 | 方案 A（源对齐，推荐/默认） | 方案 B（现状保留） |
|------|------------------------------|--------------------|
| B22B 渲染 | 新建 `b22b-control-matrix` 控制矩阵专属组件 | 保持 `b22b-deficiency-evaluation` 不动 |
| 控制矩阵 | B22B 可编辑登记册（12 列） | B22A 只读登记册转为可编辑独立区 |
| 缺陷严重程度真源 | 收敛至 B22C（单一真源） | 保留 B22B 缺陷评价（与 B22C 职能重叠现状） |
| A9 联动 | A9_Deficiency_Loader repoint 至 B22C + 旧格式兼容 | A9 不变（继续读 B22B-def-*） |
| 源模板一致性 | ✅ 完全对齐 | ❌ 职能错位保留 |
| 改动量/风险 | 大（新组件 + 迁移 + A9 repoint） | 小（仅 B22A 编辑化） |

**默认方案 A**：符合"彻底解决不绕开"。方案 B 回退点：跳过 Requirement 3/4 的 A9 repoint，仅实现 Requirement 1.3 的 B22A 登记册可编辑化 + Requirement 2 列结构，B22B 组件保持不变。design/tasks 以方案 A 展开，若用户在实现前改选方案 B，则停用 W2/W3 波次的 A9 迁移任务。

### 决策 2：IT 边界（Requirement 6）

- **B22A 承载 IT 了解**（复杂度判断 / 系统清单 / IT 环境 4 维 / ITGC 分类了解 / SoD 矩阵了解）——属"了解与评价设计"。
- **C22（`c22-itgc-bundle`）承载 ITGC 测试**（设计有效性测试 + 运行有效性测试）——属控制测试。
- B22A IT 子区通过 `Cross_Ref_Chip` 指向 C22，不在 B22A 重复测试内容。

### 决策 3：渲染兜底（Requirement 8.3）

B22B_Matrix_Component 为纯前端自加载专属组件（无 RENDERER_DISPATCH）。参照 B19/B22A 已验证的坑：render-config 必须折叠为单 sheet 且 `html_data.cells` 清空，否则 GtGridSheet 网格兜底会 shadow 专属组件。若模板产 cells，需后端 render 策略返回结构化非-cells dict 或在 self-contained 集合内特殊处理。

## Architecture

```
                 ┌─────────────────────────────────────────┐
   B22A (了解)   │ GtB22AControlMatrix.vue                  │
   b22a-control  │  Tab1 控制环境 / Tab2 风险评估(+管理层凌驾)│
   -matrix       │  Tab3 信息与沟通(+财务报告过程 4子过程 NEW)│
                 │  Tab4 IT详细(结构化重建: 概要/系统清单/    │
                 │       环境4维/ITGC/SoD → Cross-ref C22)   │
                 │  Tab5 监督 / 汇总(只读控制矩阵总览)        │
                 └───────────┬─────────────────────────────┘
                             │ 控制点带入(仅填空)
                             ▼
   B22B (矩阵)   ┌─────────────────────────────────────────┐
   b22b-control  │ GtB22BControlMatrix.vue (NEW)            │
   -matrix (NEW) │  12列控制矩阵登记册 + xlsx导出          │
                 └───────────┬─────────────────────────────┘
                             │ 识别缺陷
                             ▼
   B22C (评价)   ┌─────────────────────────────────────────┐
   b22c-design   │ GtB22CDesignEffectiveness.vue           │
   -effectiveness│  缺陷严重程度单一真源 + 判断矩阵         │
                 └───────────┬─────────────────────────────┘
                             │ 缺陷 + 严重程度
              ┌──────────────┴───────────────┐
              ▼                              ▼
   A9-1/A9-2 缺陷沟通函              B50 控制风险 / C 类控制测试
   (_load_b22b_deficiencies         (EventBus)
    → repoint 读 B22C)
```

## Components and Interfaces

### 1. B22B 控制矩阵专属组件（新建，方案 A）

- 前端 `GtB22BControlMatrix.vue` + `useB22BControlMatrix.ts`：12 列可编辑表（枚举列下拉）+ 增删行 + 从 B22A 带入 + 客户端 xlsx 导出（复用 B22A `exportControlMatrix` 的列定义）。
- 持久化：`checklist_responses`，item_id 前缀 `B22B-row-{n}-{field}` + `B22B-row-count`（与旧 `B22B-def-*` 键空间不冲突，便于共存与迁移）。
- 组件复用：字号 13px、版本链、复核入口、双模式工具栏（沿用快赢范式）。
- 现 `GtB22BDeficiencyEvaluation.vue` 的缺陷评价能力在方案 A 下迁移到 B22C（见第 3 节），组件本身在切换 componentType 后不再被 wp_code B22B 路由；保留文件供兼容期读取/迁移。

### 2. B22A 财务报告过程 + IT 详细结构化

- `GtB22AControlMatrix.vue` Tab3（信息与沟通）新增 Financial_Reporting_Process 记录区（4 子过程 × [不适用勾选 + 了解文本]），item_id 前缀 `B22A-frp-`。
- Tab4 IT 区由 `useB22AControlMatrix.ts` 的 6 通用 subPanel 重建为结构化子区（IT 概要 / 系统清单 / IT 环境 4 维 / ITGC / SoD）。旧 `B22A-T4-IT-*` 数据经迁移映射函数落入新槽位或标注待复核。
- 保留管理层凌驾专区与既有业务规则告警（IT 依赖高 + ITGC 无效）。

### 3. 缺陷严重程度收敛至 B22C

- `useB22CDesignEffectiveness.ts` 扩展缺陷条目携带严重程度（重大/重要/一般）字段，并派生 CAS 1152 两级映射；`loadFromUpstream` 除 B22A 外，兼容读取旧 `B22B-def-*` 迁移进 B22C。
- B22C 成为 A9 缺陷读取真源。

### 4. A9 缺陷 Loader repoint（Requirement 4）

- `_a91_deficiency_letter.py::_load_b22b_deficiencies` 改造：优先从 B22C（`B22C-*` 缺陷 + 严重程度）读取并分组；保留对 `B22B-def-*` / `b22b-deficiency-*` 旧格式的向后兼容分支（迁移完成前双读、去重）。
- 分组等价性由 PBT 保证（同批数据重做前后 major/significant/general 分组一致）。

### 5. 数据迁移

- 一次性幂等迁移：`B22B-def-*`（缺陷 + 严重程度）→ B22C 缺陷结构；旧 B22B 控制矩阵（此前藏于 B22A `controlMatrixRegister` 只读导出，本身无独立持久化）无需迁移，改由 B22A 控制点带入 B22B。
- 迁移标注 `migratedFrom` 元数据，重复执行不产生重复行。

## Data Models

### Control_Point（B22B 控制矩阵行，12 列）

| 字段 | 类型 | 说明 |
|------|------|------|
| element | enum | 要素（控制环境/风险评估/信息与沟通/监督/IT） |
| subCategory | string | 子类别 |
| code | string | 编号（客户控制编号） |
| controlName | string | 控制名称 |
| description | text | 详细控制描述 |
| antiFraud | enum(是/否) | 是否为反舞弊控制 |
| frequency | enum | 控制频率 |
| performer | string | 执行人 |
| competence | text | 执行人知识/经验/技能 |
| relatedRisk | enum | 与控制相关的风险 |
| nature | enum(自动/人工) | 自动/人工 |
| itApp | string | IT应用名称 |

- 持久化：`B22B-row-{n}-{field}` + `B22B-row-count`（与旧 `B22B-def-*` 键空间隔离）。

### Financial_Reporting_Process（B22A-4-5，4 子过程）

- `subProcess ∈ {结账过程, 合并过程, 集团层面控制, 编制过程}`，每项含 `notApplicable: bool` + `understanding: text`。
- 持久化：`B22A-frp-{subProcess}-na` / `B22A-frp-{subProcess}-note`。

### IT_Understanding（B22A-4-1~4-4-2，结构化）

- 子结构：`itSummary`(复杂度 高/中/低) / `systemInventory`(行) / `itEnv`(应用·基础设施·流程·信息处理 4 维) / `itgc`(安全维护·作业调度接口) / `sodMatrix`(角色×职责)。
- 迁移：旧 `B22A-T4-IT-{sub}-*` → 新槽位映射函数，未匹配标注 `needsReview`。

### B22C 缺陷（严重程度收敛真源）

- 缺陷条目扩 `severity ∈ {重大缺陷, 重要缺陷, 一般缺陷}`；派生 CAS1152 两级 `{值得关注, 一般}`；A9 分组映射 `重大→major / 重要→significant / 一般→general`。

## Correctness Properties

### Property 1: 渲染一致性
wp_code B22B 恒渲染 `b22b-control-matrix`；render-config 单 sheet + 空 cells，不被 grid 兜底 shadow。

**Validates: Requirements 1.1, 8.3**

### Property 2: 12 列完整
控制矩阵导出/持久化列集合恒等于源模板 12 列，顺序稳定。

**Validates: Requirements 2.1, 2.4**

### Property 3: 带入仅填空
从 B22A 带入控制点时，已编辑行不被覆盖；重复带入不产生重复行。

**Validates: Requirements 1.4**

### Property 4: 缺陷单一真源
任一缺陷严重程度在 B22C 有且仅有一处权威值。

**Validates: Requirements 3.1**

### Property 5: A9 分组等价
对同一批缺陷数据，重做后 A9 分组结果与重做前（读 B22B-def-*）等价。

**Validates: Requirements 4.3**

### Property 6: A9 向后兼容
当仅存在旧 `B22B-def-*` 数据（未迁移）时，A9 仍能正确分组。

**Validates: Requirements 4.2**

### Property 7: 迁移幂等
迁移执行 N 次与执行 1 次结果一致，无重复、无漂移。

**Validates: Requirements 10.2**

### Property 8: FRP 不适用可空
财务报告过程子过程标记不适用时了解文本可空且不计入完成度缺口。

**Validates: Requirements 5.4**

### Property 9: IT 迁移不丢失
旧 `B22A-T4-IT-*` 数据迁移后可回溯（映射或标注待复核），无静默丢弃。

**Validates: Requirements 6.3**

### Property 10: 只读封锁
只读/已复核态下全部编辑控件禁用，setter 短路不调 PUT。

**Validates: Requirements 11.1**

### Property 11: 事件有消费者
B22 发布的每个 EventBus 事件至少一个已实现消费者（B50/C1/B23 之一）。

**Validates: Requirements 12.1**

### Property 12: 注册契约
`b22b-control-matrix` 满足 DEDICATED⊆VALID∩FE、WHOLE−DISPATCH⊆WHITELIST∪CONFIRMATION 等注册契约。

**Validates: Requirements 8.2**

### Property 13: 管理层凌驾归属
管理层凌驾缺陷归风险评估区而非 ITGC，不因 `-IT-` 前缀误判。

**Validates: Requirements 7.1**

## 需求 → 属性映射

| Requirement | Properties |
|-------------|-----------|
| 1 | P1, P3 |
| 2 | P2 |
| 3 | P4 |
| 4 | P5, P6 |
| 5 | P8 |
| 6 | P9, P13 |
| 7 | P11, P13 |
| 8 | P1, P12 |
| 9 | （回归：快赢 vitest + Vite transform 200） |
| 10 | P6, P7, P9 |
| 11 | P10 |
| 12 | P11 |

## Error Handling

- render-config / checklist-responses 请求失败 → 组件降级为可手工填写，ElMessage 警告，不阻断。
- OnlyOffice 健康检查失败 → OO 选项禁用（已落地），@fallback 回退 HTML。
- 迁移失败 → 记录 warning，保留原始数据，不删除。
- A9 读取 B22C 失败 → 回退旧 `B22B-def-*` 分支（双读兼容期）。

## Testing Strategy

- 后端 PBT：P5/P6/P7 在 `test_a91_deficiency_letter.py` 扩展 + 新建迁移契约测试。
- 前端 vitest：P2/P3/P4/P8/P9/P10/P13 在新建 `useB22BControlMatrix.spec.ts` / 扩展 `useB22CDesignEffectiveness` 测试。
- 契约测试：P1/P12 在 `test_dedicated_component_registry_contract.py` + 前端 registry 契约。
- Vite transform 200（崩溃类权威）+ get_diagnostics 全清。
- Playwright：B22 实例化后 round-trip（B22B 矩阵录入落库 / B22C 缺陷带入 / A9 分组反映）。
