# C22 ITGC 无开关与域码 sheet 名通道 — 需求

## 背景

本 spec 承担 C 循环 2 条 entry 中的 **1** 条：`xlsx/gt-c22-itgc-bundle`（IT 一般控制测试 bundle）。

共同判据由 `c-cycle-sync-foundation-and-first-canary` 一次性裁定为 **CC-1 ~ CC-68**，本 spec **只引用编号，不重复裁决**。

与 canary 那条（`xlsx/gt-c-control-test`）分开的理由：两条 entry 在 **14 个维度上逐项相反**，且本条背负 **BP-10**（`no_switch_at_all`），slice 明文 `must_fix_before` = 「任何 entry 从待裁决态改裁 bidirectional 之前」⇒ **必须先补模式开关**，与 canary 的 `redeemable` 路径性质不同。

## 范围

| 项 | 值 |
|---|---|
| entry_id | `xlsx/gt-c22-itgc-bundle` |
| 宿主 | `audit-platform/frontend/src/components/workpaper/GtC22ItgcBundle.vue`（922 行） |
| wp_code pattern | `C22I`（🔴 解析为 `None`） |
| 真实 wp_code | `C22`（1 个） |
| `component_type_family` | `c_class_bundle` |
| `group_id` | GRP-06 |
| `dual_mode_carrier.kind` | **`no_carrier`** |
| `switch_verdict` | **`no_switch_at_all`** |
| BP 数 | **8**（含 **BP-10**） |
| segmented / mode 门控 | **0 / 0** |
| `item_id` 命名轴 | **`C22.{controlId}.{field}`**（点号分隔） |
| 持久化通道深度 | **D0**（宿主内直调 `/checklist-responses`） |
| import 闭包 | **8** 册（全 C 域最小） |
| 真库行数 | **0** |
| 权威册 | `C22 IT一般控制测试.xlsx`（**34** sheets，其中 **33** 个是 ITGC 域码） |

## 本条 entry 的三项独有缺陷

1. **BP-10 无模式开关**（全 slice 仅 4 条之一）
2. **传入 sheet 名与册内 sheet 名零交集**（命中 **0 / 3**）
3. **OO 挂点加载的册不是本 entry 的册**（实际加载 `C21` / `C21-1`，均属排除册）

## 需求

### 需求 1：补模式开关（BP-10 前置硬约束）

**用户故事**：作为审计助理，我需要能在 C22 ITGC bundle 上选择结构化视图与在线编辑，而不是被系统静默决定。

#### 验收标准

1. WHEN 当前无任何模式开关 THEN 系统 SHALL 补入开关，且补开关 SHALL 在改裁 `bidirectional` 之前完成
2. WHEN 补开关前 THEN SHALL 先落地三条论证：`html_counterpart_verdict` 为 `exists` · 权威册可解析 · 册内 sheet 与公式格现算非空
3. WHEN 补开关 THEN SHALL 直接采用已有的正确形态（`{label, value}` 分离），禁引入中文标签直接作 mode 值的形态
4. WHEN 开关补完 THEN foundation 基线中「C 域 segmented 总数」与「mode 门控总数」SHALL 同步更新，且**同一 commit 内改两处**防漂移
5. IF 补开关后 OO 挂点条件变化 THEN 与 slice `ui_toolbar_gate` 的双向对账 SHALL 重新执行

### 需求 2：sheet 名解析改为真实 sheet 名

**用户故事**：作为审计助理，我切到在线编辑时应打开正确的工作表，而不是空白或错误的表。

#### 验收标准

1. WHEN 传入 sheet 名 THEN 系统 SHALL 传册内真实存在的 sheet 名，而非 wp_code
2. WHEN 现状传入 `C21` / `C21-1` / `C22` THEN 判据 SHALL 断言三者对册内 sheet 名命中为 **0 / 3**
3. WHEN 目标册是 `C22 IT一般控制测试.xlsx` THEN 解析 SHALL 能定位其 **34** 个 sheet 中的目标 sheet（主 sheet `C22 IT一般控制测试` 或 33 个 ITGC 域码之一）
4. WHEN sheet 名含空格或全角字符 THEN 匹配 SHALL 按原始字面量进行，禁归一化

### 需求 3：权威册归属错误被纠正

**用户故事**：作为改线工程师，我需要知道这条 entry 的 OO 挂点到底加载哪本册，才能正确接线。

#### 验收标准

1. WHEN `activeDocTab` 只匹配 `kind === 'c21' || kind === 'c21-1'` THEN 判据 SHALL 断言 OO 挂点**只在 C21 / C21-1 两个 tab 上渲染**
2. WHEN OO 挂点加载 C21 / C21-1 册 THEN 判据 SHALL 断言这两本册属 foundation 的**排除册清单**（7 本之一）
3. WHEN 本 entry 的权威册是 `C22 IT一般控制测试.xlsx` THEN 判据 SHALL 断言该册**从未被 OO 侧加载过**
4. IF 改线决定让 OO 侧加载 C22 册 THEN 须同时裁定 C21 / C21-1 两本册的归属（是否另立 entry）

### 需求 4：点号命名空间与共享边界

**用户故事**：作为维护者，我需要知道 C22 的 item_id 命名空间被哪些组件共用，避免改一处坏另一处。

#### 验收标准

1. WHEN 断言 `item_id` 构造 THEN SHALL 断言形态为 `C22.{controlId}.{field}`（**点号**分隔，与 canary 那条的连字符体系不同）
2. WHEN `GtC22ControlSheet.vue`（排除组件）也写 `/checklist-responses` THEN 判据 SHALL 断言两者**共用同一 `itgcItemId()` 与同一命名空间**，属有意共享而非冲突
3. WHEN 改动命名空间 THEN 两个组件 SHALL 同步改动
4. WHEN 真库该命名空间为 **0** 行 THEN 验证 SHALL 依赖人造数据并显式声明该前提
