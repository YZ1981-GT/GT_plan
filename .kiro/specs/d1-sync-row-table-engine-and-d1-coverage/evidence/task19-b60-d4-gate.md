# Task 19：B60 / D4 过门（不声明化，只验证兼容）

**实施日期**：2026-09-26　**方法**：golden digest 门禁现测 + **真栈** D4 整册
materialize/extract/verify 闭环实跑（真库 `audit-postgres`，真实 generation=164 数据）。

## 一、结论：两项要求均已达成（真栈段首次跑通）

| 要求 | 结论 |
|---|---|
| B60/D4 的 digest 子集零变化 | ✅ golden digest 门禁现测 **75 个 digest 逐个不变**，B60/D4 均在其中且为 per-sheet 粒度 |
| D4 整册真 materialize + verify 全绿（30 受管 sheet） | ✅ 真栈实跑通过，`verify equivalent=True`，受管 sheet 数实测 **30** 与任务描述逐字相符 |

## 二、B60 / D4 digest 子集（`check_sync_provider_golden_digest.py` 现测）

```
✅ golden digest 零回归：75 个 digest 逐个不变
```

B60（`b60.hour_budget`，simple_checklist 形态）：
```json
{
  "contract_payload_sha256": "527e6e38ba3aaf6763867fd0b442821615940e3c5c7ab5fa2130bc000635cd0b",
  "sheet_digests": {"b601-managed": "299b30f8d7dade4913c33726beb85005911c950eb3ff52d40bf5a305b79e453b"},
  "store_projection_sha256": null,   // B60 无 build_store_projection，如实记 null 不假造
  "instrumentation_sha256": "5a29ef8e2bff9f551c2d3a1594a089dbe4180898aad6ba19140ddf2c2a4681b6"
}
```

D4（`d4.revenue_detail`）：`contract_payload_sha256` =
`9fa97e7f4e5546baa0b4ab158c68281f7a6fcc48b71f7f6bc6ffb91e2eafd3a8`，
**35 个 per-sheet digest**（含转置表等），逐个不变。

受管 sheet 计数实测（`instrumentation_specs()` 现算，非抄文档）：
* instrumentation spec 数 = **36**
* 去重 `managed_sheet` 数 = **30** ← 与任务描述「30 受管 sheet」逐字相符
* 差值 6 = 同 sheet 多受管区（D4-1 主营/其他 · D4-9 本期/上期 · D4-20 三区 ·
  D4-34 租金/咨询 · D4-36 顺查/逆查），正是 Task 24 参数化判据覆盖的那 5 张

## 三、D4 整册真栈闭环（脚本：`backend/scripts/e2e/verify_d4_full_book_real_stack.py`）

真实宿主：`project_id=0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49` /
`wp_id=b3ab3c46-828f-4f48-950e-aee9bbdc923f` / `entry_id=xlsx/gt-d4-operating-revenue`。

```
[①] attach=('d4.revenue_detail',) adapter_id='d4.revenue_detail'
[②] generation=164 substrate=000000164-98656478027d.xlsx size=259689
[③a] store item=46 有载荷=43 store values=1885
[③b] overlay_applied=True values=1185 表数=43 行数=433
[④] materialize OK 5.7s size=259689 row_shift=None
[⑤] extract OK 1.8s values=1185 表数=38
[⑥] verify OK 4.9s equivalent=True
[总计] materialize 5.7s + extract 1.8s + verify 4.9s = 12.4s
✅ D4 整册真栈闭环全绿（materialize + extract + verify equivalent）
```

四次连续实跑耗时稳定在 **11.7 ~ 12.4s**（materialize 5.2~5.7 / extract 1.6~1.8 /
verify 4.8~4.9），`equivalent=True` 稳定复现，退出码 0。

### 3.1 两条必须走对的路（走错则结论无意义，已在脚本 docstring 固化）

🔴 **必须走隔离式 attach，不能走全量注册**：共享的 `registry.register_from_manifest()`
会在轮到 D4 **之前**先炸在 `d2.receivable_detail` 的 `ContractDriftError`
（实测报错：`sheet='d21-managed' table='adjudication_cells'
field='adjudication_cells/aging_b' locator='B:static:10'`）。那是 D2 lane 的在途工作
（并发会话把 D2-1 加进契约后 live representation 尚未重物化），与 D4 无关。D4 单独
`attach_pilot_adapters()` 可达——这也是 D4 与 D1/D3/D5/D6/D7 的关键差异：
`adapter_registered=True` 仅 D4 成立（manifest slice 实测），其余五家 manifest capability
非 `bidirectional`，`attach_adapters()` 在任何 DB 查询之前短路返回 `()`。

🔴 **`before` 必须用真实 substrate 字节，不能用 `read_authoritative_template()`**：
这条真实数据已演化 164 代，权威模板与当前 representation 之间存在大量**合法**结构差异
（历史插行 / footer 重冻结坐标 / sibling ref 位移）。拿模板当 before 会把合法历史变化
逐字节判成 drift，判据失去意义。`verify_unmanaged_regions` 的语义是「**这一次**
materialize 有没有动不该动的字节」，参照系必须是这一次的输入。

## 四、如实登记的三项限制（不夸大本次结论覆盖面）

1. 🔴 **本次 `row_shift=None`** —— 这一跑没有触发结构性插行，因此**未**走通
   「同 sheet 多受管区插行 → 兄弟区 ref 位移」这条路径（Task 24 参数化判据守的正是它）。
   本次 verify 全绿证明的是「不插行场景下整册闭环无未管理区漂移」，**不等于**证明了
   多区插行路径在真栈无漂移。后者仍由离线判据
   `test_sibling_table_ref_row_shift.py`（16 用例）守护。
2. `extract` 反读出 **38 张表** 而 projection 有 **43 张** —— 差值 5 是
   HTML-only / dict-store item（不映射到 Excel Table），属既有设计
   （`html_only_item_ids` / `StoreKind.dict`），非丢数据。
3. 耗时 12.4s 显著低于代码注释里记录的历史值（materialize 42.8s / extract 60.8s）——
   本次 `row_shift=None` 走的是 `_try_single_pass_materialize` 单趟路径，且
   `BASELINE_EXTRACT_CACHE` / scoped workbook 缓存均命中；历史高值对应「逐趟链式 39 趟」
   的最坏情形。**不得**据本次 12.4s 断言性能问题已解决。

## 五、脚本落点与可重跑性

`backend/scripts/e2e/verify_d4_full_book_real_stack.py`（正式工具，无 `_` 前缀）。
需 `audit-postgres` 可连，**不需要**真后端进程。退出码 0 = 全绿。
放 `scripts/e2e/` 而非 pytest：它依赖真库特定 UUID，进 CI 会在无库环境必红——
同 `test_task5_d3_performance_baseline.py` 的定位差异（那条是 D3 lane 的 pytest，
本条刻意做成手动可重跑的脚本，不进任何 CI job 的 test 列表）。
