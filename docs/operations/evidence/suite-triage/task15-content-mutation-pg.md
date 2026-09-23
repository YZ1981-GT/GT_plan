# Task 15 内容变更（content mutation）PG 测试集诊断

- 状态：进行中（根因已定位，正在修）
- 目标文件：`backend/tests/workpaper_sync/test_task15_content_mutation_pg.py`
- 兄弟文件：`backend/tests/workpaper_sync/test_task15_content_mutation.py` → **82 passed，全绿，无需处理**

## 运行前基线（实测）

```
rtk ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task15_content_mutation_pg.py -q --tb=line -rf -p no:randomly
46 failed, 3 passed, 1 warning in 8.86s
```

## 按根因分组的失败（1 个根因，46 个失败）

| 根因 | 失败数 | 形态 |
|------|--------|------|
| R1 `_JsonCarrierAdapter.verify_unmanaged_regions()` 不接受 `row_shift` 等位移感知 kwargs | 46 / 46 | 1 个 `TestHarness::test_no_harness_errors` 直报 `TypeError`，其余 45 个是同一次 `_collect()` 失败后 fixture dict 缺键的 `KeyError`（`snap["atomicity"]` 等全空） |

首条真实异常（`--tb=long`）：

```
AssertionError: 采集内部异常: [
  "business_commit: TypeError: _JsonCarrierAdapter.verify_unmanaged_regions() got an unexpected keyword argument 'row_shift'",
  "collect_aborted: TypeError: _JsonCarrierAdapter.verify_unmanaged_regions() got an unexpected keyword argument 'row_shift'"
]
```

`_collect()` 是**一次采集覆盖全部场景**的 session 级 harness：它在 `business_commit` 阶段就抛，
后面 45 条断言全部读不到自己那一段快照 → 46 个失败实为**一个**缺陷。

## ours vs pre-existing 判定：**pre-existing（不是本会话造成）**

证据（不靠标签，逐条实证）：

1. **调用方在工作树里零改动**。`rtk git diff HEAD --stat` 覆盖
   `content_mutation.py` / `test_task15_content_mutation_pg.py` 两个文件 → **均不在 diff 中**；
   本会话只改了 `adapters/excel.py`（+135）与 `materialize_coordinator.py`（+136）。
2. **`row_shift=` 这一串 kwarg 是已提交历史**。`git log -L 1700,1720:...content_mutation.py`：
   - `82f58ea44 feat(d4-ipo)` 引入 `row_shift` / `total_formula_rows` / `propagation`
   - `93892b99f fix(workpaper-sync)` 追加 `per_table_shift`
3. **HEAD 的真 adapter 早已有这 4 个可选形参**：`git show HEAD:...adapters/excel.py` 里
   `row_shift: Any = None` / `total_formula_rows: Any = ()` / `propagation: Any = None` /
   `per_table_shift: Any = None` 全在 → 与本会话对 `excel.py` 的改动无关。
4. **本会话 task 8/9/10 的三个怀疑点都排除**：
   - task 8 的 `_stage_cpu_segment_scoped` 拆分**已提交**且工作树无改动；它只是把同一段包进
     `workbook_read_scope()`，参数表逐字未变。
   - task 10 的 `MaterializeOutcome.reuse_verdict` 必填：**此路径不经 coordinator**。
     `_stage_cpu_segment_scoped` 直接 `adapter.materialize(...)` 并校验返回 `MaterializeResult`
     （不是 `MaterializeOutcome`）；替身的 materialize 阶段实测通过，异常发生在其之后。
   - task 9 未改生产代码。

结论：Task 3 的 A/B 差分把这簇标成 pre-existing 是**对的**，但它给的理由不完整 ——
真正的根因不在单趟改动附近，而是 adapter 契约本身的**欠声明**（见下）。

## 真正的根因：adapter Protocol 欠声明（生产侧缺陷）

`app/services/workpaper_sync/adapters/base.py` 的 `WorkpaperSyncAdapter` Protocol 声明的是：

```python
def verify_unmanaged_regions(
    self, *, before: Path, after: Path, contract: SyncContract
) -> UnmanagedRegionReport: ...
```

而唯一的编排调用方 `content_mutation._stage_cpu_segment_scoped` **无条件**多传 4 个位移感知
kwarg。于是：**任何严格照 Protocol 实现的 adapter（测试替身、将来的 Word adapter）一上线就
`TypeError`**。文档化的契约与调用方不一致，这是生产侧的契约缺陷，不是替身写错。

（`ExcelSyncAdapter` 之所以没事，只因为它自己把 4 个形参都加了默认值 —— Protocol 从未跟上。）

## 修复内容

（进行中）

## 运行后结果

（待填）
