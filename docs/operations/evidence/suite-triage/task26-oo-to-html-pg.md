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
