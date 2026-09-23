# 残余三项失败 triage（residual-three）

日期：2026-06-01
范围：三项互相独立的残余失败，每项已有诊断与既定修法。

| # | 测试 | 失败用例 | 处置方向 |
|---|------|----------|----------|
| 1 | `test_task73_entry_profile_manifest.py` | `TestClosureGateConsumesProfileDrift::test_profile_drift_participates_in_the_blocking_total` | 重新生成派生特征化产物 `workpaperSyncLegacyBaseline.generated.ts`（须证明行为中性） |
| 2 | `test_task26_oo_to_html.py` | `test_coordinator_source_has_no_bare_warning_swallow` | 为 `finally` 中释放锁的惯用法加最窄 AST 豁免 + 自检 |
| 3 | `test_task28_sync_router_pg.py` | `TestFlushDoesNotAdvanceRevision::test_an_entry_without_an_approved_adapter_fails_visible` | 修 harness 隔离（方案 A），产物发布到生产真实读取的根下的按次子目录 |

状态：进行中（stub 已落盘，按项追加）

---

## Item 1 — task73 `test_profile_drift_participates_in_the_blocking_total`

### 根因确认

失败来自 `check_workpaper_sync_closure.py:121`：

```python
if baseline.get("manifest_digest") != manifest.get("manifest_digest"):
    raise ClosureGuardError("legacy characterization is stale for the current manifest")
```

overlay 批准后 manifest 重生成（`5c55208f…` → `afdffafd…`，hosts=154 mounts=244 entries=155），
而**派生**特征化产物未随之重生成。生成器 = `backend/scripts/gen/generate_workpaper_sync_legacy_baseline.py`
（`--check` / `--apply`），它一次写两份产物：

- `backend/data/workpaper_sync_legacy_baseline.json`
- `audit-platform/frontend/src/components/workpaper/sync/workpaperSyncLegacyBaseline.generated.ts`

改前 `--check`（真实输出）：

```
[SOURCE] entries=155 independent=142 template_only=135 reload_only=14 no_forcesave=135 no_ack=142 missing_adapter=138 single_with_switch=128
[FAIL] stale generated legacy baseline: ['backend\data\workpaper_sync_legacy_baseline.json', 'audit-platform\...\workpaperSyncLegacyBaseline.generated.ts']
```

同时确认 manifest 侧生成器**已同步**（不是它欠债）：
`generate_workpaper_sync_manifest.py --check` → `[OK] manifest digest afdffafd…`。

### 行为中性证明（重生成前先算差异，再决定是否落盘）

对「磁盘上的旧 baseline」vs「按新 manifest 现算的 baseline」逐 entry 比对
（`capability` / `migration_state` / `independent_entry` / `reason_codes` / 全部 `flags` /
`mode_switch_visible` / 证据 kind 集合）：

| 维度 | 结果 |
|------|------|
| 共有 entry 的裁决位移 | **`shifted_entries=0`** —— capability/migration_state/independent/flags/reason_codes/mode_switch_visible 全部逐字相同 |
| 证据 kind 集合位移 | **`kind_set_shifted_entries=0`** |
| entry 集合 | old=176 → new=155，`added=0`，`removed=21` |
| 被移除的 21 条 | 全是 `xlsx/d4/**` 的 `state=parent_duplicate`、`independent_entry=False`、`reason_codes=[]`；`contributing_removed_entries: NONE` |
| 聚合 stats | 仅 `entry_count` 176→155 变化；`independent(142)` / `template_only(135)` / `reload_only(14)` / `no_forcesave(135)` / `no_ack(142)` / `missing_adapter(138)` / `single_with_switch(128)` / `claimed_bidirectional_without_adapter(0)` **全部不变** |
| 仅证据差异的 entry | 29 条，变化键只有 `source_sha256` 和 `ui_characterization.evidence`（行号/片段随源码移动），无一条裁决变化 |

结论：这是对新 manifest 的**纯重新特征化** —— entry 分母收窄（上游已批准的 manifest 少了 21 条
parent_duplicate 影子 entry，它们对任何 independent 统计贡献为 0），加上源码 hash 与证据行号刷新。
没有出现 verdict/category 变化，因此**不触发**「停下来报告」的条件（与 task66 计划拒绝重生成的场合不同：
那次是裁决会变）。

### 无人钉住旧 digest

grep 旧 `baseline_digest 17c98f56…` / `source_digest 8db9feb4…` / 旧 `manifest_digest 5c55208f…`：
除两份产物自身外，仅出现在 `docs/.../_ms_diff.txt`（历史诊断快照）与 spec evidence README（历史记录）。
消费方 `workpaperSyncLegacyBaseline.spec.ts` 只断言 digest 形态 `/^[0-9a-f]{64}$/` 与「与 manifest
分母一致」，不钉具体值。无手改 digest。

### 改了什么

未改代码。用生成器自带命令重生成两份产物：

```powershell
..\.venv\Scripts\python.exe scripts/gen/generate_workpaper_sync_legacy_baseline.py --apply
```

```
[APPLIED] backend\data\workpaper_sync_legacy_baseline.json sha256=681beeeb99120f02
[APPLIED] audit-platform\...\workpaperSyncLegacyBaseline.generated.ts sha256=cc38452cb90b212b
[GENERATED] entries=155 independent=142 template_only=135 reload_only=14 no_forcesave=135 no_ack=142 missing_adapter=138 single_with_switch=128
[OK] baseline digest 8dbe2c3a592ca515fcce6b16e829265a58185911813a7f53666f5767014c1fe1
```

改后 `--check` → `[OK] baseline digest 8dbe2c3a…`（exit 0）。

### 改后测试

```
rtk ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task73_entry_profile_manifest.py tests/test_workpaper_sync_legacy_baseline.py -q -p no:randomly
→ 52 passed, 1 warning in 36.63s
```

### 附注：一条**先于本次改动即存在**的前端 spec 失败（非我引入，未扩大）

`workpaperSyncLegacyBaseline.spec.ts` 有 2 条 red，逐字比对 HEAD 与工作树后确认**改前改后完全一致**：

```
--- HEAD(before) ---   entry_count=176 spec_recount=132 stat=128 match=False
                       offenders(4)=['xlsx/gt-d2-accounts-receivable','xlsx/gt-d4-operating-revenue','xlsx/gt-g7-long-term-equity-main','xlsx/gt-h1-fixed-assets']
                       D2 capability=bidirectional reason_codes=['no_durable_forcesave_ack']
--- worktree(after) -- entry_count=155 spec_recount=132 stat=128 match=False
                       offenders(4)= 同上
                       D2 capability=bidirectional reason_codes=['no_durable_forcesave_ack']
```

成因：spec 把 `single_mode_switch_visible_count` 重算为 `independentEntry && modeSwitchVisible`，
**漏了生成器 flag 里的 `capability ∈ {single_html, single_onlyoffice}` 这一项**，于是 4 条已经
`bidirectional` 的 entry 被多计（132 vs 128）；同理 D2 有 adapter 后 `missing_adapter` 不再成立。
两条都不属本次三项范围，且我的重生成**修好了**该 spec 的第一条断言（分母 176→155 现与 manifest 相等）。
留待口径归属方裁决，未动其断言。

---

## Item 2 — task26 `test_coordinator_source_has_no_bare_warning_swallow`

### 根因确认（生产代码是对的，判据是代理判据）

`oo_to_html.py:2471`（`_apply_settled` 尾部，现读）：

```python
await self._repo.lock_room_oo_apply(state.frozen.room_id)
try:
    return await self._apply_settled_locked(state, adapter=adapter, merged=merged)
finally:
    try:
        await self._repo.unlock_room_oo_apply(state.frozen.room_id)
    except Exception:  # noqa: BLE001 — 连接已死时仍要让主异常冒泡
        pass
```

在 `finally` 里 `raise` 会用「解锁失败」**顶掉在飞的主异常**（连接已死时主异常恰恰是
真正的病因），诊断严格变差。守卫的代理判据「每个 `except Exception` 必须 `raise` 或
`_record_post_durable_failure`」覆盖不到「在 `finally` 里释放锁」这个惯用法 —— 所以是
判据欠一个口径，不是生产 fail-open。

改前口径复现（用老判据 = `ast.walk` 找 `ExceptHandler`、无豁免，跑现在的生产源码）：

```
改前口径 offenders = [2471]
```

### 改了什么（只改测试，生产代码一字未动）

`backend/tests/workpaper_sync/test_task26_oo_to_html.py`：

1. 抽出模块级 `_bare_swallow_offenders(source) -> list[int]`。改为遍历 `ast.Try` /
   `ast.TryStar` 再取 `node.handlers`（`ExceptHandler` 的父节点只可能是这两种，**覆盖面
   与原来 walk handler 等价**），这样才拿得到配对的 `try` 体 —— 豁免判据必须看它。
2. 豁免口径钉到最窄，两条**同时**成立才放过：
   - 处理块**恰好只有一条 `pass`**（`len(body)==1 and isinstance(body[0], ast.Pass)`）；
   - `try` 体**唯一一条语句**是 `[await] <obj>.unlock_room_oo_apply(...)`
     （`_is_sole_unlock_call`，按 `ast.Attribute.attr` 精确比对方法名）。

   刻意**不**按「任意 unlock」、「任意 finally」、「函数名」豁免。
3. 新增反向自检 `test_lock_release_exemption_does_not_admit_generic_swallows`：一份
   合成源码里放 5 种形态，断言只有豁免那一种不报 ——
   generic `except Exception: pass`（报）/ 豁免形态（不报）/ unlock + 多一条语句（报）/
   unlock 但处理块是 `logger.warning`（报）/ `finally` 里 unlock **别的东西**（报）。

### 变异验证：豁免不可能悄悄变宽

人为放宽 `_is_sole_unlock_call` 三种方式，反向自检全部报红：

```
baseline (未变异)                              -> GREEN
放宽成「任意 finally / 任意 try 体」            -> RED  (期待报 [5, 21, 27, 36]，实报 [27])
放宽成「try 体里出现 unlock 字样」              -> RED  (期待报 [5, 21, 27, 36]，实报 [5, 27])
放宽成「try 体只有一条调用即可」（丢方法名）      -> RED  (期待报 [21, 27]，期待 [5, 21, 27, 36])
生产源码 offenders = []
```

注意第一种放宽下 generic `except Exception: pass`（第 5 行）会被放过 —— 这正是「豁免变宽
就会漏掉普通吞异常」的证据，而自检把它逮住了。

### 改后测试

```
rtk ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task26_oo_to_html.py -q -p no:randomly
→ 134 passed, 1 warning in 1.48s
```

（含新增自检；改前该文件 1 failed。）

---

## Item 3 — task28 `test_an_entry_without_an_approved_adapter_fails_visible`

### 根因确认（诊断属实，生产是对的）

生产在这条路径上唯一的文件系统读是
`resolution.py:386 → CanonicalArtifactRepository.resolve_published_artifact()`，它
①`assert_canonical_resolvable` ②`resolve_relative_path` = `base_root / relative_path`
③`assert_project_owns` ④存在性检查。`pilot_d2_large_json` 按 BP-29 用
`CanonicalArtifactRepository(_BACKEND_ROOT)`（`_BACKEND_ROOT = backend/`），而
`relative_path` 自带 `storage/` 前缀。harness 原来把字节发布到
`CanonicalArtifactRepository(Path(mkdtemp("tmp_task28_store_")))` ⇒ 行在、文件不在生产读的
根下 ⇒ 生产**正确地** fail visible：

```
{"error_code":"artifact_publish_failed",
 "message":"published artifact 指针指向的文件不存在: storage/<project>/representations/
            xlsx/gt-d2-accounts-receivable/000000001-<hash>.xlsx（publish-then-commit 顺序被破坏，或已被 GC 误删）"}
```
（改前实测 body，记录于 `task27-28-router-conflict-pg.md:144`。）

取方案 **(A) 修 harness 隔离**。未取 (B)：把 `artifact_publish_failed` 加进可接受错误集合
会把 harness bug 供成不变式。

### 改了什么（只改测试）

`backend/tests/workpaper_sync/test_task28_sync_router_pg.py`：

1. 文件根改成生产读的那个根，并加**反漂移门**：
   `if PD2._BACKEND_ROOT.resolve() != _BACKEND.resolve(): raise _HarnessError(...)` ——
   根是照抄生产常量比对出来的，不是猜的。
2. 隔离改成「生产读的根**之下**的 per-run 子目录」：
   - `project = uuid.uuid4()` 提前生成；
   - `base_root = _BACKEND`（= `backend/`）；
   - `run_scratch_root = backend/storage/{project}`，`mkdir(parents=True, exist_ok=False)`
     —— `exist_ok=False` 让撞名立刻炸而不是复用别人的目录；
   - `storage_dirname` **保持生产默认**（必须：`assert_project_owns` 用默认 layout 算
     `storage/{project}/workpapers`，改了就被判 `cross_project_path`）；
   - 只把 `definition_dirname` 改成 `storage/{project}/definition_store`，让 teardown
     目标收敛成**一个**目录（definition blob 由 `resolve_relative_path` 读，不过归属门，安全）。
3. `artifacts = CanonicalArtifactRepository(base_root, layout=store_layout)`。
4. 删掉不再使用的 `import tempfile`；模块 docstring「独立文件根」那句改成事实。
5. 修掉事实性过期的 docstring：原写「manifest 里这个 entry 的 capability 也是
   `single_onlyoffice`」→ 改为「**现已是 `bidirectional`**」（本文件 `_STUB_DDL` 上方注释
   早已记载这次翻转）。

### teardown 究竟删什么（🔴 显式回答）

```python
_storage_root = (base_root / "storage").resolve()      # backend/storage
_victim = run_scratch_root.resolve()                   # backend/storage/{project}
if _victim.parent == _storage_root and _victim != _storage_root:
    shutil.rmtree(_victim, ignore_errors=True)
else:
    snap["harness_errors"]["scratch_teardown_refused"] = ...
```

**删的是且仅是 `backend/storage/{project}/` 这一个目录**（`{project}` = 本次运行现生成的
uuid4），连带其中的 `workpapers/`（`.staging` / `.versions` / `.incoming` /
`.upgrade-candidates`）与 `definition_store/`。

逐项目视检证明逃不出去：
- 唯一 `rmtree` 调用的实参是 `_victim`，`_victim` 由 `run_scratch_root.resolve()` 得来，
  且删除前断言 `_victim.parent == backend/storage` **且** `_victim != backend/storage`
  —— 空 `project`、`..`、指到 `storage` 本身、指到 `backend/` 全部落进 else 分支被拒并记账；
- 断言用的是 `resolve()` 之后的路径，字符串前缀骗不过去；
- 不存在第二个 `rmtree`/`unlink` 调用（原来那句 `shutil.rmtree(base_root)` 已删）。

**不删**：`backend/storage/` 本身、它的任何兄弟目录、`backend/definition_store/`、
`backend/` 下任何其他内容。真机上 `backend/storage/` 装着 700 个条目（数百个真实项目
UUID 目录 + `attachments` / `projects` / `workpapers` / `deliverables` / `definition_store`
/ `ledger_uploads` / `preview` / `qc_annual_reports`），原来那句 `rmtree(base_root)` 一旦
把根指向 `backend/` 就会连它们一起删 —— 这就是本项的高危点。

实测（同一次运行前后）：

```
backend/storage entries BEFORE = 700
backend/storage entries AFTER  = 700
project 目录里残留 definition_store 的：（无）
%TEMP%\tmp_task28_store_* 残留：0
```

`snap["harness_errors"] == {}`（拒删分支未触发，`test_no_phase_crashed_during_collection`
通过）。

### 改后测试：诊断的根因已修，但目标断言仍红（第二个独立缺陷）

```
rtk ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task28_sync_router_pg.py -q -p no:randomly
→ 1 failed, 46 passed, 1 warning in 19.51s
```

`artifact_publish_failed` **已消失**（文件现在找得到了，方案 A 生效、根因确证）。新 body：

```
{"detail":{"error_code":"published_identity_frozen_child_unusable",
 "message":"definition ecdae786-… 的 payload canonical digest 与 row 上冻结的
            'f28a47a1cc9705b2358acba412e615e807cc1b0c3b99c51dd5bd5c48f21a20ad' 不一致
            —— 已 approved 的 definition 不可被改写"}}
```

**这是另一个预存缺陷，不在授权范围内，故停手上报**（与 task66 计划那次同样的纪律）：

- `published_identity_observer._read_definition_payload` 要求
  `canonical_digest(parsed_payload) == child.sha256`；
- harness 的 definition blob 载荷是 `json.dumps({"k": name})`，而 definition row 的
  `sha256` 是 `_d("task28-instrumentation")` 这类**凭空编的**摘要（现读
  `test_task28_sync_router_pg.py` 的 `create_definition_artifact` 调用）—— 两条腿各自编，
  从不同源。这正是 `task27-and-share-parse-restore.md:87` 记录的同一族 harness 伪造问题
  （「三方锁的三条腿各自编」）。
- 即便把 digest 同源修好，下一关 `_frozen_sheet_anchors()` 还会要求冻结 instrumentation
  载荷里有真实的 `managed_sheets` / Excel Table / 隐藏 UUID 列锚点，并要求 artifact 是
  一份真的受管 workbook —— 那是 harness 保真度专项，规模远超「修隔离」。
- 顺带暴露一个值得裁决的**生产排序**问题：registry 零注册时，生产先做完整 published
  identity 观测、才轮到 adapter 可用性判定，所以 422 的 `error_code` 不落在
  `adapter` / `bidirectional` 上。断言是否该改，取决于这个排序是否是有意的 —— **未动断言**。

未弱化任何断言、未加 skip/xfail、未把 `artifact_publish_failed` 或
`published_identity_frozen_child_unusable` 塞进可接受集合。46 passed 与改前同一总数
（改前 46 passed + 1 failed），无新增红、无回归。

---

## 汇总

| # | 结论 |
|---|------|
| 1 | ✅ 绿。纯重新特征化（0 裁决位移），重生成两份产物，52 passed |
| 2 | ✅ 绿。生产代码未动；最窄 AST 豁免 + 反向自检（变异验证三种放宽全报红），134 passed |
| 3 | 🟡 授权的方案 A 已落地并验证（`artifact_publish_failed` 消失、teardown 收敛到一个子目录、700→700 无副作用）；目标断言仍红于**第二个独立预存缺陷**（definition digest 两腿各自伪造 + instrumentation 锚点缺失），按纪律停手上报，未弱化断言 |

### 附：本次改动清单

| 文件 | 性质 |
|------|------|
| `backend/data/workpaper_sync_legacy_baseline.json` | 生成物重生成（item 1） |
| `audit-platform/frontend/src/components/workpaper/sync/workpaperSyncLegacyBaseline.generated.ts` | 生成物重生成（item 1） |
| `backend/tests/workpaper_sync/test_task26_oo_to_html.py` | 测试：抽 `_bare_swallow_offenders` + 最窄豁免 + 反向自检（item 2） |
| `backend/tests/workpaper_sync/test_task28_sync_router_pg.py` | 测试：harness 文件根/隔离/teardown + 两处事实性 docstring（item 3） |

未触碰：`workpaper_sync_task66_legacy_deletion_plan.json`、`test_task66_legacy_deletion_plan.py`、
`test_task67_structural_pre_reconcile.py`、`test_workpaper_sync_program_milestones.py`、
`workpaper_sync_entry_overlay.json`、任何 `tasks.md`。生产代码零改动。
临时脚本（`_diff_legacy_baseline.py` / `_chk_switch_debt.py` / `_mut_swallow_guard.py`）用完即删。
