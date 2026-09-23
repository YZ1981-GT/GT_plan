# Task66 三件套失败三角 — BP-66-2 该不该解除？

- **结论：不解除、不重生成。** 释放判据本身**已满足**，但「重跑生成器」这条**释放动作现在跑不得**，
  且重跑**也清不掉那 14 红**。详见 §5 的三条阻塞。
- 范围：`test_task66_legacy_deletion_plan.py`(14) / `test_task67_structural_pre_reconcile.py`(6) /
  `test_task68_backend_chain_regression.py`(1) —— 实测基线 **21 failed / 200 passed**（223s）
- 取证方式：全部现算。`build_record()` 在内存里跑一遍（**未** `--write`），逐字段与磁盘记录比对；
  git 事实用 `ls-files` / `ls-tree -r HEAD` / `log --diff-filter=A|D` 逐路径复核
- 未触碰：`workpaper_sync_entry_overlay.json`、`test_workpaper_sync_program_milestones.py`、`tasks.md`；
  未加任何 skip/xfail、未放宽任何断言、未手改任何 hash/digest、未跑全量套件

---

## 1. BP-66-2 是什么 —— 逐字

声明处：`backend/scripts/gen/generate_task66_legacy_deletion_plan.py`
§11「阻塞前置（BP-66-n）」`build_blocking_preconditions()`，L2411 起。**它不是手工登记表，是每次现算的派生项**。

```
"id": "BP-66-2",
"title": "替代面自身未入库 ⇒ rollback 隔离门 blocked",
"statement": f"{len(untracked)} 个替代面模块在 plan commit 上是 git `??` 未跟踪；"
             "「删 legacy 保 replacement」这笔事务整体不可逆",
"owner_task": "72",
"blocked_paths": sorted(untracked),
"release_condition": "替代面全部入库后重跑本生成器，门自动转 open",
"evidence": ["`git ls-files` 现算 tracked 集合",
             f"rollback 门 verdict = {rollback_gate['verdict']}"],
```

**释放判据（逐字）**：`替代面全部入库后重跑本生成器，门自动转 open`
⇒ 拆成两个可分别判定的条件：**(a) 替代面全部入库**；**(b) 重跑生成器**。

释放惯例（找同族先例，不自创）：`oo-html-bidirectional-writeback-5-lane-assignment.md` §7 对 BP-18 的定性是
「**派生状态，无需裁决** … 会随 L1 完成而解除」、「**不要动那一行**」。即本仓的约定是
**派生 BP 不手工解除，靠重跑生成器让度量自己翻转**；判据写死成常量是明令禁止的反模式
（`mutate_task68_backend_chain_regression_guards.py`：「🔴 BP-68-2 的度量值写死成常量 …
会在供给到位后**静静过期**」）。

---

## 2. 条件 (a)「替代面全部入库」—— ✅ 已满足（独立复核通过）

22 条路径全部落在同一个 commit：

```
42d2f6e6f  2026-09-02  feat(workpaper-sync): HTML<->OnlyOffice 双向回写闭环 spec 全量产物入库（Task 1~77，72/77 完成）
   └── 22 / 22 条替代面路径的首次 A（add）commit 都是它
```

逐路径核对（不只看 index，**同时看 HEAD tree**，因为 `git ls-files` 只反映索引，
仅 `git add` 未 commit 也会判 tracked，而 `restore_command = git checkout <HEAD> -- <path>` 需要 blob 真在 commit 里）：

```
NOT_in_index     = 0 / 22
NOT_in_HEAD_tree = 0 / 22
```

21 条为 `audit-platform/frontend/src/components/workpaper/sync/**`（7 个 .vue + 14 个 .ts），
第 22 条为 `backend/app/routers/wp_sync_router.py`。

顺带复核 `pending_delete_unrecoverable 2 → 0` 的来源：
`sync/usePilotBridgeAdapter.ts` 同样由 `42d2f6e6f` 入库（DISK_YES / HEADtree=True）——
这 2 项转 0 是**真事实**，不是度量漂移。

**⚠ 一处削弱**：22 条里 `sync/workpaperSyncManifest.generated.ts` 当前工作树是 `M`（已改未提交）。
门判据 `replacement_surface_is_itself_recoverable` 只测 `git ls-files` 成员关系 ⇒ 会判 `passed=True`，
但该文件**当前内容不在任何 commit 里**，记录的 `restore_command` 会还原成**另一份**。
门按自己的定义没说错，只是对这一条**言过其实**。

---

## 3. `blocked → open` 的语义 —— 从源码定死，`open` 是**好**状态

`build_rollback_gate()`（同文件 L2205 起）自带 `verdict_meaning`，逐字：

```
"verdict_meaning": (
    "`open` = Task 72 Stage B 在 rollback 维度上可执行（其余门由 Stage A 把守）；"
    "`blocked` = 至少一条约束被违反，Stage B 若照删则该项不可逆"
),
"what_this_gate_does_not_certify": [
    "不认证未裁决/假双向/未验收/stale 五个零（Task 67 报告 + Task 72 Stage A）",
    "不认证任何真实 OO probe 已通过（Task 70）",
    "不授权删除：本任务只生成计划",
],
```

`verdict` 的算法是 `"open" if all(c["passed"] for c in checks.values()) else "blocked"` —— 六条约束全过才 open。

**裁定：`open` = 「回滚现在办得到」，不是「回滚隔离不再有保障」。** 三条独立佐证：

1. `verdict_meaning` 明写 open 是「**可执行**」、blocked 是「若照删则**不可逆**」——
   `blocked` 才是危险面，`open` 是危险面消失。
2. 2 项 `rollback_target.mode` 由 `pre_delete_snapshot_required` → `git_blob_at_plan_commit`：
   读 `_rollback_target()`（L1173）——`mode` 只是 `tracked` 的三元投影，
   `tracked=False` 时 `restore_command` 是「（未跟踪：Stage B 前必须先入库或落文件快照，否则删除不可逆）」，
   `tracked=True` 时是 `git checkout <plan_commit> -- <path>`。
   即这两项从「**得先自己造快照**」升级为「**git 里就有 blob**」，是**严格变好**。
3. 下游不会因此自动放行删除：`check_task72_pre_delete_eligibility_gate.py` 只把
   `rollback_isolation_verdict` 当**观测值**记进 landing/report（L574 / L1029 / L2286），
   而 `legacy_delete_gate_released` 是**硬编码 False**（L2509），`gate_can_go_green` 另由 Stage A 八条谓词决定。

⇒ 「用一条生成命令解除一个安全门」这个担忧**不成立**：翻 open 不解除任何删除授权。
前一轮把 verdict 翻转标成 🔴🔴 是**误判方向**（该轮自己也注明「flagged 但未 resolve」）。

---

## 4. items +2 / −1 是真的（逐条 git 复核）

| 变化 | 复核结果 |
|---|---|
| **−1** `legacy_composable:…/composables/useG7LonTerDualMode.ts` | ✅ 该文件由 **`42d2f6e6f` 删除**（`--diff-filter=D` 命中），DISK_NO / HEADtree=False；同目录只剩 `useG7LonTerFormData.ts` / `useG7LonTerFormulaEngine.ts`。legacy 文件真没了，条目该下线 |
| **+2** `legacy_state_machine:…/sync/useD2SyncBridge.ts` + `legacy_local_storage_key:workpaper-sync-mode:@duplicate_writer:…/sync/useD2SyncBridge.ts` | ✅ 真实现存代码：`audit-platform/frontend/src/components/workpaper/sync/useD2SyncBridge.ts`，HEADtree=True，338 行，L196/L204/L206 真有 `localStorage` 的 html/oo 模式持久化，L32 `D2SyncMode = 'html' \| 'onlyoffice'`。由 `a2706e1d6` / `cee7ed518` 两次 D2 修复带入 |

值得单独记一笔：这两条新项**落在替代面目录 `sync/` 内部**，
即**替代面自己开始携带 legacy dual-mode 形态**（`@duplicate_writer` 标记的重复写者）。
这是一条**新发现**，不是清册漂移，应进 Task 67/72 的视野。

---

## 5. 条件 (b)「重跑本生成器」—— 🔴 现在跑不得，三条阻塞

内存现算 vs 磁盘（`--check` 语义，未落盘）：

```
verdict       blocked -> open        （六条 checks 全 passed，failing = []）
plan_commit   d330d7cea -> fb7a0ace2

form_unconsumed_bridge_subjects                    19  -> 2
items_total                                       215  -> 216
items_disposition_pending_delete                  207  -> 208
manifest_entry_total                              186  -> 155      🔴
manifest_entry_with_adapter                         0  -> 4        🔴
pending_delete_unrecoverable                        2  -> 0
replacement_surface_modules                        22  -> 24
replacement_surface_untracked                      22  -> 0
replacement_surface_unreachable_from_production_host 19 -> 2
single_switch_entries                             132  -> 128
```

### 🔴 阻塞一：`manifest_entry_total` 是**活动靶**，且 155 这个数**不在任何 commit 里**

```
HEAD (fb7a0ace2) : 176
0c9eb40d6        : 176
工作树            : 155      ← `M backend/data/workpaper_sync_entry_manifest.json`（并发泳道在改）
```

前一轮量到 176，**本轮量到 155** —— 同一个数在两次取证之间又掉了 21。
生成器从**磁盘工作树**读 manifest，却把 `plan_commit` 绑成**当前 HEAD**。
一旦 `--write`，产物会声明 `plan_commit = fb7a0ace2` 同时记 `manifest_entry_total = 155`，
而从 `fb7a0ace2` 只能复算出 **176** ⇒ **三边锁在出生那一刻就是假的，且任何人都复算不出来**。
这不是「清册过期」，是**产物自述不可复现**。
（同源信号：`workpaper_sync_entry_overlay.json` 也在 `M`，且由另一会话刚批准 —— 供给侧明确在途。）

### 🔴 阻塞二：`--write` **清不掉那 14 红**，反而会把一条现在绿的判据打红

`build_blocking_preconditions()` **无条件**吐三条 BP，不会因度量归零而下线。现算后 BP-66-2 长这样：

```
ID BP-66-2  blocked_paths=0
   stmt: 0 个替代面模块在 plan commit 上是 git `??` 未跟踪；「删 legacy 保 replacement」这笔事务整体不可逆
   ev  : rollback 门 verdict = open
```

一条「违反项 0 条、门已 open」却仍断言「整体不可逆」的阻塞前置 —— **产物级自相矛盾**。
于是：

- `TestRollbackIsolationGateIsMeasured::test_the_gate_is_currently_blocked_for_a_recorded_reason`
  （L863，断言 `failing` 非空）**当前是绿的**，`--write` 后现算 `failing == []` ⇒ **它会变红**。
  它的断言消息本身就写着「门已经全过了 —— 若替代面真的都入库了，请同步解除 BP-66-2 **并更新本判据**」。
- `TestFiveBindingsArePresentAndSound::test_rollback_target_helper_distinguishes_tracked_from_untracked`
  （L526）把 `sync/usePilotBridgeAdapter.ts` 硬编码成「未跟踪」对照组，该路径已入库 ⇒
  **这条红与产物无关，`--write` 也修不了**，必须换一条真未跟踪的对照路径。

⇒ 「重生成即可清 14+6+1」的前提**不成立**：至少 2 条需要改生成器/判据，重跑只是把红换个位置。

### 🔴 阻塞三：`--write` 会顺手吞掉**别人家的** BP-66-3

`manifest_entry_with_adapter 0 → 4` 是 authority model 供给侧的**状态翻转**
（`check_task61_oo94_word_pilot_gate.py` L2492 已独立记过同一事实，并明确「**BP-61-1 是否已解除不在此处裁决**」）。
BP-66-3 的 `owner_task` 是 **70**，不是 66。更糟的是它的 `statement` 把 **186 写死在 f-string 里**：

```
f"manifest 186 个 entry 里 adapter_id 非空 {adapters} 个、approved bundle 供给为 0，…"
```

`--write` 后产物会同时出现「manifest **186** 个 entry」与 `manifest_entry_total: **155**`。
这正是本仓反复点名的假绿第③源（拿旁路观测值/写死常量当门禁基线）。

---

## 6. 决定与解锁顺序

**不重生成、不解除 BP-66-2。** 21 红是**绊线正常工作**，维持现状。

BP-66-2 的判据 (a) 已满足、`open` 语义也已确认无害 —— 唯一缺的是**一个能诚实执行释放动作的时刻**。
按本仓「派生 BP 随重跑自动解除」的惯例，解除需要下面四步**一次做完**（顺序不可换）：

1. **等并发泳道收口**：`workpaper_sync_entry_manifest.json` / `workpaper_sync_entry_overlay.json`
   落 commit，使 `manifest_entry_total` 稳定且**与 `plan_commit` 可互相复算**
   （`git show <plan_commit>:…` 的 entry 数 == 产物记的数）。这是阻塞一的唯一出口。
2. **补生成器的两个缺口**（不是放宽判据，是让判据说真话）：
   - `build_blocking_preconditions()` 在 `untracked == []` 时把 BP-66-2 落成**已释放**形态
     （或从 blocking 列表移出、进一个 `released_preconditions` 并记 release commit `42d2f6e6f`），
     不再输出「0 条违反 + 整体不可逆」。
   - BP-66-3 `statement` 里写死的 `186` 改成现算 `len(manifest.entries)`。
3. **同步更新两条判据**（按 L870 断言消息的明文要求）：
   `test_the_gate_is_currently_blocked_for_a_recorded_reason` 改为「门已 open ⇒ BP-66-2 必须登记为已释放、
   且 Stage A 仍把守删除授权」的正向判据；`test_rollback_target_helper_…` 换一条**真未跟踪**的对照路径。
4. 最后才 `..\.venv\Scripts\python.exe scripts\gen\generate_task66_legacy_deletion_plan.py --write`
   （cwd=`backend`），再依次跑 task66 → task67 → task68。

另需一并裁决（不在本文件权限内，需人拍板）：
`manifest_entry_total` 176 → 155 是否为**预期终态**（D4 退网同族），以及
`sync/useD2SyncBridge.ts` 自带 legacy dual-mode 形态该由谁收（§4 末）。

## 7. 本次动作清单

- 只读取证：`build_record()` 内存现算、`git ls-files` / `ls-tree` / `log`、三个测试文件实跑
- **未**执行 `--write`；**未**修改任何生成器 / 判据 / 产物 / JSON
- 唯一落盘：本文件
- 基线（before，无 after —— 未行动）：`21 failed / 200 passed`，
  分布 task66 **14** / task67 **6** / task68 **1**
