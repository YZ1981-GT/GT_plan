# B 循环双向回写地基与首张 canary — 需求

## 背景

B 循环（控制了解与风险评估）在 `workpaper_sync_abcs_cycle_manifest_slice.json` 中占 **10 条** in-scope entry（A/B/C/S 四循环合用同一份 slice，A 轮已切出 A 域 20 条，本轮切出 B 域 10 条）。`xlsx/b60/*` 系列 pilot 已在 Task 40/57 交付，**不在本轮范围**。

这 10 条的共同现状（现算自 slice `independent_entries`，非推演）：

- `migration_state` 全部 `legacy_fake_bidirectional`（假双向）
- `capability` 全部 `null`，`capability_target` 全部 `bidirectional`
- `capability_target_blocked_by` **完全相同** = `[BP-1, BP-2, BP-3, BP-4, BP-5, BP-7, BP-8]` 共 **7** 项
- `dual_mode_carrier.switch_verdict` 全部 `redeemable`（无 inert、无 no_switch）
- `ui_toolbar_gate.mounts_ac14_notice` 与 `claims_bidirectional_in_template` 全部 `false`
- `resolution_kind` 全部 `runtime_sheet_name_expression`
- `template_ref.workbook` 全部 `null`，`workbook_format` 全部 `null`
- `mount_count` 全部 1，`component_type_family` 全部 `b_class_risk_and_control`
- `adapter_id` / `authority_model` / `instrumentation_candidate` / `scenario_profile_id` 全部 `null`
- `html_counterpart_verdict` 全部 `exists`

**本轮与 A 轮的根本差异**：A 域 20 条有 5 个 BP 区分项，可按 BP 切分；B 域 **区分项 BP 为 0**，10 条在 BP 维度完全同构 ⇒ A 轮的切分方法在 B 域失效，须改用**载体轴**切分（见 design.md 拆分裁决）。

## 范围

### 10 条 entry（全名，无重无漏）

| # | entry_id | wp_code pattern | 真实 wp_code（via component_type） | 载体 | group |
|---|---|---|---|---|---|
| 1 | `xlsx/gt-b1-evaluation` | `B1E` | `B1-3` / `业务评价表B1-3` | `useWpDualMode` | GRP-04 |
| 2 | `xlsx/gt-b1-kaa-check` | `B1K` | `' B1-5 KAA检查表-业务承接'` / `B1-5` | `useWpDualMode` | GRP-04 |
| 3 | `xlsx/gt-b1-risk-assessment` | `B1R` | `B1-1` / `B1-2` / `风险评估表-保持` / `风险评估表-承接` | `useWpDualMode` | GRP-04 |
| 4 | `xlsx/gt-b14-due-diligence-report` | `B14D` | `B1-4` | host_inline | GRP-04 |
| 5 | `xlsx/gt-b22-a-control-matrix` | `B22A` | `B22A` | 共享基类 | GRP-04 |
| 6 | `xlsx/gt-b22-b-control-matrix` | `B22B` | `B22B` | 共享基类 | GRP-04 |
| 7 | `xlsx/gt-b22-b-deficiency-evaluation` | `B22B`（共用） | （空，override 零命中） | 共享基类 | GRP-04 |
| 8 | `xlsx/gt-b22-c-design-effectiveness` | `B22C` | `B22C` | 共享基类 | GRP-04 |
| 9 | `xlsx/gt-b23-process-control` | `B23P` | `B23` | host_inline | GRP-04 |
| 10 | `xlsx/gt-b50-risk-assessment` | `B50R` | `B50` | 共享基类 | GRP-05 |

载体分布 3 + 5 + 2 = **10** ✓ · group 分布 9 + 1 = **10** ✓

### 本 spec 承担

1. 一次性裁定 **BC-1 ~ BC-60** 共同判据（以 A 轮 AC-1 ~ AC-48 为基准逐条重裁 + B 域新增 12 条）
2. 锁定 10 条 entry 的事实基线（BP 归属 / 载体 / 解析路径 / 真库分母）
3. 落地首张 canary：**`xlsx/gt-b22-a-control-matrix`**（选型依据见 design.md BC-18）

### 不在本 spec（由两份 lane spec 承担）

- `b-class-shared-base-carrier-lanes`：共享基类载体剩余 **4** 条（#6 #7 #8 #10）
- `b-class-orphan-carrier-and-host-inline-lanes`：`useWpDualMode` **3** 条（#1 #2 #3）+ host_inline **2** 条（#4 #9）

### 显式排除边界

- `xlsx/b60/*` pilot 系列（已交付，`GtB60Bundle` / `GtB60DocxPane` / `GtB60HourBudgetPanel` / `GtB60MainDoc` / `GtB60SubSheetForm` 5 个组件）
- `components/workpaper/` 下 strict 域内但**无 OO 挂点**的 **9** 个 B 组件：`GtB13Bundle` `GtB19Bundle` `GtB212Evaluation` `GtB25Evaluation` `GtB2Bundle` `GtB2FlowOverview` `GtB2PredecessorInfo` `GtB30GroupAudit` `GtB51Bundle`
- 本轮 entry 的子对话框（不带 `Gt` 前缀，无 OO 挂点）：`B22AControlItemDialog` `B23ControlPointDialog` `B50AccountRiskDialog`

## 需求

### 需求 1：BC 判据一次性裁定

**用户故事**：作为承接 B 域三份 spec 的工程师，我需要一份权威的共同判据表，避免同一判据在三份 spec 里各裁一次导致口径漂移。

#### 验收标准

1. WHEN 读 design.md THEN 系统 SHALL 提供 BC-1 ~ BC-60 连续无缺号的裁决表，每条含「主题 / AC 基准 / 判定 / B 侧现算分母 / 归属」五列
2. WHEN 判定为 ❌（不适用）THEN 该条 SHALL 附「空分母的现算证据」而非「推测不适用」
3. WHEN 判定为 🔁（反转）THEN 该条 SHALL 同时写明 A 轮结论与 B 轮证伪证据
4. WHEN 两份 lane spec 引用判据 THEN 它们 SHALL 只写 BC 编号，不重复裁决内容

### 需求 2：10 条 entry 事实基线锁定

**用户故事**：作为后续改线的工程师，我需要每条 entry 的解析路径、载体、真库分母被冻结成可复算的断言，避免改线时凭印象操作。

#### 验收标准

1. WHEN 运行基线守卫 THEN 系统 SHALL 逐条断言 10 个 entry 的 `entry_id` / 载体 / `group_id` / `capability_target_blocked_by`
2. WHEN slice 被改动导致 B 域 entry 数不再是 10 THEN 守卫 SHALL 失败并指明差异
3. WHEN 断言解析路径 THEN 守卫 SHALL 同时覆盖三种失败模式（返回 `None` / 抛 `FileNotFoundError` / 多册歧义）
4. IF 某 entry 的真库载荷为 0 行 THEN 基线 SHALL 显式登记为空分母而非跳过

### 需求 3：首张 canary 可切换且可回滚

**用户故事**：作为质控，我需要首张 canary 证明「真双向」在 B 域可落地，且失败时能一键退回假双向。

#### 验收标准

1. WHEN canary entry 的 `capability` 被置为 `bidirectional` THEN 其结构化视图与 OO 视图 SHALL 读同一权威源
2. WHEN OO 侧写入后切回结构化视图 THEN 结构化视图 SHALL 反映写入结果（非缓存快照）
3. WHEN canary 落地后跑既存守卫 THEN 既存 B60 pilot 的 **7** 处断言 SHALL 全部保持通过
4. IF canary 出现回归 THEN `capability` SHALL 可退回 `null` 且不留脏数据

### 需求 4：五项 B 域独有阻塞被显式登记为外部依赖

**用户故事**：作为项目经理，我需要知道哪些阻塞不是本轮能解的，避免把 spec 标成假完成。

#### 验收标准

1. WHEN 读 tasks.md THEN 全 slice 共有的 **5** 项阻塞（BP-1 approved 模型 / BP-2 contract / BP-3 capability 裁决 / BP-4 bundle+published / BP-5 adapter 注册）SHALL 标记为 `[ ]*` 并注明「外部依赖」
2. WHEN xlsm 宏层双重丢失（BC-49）无技术解 THEN 该项 SHALL 记录为「数据验证扩展无法保留」而非标为已解决
3. WHEN 某判据因外部依赖无法实测 THEN 措辞 SHALL 为「代码已改但未实测」

### 需求 5：B 域行身份缺陷族被识别而非漏判

**用户故事**：作为审计助理，我在底稿中插入或删除行后，已填内容不应错位或丢失。

#### 验收标准

1. WHEN 扫描行身份缺陷 THEN 扫描器 SHALL 覆盖**函数参数式行下标**形态（`rowIndex` / `idx` 形参），不得只扫 N 轮的 `${PREFIX}-${index}` 形态
2. WHEN 扫描器在 B 域返回 0 命中 THEN 该结果 SHALL 被判为扫描器缺陷而非「本域无缺陷」
3. WHEN 行数用独立 `count` 键持久化 THEN 守卫 SHALL 断言 `count` 与实际行键数量一致
4. WHEN 渲染 key 使用可编辑文本（科目名 / 分组 label）THEN 守卫 SHALL 报缺陷并指向稳定替代（行携 `id`）
