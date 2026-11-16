# Phase 0.4 改动前测试与门禁基线（2026-11-01）

基线 HEAD：`de31e7bf6`（干净 worktree `tmp_workpaper_sync_impl/baseline_wt`，已 lock）。
比对脚本：`tmp_workpaper_sync_impl/compare_junit.py`（后端）、`tmp_workpaper_sync_impl/compare_vitest.py`（前端）。
两者都先剥 ANSI，并断言「解析出的失败节点数 == 摘要 failed+errors」—— 否则判漏算而非报差集。

## 1. 后端点名选集（15 个文件，`tmp_workpaper_sync_impl/selection.txt`）

| 树 | 结果 |
|---|---|
| HEAD 基线（选集里 HEAD 存在的 10 个文件） | `34 failed, 818 passed, 2 skipped, 6 errors` |
| 候选（15 个文件，含本轮 5 个新文件） | `29 failed, 863 passed, 2 skipped` |

逐节点差集：**added 0 / resolved 11**。resolved 的 11 条是本轮修掉的：

* `test_workpaper_sync_manifest_contract.py` 的 6 个 **ERROR**（manifest schema / 投影 / mount 集合 /
  parent duplicate / unreachable / source digest fail-closed）
* `test_task13_contract_registry.py` 的 5 条，其中
  `test_contract_directory_matches_the_delivery_ledger` 在 HEAD 必红 —— `g4.ecl_stage` /
  `g6.ecl_stage` 契约已在生产目录却没有台账行（`git show HEAD:…delivered_contracts_ledger.py`
  现算 `ecl_stage` 命中 0 次，`git ls-tree HEAD` 现算两个契约文件都在）。

剩余 29 条红在 HEAD 逐条复现，属其他 spec 欠账，本轮未改：

* `test_attach_wiring_completeness.py` 22 条（writeback-followup R12：f2/f4/f5/g1/g3/g9/h3/h7/i5/k1/c2
  的兄弟 binding 与 digest 比对欠账）。HEAD 基线 `22 failed, 91 passed`，候选 `22 failed, 94 passed`，
  失败节点集合逐条相同（added 0 / resolved 0），新增 3 条是本轮第五形态判据且全绿。
* `test_projection_lane_registry.py::TestAuthorityLogicalSuffixMatchesProviders` 3 条
* `test_c_cycle_baseline.py::TestPatternLessAttribution::test_a_program_console_32_codes` 等 4 条

## 2. 采集期崩溃（本轮实测，属环境/判据面问题）

1. `tests/workpaper_sync` **整目录**跑会卡死：某条 gate 用系统 Python（`…/Python312/python.exe`）
   以**同一个选集**重新起 pytest 子进程（实测父 12440 → 子 31388，子进程 CPU 1308 s / RSS 1.87 GB），
   进度停在 45%。⇒ 本 spec 的回归一律用点名选集，不跑整目录。
2. `test_task44_oo94_excel_pilot_gate.py` / `test_task61_oo94_word_pilot_gate.py` 采集期
   `ModuleNotFoundError: No module named '_spec_dir'`（check 脚本经 importlib 加载时
   `backend/scripts/check` 不在 `sys.path`）。HEAD 同形态，非本轮引入。

## 3. 前端 sync 选集

| 树 | 结果 |
|---|---|
| HEAD 基线（5 个失败文件） | `13 failed, 233 passed` |
| 候选（同 5 个文件） | `13 failed, 233 passed` |
| 候选（`sync/__tests__` 全目录 46 文件） | `13 failed, 1174 passed` |

逐节点差集 **added 0 / resolved 0**。13 条红分布：`WorkpaperSyncEditorHost` 2、
`WorkpaperSyncStatusBar` 1、`task69IndependentRegression` 1、`workpaperSyncEditorHostSizing` 5
（B22A / M1 / M5 / M8 / M9 缺 `height: calc(100vh …)` 容器）、`bridgeMaterializeDriven` 4
（`GtA91DeficiencyLetter.vue`）。

🔴 中途曾有 26 条**本轮引入**的红（全在 `task69IndependentRegression.spec.ts`）：统一桥新增的
`GET …/readiness` 未登记进该文件的独立 URL 分类器 ⇒ 被判 `UNKNOWN` 并被 harness 以
「未登记的请求」拒绝。已按两步修完并复测归零：①分类器加 `read_entry_readiness`；
②默认放行应答放进 `resetObservations()`（放 `beforeEach` 不够 —— 有多条用例在体内再次
`resetObservations()`，会把 beforeEach 登记的路由一起清掉）。

## 4. 门禁与生成器

| 命令 | 结果 |
|---|---|
| `generate_workpaper_sync_manifest.py --check` | OK，digest `dcde4f2377050e7e…` |
| `generate_workpaper_sync_legacy_baseline.py --check` | OK，digest `ef609a1c9b05f3ec…` |
| `generate_workpaper_sync_current_state.py --check` | OK，`360bf9d7acfed390` |
| `generate_workpaper_sync_cycle_projection.py --check` | OK，`aa045510c9584871` |
| `check_workpaper_sync_closure.py --expect-open-debt --write-report` | exit 0，`total blocking facts: 938` |
| `apply_pending_runtime_adjudications.py --check` | OK，`runtime-ready overrides=13` |

## 5. 本基线的用法

后续任何一轮都必须与**同一最新 HEAD** 的基线按节点集合比对，而不是与本文件里的绝对条数比：
上面的数字会随其他 spec 的进展变化，判据是「added 为 0」，不是「failed 等于 29」。
