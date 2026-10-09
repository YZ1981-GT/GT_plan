# B 类共享基类载体通道 — 设计

## 定位

本 spec 是 B 循环三份 sync spec 的 **lane 2**，承担共享基类 `useWorkpaperEntryDualMode.ts` 上的 **4** 条 entry（canary 那条在 foundation）。

共同判据一律引用 `b-cycle-sync-foundation-and-first-canary` 的 **BC-1 ~ BC-60**，本文件不重复裁决，只写本组特有的落地设计。

## 一、本组 4 条 entry 的事实矩阵

| 项 | `gt-b22-b-control-matrix` | `gt-b22-b-deficiency-evaluation` | `gt-b22-c-design-effectiveness` | `gt-b50-risk-assessment` |
|---|---|---|---|---|
| 宿主行数 | 531 | 1148 | 685 | **2772** |
| 载体挂点 | `#L29` | `#L32` | `#L24` | `#L30` |
| `group_id` | GRP-04 | GRP-04 | GRP-04 | **GRP-05** |
| sheet 名表达式 | `props.wpCode \|\| 'B22B'` | `props.wpCode \|\| 'B22B'` | `props.wpCode \|\| 'B22C'` | `ooSheetName` |
| mode 值 | `'onlyoffice'` | `'onlyoffice'` | `'onlyoffice'` | `'onlyoffice'` ×2 |
| 门控假阴 | 否 | 否 | 否 | **是** |
| `checklist` 通道深度 | D1（`useB22BControlMatrix.ts`） | **D0（宿主内直调）** | **D0（宿主内直调）** | D1（`useB50FormData.ts`） |
| `idx` 形参 | — | **有** | **有** | **有** |
| `count` 键 | — | — | **有** | **有** |
| `removeRow` | **有** | — | — | — |
| 熵键 | — | **有** | — | — |
| label 作 key | — | — | — | **4 处** |
| 真库载荷 | 13 行（与 deficiency 共用 `B22B`） | （同上，无法拆分） | **23 行 / remark 7 / concl 1** | **0 行** |

## 二、共享基类改线设计（需求 1）

### 2.1 边归属现状

`useWorkpaperEntryDualMode.ts` 共 **26** 条生产边，B 域占 **5**（本组 4 + canary 1），其余 **21** 条属其他循环。

⇒ 改线不可改变默认行为。设计为**新增可选参数 + 缺省退回旧路径**：未传新参数时走改线前逻辑，传入时走权威源解析。

### 2.2 与 `useWpDualMode` 的对比（为什么本组不成孤儿）

| 载体 | B 域边 | 全域边 | 改线后 |
|---|---|---|---|
| `useWpDualMode.ts` | 3 | 3 | 🔴 成孤儿（全 slice 唯一），须连带删除 |
| `useWorkpaperEntryDualMode.ts` | 5 | **26** | 不成孤儿，须保兼容 |

这是两份 lane spec 分开的根本原因（BC-58）。

## 三、`B22B` 一码双 entry 消歧设计（需求 2）

### 3.1 现状

两条 entry 共用 pattern `B22B`，但：

- `xlsx/gt-b22-b-control-matrix` 的 `wp_codes_via_component_type` = `['B22B']`
- `xlsx/gt-b22-b-deficiency-evaluation` 的 `wp_code_count_via_component_type` = **0**（override 表零命中）

两者是不同 componentType + 不同宿主文件。这是 A 域 BP-11（单宿主多 componentType）的**对偶形态**（BC-45）。

### 3.2 消歧方案

以 componentType 为归属主键，wp_code 仅作模板定位线索：

1. 解析权威册时用 componentType → 显式册映射，不走 `props.wpCode || 'B22B'` 的 fallback
2. `xlsx/gt-b22-b-deficiency-evaluation` 因 override 零命中，须在映射表补一条显式项
3. `item_id` 命名空间已天然分离（真库实测 `B22B-row-{n}-{field}` 只属控制矩阵一侧），但 deficiency 侧的命名轴须在改线时确认并登记

### 3.3 真库分母的归属限制

真库 `B22B` 13 行全部是 `B22B-row-0-{12 个字段}` + `B22B-row-count`，均属控制矩阵形态 ⇒ **deficiency 侧真库载荷为 0**。改线验证须造人工数据，并声明该前提（同 `gt-b50-risk-assessment`，见 §五）。

## 四、行键与 `count` 键设计（需求 3）

### 4.1 违规形态现状（BC-53 / BC-54 / BC-56）

| 形态 | 位置 | 基准 |
|---|---|---|
| `B22B-row-{n}-{field}` | 真库，12 字段/行 | **0-based** |
| `B22C-env-def-{n}-{field}` | 真库，4 字段 | **1-based** |
| `idx` 形参索引 JSON 数组 | 3 个宿主（deficiency / b22c / b50） | 数组下标 |
| `:key` 绑定 `row.name` / `grp.label` | `GtB50RiskAssessment.vue` 4 处 | 文本 |

### 4.2 迁移设计

行键改为稳定 `id`（参照 B60 pilot 已落地的 `rowUuid: "GTROW-B601-0007"` 形态）：

1. 新行生成时携带稳定 id，不复用数组下标
2. 存量数据迁移：`row-{n}` / `env-def-{n}` 按当前顺序一次性映射到新 id，**两种基准分别处理**（0-based 与 1-based 不可统一假设）
3. `count` 键保留但降级为校验值：读取时断言 `count` == 实际行键数，不一致则报错而非静默取小值
4. `:key` 改绑稳定 id，`row.name` / `grp.label` 仅作显示

### 4.3 熵键单点（`gt-b22-b-deficiency-evaluation`）

该宿主含 **1** 处熵键（`Date.now()` / `Math.random()` / `crypto.randomUUID` 之一）。熵键在渲染 key 上会导致每次渲染 DOM 重建，在持久化键上会导致数据无法二次定位 ⇒ 改线时须确认其用途并替换为稳定 id。

## 五、`GRP-05` 与零分母处理（需求 4）

### 5.1 `gt-b50-risk-assessment` 的三重特殊

1. **唯一 `GRP-05`**（其余 9 条 B 域 entry 全 `GRP-04`），差异在多一条 `field_overrides` 通道
2. **前端 import 闭包深度 3 内 `field-overrides` 命中为 0** ⇒ 该通道不在前端闭包内，须实测确认走后端或已废弃（不可推演）
3. **真库载荷 0 行** ⇒ 改线验证无真实数据可依

### 5.2 零分母验证设计

对 `gt-b50-risk-assessment` 与 `gt-b22-b-deficiency-evaluation` 两条零分母 entry：

1. 造人工最小数据集（至少 2 行，以暴露行键错位）
2. 显式在测试中声明「本 entry 真库分母为 0，以下验证基于人造数据」
3. 🔴 不得因分母为 0 而跳过验证 —— 这正是 BC-20 空分母纪律要求的变异证明

### 5.3 `gt-b50-risk-assessment` 的规模风险

宿主 **2772** 行（全 B 域最大），含门控假阴、`idx` 形参、`count` 键、label 作 key、`GRP-05` 五项缺陷 ⇒ 建议本组按「先 b22 三条、后 b50」顺序推进，b50 的改线经验依赖前三条。

## 六、Property 清单（BG-P1 ~ BG-P18）

| Property | 命题 | 现算值 | 判据 |
|---|---|---|---|
| BG-P1 | 本组 4 条全挂 `useWorkpaperEntryDualMode.ts` | 4 | BC-2 |
| BG-P2 | 该载体全域边 26，B 域 5（本组 4 + canary 1） | 26 / 5 | BC-58 |
| BG-P3 | `becomes_orphan_after_rewire` 为假（与 `useWpDualMode` 相反） | False | BC-58 |
| BG-P4 | 4 条挂点行号 `#L29` / `#L32` / `#L24` / `#L30` | 4 | BC-2 |
| BG-P5 | `B22B` 被 2 条 entry 共用（不同 componentType + 不同宿主） | 2 | BC-45 |
| BG-P6 | `gt-b22-b-deficiency-evaluation` 的 override 命中为 0 | 0 | BC-45 |
| BG-P7 | 4 条 mode 值全 `'onlyoffice'`，b50 出现 2 次 | 4 / 2 | BC-41 |
| BG-P8 | 4 条均未在宿主内声明 `modeOptions` | 0/4 | BC-41 |
| BG-P9 | `checklist` 通道深度：D0 两条 + D1 两条 | 2 / 2 | BC-42 |
| BG-P10 | b50 的 localStorage 在 D1（全 B 域最浅） | D1 | BC-42 |
| BG-P11 | 门控假阴本组 1 条（b50） | 1 | BC-13 |
| BG-P12 | `idx` 形参出现在本组 3 个宿主 | 3 | BC-53 |
| BG-P13 | label 作 key 4 处全在 `GtB50RiskAssessment.vue` | 4 | BC-48 |
| BG-P14 | 熵键 1 处在 `gt-b22-b-deficiency-evaluation` | 1 | BC-53 |
| BG-P15 | 两种位置化编号基准并存：`row-0`（0-based）与 `env-def-1`（1-based） | 2 | BC-56 |
| BG-P16 | `count` 键本组两种：`B22B-row-count` / `B22C-env-def-count` | 2 | BC-54 |
| BG-P17 | `gt-b22-c-design-effectiveness` 是全 B 域唯一 conclusion 非空的 entry | 1 | BC-34 |
| BG-P18 | `gt-b50-risk-assessment` 真库 0 行 ⇒ 验证须人造数据并声明前提 | 0 | BC-60 |

**编号完整性**：BG-P1 ~ BG-P18 连续 **18** 条，无缺号无重号。

## 七、守卫测试类映射

| 测试类 | Property |
|---|---|
| `TestSharedBaseCompatibility` | BG-P1 ~ BG-P4 |
| `TestB22BDualEntryDisambiguation` | BG-P5 ~ BG-P6 |
| `TestModeAndPersistenceChannels` | BG-P7 ~ BG-P11 |
| `TestRowIdentityAndCountKeys` | BG-P12 ~ BG-P16 |
| `TestPayloadDenominators` | BG-P17 ~ BG-P18 |
