# C 循环双向回写地基与首张 canary — 需求

## 背景

C 循环（控制测试）在 `workpaper_sync_abcs_cycle_manifest_slice.json`（A/B/C/S 四循环合用，A 轮已切 20 条、B 轮已切 10 条）中占 **2 条** in-scope entry，覆盖 **29 个 wp_code**。

🔴 **按 `wp_code_patterns` 首字母切域只得 1 条，会漏掉 C 循环主体**：`xlsx/gt-c-control-test` 的 `wp_code_patterns` 是**空数组**（属 slice 的 5 条 `pattern_less` 跨循环共享宿主之一），但它的 `wp_codes_via_component_type` 有 **28 个 C 码** —— 它才是 C 循环的业务主体。slice 的 AD-1 已明文警告「照抄单字母规则会漏这 5 条」，AD-9 进一步警告「`c-control-test` 1 条 entry 覆盖 28 个 wp_code ⇒『每 entry 一个 wp_code_pattern』的判据在本轮会**漏掉 27 个码**」。

## 范围

### 2 条 entry（全名）

| # | entry_id | pattern | 真实 wp_code | family | group | 载体 | switch | BP 数 | 宿主行数 | 真库行数 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `xlsx/gt-c-control-test` | （空数组） | **28 个**（`C2`~`C15` 与 `C2-2`~`C15-2`） | `control_test_router` | GRP-07 | `host_inline_segmented` | `redeemable` | 7 | 1719 | **136** |
| 2 | `xlsx/gt-c22-itgc-bundle` | `C22I` | `C22`（1 个） | `c_class_bundle` | GRP-06 | `no_carrier` | `no_switch_at_all` | **8**（含 **BP-10**） | 890 | **0** |

1 + 28 = **29** 个 wp_code。两条 entry 的形态**几乎处处相反**（载体 / switch / 门控 / 码数 / BP 数 / 真库分母），故拆两份 spec（见 design.md §一）。

### 本 spec 承担

1. 一次性裁定 **CC-1 ~ CC-56** 共同判据（以 B 轮 CC 基准 BC-1 ~ BC-60 逐条重裁）
2. 锁定 2 条 entry 的事实基线（BP 归属 / 载体 / 解析路径 / 真库分母 / 模板册）
3. 落地首张 canary：**`xlsx/gt-c-control-test`**（选型依据见 design.md §四）

### 不在本 spec

- `xlsx/gt-c22-itgc-bundle` 的改线由 `c22-itgc-no-switch-and-domain-code-sheet-lane` 承担（本 spec 只锁它的事实基线与 CC 判据）

### 显式排除边界

**A. `pattern_less` 另 4 条不属 C 轮**（归属裁决依据现算自 `wp_codes_via_component_type` 与 override 表反查）

| entry | override 反查 | 裁决 |
|---|---|---|
| `xlsx/cash-flow-verification` | `cf-verification` → **1 码 `A5`** | 🔴 **属 A 域，A 轮遗漏** —— 本 spec 只登记缺口，不在本轮修 |
| `xlsx/gt-custom-wp-editor` | `custom` → **0 码** | 留独立一轮（channel `custom_cells` 为全 slice 唯一；`migration_state` 是 `adapter_candidate`） |
| `xlsx/gt-wp-renderer` | 无 componentType | 留独立一轮（BP **9 项**，含 BP-10 + BP-12） |
| `xlsx/shared/cycle-standalone-procedure-shell` | `a-program-console` → **32 码** | 留独立一轮（规模比 `c-control-test` 更大，且 32 码横跨 B/F/G/H/K/L/S 六个字母 + 2 个中文码） |

**B. strict 域内无 OO 挂点的 7 个组件**：`GtC1EntityControl` / `GtC21FindingsSummary` / `GtC22ControlSheet` / `GtC23JournalControl` / `GtC24JournalDetail` / `GtC25InternalAudit` / `GtC26InfoControl`

**C. 目录内不属本轮 entry 的 7 本册**：`C1 企业层面控制测试` / `C21 具有信息技术专业技能的项目组成员` / `C21-1  IT审计发现汇总表` / `C23 会计分录 - 控制测试` / `C24 会计分录 - 细节测试` / `C25 利用内审工作` / `C26 信息处理控制测试`

## 需求

### 需求 1：CC 判据一次性裁定

**用户故事**：作为承接 C 域两份 spec 的工程师，我需要一份权威共同判据表，避免同一判据两处各裁一次导致口径漂移。

#### 验收标准

1. WHEN 读 design.md THEN 系统 SHALL 提供 CC-1 ~ CC-56 连续无缺号的裁决表，每条含「主题 / BC 基准 / 判定 / C 侧现算分母 / 归属」五列
2. WHEN 判定为 ❌（不适用）THEN 该条 SHALL 附空分母的现算证据
3. WHEN 判定为 🔁（反转）THEN 该条 SHALL 同时写明 B 轮结论与 C 轮证伪证据
4. WHEN lane spec 引用判据 THEN 它 SHALL 只写 CC 编号，不重复裁决内容

### 需求 2：28 码 router 的一对多归属被正确处理

**用户故事**：作为改线工程师，我需要 `gt-c-control-test` 这一条 entry 下的 28 个 wp_code 都被覆盖，而不是只处理 1 个。

#### 验收标准

1. WHEN 断言该 entry 的 wp_code 集合 THEN 系统 SHALL 用 override 表反查 componentType，现算得 **28** 个而非 1 个
2. WHEN 28 码分成主册与 `-2` 册两族 THEN 判据 SHALL 按族分别断言（两族的缺陷分布完全不同）
3. WHEN 真库只有 4 个循环有载荷 THEN 其余 10 个循环 SHALL 被显式登记为空分母而非跳过
4. IF 某判据只对 1 个码成立 THEN 该判据 SHALL 声明覆盖面而非假装覆盖全部 28 码

### 需求 3：行身份 CLEAN 结论不被误判为缺陷

**用户故事**：作为审计助理，控制测试步骤行的身份来自程序表步骤号，我不希望改造把它换成数组下标。

#### 验收标准

1. WHEN 扫描行身份 THEN 扫描器 SHALL 区分「`idx` 进入持久化键」与「`idx` 仅作内存与 UI 局部索引」两类
2. WHEN `idx` 仅作内存与 UI 局部索引 THEN 该处 SHALL NOT 被判为缺陷（照抄 B 轮口径会产生假阳）
3. WHEN 行身份为 `step.num`（程序表业务键）THEN 改造 SHALL 保留该机制，不得改为下标
4. WHEN 断言该结论 THEN 证据 SHALL 包含「`item_id` 模板串含 `idx` 的命中数为 0」与「持久化模块内 `idx`/`index` 命中数为 0」两项

### 需求 4：boolean falsy 值持久化不丢失

**用户故事**：作为审计助理，我在偏差评价决策树里显式选了「否」，不应与「未填」无法区分。

#### 验收标准

1. WHEN 决策树字段类型为 `boolean` 且值为 `false` THEN 持久化 SHALL 保留该值而非按空值跳过
2. WHEN 真库缺少某 step 键 THEN 判据 SHALL 区分「用户未填」与「填了 falsy 值被丢弃」
3. WHEN 断言决策树字段 THEN 断言 SHALL 覆盖全部 **6** 个 step 字段而非只覆盖真库可见的 5 个
4. IF 该缺陷修复 THEN 存量数据 SHALL 可区分两种情形或显式声明无法区分

### 需求 5：四项 C 域共有阻塞被显式登记为外部依赖

**用户故事**：作为项目经理，我需要知道哪些阻塞不是本轮能解的，避免把 spec 标成假完成。

#### 验收标准

1. WHEN 读 tasks.md THEN 两条 entry 共有的阻塞（BP-1 / BP-2 / BP-3 / BP-4 / BP-5 / BP-7 / BP-8）SHALL 标记为 `[ ]*` 并注明外部依赖
2. WHEN 某判据因外部依赖无法实测 THEN 措辞 SHALL 为「代码已改但未实测」
3. WHEN `C22` 真库分母为 0 THEN 其验证 SHALL 依赖人造数据并显式声明该前提
