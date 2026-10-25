# Task 34 证据：状态条 / 冲突对话框 / recovery 面板 / 详情 timeline

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 34
Requirements: 5.8, 8.1, 8.2, 8.3, 8.4, 11.2, 11.3, 11.5, 11.6, 11.7, 11.10, 11.11
Properties: 35 / 46 / 47 / 48

## 交付物

| 文件 | 作用 |
|---|---|
| `sync/workpaperSyncPresentation.ts` | 纯投影层：基调/等待语义/动作提示三张穷尽表、close 仲裁推导、冲突预览解析、批量范围、resolve fence、recovery 阻断推导、timeline 投影、缺口登记 |
| `sync/WorkpaperSyncStatusBar.vue` | 紧凑状态条：24 个可观测状态逐一可辨、error 优先、duplicate 折叠、close 仲裁进展、追溯 chips、三个 verdict 布尔披露 |
| `sync/WorkpaperSyncConflictDialog.vue` | sheet/table/row 三级分组、逐项与显式范围批量裁决（二次确认）、关闭不应用、八项 fence 齐备或可见失败 |
| `sync/WorkpaperSyncRecoveryPanel.vue` | authorization-first list 唯一可见性门、claim 前三实体全空且零重试入口、claim 后三实体齐备并跟踪原 operation、download-only 不称回写完成 |
| `sync/WorkpaperSyncDetailsDrawer.vue` | 追溯事实 + 缺口显式留白、operation / recovery 两条独立 timeline、rollback 只提交 opaque UUID（二次确认） |
| `sync/__tests__/workpaperSyncUiHarness.ts` | 真桥驱动器（只注入 API stub），把桥推到 24 个可观测状态 |
| `sync/__tests__/*.spec.ts`（5 个） | 挂载判据：DOM + 真实 emit + prop/emit 正面判决 |
| `backend/scripts/check/mutate_task34_sync_ui_guards.py` | 63 条变异，四态判定 |
| `backend/scripts/diagnose/probe_task34_sync_ui_radiation.py` | 辐射面测算（按导入图，不按词搜索） |

## 判据结果

* 前端：`src/components/workpaper/sync` 全目录 **15 文件 / 572 例通过**（本任务新增 189 例：
  投影 53 / 状态条 40 / 冲突 36 / recovery 32 / 详情 29；`--reporter=basic` 全绿）。
* `npx tsc --noEmit`：**2128** 个 `error TS`（基线 2124）。新增 4 条全部是
  `TS2307 Cannot find module '../XXX.vue'` —— 与 Task 33 的
  `WorkpaperSyncEditorHost.spec.ts` 同一族既存类别（裸 `tsc` 不解析 `.vue`）。
  首轮另有 1 条真实新错（harness 的 `never` 穷尽性断言），已修。
* `npx eslint src/components/workpaper/sync/`：**0 problems**。
* 变异：**63/63 RED**（单次全量运行，基线 189/189 passed，覆盖面 5/5 分母文件均被命中）。

## 辐射面（按导入图闭包）

* 前端：图 7183 节点 → 闭包 11 个，其中 spec 文件 **5 个**（全是本任务新建）。
  本任务**未修改**任何既有生产文件，故存量 spec 零辐射。
* 后端：只改了 spec 的 `tasks.md`（两个复选框）与生成物
  `workpaper_ac_coverage_matrix.json`。直接引用者 2 个模块、闭包 4 个，
  测试文件 **1 个**（`test_workpaper_ac_coverage_matrix.py`，50 例通过）。

## 变异过程中抓到的两个**判据缺陷**（都已修，并在源码里留下成因）

1. **M30 首轮 GREEN**（`plainRetryVisible` 的 recovery 排除）。
   原判据用 `driveTo('recovery_pending')` + `notifyHostFailure`，但
   `recovery_pending` 有 `sync_failed` 出边 ⇒ 上报失败后状态其实已是 `error`，
   且那条路上 `requestedOperationId` 恒为 null ⇒ 关掉的是**另一道**门。
   改成可达路径：`applied → reloadAfterApplied（桥不清 requestedOperationId）
   → notifyRecoveryCase → claim 失败回到 recovery_pending 且 error 粘住`。
2. **M52 首轮 GREEN**（`canClaim` 的阻断原因门）。
   原判据没先选候选确认 ⇒ 关掉门的其实是「未选候选」那一道。改成先选候选再断言禁用，
   并补一条「已选候选仍不许认领且 claim API 零调用」。

两者都是同一形态：**一个门被另一个门遮住，于是它的判据永远 GREEN**。

## 探针自身也修过两次（记录在脚本 docstring 里）

辐射面探针最初用裸 `tasks.md` 做判别 ⇒ 命中 67 个模块；补上 spec 目录名后**涨到 170**
—— 因为本 spec 每个源文件的 docstring 头都写着它，闭包吹到 986 个测试文件。
最终收敛为「唯一指向被改数据文件的子串 + AST 扫描跳过 docstring」。

## 已登记的上游缺口（本任务把它们变成可见事实，未编造任何值）

见 `workpaperSyncPresentation.WP_SYNC_TRACE_GAPS`（5 项）与下列三条：

1. `room_latest_durable_application_id / room_latest_durable_sequence` 无读取面 ⇒
   冲突面板要求宿主显式提供，否则提交禁用并逐项列出阻断原因（绝不用 canonical
   application 顶替）。
2. 桥的 `notifyCloseSuccessorApplied(id)` **校验但不保存** successor intent id ⇒
   接任者标识只能由宿主回传；缺失时渲染「尚未确定 / 未由宿主回传」。
3. claim 的 202 回执没有 shape、桥也没保存 recovery request id ⇒ 三实体从
   `GET recovery-cases/{id}/timeline` 取，并与桥跟踪的原 operation 交叉核对。

## 本任务实测发现（非本任务引入）

`materializing` 与 `forcesave_accepted` 两个已声明的桥状态在 Task 32 的实现里是
「两个 `apply()` 同步相邻」的中间态，公开面**永远观测不到**，因此状态条也永远
渲染不出它们。`workpaperSyncUiHarness.UNOBSERVABLE_BRIDGE_STATES` 登记了这个事实，
并由判据**反向自证**（驱动器对它们抛错）——不是豁免。
