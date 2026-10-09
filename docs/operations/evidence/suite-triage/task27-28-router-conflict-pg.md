# Suite triage: task27 conflict-resolution + task28 sync-router (PG)

状态：进行中（stub 先落盘，findings 随得随 append）

## 范围
- `backend/tests/workpaper_sync/test_task27_conflict_resolution_pg.py`
- `backend/tests/workpaper_sync/test_task28_sync_router_pg.py`
- 非 PG 兄弟 `backend/tests/workpaper_sync/test_task28_sync_router.py`（如成本低）

## 关键怀疑点（本会话改动）
本会话两次改 `backend/app/routers/wp_sync_router.py`：
1. task 10：`materialize` 端点加 2 个 metrics emit（`REUSE_METRIC` / `SINGLE_PASS_DECLINE_METRIC`）+ `single_pass_decline_scope()` 包裹 `coordinator.materialize(...)` + defect-class ERROR 日志
2. task 11：新增端点 `POST …/rooms/{room_id}/participants/{participant_id}/leave`（`leave_room`）

需判定：失败是"我们的回归"还是"预存"。Task 3 早前 A/B 差分把此簇标为预存，但那次 A/B 跑在 task 10/11 之前，不覆盖。

## 附加核查
`leave_room` 是否真的注册进 `backend/app/router_registry/`（定义但未注册 = 404 且测试无感知）。

---

## 运行记录（append）

### task28_sync_router_pg BEFORE
命令（cwd=backend）：
`rtk ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task28_sync_router_pg.py -q --tb=short -rf -p no:randomly`
结果：**8 failed, 39 passed**（10.90s）

失败 8 例按根因分组 —— **只有 1 个根因**：
```
ProgrammingError UndefinedTableError: relation "wp_index" does not exist
[SQL: SELECT s.current_representation_id AS rid
      FROM working_paper_sync_entry_state s
      JOIN working_paper wp ON wp.id = s.wp_id
      JOIN wp_index wi ON wi.id = wp.wp_index_id
      JOIN projects p ON p.id = wp.project_id
      WHERE s.entry_id = $1 ... ORDER BY wp.created_at, wp.id LIMIT 1]
[parameters: ('xlsx/gt-d2-accounts-receivable',)]
```
- 抛出点：`backend/app/services/workpaper_sync/projection_target_resolution.py:275`
  `resolve_visible_current_representation_id()`（BP-27 收敛出的**唯一**可见性口径）
- 调用链：router `_materialize_request` → `_registration` → `_attach_pilot_adapters`
  → `pilot_d2_large_json.attach_pilot_adapters`（其 `PILOT_ENTRY_ID` 正是测试 fixture 的
  `ENTRY = "xlsx/gt-d2-accounts-receivable"`）
- 2 个 harness 阶段崩（`pending_mutation` / `rollback`）→ 快照缺 2 个 scenario key →
  2 个 TestHarnessIntegrity + 2 个 TestFlushDoesNotAdvanceRevision + 4 个
  TestOpaqueVersionIdRollback 共 **8 例**全是这一个根因的下游。

### ours vs pre-existing 判定：**pre-existing（不是本会话回归）**
证据：
1. 失败与 route 表/metrics 集合/端点清单**无关**——错误是 PG `UndefinedTableError`，
   在 `_registration` 阶段就抛了，还没走到 task 10 的 metrics 或 task 11 的 leave_room。
2. 崩溃链上的文件**全部工作树未修改**（`git status --porcelain` 无这些条目）：
   `pilot_d2_large_json.py` / `projection_target_resolution.py` / `entry_profile.py` /
   `backend/data/workpaper_sync_entry_manifest.json`。
3. 触发条件是 manifest 的 D2 entry capability 已翻成 `bidirectional`
   （实测 `manifest_capability_enabled() == True`），使 pilot 的
   「capability 未启用就 return () 且一次库都不读」早退路径**不再生效** →
   首次真的去读库。该 manifest 最后一次改动在 **已提交** 的 `0c9eb40d6`
   （`git log -- backend/data/workpaper_sync_entry_manifest.json`），工作树 clean。
4. 本会话 `wp_sync_router.py` 的 3 个 hunk 分别落在 `materialize`(~870)、
   新 `leave_room`(~1491)、`_build_error_code_status`(~2966)，均不在
   `pending-mutations` / `versions/{id}/rollback` 路径，且没有任何 `wp_index` 查询新增
   （`git diff | Select-String wp_index` 为空）。

→ 结论：Task 3 早前 A/B 把此簇标 pre-existing 是**对的**，即使 A/B 跑在 task 10/11 之前，
本次独立复核（根因 + 工作树 diff 双重证据）仍得出同一结论。


---

## 🔴🔴 环境事件（最高优先，非我造成，需人拍板）

**本次排查进行中，工作区被并发进程改写：git 分支与 HEAD 变了，且有文件被回退到 HEAD。**

时间线（同一会话内、我未执行任何 git 写操作）：

| 时点 | 观测 |
|------|------|
| 开始 | `git status --porcelain` 显示 ~10 个 `backend/app/services/workpaper_sync/*.py` 为 **未暂存修改**（` M`），其中 `published_identity_observer.py` 含本会话 task 10 的 `share_parse=True` 改动 + 🔴 注释块 |
| 中途 | 我做了一次 2 行 A/B 实验：`share_parse=True` → `False`（用于判定 task27 根因是否为本会话回归） |
| 之后 | `git branch --show-current` = **`work/2026-09-14-d4-dual-mode-p0-fixes`**，`git log -1` = **`30622dfa3`**（`fix(oo-sync): 未改动切回结构化视图丝滑返回 + OO 画布停在目标 sheet + 修 flush 500`）；`git status` 里这些 service 文件**全部消失**，改动变成 **已暂存**（`M ` 第一列）状态；根目录多出已暂存的 `A  _t26.txt` |
| 现状 | `backend/app/services/workpaper_sync/published_identity_observer.py` **工作树 == HEAD**，`git log -1 -- <该文件>` = `3e894ed48`（旧提交）；文件里 **`share_parse` 一处都没有** |

⚠️ **`published_identity_observer.py` 的 `share_parse=True` 接线（spec 需求 2.1，task 10 产物）已从工作树消失。**
`phase5_transposed_sheet.py` 侧的 `share_parse: bool = False` 形参**仍在** ⇒ 当前是**半接线状态**：
能力做好了、调用点没开 ⇒ D4 单遍解析复用在这条路径上是死代码。

**证据表明不是我的 A/B 造成的**：我只把 2 行的 `True` 改成 `False`，而文件里连同我从未触碰的
🔴 注释块（`# 🔴 share_parse=True（spec oo-single-pass-materialize-and-room-leave 需求 2.1）…`）
一起消失了，且 `git diff` 对该文件为空、最后一次改动落在旧提交 `3e894ed48`
⇒ 发生的是**文件级 git 回退/切换**（`git checkout -- <file>` 或分支切换），不是我的编辑。

**我没有尝试修复它**：并发有其它 subagent 在写盘，且指令明确禁止 `git stash`；恢复别人的未提交
成果属于需要人拍板的高风险动作。**建议**：从 `git fsck --lost-found` / 编辑器本地历史找回该
call site，或直接重做 task 10 的这 2 行 + 注释（内容见上表，`share_parse=True` 两处）。

**对本次判定的影响**：task28 的 ours-vs-pre-existing 结论**不受影响**（根因链上的文件从头到尾
都没被本会话改过，且触发条件是**已提交**的 manifest capability 翻转）。task27 的归属判定
**受影响**：工作树现已 clean，无法再用「工作树 diff」做 A/B。

---

## `leave_room` 路由注册核查：✅ **已注册，无 404 缺口**

- 端点定义：`backend/app/routers/wp_sync_router.py:1493-1496`
  `@router.post(USER_SYNC_PREFIX + "/rooms/{room_id}/participants/{participant_id}/leave")`
  → 挂在 `router = APIRouter(...)`（同文件 `:174`），**不是**新建的 APIRouter 实例。
- 注册文件：**`backend/app/router_registry/workpaper.py`**
  - `:340` `from app.routers.wp_sync_router import router as wp_sync`
  - `:406` `app.include_router(wp_sync, tags=["渲染"])`
  ⇒ 复用已有 include，新端点自动进路由表，**无需新增注册行**。
- 实测路由表（`from app.main import app` 后过滤 `/leave`）：
  ```
  ['POST'] /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}/rooms/{room_id}/participants/{participant_id}/leave
  total_leave_routes = 1
  ```
  恰好 1 条、方法为 POST、路径与前端 `workpaperSyncContract.generated.ts` 的 `leave_room` 对齐。
  （注：FastAPI 不热加载 router，跑起来的服务需重启 `start-dev.bat` 才见到它。）

---

## 修复：task28_sync_router_pg — scratch schema 补齐生产可见性 SQL 所需的列

改动文件：**`backend/tests/workpaper_sync/test_task28_sync_router_pg.py`**（仅 harness，未动任何断言）
1. `_STUB_DDL`：`projects` 加 `is_deleted`；新建 `wp_index(id, project_id, wp_code, is_deleted)`；
   `working_paper` 加 `wp_index_id UUID NOT NULL REFERENCES wp_index(id)` 与 `created_at`。
2. 播种：每项目播 1 条 `wp_index`，两份 `working_paper` 都真实挂上它
   （生产语义：`wp_index` 是「底稿类型」维度，同类型可多实例 —— 正是
   `entry_state` 主键为 `(wp_id, entry_id)`、解析必须带全序的原因）。
3. 加了 ~18 行 🔴 注释说明这四项来自 `TARGET_VISIBILITY_SQL` / `VISIBLE_REPRESENTATION_ORDER_SQL`
   的逐字要求，以及「为什么这不是提前做 Task 30 的集成门」。

**没有放宽任何判据**：没有 skip/xfail，没有改断言，`wp_index_id` 建成 NOT NULL 且真实播种
（若建成可空/不播种，INNER JOIN 恒空 = 绕开可见性判据，那才是放宽）。

### task28_sync_router_pg AFTER
`8 failed, 39 passed` → **`1 failed, 46 passed`**（19.68s）

### 残留 1 例（已诊断，未改 —— 属设计取舍，不由我拍板）
`TestFlushDoesNotAdvanceRevision::test_an_entry_without_an_approved_adapter_fails_visible`
- 断言 `status == 422` **已通过**（fail-visible 不变量成立）；
  失败在后一句 `"bidirectional" in body or "adapter" in body`。
- 实得 body：`{"error_code":"artifact_publish_failed","message":"published artifact 指针指向的文件不存在: storage/<project>/representations/xlsx/gt-d2-accounts-receivable/000000001-<hash>.xlsx（publish-then-commit 顺序被破坏，或已被 GC 误删）"}`
- 根因：**harness 文件根隔离与生产读取根不一致**。harness 用
  `CanonicalArtifactRepository(Path(mkdtemp("tmp_task28_store_")))` 把字节发到临时根，
  而 `pilot_d2_large_json` 组装 adapter 时按 BP-29 用 `_BACKEND_ROOT`（= `backend/`）解析
  ⇒ DB 里的相对路径存在、文件不在生产读的那个根下 ⇒ 生产**正确地** fail visible 报
  `artifact_publish_failed`。同样是「capability 翻成 bidirectional 之后才可达」的预存问题。
- 该测试 docstring 已**事实性过期**：写着「manifest 里这个 entry 的 capability 也是
  `single_onlyoffice`」，而实测 `manifest_capability_enabled() == True`（= bidirectional）。
- 两条可选处置（建议由 spec owner 定，我没有单方面改断言以免把 harness 隔离缺口写进判据）：
  - **(A) 修 harness 隔离**：让 harness 发布到生产读取的根（`backend/` 下按 project uuid 建子目录，
    teardown 只 rmtree 该子目录）。⚠️ 现 teardown 是 `rmtree(base_root)`，直接改 base_root
    会变成 rmtree 整个 `backend/storage` —— **高危，必须同步改 teardown**。
  - **(B) 更新期望清单**：把 docstring 改到当前世界，并把可接受的 fail-visible 缺陷类扩成闭集
    `{adapter_not_ready / 非 bidirectional / artifact_publish_failed}`。风险：会把 (A) 的隔离缺口
    固化成判据，将来真的「adapter 没注册」回归时不一定打红。

### 非 PG 兄弟 `test_task28_sync_router.py`
**全绿**（与 task27 合跑 `133 passed`，24 failed 全部来自 task27）。
本会话对它的 12 行改动（task 11 的 leave_room 清单）是**对的**，不需要再动。

---

## task27_conflict_resolution_pg — 24 例、**单一根因**

### BEFORE / AFTER（未修，计数未变）
`24 failed, 32 passed`（21.22s）→ 复跑仍 `24 failed`（23.21s）

### 根因（1 个，其余 23 例全是下游）
```
ResolveApplyFailedError: 裁决落地失败(result=error,
  published_identity_frozen_child_unusable @ post_durable)
  @ conflict_resolution.py:579 <- conflict_resolution.py:1169
```
- `resolve_ok` 与 `resolve_via_duplicate` 两个采集阶段崩（同一错误）；
- `rollback` 阶段随后以 `ContentVersionNotFoundError: content version None` 崩
  —— 因为上一步没发布出新 content version（**是下游，不是第二个根因**）；
- 快照缺 3 个 scenario key ⇒ 6 + 5 + 5 = 16 例 `KeyError`，
  再加 2 例 `TestHarness` + 6 例直接断到 `apply_error_code` 的，共 **24**。

### ours vs pre-existing：**不是本会话的 `share_parse` 改动**（已实证）
A/B：把 `published_identity_observer.collect_workbook_structure` 里本会话新加的
`share_parse=True` 两处临时改成 `False` 后复跑 `TestHarness` ⇒ **同样 2 failed / 同一错误**。
（该临时改动随后被上文「环境事件」里的 git 回退一起抹掉，现工作树无残留。）

### 未定到具体抛出点 —— 以及为什么这本身是个可观测性缺口
`FrozenChildUnusableError` 在 `published_identity_observer.py` 有 ~18 个抛出点、
`publish_time_structure_hash.py` 有 5 个。而 `conflict_resolution._assert_apply_landed`
（`:579`）**只透传 `error_code` + `stage`，把观测器 `as_dict()` 里的 message/context 丢了**
⇒ 24 个测试红着，但没有一处能告诉你「为什么 frozen child 不可用」。
**建议**（小改、收益大）：把 observer 的 message/context 一并带进
`ResolveApplyFailedError`（或至少 `logger.error` 一条），否则这个簇每次都得靠手工插桩才能定位。

### 强怀疑（未证实）与 task28 残留同族
task27 harness 同样把 canonical store 隔离进 `mkdtemp("tmp_task27_store_")`
（`test_task27_conflict_resolution_pg.py:396`、`:457` `CanonicalArtifactRepository(base_root)`），
而 `FrozenChildUnusableError` 的抛出点里就包含「definition 的 blob artifact 不存在」
「slot digest 与 row sha256 不一致」「resolution service 未装配 artifact 仓储」这类
**artifact 仓储解析失败**。若 post_durable 观测走的是生产默认装配（根在 `backend/`），
就与 task28 残留那 1 例是同一个「harness 隔离根 ≠ 生产读取根」故事。
**下一步最省的探针**：在 `_assert_apply_landed` 抛错前打一条 `logger.error(observer_error.as_dict())`，
跑 `TestHarness::test_no_phase_crashed_during_collection` 一次即可定点。

---

## 合计

| 文件 | BEFORE | AFTER | 归属 |
|------|--------|-------|------|
| `test_task28_sync_router_pg.py` | 8 failed / 39 passed | **1 failed / 46 passed** | pre-existing（已修 7） |
| `test_task28_sync_router.py`（非 PG） | — | **0 failed** | 本会话 12 行改动正确 |
| `test_task27_conflict_resolution_pg.py` | 24 failed / 32 passed | 24 failed（未修） | 非 `share_parse` 回归；根因 1 个 |

**route 表 / metrics 集合 / 端点清单这三类「路由测试常见断言」在这两个文件里一个都没被触发**
—— task 10 的 metrics 与 task 11 的 leave_room **没有**造成这 32 例中的任何一例。
`leave_room` 已正确注册（`router_registry/workpaper.py:340` + `:406`，实测路由表 1 条 POST）。
前端 `workpaperSyncContract.generated.ts` 的 `leave_room` 条目与后端路径一致；后端侧没有
需要同步更新的闭集清单（新端点挂在已 include 的同一个 `APIRouter` 上）。

---

## task28 修复（option A）

上文「残留 1 例」的两条处置里，**(A) 修 harness** 已被采纳并推进了一层：artifact 文件根已收敛到
生产读的根（`base_root = _BACKEND` + per-run 子目录 `backend/storage/{project}/`），于是
`artifact_publish_failed` 消失、暴露出**下一层同族缺陷 —— harness 伪造 definition digest**。
本次修的就是这一层。**(B)（把 mismatch 加进可接受错误集合）继续被拒**：那会把 harness 自己的
digest 伪造供成不变式。

### 复现（verbatim，cwd=`backend`）
命令：
`..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task28_sync_router_pg.py -q --tb=short -rf -p no:randomly`

```
.............F.................................                              [100%]
==================================== FAILURES =====================================
_ TestFlushDoesNotAdvanceRevision.test_an_entry_without_an_approved_adapter_fails_visible _
tests\workpaper_sync\test_task28_sync_router_pg.py:1284: in test_an_entry_without_an_approved_adapter_fails_visible
    assert "bidirectional" in observed["body"] or "adapter" in observed["body"]
E   assert ('bidirectional' in '{"detail":{"error_code":"published_identity_frozen_child_unusable","message":"definition ddf251b1-9421-41d2-a589-8288... row 上冻结的 \'f28a47a1cc9705b2358acba412e615e807cc1b0c3b99c51dd5bd5c48f21a20ad\' 不一致 —— 已 approved 的 definition 不可被改写"}}' or 'adapter' in '{"detail":{"error_code":"published_identity_frozen_child_unusable","message":"definition ddf251b1-9421-41d2-a589-8288... row 上冻结的 \'f28a47a1cc9705b2358acba412e615e807cc1b0c3b99c51dd5bd5c48f21a20ad\' 不一致 —— 已 approved 的 definition 不可被改写"}}')
============================= short test summary info =============================
FAILED tests/workpaper_sync/test_task28_sync_router_pg.py::TestFlushDoesNotAdvanceRevision::test_an_entry_without_an_approved_adapter_fails_visible - assert ('bidirectional' in '{"detail":{"error_code":"published_identity_frozen_...
1 failed, 46 passed, 1 warning in 18.75s
```

### 诊断复核（成立）
生产判据唯一点：`backend/app/services/workpaper_sync/published_identity_observer.py:933`
（`_read_definition_payload`）—— 现读 blob 字节 → `canonical_digest(payload)` → 与 definition 行
冻结的 `sha256` 逐字比对。

harness 两侧各捏一遍，实测数值对得上：
```
python -c "import hashlib,json; ..."
literal sha256('task28-instrumentation') = f28a47a1cc9705b2358acba412e615e807cc1b0c3b99c51dd5bd5c48f21a20ad   ← 行上冻结值（= 报错里那个）
sha256(json.dumps({'k':'instr'},sort_keys=True)) = bafc9e063bf3eeb7d8e0ab8f8df7641a80f16e7825a10fb5ec1c8914b100fe0e ← blob 真实字节
```
⇒ 报错里的 `f28a47a1…` 正是 `_d("task28-instrumentation")`，与 blob 必然不等。与
`test_task27_conflict_resolution_pg.py` 已修的那一处**同族**（该文件工作树改动：新增
`_instrumentation_payload()` / `_instrumentation_digest()`，`_def_payload` 对 `instr` 返
`D.canonical_json_bytes(...)`，instr 行 `sha256=_instrumentation_digest()`，契约
`instrumentation_definition_sha256` 也换成同一 helper —— 三处同源）。

### 改动（diff，仅 harness，未动任何断言）
`backend/tests/workpaper_sync/test_task28_sync_router_pg.py`，3 处：

```diff
@@ 模块级，紧随 _d() 之后 @@
+def _instrumentation_payload() -> dict[str, Any]:
+    """instrumentation definition 的 canonical payload —— 本文件的**唯一**真源。
+    …（注释说明 :933 的 digest 复核，以及为何本文件不放结构锚点）…
+    """
+    return {"k": "instr"}
+
+
+def _instrumentation_digest() -> str:
+    """instr definition 行冻结的 `sha256`：由**生产 helper** 从 payload 派生。"""
+    from app.services.workpaper_sync import definitions as D
+
+    return D.canonical_digest(_instrumentation_payload())

@@ _collect()：definition blob 发布 @@
+        def _def_payload(name: str) -> bytes:
+            if name == "instr":
+                return D.canonical_json_bytes(_instrumentation_payload())
+            return json.dumps({"k": name}, sort_keys=True).encode()
+
         blobs = {
             name: artifacts.publish_definition_blob(
                 project_id=project, wp_id=wp_a, definition_kind=kind,
-                payload=json.dumps({"k": name}, sort_keys=True).encode(),
+                payload=_def_payload(name),
             )

@@ _collect()：instr definition 行 @@
             instr = await repo.create_definition_artifact(
                 kind="instrumentation", logical_id="task28.instr",
                 semantic_version="1.0.0", blob_artifact_id=art["instr"].id,
-                sha256=_d("task28-instrumentation"),
+                # 与 instr blob 字节**同源**（`_read_definition_payload` 的 digest 复核）。
+                sha256=_instrumentation_digest(),
```

**与 task27 的一处刻意差异（已写进代码注释）**：task26/27 的 payload 带结构锚点
（`managed_sheets` / `hidden_metadata_sheet`，取自 G1 真实 instrumented xlsx），因为它们的载体要被
观测器按锚点反读；task28 的 representation 是 `b"PK\x03\x04" + json`（`validate_ooxml=False`），
且观测顺序里 `_load_frozen_contract` 在 `_observe_workbook` **之前**就以 adapter 形态被拒
（见下），锚点根本读不到 —— 在这里补锚点等于让 harness 声称一份它并不持有的受管结构。

### 修复后端点实得的 422（已实测，非推断）
临时插一句探针断言（`assert "___probe___" in observed["body"]`，`-vv --tb=long`）取回完整 body，
随后已移除：
```
{"detail":{"error_code":"published_identity_frozen_child_unusable","message":"adapter 'xlsx/gt-d2-accounts-receivable' 的磁盘 per-entry contract 不可用: adapter_id 形态非法（不得含路径分隔或 `..`）: 'xlsx/gt-d2-accounts-receivable'"}}
```
链路：`_registration` → `attach_pilot_adapters` → `resolve_published_frozen_definitions` →
observer `observe()`：frozen_children（digest 复核，**现已通过**）→ `_read_published_bytes`（文件
已在生产根下，通过）→ `_load_frozen_contract` → `contracts.contract_path_for()` 按形态直接拒
（`adapter_id` 含 `/`）⇒ `FrozenChildUnusableError`，message 含 `adapter` ⇒ 断言过。

⚠️ **诚实标注（留给 spec owner，我没有改断言）**：`error_code` 仍是
`published_identity_frozen_child_unusable`（stage=`observe_workbook`），**不是** registry 那条
`adapter_not_ready`。测试断言是**文案级**（`"adapter" in body`），当前通过的理由是「这个 entry
的 adapter 在磁盘上没有可用 per-entry contract」—— 与 docstring「没有可用的 approved adapter ⇒
fail visible」语义一致，但不是同一个抛出点。若将来要把它收紧成 error_code 闭集判据，那是
断言层的设计决定，不在本次 harness 修复范围内。

### MUTATION-VERIFY（R01：把 digest 重新伪造回去，必须重新变红）
把 instr 行改回 `sha256=_d("task28-instrumentation")  # MUTATION-R01 临时伪造`，复跑同一命令：
```
.............F.................................                              [100%]
D:\GT_plan\backend\tests\workpaper_sync\test_task28_sync_router_pg.py:1322: assert ('bidirectional' in '{"detail":{"error_code":"published_identity_frozen_child_unusable","message":"definition 961938c9-e693-4c0c-99e7-294a... row 上冻结的 \'f28a47a1cc9705b2358acba412e615e807cc1b0c3b99c51dd5bd5c48f21a20ad\' 不一致 —— 已 approved 的 definition 不可被改写"}}' or 'adapter' in …)
1 failed, 46 passed, 1 warning in 19.24s
```
⇒ **RED 复现，且是与修复前逐字同款的那一条**（同 `f28a47a1…`、同 error_code、同计数
1 failed/46 passed）。证明这次不是「把测试改成无条件通过」。随后已还原，复跑 47 passed。

### 触类旁通：`backend/tests/workpaper_sync/` 同族反模式清扫
`json.dumps({"k"` + instr 行 digest 另捏一遍（或从契约取而非从 blob 派生）—— 全部命中如下。

| 文件 | blob | instr 行 `sha256` | 判定 |
|------|------|-------------------|------|
| `test_task28_sync_router_pg.py:354/388` | `{"k": name}` | `_d("task28-instrumentation")` | ✅ **本次已修** |
| `test_task27_conflict_resolution_pg.py:546` | `instr` 走 canonical | `_instrumentation_digest()` | ✅ 本会话先前已修（本次修复的镜像来源） |
| `test_task26_oo_to_html_pg.py:586` | 同上 | 同上 | ✅ 先前已修 |
| `test_task25_materialize_coordinator_pg.py:571` | `instr` 走 `instr_payload_bytes` | — | ✅ 先前已修 |
| `test_task29_timeline_evidence_pg.py:229 / :263` | `{"k": name}` | `_d("task29-instrumentation")` | 🟡 同族，**未修**（见下） |
| `test_task15_content_mutation_pg.py:490 / :576` | `{"k": name}` | `_d("task15-pg-instrumentation")` | 🟡 同族，休眠，未修 |
| `test_task12_resolution_pg.py:251 / :261,307` | `{"k": name}` | `sha["instr"] = _d("task12-instrumentation")`（注释自认「用固定标签生成」） | 🟡 同族，休眠，未修 |
| `test_task11_retention_orphan_pg.py:229 / :269` | `{"k": name}` | `_d("instr-def")` | 🟡 同族，休眠，未修 |
| `test_task38_excel_materialize_pg.py:244 / :290` | `{"k": name}` | `contract.instrumentation_definition_sha256` | 🟡 同族**变体**：digest 从契约取、不从 blob 派生，未修 |
| `test_task59_word_candidate_pg.py:225 / :272` | `{"k": name}` | `contract_payload["instrumentation_definition_sha256"]` | 🟡 同族**变体**，未修 |

**为什么这 6 个只列不修（不是偷懒，是三条实证理由）**：

1. **休眠而非活跃**：`:933` 的 digest 复核只在观测器真被调用时发生，而观测器由
   `pilot_d2_large_json.attach_pilot_adapters` 触发，只对 pilot entry
   `xlsx/gt-d2-accounts-receivable` 生效。实测这些文件的 `ENTRY` 分别是
   `g7.disclosure.listed`（task11/12/15）、`k11.adjudication`（task38）、word 候选（task59）
   ⇒ 那条路径结构性不可达，改 digest 不改变它们任何一条判据。
2. **唯一用 pilot entry 的同族文件 task29 今天红在别的根因**（实测，非推断）：
   `..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task29_timeline_evidence_pg.py -q --tb=line -rf -p no:randomly`
   → `41 failed, 3 passed`，`-x` 定位首因：
   ```
   AssertionError: {'collect': "EvidenceError: manifest 里没有 entry 'xlsx/d4/analysis/d4-tab-indicator' —— 未登记入口不得产出 evidence @ evidence.py:770 <- test_task29_timeline_evidence_pg.py:1176"}
   ```
   是 manifest 漂移（entry 已从 manifest 消失），与 digest 无关；digest 伪造被这道更早的门挡在
   后面。**同款最小修复在 task29 上不 apply cleanly**（修了也仍是 41 红），属另一个 triage 簇。
3. **task38 / task59 不是一行改动**：它们的 instr 行 digest 取自**契约声明**的
   `instrumentation_definition_sha256`，要修就得像 task27 那样把「契约字段 + blob 字节 + 行 sha256」
   三处一起换成同一 helper（三向锁）。在这两个**当前全绿**的文件上做三点改动，属于超出本次
   单缺陷授权、且有回归风险的动作。

### 计数（before / after）
| 文件 | BEFORE | AFTER |
|------|--------|-------|
| `test_task28_sync_router_pg.py` | 1 failed / 46 passed（18.75s） | **0 failed / 47 passed**（19.32s） |
| `test_task27_conflict_resolution_pg.py` | 56 passed（本次未动） | **0 failed / 56 passed**（24.55s）无交叉回归 |

两文件分别独立 invocation 跑（不合跑、不跑整个 `tests/workpaper_sync`）。
`get_diagnostics` 对改动文件为空。
