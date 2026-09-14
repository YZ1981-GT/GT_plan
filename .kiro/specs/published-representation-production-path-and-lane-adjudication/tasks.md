# Implementation Plan: published-representation-production-path-and-lane-adjudication

## Overview

实现语言 **Python 3.12**（设计文档全程使用 Python，无需再选）。交付顺序遵循 design.md §Rollout：裁决先行 → 只读预演 → 首版落成 → 第二个 entry → capability 裁决 → 回归门更新 → 收口。

**不新增数据库迁移**（磁盘最高 V153，本 spec 不加 V154）。一切写库经服务层或幂等宿主脚本，PG MCP 全程 restricted 只读。

新增/改动文件：

| 记号 | 路径 | 性质 |
|---|---|---|
| F1 | `backend/app/services/workpaper_sync/projection_lane_registry.py` | 新增 |
| F2 | `backend/app/services/workpaper_sync/projection_first_publication.py` | 新增 |
| F3 | `backend/scripts/fix/fix_projection_first_publication.py` | 新增（唯一宿主） |
| F4 | `backend/scripts/check/check_projection_lane_adjudication.py` | 新增（回归门） |
| F5 | `backend/scripts/diagnose/mutate_projection_first_publication_guards.py` | 新增（变异） |
| F6 | `backend/tests/workpaper_sync/test_projection_lane_registry.py` | 新增 |
| F7 | `backend/tests/workpaper_sync/test_projection_first_publication.py` | 新增 |
| F8 | `backend/tests/workpaper_sync/test_projection_first_publication_pg.py` | 新增（真实 PG） |
| F9 | `backend/tests/workpaper_sync/test_projection_lane_regression_gate.py` | 新增 |
| F10 | `backend/app/services/workpaper_sync/opaque_entry_gate.py` | 改（更正过期读数） |
| F11 | `backend/scripts/check/check_task61_oo94_word_pilot_gate.py` | 改（BP-61-1 判据） |
| F12 | `.github/workflows/governance-checks.yml` | 追加 job（只加不动） |

命令一律 Windows PowerShell、仓库根、`;` 分隔、`cwd` 参数代替 `cd`；pytest 从仓库根跑，**不跑全量** `backend/tests`。

## ✅ 收口记录（2026-09-05 · K · Task 11.2 / 12）

### 判据总量与三门基线

| 产物 | 判据数 | 说明 |
|---|---|---|
F6 `test_projection_lane_registry.py` | **73** | Property 1/2/3/4/5/6/7/8/9/17 |
F7 `test_projection_first_publication.py` | **70** | Property 10/11/12/14/15/16/18/19/20/21/22/23/24/25/26 |
F8 `test_projection_first_publication_pg.py` | **51** | 真实 PG 临时 schema。Property 13/18 行为侧/22/24/26 落库侧/33/34/35 + 空载荷 provider 声明 |
F9 `test_projection_lane_regression_gate.py` | **41** | Property 27/28/29/30/31/32 |
合计 | **235** | 全绿（2026-09-05 实测 61.4s）|

三门基线：

| 门 | 入口 | 结果 |
|---|---|---|
F4 完整 | `check_projection_lane_adjudication.py --json <p>` | exit 0 · 已验证 5 项全成立 |
F4 offline（CI 用） | 同上 `--offline` | exit 0 · 已验证 2 项（R3b/R4），另 3 项逐项写明未验证 |
F5 锚点自检 | `mutate_...guards.py --check-anchors` | 9/9 锚点可用 |
Task 44 四态（差集分母）| F4 的 R1 现跑 | `{failed: 28, passed: 5, unverifiable: 140}` —— **failed 未因本 spec 增加** |

### 九条变异判读（`--run`，2026-09-05 实测 199.07s）

`{'RED': 2, 'RED(+其它)': 7}` · `all_red = True`。基线 F7 70 / F6 73 与上表一致。
`RED(+其它)` 是**判据更强**而非缺陷：同一处退化确实同时打红相邻判据。

### Final checkpoint 五项收口核对（全部成立）

| # | 判据 | 实测 |
|---|---|---|
① | manifest entry 有 current `projection_contract` representation | `xlsx/gt-g7-long-term-equity-main` gen=1 bundle=`889fcb95dded` |
② | `--check` 对 B60/G7 落在对应格（负例证明判据在跑）| B60=`blocked_ooxml_gate` · G7=`already_published` |
③ | 九条变异全 RED | total=9 all_red=True |
④ | 三门基线已记录且 `failed` 未增 | 28 → 28 |
⑤ | F1~F12 + spec 四文件全部已入库 | 16/16 |

### 🔴 CI 接线的一处偏离（Task 11.1）

tasks.md 11.1 原文要求把 `check_projection_lane_adjudication.py` 挂进 CI，实际挂的是
**`--offline`**。理由是环境事实：R1/R2 度量的是「本仓库 dev 库里首版已落成」，而 CI 每次起崭新空库。
2026-09-05 实测（空临时 schema + 跑完 V151/V152/V153）：`working_paper_content_representation`
**0 行**、`working_paper_sync_definition_bundle` **0 行** ⇒ R2 的「≥1 条 projection_contract
representation」必不成立、R1 的供给判据 B 为假 ⇒ 四个 pilot 全被拒。挂完整门只会得到恒红 job，
而恒红的门很快会被人 skip 掉 —— 那比没有门更糟。

CI 可用性由**对照组**证成：把 `DATABASE_URL` 指到 `127.0.0.1:1`（不存在），`--offline` 与
`--check-anchors` 都 exit 0，而完整模式在**同一环境**下以 `ConnectionRefusedError` exit 2。

R1/R2/R3a 的验收留在有数据的环境里人工跑。

### 🔴 一处与 Requirement 12.5 的实测差距（跨 spec，待裁决）

Requirement 12.5 声明 H1 与 D2 为**可发布目标**，而在干净临时 schema 上逐个实测，
**四个 entry 都没走完发布链**。H1 与 D2 撞的是同一错形，根因已定位到单元格级：

* H1 契约声明受管数据行 13..27，模板里 13..26 是序号 `1..14`、**行 27 是 `'……'`**；
* D2 契约声明 13..25，模板里 13..24 是 `1..12`、**行 25 是 `'……'`**。

`'……'` 是模板「此处可续行」的视觉约定，而契约把该行也算受管数据行且 `seq` 的
`value_type` 是 `integer`。空 store ⇒ overlay 保留基线 ⇒ materialize 把 `'……'` 写回
integer 字段 ⇒ 规范化拒绝（那正是 `excel_materialize` 该做的）。与真库 `--apply` 实测的
`blocked_template_contract_drift` / `blocked_row_insertion_required` 同源。

三种改法都跨出本 spec 范围（收窄已冻结的契约受管区 / 放宽 `value_type`（Requirement 7 明禁）/
改 extract 的行身份语义），故**照实固化为 F8 的判据**（`TestFirstPublicationFeasibleDomain`）：
谁修通了它就打红，提示更新可行域与本节。

### ✅ 已修：空 store 载荷改为**由 provider 自己声明**（2026-09-05 · K）

**缺陷**：宿主用**同一个** `_EMPTY_STORE_PAYLOAD = "[]"` 喂所有 provider，但四个 pilot 的
store 根形态并不相同 —— H1/D2 是**行数组**、**G7 是对象**（带 `version` / `entitySlots` /
`tables`）⇒ 单一常量对 G7 无解，而换成 `"{}"` 会让 H1/D2 全崩。至今未爆是因为
`resolve_plan` 排在 `_read_store_payload` **之前**，真库上 G7 被 `already_published` 拦住；
干净库上会崩且 `StorePayloadError` 当时未登记进 `_ERROR_CODE_TO_STATE` ⇒ 落进
`blocked_unregistered_failure_shape`，把一个有明确解除方的情形报成「词表要扩」。

**实测先定性再改**：逐个喂四种候选形态给 G7，全被拒且各有正当理由 ——
`"[]"` 根形态不对 · `"{}"` state version=None · `{"version":2}` entitySlots 缺失 ·
`{"version":2,"entitySlots":{},"tables":{}}` 实体列表为空。最后那条是关键：
`iter_store_entities` 对空实体列表**故意抛错**（「审计师删到 0 家」必须显式失败，
不得被静默补成模板默认的 5 列）。⇒ **G7 根本没有「空载荷」这个合法状态**，
给它编一个形状等于去对抗一条正确的判据（Task 43 的判据）。

**改法**（「空载荷长什么样」只有 provider 自己知道，放在调用方就是猜）：

| 改动 | 内容 |
|---|---|
H1 / D2 | 各声明 `EMPTY_STORE_PAYLOAD = "[]"`（实测自己接受、产出 values=0）|
**G7** | 声明 `EMPTY_STORE_PAYLOAD = None` —— **故意为 None，不是漏填**，docstring 里写清四种候选形态各自被拒的理由 |
宿主 | 新增 `_empty_store_payload_for(provider)` 问 provider；`_read_store_payload` 加 `provider` / `entry_id` 实参 |
宿主 | 新增 `EmptyStoreNotPublishableError`（`error_code = store_payload_empty_and_not_publishable`）|
封闭词表 | 新增两格：`store_empty_nothing_to_publish` 与 `blocked_store_payload_shape` |

🔴 **两处刻意的设计选择**：

1. `store_empty_nothing_to_publish` **不叫** `blocked_*` —— 它不是阻塞。
   「审计师还没在 HTML 侧录内容」没有任何东西需要被解除，归进 `blocked_*` 会让
   运维去找一个并不存在的解除方。
2. 「store 空」与「store 形态不符」是**两格**。修之前两者都落兜底格，合成一格会让
   「先去录数据」和「数据坏了要修」指向同一个解除方，而它们的处置完全不同。
   顺带把此前未登记的 `sync_pilot_store_payload_invalid` 也登记了。
3. provider **未声明**时抛 `HostError` 而**不是** `EmptyStoreNotPublishableError` ——
   「漏了声明」与「本 pilot 没有这个状态」是两件事，混同会把疏漏静默结算成正常结论。

**判据**：F8 的 `TestEmptyStorePayloadIsProviderDeclared`（9 条，45 → 51 passed）。
含防回退判据 `test_the_host_no_longer_has_a_one_size_fits_all_constant`（AST 扫模块级
赋值，谁把单一常量加回来就打红）、声明自洽判据（现跑 `build_store_projection` 验
声明的空载荷真被自己接受）、以及「声明 None 的必须确实没有任何可用空形态」
（防「懒得找形状就写 None」）。

**变异检验 8 条全 RED**：未声明预检短路 / 声明 None 时回退到猜 `"[]"` / 新 code 映射到
`blocked_*` / 两格合成一格 / 给 G7 编一个它自己不接受的空载荷 / H1 声明成对象形态 /
error_code 改成未登记值 / 新格不进封闭词表。

## ✅ M1 已达成：首版 projection representation 已在真实库落成（2026-09-04 · A）

**Checkpoint Task 8 的判据成立**（PG 只读现查，不看退出码）：

| 字段 | 值 |
|---|---|
`entry_id` | `xlsx/gt-g7-long-term-equity-main` —— **manifest entry，非 `opaque-` 命名空间** |
`authority_model_type` | **`projection_contract`** |
`logical_id` / `bundle_state` | `g7.soe_subsidiary_disclosure.authority-model` / `approved` |
`adapter_id` / `generation` / `content_revision` | `g7.soe_subsidiary_disclosure` / 1 / 1 |
`structure_hash` / `definition_bundle_sha256` | `7048d2c2777f…` / `889fcb95dded…` |

`definition_bundle_sha256` 与 Task 76 宿主 `--apply` 的产出**逐字相同** —— 两条独立路径互证。
三表 `1/1/1` → **`2/2/2`**；`projection_contract` lane representation **0 → 1**。

**幂等已验**（Requirement 6.8）：重跑 `--apply` 落 `already_published`，三表行数与
bundle / artifact 计数**逐项不变**（`2/2/2` · 6 · 18）。

**逐 entry 独立事务已验**（Requirements 6.6 / 6.7 / 6.11）：同一次 `--apply` 里 H1 与 D2
各自失败并只回滚自己、G7 成功提交、四个 entry 全部被处理、最终退出码非零。

## 🔴 L1 首版实测阻塞（2026-09-04 · A · Wave 9~10 现场记录）

`--apply` 真跑过，**四个 entry 一个都发不出去，库里 0 新增行**（逐 entry 独立事务全部完整
回滚；判据取自数据：`content_version` / `content_representation` / `entry_state` 三表逐项等于
基线 1/1/1，`projection_contract` lane representation 仍为 0，H1 目标底稿 `content_revision`
仍为 0 且 `updated_at` 还是 2026-05-31）。

| entry | 结算 | 止步 | 阻塞与解除方 |
|---|---|---|---|
`xlsx/gt-h1-fixed-assets` | `blocked_template_contract_drift` | 7/10 | **A27 的 `……` 无法按 `integer` 规范化**。见下 Open Gate 4 |
`xlsx/gt-d2-accounts-receivable` | `blocked_row_insertion_required` | 7/10 | **729 个行身份在 substrate 上无物理行**，要结构性插行 ⇒ 解除方 = `excel-structural-row-insertion-and-shift-aware-verification` 的 Wave 4 |
`xlsx/b60/gt-b60-bundle` | `blocked_ooxml_gate` | 3/10 | `gate=external_relationships`，安全策略裁决（本 spec 不放宽） |
`xlsx/gt-g7-long-term-equity-main` | 首轮 `blocked_missing_approved_bundle` 2/10 → **现 `ready_to_publish` 10/10，已发布** | — | **已解开**，见下「G7 解锁链」 |

### G7 解锁链：2/10 → 10/10，四处缺陷全在本 spec 交付面内

每一处都是「前三个 entry 恰好不触发，于是判据在空集上恒真」的形态：

| # | 缺陷 | 为什么前三个 entry 查不出来 |
|---|---|---|
1 | `workpaper_sync_entry_wp_code_adjudication.json` 用一个 `resolvable_today` 布尔把「能否定位宿主底稿」与「wp_code 能否当 EntryMatcher 域」两件事混在一起。G7 的后者为假（三个 entry 真码同为 G7 ⇒ RG-3 `MatcherOverlapError`），于是前者被一并关掉，Task 76 对 G7 完全不 provision | 只有 G7 有 matcher 域冲突。**且该文件自己的 `basis.blocked_note` 明写「本条裁决只供 provisioning 定位宿主，不得直接当 EntryMatcher 的域」—— 文件自相矛盾** |
2 | `_identity_binding` 硬取 `provider.ROWS_TABLE_KEY` | 那是**只有 3/4 provider 遵守的命名约定**。G7 有两张表，导出的是 `MATRIX_TABLE_KEY` / `RECORD_TABLE_KEY` ⇒ `AttributeError`。已改为从**冻结契约**派生行身份表（「`row_identity` 非空 ∧ 有 `row_from=row_identity` 字段」的表，实测 4/4 各恰 1 张）+ 与 provider 常量双向锁死 |
3 | `_identity_binding` 往 `dynamic_column_columns` 塞的是 **label**，而它要的是 **Excel 列标** | 前三个 entry 的契约都没声明 `dynamic_columns` ⇒ 字典恒空 ⇒ 错形完全不可见。G7 实测炸 `ValueError: 'minority_financials#1' is not a valid column name`。已改为委派生产实现 `published_identity_observer.observe_dynamic_column_bindings`（与 label 那一份共用 `_dynamic_spans`，故「键数≠列数」「两键同列」构造上不可能） |
4 | `_overlay_store_on_substrate_baseline` 把 provider 吐出的**占位 `None`** 原样叠进 projection | G7 的 `minority_financials` 是 10×10 矩阵，`build_store_projection` 吐 **100 个显式 None** 的 amount 字段，而 substrate 上那 100 格是空的（`extract` 对空格不产键，基线只有 5 个值）⇒ materialize 把 None 写成 `0`，反读 100 处全部 `None → 0` 不等值。已改为**只丢「基线没有该键 ∧ store 值为 None」**的字段 —— 保留「基线有值而 store 给 None」的清空语义，少了这一半会把审计师的清空动作静默吞掉 |

### 🔴 附带更正：entry → wp_code 曾有三份真源

`_index.json` 反查（本宿主原来的做法）与 reviewed 裁决表实测**分歧 2/4**，且**两边各错一处**：

| entry | `_index.json` 反查 | reviewed 裁决（原） | store 载荷实际落点 | 谁对 |
|---|---|---|---|---|
B60 | `B60`（5 底稿 / **1** 有文件，那 1 个是 5749 B 占位表无受管 sheet） | **`B60-1`**（3 底稿 / 3 全有文件） | 该 provider 无 `STORE_ITEM_ID` | **裁决表** |
D2 | **`D2`**（39 底稿 / 35 有文件 / **866,972 B** 载荷） | `D2-2`（5 底稿 / **0 载荷**） | **`D2`** | **反查** |
H1 | `H1` | `H1` | 无载荷（空表单是合法事实） | 一致 |
G7 | `G7` | `G7` | `G7`（3 底稿 / 32,617 B） | 一致 |

根因：裁决表的 `wp_index_evidence` 只查「几行有 `file_path`」，**从没查 store 载荷**，于是
在 D2 上被「受管 sheet 名『明细表D2-2』与 wp_index 的 `D2-2`『应收账款明细表』完美同名」
这条线索带偏。按它发首版会得到空 projection，且 representation 挂在用户并不编辑的那个底稿
上、与 HTML 永久失联。

已处置：① 裁决表 D2 改为 `D2`，新增 `store_payload_evidence` 字段与
`basis_rule_precedence`（**载荷落点优先于名字相符**）② 本宿主删掉 `_template_wp_code`，
改读同一份裁决表（`_adjudicated_wp_codes`），第二真源消除 ③ `resolvable_today` 拆成
`resolvable_for_provisioning` + `matcher_domain_conflict`，缺键即抛不默认放行
④ `adjudication_digest` 原算法全仓无处记载，换成算法自带的自描述形态并自证复算。

### 🔴 更正 design.md 与分工书的关键路径判断

原判断「`bidirectional = 0` 是最根本的阻塞 —— 没有首版，B / C / D 做完也没有可回写的对象」
**方向是反的**。实测：D2 的首版发布**依赖结构性插行泳道**（`excel_row_shift.py` 现在生产零
引用），所以 **M2（插行可用）是 M1（首版落库）的前置**，不是相反。本 spec 的 Wave 10~11
在插行接线完成前无法收口 —— 这不是本 spec 的实现缺陷，是依赖顺序此前被算错了。

### Open Gate 4（新增）：受管区末行的「……」排版占位行

H1 的 `disposal_check_rows` 受管区是**派生**的（`anchor=A10` + `header_rows=3` + footer 锚点
「合计」⇒ 13..27），派生规则「表头与合计之间都是数据行」把模板的续行省略号一并吞进受管区：

```
A13..A26 = 1..14        （整数 seq，合法）
A27      = ……           ← 排版占位，被当成第 15 行业务数据的 seq
A28      = 合计          （footer）
```

契约 `h1.disposal_check.json` 的 `review` 块**自己记着这个事实**（`reviewed_basis` 明写
「A13..A26 字面量 1..14 + A27 占位 ……」），而且对**列**方向已有先例 ——
`excluded_columns` 排除了 X 列，理由「模板的扩展占位列（表头文本恰为 `……`），没有业务语义」。
但**没有行方向的对应物**：`review` 里没有 `excluded_rows` 键（4 份 pilot 契约全都没有）。

普遍性实测（349 份 xlsx / 2602 张 sheet 全扫，0 失败）：

| 事实 | 值 |
|---|---|
整格为纯省略号的 A/B/C 列格 | **842** |
「`……` 行紧跟合计/小计/总计行」形态 | **170** |
涉及模板 | **37 份** |
涉及 wp_code | **35 个**（A1 A3 A5 D0 D1 D2 D4 E1 F1 F2 G1 G5 H1 H2…S21） |
H1 自身命中 | **5 处**（含卡住首版的 `减少检查表H1-8!A27`） |
D2 自身命中 | **1 处**（`明细表D2-2!A25`）⇒ **B 接完插行后 D2 会撞同一个门** |

⇒ **裁决建议：平台级派生规则，不是逐契约 `excluded_rows`。** 170 处 / 37 份 / 35 个码族，
逐契约声明等于要写 170 条排除，且每份新契约都得记得写 —— 那是必然遗漏的形态。

具体落点 = `excel_extract.resolve_managed_region` 派生 `last_row` 时剔除「整行只有首列且首列
为纯省略号」的行（H1 受管区 15 行 → 14 行）。

🔴 **该文件归结构性插行泳道（B）独占，A 不动它。**

**已于 2026-09-04 正式提请 B**，交接件（自包含）：
`docs/operations/bp-21-managed-region-typography-row-handoff.md`

**验收判据**（已入库，B 落地后跑它即可判成败）：

```
python backend/scripts/check/check_managed_region_typography_rows.py --expect-managed-region-hits 0
```

判据落在 **§B 逐 pilot 受管区扫描**（现读 `resolve_managed_region` 的真实返回值），
**不是** §A 的全库清册数 —— 后者恒为 170、不随修复变化，拿它当验收永远打红（首版脚本
写的就是这个错，已更正）。落地前实测基线：

| entry | 受管区 | 区内占位行 |
|---|---|---|
H1 | `A13..27`（15 行，`table_ref=A13:AB27`） | 🔴 **A27** |
D2 | `A13..25`（13 行，`table_ref=A13:AN25`） | 🔴 **A25** |
G7 | `A79..83`（5 行） | ✅ 干净 —— 所以它能发 |
B60 | — | ⊘ `unverifiable_ooxml_gate`（从分母剔除，剔除数已写出） |

退出码 **1**，区内占位行 **2 行 / 涉及 2 个 entry / 实扫分母 3 个**。

**D2 那一行很重要**：BP-21 挡的是**两个** entry，不是只挡 H1 —— B 接完插行后 D2 会撞同一处。

若 B 判定不宜在其 spec 内承接，退路是本 spec 加一条契约裁决任务并走
`template → instrumentation → contract → bundle → representation` 完整发布链
（重，且 H1 bundle 现为 approved）。

### ✅ Tasks 10.1 / 10.3 完成（2026-09-04 · A）—— 九条变异全 RED，暴露 1 真守卫缺陷 + 5 处本脚本缺陷

`backend/scripts/diagnose/mutate_projection_first_publication_guards.py` 已建，
报告落 `backend/data/workpaper_sync_projection_first_publication_mutations.json`。
**判读分布 `{RED: 7, RED(+其它): 2}`，`all_red: True`，用时 65s。**

先建了缺失的靶子文件 **F6**（`test_projection_lane_registry.py`，45 例）——
九条变异里 M1/M2/M3/M7 打在 lane registry 上，而它的测试文件此前**不存在**：
没有靶子的变异只会判 WRONG-TEST，证明不了任何事。F7 同时补了 5 条缺失靶子
（M4 判据 ③ 取反 2 条、M8 逐 entry 事务 2 条、M9 additive 死代码 1 条），现 27 例。

#### 🔴 第一轮 `--run` 判出 5 条 GREEN —— 逐条归因后 **4 条是本脚本缺陷，1 条是真守卫缺陷**

这是本次最有价值的产出：**GREEN 不等于守卫有缺陷**，必须先证明变异真的改变了语义。

| 变异 | 首轮 | 归因 | 处置 |
|---|---|---|---|
M1 | GREEN | 锚点落在**注释行**上，替换后 `if False:` 与原 `if` 缩进错乱 ⇒ **语法错** | 改为短路 `_is_opaque_entry_id` 的返回值 |
M3 | GREEN | 把 `raise X(...)` 换成多行 `return`，残留 `from exc` ⇒ **语法错** | 跨行锚点，连 `from exc` 一并替换成「四条皆假」 |
M6 | GREEN | 只在 `adapter=adapter` 旁**新增注释** ⇒ AST 完全相同（**空操作**） | 跨行锚点定位 commit 那处，`adapter=adapter` → `adapter=None` |
M8 | GREEN | 锚点落在**注释行**上 ⇒ AST 完全相同（**空操作**） | 跨行锚点，`async with Session()` → `nullcontext(_shared_session)` |
M7 | GREEN | **真守卫缺陷**（见下） | 修生产守卫 |

**为什么语法错会被误判成 GREEN**：变异让文件语法错时 pytest 报 `ERROR collecting`
（collection error），它**不以 `FAILED` 开头** ⇒ 我的 `_run_pytest` 只数 FAILED 行 ⇒
得到「零新增失败」⇒ 判 GREEN。而那与守卫毫无关系，变异根本没被执行到。

**脚本随之补了三道自检**（都落在 `--check-anchors`，秒级只读）：

1. **命中次数恰为 1**（原有）
2. **变异后 `ast.parse` 仍成功** —— 语法错在预检阶段就报 ANCHOR-MISS，不进判读
3. **变异后 AST dump 与原文不同** —— 空操作（只改注释/空白）直接报 ANCHOR-MISS

外加运行期兜底：`_run_pytest` 新增第四个返回值 `collection_failed`（认
`ERROR collecting` / `SyntaxError` / `IndentationError` / `INTERNALERROR` 等标志），
命中即判 **ANCHOR-MISS** 而非 GREEN。M9 就是被第 2 条预检当场抓住的（`invalid syntax`）。

#### 🔴 M7 是真守卫缺陷：文件级 import 豁免短路了作用域级判据

`assert_no_second_lane_decision_site` 的 `startswith("opaque-")` 分支原判据是

```python
if (_scope_calls_lane_registry(...)                      # 作用域级：对的
    or (imported_from_lane_registry & _LANE_REGISTRY_FUNCTIONS)   # 文件级：把整个文件豁免
    or (imported_from_opaque_gate & _OPAQUE_GATE_NAMES)):          # 同上
```

后两条让「这个文件 import 过裁决函数」豁免**整个文件**里的任意 `startswith("opaque-")`。
实测：`projection_first_publication.py` 正当地 import 了 `assert_projection_lane` 与
`observe_lane_supply`（交集非空），于是在其中新增一个私自判定的
`_is_opaque_second_source` 时扫描器**放过**了它 —— 判据取值 `False or True ⇒ 合规`。

**这正是该函数 docstring 与 `_scope_calls_lane_registry` 自己写明要避免的形态**：
「一个文件可以既 import 裁决函数、又在另一个函数里私自判 lane，文件级判据会把后者一起
放过」。作用域级判据已经实现了正确语义，却被两条 `or` 短路成了文件级。

**修法**：删掉两条文件级豁免，只留作用域级。真源自身不受影响 ——
`writer_migration.opaque_entry_id` 是**构造**前缀、`opaque_entry_gate` 是 lane 表，
两者都不用 `startswith("opaque-")` 判定 entry，本 pattern 根本不命中。
修完 72 例仍全绿 ⇒ **没有任何正当调用点依赖那条豁免**（若有，那才说明豁免是必要的）。

#### 一处刻意放宽的纪律（带理由，不是偷懒）

tasks.md 原文要求「锚点不含 `\n`」，理由是「CRLF 下跨行锚点必 MISS」。本脚本在匹配**之前**
已把读入文本 CRLF → LF 归一，该失效原因不存在；而它确实**拦住了正确的变异** ——
M3（`from exc` 子句必须一并替换）、M6（`adapter=adapter` 全文两处，且旁边新增会构成重复
关键字实参）、M9（实参列表必须整体替换）在语法上都必须跨行。强行单行的结果就是首轮那样：
语法错 → collection error → 误判 GREEN。**仍禁 `\r`**（锚点一律按 LF 书写）。

#### 收口自证

* 九条变异**全部干净还原**：生产文件搜 `← 变异` 标记 **0 命中**，三个文件均可 `ast.parse`
* 每条变异还原后 **sha256 逐条自证**，不等即抛 `MutationHarnessError`
* 基线阈值**逐文件**登记（F6 36 / F7 20），不用全局数 —— 首版用全局 60 把 F7 正常通过的
  27 条误判成「测试没跑起来」，第一次 `--run` 即被自己的自检拦住
* 测试调用走 `subprocess.run([...])` 列表形式，不经 shell
* `--check-anchors` 只读入口秒级，可用于核对「已归档 spec 是否还可复现」

### ✅ Open Gate 5 只读预演已完成（2026-09-04 · A）—— 裁决：只改 D2，不动 H1

**判据是失败形态的移位，不是「感觉通了」。** 隔离单变量做的对照（直调纯函数
`plan_managed_writes`，definitions 仍取既有 frozen bundle，只把它的 `contract` 入参换成
内存打了补丁的那份）：

| entry | 目标底稿 | projection | as-is | patched（`carries_total_formula: true`） |
|---|---|---|---|---|
**D2** | `ef7f88e3` / 490,291 B | 28,495 值 / **742 行** | `RowSetDivergenceError` **[contract_total_formula_not_extendable]** | **推进了** → `EditableCellWriteError` A25 = `……`（即 **BP-21**） |
**H1** | `f663b18c` / **0 B** | 15 值 / 15 行 | `EditableCellWriteError` A27 = `……` | **逐字相同，零变化** |

**结论一：D2 确实需要 Open Gate 5**，且与 BP-21 **串联**（§13.3 的判断被实测证实）——
打开后 footer 门放行、接受插 729 行，随即撞上 BP-21 的 `……`。两道都得解。

**结论二：H1 今天不需要 Open Gate 5。** 它的 store 载荷 **0 字节** ⇒ projection 15 行 =
物理 15 行 ⇒ **不触发插行** ⇒ footer 门根本走不到。BP-21 收缩到 14 行后 baseline 也随之
变 14 行，仍不插行。⇒ **改 H1 契约会白白作废它的 approved bundle 与 4 份冻结证据、
换不到任何推进**。H1 的 footer 确实承载 7 条 `SUM(x13:x27)`（声明为 `true` 是如实的），
但**等它真有数据需要插行时再改**，那时代价换来的是真实推进。

#### 实测代价（改 D2 一份契约）

| 项 | 旧 | 新 |
|---|---|---|
contract canonical digest | `bdd2f6494185…` | **`cb3beceb1dec…`** |
patch 点 | — | `d22-managed/receivable_detail_rows`: `None` → `True`（**仅 1 处**） |
`review_status` | `reviewed` | 不变（`assert_projection_supply_authentic` 要求它恒为 `reviewed`） |
`template_definition_sha256` / `instrumentation_definition_sha256` | 不变 | 不变（模板字节没动，单向引用不断） |

（H1 若改，digest 会是 `15dea471349e…` → `608cce5bca41…`，但按结论二**不改**。）

#### 🔴 双向锁：改 JSON 一份不够

`pilot_d2_large_json.assert_contract_file_matches_source()` 要求**磁盘 JSON 与 provider 的
`build_contract_payload()` 现算 payload 逐字相等**（实测两侧当前 digest 相同）。故必须同步改：

1. `pilot_d2_large_json.py::build_contract_payload()` —— 加 `carries_total_formula: True`
2. `backend/scripts/gen/generate_pilot_d2_large_json_contract.py --apply` —— 重生成 JSON 并人工复核 diff

只改 JSON ⇒ 双向锁打红；只改代码 ⇒ 同样打红。**G7 的 provider 已有先例**
（`pilot_g7_two_level_dynamic.py` 里显式写着 `"carries_total_formula": False` + 理由注释），
照它的形态写即可。解析器侧**无需改动**：`contracts.py` 已解析该键且对非布尔 fail-closed。

#### 🔴 无旁路：`review` 块也进 canonical payload

实测「往 `review` 里加一个键」digest 同样变 ⇒ 不存在「把声明放在不进 digest 的地方」这条
捷径。改契约就必然换 digest、必然要新 contract definition + 新 bundle。

#### 会因此变旧的冻结资产（**9 份**，其中 6 份属别人 spec）

```
别人 spec 的 evidence（W spec = workpaper-html-onlyoffice-bidirectional-writeback-closure）:
  W/evidence/task41-d2-large-json-pilot/README.md
  W/evidence/task41-d2-large-json-pilot/real_payload_facts.json
  W/evidence/task44-oo94-excel-pilot-gate/gate_report.json          ← D2+H1 两份 digest 都在里面
  W/evidence/task61-oo94-word-pilot-gate/first_published_representation_bootstrap.json
  W/evidence/task42-h1-grouped-dynamic-pilot/identity_and_digests.json   ← 仅 H1，不改则不受影响
生成数据文件:
  backend/data/workpaper_sync_task67_structural_pre_reconcile.json
  backend/data/workpaper_sync_task70_oo_scenario_refresh.json            ← 仅 H1 bundle
definition store:
  backend/definition_store/bundles/db877e9dbc73….json                    ← D2 旧 bundle（保留，不删）
  backend/definition_store/bundles/05086f4021a6….json                    ← 仅 H1，不改则不受影响
```

**只改 D2 时实际受影响 5 份**（H1 那 3 份 + task70 全部避开）—— 这是「只改 D2」的第二个收益。

#### 已确认不必付的代价

* **D2 / H1 都还没有 published representation**（`content_representation` 仅 2 行：1 opaque +
  1 G7）⇒ **无需退役任何 representation、无需 pointer 迁移**。这是现在改比以后改便宜的地方。
* 旧 bundle `db877e9dbc73` 不必删：Task 76 宿主按 canonical digest 幂等定位，新 digest 会
  产出**新** bundle，旧的留作历史（S spec AC 5.5 的「不得原地改写已发布 definition」正是要这样）。

#### 🔴 预演中撞到的一道门（它在正确工作）

试图把打补丁的契约喂给 `adapter.materialize(contract=...)` 时被拒：

```
ExcelAdapterIdentityError [excel_adapter_contract_identity_mismatch]
extract: 传入 contract 'd2.receivable_detail' 的 canonical digest cb3beceb1dec… 与 adapter
冻结的 'd2.receivable_detail'/bdd2f6494185… 不一致 —— adapter 按 operation 冻结身份构造
```

⇒ **adapter 在构造时冻结契约 digest**，改契约后**必须**重新走 definition/bundle 发布链才能
生效，没有「先试试看」的捷径。这也解释了为什么预演必须直调 `plan_managed_writes`：
`adapter.materialize(contract=...)` 的那个入参**只用于身份断言**，真正生效的是
`definitions.contract`（来自 frozen bundle）—— 换它对行为零影响。

#### 待裁决（实施前需人工确认）

改 D2 契约 = 动一份 `review_status: reviewed` 的人工审核契约。虽然改动内容是**如实描述模板
事实**（footer 17 条 `SUM(x13:x25)` 实测在册），但「已审契约的再审」应由人确认，A 不自裁。

### 🔴 Open Gate 5 原始记录：D2 / H1 的 footer 合计公式需要契约声明 `carries_total_formula`

**2026-09-04 19:15 实测**：B 的插行已实质接线（`excel_row_shift.py` 从生产**零引用**变成
**19 处**：`excel_materialize` 14 / `adapters/excel` 1 / `excel_extract` 4；
`carries_total_formula` 在 materialize 里 18 处）。D2 的阻塞随之**变形**：

```
[contract_total_formula_not_extendable]
需要插 729 行；但 footer 的合计区间覆盖不到位移后的末行 754，而契约**没有**声明
`footer_anchor.carries_total_formula` ⇒ 引擎无权扩张它。
照插会产出一张合计漏算 729 行的审计底稿。原始判据：footer 格 E26 的公式 'SUM(E13:E25)'
```

即：插行能力已就位，卡在**契约声明**上。而 B 的 spec Task 14 明写「**不**改任何既有契约
JSON（那会改 canonical digest）；改契约是后续 entry 迁移的事」⇒ **这一条归本 spec**。

**裁决依据（实测 footer 行公式，不是按常识推断）**：

| entry | 受管区 | footer 行 | footer 公式条数 | 公式形态 | 区间末行 |
|---|---|---|---|---|---|
D2 | `A13:AN25` | 26 | **17** | `SUM(x13:x25)`（B/F/I/K/L/N/P/S/T/Z/AA/AC~AH 列） | 25 = **受管区末行** |
H1 | `A13:AB27` | 28 | **7** | `SUM(x13:x27)`（I~O 列） | 27 = **受管区末行** |
G7 | `A79:N83` | 85 | **0** | 无合计公式 | — |
B60 | — | — | 不可验 | OOXML 门拒 | — |

⇒ D2 与 H1 的 footer **确实**承载合计公式、且区间末行**恰好等于受管区末行**。声明
`carries_total_formula: true` 因此是**如实描述模板事实**，不是为了让插行通过而放宽判据。
G7 一条合计公式都没有 —— 这正好解释了四个 entry 里为什么只有它发得出去。

**与 BP-21 是串联关系，不是二选一**：D2 受管区末行 A25 本身就是 `……` 行。BP-21 收缩到
`A13..24` 后 footer 仍在 26、公式仍是 `SUM(E13:E25)`；插 729 行后新数据行到 753、`……` 行被
推到 754、footer 推到 755，合计区间仍必须扩张 ⇒ `carries_total_formula` 仍然必需。

**🔴 代价与纪律**：改契约 JSON ⇒ canonical payload digest 变 ⇒ **必须走
`template → instrumentation → contract → bundle → representation` 完整发布链**（S spec
AC 5.5），不得原地改写已发布的 definition / bundle。D2 的 bundle 现为 approved
（`db877e9dbc73`），改契约会产生**新的** contract definition 与新 bundle。Task 76 的宿主
正是那条链的入口（幂等、按 canonical digest 定位），但「旧 bundle 如何退役」需要先实测。

### 🔴 首版落库的连带发现：Task 9.1 阶段一判据已成立，BP-61-1 的绑定根因移位

G7 首版落库后实测（`_describe_entry_supply` 逐 entry 真跑 + `build_manifest_registration_plan`
+ `build_production_registry`）：

| 判据 | 实测 |
|---|---|
`_describe_entry_supply(entry_id="xlsx/gt-g7-long-term-equity-main")` | **`None` ⇒ 放行** |
其余三个 pilot entry | 仍返回拒绝原因（「该 entry 还没有 current published representation」） |
该 entry 的 registration plan item `blocked_reason` | **`None`**（不再被阻塞） |
`build_production_registry().registered_adapter_ids` | **`[]`** 仍为空 |
该 entry 的 manifest `capability` | `single_onlyoffice`（**不是** `bidirectional`） |
`manifest.stats.capability_counts` | `single_html 5 / single_onlyoffice 180 / unreachable 1` ⇒ `bidirectional` **0** |

⇒ **Task 9.1「阶段一」的实质判据已成立**：供给门放行，且判据落在供给门返回值上、不落在
`adapter_registered`。**阶段二未成立**且不属本 spec（需 manifest 重生成 + `approved_source_digest`
人工复核）—— 与该任务 2026-09-03 的两阶段裁决逐字吻合。

BP-61-1 的旧字面量有两句已成假话（Task 9.3 已按此更正）：

| 旧字面量 | 实测 |
|---|---|
「`working_paper_sync_entry_state` 全表 0 行」 | **2 行**（1 opaque + 1 manifest entry） |
「对 **186 个** planned entry 全部给出拒绝原因」 | **185 个** |
「`registered_adapter_ids` 恒为空」 | 仍为空，但**根因已移位**到「capability 未翻转」 |

约束**未解除**，但供给侧与 capability 侧的解除方不同，混在一句话里会把工作派给错的人 ——
`owner_task` 已随之拆成两侧。三臂度量逻辑一字未动（159 → 221 例仍全过，`binding_constraint_id`
仍实测为 `BP-61-1`）。

### 生成器 staleness 的归因与排期（2026-09-04）

改动后两处 freshness 判据打红，逐条归因如下 —— **不整份重跑**（分工书规则 3）：

| 报告 | diff 规模 | 归因 | 处置 |
|---|---|---|---|
`workpaper_task61_word_pilot_gate_probes.json` | **+24 / -3** | **100% 我的**（`measured_2026_09_04` 块 + `owner_task` + `what` + `registry_digest`），probe 计数 41/34/26/7/75 一项未变 | ✅ 已 `--apply`，`--check` 复绿，`git diff --numstat` 自证 24/3 |
`workpaper_sync_task67_structural_pre_reconcile.json` | **602 条漂移路径** | **我的 ~140**（`database_snapshot` / `counters` / `chain_checks` / `blocking_preconditions`：bundle 5→6、artifact 14→18、entry_state 1→2、working_paper_artifact 20→27）· **并发会话 ~456**（全在 `entries[*]` 的 `rebuilt_from_source` 184 / `evidence_rerun_axes` 136 / `changed` 136；`entries_with_changed_source_digest` **48 → 184**） | ⏸ **不跑** —— 整份 `--write` 会把 456 条别人的在途漂移写进报告、替他们背书。**排期：并发会话收口后由 A 协调重跑**（规则 3：中途不跑、收口才跑） |

那 ×136 与分工书规则 3 里已实测记录的 `scenario_profile_changed`×136 是同一批，可交叉印证归因。

### 既存红（非本 spec 引入，不在 Task 9.3 范围）

`test_task61_oo94_word_pilot_gate.py::TestAdmissionIsRealReadback::test_no_f2_entry_is_admitted_today`
—— carrier 证据的 `source_commit` 记录为 `d330d7cea6bb`，现读 HEAD `aff85fb6ab5c`，
`stale_reasons` 报「source_commit 变化」⇒ `really_passed=False`。

🔴 **刻意不修**：把 commit 号往上撞而不重新取证，正是「把错值当基线锁死」（假绿第③源）。
记录如实说「证据已旧」才是对的。重新取证需要真实 OO 9.4 的 F2-22/F2-23 pilot 往返 ——
那是 Task 61 本体，被 BP-18 挡着（而 BP-18 随 Tasks 75/76 完成自动解除）。

### 变异检验（2026-09-04 首轮，覆盖本次改动的守卫）

四态判读，不以退出码代替判读；锚点命中数必须恰 1；还原后 sha256 自证。

| id | 变异 | 判读 |
|---|---|---|
M1 | `if "resolvable_for_provisioning" not in verdict:` → `if False and …` | 首轮 **GREEN**（守卫缺陷）→ 补强后 **RED** |
M2 | `verdict["resolvable_for_provisioning"]` → `verdict.get(…, True)` | **RED** |
M3 | `verdict = adjudication.get(entry_id)` → 回落 `getattr(supply, "PILOT_WP_CODES", ())` | **RED** |
M4 | `adjudication = load_wp_code_adjudication()` → `{}` | **RED** |

🔴 **M1 首轮 GREEN 是真守卫缺陷**：原判据只查「存在一个 `KEY not in verdict` 的 `Compare`
节点」，把它短路成 `False and (KEY not in verdict)` 时 Compare 仍在 ⇒ 照样绿。已改为要求
「存在一个 `ast.If`，其 test **恰为**该 Compare（不是被 `and` 包起来的子项）且 body 内含
`raise`」—— 判据从「节点存在」升级为「该比较真的门控了一个 raise」。

**两条登记为已知判据缺口（预期 GREEN，非守卫缺陷）**：

| id | 变异 | 缺口 |
|---|---|---|
M5 | 首版宿主的 `_adjudicated_wp_codes(entry_id)` → 写死 `("D2",)` | **没有任何判据盯首版宿主的目标解析** —— 现有守卫只盯 Task 76 宿主。第三份真源可以无声复活 |
M6 | 叠加层 `if field.value is None and key not in baseline.values:` → 去掉后半个条件 | **清空语义无测试覆盖**（F7 `test_projection_first_publication.py` 不存在）—— 「基线有值而 store 给 None」被静默吞掉不会被任何判据抓住 |

两条缺口都要在 Task 10.1 的九条变异里补进去，并在 F7 落对应属性测试。

### Task 6.1 已按实测修正（2026-09-04）

原实现止步 `adapter_built`，H1 / D2 双双报 `ready_to_publish` 而 `--apply` 双双失败 ——
**预演说能发、真发发不出，是假绿**。Requirement 6.2 要的「跑完全链」，后四段一段没跑。已改：

* `CHECK_STAGES` 6 → **10**，补 `projection_composed` / `materialized` / `roundtrip_verified` /
  `unmanaged_regions_verified`，与 `--apply` 走**同一条**代码路径（同一 projection 构造、同一
  `adapter.materialize`、**复用**生产的 `_assert_roundtrip_equivalent`，不抄第二份比对口径），
  仅产物落临时目录、不进事务。AST 复核 `run_check` 内 `.commit(` / `.add(` / `.flush(` /
  `register_` 出现次数 **0/0/0/0**
* `CHECK_ENTRY_STATES` 6 → **11 格**；materialize 侧取值域按 `excel_materialize.FAILURE_KINDS`
  的 10 个权威键登记，按「解除方是谁」归两格
* **删掉两处 `except → blocked_contract_not_reviewed` 兜底** —— 它把「模板漂移」与「要插行」
  双双伪装成「契约未复核」，而两份契约都是 reviewed 的。新增 `_settle_exception` 统一落格，
  未登记 error_code 落进 `blocked_unregistered_failure_shape`（语义 = 词表要扩），不再冒充已知格
* 每格带 `_STATE_UNBLOCK_OWNER` 解除方，`--json` 一并落盘

## M0 复选框对齐（2026-09-04 · A · 5 泳道分工书第 0 步）

对齐判据 = **真实执行**，不是"文件存在"。取证命令与产物：

```
python backend/scripts/fix/fix_projection_first_publication.py --check --json tmp_a_m0_check.json
python tmp_a_m0_probe_p.py        # 裁决层符号面 + 两条自检真跑 + import 期调用的 AST 定位
```

`--check` 实测结算分布 **`{blocked_missing_approved_bundle: 1, blocked_ooxml_gate: 1, ready_to_publish: 2}`**：

| entry | 结算 | 阶段 | 说明 |
|---|---|---|---|
`xlsx/gt-h1-fixed-assets` | `ready_to_publish` | 6/6 | store 载荷 0 B（合法空首版） |
`xlsx/gt-d2-accounts-receivable` | `ready_to_publish` | 6/6 | store 载荷 490,291 B |
`xlsx/b60/gt-b60-bundle` | `blocked_ooxml_gate` | 3/6 | `gate=external_relationships`，落对已知负例格 |
`xlsx/gt-g7-long-term-equity-main` | `blocked_missing_approved_bundle` | 2/6 | 判据 A 不成立，诊断指向 Task 76 宿主 |

裁决层四条独立实测：`LaneVerdict` 恰三值封闭 · `assert_registry_covers_opaque_lanes()` PASS 且
以 AST 确认它是**模块级表达式**（import 期真跑） · `assert_no_second_lane_decision_site()` PASS
（2 个合规调用模块） · 四个 entry 全判 `projection`，`opaque-<32 hex>` 判 `opaque`。

**已勾（执行验证过）**：1.1 / 1.3 / 2.1 / 4.1 / 4.3 / 6.1

**故意不勾**，理由逐条：

| 任务 | 磁盘状态 | 为什么不勾 |
|---|---|---|
4.5 `publish_first_generation` | 实现已在 F2 | `--check` 只跑到 loader+adapter，**commit 腿从未执行**。待 `--apply` 真跑后勾 |
6.3 `--apply` | 实现已在 F3（逐 entry 独立 session） | 同上，尚未真发布 |
全部 `*` 测试子任务 | **F6~F9 四个测试文件磁盘不存在** | 没有测试就没有 hypothesis 判据，勾即假绿 |
Checkpoint 3 / 5 | — | 其所在 wave 的 `*` 测试未写，"Ensure all tests pass" 无分母 |
9.x / 10.x / 11.x | F4 / F5 不存在 | 回归门与变异脚本尚未建 |

🔴 **F1 / F2 / F3 三个文件在 git 里是 `??` 未跟踪**（仅存在于工作树）。丢工作树即本 spec
地基全部蒸发。收口前按 Task 11.2 逐产物 `git add`。

## Tasks

- [x] 1. 建 lane 裁决单一真源
  - [x] 1.1 建 `LaneVerdict` 枚举、`LaneSupplyFacts` 数据类与 L1~L5 裁决 (F1)
    - 定义封闭三值枚举 `LaneVerdict{projection, opaque, undecided}` 与 frozen dataclass `LaneSupplyFacts`（四个布尔字段 + `entry_id` + `verdict`）
    - 实现 `adjudicate_lane(entry_id, *, manifest=None)`：L1 opaque entry_id 形态 → L2 manifest 归属 → L3 `DELIVERED_PER_ENTRY_CONTRACTS` 登记 → L4 `independent_entry` 且 capability 非 `unreachable` → L5 磁盘契约 `review_status == reviewed`
    - L1 **必须**排第一并在命中时立即 `return opaque`：反过来排会让 opaque entry_id 先撞 L2 的 `undecided`，L1 变成不可达分支
    - 实现 `assert_projection_lane(entry_id)`：`opaque` → `error_code=lane_is_opaque`（附命中的 `lane_id`）；`undecided` → `error_code=lane_undecided`（附首个不成立判据编号 + 该判据的真源文件路径）
    - 各真源一律现读，本模块不抄第二份：opaque 形态取自 `opaque_entry_gate.OPAQUE_AUTHORITY_LANES`、manifest 取自 `manifest_entries_by_id(load_entry_manifest())`、契约登记取自 `adapters.registry.DELIVERED_PER_ENTRY_CONTRACTS`、契约解析走 `contracts.load_contract`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x]* 1.2 属性测试：裁决的封闭性、确定性与两条终止分支 (F6)
    - **Property 1: lane 裁决三值封闭且确定**
    - **Validates: Requirements 1.1, 1.2, 1.6**
    - **Property 2: opaque 命名空间的 entry_id 恒判 opaque 且不受后续判据影响**
    - **Validates: Requirements 1.3, 1.4, 1.7**
    - **Property 3: 判据不足恒判 undecided 并点名首个不足判据与其真源**
    - **Validates: Requirements 1.5, 1.7**
    - 生成器覆盖三类 entry_id：由每条 opaque lane 的 `entry_id_source` 形态现造的、manifest 里真实存在的、两者皆不在的任意字符串
    - Property 2 的关键构造：固定一个 opaque 形态 entry_id，**同时**扰动 L2~L5 的输入（抽掉 manifest 项 / 抽掉契约登记 / 把契约 `review_status` 改非 reviewed），结论必须恒为 `opaque`
    - `hypothesis` 每条 ≥100 例

  - [x] 1.3 建与既有真源的双向锁及无第二真源守卫 (F1)
    - 实现 `assert_registry_covers_opaque_lanes()`：L1 形态表与 `OPAQUE_AUTHORITY_LANES` 逐项（`lane_id` + `entry_id_source`）交叉锁死，不一致时指出具体 `lane_id`
    - 实现 `assert_no_second_lane_decision_site()`：以 `ast` 扫 `backend/app/**` 与 `backend/scripts/**`，把「比较 authority model 取值」与「判 `opaque-` 前缀」两类语法位置报为违规（除非该位置调用本模块），返回按模块归组的合规调用点清册供 evidence 现读
    - AST 扫描**不得**用 `strip_comments` 预处理（会连带剥掉 `sa.text("""…SQL…""")`）；节点定位一律走语法树而非字符窗口
    - import 期即跑 `assert_registry_covers_opaque_lanes()`（坏表不许被加载，与 `assert_lane_self_consistent()` 同款）
    - _Requirements: 1.8, 1.9_

  - [x]* 1.4 属性测试：双向锁、无第二真源与顺序门不可交换 (F6)
    - **Property 4: L1 形态表与 opaque lane 登记双向锁**
    - **Validates: Requirements 1.8**
    - **Property 5: lane 判定没有第二真源**
    - **Validates: Requirements 1.9**
    - **Property 17: L1 的顺序门不可交换**
    - **Validates: Requirements 1.3**
    - Property 4 的构造：对两侧任一做单条增/删/改（monkeypatch 内存副本），断言 `assert_registry_covers_opaque_lanes` 失败且消息含被改动的 `lane_id`
    - Property 5 的反向自检：临时在扫描根内写一处 `entry_id.startswith("opaque-")`，断言被报违规；删掉后恢复合规（**不得**只断言当前源码合规 —— 那是空分母）
    - Property 17 的判据必须落在「打红的恰是 Property 2 那条测试」而非「有测试打红」

- [x] 2. 建供给四条独立判据
  - [x] 2.1 实现 `observe_lane_supply` 与 `describe_supply_gap` (F1)
    - 四条判据各自独立取数，来源两两不同：
      - A `projection_bundle_provisioned` ← `working_paper_sync_definition_bundle` JOIN `working_paper_sync_definition_artifact`，要求 `authority_model_type='projection_contract'` ∧ 两侧 `state='approved'` ∧ 三 slot 均 `is_definition` ∧ `logical_id` 等于该 entry 的 authority model key
      - B `published_representation_current` ← `working_paper_sync_entry_state` 按 **(wp_id, entry_id)** 取（本模块带 scope，不复制供给门那条全局 `.first()`）
      - C `representation_follows_projection_contract` ← representation `definition_bundle_id` 反查 bundle 的 `authority_model_type`
      - D `representation_contract_digest_matches` ← 磁盘契约 `canonical_sha256` 与 bundle contract slot digest 比对（跨来源，非自我比对）
    - `supply_satisfied` = A ∧ B ∧ C ∧ D，**四条全部必需**
    - `describe_supply_gap(facts)`：供给成立返回 `None`；否则返回点名首个为假判据的文本。A 真 B 假时文本**同时**点明「判据 A 已满足」与「判据 B 未满足」
    - 取数异常一律 `raise` 携 `error_code=lane_supply_observation_failed` 并记 ERROR 级 —— **禁止** `except Exception: return False`（fail-open 掩盖接线错误是本仓库最贵的一类缺陷）
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7, 2.8_

  - [x]* 2.2 属性测试：四条判据的合成语义与取数语义 (F6)
    - **Property 6: 供给成立当且仅当四条判据全为真**
    - **Validates: Requirements 2.1, 2.3, 2.4**
    - **Property 7: 「已 provision bundle」不蕴含「供给成立」**
    - **Validates: Requirements 2.5**
    - **Property 8: 判据 A 与判据 C 的取数语义互不重叠**
    - **Validates: Requirements 2.2, 2.7, 2.8**
    - Property 6 穷举 16 种布尔组合（不用随机 —— 分母有限时穷举比抽样强），断言 15 种为假的组合各自返回非空文本且点名首个为假者
    - Property 8 的判据 C 构造：造一条绑定 opaque bundle 的 current representation，断言 C 为假（这是 D2 那类情形的直接落点）

  - [x]* 2.3 属性测试：观测异常不降级为假值 (F6)
    - **Property 9: 供给观测的异常不被降级为假值**
    - **Validates: Requirements 2.6**
    - 三种致错情形各一例：表缺失、外键悬挂、session 抛错。断言抛出 `error_code=lane_supply_observation_failed` 且**不**返回四条皆假的 `LaneSupplyFacts`
    - 反向自检：把实现改成 `return False` 后本条必须打红

- [x] 3. Checkpoint - 裁决层完成
  - Ensure all tests pass, ask the user if questions arise.
  - 此时一行库都不写。用 `--check` 之前的临时探针确认：B60/D2/G7/H1 四个 entry 的 `adjudicate_lane` 全部返回 `projection`，`opaque-<uuid>` 形态返回 `opaque`。

- [x] 4. 建首版发布服务层
  - [x] 4.1 建 `FirstPublicationPlan` 与 `resolve_plan` 五条准入 (F2)
    - `FirstPublicationPlan` 为 frozen dataclass，`__post_init__` 调 `assert_no_mutation_surface`（不持 session / repository / outbox，与 `ContentCommitPlan` 同款）
    - `resolve_plan` 按固定顺序求值：① `assert_projection_lane` ② 判据 A 必须为真 ③ 判据 B 必须为 **False**（首版专用）④ bundle 三 typed slot 逐项校验 ⑤ 磁盘契约 `review_status == reviewed`
    - 每条不成立各有独立 `error_code`：`lane_undecided` / `lane_is_opaque` / `projection_bundle_not_provisioned`（诊断指向 `fix_task76_provision_projection_definitions.py`）/ `first_publication_already_done` / `contract_not_reviewed`
    - `authority_model_logical_id` 从 `DELIVERED_PER_ENTRY_CONTRACTS` **现取**，本模块不写死该字面量
    - 第 ④ 条**委派** `resolution.load_bundle_snapshot` + `ExcelEntryDefinitionLoader`，本模块不重写同一判据（重写一份的后果不是更安全，而是任一侧被短路都不改变行为 ⇒ 变异判 GREEN）
    - 任一准入不过时不写任何库行
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [x]* 4.2 属性测试：准入顺序、首版专用与拒绝码互不相同 (F7)
    - **Property 10: 首版准入按固定顺序求值并返回无写入面的冻结计划**
    - **Validates: Requirements 3.1, 3.2, 3.9**
    - **Property 11: 首版入口拒绝已有 current representation 的 entry**
    - **Validates: Requirements 3.4**
    - **Property 12: 一切拒绝形态的 error_code 两两不同并指出首个不符项**
    - **Validates: Requirements 3.5, 3.6, 7.1, 7.3, 7.5, 7.6, 7.7**
    - Property 10 的顺序判据：逐一构造「使第 k 条不成立」的输入，断言抛出的 `error_code` 恒为第 k 条那一个（不被后续判据遮蔽）—— 这条才能让顺序不可交换
    - Property 12 收集全部拒绝形态的 `error_code` 做两两不等断言（伪造供给五形态 + 占位 adapter 标识三形态 + 缺 bundle + 契约未 reviewed），并断言诊断指出首个非法 slot
    - 补单元测试：`assert_no_mutation_surface` 对塞了 session 的 plan 必须抛；`authority_model_logical_id` 与 `DELIVERED_PER_ENTRY_CONTRACTS` 现算值相等（改登记表即失败）

  - [x] 4.3 实现 `stage_instrumented_substrate` (F2)
    - 纯文件侧：权威模板字节 → `instrument_workbook_bytes(spec, gate=…)` → `validate_ooxml_artifact(path, document_type="xlsx", limits=load_limits())` → 现算 `identity_inventory` / `observed_structure` / `observed_business_sheets` / `observed_dynamic_columns`
    - **暂存期零数据库读写**（失败时库一行没动，调用方可直接报错）
    - OOXML 安全门排在产出 staged artifact **之前**：B60 的 `external_relationships` 必须在发布前以 `error_code=ooxml_security_rejected` + `gate` 名显式拒绝，而不是让 `commit` 在事务中途炸出看不出来源的错误
    - 动态列键一律 `dynamic_column_stable_keys(slot, count)`，label 只进 observed 侧、不充当键（label 撞键是本仓库已踩过的坑）
    - 临时目录跑完即删
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x]* 4.4 属性测试：暂存的实测入参、零 DB 与安全门 (F7)
    - **Property 14: substrate 暂存现算四项实测入参且动态列键不由 label 充当**
    - **Validates: Requirements 4.1, 4.6**
    - **Property 15: substrate 暂存期零数据库读写**
    - **Validates: Requirements 4.2**
    - **Property 16: 被策略拒绝的 OOXML 部件在发布前失败且不留 staged artifact**
    - **Validates: Requirements 4.3, 4.4, 4.5**
    - Property 16 三类部件各一例：注入 `xl/externalLinks/`、注入 `xl/vbaProject.bin`、注入嵌入对象。断言 `error_code=ooxml_security_rejected` + 携带 `gate` 名 + staged 目录为空
    - Property 16 必须包含 **B60 权威模板的真实字节**作为已知负例（实测 `gate=external_relationships`）
    - Property 14 的 label 判据：扰动任一表头 label，断言全部动态列键逐项不变
    - Property 15 用不可用 session 构造（`stage_*` 签名里根本不该有 session ⇒ 判据落在签名 + 行为双侧）

  - [x] 4.5 实现 `publish_first_generation`（loader → adapter → commit）(F2)
    - 链路：`ExcelEntryDefinitionLoader.load(entry_id, frozen_bundle_id, frozen_bundle_sha256, adapter_build, identity_inventory, observed_*)` → `build_excel_adapter(definitions=…, binding=…, direction="html_to_oo")` → `ContentMutationService.commit(plan=…, mutation=…, adapter=<该 adapter>)`
    - 本方法**不**降级任何判据：`commit` 的 `_assert_authority_shape` 仍要求 projection + contract + adapter 三者齐备；bundle 仍必须 approved；typed slot 仍不得是 marker
    - 本方法不 commit、不选目标底稿、不发布 definition（事务边界与目标选取属宿主脚本，与 `word_entry_gate` / `OpaqueAuthorityProvisioner.resolve` 的既有约定一致）
    - 结构守卫（在 4.6 落判据）：函数体内 `registry.register` / `PENDING_ENGINE_ADAPTERS` / `adapters/word` 零引用；不出现 `adapter=None`；不改写 `PublishedIdentityObserver`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 7.2, 7.9, 7.10_

  - [x]* 4.6 属性测试：破环点与空 adapter 必被拒 (F7)
    - **Property 18: Frozen_Definitions 的生产入参零 representation 依赖**
    - **Validates: Requirements 5.1**
    - **Property 21: 以空 adapter 提交 projection 必被拒**
    - **Validates: Requirements 5.8, 7.4**
    - Property 18 是本 spec 的**核心判据**：在库中不存在该 (wp, entry) 任何 representation 时，产出 `FrozenEntryDefinitions` 的调用仍成功；并以 AST 断言该调用的入参集合不含任何 representation 标识
    - Property 21 双侧：`commit(adapter=None)` 必抛 `ContractRequiredError`；`PublishedIdentityObserver.observe(representation=None)` 必抛 `RepresentationShapeError`（不返回 `None`、不返回空 identity）
    - 补结构守卫：`publish_first_generation` 的 `direction` 实参恒为 `"html_to_oo"`；函数体内 Word 相关路径零引用

- [x] 5. Checkpoint - 服务层完成
  - Ensure all tests pass, ask the user if questions arise.
  - 此时仍未在真实库写入任何行。

- [x] 6. 建唯一幂等宿主
  - [x] 6.1 建 `--check` 只读预演与封闭结算词表 (F3)
    - `--check` 逐 entry 跑完：`adjudicate_lane` → `observe_lane_supply` 四条判据 → 临时目录 instrument → OOXML 安全门 → loader 全部校验步骤 → `build_excel_adapter`。**一行库都不写**
    - 结算词表为封闭集 `CHECK_ENTRY_STATES = ("ready_to_publish", "blocked_missing_approved_bundle", "blocked_ooxml_gate", "blocked_contract_not_reviewed", "blocked_lane_undecided", "already_published")` —— 自由文本会让守卫只能比字符串
    - 目标清单从 `DELIVERED_PER_ENTRY_CONTRACTS` × 真实 `working_paper` **现算**，不写第二份 entry 清单
    - `TARGET_ORDER_SQL = "wi.wp_code, wp.created_at, wp.id"` 全序为每个 entry 选唯一目标底稿（与 `fix_task77_finalize_word_entry_representation.py` 同款；这解决设计文档 C8 的取值确定性）
    - 已知负例必须落对格：`xlsx/b60/gt-b60-bundle` → `blocked_ooxml_gate`（诊断写明解除条件属安全策略裁决）；`xlsx/gt-g7-long-term-equity-main` → `blocked_missing_approved_bundle`（诊断指向 Task 76 宿主）
    - 提供 `--json` 把结算快照落盘（脚本内 `Path.write_text(encoding="utf-8")`，**不**用 PowerShell 重定向 —— 会把中文腌成乱码）
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.9, 6.10_

  - [x]* 6.2 属性测试：只读性、封闭词表与目标选取确定性 (F7)
    - **Property 22: `--check` 只读且跑完全链**
    - **Validates: Requirements 6.2**
    - **Property 23: 逐 entry 结算落在封闭词表内**
    - **Validates: Requirements 6.3**
    - **Property 24: 目标选取在固定库状态下确定**
    - **Validates: Requirements 6.5**
    - Property 22 判据落在「执行前后逐表快照逐行相等」+「六个链路阶段各留下一条真实执行痕迹」双侧 —— 只断言只读会让「什么都没跑」也通过
    - Property 24 的构造：以不同插入顺序造出等价的目标行集合，断言选出的 (project_id, wp_id) 相同
    - 补结构守卫：`--check` 的 AST 里对写入面（`session.add` / `INSERT` / `UPDATE` / `repository.register_*`）零引用

  - [x] 6.3 建 `--apply` 逐 entry 独立事务 (F3)
    - `--apply` 只对 `--check` 结算为 `ready_to_publish` 的 entry 发布首版；逐 (wp_id, entry_id) **独立事务**
    - 单 entry 失败只回滚它自己、继续后续 entry，最终以非零退出码报 ERROR —— **不**降级成「本项目无此数据」
    - 幂等：对已发布首版的 entry 结算为 `already_published`，不产生第二份供给
    - 事务边界**不得**共用一个 `engine.begin()`（一处失败全部回滚是本仓库已踩过的坑）
    - 破坏性运行前设 `$env:PYTHONIOENCODING='utf-8'`；判成败一律查数据不看退出码（被 `^C` 中断的运行可能已提交部分变更）
    - _Requirements: 6.6, 6.7, 6.8, 6.11_

  - [x]* 6.4 属性测试：事务隔离与幂等 (F7)
    - **Property 25: 每 entry 独立事务，单点失败只回滚自身并以非零退出码报错**
    - **Validates: Requirements 6.6, 6.7, 6.11**
    - **Property 26: 重跑 `--apply` 幂等，不产生第二份供给**
    - **Validates: Requirements 6.8**
    - Property 25 的构造：对 N 个目标注入第 k 个失败，断言前 k-1 个的落库结果不变、后 N-k 个仍被处理、退出码非零
    - Property 26 判据落在「行数与 digest 逐项不变」而非「没报错」

- [x] 7. 真实 PG 上的首版落成验证
  - [x] 7.1 建真实 PG 临时 schema 夹具 (F8)
    - 真实 PostgreSQL 上 `CREATE SCHEMA` → 跑迁移 → 发布 → 断言 → `DROP SCHEMA`；DB 非 PostgreSQL 时**不 skip**，直接 fail（判据是「真库上真的成了」）
    - 三坑逐条落实：① timestamptz 一律在 **Python 侧**转 `datetime`（SQL 层 `CAST(:x AS timestamptz)` 无效，asyncpg 发送前就按目标类型编码）② 复原每步用独立事务边界（不共用一个 `engine.begin()`）③ 判成败查数据不看退出码
    - 连库快照用**一次** `asyncio.run` 取全部（每测试各自 async 会污染共享连接池，第二个起 `NoneType has no attribute send`）
    - 目标顺序按 design.md §首版目标选取：先 `xlsx/gt-h1-fixed-assets`（最干净），再 `xlsx/gt-d2-accounts-receivable`（判据 C 的活证人 —— 该 wp 已有 opaque representation）
    - 若 H1 卡在 loader 某一步而 D2 通得过，对调顺序并把实测原因记入 evidence（design.md §Open Gates 第 3 项）
    - 🔴 **2026-09-03 Gate 3 裁决已落：首版目标顺序 H1 → D2 维持不变**，且已在**真库只读**上把 `loader.load()` 完整九步跑通（H1 bundle `e21fb645` approved / digest `05086f4021a6` / contract `h1.disposal_check` / `projection_contract` / structure 25；D2 bundle `d443feca` / `db877e9dbc73` / `d2.receivable_detail` / structure 39）。H1 的 bundle digest 与 Task 44 门禁报的 `bundle=05086f4021a6` 逐字一致（两条独立路径互证）。H1 动态列 **0** 项（G7 为 `minority_financials: 10`），故 H1 确为最干净首版。⇒ 本任务**不需要**再为「H1 是否可行」留退路分支；若实施中 H1 反而失败，那是回归而非未知，必须定位原因不得直接对调顺序。
    - _Requirements: 11.1, 11.5, 11.6_

  - [x]* 7.2 属性测试：落库字段一致、事务形状与失败无残留 (F8)
    - **Property 13: 任一阶段失败时数据库四处逐行不变**
    - **Validates: Requirements 3.8, 5.7**
    - **Property 19: 落库 representation 的七个冻结字段与计划及实测值逐项相等**
    - **Validates: Requirements 5.4**
    - **Property 20: 首版发布恰好一次 revision 推进、一组单行产出与一次 commit**
    - **Validates: Requirements 5.5, 5.6**
    - Property 19 的七字段：`definition_bundle_id` / `definition_bundle_sha256` / `authority_model_definition_id` / `adapter_id` / `adapter_build_digest` / `structure_hash` / `identity_inventory_sha256`。期望值从 plan 与 staged 实测**现取**，不写死字面量
    - Property 20 的 commit 计数取自 `_CommitLatch` 的既有见证，不另装计数器
    - Property 13 在三个阶段各注入一次失败，逐表快照比对

  - [x]* 7.3 属性测试：判定取自数据、时间戳往返与复原事务边界 (F8)
    - **Property 33: 成败判定取自数据库数据而非进程退出码**
    - **Validates: Requirements 11.2**
    - **Property 34: 带时区时间戳在 Python 侧编码后可往返**
    - **Validates: Requirements 11.3**
    - **Property 35: 复原流程每步独立事务，先前成功步骤不被撤销**
    - **Validates: Requirements 11.4**
    - Property 33 构造两种不一致：「已提交但退出码非零」与「未提交但退出码为零」，断言判定由数据库最终状态唯一决定
    - Property 34 用 `hypothesis` 的 `datetimes(timezones=…)` 生成器，往返后比时间点相等（不比字符串表示）
    - Property 35 在多步复原序列中注入失败，断言先前成功步骤的写入保留

- [x] 8. Checkpoint - 首版已在真实库落成
  - Ensure all tests pass, ask the user if questions arise.
  - 此时应能用 PG 只读查到：至少一条 representation 绑定的 bundle 的 `authority_model_type='projection_contract'`，且其 `entry_id` 是 manifest entry（非 `opaque-` 命名空间）。

- [x] 9. 回归判据接线与过期登记更正
  - [x] 9.1 建 `check_projection_lane_adjudication.py` 回归门 (F4)
    - 复用既有门读数，**不另造**：R1 直接消费 `check_task44_oo94_excel_pilot_gate.py` 的输出（`adapter_registered` / `capability_enabled` / 四态分布），R2 走 PG 只读现查
    - R2 的判据：至少一条 representation 绑定 `projection_contract` bundle；并把「upgrade candidate 表可能有行」表述为首版落成**之后**的结果，**不**作为前置条件
    - 落 candidate 结构依据：断言 `working_paper_representation_upgrade_candidate.source_representation_id` 为 NOT NULL 外键 —— 这是「candidate 路径产不出首版」的结构证据（design.md C1）
    - 落范围边界的结构缺席判据：本 spec 交付物中不含 Task 74 的 writer 迁移改动、不含 `multi_resolver` 改动、不含 `allow_external_relationships` 变更、不含供给门/pilot attach 的 scope 参数、不含新增 `backend/migrations/V*.sql`
    - 落 capability 变更纪律判据：若 manifest capability 出现 `bidirectional`，则 overlay 必须已 reviewed 且 `approved_source_digest` 复核门未被绕过
    - `--json` 落盘新基线并记录与旧基线的差集（`failed` 计数不得因本 spec 交付而增加）
    - 🔴 **2026-09-03 Open Gates 裁决已落：R1 按 Requirement 12.6 拆两阶段**（Gate 1 实测门确实拒绝，`--check` 退出码 2，approved `b0fd31f17739…` vs current `d9fddb64a7b3…`，且 current 随宿主 `.vue` 编辑漂移 —— BP-67-1 登记时为 `5756356a0ac9…`）。
      **阶段一（本 spec 交付）**：只证「供给门放行」—— `_describe_entry_supply` 对该 entry 返回 `None`。判据落在供给门返回值上，**不**落在 `adapter_registered`。
      **阶段二（本 spec 不做，另立）**：capability 翻转致 `adapter_registered` False→True。它需要 manifest 重生成，而更新 `approved_source_digest` 须人工复核 mount diff（owner = Task 67 登记的「1/67 复核方」），且宿主稳定前不宜复核。
      ⇒ 本门**不得**把 `adapter_registered=True` 写成阶段一的通过条件（那会让本 spec 永远无法收口，或诱导去绕 `approved_source_digest` 复核门 —— 后者已被 Requirement 7.8 明令禁止）。Gate 2 实测**成立**（四个 pilot entry 与源文件严格 1:1，单文件 glob 即逐 entry 精确，`capability` 可覆盖，无需扩 schema），故阶段二在表达上没有障碍，只被 Gate 1 卡在后面。
    - _Requirements: 8.1, 8.4, 8.5, 8.8, 9.3, 9.4, 12.1, 12.2, 12.3, 12.4, 12.5, 7.8_

  - [x]* 9.2 属性测试：供给门放行与注册会计恒等式 (F9)
    - **Property 27: 首版落成且 capability 裁决后供给门放行且注册集合含该 entry**
    - **Validates: Requirements 8.2**
    - **Property 28: 注册会计恒等式在任何供给状态下成立**
    - **Validates: Requirements 8.3**
    - Property 27 是**非空跑证明**（避免「供给为 0 所以注册 0」的重言式）：在临时 schema 上落成首版 + 以内存 manifest 把该 entry 的 capability 置为 `bidirectional`（`build_production_registry(manifest=…)` 本就支持传入 manifest），断言 `_describe_entry_supply` 返回 `None` 且 `register_from_manifest` 的 `registered_adapter_ids` 含该 entry 的 `contract_id`
    - 注册必须由**生产** `attach_pilot_adapters` 完成（其返回值就是证据），不得由测试自己组装后再数 registry
    - Property 28 穷举多种供给状态（0 供给 / 1 供给 / 供给但 capability 未开），断言 `len(registered_entry_ids) + unregistered_entry_count == planned_entry_count`

  - [x] 9.3 更正 BP-61-1 判据字面量 (F11)
    - 把 `BINDING_CONSTRAINTS` 中 `BP-61-1.what` 的「`working_paper_sync_entry_state` 全表 0 行」改为「不存在任何 **manifest entry** 的 current published representation」—— 实测该表现有 1 行但那 1 行是 `opaque-…` 命名空间，旧字面量已成假话
    - 判据实现改为按 manifest entry_id 集合过滤 entry pointer，而不是数全表行数
    - `owner_task` 与 `unblocks` 字段随之更新：owner 指向本 spec，`unblocks` 保持「Task 61 正文第一句的准入条件」
    - **不动** arm_a / arm_b / arm_c 三臂度量逻辑：绑定约束的先后关系继续由实测得出，而不由写死字面量得出（该门自己已写明「arm_b 原因不再逐字相等时拒绝沿用旧裁决」）
    - 只改本 spec 归属的字节区间；同文件其他 constraint 一律不动（归因型验收，不用全局等值型 —— 并发会话可能同时改同一文件）
    - _Requirements: 8.6, 8.7_

  - [x]* 9.4 属性测试：绑定约束由三臂实测得出 (F9)
    - **Property 29: BP-61-1 的绑定约束先后由三臂实测得出**
    - **Validates: Requirements 8.7**
    - 构造两种供给状态（无 manifest entry representation / 有），断言 `binding_constraint_facts(arms)` 的 `binding_constraint_id` 随实测改变而改变
    - 反向自检：把三臂之一改成恒定返回后本条必须打红
    - 归因型验收：断言本次改动只落在 `BP-61-1` 的字节区间内，`BP-61-2` / `BP-61-3` 的取值逐字不变

  - [x] 9.5 更正 `ENTRY_ID_NAMESPACE_SPLIT_NOTE` 过期读数 (F10)
    - `measured_migration_cost_at_task65` 现记三表均 0 行，实测为 `working_paper_content_version=1` / `working_paper_content_representation=1` / `working_paper_content_application=0` —— 更正为实测值并加注更正时点
    - `adjudication_owner_task` 保持 `"67"`，**不**合并 opaque lane 内部的 entry_id 命名空间分叉（那是 Task 67 的范围）
    - 加一条注解说明本登记表裁决的是 opaque lane **内部**的 `wp_code` / `wp_id` / `wp_code_with_sheet` 三种口径，**不涉及** projection vs opaque（后者归本 spec 的 Lane_Registry）
    - _Requirements: 9.1, 9.2_

  - [x]* 9.6 属性测试：登记读数与真库双向一致 (F9)
    - **Property 30: 登记读数与真实库行数双向一致**
    - **Validates: Requirements 9.1**
    - 判据两侧：登记表读数 == 真库现查行数。任一侧改变而另一侧未更新时打红
    - 反向自检：把登记读数改回 0 后本条必须打红（**不得**把错值当基线锁死 —— 那是假绿第③源）

- [x] 10. 变异检验
  - [x] 10.1 建 `mutate_projection_first_publication_guards.py` (F5)
    - 九条变异各带 `id` / `path` / `anchor` / `new` / `want`（预期打红的**具体测试**）/ `why`（它守的假绿形态）：
      1. `adjudicate_lane` 的 L1 分支移到 L2 之后 → 守「opaque entry 恒 undecided」的顺序门
      2. `supply_satisfied` 改成只读判据 A → 守「四条判据合成一条」
      3. `observe_lane_supply` 的 `raise` 改成 `return False` → 守 fail-open 掩盖接线错误
      4. `resolve_plan` 第 ③ 条的期望值取反 → 守「首版入口被拿去覆盖既有 representation」
      5. 删掉 `validate_ooxml_artifact` 调用 → 守 B60 的 `external_relationships` 静默通过
      6. `commit(adapter=<adapter>)` 改成 `adapter=None` → 守绕开 `_assert_authority_shape`
      7. 新写一处 `entry_id.startswith("opaque-")` 判定 → 守第二真源
      8. `--apply` 的每 entry 独立事务改成共用一个 `engine.begin()` → 守「一处失败全部回滚」
      9. 宿主里 `await service.publish_first_generation(...)` 改成只取引用不调用 → 守 additive 死代码（假绿第①源）
    - 四态判读 RED / GREEN / ANCHOR-MISS / WRONG-TEST，**不以退出码代替判读**；WRONG-TEST 需比对失败测试名差集而非只看有无失败
    - 锚点命中次数必须恰为 1（≠1 即 ANCHOR-MISS 并报告实际次数）；锚点不含 `\n`（CRLF 下跨行锚点必 MISS）；CRLF 归一后再匹配；还原后 sha256 自证
    - 提供 `--check-anchors` 只读入口（秒级，用于核对「已归档 spec 是否还可复现」）
    - 加「passed < N 即中止」自检；测试调用走 `subprocess.run([...])` **不经 shell**（`-k "a or b"` 经 shell 会被拆成多个位置参数）
    - _Requirements: 10.1, 10.4, 10.5, 10.6_

  - [x]* 10.2 属性测试：四态判读与函数体截取 (F9)
    - **Property 31: 变异结果按四态判读，锚点命中数不等于一即 ANCHOR-MISS**
    - **Validates: Requirements 10.2, 10.3**
    - **Property 32: 守卫脚本对任意签名与内嵌 SQL 均正确截取函数体**
    - **Validates: Requirements 10.7, 10.8**
    - Property 31 的构造：喂入命中 0 次 / 1 次 / 2 次的锚点各一例，断言判读分别为 ANCHOR-MISS / 可判 / ANCHOR-MISS
    - Property 32 生成器覆盖：多行签名、带 `-> Mapping[str, Any]` 返回注解、体内含三引号 SQL 文本块。断言截取起止与 `ast` 给出的一致，且 SQL 块不被注释剥离逻辑移除

  - [x] 10.3 执行全部变异并把非 RED 判读修到 RED (F5 与各守卫)
    - 逐条执行九条变异，记录四态判读结果
    - GREEN → 守卫有缺陷，补强守卫（**不是**代码没问题）
    - ANCHOR-MISS → 脚本缺陷，重指锚点
    - WRONG-TEST → 锚点错行或污染残留，定位并修正
    - 全部收敛为 RED 后把结果落 `--json`，作为收口证据
    - _Requirements: 10.1, 10.2, 10.3, 10.5_

- [x] 11. CI 接线与收口
  - [x] 11.1 把回归门与锚点自检挂进 CI (F12)
    - 在 `.github/workflows/governance-checks.yml` **追加**（`fs_append`，不改既有 job）两个 job：`check_projection_lane_adjudication.py` 与 `mutate_projection_first_publication_guards.py --check-anchors`
    - 验收用**归因型**判据（变动是否落在本 spec 追加的字节区间内），**不用**全局等值型（「其他 job 一个都没变」在并发多会话下必假红）
    - 挂 job 前先 `git status --porcelain` 确认被引用的脚本已入库 —— 干净 checkout 下文件不存在会让 job 必挂
    - _Requirements: 8.1, 8.8_

  - [x] 11.2 逐产物核对 git 跟踪状态并清理临时产物
    - 对 F1~F12 逐个 `git status --porcelain -- <path>`，见到 `??` 即 `git add`（「spec 全绿 ≠ 产物已入库」是本仓库反复出现的问题；本 spec 目录自身也必须入库，否则丢工作树即全部蒸发）
    - 清理本次会话产生的 `tmp_*` 与 `_wip_*` 诊断产物（`.gitignore` 已收这两类前缀；按 mtime 判归属，并发会话在用的不动）
    - 记录三门新基线（R1/R2/R3）与九条变异判读结果，供后续复盘现读
    - _Requirements: 11.7, 12.6, 12.7_

- [x] 12. Final checkpoint - 全部判据收敛
  - Ensure all tests pass, ask the user if questions arise.
  - 收口核对：① 至少一个 manifest entry 有 current published representation 且其 bundle 为 `projection_contract` ② `--check` 对 B60/G7 落在对应 blocked 格（负例证明判据在跑）③ 九条变异全 RED ④ 三门新基线已记录且 `failed` 未增 ⑤ F1~F12 全部已入库。

## Notes

- 标 `*` 的子任务为测试任务，可为快速 MVP 跳过；顶层任务不标 `*`。
- 每条属性测试用 `hypothesis`，`max_examples` ≥100，并以 `**Feature: published-representation-production-path-and-lane-adjudication, Property N: <标题>**` 标签回指 design.md。
- **每写完一条守卫必做变异检验**（改一字看是否变红）。没打红 = 守卫有缺陷，不是代码没问题。
- 判据一律落在行为 / 结构 / 真实执行，**不得**落在「字符串是否存在」。
- 判磁盘一律 `python -c "open(p,encoding='utf-8').read()"`（读文件工具对刚改的文件可能返回陈旧版本）。
- 命令用 `;` 分隔、`cwd` 参数代替 `cd`；pytest 从仓库根跑，按对本 spec 交付物的实际引用关系确定辐射面，**不跑全量** `backend/tests`（1522 个文件）。
- design.md §Open Gates 的三项在实施中确认：manifest 能否重生成（BP-67-1）、overlay 是否支持逐 entry capability 覆盖、H1 的 instrumented 字节能否通过 loader 全部步骤。任一不成立即按该节的应对调整，**不绕开**。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 0,
      "name": "裁决层骨架",
      "tasks": ["1", "1.1"],
      "depends_on": [],
      "rationale": "lane 裁决是后续一切判据的地基：不先有单一真源，供给观测与发布准入都无从判断某个 entry 该走哪条路。L1~L5 顺序不可交换，故先立枚举与裁决本体"
    },
    {
      "wave": 1,
      "name": "裁决层守卫与双向锁",
      "tasks": ["1.2", "1.3", "1.4"],
      "depends_on": [0],
      "rationale": "与既有真源的双向锁、无第二真源守卫必须紧跟裁决本体落地，否则「各处按形态自行猜测」会继续新增。属性测试同波，防裁决被写成开放枚举"
    },
    {
      "wave": 2,
      "name": "供给四条独立判据",
      "tasks": ["2", "2.1"],
      "depends_on": [1],
      "rationale": "供给观测要调裁决层，故依赖 Wave 1。四条判据 A/B/C/D 必须各自独立取数，任一侧走短路时守卫都能打红 —— 合成一条会互相遮蔽"
    },
    {
      "wave": 3,
      "name": "供给属性测试与裁决层 Checkpoint",
      "tasks": ["2.2", "2.3", "3"],
      "depends_on": [2],
      "rationale": "观测异常不得降级为假值（否则「取不到」被伪装成「本来就没有」）。Checkpoint 3 是裁决层完成闸门，不通过不进服务层"
    },
    {
      "wave": 4,
      "name": "首版发布准入",
      "tasks": ["4", "4.1"],
      "depends_on": [3],
      "rationale": "五条准入要用裁决与供给的结论，故依赖裁决层已收口。准入顺序与拒绝码互不相同，是「为什么发不出去」可解释的前提"
    },
    {
      "wave": 5,
      "name": "instrumented substrate 暂存",
      "tasks": ["4.2", "4.3"],
      "depends_on": [4],
      "rationale": "暂存必须零 DB、零发布副作用：先证明能产出合规 substrate，再谈发布。安全门在此把住，避免把不合规产物带进发布链"
    },
    {
      "wave": 6,
      "name": "首版 representation 发布",
      "tasks": ["4.4", "4.5"],
      "depends_on": [5],
      "rationale": "发布是 loader → adapter → commit 三段；loader 的零 representation 依赖是破环点，没有它首版永远发不出第一份"
    },
    {
      "wave": 7,
      "name": "破环点验证与服务层 Checkpoint",
      "tasks": ["4.6", "5"],
      "depends_on": [6],
      "rationale": "破环点与空 adapter 必须拒的两条属性测试，是「首版发布不是靠伪造供给绕过去」的证明。Checkpoint 5 是服务层完成闸门"
    },
    {
      "wave": 8,
      "name": "唯一幂等宿主 --check",
      "tasks": ["6", "6.1"],
      "depends_on": [7],
      "rationale": "宿主先只做可预演的 --check：在任何写入之前，把「哪些 entry 能发、哪些被哪一条准入挡住」变成可读结论"
    },
    {
      "wave": 9,
      "name": "宿主 --apply 与逐 entry 独立事务",
      "tasks": ["6.2", "6.3"],
      "depends_on": [8],
      "rationale": "--apply 必须逐 entry 独立事务：一个 entry 失败不得回滚已成功的其它 entry（`engine.begin()` 内一处失败全部回滚是实测踩过的坑）"
    },
    {
      "wave": 10,
      "name": "幂等与真实 PG 落成",
      "tasks": ["6.4", "7", "7.1"],
      "depends_on": [9],
      "rationale": "幂等要在真实库上验（重跑无新增），故与真实 PG 夹具同波。临时 schema 夹具让验证不污染主库"
    },
    {
      "wave": 11,
      "name": "PG 落库判据与首版 Checkpoint",
      "tasks": ["7.2", "7.3", "8"],
      "depends_on": [10],
      "rationale": "判定必须取自数据而非 exit code（被 Ctrl+C 中断的运行可能已提交部分变更）。timestamptz 往返与复原事务边界是实测踩过的两个坑。Checkpoint 8 = 首版已在真实库落成"
    },
    {
      "wave": 12,
      "name": "回归判据接线与过期登记更正",
      "tasks": ["9", "9.1", "9.3", "9.5"],
      "depends_on": [11],
      "rationale": "回归门要能引用真实已发布的首版，故依赖 Wave 11。BP-61-1 与命名空间拆分说明的读数已过期，与接线同波更正，避免判据锁死错值"
    },
    {
      "wave": 13,
      "name": "回归属性测试",
      "tasks": ["9.2", "9.4", "9.6"],
      "depends_on": [12],
      "rationale": "供给门放行与注册会读恒等式、绑定约束由三肢实测得出、登记读数与真库双向一致 —— 三条都是「判据不是抄来的」的证明"
    },
    {
      "wave": 14,
      "name": "变异检验",
      "tasks": ["10", "10.1", "10.2", "10.3"],
      "depends_on": [13],
      "rationale": "变异要在全部守卫到位后做。四态判读（RED / GREEN / ANCHOR-MISS / WRONG-TEST）与函数体截取必须括号配对，不能用固定字符窗口"
    },
    {
      "wave": 15,
      "name": "CI 接线与收口",
      "tasks": ["11", "11.1", "11.2", "12"],
      "depends_on": [14],
      "rationale": "挂 CI 的前提是判据已全 RED 验证过；逐产物核对 git 跟踪状态防「spec 全绿 ≠ 产物已入库」。Checkpoint 12 是全部判据收敛闸门"
    }
  ]
}
```
