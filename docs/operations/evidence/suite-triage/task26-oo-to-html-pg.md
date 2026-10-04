# Task 26 OO→HTML (PG) suite triage

状态：进行中（stub，findings 持续追加）

- 目标文件：`backend/tests/workpaper_sync/test_task26_oo_to_html_pg.py`
- 兄弟文件（若廉价）：`backend/tests/workpaper_sync/test_task26_oo_to_html.py`
- 先前测量：约 49 failures
- 前提：task 3 A/B 差分已证明该簇与本次 single-pass write 改动无关（pre-existing），本次需快速复核

## 运行记录

（待追加）

### Run 1 (before) — 实测计数

```
rtk ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task26_oo_to_html_pg.py -q --tb=line -rf -p no:randomly
=> 49 failed, 50 passed, 1 warning in 21.60s
```

与先前测量一致（49 failures）。

### 主导错误签名（几乎所有 happy-path 失败共用）

```
error_code : published_identity_frozen_child_unusable
error_stage: post_durable
detail     : FrozenChildUnusableError: definition <uuid> 的 payload canonical digest
             与 row 上冻结的 '<sha>' 不一致 —— 已 approved 的 definition 不可被改写
trail      : published_identity_observer.py:933
          <- publish_time_structure_hash.py:201
          <- oo_to_html.py:2531
          <- oo_to_html.py:2465
```

注意：`published_identity_observer.py` 属于本 session 改动文件之一 → 需判定是否与 task 3 A/B 结论冲突。

## A/B 复核结论（与 task 3 一致：pre-existing）

`rtk git status --short` 显示本 session 改动的 workpaper_sync 文件中，只有
`published_identity_observer.py` 出现在失败 trail 上。其 diff **仅** 为
`collect_workbook_structure` 内两处 `share_parse=True`（+12/-2），**不涉及**
`_read_definition_payload`（L909-939）的 digest 复核逻辑。
`publish_time_structure_hash.py` / `oo_to_html.py` / 本测试文件均未被本 session 改动。
⇒ 本簇失败与本 session 的 11 个 task 无因果关系，确认 pre-existing。

## 根因分组

### 根因 A（≈49 failures 的第一道墙）— 测试夹具从未随 BP-30 迁移

BP-30（commit `0565cd5b9`「修复 structure_hash 语义分裂」）把 xlsx projection
commit 路径改成：`content_mutation._projection_structure_hash` →
`compute_structure_hash_from_artifact` → `collect_workbook_structure`
→ 读**冻结 instrumentation definition payload** 的 4 个反读锚点，从「要发布的
xlsx 字节」实测受管结构。

该迁移同步更新了 `test_task25_materialize_coordinator_pg.py`（引入共享夹具
`tests/workpaper_sync/g1_structure_fixture.workbook_fixture()` + `_instrumentation_payload()`），
但 **Task 26 的 harness 没有被一起迁移**，仍是 BP-30 之前的形态：

| 位置 | BP-30 前（Task 26 现状） | 不变量要求 |
|---|---|---|
| instr blob 字节 | `json.dumps({"k": "instr"})` | 必须是真实 instrumentation payload 的 canonical 字节 |
| instr definition 行 `sha256` | `_d("task26-instrumentation")`（标签哈希，凭空取值） | 必须 == `canonical_digest(payload)` |
| 契约 `instrumentation_definition_sha256` | 同上标签哈希 | 三向锁要求同源 |
| 载体 `_ooxml()` | `xl/workbook.xml = <root/>` 空壳 | 必须是真 xlsx（Excel Table + 隐藏 uuid 列 + veryHidden 元数据表），否则 openpyxl 反读不出结构 |

⇒ `_read_definition_payload` 的 digest 复核必抛 `FrozenChildUnusableError`。

**判定：改测试，不改生产。** `canonical_digest(payload) == child.sha256` 是
「已 approved 的 definition 不可被改写」的防篡改不变量，削弱它等于废掉冻结身份链；
而夹具那个 `_d("task26-instrumentation")` 与它指向的 blob `{"k":"instr"}`
**从来就不自洽**，属于内部矛盾的 fixture，不是对生产行为的期望。

修复（全部在测试文件内，未动任何断言）：
- 引入 `g1_structure_fixture.workbook_fixture(sheet_key="d2-detail")` 作真实受管载体
- 新增 `_instrumentation_payload()` / `_instrumentation_digest()`，四锚点取自夹具
- instr blob 改 `D.canonical_json_bytes(...)`；instr 行与契约 digest 改同源取值
- `_ooxml()` 改为「真夹具字节 + 追加受管部件」，6 个调用点签名不变
- 合成的「未管理区域」部件由 `xl/unmanaged.xml` 移到 `_gt_sync/unmanaged.xml`
  （`[Content_Types].xml` 不声明它，摆在 `xl/` 等于赌 openpyxl 的容忍度）

### 根因 B — harness adapter 的 `verify_unmanaged_regions` 签名过期

修掉 A 后流程推进到 materialize，暴露第二道：

```
TypeError: _JsonCarrierAdapter.verify_unmanaged_regions() got an
unexpected keyword argument 'row_shift' @ content_mutation.py:1705
```

生产已按 D4 行位移治理传入 `row_shift` / `total_formula_rows` /
`propagation` / `per_table_shift`，Task 26 的替身仍是三参老签名。
同属「夹具未随生产协议演进」类，改测试。

### 根因 C — close-capture 的 contributor 快照方向反了（PG 最后 4 红）

修掉 A、B 后剩 4 红，全在 `TestCloseCaptureEligibilityFence`，且**都不是**它们各自
判据失败，而是统一停在更靠前的一道 fence：

```
error_code: final_fence_contributor_snapshot_drift
（期望 final_fence_eligibility_epoch_advanced / applied）
fence_compared_before_publish: []   ← eligibility 判据一条也没跑到
```

生产侧 `repository.reconcile_close_intents`（L2953-2971）对 close-capture **刻意冻结
空集** contributor digest，注释写明两条理由：幂等键
`close-capture:{room}:{gen}:{epoch}` 要求 fingerprint 只由 `(room, generation)` 决定；
以及 `record_contributor_snapshot()` 在生产链路上零调用方 ⇒ 观测侧恒为空集。
并附警告：

> 改成「room 现存 edit participant 集合」前必须先接上 `record_contributor_snapshot()`：
> 否则冻结非空、观测为空，每次 clean close 都会在最终 fence 被拒

Task 26 的 `_stage_close_capture` 恰好踩了这条警告的**反方向**：它在 promotion 之后
补调 `record_contributor_snapshot()`，写进一行 live contributor ⇒
`_recompute_contributor_digest()`（oo_to_html.py L2060-2105，按
`p.state IN ('active','closing')` 过滤 live 行）观测到非空，而冻结侧是空集 ⇒ drift。

**判定：改测试。** 生产的取值是为幂等显式论证过的，且自带警告；夹具那次补记
与 close-capture 的冻结口径相矛盾。普通 forcesave 仍在 `_build_room` 侧记录
（冻结值同源），两条路径各自自洽。修复 = `_stage_close_capture` 不再补记
contributor snapshot（保留 `mint_route_credential`，req 仍需 credential）。

## before / after（实测命令输出）

```
# before
..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task26_oo_to_html_pg.py -q --tb=line -rf -p no:randomly
49 failed, 50 passed, 1 warning in 21.60s

# after
..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task26_oo_to_html_pg.py -q --tb=line -rf -p no:randomly
99 passed, 1 warning in 23.86s
```

## 兄弟文件 `test_task26_oo_to_html.py`（非 PG）

before 4 failed / 129 passed → after **1 failed / 132 passed**。
这 4 条与 PG 那 49 条**不同类**：全是「读生产源码断言形态」的硬化守卫，随生产重构失锚。
定性为 pre-existing 的依据：`content_mutation.py` 最近一次提交是 `34eb8fc59`
（本 session 之前），且它从未出现在本 session 的 dirty 列表里。

已修 3 条（均**未削弱**判据，反而修回一条已空转的）：

1. `test_resolutions_reach_the_commit_boundary`
2. `test_conflict_resolution_source_bucket_is_distinguishable`
3. `test_settle_branches_are_the_single_decision_point` —— 它当时是 **假绿**：
   G4-0d 把发布分支拆成 `_apply_settled`（决策+取锁）+ `_apply_settled_locked`
   （锁内 commit）后，`merge.merged` 搬去了后者，只看前者的判据恒真。
   → 新增 `_settled_branch_ast()`，把两段源码拼起来 walk，并在方法改名时**判红**而非少查。
4. `test_before_publish_is_called_between_unmanaged_check_and_publish` —— `34eb8fc59`
   把 CPU 段（materialize→extract→unmanaged→structure hash）搬进
   `_stage_cpu_segment{,_scoped}` 由 `asyncio.to_thread` 卸载，`_stage_and_verify`
   里再也 index 不到 `unmanaged.assert_equivalent()` ⇒ `ValueError: substring not found`
   （判据失锚而非判红）。→ 改为跨方法证明：段内证「未管理区域比对在 CPU 段里」，
   段外证「cpu_segment → fence → publish」。

## 仍红 1 条 —— 需裁决，未擅自改（`test_coordinator_source_has_no_bare_warning_swallow`）

守卫规则：`oo_to_html.py` 里每个 `except Exception` 处理块必须出现 `raise` 或
`_record_post_durable_failure`。唯一 offender 是 `oo_to_html.py:2471`：

```python
finally:
    try:
        await self._repo.unlock_room_oo_apply(state.frozen.room_id)
    except Exception:  # noqa: BLE001 — 连接已死时仍要让主异常冒泡
        pass
```

这是 G4-0d 的 advisory lock 释放。**生产在这里是对的**：在 `finally` 里 `raise`
会用「解锁失败」顶掉正在冒泡的主异常，严格更差，也与行内注释的意图相反。
问题在守卫用的**代理判据**（必须 raise / 落终态）覆盖不到「finally 中释放锁」这个惯用法。

建议（未实施，等裁决）：把豁免收到最窄——仅当处理块体恰为 `pass`
**且** 其 `try` 体唯一语句调用 `unlock_room_oo_apply` 时放行。其余任何位置的
fail-open swallow 照旧判红，豁免口径只有一个函数名宽。
之所以不擅自改：这是往 fail-open 硬化守卫上开豁免口，属于需要 ratify 的设计决定。

## 没有发现「陈旧固定证据」（manifest / source_commit / 内容哈希）类失败

本簇没有需要跑刷新命令的钉证据。`_d("task26-instrumentation")` 形似固定哈希，
但它不是「随生产源码变化而过期的证据」，而是一个**从未与其 blob 自洽**的凭空标签值，
所以按夹具缺陷修正、而非按刷新证据处理。

## 与其他 subagent 的交叉

根因 A（夹具未随 BP-30 迁移到真实 instrumentation payload + 真 xlsx 载体）与根因 B
（`verify_unmanaged_regions` 老签名）是**通用类**，很可能同样解释
`test_task27_conflict_resolution_pg.py` / `test_task28_sync_router_pg.py` 的失败 ——
`conflict_resolution.py:1436` 同样调 `load_frozen_structure_anchors`。
按分工未改那两个文件，仅在此报告。可直接参照的正确样板：
`tests/workpaper_sync/test_task25_materialize_coordinator_pg.py` L160-240。
