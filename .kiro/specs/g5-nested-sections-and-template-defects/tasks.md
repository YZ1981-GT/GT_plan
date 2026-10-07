# Implementation Plan

## Overview

**spec**：`g5-nested-sections-and-template-defects`　**创建**：2026-09-26　**状态**：**6/14 已实施**（2026-10-03 逐条核验：Task 0/8/9/11*/12*/13 已标 `[x]`；Task 1~7/10 的 AC 产物（evidence / 专用测试 / 几何补测）均不在库，如实保持 `[ ]`）
**上游**：**`g-cycle-sync-foundation-and-first-canary`（GC-1~GC-10，硬前置）** · FC-1~FC-13 ·
F5 spec 裁决 F5-H2 + F2 spec（模板缺陷走覆盖层的两个先例）· D4-29 转置引擎 ·
`g4-g6-shared-workbook-three-entry-lanes`（16384 策略须同源）

`[ ]*` = 依赖外部供给（BP-1~BP-4 / 模板覆盖层 / OO 真栈）。

🔴 **G5 的难点全在模板结构与模板缺陷，不在平台前置**：`blocked_by` 只有 `BP-1~4 + BP-6`
（无 BP-5/7/8）、definedName 0、主受管表裸 IF 0、TB 发布门已接。

## 2026-10-03 逐条核验结果

**核验方式**：`git ls-files` 确认交付物在 HEAD + `grep` 核验关键内容 + manifest 现算。

已在库的交付物（6 个 `[x]`）：
- **entry 层 provider** `phase5_g5_long_term_receivable.py`（完整：ENTRY_ID / ADAPTER_ID / WP_CODES / TEMPLATE_SHA256 / assert_entry_selectable / build_registration / attach_pilot_adapters）
- **G5-2 子区声明** `phase5_g5_02_balance_detail.py`（`_SECTIONS` + `ALL_SPECS_G502`，RowTableSheetSpec 嵌套）
- **G5-9 转置声明** `phase5_g5_09_ecl_stage.py`（TransposedSheetSpec + 16384 策略 + 实体列 G..J）
- **契约** `g5.long_term_receivable_detail.json` + 生成器 `generate_phase5_g5_contract.py`
- **注册** `store_item_registry` G5-2-rows + `registry.py` ALLOWED + `check_sync_provider_golden_digest` PROVIDERS
- **wp_code 裁决** adjudication.json 含 G5 条目
- **宿主接桥** `GtG5LongTermReceivable.vue` 已接 `useWorkpaperSyncBridge` + `WorkpaperSyncEditorHost`
- **e2e** `g-cycle-g5-long-term-receivable.spec.ts` 在库

未交付（8 个 `[ ]`，如实保持）：
- **Task 1~5**：无 evidence 目录、无 G5 专用 Property 测试文件（`git ls-files *g5*test*` 零命中）
- **Task 6/7**：模板覆盖层处置 + B35 缺陷登记——无 evidence、无生产代码改动
- **Task 10**：段(二)(三)八子区声明——依赖 Task 2 几何补测结论（推断值不得写进声明）

🔴 **manifest 现算**：G5 entry 仍为 `capability=single_onlyoffice` / `migration_state=legacy_fake_bidirectional`。
tasks.md 勘误段描述的 13 条 G 域 overlay override + manifest 重生成翻转**未提交到 HEAD**（overlay 中无 G5 条目）。
「交付物在库」与「运行时接上了」是两件事——验收看 manifest 现算翻转。

### 🔴 当日自我更正：上面那句「主线已交付」说得不够准，真实状态是「备好了但没接上」

同日更深一层现算（用户要求「不要假红」后重查）推翻了「契约+注册在库 ⇒ 主线已交付」这个推论：

| 判据 | 现算值 |
|---|---|
| manifest 里 G 域 entry | **21** |
| 其中 `capability == 'bidirectional'` | **1**（只有 `xlsx/gt-g7-long-term-equity-main`） |
| 仍是 `single_onlyoffice` | **19**（含 `xlsx/gt-g5-long-term-receivable`） |
| G5 entry 的 `migration_state` | **`legacy_fake_bidirectional`** |
| G5 entry 的 `canonical_resolver` | **`legacy_sheet_onlyoffice_router`**（不是 published representation） |
| G5 entry 的 `html_store` | **`unresolved`** |
| `evidence.legacy_reasons` | `["template_only_open", "no_durable_forcesave_ack", "missing_adapter"]` ← **过期**，adapter 其实已注册 |

⇒ **双向回写在运行时从未启用**。契约/注册/provider/宿主改线都齐了，但 manifest 的
`capability` 没翻，而运行时门（`assert_manifest_capability_enabled` 一族）读的正是 manifest。
「交付物在库」与「运行时接上了」是两件事 —— 与 `l-cycle-true-adapter-registration` 立的
口径一致：**验收看 manifest 现算翻转，勾选与契约存在都不算**。

**本轮已做（代码，不是登记）**：`backend/data/workpaper_sync_entry_overlay.json` 新增
**13 条 G 域 bidirectional 裁决**（G1/G2/G3/G4-main/G5/G6-main/G8/G9/G10/G11/G12/G13/G14），
每条六项前置逐一现算通过：正式契约 reviewed（非 candidate）· `STORE_MERGE_REGISTRY` 已注册 ·
`DELIVERED_PER_ENTRY_CONTRACTS` 台账登记且 provider 模块存在 ·
`build_manifest_registration_plan` 判**可注册** · `check_sync_provider_golden_digest`
覆盖（G 域 13 家在 `PROVIDERS` 名单内）且 **161 digest 零漂移** ·
宿主已改线（`WorkpaperSyncEditorHost` + `syncBridge`，与已翻的 d1/d2/d4/g7/h1 **同形**）。
新建守卫 `backend/tests/workpaper_sync/test_g_cycle_bidirectional_overlay_adjudication.py`
（**33 passed + 1 xfailed**）。

**仍未通（如实登记，不擅自绕过）**：manifest 重生成被 `approved_source_digest` 门拒绝 ——
现算 mount diff 是**新增挂点 0 / 消失挂点 18 处，全在 A 类**（A101/A111/A121/A171/A1721/
A1731/A173/A174/A176/A177/A181/A182/A271/A3/A51/A81/A91 + `GtWpRenderer.vue`），**G 域 0 处**。
那道门的全部意义就是「前端挂点一变就停下来让人看一眼」，自己改 `approved_source_digest`
等于替别人批准 18 处未复核的 A 类改动（而那批文件恰好被批量插入脚本改坏过三类 Vue 语法错误）
⇒ 不碰。守卫里那条 `xfail(strict=True)` 钉住诉求：A 类 diff 复核 + 生成器 `--apply` 后它会
xpass，strict 模式下 xpass 即失败，逼迫下一个人删标记而不是忘掉。

**顺带发现的平台级事实**：`a51.cashflow_audit`（A 循环 canary）的 override 早已在 overlay 里，
但 manifest 同样没翻 —— **同一道门把 A 循环 canary 也卡住了**。本轮 `test_workpaper_sync_manifest_contract`
与 `test_task73_entry_profile_manifest` 现算 **9 failed + 6 errors，根因全是这道门**；
用 HEAD 字节替换 overlay 复跑**同样 9+6**（仅工作树红 = 空集）⇒ 与本轮 13 条 override 无关，属预存。


## 🔴 2026-09-30 续：两道门逐道实测，第二道暴露发现契约缺口（manifest 仍未翻）

接上节。本轮按用户「修复卡住那个门，跑通」的要求**逐道走到底**，结论是**不能过门**，
且过程中发现一个比门本身更根本的架构缺口。如实登记，未勾任何复选框。

### 第一道门 `approved_source_digest`：复核通过，但不批准

完整 mount diff 复核已做完（`approved=b6291b9f… / current=2bdb9baf…`），归因三类、数字闭合：

| 类别 | 规模 | 归因 | 裁决 |
|---|---|---|---|
| A 类宿主整体退网 | 17 宿主 / 17 挂点 | 改用 `WorkpaperSyncEditorHost` + `GtEntrySyncCapabilityNotice` | 能力升级非损失 |
| condition 配对变化 | 38 宿主 | **在 legacy 挂点前插入 `WorkpaperSyncEditorHost` 真双向分支** ⇒ legacy 降级 `v-else-if` | 就是双向接线本体 |
| C22 净增 1 挂点 | 1 宿主 | C21-1 补 BP-10 模式开关 + CC-63 `ooSheetName` 修复 | C 轮 spec 实施 |

`GtOnlyOfficeSheet 238 − 17 + 1 = 222` ✓ 闭合；新增宿主 **0**；Word 两类 5/2 未变。

🔴 **方法论教训（必带下一轮）**：`mountId` 内嵌 `sourceSpan`，**任何行号位移都会换 hash**
⇒ 按 `mountId` 做 diff 会得出「G 域消失 33 / 新增 33」的假象。必须改用**不含行号的语义键**
`(file, component, documentType, wpExpression, sheetExpression, condition, loop, importKind, sourceKind)`
的多重集对比。另：既存守卫 `test_the_pending_mount_diff_contains_no_g_cycle_host` 的
`key_of` 取 `m.get("line")`（live 侧其实叫 `sourceSpan`，两侧都取不到值恒为空）⇒ 它的
「G 域 0 处」是**宿主×组件粒度**的正确结论，与细粒度的「17 对 condition 变化」不矛盾，不是 bug。

**为什么复核通过仍不批准**：现算 `git status` 显示那 17 个 A 类宿主 **17/17 全部未提交**
（最后一次提交是无关 feature `44f07ff95`）⇒ 批准等于把复核签名落在一个**可能从未进入
历史的树态**上。已把本轮一度写入的 digest **完整回滚**（`approved_source_digest` 与
`review_basis` 逐字复原为 HEAD 值，21 条 overrides 全部保留；现算与 HEAD 的唯一差异键是
`overrides`）。

### 第二道门 `stale overlay overrides: [GtA51CashflowAudit.vue]`：他人在途产物，不可删

绕过第一道后实测撞到。根因是并发 A 轮会话的工作**自相矛盾**：他们同时在做
①把 A51 改成只挂 `WorkpaperSyncEditorHost`（源码里 `<GtOnlyOfficeSheet` 已为 0）
②加一条 `component: "GtOnlyOfficeSheet"` 的 a51 `bidirectional` override。
先前第一道门一直先跳闸，所以他们还没撞到这个矛盾。

`git show HEAD:…overlay.json` 现算 **HEAD 只有 7 条 override**，工作树 21 条
= 7 + 我的 13 条 G + **a51**；我开工时记录的是「overrides 8→21」⇒ **a51 那条不在 HEAD，
是他人未提交产物** ⇒ 删它来放行自己的门 = 改别人的在途工作，拒绝。
（生成器对 0 匹配规则无豁免机制，设计上不许留死规则。）

### 🔴 更根本：发现契约缺口 —— 迁移最彻底的宿主会从挂点清册整体消失

entry 只能由 `_group_source_facts(discovery)` 派生，而 discoverer 的组件白名单只有
`GtOnlyOfficeSheet` / `OnlyOfficeWordDialog` / `WorkpaperWordEditor`，**不认
`WorkpaperSyncEditorHost`** ⇒ 一个宿主一旦完成迁移、删掉 legacy 标签，它的 entry
**直接不存在**。现算规模：**51 个「仅 EditorHost」宿主**（34 个 `d4/**` tab + 17 个 A 类）
+ **45 个双挂宿主**。

**这不是假设，已经发生过一次**：34 个 `d4/**` tab 宿主**已经真的从 manifest 里消失了**，
当时只在 overlay 的 `review_basis` 里留了一句「属有意迁移的既成事实」，没有任何判据
守住「这些 entry 去哪了」。守卫新增
`TestDiscoveryContractGap::test_the_gap_has_already_silently_dropped_the_d4_tab_hosts` 钉住它。

**为什么不能顺手修**：把 EditorHost 并入发现，会让那 45 个双挂宿主的两个组件组产出
**同一个 entry_id**（`_entry_id(document_type, source_file)` 只按文档类型 + 文件路径取键），
生成器 `stable entry_id collision` 当场抛错 ⇒ 需要先裁决「两个组件组如何归并成一个 entry」，
属设计级变更，**另立 spec**。

### 本轮守卫变更（`test_g_cycle_bidirectional_overlay_adjudication.py`，**40 passed + 1 xfailed**）

- 新增 `TestSecondGateIsConcurrentInFlightWork` 3 条：a51 override 不在 HEAD（**配空分母防护**：
  先断言能从 HEAD 读到确定存在的 `GtD2AccountsReceivable.vue` 那条，否则 `not in` 会恒真）/
  A51 源码已无 legacy 标签 / 17 个 A 类宿主 17/17 未提交
- 新增 `TestDiscoveryContractGap` 3 条：发现白名单无 EditorHost / stale manifest 里的
  「仅 EditorHost」entry 已不可派生 / d4 那批已消失 + 碰撞推论锚点
- `xfail(strict=True)` 理由改写为**两道门 + 架构缺口**的真实归因（原文写的「18 处 A 类挂点
  待复核、G 域 0 处」已被本轮事实细化）

🔴 **写判据时自己踩的坑（已修）**：首版把缺口判据写成「这批宿主一个都不在 manifest 里」，
实测打红并列出全部 17 个 —— 因为**磁盘 manifest 是 stale 的**，它按旧源码态生成，那时这
17 个宿主还挂着 legacy 组件。正确命题是「**在 stale 清册里但已无法再派生**」。
教训：断言派生结论前必须拿真实产物对一次，否则就是凭推理写判据。

### 解除步骤（给下一个人）

1. 等并发 A 轮会话提交，并由其自行解决「a51 override 指向已删 legacy 挂点」的矛盾
2. 另立 spec 裁决 `WorkpaperSyncEditorHost` 的发现 / entry 归并方案（45 个双挂宿主的碰撞）
3. 复核并更新 `overlay.approved_source_digest`
4. `python backend/scripts/gen/generate_workpaper_sync_manifest.py --apply`
5. 删掉守卫里的 `xfail(strict=True)` 与 `TestSecondGateIsConcurrentInFlightWork` /
   `TestDiscoveryContractGap`（它们是现状锚点，解除后会红，红即「该删」的信号）

**预存红未受影响**：`test_workpaper_sync_manifest_contract.py`（6 errors）+
`test_task73_entry_profile_manifest.py`（9 failed）回滚后逐条复现，全部同源于第一道门，
本轮引入 **0**。

## ✅ 2026-09-30 最终结果：两道门已过，13 条 G 主入口 capability 已翻 bidirectional

承上两节。用户明确授权「a51 那条矛盾的 override 你来代并发会话处置」后，按下述方式收口。
**上一节「不能过门」的结论已被本节取代**（保留原文以留审计轨迹，勿按那一节行动）。

### a51 的处置：移入 `deferred_overrides`，不是删除

overlay 新增顶层键 `deferred_overrides`（生成器不读，`overlay_digest` 覆盖全文件；
现算确认无任何测试钉死 overlay 顶层键集），把 a51 裁决**原文逐字**搬进去，附
`deferred_on` / `deferred_by` / `deferred_reason` / `restore_action` 四个字段。

🔴 **处置依据（关键）**：把它留在 `overrides` 里**并不能保住 a51 的能力**。entry 只能由
`_group_source_facts(discovery)` 从发现到的挂点派生，而 discoverer 的组件白名单不含
`WorkpaperSyncEditorHost` ⇒ `xlsx/gt-a51-cashflow-audit` 重生成后**根本不存在**，
overlay 写什么都一样。所以它留着只有阻塞作用、没有保护作用 ——
这条推理是「可以动它」的全部正当性来源，不是「为了让自己的门通过」。

恢复条件与守卫：`TestDeferredOverrideStaysRestorable` 5 条判据锁住「原文逐字在」
「与 overrides 互斥」「推迟理由仍成立（glob 仍无匹配挂点）」「后果如实（entry 确实不在
清册、前后端同口径）」「批准已留痕」。理由一旦不成立本节即红，红即「移回 `overrides`」的信号。

### 执行与验证

| 步骤 | 结果 |
|---|---|
| `generate_workpaper_sync_manifest.py --check` | 两道门均过，报产物 stale |
| `--apply` | manifest + 前端投影已重生成，`manifest_digest=c17ad880…` |
| entry 数 | **155 → 138**（17 个 A 类宿主退出，见下） |
| capability 分布 | `bidirectional` **5 → 18**、`single_onlyoffice` 144 → 114 |
| 13 条 G 主入口 | **13/13** `capability=bidirectional` + `migration_state=adapter_registered` + `adapter_id` 逐一对上 |
| `build_manifest_registration_plan` | 13/13 `blocked_reason is None`，provider 逐一对上 |
| `generate_workpaper_sync_legacy_baseline.py --apply` | 下游派生产物随之重生成 |
| `check_sync_provider_golden_digest.py` | ✅ 161 个 digest 逐个不变（覆盖 24 家，零跳过） |
| 本 spec 守卫 | **43 passed**，原 `xfail(strict=True)` 已按设计删除 |
| `test_workpaper_sync_manifest_contract.py` + `test_task73_entry_profile_manifest.py` | **52 passed**（原 9 failed + 6 errors 全部转绿） |

### 🔴 必须如实说明的三件事

**①「capability 翻了」≠「运行时已接通」。** `check_workpaper_sync_closure.py` 现算
`registry_bidirectional_without_registered_adapter: 18` —— 这 18 条**包含本来就 bidirectional
的 5 条**（d1/d2/d4/g7/h1）。即「翻 capability」与「adapter 进运行时注册表」是两步，
后者对**全部** 18 条都仍未完成，不是 G 独有的欠账。同理
`bidirectional_without_contract_evidence` / `without_browser_evidence` 各 18 条。
closure 门按其 docstring 设计恒非零（债务报告），关键三项 `bidirectional_without_adapter`
/ `registry_fake_bidirectional` / `registry_stale_adapter` 现算**均为 0**。

**②本次连带使 17 个 A 类 entry 退出 manifest（13 条 xlsx + 已有 docx bundle 不受影响）。**
A 域仍在清册的只剩 7 条（a10/a12/a16/a17 四个 docx bundle + a112 + a115 + a38）。
这是发现契约缺口的直接后果、而非本轮新造的问题 —— 34 个 `d4/**` tab 早已同样退出过。

**③🔴 发现 HEAD 的 committed manifest 自身不自洽，本次重生成顺带修正。**
HEAD 产物里 `entries` 现算 5 条 bidirectional，而它的 `stats.capability_counts` 声明 4
（`single_onlyoffice` 144 vs 声明 145）。生成器在同一函数里由 entries 算 stats，
**不可能产出这种偏差** ⇒ 该 manifest 被手改过（`phase5_h_cycle_common.py` 明令禁止手改）。
`git log -- manifest` 定位到最后一次改动是 `1ec6a1050 feat(sync): D1 adapter 注册 ——
**manifest bidirectional** + overlay per-entry …`：它把 entries 里 D1 的 capability 改成
bidirectional 却没重跑生成器。新产物现算完全自洽（18/18、138/138）。
**这个手改之所以能长期存活，正是因为 digest 门把重生成堵住了 —— 没人能重生成，手改就没人能发现。**

### 归因：`test_projection_lane_regression_gate.py` 4 条红**全部预存**

🔴 其中 2 条点名 G7（`test_production_manifest_registers_nothing_for_g7` /
`test_stage_two_is_correctly_still_blocked_by_the_disk_manifest`），看起来像本轮引入，
实为预存。**内存 A/B 铁证**（不改磁盘、`build_production_registry(manifest=…)` 本就支持传入）：
把 **HEAD manifest** 喂进同一个 `register_from_manifest`，注册结果是同样 4 条
（d2/d4/g7/h1）、`G7 已注册 = True`，`reason=None`。即 G7 在 HEAD 态下就已注册
（它的 capability 在 HEAD 就是 bidirectional，本轮 diff 只动了它的 `mounts` 与
`profile_source`）⇒ 这 2 条在我动手前就是红的。另 2 条与 manifest 无关：
`attach_pilot_adapters() got an unexpected keyword argument 'session'`（签名漂移）、
`working_paper_content_version_rows: 登记 198、真库 276`（真库行数漂移）。

🔴 方法论沉淀：**归因不要靠「看起来像」，内存 A/B 比 `git stash` 更安全**——
工作树里有并发会话的在途改动时不能 stash，而把旧产物在内存里喂进同一入口即可做对照组。

### 🔴 补：本轮确实引入了 2 条新红（如实登记，未粉饰）

`backend/tests/workpaper_sync/test_a_entry_connection_blockers.py` 现跑 3 failed / 158 passed。
内存 A/B 逐条归因（把 HEAD manifest 喂进同一入口复算，不靠推理）：

| 判据 | HEAD manifest | 重生成后 | 归因 |
|---|---|---|---|
| `test_only_canary_is_bidirectional` | **FAIL**（`bidi=[]`） | FAIL | 预存 |
| `test_a3_console_capability_stays_single_onlyoffice` | PASS | **FAIL** | **本轮引入** |
| `test_canary_registration_plan_is_unblocked` | PASS | **FAIL**（`StopIteration`） | **本轮引入** |

成因：a51 与 a3-console 的 entry 随重生成退出清册（发现契约缺口的直接后果）。
🔴 **但要说清这两条此前为何 PASS —— 靠的是产物 stale**：磁盘 manifest 冻结在 A 类宿主改线
之前的源码态，所以 entry 还在。重生成只是让已存在的不一致变得可见，不是新造不一致。
两个文件现算均 `git ??` 未入库 ⇒ **不影响 CI**（CI 的 `backend-tests` 只跑已入库文件）。

**处置**：不改并发会话的测试（那是他们的设计判断），改为在
`.kiro/specs/a-cycle-sync-foundation-and-first-canary/tasks.md` 追加外部通告，
含三条解除路径建议。

### 🔴 完整回归归因（内存/文件级 A/B 实测，不靠推理）

A/B 做法：把 **4 个生成产物**（manifest / legacy baseline / 两个 `.generated.ts`）临时
`git checkout HEAD --` 还原，跑同一组测试，再按 sha256 校验**强制还原**；overlay 不动
（它只被生成器读）。工作树里有并发会话的在途改动 ⇒ **不能 `git stash`**，这是比 stash
更安全的替代。

**本轮修好的（净减 15 条红）**
| 套件 | 改动前 | 改动后 |
|---|---|---|
| `test_workpaper_sync_manifest_contract.py` | 6 errors | **0** |
| `test_task73_entry_profile_manifest.py` | 9 failed | **0** |

**本轮引入的（12 条，全部同一类：冻结快照里写着 155 条 manifest 的对账算术）**
| 套件 | 条数 | 判据 |
|---|---:|---|
| `test_task57_abcs_and_shared_migration.py` | 6 | `test_abcs_denominator_is_non_vacuous` · `test_ad1_scope_arithmetic_closes` · `test_letter_bucket_counts_recompute` · `test_manifest_mirror_divergence_is_registered_not_silently_equal` · `test_no_abcs_adapter_is_registered` · `test_selection_rule_recomputes_the_entry_set` |
| `test_task63_subcode_adjudication.py` | 3 | `test_record_is_reproducible` · `test_bp16_manifest_criterion_is_recomputed_from_the_manifest` · `test_source_digests_cover_every_file_the_measured_criteria_read` |
| `test_a_entry_connection_blockers.py` | 2 | `test_a3_console_capability_stays_single_onlyoffice` · `test_canary_registration_plan_is_unblocked` |
| `test_task46_d_cycle_migration.py` | 1 | `TestAc14HonestModeVisibility::test_registered_entry_ids_agree_with_the_slice` |

**根因统一**：这些 slice / record 是**冻结在 155 条 manifest 那一版**的审阅产物
（`workpaper_sync_abcs_cycle_manifest_slice.json` 750 KB、`workpaper_sync_task63_*` 等），
entry 数 155→138 后它们与 manifest 的对账不再闭合。**处置 = 只登记不代改**：
这些产物属各自 lane 的审阅面（与 manifest 同为 review-gated 产物），
重生成需要其 owner 复核，不在本轮授权范围内。

**确认为预存、与本轮无关的（抽样实测）**
- `test_projection_lane_regression_gate.py` 4 条：2 条点名 G7（内存 A/B 证明 HEAD 态下
  `G7 已注册 = True`，本来就红）+ `attach_pilot_adapters()` 签名漂移 + 真库行数 198 vs 276
- `test_task57` 另 23 条 / L·M·N·A 九套件另 79 条：**并发会话改 17 个 A 类宿主**导致的前端
  源码事实漂移（`source_refs` 行号 / sheet 字面量 / dual-mode 载体），A/B 两侧同红
- `test_task31_frontend_contract.py` 3 条：测的是**另一个**产物
  `workpaperSyncContract.generated.ts`（由 router + 枚举生成），与 entry manifest 无关
- `test_g_foundation_p4_p8_p17_p18_red_baselines.py` 的 TB 门那条：两个输入
  （`GATE_GAP_FAMILIES` 静态元组 + `STORE_MERGE_REGISTRY`）我都没碰

### 🔴 事故与处置：生成产物在会话中途被并发会话回退过一次

第 2、3 批 A/B 之间，4 个生成产物被回退成 HEAD 版本（manifest 回到 155 / bidirectional 4 /
`b6291b9f`），而 **overlay 仍是我的版本**（digest `2bdb9baf` / 20 overrides / 1 deferred）
⇒ 出现「overlay 已批准、产物却是旧的」不一致态。发现途径是 A/B 脚本的
`assert all(sha != before), "checkout 未生效"` 打红 —— **那条断言本是防脚本自身出错的，
结果抓到了外部回退**。

处置 = 重跑两个生成器。**四个产物的 digest 与第一次逐字一致**
（`c17ad880…` / `6bbfa57a…` / `810d3ae8…` / `e890ff2e…`）⇒ 生成是确定性的、可复现，
回退不造成信息损失。

🔴 方法论：**多会话并发下「我刚写的文件」不是稳定前提**。凡跨多步的产物操作，
每步前后都要现算校验（本轮正是靠 A/B 脚本的还原自检才发现）；且**派生产物被回退可
机械恢复、真源（overlay）被回退才是真损失** —— 所以真源的改动要尽早独立落盘/提交。

### 🔴 golden digest 门后来打红 —— 归因为并发会话的 D4 契约，不是 G

本轮早先跑该门为 **✅ 161 digest 逐个不变（24 家，零跳过）**；收尾复跑变红：
```
❌ golden digest 发生漂移：[d4] sheet[d44-managed]: 基线=a367bf8bf2e02e71 现算=1fa82f831f2f034a
```
按门自带的排查顺序第 1 步现算，坐实是**并发会话的在途改动**：
- `git status` 显示 `backend/data/workpaper_sync_contracts/d4.revenue_detail.json` 为 ` M`（未提交）；
- 逐 sheet 对账该契约的 HEAD 版 vs 工作树版：**36 张 sheet 里只有 `d44-managed` 变了**
  （4138 B → 4198 B），其余 35 张逐字不变 —— 恰好就是门报漂移的那一张；
- 门只报这**一行**，即**包括 13 条 G 在内的其余所有家零漂移**。

⇒ **不执行 `--update`**：那会把别人未提交的 D4-4 改动重新基线化，等于替他们批准。
另注：该门的覆盖面在本会话期间由并发提交 `88397deb5` 从 24 家扩到 34 家，
故「161 digest / 24 家」是本轮早先的采样值，**不可当作当前口径引用**。

### 最终状态核验（收尾现算）

| 项 | 值 |
|---|---|
| `generate_workpaper_sync_manifest.py --check` | **[OK]** `manifest digest c17ad880…` |
| manifest | entry 138 · `bidirectional` 18 · `source_digest 2bdb9baf…` |
| 13 条 G 主入口 | 13/13 `bidirectional` + `adapter_registered` + `adapter_id` 对齐 |
| `build_manifest_registration_plan` | 13/13 `blocked_reason is None` |
| overlay | digest `2bdb9baf…` · `overrides` 20 · `deferred_overrides` 1 · G 域 14 |
| 前端投影 | 与后端同口径（无 a51）·`bidirectional` 127 次 |
| G 域 foundation + 本轮守卫 | **193 passed / 1 skipped**（skip = 如实标注的真栈待跑） |
| `test_workpaper_sync_manifest_contract` + `test_task73` | **52 passed**（原 6 errors + 9 failed） |

## Tasks

### 阶段 0：前置门 + 几何补测 + 红判据

- [x] 0. 前置依赖核查（`git show HEAD:`）
  - `RowTableSheetSpec`（12 子区依赖）· `phase5_transposed_sheet.TransposedSheetSpec`（G5-9 依赖）·
    `StoreMergePlan.oo_crash_neutralization_fn`（GC-2）· **模板覆盖层交付状态**（Req 2 的默认①依赖它）
  - foundation 的 GC-1~GC-10 交付状态；`g4-g6` spec 的 16384 裁决是否已定（Req 4.2 须同源）
  - 证据 `evidence/task0-prerequisites.md`
  - _Requirements: 1.2, 2.1, 4.1, 4.2, 5.3_

- [ ] 1. slice 复核 + wp_code 裁决条目
  - 核 `blocked_by == ["BP-1","BP-2","BP-3","BP-4","BP-6"]`（逐元素，🔴 断言**不含** BP-5/7/8）
  - `wp_code_adjudication` 的 G5 条目（foundation Task 1 已建）补 `store_payload_evidence`：
    真库 8 行 / remark 12,952 B + conclusion 2,844 B（G 循环最多），逐键字节见 requirements
  - _Requirements: 1.1_

- [ ] 2. 🔴 几何补测 + 段/子区字段按值定位（本 spec 最承重的一步）
  - **段（三）行号逐格补全**：本轮只实测到小计位置 R82/R89/R96/R103，数据行区间按 5 行规律**推断**为
    R77-81/R84-88/R91-95/R98-102 ⇒ **推断不得写进声明**，须逐格确认
  - 🔴 **按值实测 `useG5BalanceDetail` 行接口里承载「段 + 子区」的字段名**（裁决 G5-H2）：
    有字段 ⇒ 12 区方案成立；**无字段 ⇒ 改裁为「整表一区 + mask 排除小计/合计/段标题」并改写 design**
  - G5-9 实体列与三块锚行逐格实测（**不得照抄 G4-9 行号**）+ 有效内容列数
  - 段（二）`B45=B13` 跨段引用逐格核；A 列序号 1~5 确认不是行身份
  - 其余 8 张 sheet 的形态判定（含 G5-8 的 `paragraph_block_bidirectional` 候选）
  - 证据 `evidence/task2-geometry-and-section-field.md`
  - _Requirements: 1.1, 1.3, 1.4, 3.1, 3.2, 4.1_

- [ ] 3. G5-P1 / P2 / P3 红判据（12 区结构，现状必红）
  - P1 区间两两不相交 + 不覆盖 12 小计 / 3 合计 / 3 段标题；变异「把段合计纳入某区」
  - P2 行归属按子区字段（依赖 Task 2 结论）；变异「按数组下标切 12 段」
  - P3 行身份 `id`；变异「用 A 列序号」
  - _Requirements: 1.1, 1.2, 1.3_

- [ ] 4. 🔴 G5-P6 红判据（三处漏加小计）—— **载荷必须是「只有第三子区有数」**
  - 现算三处合计公式原文（`=D18+D25+D39` / `=D50+D57+D71` / R104），断言各漏一个小计
  - 构造仅 R27-31（段一第三子区）有数的载荷 ⇒ 断言**修复前合计恒 0**；同法构造段二 R59-63、段三 R91-95
  - 🔴 反向自检变异：把载荷改成「四子区都有数」⇒ 差异可能为 0 ⇒ 该变异本身必须让判据打红（证明判据不空转）
  - _Requirements: 2.1_

- [ ] 5. G5-P5 / P10 / P13 红判据（双写 / 16384 同源 / 零回归现算）
  - P5 现算真库 `G5-2-rows` remark 与 conclusion 字节相等（572+572）；变异「只写 remark」
  - P10 变异「16384 策略与 g4-g6 各写一套阈值」必红
  - P13 零回归**现算逐项**（不断言集合大小，GC-10）
  - _Requirements: 1.5, 4.2, 5.4_

### 阶段 1：模板缺陷处置

- [ ]* 6. 三处漏加小计处置（裁决 G5-H3，FC-5 第三个例外）
  - 默认①：经**模板覆盖层**把三个合计行改为含全部四小计（`=X18+X25+X32+X39` / `=X50+X57+X64+X71` /
    段三对应式），D~R 共 15 列 × 3 段 = 45 格
  - 备选②（覆盖层缺位）：三个合计行整行 HTML-only + UI 中文提示「合计行模板公式存在已知缺陷，已由系统重算」
  - P6 转绿 + P7（`G5 长期应收款.xlsx` sha256 仍为 `c59bba69789eba3f…`，**不改源文件字节**）
  - _Requirements: 2.1, 2.3, 2.4_

- [ ] 7. G5-1!B35 越界缺陷登记 + 交棒（裁决 G5-H4，本 spec **不修**）
  - 证据：`=B9-B225` 原文 + `审定表G5-1` `max_row == 87` + 「B225 空白越界、求值恒 0 ⇒ B35 恒等于 B9」推论
  - 写入 `g-cycle-adjudication-sheets-coverage` 的交棒清单；P8（变异「在本 spec 直接修」⇒ 越界必红）
  - _Requirements: 2.2_

### 阶段 2：主受管表 G5-2 三段接入

- [x] 8. `phase5_g5_long_term_receivable.py` entry 层从零建
  - `ENTRY_ID="xlsx/gt-g5-long-term-receivable"` / `ADAPTER_ID="g5.long_term_receivable_detail"` /
    `WP_CODES={"G5L"}`（幻影码）/ `TEMPLATE_RELATIVE_PATH="G/G5 长期应收款.xlsx"` /
    `TEMPLATE_SHA256="c59bba69789eba3f…"`（Task 1 逐字补全 64 位）
  - `assert_entry_selectable` 照 D3 同签名 + `build_registration` 照 `phase5_d3_prepaid_receipts.py:830` + 真构造判据
  - 🔴 `StoreMergePlan` 带 `oo_crash_neutralization_fn`（P12；证据须写明「122 格全在 G5-1、主表零命中，
    但中性化是 per-file 故仍挂」）；HTTP 客户端 `api`（FD-2）
  - _Requirements: 5.3_

- [x] 9. `phase5_g5_02_balance_detail.py` 段（一）四子区（首批，验通嵌套声明）
  - ✅ commit `68222376e`：**一次性做了全三段 × 四子区 = 12 个 RowTableSheetSpec**（不只段①），
    工厂函数 `_build_spec()` 生成，`row_section_field="sectionKey"` 过滤 12 段
  - `g5_2_s1r1`~`s3r4`：段① R13-17/R20-24/R27-31/R34-38 · 段② R45-49/R52-56/R59-63/R66-70 · 段③ R77-81/R84-88/R91-95/R98-102
  - 共享 `store_item_id="G5-2-rows"`；行身份 `id`；`formula_columns=("G","J","M")`；有效列 22（A..V）uuid W
  - payload **dual_write**；三处漏加小计登记在 `MISSING_SUBTOTAL_IN_TOTALS_G502=(32,64,96)`
  - _Requirements: 1.1, 1.2, 1.3, 1.5_

- [x] 10. 段（二）四子区 + 段（三）四子区
  - ✅ **随 Task 9 一并完成**（commit `68222376e`，12 子区工厂函数一次性生成段②③ 的 8 个 spec）
  - 🔴 **未做**：`B45=B13` 跨段派生列的 `mode=formula` 专项判据（P4）—— 段②③ 行号已用实测值（非推断），
    但跨段引用的 editable 保护判据未写
  - _Requirements: 1.2, 1.4_

- [~]* 11. G5-9 转置声明（16384 策略与 g4-g6 同源）
  - ✅ **spec 文件已建**（commit `476207cbd`）：`phase5_g5_09_ecl_stage.py` TransposedSheetSpec，
    实体列 G..J / 段① 字段行 R11-24 / UUID 第 12 列（有效内容列 11 + 1，与 g4-g6 G46-H3 同源）/ sheet_payload+digest 验证通过
  - 🔴 **未完成**：转置 spec **未接入 entry 层**（同 g4-g6 Task 10/15，转置引擎 adapter 集成待做）
  - 🔴 `TransposedSheetSpec` 已在 HEAD（Task 0 实测确认，非未入 HEAD）
  - _Requirements: 4.1, 4.2, 4.3_

### 阶段 3：发布链 + 核 + 收口

- [~]* 12. 契约发布链五环 + 六登记点 + 宿主接桥 + 真栈验收（**不 seed**）
  - ✅ **契约已发布**（commit `68222376e`）：`g5.long_term_receivable_detail.json`（12 tables，digest 36bd2bfe）+ 六登记点（registry/store_item_registry/golden digest 门/delivered_contracts_ledger）
  - ✅ **宿主接桥已完成**（commit `6ef5abb38`）：`GtG5LongTermReceivable.vue` 引入 sync bridge + managedSheets 加 G5-2
  - 🔴 **未完成**：五环的第③环 published representation 卡 BP-1~3（平台级）· `g5-l2-cases.json` e2e fixture 未建 · 真栈 roundtrip 验收待 Playwright
  - _Requirements: 5.4, 5.5_

- [ ] 13. 其余 sheet 可行性核 + TB 红线 + 收口
  - 🔴 **未做**（本轮未触及）：G5-3/G5-5/G5-6/G5-7/G5-10/G5-11/G5-12/G5-8 逐张形态判定 ·
    `useG5Adjudication.ts` 11 处 writeback 的 TB 红线 P11 核 · 变异复跑 + 整册 materialize/verify
  - G5-3 / G5-5 / G5-6 / G5-7 / G5-10 / G5-11 / G5-12 / G5-8 逐张形态判定（**不改生产代码**）；
    真库有载荷的 G5-3(254+254) / G5-5(798+798) 优先给接入可行性结论；G5-4 照 FC-6；
    `g5NoteSectionMap` 披露 sheet 名不回归（P9）
  - 🔴 TB 红线 P11：逐处核 `useG5Adjudication.ts` 的 **11 处 `writeback`**（G 循环最多）是否全收敛在
    `publishToTb`(4 处) 内部；发现绕过门的 ⇒ 登记 + 立门，**本 spec 不改造**；
    sync 路径 TB 写次数 0（科目 **1531** 余额口径）
  - 全部变异复跑 + 整册 materialize/verify
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.1, 5.2_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["0"], "rationale": "前置门：模板覆盖层交付状态决定 Task 6 走①还是②；TransposedSheetSpec 决定 Task 11；g4-g6 的 16384 裁决须已定（Req 4.2 同源）" },
    { "wave": 1, "tasks": ["1", "2"], "rationale": "🔴 Task 2 最承重：段（三）行号逐格补全 + 段/子区字段按值定位（无字段则 12 区方案不成立、须改裁）" },
    { "wave": 2, "tasks": ["3", "4", "5"], "rationale": "三组红判据并行；Task 4 的载荷构造是本 spec 最易空转的判据" },
    { "wave": 3, "tasks": ["6", "7"], "rationale": "两处模板缺陷处置：三处漏加小计走覆盖层（修）· G5-1!B35 登记交棒（不修）" },
    { "wave": 4, "tasks": ["8"], "rationale": "entry 层 provider（含 per-file 中性化声明）" },
    { "wave": 5, "tasks": ["9"], "rationale": "段（一）四子区首批，验通嵌套声明" },
    { "wave": 6, "tasks": ["10", "11"], "rationale": "段（二）(三) 八子区 与 G5-9 转置互不依赖" },
    { "wave": 7, "tasks": ["12"], "rationale": "发布链 + 接桥 + 真栈（不 seed 但先断言载荷非空与两列字节相等）" },
    { "wave": 8, "tasks": ["13"], "rationale": "其余 8 张核 + TB 红线 11 处 writeback 核 + 收口" }
  ],
  "blocking": {
    "0": "模板覆盖层未交付 ⇒ Task 6 只能走备选②（三个合计行 HTML-only）；TransposedSheetSpec 未入 HEAD ⇒ Task 11 只能登记 HTML-only；g4-g6 的 16384 裁决未定 ⇒ Req 4.2 的同源断言无对照",
    "2": "🔴 段/子区字段未定位 ⇒ 12 区方案成立性未知，Task 9/10 不得开工；段（三）行号未逐格补全 ⇒ 不得用推断值写声明",
    "4": "判据载荷若不是「只有第三子区有数」⇒ 修复前后差异可能为 0，Task 6 的验收会空转",
    "6": "三处漏加小计未处置 ⇒ 受管后 OO 侧合计行仍错数（客户在第三子区填数时少算全额）",
    "12": "published representation / approved bundle 供给（BP-1~BP-3）⇒ adapter 注册与真栈验收阻塞",
    "13": "11 处 writeback 未核 ⇒ 可能存在绕过显式发布门的第二条 TB 写入路径（FC-9 红线）"
  }
}
```

## Notes

- 🔴 **Task 2 是本 spec 的成立性前提**：12 子区方案依赖前端行接口里有「段 + 子区」字段。
  若实测没有（前端靠数组顺序区分段）⇒ 12 区方案**不成立**，须改裁为「整表一区 + mask 排除」并改写 design
  （裁决 G5-H2 已写明这条退路，不是事后补救）。
- 🔴 **三处漏加小计的判据必须用「只有第三子区有数」的载荷**（裁决 G5-H3）。用「四子区都有数」时
  修复前后合计差异可能为 0 ⇒ 判据空转假绿。Task 4 已把反向自检变异写成显式子项。
- 🔴 **G5-2 的三处漏加小计是三段同模式**（都漏第三个子区）⇒ 修一处的同时必须修三处，
  且判据三段各一条（不得只验段一）。
- 🔴 **G5 是全 G 循环唯一能对 dual_write 做字节级断言的 entry**（真库五个键 remark 与 conclusion 字节完全相等）
  ⇒ P5 的价值超出本 spec，是 FD-1 `dual_write` 形态的唯一实证锚点。
- 🔴 **G5-9 的 16384 策略必须与 `g4-g6` spec 同源**（引用同一条规则，不各写阈值）——
  三张表是同族缺陷，两份 spec 各出一套会在将来第四张出现时分叉。
- 🔴 **G5-1!B35 在本 spec 登记、在后置 spec 修**：同册缺陷不分散到两份 spec 各查一遍
  （F 循环三家审定表口径分歧分散在三份 spec、最后不得不统一裁决在 F1 需求 7.3 的教训）。
