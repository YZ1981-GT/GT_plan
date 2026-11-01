# Phase 5 物理删除前置核查（2026-11-01，只读）

本轮**未执行任何删除**。下面是两个删除目标的现算事实与「要删就必须一起改」的清单。
现算脚本：`tmp_workpaper_sync_impl/probe_delete_candidates.py`（扫 `audit-platform/frontend/src`
下全部 `.ts` / `.vue` / `.json`，区分 import/调用形态与仅文本提及）。

## 1. `components/workpaper/sync/usePilotBridgeAdapter.ts`（202 行）

| 维度 | 现算值 |
|---|---|
| 生产 importer / 调用方 | **0** |
| 测试 importer | 2：`components/workpaper/__tests__/h1SyncHostWiring.spec.ts`、`components/workpaper/sync/__tests__/usePilotBridgeAdapter.spec.ts` |
| 仅注释提及（不是调用） | 6 个生产文件：`b60/GtB60Bundle.vue`、`b60/GtB60DocxPane.vue`、`GtG7LongTermEquityMain.vue`、`GtH1FixedAssets.vue`、`sync/hManagedSheets.ts`、`sync/useD2SyncBridge.ts` |

「零生产调用」这一条成立。但**断言它存在**的判据有 6 处，删文件会把它们全部打红：

1. `backend/tests/workpaper_sync/test_task45_pilot_legacy_deletion.py`
   - `test_pilot_bridge_adapter_exists`（直接断言 `adapter.exists()`）
   - `test_pilot_bridge_adapter_does_not_call_config_endpoint`
   - `test_bridge_adapter_uses_unified_storage_key`
   - `test_no_legacy_storage_prefixes_in_adapter`
   - `test_adapter_exposes_entry_id_parameter`
   - `test_adapter_is_documented_as_transitional`
   - `_adapter_interface_fields()`（从 `export interface PilotBridgeAdapter` 抽字段的真源）
2. `backend/tests/workpaper_sync/test_task46_d_cycle_migration.py::test_bridge_adapter_supports_entry_id`
3. `backend/tests/workpaper_sync/test_task48_f_cycle_migration.py::test_bridge_adapter_supports_entry_id`
4. `backend/tests/workpaper_sync/test_task49_g_cycle_migration.py::test_bridge_adapter_supports_entry_id`
5. `audit-platform/frontend/src/components/workpaper/sync/__tests__/bridgeMaterializeDriven.spec.ts`
   —— 从磁盘读该文件再断言它不是驱动方
6. `backend/tests/workpaper_sync/test_task66_legacy_deletion_plan.py` 把该路径当「未跟踪」**对照组**
   （该对照已失效：路径现已入库，这条在 HEAD 上即为红，属 BP-66-2 欠账，非本轮引入）

🔴 仓库自己的判据已写明删除程序：`test_task45` 的
`test_adapter_consumer_hosts...` 在消费方归零时断言「文件还在」，并在失败消息里要求
「请随文件一并删除（连同 test_task46/48/49 的 …）」。也就是说正确动作是**同一次提交**里
删文件 + 删这些字段契约判据类，并把 `bridgeMaterializeDriven` 那条改成「文件必须不存在」。

另有两处数据产物把它登记为 pre-delete subject，删除后需同步：
`backend/data/workpaper_sync_task72_pre_delete_eligibility.json`（BP-72-3）与
`backend/scripts/check/check_task72_pre_delete_eligibility_gate.py` 的 disposition 文案。

**本轮裁定：不删。** 理由不是「不该删」，而是它是一次跨 7 个文件的协同删除；
CI 的 `backend-tests` 是 `pytest -x`，半截状态会让整个 job 停在第一条红上。

## 2. `components/workpaper/GtG6OtherBondEcl.vue`（52 行，历史简版桩）

| 维度 | 现算值 |
|---|---|
| 生产 importer | **1**，且是生成物：`components.d.ts`（unplugin-vue-components 声明，非真实 import） |
| 测试 importer | 0 |
| 仅文本提及 | `components/workpaper/coverage-ledger.json`、替代组件 `GtG6OtherBondInvestmentEcl.vue` 的说明、`sync/workpaperSyncManifest.generated.ts` |
| 替代组件 | `GtG6OtherBondInvestmentEcl.vue` 存在（276 行） |
| `htmlRendererRegistry.ts` | 两个组件名都**没有**直接出现；`componentType` 联合类型里有 `'g6-other-bond-investment-ecl'` |

删除的连带面：

* 该桩正是 manifest 里**唯一**的 `unreachable` entry（`xlsx/gt-g6-other-bond-ecl`）。删文件后
  源发现器不再产出这条 entry ⇒ `entries 198 → 197`、`unreachable 1 → 0`，必须重生成
  manifest / legacy baseline / current-state / cycle projection 并重跑 closure；
* `coverage-ledger.json` 把它记成 componentType `g6-other-bond-investment-main` 的 `entryFile`
  —— 这条登记本身可疑（替代组件是 `-ecl`），删除前要先裁定台账是写错了还是指的别的东西；
* `test_workpaper_sync_manifest_contract.py::test_unreachable_stub_is_explicit_and_not_counted_as_independent`
  以「存在一条显式 unreachable」为前提，归零后该判据需改写（否则它会因为「桩删掉了」而红）。

**本轮裁定：不删。** 同样是协同改动（4 个生成物 + 2 个判据 + 1 条台账裁定），
且必须在同一次提交里完成才不留半截状态。

## 结论

两条删除的**前置事实**（零生产调用 / 替代组件在库）都已现算成立；阻塞项是「与之绑定的判据
与生成物必须同批改」。本 spec 的 tasks 5.3 / 5.4 保持未勾选，清单即为上面两节。
