# Task 15 内容变更（content mutation）PG 测试集诊断

- 状态：**已修复，全绿**
- 目标文件：`backend/tests/workpaper_sync/test_task15_content_mutation_pg.py`
- 兄弟文件：`backend/tests/workpaper_sync/test_task15_content_mutation.py` → 本来就 **82 passed 全绿**，无需处理（修完再跑仍 82 passed，零回归）

## 运行前 / 运行后（实测命令输出）

```
# 前
rtk ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task15_content_mutation_pg.py -q --tb=line -rf -p no:randomly
46 failed, 3 passed, 1 warning in 8.86s

# 后（+1 条新增漂移守卫 = 50）
rtk ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task15_content_mutation_pg.py -q --tb=line -rf -p no:randomly
50 passed, 1 warning in 10.70s

# 兄弟件回归
rtk ..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync/test_task15_content_mutation.py -q --tb=short -rf -p no:randomly
82 passed, 1 warning in 39.92s
```

## 按根因分组的失败：46 个失败 = **2 个根因**（串联）

`_collect()` 是**一次采集覆盖全部场景**的 module 级 harness。它在第一个场景
（`business_commit`）就抛，后面 45 条守卫读不到自己那段快照，全部退化成
`KeyError: 'atomicity' / 'outcome' / 'room' …`。所以 46 个失败只有**1 个观测点**，
修掉第一层才看得见第二层。

| # | 根因 | 表现 | 归属 |
|---|------|------|------|
| R1 | 替身 `_JsonCarrierAdapter.verify_unmanaged_regions` 接不住编排方传的位移感知 kwargs | `TypeError: ... got an unexpected keyword argument 'row_shift'` | pre-existing |
| R2 | xlsx projection plan 没传 `structure_anchors`，且替身写盘是空壳 zip（反读不出受管结构） | `ContentMutationError: projection Excel commit requires frozen structure_anchors and contract` | pre-existing |

两层都是「生产面早已前移、这份 PG harness 没跟上」，**不是** 46 个独立缺陷。

## ours vs pre-existing：**46/46 全是 pre-existing，0 个是本会话造成**

不信旧标签，逐条实证：

1. **调用方与测试文件在工作树里零改动**。`rtk git diff HEAD --stat` 只列出
   `adapters/excel.py`（+135）与 `materialize_coordinator.py`（+136）；
   `content_mutation.py` 与 `test_task15_content_mutation_pg.py` **都不在 diff 里**。
2. **R1 的 kwargs 是已提交历史**。`git log -L 1700,1720:...content_mutation.py`：
   - `82f58ea44 feat(d4-ipo)` 引入 `row_shift` / `total_formula_rows` / `propagation`
   - `93892b99f fix(workpaper-sync)` 追加 `per_table_shift`
3. **HEAD 的真 adapter 早有这 4 个可选形参**：`git show HEAD:...adapters/excel.py` 里
   `row_shift: Any = None` / `total_formula_rows: Any = ()` / `propagation: Any = None` /
   `per_table_shift: Any = None` 全在 ⇒ 与本会话对 `excel.py` 的改动无关。
4. **R2 的 fail-closed 门也是已提交历史**：`0565cd5b9 fix(workpaper-sync): BP-30 按方案 A 修
   structure_hash 语义分裂` 引入 `_projection_structure_hash`。非 PG 兄弟件当时同步更新过
   （它有 `FIXTURE_ANCHORS` + `_NOT_PASSED` 哨兵，因此一直全绿），**这份 PG harness 漏了**。
5. **本会话 task 8/9/10 三个怀疑点全部排除**：
   - task 8 的 `_stage_cpu_segment_scoped`：**已提交**且工作树无改动；它只是把同一段包进
     `workbook_read_scope()`，参数表逐字未变。
   - task 10 的 `MaterializeOutcome.reuse_verdict` 必填：**此路径根本不经 coordinator**。
     `_stage_cpu_segment_scoped` 直接 `adapter.materialize(...)` 并校验返回
     `MaterializeResult`（不是 `MaterializeOutcome`）；实测 materialize 阶段通过，两次异常
     都发生在其之后。
   - task 9 未改生产代码。

结论：Task 3 的 A/B 差分结论（pre-existing）**成立**，但理由不完整 —— 真正的根因是
adapter 契约**欠声明** + PG harness 未跟上 BP-30 发布时刻哈希语义，都在单趟改动之外。

## 修复内容

### 生产侧（1 处，根因修复）

`backend/app/services/workpaper_sync/adapters/base.py` —
`WorkpaperSyncAdapter.verify_unmanaged_regions` 补上 4 个位移感知 keyword（默认值与
`ExcelSyncAdapter` 逐一对齐，类型同样留 `Any` 以免 `adapters.base` 反向依赖 excel 侧位移模块）。

为什么这是**生产缺陷**而不是替身写错：Protocol 声明的是 `before/after/contract` 三个参数，
而唯一的编排方 `content_mutation._stage_cpu_segment_scoped` **无条件**多传 4 个。于是
「严格照契约实现的 adapter」（测试替身、将来的 Word/JSON 载体）一上真实 commit 就 `TypeError`。
`ExcelSyncAdapter` 没事只因为它自己加了默认值 —— 文档化的契约从未跟上。
（注意：`ADAPTER_REQUIRED_METHODS` 与 registry 只按**方法名**准入，不查签名，所以这个缺口
没有任何一道现存关卡能拦住。）

### 测试侧（同一文件，3 处，全部是「把替身对齐真实生产面」，无一处放宽断言）

1. `_JsonCarrierAdapter.verify_unmanaged_regions` 显式列出 4 个位移感知 kwarg
   （JSON 载体没有行位移概念，接住后忽略 == `None` 语义 == 位移就是漂移）。
2. `_JsonCarrierAdapter.materialize` 的 xlsx 分支改写**真实受管结构**字节：复用共享
   fixture `tests/workpaper_sync/g1_structure_fixture.py` 的
   `workbook_fixture()` + `attach_projection_json()`（Excel Table + 隐藏 UUID 列 +
   `_GT_SYNC` sheet，projection JSON 注进同一个 zip 所以 extract 仍真读回投影、roundtrip
   等值照跑）。docx 分支保留原 `_ooxml` 空壳，行为不变。
   —— 这套字节 + 本文件契约 + `FIXTURE_ANCHORS` 组合实测能通过
   `compute_structure_hash_from_artifact`（先单独验证过再动代码）。
3. 5 处 xlsx projection `ContentCommitPlan` 补 `structure_anchors=dict(_FIXTURE_ANCHORS)`
   （`cv0` / stale `cv1` / `cv1` 再提交 / 幂等 `cv2` / room `cv3`）。
   **custom/authoritative 那一处刻意不补** —— 它走 `_stage_authoritative`，
   `contract=None`，本就不该有受管结构锚点。

### 新增 1 条漂移守卫（下次漂移在替身处打红，而不是 46 条 KeyError）

`TestHarness::test_stub_mirrors_the_orchestrator_call_surface`：从**生产调用点的 AST**
里取 `adapter.verify_unmanaged_regions(...)` 实际传的 keyword 集合，再要求
`_JsonCarrierAdapter` 与 `WorkpaperSyncAdapter` **两侧**都接得住。参数名不抄死，
编排方再加参数时这一条带明确原因打红。（对照本会话 `test_d4_29_customer_detail_sync.py`
的 `Host` 桩 + AST 漂移门做法。）

未做的事：没有放宽任何断言，没有 skip/xfail，没有手改任何 hash/manifest。

## 波及面 / 给其他并发 subagent 的情报

- **`test_task26_oo_to_html_pg.py` 与 `test_task27_conflict_resolution_pg.py` 里有同名
  `_JsonCarrierAdapter`，同样只写了 `before/after/contract`** ⇒ 极可能是**同一个 R1 根因**。
  按分工未动这两个文件。（`test_task26_oo_to_html_pg.py:383` 已出现引用「protocol 声明必须接得住」
  的注释，方向与本次生产修复一致。）它们若也走 xlsx projection commit，还会撞上 R2。
- `test_task13_contract_registry.py:2203-2210` 只按**名字**查 Protocol 的 annotations/方法，
  不查签名；本次生产改动不新增成员，对它无影响（未运行该文件，按分工归属他人）。
- `test_single_pass_parse_reuse.py` / `test_single_pass_verify_not_relaxed.py` 里那两条
  「`verify_unmanaged_regions` 形参不得出现 extract 产物（`extracted`/`projection`/
  `extract_outcome`）」的守卫：本次新增的 4 个参数都不在禁列，且它们查的是
  `ExcelSyncAdapter` 而非 Protocol。

## 环境阻塞

无。真 PG（`audit-postgres`，PG 16，`audit_platform`）可用，scratch schema
`tmp_task15_cm_*` 正常建/删；未跑全量套件。

## 改动文件

- `backend/app/services/workpaper_sync/adapters/base.py`（生产，1 处签名补全）
- `backend/tests/workpaper_sync/test_task15_content_mutation_pg.py`（替身对齐 + 5 处 plan 补锚点 + 1 条漂移门）
