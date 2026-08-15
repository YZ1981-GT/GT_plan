# 共享文件争用核查（R11.3）

- spec：`x3-adjustment-entry-import-export` · 任务 1.8 · 生成时间 2026-08-15T12:54:37+08:00
- 生成脚本：`backend/scripts/diagnose/snapshot_x3_baseline.py --contention`（结果可复算，逐条给 文件:行号）
- 清单真源：`design.md` §边界与禁区 R11.3 行的「已知需核查清单：」，实解析 10 项

## 一、active spec 实扫结果（真源 = 磁盘复选框，非 memory 旧数）

判据：有 tasks.md 且存在 `^\s*-\s\[([ x~-])\]` 中标记为 ' ' / '-' / '~' 的行

| active spec | 复选框总数 | 未完成 | tasks.md mtime |
|---|---:|---:|---|
| `e1-variant-recalc-and-mutation-denominator-closure` | 19 | 12 | 2026-08-15T12:42:30+08:00 |
| `k-cycle-extraction-formula-and-disclosure-closure` | 25 | 3 | 2026-08-15T12:47:08+08:00 |
| `l-cycle-extraction-formula-and-disclosure-completion` | 26 | 23 | 2026-08-09T23:42:51+08:00 |
| `procedure-trim-report-line-account-resolution` | 16 | 16 | 2026-08-12T08:59:14+08:00 |
| `workpaper-import-export-lifecycle-closure` | 25 | 1 | 2026-08-12T23:00:20+08:00 |

> ⚠️ 任务简报点名、但实扫**不在** active 集：`g7-column-alignment-and-extraction-closure` · `i-cycle-extraction-formula-and-disclosure-closure`（多半已收口或无未完成复选框）

> ⚠️ 实扫为 active、简报未点名：`e1-variant-recalc-and-mutation-denominator-closure` · `procedure-trim-report-line-account-resolution` —— 它们也在核查面内

## 二、十项共享文件 × 争用命中

| # | 共享文件 | 仓库路径 | 命中的 active spec 文档 | 命中行数 |
|---:|---|---|---|---:|
| 1 | `_kfgh_cycle_adapters.py` | `backend/app/services/bulk_tab/_kfgh_cycle_adapters.py` | `workpaper-import-export-lifecycle-closure/tasks.md` | 1 |
| 2 | `_cycle_import_export_common.py` | `backend/app/routers/wp_render_strategies/_cycle_import_export_common.py` | — | 0 |
| 3 | `generate_catalog.py` | `backend/scripts/acnr/generate_catalog.py` | — | 0 |
| 4 | `check_ie_catalog_sync.py` | `backend/scripts/acnr/check_ie_catalog_sync.py` | — | 0 |
| 5 | `global_catalog.json` | `backend/data/acnr/global_catalog.json` | `workpaper-import-export-lifecycle-closure/tasks.md` | 1 |
| 6 | `adjustment_ie_contract.json` | `backend/data/adjustment_ie_contract.json` | — | 0 |
| 7 | `cycleImportExportRegistry.generated.ts` | `audit-platform/frontend/src/components/workpaper/shared/cycleImportExportRegistry.generated.ts` | `workpaper-import-export-lifecycle-closure/design.md`、`workpaper-import-export-lifecycle-closure/tasks.md` | 3 |
| 8 | `governance-checks.yml` | `.github/workflows/governance-checks.yml` | `e1-variant-recalc-and-mutation-denominator-closure/design.md`、`e1-variant-recalc-and-mutation-denominator-closure/tasks.md`、`k-cycle-extraction-formula-and-disclosure-closure/tasks.md`、`l-cycle-extraction-formula-and-disclosure-completion/tasks.md`、`procedure-trim-report-line-account-resolution/tasks.md`、`workpaper-import-export-lifecycle-closure/design.md` | 12 |
| 9 | `test_ie_route_inventory.py` | `backend/tests/test_ie_route_inventory.py` | `workpaper-import-export-lifecycle-closure/design.md`、`workpaper-import-export-lifecycle-closure/tasks.md` | 3 |
| 10 | `test_ie_prefix_reachability.py` | `backend/tests/test_ie_prefix_reachability.py` | `workpaper-import-export-lifecycle-closure/tasks.md` | 1 |

## 三、逐条命中明细（文件:行号 + 原文）

### `_kfgh_cycle_adapters.py`

- `.kiro/specs/workpaper-import-export-lifecycle-closure/tasks.md:412` — - **删除后应下调的基线（已实测，前置满足后直接照用）**：`_BASE_IE_MODULES` 99 → 80 · `_BASE_FACTORY_PREFIXES` 62 → 43 · `_TRULY_DEAD_FACTORY_PREFIXES` → 空集 · `IE_ADAPTER_REGISTRY` 97 → 78 · `test_kfgh_cycle_adapters.py` 的 `EXPECTED_PREFIXES["CEI

### `global_catalog.json`

- `.kiro/specs/workpaper-import-export-lifecycle-closure/tasks.md:495` — 修复已 apply：`backend/data/acnr/global_catalog.json` md5 `4daec223` → `88d0408b`，

### `cycleImportExportRegistry.generated.ts`

- `.kiro/specs/workpaper-import-export-lifecycle-closure/design.md:195` — - 新建 `audit-platform/frontend/src/components/workpaper/shared/cycleImportExportRegistry.generated.ts` —— 由脚本从 ACNR catalog 生成（含 `apiPrefix` / `sheets[]` / `itemId` / `storageField`）。
- `.kiro/specs/workpaper-import-export-lifecycle-closure/tasks.md:137` — - 新建生成脚本 + `cycleImportExportRegistry.generated.ts`：从 ACNR catalog 的 `import_export` 段派生（`apiPrefix`/`sheets[]`/`itemId`/`storageField`）
- `.kiro/specs/workpaper-import-export-lifecycle-closure/tasks.md:887` — `cycleImportExportRegistry.generated.ts`（49 前缀，脚本产出）·

### `governance-checks.yml`

- `.kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/design.md:463` — 挂进 `governance-checks.yml` 的每个文件路径在干净 checkout 下都存在且被 git 跟踪（沿用本轮复盘的「exists + tracked」判据形态）。
- `.kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/design.md:469` — 对 `governance-checks.yml` 的验收判据是「变动是否落在本 spec 的字节区间内」，不是「其他 job 一个都没变」—— 并发会话同时改该文件是常态，全局等值型判据必假红。
- `.kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/design.md:505` — - 改 `governance-checks.yml` 用 `fs_append` 或精确 `str_replace`，验收用归因型判据（Property 32）。
- `.kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/tasks.md:178` — - 在 `.github/workflows/governance-checks.yml` 新增 job：A 组前端守卫（vitest）+ B 组后端守卫（pytest）+ 共享件能力守卫 + `--check-anchors` 静态自检
- `.kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/tasks.md:234` — | `.github/workflows/governance-checks.yml` | 带并发 K 循环 +22 未提交改动 | Task 17 用归因型验收 |
- `.kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/tasks.md:216` — - `governance-checks.yml` 新增 job `k-cycle-extraction-formula-closure`（10 步）
- `.kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/tasks.md:437` — **任务选择理由**：Task 14/23 当时都不安全 —— 实测 `note_template_soe.json` **35 分钟前**被并发会话改过、`governance-checks.yml` **4.6 分钟前**被改过。Task 22 只新建文件，零冲突。
- `.kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/tasks.md:547` — **交付**：`governance-checks.yml` 新增 job `k-cycle-extraction-formula-closure`（10 步）+ 新建 `backend/tests/test_k_cycle_ci_wiring.py`（13 例）+ 变异 **M54~M60 全 RED**（全量 **60/60 RED**）。
- `.kiro/specs/l-cycle-extraction-formula-and-disclosure-completion/tasks.md:248` — - `governance-checks.yml` 新增后端 + 前端两个 job，把幂等脚本 `--check` 纳入步骤
- `.kiro/specs/l-cycle-extraction-formula-and-disclosure-completion/tasks.md:280` — | `g7-column-alignment-…`（3/21） | 两份 `note_template_*.json` · `governance-checks.yml` | 同上；G7 在改列结构，本 spec 只碰 L 章节 |
- `.kiro/specs/procedure-trim-report-line-account-resolution/tasks.md:195` — - `.github/workflows/governance-checks.yml` 新增两个 job：`report-line-account-resolution`（后端守卫 + 变异脚本）与 `report-line-account-resolution-frontend`（前端两个守卫）
- `.kiro/specs/workpaper-import-export-lifecycle-closure/design.md:604` — `governance-checks.yml` 新增 job 覆盖本 spec 全部守卫；`yaml.safe_load` 可解析且无重名 job。

### `test_ie_route_inventory.py`

- `.kiro/specs/workpaper-import-export-lifecycle-closure/design.md:643` — | L4 | `backend/tests/test_ie_route_inventory.py` | **运行期 `app.routes`** 分组（照抄 `group_ie_routes`）+ 三向锁死 + 台账数字固化 |
- `.kiro/specs/workpaper-import-export-lifecycle-closure/tasks.md:54` — - 新建 `backend/tests/test_ie_route_inventory.py`：**运行期** `app.routes` 分组，口径照抄 design §Data Models 的 `group_ie_routes`（**必须剔除 `{wp_id}`/`{wp_code}` 路径参数段** —— 立项的「87 组」含此误计）
- `.kiro/specs/workpaper-import-export-lifecycle-closure/tasks.md:469` — `backend/tests/services/test_wp_download_manifest.py` + `backend/tests/test_ie_route_inventory.py`（Task 2，22 例）·

### `test_ie_prefix_reachability.py`

- `.kiro/specs/workpaper-import-export-lifecycle-closure/tasks.md:169` — - **新增守卫**：`ieWiringIntegrity.spec.ts`（11 例，前端接线闭环）+ `backend/tests/test_ie_prefix_reachability.py`（11 例，路由可达性 + sheet 参数一致性）

## 四、补充核查面（本 spec tasks.md 点名、但不在 R11.3 十项内）

判据：本 spec tasks.md 里反引号包裹的文件名，减去 R11.3 十项；共 200 项，命中 10 项。

| 文件 | 命中的 active spec 文档 | 行号 |
|---|---|---|
| `.generated.ts` | `.kiro/specs/workpaper-import-export-lifecycle-closure/design.md` | 195 |
| `.generated.ts` | `.kiro/specs/workpaper-import-export-lifecycle-closure/tasks.md` | 137, 887 |
| `cycleImportExportRegistry.spec.ts` | `.kiro/specs/workpaper-import-export-lifecycle-closure/design.md` | 198, 644 |
| `cycleImportExportRegistry.spec.ts` | `.kiro/specs/workpaper-import-export-lifecycle-closure/tasks.md` | 61, 556 |
| `fix_acnr_catalog_ie_gap.py` | `.kiro/specs/workpaper-import-export-lifecycle-closure/tasks.md` | 939, 1003 |
| `ieWiringIntegrity.spec.ts` | `.kiro/specs/workpaper-import-export-lifecycle-closure/tasks.md` | 169 |
| `l2_interest_payable.py` | `.kiro/specs/workpaper-import-export-lifecycle-closure/tasks.md` | 421 |
| `mutate_ie_lifecycle_guards.py` | `.kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/design.md` | 385, 504 |
| `mutate_ie_lifecycle_guards.py` | `.kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/tasks.md` | 31, 232, 270, 272 |
| `mutate_ie_lifecycle_guards.py` | `.kiro/specs/workpaper-import-export-lifecycle-closure/design.md` | 649 |
| `mutate_ie_lifecycle_guards.py` | `.kiro/specs/workpaper-import-export-lifecycle-closure/tasks.md` | 271 |
| `prefill_formula_mapping.json` | `.kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/design.md` | 36 |
| `prefill_formula_mapping.json` | `.kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/tasks.md` | 11, 374, 384, 446, 468, 508, 813 |
| `prefill_formula_mapping.json` | `.kiro/specs/l-cycle-extraction-formula-and-disclosure-completion/design.md` | 45, 301, 318 |
| `prefill_formula_mapping.json` | `.kiro/specs/l-cycle-extraction-formula-and-disclosure-completion/tasks.md` | 9, 279 |
| `test_kfgh_cycle_adapters.py` | `.kiro/specs/workpaper-import-export-lifecycle-closure/tasks.md` | 412 |
| `tmp_t22_base.json` | `.kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/tasks.md` | 65, 199 |
| `wp_bulk_router.py` | `.kiro/specs/workpaper-import-export-lifecycle-closure/design.md` | 10 |
| `wp_bulk_router.py` | `.kiro/specs/workpaper-import-export-lifecycle-closure/tasks.md` | 9 |

> 这一层不属 R11.3 字面清单，但同样会被并发会话回退 —— 命中项在改动前须同样核 mtime 与 git status

## 五、sheet 级交集（R11.2 —— 文件级 grep 抓不到的那一层）

判据：在其他 active spec 的 tasks/design/requirements.md 里扫 `{父 wp_code}-{数字}`，数字为 3 的（= X-3 本体）不计

| 父底稿 | 被别的 active spec 提及的非 X-3 sheet | 命中位置（文档:行号） |
|---|---|---|
| `L2` | `L2-1` | `l-cycle-extraction-formula-and-disclosure-completion/design.md`:324；`l-cycle-extraction-formula-and-disclosure-completion/requirements.md`:63；`l-cycle-extraction-formula-and-disclosure-completion/tasks.md`:72 |
| `L2` | `L2-2` | `l-cycle-extraction-formula-and-disclosure-completion/design.md`:64,66,67,71,72；`l-cycle-extraction-formula-and-disclosure-completion/requirements.md`:25,121,231；`l-cycle-extraction-formula-and-disclosure-completion/tasks.md`:174,175,293,330 |
| `L6` | `L6-1` | `l-cycle-extraction-formula-and-disclosure-completion/design.md`:324；`l-cycle-extraction-formula-and-disclosure-completion/requirements.md`:69；`l-cycle-extraction-formula-and-disclosure-completion/tasks.md`:72 |
| `L6` | `L6-2` | `l-cycle-extraction-formula-and-disclosure-completion/design.md`:348；`l-cycle-extraction-formula-and-disclosure-completion/requirements.md`:85；`l-cycle-extraction-formula-and-disclosure-completion/tasks.md`:81,319 |

> 有交集 ⇒ R11.2「L2 / L6 非 X-3 业务表逐字节不变」不是形式条款；本 spec 对这些底稿只许在专属 router 内**追加**形态 A 端点与 IE_SHEETS 常量

## 六、处置

- 有命中的文件：本 spec 的破坏性任务（2.1 / 6.1 / 9.1 / 14.2）在改动前**再跑一次本脚本**并核 mtime；若 mtime 为秒/分钟级说明并发会话正在写，**暂缓改动**。
- 无命中不等于无风险：并发会话可能改了文件却没在 spec 文档里写。故改动前另查 `git status --porcelain <file>` 与 mtime，两条都干净才动手。

## 七、任务 6.1 施工前防呆（`_kfgh_cycle_adapters.py`，2026-08-14）

本节由任务 6.1 追加，记录**该次改动当刻**的实测结论（上面第一~六节是本脚本 `--contention` 的自动产物，本轮已重跑刷新）。

### 7.1 并发会话判定 —— 无争用，可动手

| 判据 | 实测 |
|---|---|
| mtime | `2026-08-13 08:17:16`（施工当刻 `2026-08-14 19:49`，**距今约 35 小时**）⇒ 非秒/分钟级，无并发会话正在写 |
| md5 | `89ec310cc36a3729f95260b4fe0e11aa` = 任务给定基线，逐字相符 |
| `git status --porcelain` | ` M`（**行尾单一差异**：HEAD 侧 LF 规范化 15830 B，工作树纯 CRLF 16193 B；`15830 + 363 LF = 16193` 且 `git show HEAD:<path>` 的 LF→CRLF 重建结果 md5 **恰等于** `89ec310c…` ⇒ 改前工作树内容与 HEAD 逐字相同，` M` 不是他人未提交的内容改动） |

### 7.2 其他 active spec 的提及 —— 1 处，方向相反但**已被裁决为下游**

七个 active spec 里只有 **`workpaper-import-export-lifecycle-closure`（父 spec）** 提到本文件，仅 1 行：

- `workpaper-import-export-lifecycle-closure/tasks.md`:412 —— Task 25「删 19 个工厂模块」施加后应下调的基线清单（`_BASE_IE_MODULES` 99→80 · `_BASE_FACTORY_PREFIXES` 62→43 · `IE_ADAPTER_REGISTRY` 97→78 · `_TRULY_DEAD_FACTORY_PREFIXES` → 空集 · `test_kfgh_cycle_adapters.py` 的 `EXPECTED_PREFIXES["CEIJL"]` 移除 19 项）。

🔴 **两处需父 spec 在解除阻塞时同步修订的记载（本轮只登记、不代改）**：

1. 同文件 :413 写「**`_PREFIX_TO_MODULE` 处置方式已定：删 19 个键，不改指专属 router** —— 因为 `l2` / `m1` 的 6 个端点无 `sheet` 参数，改指后 `sheet_code` 会被 FastAPI 静默忽略」。该结论的**前提已被本 spec 消除**：任务 5.1/5.2 通过 `attach_shape_a_routes` 给 16 个专属 router 各挂了**独立的形态 A 三态端点**，其签名 `(wp_id, sheet: str = Query(...), db, current_user, file, strategy)` 里 `sheet` 是**必填**，adapter 的 `_endpoint_for` 按 `/{短前缀}/{suffix}` 命中的正是这三条新端点（不是无 `sheet` 的既有形态 B handler）⇒ 「`sheet_code` 被静默忽略」在改指后不成立。父 spec :413 属**过期记载**。
2. 同文件 :412 的「删 19 个键」在本任务施加后应改为「删 **3** 个键（`h9`/`l7`/`l8`）」：19 个待删工厂模块对应的键里，**16 个已由本任务改指专属 router**，其键必须**保留**（删键会同时废掉 bulk 通路）。父 spec :410 已裁决该前置「单独立项，不在本 spec 半径内」⇒ 本任务与 Task 25 **不构成并发编辑**（父 spec 该任务处于阻塞驻留态，非被中断）。

结论：**零争用，可施工**。本任务遵 R11.5 **不删任何工厂模块**（含这 19 个），只切断 16 个键对工厂的引用。

### 7.3 施工后复核

- 本文件改动后 md5 = `5b4b06249e5146ea18cdffeca5d008f4` / 17405 B / **382 CRLF / 0 LF-only**（纯 CRLF 保持）。
- 89 键规模与**键序**均未变；仅 16 个值改指，其余 73 键逐字不变（逐键 diff 见任务 6.1 实录）。
## 八、任务 6.3 施工前防呆（`test_ie_route_inventory.py`，2026-08-14）
本节由任务 6.3 追加。作业面两文件里 `test_x3_adapter_host_same_module.py` 是本 spec 任务 1.4 新建的 `??` 未跟踪文件（无争用面），需核查的只有 `test_ie_route_inventory.py`（父 spec 任务 2 的交付物）。
### 8.1 并发会话判定 —— 无争用，可动手
| 判据 | 实测（施工当刻 2026-08-14 21:10） |
|---|---|
| mtime | `2026-08-10 13:30:27`（**距今约 104 小时**）⇒ 非秒/分钟级，无并发会话正在写 |
| md5（改前） | `f337b2a449545f897b7da2946d9c81f6` / 28203 B / **0 CRLF / 567 LF-only（纯 LF）** ⇒ 行尾先量后保，改后仍 0 CRLF |
| `git status --porcelain -- <该文件>` | **零条目**（既非 ` M` 也非 `??`）⇒ 工作树与 HEAD 逐字相同，不存在他人未提交改动可被覆盖 |
| 全仓 `git status --porcelain` 行数 | 2085（其余 ` M`/`??` 属并发会话或本 spec 前序任务，本轮未动） |
### 8.2 其他 active spec 的提及 —— 3 处，全在父 spec，且均非并发编辑
| 位置 | 内容 | 是否构成争用 |
|---|---|---|
| `workpaper-import-export-lifecycle-closure/design.md`:643 | 守卫清单 L4 行：「运行期 `app.routes` 分组（照抄 `group_ie_routes`）· 三向锁死 + 台账数字固化」 | 否 —— 只描述判据形态，不约束具体数值 |
| 同 spec `tasks.md`:54 | 父 spec **Task 2**「新建本文件」的任务正文 | 否 —— Task 2 已 `[x]`，交付物即本文件 |
| 同 spec `tasks.md`:469 | CI/守卫挂载清单里列出本文件（Task 2 的 2 例） | 否 —— 只列文件名，不列数值 |
父 spec 25 个复选框实扫：**仅 1 项未完成** = `tasks.md`:404 的 **Task 25**，标记 `[-]` 且正文写明「阻塞：待前置立项完成，本任务有意驻留、非被中断」⇒ 按 memory 的三条判据属**有意驻留**，不是被中断的批量执行 ⇒ 与本任务不构成并发编辑。
### 8.3 本轮对该文件的改动性质（父 spec 视角）
- 只上调**台账数字**（`_BASE_*`）与死集，**判据本体（`group_ie_routes` / `classify_route_shapes` / `_factory_api_prefixes`）一字未改** ⇒ 父 spec design:643 的「三向锁死」形态不变。
- 新增 3 条测试（`test_dead_set_records_the_x3_revival` / `test_x3_delta_is_internally_consistent` / `test_task25_targets_are_registered_but_not_yet_applied`），**未删改任何既有测试**，父 spec 的 CI 挂载清单无需变动。
- 父 spec Task 25 的目标基线以 `_TASK25_PENDING_BASELINES` 登记为「待启用」，并由 `test_task25_targets_are_registered_but_not_yet_applied` 钉住「只登记不生效」⇒ Task 25 解除阻塞时改 4 个常量即可，不必重新实测。
### 8.4 施工后复核
- 改后 md5 = `d4bdd4f045e63387727c538262981c58` / 40639 B / **0 CRLF / 754 LF-only**（纯 LF 保持）。
- `test_x3_adapter_host_same_module.py` 改后 md5 = `73ea95d6084181e59740acd6718724ef` / 47828 B / **0 CRLF / 882 LF-only**（纯 LF 保持，仍为 `??` 未跟踪）。
- 禁改面 4 文件 md5 逐个核对未变：`_x3_adjustment_import_export.py` = `a97a28aa11edc9d839a7c065d833c001` · `_kfgh_cycle_adapters.py` = `5b4b06249e5146ea18cdffeca5d008f4` · `adjustment_ie_contract.json` = `fc5d54650a2a4b3b2486fc060576d6c8` · `global_catalog.json` = `af0868bd50d13027e091afd370fa6a41`（其中 `_kfgh_cycle_adapters.py` 在 MUT-3/MUT-4 复现中被真落盘变异过两次，每次跑完立即逐字节还原，收尾 md5 回到基线）。

## 九、任务 17.1 施工前后防呆（`_kfgh_cycle_adapters.py` **第二次**改动，2026-08-15）

本节由任务 17.1 追加。作业面两文件：`_kfgh_cycle_adapters.py`（第二次改动，第一次是任务 6.1，见 §七）+ `test_x3_bulk_strategy_parity.py`（本任务新建，`??` 未跟踪 ⇒ 无争用面）。防呆脚本本轮**实跑**（mtime + `git status --porcelain` + 其他 active spec grep 三腿齐跑），复核当刻 **2026-08-15T00:13:07**。

### 9.1 并发会话判定 —— 无争用，可动手

| 判据 | 实测（复核当刻 2026-08-15 00:13:07） |
|---|---|
| `mtime` | `2026-08-14 23:49:40` —— **秒/分钟级，但归属本会话**：该时刻 = 变异检验 POST-RESTORE 的写盘时刻，备份 `tmp_x3_t171_impl.orig`（mtime `23:45:38`）与当前文件**逐字节相同** ⇒ 按 memory「按 mtime + 内容判归属」判为**自己刚写的**，不是并发会话在写 |
| `md5` | `2fcdd118050af1fad97501d9ed36a3ef` / 18817 B / **402 CRLF / 0 LF-only**（纯 CRLF 保持，与 §7.3 同向） |
| `git status --porcelain -- <该文件>` | ` M` —— **不是他人未提交的内容改动**。该 ` M` 自任务 6.1 起即存在（§7.1 已证 6.1 之前的 ` M` 仅是行尾差异），本轮增量可**算术对齐**：382 → 402 CRLF（**+20 行**）、17405 → 18817 B（**+1412 B**），与四处改动逐条相符（形参 1 行 + 段前空行 1 行 + docstring 11 行 + 探测块 2 行 + 调用点 1 行展开为 6 行 ⇒ +20） |
| 全仓 `git status --porcelain` 行数 | **349**（§8.1 当刻为 2085；差额属并发会话与本 spec 前序任务，本轮未动） |
| 并发会话是否活跃 | **是，但不交叉**：8 个 active spec 里 4 个 tasks.md mtime 为分钟级（见 9.2 表）⇒ 确有并发会话正在写它们，但**无一提及本文件** |
| `.github/workflows/governance-checks.yml` | 仍 ` M`，与 §7 / §8 同一条，属并发会话，本轮**未读未写** |

### 9.2 其他 active spec 的提及 —— 仍 1 处，且与本轮作业区**行区不相交**

active spec 实扫（真源 = 磁盘复选框 `^\s*-\s\[([ x~-])\]`，非 memory 旧数）：

| spec | 框数 | 未完成 | tasks.md mtime |
|---|---|---|---|
| `frontend-excel-io-single-entry-convergence` | 18 | 3 | 2026-08-15 00:12:51 |
| `g7-column-alignment-and-extraction-closure` | 24 | 4 | 2026-08-15 00:01:40 |
| `i-cycle-extraction-formula-and-disclosure-closure` | 25 | 3 | 2026-08-15 00:01:29 |
| `k-cycle-extraction-formula-and-disclosure-closure` | 25 | 9 | 2026-08-14 23:56:02 |
| `l-cycle-extraction-formula-and-disclosure-completion` | 26 | 23 | 2026-08-09 23:42:51 |
| `procedure-trim-report-line-account-resolution` | 16 | 16 | 2026-08-12 08:59:14 |
| `workpaper-import-export-lifecycle-closure`（父 spec） | 25 | 1 | 2026-08-12 23:00:20 |
| `x3-adjustment-entry-import-export`（本 spec） | 63 | 33 | 2026-08-14 23:04:41 |

三个 needle（`_kfgh_cycle_adapters` / `_call_endpoint` / `test_x3_bulk_strategy_parity`）扫全部**其他** active spec 的 `tasks.md` / `design.md` / `requirements.md` ⇒ **命中合计 1**，即父 spec `workpaper-import-export-lifecycle-closure/tasks.md:412`（与 §7.2 同一行，Task 25 的「删除后应下调的基线」）。

判零争用，三条独立依据：

1. **状态** —— 父 spec 25 框实扫**仅 1 项未完成** = Task 25，标 `[-]` 且正文写明「阻塞：待前置立项完成，**本任务有意驻留、非被中断**」⇒ 按 memory 三条判据非并发编辑。
2. **命中的其实是测试文件的名字** —— 该行里 `_kfgh_cycle_adapters` 出现在 `test_kfgh_cycle_adapters.py` 之中；`_BASE_IE_MODULES` / `_BASE_FACTORY_PREFIXES` / `_TRULY_DEAD_FACTORY_PREFIXES` 三个常量在**生产文件内 grep 零命中**（它们住在测试侧），故那行主要约束的是测试台账而非本轮作业面。
3. **行区不相交** —— Task 25 若动生产文件，作业区是 `_PREFIX_TO_MODULE` 的键集（约第 87~220 行）；本任务作业区是 `_call_endpoint`（222+）与 `_make_import_fn`（291+）⇒ 零重叠行。残余风险仅「整文件覆盖式写盘」，由本节 md5 + 备份逐字节比对兜住。

### 9.3 施工后复核

- `_kfgh_cycle_adapters.py` = `2fcdd118050af1fad97501d9ed36a3ef` / 18817 B / **402 CRLF / 0 LF-only**（纯 CRLF 保持）；与备份 `tmp_x3_t171_impl.orig`（18817 B，同 md5）**逐字节相同** ⇒ 三条变异全部已还原、零残留。
- `test_x3_bulk_strategy_parity.py` = `2eaf84f0e86ef25385346c7f0229f87b` / 56798 B / **0 CRLF / 1168 LF-only**（新建纯 LF，仍 `??` 未跟踪）。
- 禁改面三项收尾逐个复量，**全部未动**：`_x3_adjustment_import_export.py` = `a97a28aa11edc9d839a7c065d833c001` / 88726 B / 1824 CRLF · `backend/data/adjustment_ie_contract.json` = `fc5d54650a2a4b3b2486fc060576d6c8` / 228807 B · `backend/tests/test_x3_column_property.py` = `da313e7f33c9c32e68af8df5fa085dd1` / 50004 B / 纯 LF（任务 17.2 的作业面，本轮未改）。
- 本节追加前本文件 **175 CRLF / 0 LF-only**，追加后仍**纯 CRLF**（行尾先量后保）。

## 十、任务 8.1 施工前后防呆（`generate_catalog.py` **首次**改动，2026-08-15）

本节由任务 8.1 追加。作业面四文件：**共享文件** `backend/scripts/acnr/generate_catalog.py`（`_ALL_CYCLES` 追加 `l`/`m`/`n` + `--cycle` 帮助串）+ **三个新建 yaml** `backend/data/acnr/sources/{l,m,n}_cycle_ie_manifest.yaml`（对并发会话零争用）+ 新建守卫 `backend/tests/test_x3_ie_manifest_registration.py`（`??` 未跟踪 ⇒ 无争用面）。防呆脚本本轮**实跑**三腿。

### 10.1 并发会话判定 —— 无争用，可动手

| 判据 | 实测（改动前当刻） |
|---|---|
| `mtime` | `2026-07-23 17:45:05` —— **月级陈旧**（距今三周余），非并发会话在写 |
| `md5` | `33370935aba21492968622bd8f495005` / 24307 B / **660 CRLF / 0 LF-only**（纯 CRLF） |
| `git status --porcelain -- <该文件>` | **空**（无任何标记）—— 该共享文件当刻**干净且已跟踪**，不存在他人未提交改动；与 §七/§九 的 `_kfgh_cycle_adapters.py`（长期 ` M`）不同型 |
| `git status --porcelain -- backend/scripts/acnr backend/data/acnr` | **0 行** —— 整个 acnr 生成链目录与数据目录当刻零改动 |
| 全仓 `git status --porcelain` 行数 | **2338**（§9.1 当刻为 349；差额属并发会话，本轮未动） |
| `backend/wp_templates/` | `git status --porcelain` **0 行**（R11.1） |
| 三个新建 yaml 的施工前状态 | `l` / `m` / `n` 三份**全部 ABSENT** ⇒ 新建，零争用（任务 17.1 实录里「8.1 的三个 manifest 实测 ABSENT ×3」在本轮开工前复验仍成立） |
| `.github/workflows/governance-checks.yml` | 仍 ` M`，与 §七/§八/§九 同一条，属并发会话，本轮**未读未写** |

### 10.2 其他 active spec 的提及 —— **零命中**

active spec 实扫（真源 = 磁盘复选框 `^\s*-\s\[([ x~-])\]`，非 memory 旧数）：

| spec | 框数 | 未完成 | tasks.md mtime |
|---|---|---|---|
| `g7-column-alignment-and-extraction-closure` | 24 | 4 | 2026-08-15 00:01:40 |

| `i-cycle-extraction-formula-and-disclosure-closure` | 25 | 2 | 2026-08-15 00:23:22 |

| `k-cycle-extraction-formula-and-disclosure-closure` | 25 | 8 | 2026-08-15 01:11:17 |

| `l-cycle-extraction-formula-and-disclosure-completion` | 26 | 23 | 2026-08-09 23:42:51 |

| `procedure-trim-report-line-account-resolution` | 16 | 16 | 2026-08-12 08:59:14 |

| `workpaper-import-export-lifecycle-closure` | 25 | 1 | 2026-08-12 23:00:20 |

| `x3-adjustment-entry-import-export` | 63 | 29 | 2026-08-15 01:42:07 |

六个 needle（`generate_catalog` / `_ALL_CYCLES` / `l_cycle_ie_manifest` / `m_cycle_ie_manifest` / `n_cycle_ie_manifest` / `acnr/sources`）扫**全部**其他 spec 目录下的 `*.md` ⇒ 命中合计 **19 行，全部落在 `_archive/`**（`_archive/04-infra-architecture/acnr/{design,requirements,tasks}.md` 15 行 · `_archive/04-infra-architecture/acnr-invalidation-overlay-hardening/tasks.md` 1 行 · `_archive/08-disclosure-notes/k1-extraction-chain-and-note-alignment/{requirements,tasks}.md` 2 行 + 1 行）。**active spec 侧零命中** ⇒ 判零争用，无需行区分析。

> 注：`l-cycle-extraction-formula-and-disclosure-completion`（26 框 / 23 未完成）在 R11.2 的半径内（L2/L6 非 X-3 业务表），但它**不提及** acnr 生成链，且本轮未碰任何 `.vue` / 业务表 —— 本任务的写盘面只有上面四个文件。

### 10.3 施工后复核

- `generate_catalog.py` = `d9770a3e1077969de2c9a3029a2cc919` / 24965 B / **667 CRLF / 0 LF-only**（纯 C（基线/实测：G1 16/pending · G2 38/38 · G3 15/15 · G4 5/5 · G5 8/8 · G6 10/10 · G7 2/2 · G8 1/1 · G9 1/1 · G10 4/0 · G11 1/1）字面量 + `--cycle` 帮助串），不计行数。
- 三个新建 yaml（行尾**先量后写**：既有 5 份 manifest 实测全纯 CRLF ⇒ 新建同款纯 CRLF）：
  - `l_cycle_ie_manifest.yaml` = `ce9c684bd466b266ca32c957a43a8ce2` / 6655 B / **68 CRLF / 0 LF-only** / 2 条
  - `m_cycle_ie_manifest.yaml` = `0864c686ef1b427e3f37c93808e9fd4b` / 12396 B / **140 CRLF / 0 LF-only** / 10 条
  - `n_cycle_ie_manifest.yaml` = `ebc016b9ac8a45b7fd7f41c5739ef896` / 8023 B / **86 CRLF / 0 LF-only** / 4 条
- 新建守卫 `test_x3_ie_manifest_registration.py` = `85f110731a57f3332c4fd038b023b04a` / 29078 B / **0 CRLF / 639 LF-only**（新建纯 LF，与 backend/tests 下既有 x3 守卫同款）。
- **共享文件改动的外溢面实测为零**：`check_x3_deviation_registry.py --check` 在「回退本任务四处改动 → 复跑 → 还原」三步法下，**11 组逐格相同**（G1 PENDING · G2 38/38 · G3 15/15 · G4 5/5 · G5 8/5→8/8 · G6 10/10 · G7 2/2 · G8 1/1 · G9 1/1 · G10 4/0 · G11 1/1），`exit=2` 与 NOT-CLOSED 集合 `{G1, G6, G8, G10, G11}` 亦相同 ⇒ G6/G8/G10/G11 的 `ENTRY_DRIFT` 与 G10 的 `NEEDS_BASELINE_LOWERING` **属前序任务，非本任务引入**。还原自证：四文件 md5 == 回退前（`restored == original: True`）。
- **裁决 2 两列**：`acnr-ie-catalog-sync` exit=1 · drift **19 → 19（未变）**；`check-acnr-catalog-drift` exit=1 · drift **53 → 69（+16）**、hunks 53 → 69、changed_lines 258 → 386。增量**恰为**本 spec 的 16 个 `addr_id`（`added == 16 段` 为 True），原 53 条**逐条仍在**（丢失 0 条）；在**内存副本**上模拟任务 9.1 的外科补丁后 drift **回到 53**（hunks 53 / changed_lines 258 / 差集逐条 == 原 53）⇒ 8.1 + 9.1 合起来对 drift 中性。catalog 全程只读（md5 `af0868bd50d13027e091afd370fa6a41` 前后相同）。
- 本节追加前本文件 **220 CRLF / 0 LF-only**，追加后仍**纯 CRLF**（行尾先量后保）。

## 十一、任务 8.2 施工前后防呆（`check_ie_catalog_sync.py` **首次**改动，2026-08-15）

> 🔴 **本节为重建内容，非原始字节。** 原文在任务 10.1 施工时被
> `snapshot_x3_baseline.py --contention` 重写产物文件时连带抹掉（详见 §十三「事故与恢复」）。
> 重建依据 = `tasks.md` 任务 8.2 实录里「共享文件防呆」整句（该句本就是本节结论的同源摘要），
> 逐字转录如下；原文若另有明细，以 tasks.md 该行为准。

- 三腿**实跑** —— mtime 改前 `2026-07-10 20:23:02`（**月级陈旧**，非并发会话在写）·
  `git status --porcelain -- <该文件>` 改前**空**、改后 ` M`，且这条 ` M` **可证 100% 属本任务**
  （`git show HEAD:<该文件>` = 7236 B / 209 LF，LF→CRLF 后 md5 **恰等于**改前的
  `0410a4c6a26e76657be2f28071b9b9d4`，`7236 + 209 = 7445` 算术自洽 ⇒ 改前工作副本与 HEAD
  逐字节相同，没有他人未提交成果被覆盖）· 全仓 porcelain **2348** 行（§十当刻 2338，差额属并发会话）。
- 本节追加后该文件 md5 `b585c817aca970918bff2d45a343bc33` / 34180 B / **295 CRLF / 0 LF-only** 纯 CRLF 保持；
  结构核验 H1 +0 / H2 +1 / H3 +3、前缀字节逐字未动。

## 12. 任务 9.1 —— `global_catalog.json` 外科补丁（施加后已按核验结论逐字节还原）

> 🔴 **本节为重建内容，非原始字节。** 同 §十一，原文被任务 10.1 的
> `--contention` 运行抹掉，重建依据 = `tasks.md` 任务 9.1 实录里「R11.3 共享文件防呆」整句。

- 改前复核三腿 —— mtime `2026-08-12 13:44:29` · `git status --porcelain` **空** ·
  8 个带 `tasks.md` 的 spec 逐个扫四串后**非归档目录仅 1 处命中**
  （`workpaper-import-export-lifecycle-closure/tasks.md` 的 `global_catalog` ×1，实为过去式记录；
  该 spec 唯一未闭合的 Task 25 作业面是删工厂模块且自述「有意驻留」）⇒ 无争用。
- 追加前 295 CRLF / 0 lone_CR、追加后 311 CRLF / 0 lone_CR，原文字节完整保留、h2 +1 / h3 +2。
- 收尾：`global_catalog.json` 已按核验结论**逐字节还原**（md5 `6e5a66269d10dac5cde53bbea0c99da3`）。

## 十三、任务 10.1 施工前后防呆（`cycleImportExportRegistry.generated.ts` **首次**改动，2026-08-15）

作业面两个文件（均属 R11.3 十项之一或其守卫）：
`audit-platform/frontend/src/components/workpaper/shared/cycleImportExportRegistry.generated.ts`（生成器产物）与
`.../__tests__/cycleImportExportRegistry.spec.ts`（其守卫）。

### 三腿实跑

| 腿 | `generated.ts` | `cycleImportExportRegistry.spec.ts` |
|---|---|---|
| ① mtime（改前） | `2026-08-12 14:06:32` —— 距施工当刻（`2026-08-15 12:45`）约 **70 小时**，非秒/分钟级 | 末次提交 `6c53f397 @2026-08-12 23:48:58`，同属 70 小时级 |
| ② `git status --porcelain -- <该文件>`（改前） | **空**（已跟踪且干净） | **空** |
| ②b 改前工作副本 == HEAD ? | `git show HEAD:<该文件>` = 6263 B / 95 LF，LF→CRLF 重建 md5 **恰等于**改前 `c9a9b4f7fd04def5781d3868fcaef13f`（`6263 + 95 = 6358` 算术自洽）⇒ **逐字节相同** | HEAD = 37326 B / 787 LF，重建 md5 **恰等于**改前 `182d86ad0239decfab2da475a26657bc`（`37326 + 787 = 38113`）⇒ **逐字节相同** |
| ③ active spec 争用 | 见下 | 见下 |

②b 这一腿的价值：证明改前的工作副本里**没有他人未提交的成果**被我覆盖（porcelain 空只说明"与索引无差异"，
字节重建相等才说明"内容与 HEAD 相同"）。全仓 porcelain 施工当刻 **606** 行（并发会话在途，与本任务无关）。

### active spec 实扫（真源 = 磁盘复选框，行首锚定 `^\s*-\s\[([ x~-])\]\s+\d+\.`）

`.kiro/specs/` 下 **9 个非归档目录**，其中**带 `tasks.md` 且仍有未完成项的 6 个**：
`e1-variant-recalc-and-mutation-denominator-closure`（7/19）·
`k-cycle-extraction-formula-and-disclosure-closure`（22/25）·
`l-cycle-extraction-formula-and-disclosure-completion`（3/26）·
`procedure-trim-report-line-account-resolution`（0/16）·
`workpaper-import-export-lifecycle-closure`（24/25）· 本 spec（35/53，本任务勾选前）。
另 `i-cycle-…closure` 已 24/24、`procedure-delegation-visibility-isolation` 与
`visibility-isolation-go-live-hardening` **无 `tasks.md`**（空壳）⇒ 报 active 数必须区分「目录数」与「带 tasks.md 的 spec 数」。

三个 needle（`cycleImportExportRegistry.generated` / `cycleImportExportRegistry.spec` / `gen_cycle_import_export_registry`）
扫其余 active spec 的全部 `*.md`：命中 **8 行，全部落在父 spec `workpaper-import-export-lifecycle-closure`**：

| 文件:行号 | needle | 性质 |
|---|---|---|
| `design.md:195` | generated | 述形态（「含 `apiPrefix`/`sheets[]`/`itemId`/`storageField`」）—— 不约束数值 |
| `design.md:198` | spec | 述门面 = generated + MANUAL_OVERRIDES |
| `design.md:644` | spec | 守卫清单 L4 行 |
| `tasks.md:61` | spec | Task 3 正文 |
| `tasks.md:137` | generated | Task 13 正文 |
| `tasks.md:556` | spec | Task 3 实录（20 例） |
| `tasks.md:886` | 生成器 | Task 13 实录 |
| `tasks.md:887` | generated | 实录「**49 前缀**，脚本产出」= 唯一带数值的一处 |

⇒ 判**零并发编辑风险**：父 spec 24/25，唯一未闭合项是 Task 25（正文自述「阻塞…有意驻留、非被中断」）。
`tasks.md:887` 的「49 前缀」是**过去式实录**，不是生效基线（生效基线在生成文件自身的
`GENERATED_PREFIX_COUNT` 与守卫里，由 catalog 派生），本任务把它推到 78 属正常演进，不回改父 spec 实录。

### 🔴 事故与恢复（本节最该留痕的一条）

**事故**：本任务为取「十项共享文件争用」结论跑了
`python backend/scripts/diagnose/snapshot_x3_baseline.py --contention --quiet`。
该脚本**把本文件当自己的产物重写**（不是追加）⇒ 任务 6.1 / 6.3 / 17.1 / 8.1 / 8.2 / 9.1
六轮**手工追加**的 §七~§12 被一并抹掉：**36487 B（md5 `03d3c90ee01cca44e859c2a6956d1498`，311 CRLF）
→ 13314 B**，时刻 `2026-08-15 12:54:37`。本文件是 `??` **未跟踪**文件 ⇒ `git` 无法恢复。

**恢复**（当刻即做，结果 33294 B / md5 `db84aebef72c061d873326e73f1f5c10` / 302 CRLF / 0 lone_CR）：

| 段 | 来源 | 保真度 |
|---|---|---|
| §一~§六 | 保留 12:54 重新生成的**当刻**版本 | 脚本产物段，内容为当刻实测，可接受 |
| §七~§十 | Kiro local history 最新快照 `%APPDATA%\Kiro\User\History\60589408\UTEP.md`（`2026-08-15T02:21:35`，30031 B） | **逐字节**恢复 |
| §十一（任务 8.2）· §12（任务 9.1） | **无任何快照**（由脚本追加，编辑器未留 history 条目）⇒ 按 `tasks.md` 各自实录里「共享文件防呆」整句**重建** | ⚠️ **重建，非原始字节**，节内已显著标注 |

**教训（写给后续任务）**：
1. `snapshot_x3_baseline.py --contention` 是**写操作**，不是只读探针 —— 它重写
   `evidence/shared_file_contention.md` 与 `.json`。**跑它之前必须先备份这两个文件**，
   或改用只读方式自取三腿（本节的表格即为只读自取）。
2. 「防呆核查」自己踩了防呆要防的坑：R11.3 的三腿只覆盖「**我要改的文件**」，
   而本次损失来自「**我为核查而跑的脚本的产物文件**」。⇒ 三腿之外要补一条：
   **跑任何 `--emit`/`--contention`/`--snapshot` 类脚本前，先列出它的产物清单并备份**。
3. `??` 未跟踪的证据文件没有任何兜底（git 无、history 只在编辑器改动时留）⇒
   spec 收口前把 `evidence/` 入库不只是 CI 需要，也是唯一的可恢复性保障。

### 本节追加后

本节追加前 **302 CRLF / 0 LF-only / 0 lone_CR**（恢复后的字节态），追加后仍**纯 CRLF**。

## §13 任务 11.1（16 个 {X}TabAdjustment.vue 挂 dropdown + 接读回）

**三腿只读自取**（`git status --porcelain <目标>` + `mtime` + 跨 spec grep；未跑 `snapshot_x3_baseline.py --contention`，理由见上节教训 1）：

| 腿 | 判据 | 实测 |
|---|---|---|
| ① git 状态 | `git status --porcelain` 限定到 L2/L6 两个 tab 与 `useL6Adjustment.ts` | `M  composables/useL6Adjustment.ts`（任务 4.2 已 add，本轮未碰）· ` M l2/core/L2TabAdjustment.vue` / ` M l6/core/L6TabAdjustment.vue`（本轮追加） |
| ② mtime | 改前后各量一次 | 两个 tab = 本轮施加时刻；`useL6Adjustment.ts` = `2026-08-14T11:31:17`（任务 4.2 当时的时刻，**本轮零改动**） |
| ③ 跨 spec grep | 遍历 `.kiro/specs/*/`（排除 `_archive`）搜 `L2TabAdjustment` / `L6TabAdjustment` / `useL2Adjustment` / `useL6Adjustment` | **命中仅本 spec 自己的 design.md 与 tasks.md**；`l-cycle-extraction-formula-and-disclosure-completion` 的三件套里一次都没出现 |

**R11.2 边界结论**：L2/L6 半径内的并发 spec（`l-cycle-…completion`，26 框 / 23 未完成）作业面是审定表与披露 Tab 的取数/列结构，**不含 X-3 调整分录 Tab**（③ 的 grep 为证）。本轮对这两个文件**只追加**：① 一条 `import CycleImportExportDropdown` ② 容器内一个 `<CycleImportExportDropdown …/>` ③ 一个 `handleImported()` 函数；L6 另加 `loadFromResponses` 解构与 onMounted 一行调用（任务 11.1 正文点名要求）。**未动**任何业务表列定义/公式/审定回写/披露同步代码 —— 逐个 `git diff` 复核：L2 净 +20 行 · L6 净 +23 行，全部落在上述三处。

**本轮产物文件清单（跑脚本前已列出并备份，落实上节教训 2）**：
`tmp_x3_t111_backup/`（18 个 .vue 原件 + `ieWiringIntegrity.spec.ts.orig`）—— 施加脚本与变异 harness 共用同一份备份，每条变异跑完立即还原并复量 md5（5/5 逐字节相同）。

**本节追加方式**：`read_bytes` → 纯 CRLF 拼接 → `write_bytes`，未经 `str_replace`、未用含 `→`/`⇒`/emoji 的 oldStr 定位。
