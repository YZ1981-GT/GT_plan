# Task 5 性能基线 + `adapter_registered` 现状登记证据

**实测日期**：2026-09-26　**方法**：真库 `audit-postgres` 直连（`mcp_postgres_execute_sql` +
新增判据脚本 `backend/tests/workpaper_sync/test_task5_d3_performance_baseline.py` 实跑）+
读生产代码确认口径定义。全程未修改任何生产代码文件。

**HEAD**：`614b0b900`（`feat(workpaper-sync): 补齐 Task 32 两条 recovery/fold 欠账并解除
oracle upstream_debt`），比 Task 0 复核追记锚定的 `d2dbac39b` 又新了一个 commit，但不影响
Task 0 的四项前置结论（本任务未重新核查那四项，只针对 Task 5 自身的两个具体问题：性能基线
能不能测、`adapter_registered` 与耗时测试的关系）。

## 结论一句话

**真栈三端点与整册 materialize 现状不可测**——但**不是**因为 Task 0/需求文档记录的原因
（"D3 全库 0 行、无 published representation"），而是因为①D3 自己的 manifest 声明
`capability="single_onlyoffice"`（非 `bidirectional`），且②即使 D3 本身满足，共享的全量
`register_from_manifest()` 会在处理到 **D2** 时先因契约结构漂移抛错，整个注册通路在到达 D3
之前就已经中断。已给出引擎层合成基线替代口径（跳过 adapter 分派，见下文）。
`store_field_count`/`field_count` 已用真库现有 1 行真实数据 + 合成多行数据双重实测，两个口径
的定义差异已如实记录，未做作差推断。

---

## 一、"整册 materialize" 与"三端点"的定位

### 1.1 三端点（`backend/app/routers/wp_sync_router.py`）

同步往返的三个端点，均挂在同一 `USER_SYNC_PREFIX`（`/api/projects/{project_id}/workpapers/
{wp_id}/sync/entries/{entry_id}`）之下：

| 端点 | 方法/路径 | 函数 | 作用 |
|---|---|---|---|
| ① | `POST .../pending-mutations` | `create_pending_mutation`（:773） | `flushHtml()` 的落点，不推进 revision |
| ② | `GET .../store-projection` | `read_store_projection`（:786） | 服务端现算 store-backed entry 的投影，含 `field_count`/`store_field_count` |
| ③ | `POST .../materialize` | `materialize`（:826） | 唯一 `EditorLaunchDescriptor` 产出点，触发真正的 HTML→OO 物化写盘 |

三者共用同一个前置门 `_registration(svc, scope)`（`wp_sync_router.py:713`）：内部依次调用
`_attach_pilot_adapters(svc)`（manifest 全量注册）与 `svc.registry.assert_bidirectional_ready
(scope.entry_id)`，任一步失败即 `HTTPException(422)`（`wp_sync_router.py:723-733`）。**这是
本任务"能不能测"的唯一决定点**，三端点缺一不可地依赖它。

### 1.2 "整册 materialize"

指 `materialize()` 端点触发的 `MaterializeCoordinator.materialize()`（`materialize_coordinator
.py:1770`）——docstring 描述的"三段事务"编排（authorize → preflight → 幂等/重放判定 →
`ContentMutationService.commit(...)` → 终态记账 + room/descriptor）。该方法要求
`AuthorizedMaterializeRequest`，其构造同样先经 `_registration()` 解析出 `registration`
对象（含 approved bundle / contract），因此与三端点共享同一前置门，不是独立的第四条路径。

---

## 二、实测尝试结果：真栈三端点/整册 materialize 不可测的具体原因

### 2.1 与 Task 0 证据/需求文档记录的原因不同——本次实测得到更精确的归因

Task 0 证据文档（`evidence/task0-prerequisite-check.md`）与 requirements.md/design.md 引用的
`adapters/registry.py` 静态注释称：D3 因 `D3-det-rows` / `D3-vc` 全库 0 行、无 current
published representation 而未注册。**本次直连真库核实，该原因现状不成立**：

```sql
SELECT es.entry_id, es.current_representation_id, wp.id, wp.project_id
FROM working_paper_sync_entry_state es LEFT JOIN working_paper wp ON wp.id = es.wp_id
WHERE es.entry_id = 'xlsx/gt-d3-prepaid-accounts';
-- → current_representation_id = fc45730c-... （非空）

SELECT id, definition_bundle_id, adapter_id, reason, created_at
FROM working_paper_content_representation
WHERE entry_id = 'xlsx/gt-d3-prepaid-accounts' ORDER BY generation DESC;
-- → 3 条记录，全部 adapter_id='d3.prepaid_receipts_detail'，definition_bundle_id 均非空，
--   reason ∈ {content_commit ×2, rematerialize ×1}，created_at 均为 2026-09-12
```

即：`working_paper_sync_entry_state` 有行、指向的 `representation` 存在、且该 representation
绑定了非空 `definition_bundle_id`——`_describe_entry_supply()`（`registry.py:1446`）检查的
三项供给判据在 DB 层面**全部满足**，与静态注释描述的"全库 0 行、无 published representation"
不符（该注释大概率写于 2026-09-12 之前的某个时间点，此后 D3 的发布链已推进但注释未同步更新，
这是**代码注释过期**，不是本次核查的错误）。

### 2.2 真正的卡点①：D3 manifest 声明的 `capability` 仍是 `single_onlyoffice`

隔离跑 D3 自己的 `attach_pilot_adapters`（= `phase5_d3_prepaid_receipts.attach_adapters`），
不经过共享的全量注册 pass（判据 `test_d3_isolated_attach_confirms_not_registered_reason`
实测通过）：

```
[isolated] manifest 里 D3 现状 capability='single_onlyoffice'
[isolated] manifest 里 D3 现状 adapter_id=None
[isolated] D3 attach_pilot_adapters() 返回：()
```

`attach_adapters()`（`phase5_d3_prepaid_receipts.py:776`）第一步就是
`manifest_capability_enabled()` 检查：读 `backend/data/workpaper_sync_entry_manifest.json`
里 `xlsx/gt-d3-prepaid-accounts` 的 `capability` 字段，非 `"bidirectional"` 时
`assert_manifest_capability_enabled` 抛 `EntrySelectionError`，`manifest_capability_enabled()`
捕获后返回 `False`，函数在**任何 DB 查询之前**短路返回 `()`。直接读取该 JSON 确认：

```json
{
  "entry_id": "xlsx/gt-d3-prepaid-accounts",
  "capability": "single_onlyoffice",
  "adapter_id": null,
  "migration_state": "legacy_fake_bidirectional",
  "evidence": {"legacy_reasons": ["template_only_open", "no_durable_forcesave_ack", "missing_adapter"]}
}
```

`registry.py` 里 `DELIVERED_PER_ENTRY_CONTRACTS` 表项本身的 `"adapter_registered": False` 字段
经代码追踪确认**从未被注册逻辑读取**（grep 全仓 `\.get\("adapter_registered"\)` /
`\["adapter_registered"\]` 零命中）——它只是手写文档字段，真正的准入判据是
`ManifestRegistrationPlanItem.blocked_reason`（静态）→ `_describe_entry_supply`（DB 供给）→
provider 的 `attach_*`（内部再查 manifest capability + 跑 `register()` 的 RG-1~RG-19）。
D3 在 `blocked_reason`/DB 供给两关都过了，卡在**第三关**（provider 内部的 manifest capability
检查）。这与需求文档记录的"D3 因 store 全库 0 行"是**不同的卡点**，本次实测才第一次把它
精确定位到具体哪一行代码、哪一个检查点。

### 2.3 真正的卡点②：即使 D3 本身满足，共享的全量注册 pass 会先在 D2 处报错

三端点/整册 materialize 唯一的前置门 `_registration()` 调用的是**全量** `register_from_
manifest()`（覆盖 186 条 entry 的单次遍历，非按 entry 独立注册）。真跑该函数（判据
`test_real_registration_path_fails_before_reaching_d3` 实测通过，**两次独立运行得到两个不同
的报错位置**，说明遍历顺序或缓存状态非完全确定性，但结论一致——D2 挂了）：

```
第一次运行：ContractDriftError: contract d2.receivable_detail: 结构漂移，首个不一致位置
  sheet='d21-managed' table='adjudication_cells' field='adjudication_cells/aging_b'
  locator='B:static:10'
第二次运行：ContractDriftError: contract d2.receivable_detail: 结构漂移，首个不一致位置
  sheet='d23-managed' table='bad_debt_combined_rows' field='bad_debt_combined_rows/{row_uuid}/current_aje'
  locator='L:row_identity'
```

这是 `assert_no_structure_drift`（`contracts.py`）在 `register()` 的第⑦步（"contract 双重
漂移"）里真实触发的——D2 的**源码契约**（声明了 D2-1/D2-3 等新受管区，对应 commit
`04a90f386` "D2 受管覆盖 1→3 张"）与**已发布的 D2 representation**（DB 里旧代际，尚未
rematerialize 出与新契约匹配的结构）之间存在真实的结构漂移。`test_task28_sync_router.py`
（已入 HEAD 的既有守卫测试）的注释精确预言了这个场景：

> 「source contract 声明了新 sheet（如 D4-17 `d417-managed`）但已发布 representation 尚未
> rematerialize 时，`register_from_manifest` 会抛 `ContractDriftError`...它此前在
> `_attach_pilot_adapters(svc)` 处未被包进 try，一路冒泡成 opaque 500——整个 entry 的
> store-projection/materialize 全线...」

`wp_sync_router._registration()` 已经把这类异常包进了 `try/except (RegistryError,
SyncDomainError)` → `HTTPException(422)`（`wp_sync_router.py:723-733` 的注释明确写了这条
教训），所以生产环境不会 500，但**结果仍是 422**——D3 的三端点/整册 materialize 请求会先在
`_attach_pilot_adapters(svc)` 这一步就因 D2 的问题而失败，D3 自己是否已注册根本没有机会被
判断到。这是一个**与 D3 无关的平台级供给缺口**（D2 的契约与已发布产物代际不一致，本质上与
Task 0 提到的"186 个 planned entry 一个都注册不上"的 upstream_gap 同族，但具体触发形态是
"契约漂移"而不是"缺 published representation"）——不在本 spec 处理范围（design.md 裁决 F5
的处置原样适用：代码与合成判据照常推进，真栈判据如实标 `[ ]*`）。

### 2.4 小结：`adapter_registered` 与耗时测试的关系（回应任务原文要求的"确认关系"）

- 需求文档记录的 D3 未注册原因（"store 全库 0 行、无 published representation"）**已过期**，
  真库该项供给现已满足；D3 真实未注册的原因是 manifest `capability` 字段仍是
  `single_onlyoffice`（本次实测新发现，比文档记录更精确）。
- 即使把 D3 的 manifest capability 改成 `bidirectional`（本任务**未做**此改动，不改生产代码/
  数据），三端点仍会因为**同批注册里 D2 的契约漂移**而在到达 D3 之前失败——这是本次实测发现
  的第二个、且更紧迫的卡点，比 D3 自身的卡点先触发。
- 两个卡点性质相同：都是"供给链条上某个环节尚未走完发布/rematerialize 流程"，与设计文档裁决
  F5"真栈实测阻塞、代码与合成判据照常推进"的处置原则完全适用，无需修改处置结论——只是把
  "为什么不可测"的具体原因更新为本次实测确认的两条真实原因。

---

## 三、合成基线替代口径（引擎层耗时，跳过 adapter 分派）

🔴 以下全部是**引擎层**耗时（`phase5_d3_prepaid_receipts.build_store_projection`，D3-2 明细表
provider 的投影函数），**不是端到端真栈耗时**——不含 HTTP 往返 / guard / `_registration()` /
materialize 写盘 / OnlyOffice room 打开。跳过的正是上一节确认不可达的 adapter 分派层，只测
"provider 把 store payload 现算成 projection"这一段纯函数处理耗时，作为唯一可离线现测的
替代信号。判据脚本：`backend/tests/workpaper_sync/test_task5_d3_performance_baseline.py`
（新增，属判据/基线代码，不算生产代码改动，已按建议路径落盘）。

### 3.1 合成多行 payload（仿真 D3-2 明细表字段形状）

| n_rows | store_field_count（`len(projection.values)`） | elapsed_ms |
|---|---|---|
| 1 | 27 | 0.313 ~ 0.361 |
| 10 | 270 | 0.556 ~ 0.609 |
| 50 | 1350 | 2.277 ~ 2.333 |
| 200 | 5400 | 8.948 ~ 9.289 |

每行固定产出 27 个字段（11 个业务字段中含嵌套账龄结构，逐字段展开后每行 27 个 stable key），
字段数与行数成正比（`27 × n_rows` 精确对应，非近似）；耗时从 1 行到 200 行增长约 25~30 倍，
低于字段数增长的 200 倍，说明该函数本身不是纯 O(n) 逐字段循环占主导，有一部分固定开销
（contract 解析/初始化）被 200 行的量摊薄。两次运行（本文档记录了脚本两次独立执行的读数，
均在同一量级，无异常抖动）。

### 3.2 真实 DB payload（非合成，D3 已有的真实 1 行数据）

```
[real-db-payload] item='D3-det-rows' payload_bytes=59 store_field_count=27 elapsed_ms=0.148
```

`D3-det-rows` 真库现有 1 行真实业务数据（59 字节 JSON），现测引擎层 `store_field_count=27`，
与合成 payload 1 行的结果（27）逐字一致——证明合成 payload 的字段形状仿真准确，两组数据
可互相印证。

### 3.3 判据脚本运行结果（完整 7 条，全部真实通过，无 mock/无跳过）

```
$ python -m pytest tests/workpaper_sync/test_task5_d3_performance_baseline.py -v -s
tests/workpaper_sync/test_task5_d3_performance_baseline.py::test_real_registration_path_fails_before_reaching_d3 PASSED
tests/workpaper_sync/test_task5_d3_performance_baseline.py::test_d3_isolated_attach_confirms_not_registered_reason PASSED
tests/workpaper_sync/test_task5_d3_performance_baseline.py::test_synthetic_engine_layer_baseline_build_store_projection[1] PASSED
tests/workpaper_sync/test_task5_d3_performance_baseline.py::test_synthetic_engine_layer_baseline_build_store_projection[10] PASSED
tests/workpaper_sync/test_task5_d3_performance_baseline.py::test_synthetic_engine_layer_baseline_build_store_projection[50] PASSED
tests/workpaper_sync/test_task5_d3_performance_baseline.py::test_synthetic_engine_layer_baseline_build_store_projection[200] PASSED
tests/workpaper_sync/test_task5_d3_performance_baseline.py::test_real_db_payload_engine_layer_store_field_count PASSED
======================== 7 passed, 1 warning in 9.36s =========================
```

（首次跑最后一条因 Windows `ProactorEventLoop` + asyncpg 连接池跨 pytest-asyncio 函数级
事件循环复用导致 `RuntimeError: Event loop is closed`——这是环境已知问题，非产品代码缺陷，
修法是该测试内 `await engine.dispose()` 强制用当前循环重建连接，修完后稳定通过两次。）

---

## 四、`store_field_count` / `field_count` 口径定义与实测值（不作差推断）

### 4.1 两个口径的精确定义（读源码逐字确认，`store_projection_response.py`）

```python
# :234 —— store_field_count：纯 store payload 现算的字段数，overlay 之前
store_field_count = len(store_projection.values)

# :236-243 —— overlay：有 published substrate 时叠加基线（併集 + store 侧优先）
projection, overlay_applied = await _overlay_with_published_substrate(...)
#   内部调用 overlay_store_on_baseline_projection(baseline=..., store_projection=...)
#   baseline 来自 registration.adapter.extract(artifact=substrate, contract=contract)
#   —— 对已发布 substrate xlsx 做整簿 openpyxl 解析后按 contract 提取的全量投影

# :253 —— field_count：overlay 之后（若 overlay_applied=False 则等于 store_field_count）
values = _flatten_projection_values(projection)
"field_count": len(values)
```

`store_field_count` = provider 单独看 `checklist_responses.remark` 现算出的字段数（本 spec
D3 场景下即 D3-2 明细表的行数据展开字段）。`field_count` = 该投影与**已发布模板基线**做并集
后的总字段数——已发布基线包含模板里所有声明的字段坑位（不管 store 是否已填），并集会带出
store 没覆盖到的模板占位字段。**两者衡量的不是同一件事**：前者是"store 里实际有多少数据"，
后者是"模板声明的坑位 + store 数据的并集有多大"。

### 4.2 实测值（本 spec 场景，因 §二 结论只能测引擎层，overlay 步骤不可达）

| 口径 | 实测值 | 数据来源 | 备注 |
|---|---|---|---|
| `store_field_count`（真实 1 行） | **27** | `D3-det-rows` 真库 59 字节载荷 | `build_store_projection` 直算，未叠加 overlay |
| `store_field_count`（合成 1/10/50/200 行） | 27 / 270 / 1350 / 5400 | 合成 payload | 与真实 1 行结果逐字一致（27），仿真准确 |
| `field_count`（叠加 overlay 后） | **不可测** | — | `_overlay_with_published_substrate` 内部先调 `resolution.resolve(...)`，该调用依赖 `registration`（来自 `_registration()`），§二已证不可达；`registration.adapter.extract` 本身也需要一个已解析的 adapter 对象 |

🔴 **本任务不得也没有用 `store_field_count` 与 `field_count` 作差推断数据丢失**——原因不仅是
任务原文的纪律要求，本次实测还发现一个**更根本的原因**：`field_count` 在当前 D3 环境下
**根本测不出来**（overlay 步骤依赖的 `registration` 对象因 §二 的两个卡点而不可达），
不存在"两个数字都测到了，能不能作差"的场景——本任务能给出的只是 `store_field_count` 一侧的
实测值，`field_count` 一侧诚实登记为"不可测"，不是"测到了但选择不作差"。

引用既有先例作背书（D4/D2 spec 已因此误判过一次，本 spec 不重蹈）：

> `docs/operations/evidence/d4-store-contract-alignment/real-stack-probe-2026-09-23.md:175-178`：
> 「教训：`store_field_count`（1648）与 `field_count`（992）的差值不等于「store 被滤掉了多少
> 业务值」——它主要是模板占位行的空键收敛。拿两个计数的差去推断"数据被吞了"，在没读到真实
> 键集之前是没有依据的。」

本次 D3 场景与该先例的差异是：该先例**两个数字都实测到了**（1648 vs 992），只是不该作差；
本次 D3 场景是**`field_count` 一侧压根测不到**，连"能不能作差"的前提都不存在——如实登记
这个更强的诚实边界。

---

## 五、`adapter_registered` 现状复核（与 Task 0 结论对照）

| 项 | Task 0 复核追记结论（HEAD `d2dbac39b`） | 本任务实测（HEAD `614b0b900`） | 一致性 |
|---|---|---|---|
| D3 `adapter_registered` | False（已知卡点） | **False**（确认不变） | ✅ 结论一致 |
| D3 未注册的具体原因 | 引用 registry.py 静态注释："store 全库 0 行、无 published representation" | **实测发现该注释已过期**：DB 供给三项判据均已满足；真实原因是 manifest `capability='single_onlyoffice'`（非 `bidirectional`） | 🔴 **原因不一致**，本任务给出更精确归因 |
| 是否影响真栈实测 | 阻塞，标 `[ ]*` | 阻塞，标 `[ ]*`（**且发现即使解除 D3 自身卡点，仍会被 D2 的契约漂移连带阻塞**） | 结论不变，但阻塞链更长 |
| 处置原则 | 代码/合成判据照常推进，真栈判据标 `[ ]*`，不得以合成测试冒充真栈 | 同（design.md 裁决 F5 原样适用） | ✅ 一致 |

**Task 0 的四项前置判定（A/B/C/D）本身不需要重新核查**——本任务只针对"性能基线能不能测"这个
具体问题复核了 D（`adapter_registered`），确认现状仍为 False、处置原则不变，但把"为什么
False"的归因从文档记录的旧原因更新为本次实测确认的两条新原因（D3 自身 manifest capability
未裁决 + D2 契约漂移连带阻塞）。**建议**（不在本任务处理范围，仅登记）：requirements.md/
design.md 引用的 `registry.py` 该条注释应在后续任务中同步更新，避免继续以过期原因误导判断；
D2 的契约漂移应反馈给 D2 spec 或平台级 provisioning 处理，不在本 spec 范围。

---

## 六、命令 + 实际输出摘录（可复算）

### 6.1 真库 DB 直查（确认 D3 供给现状）

```sql
SELECT es.entry_id, es.current_representation_id, wp.id AS wp_id, wp.project_id
FROM working_paper_sync_entry_state es
LEFT JOIN working_paper wp ON wp.id = es.wp_id
WHERE es.entry_id = 'xlsx/gt-d3-prepaid-accounts';
-- → entry_id=xlsx/gt-d3-prepaid-accounts, current_representation_id=fc45730c-d00f-4f2f-803d-3c6bc0b1f285,
--   wp_id=d35c715a-9d71-4f4f-80ee-efc846533a24, project_id=2aa00f57-1df4-4fe8-9840-2d65d0fd8749

SELECT id, definition_bundle_id, adapter_id, reason, created_at
FROM working_paper_content_representation
WHERE entry_id = 'xlsx/gt-d3-prepaid-accounts' ORDER BY generation DESC;
-- → 3 行，adapter_id 均='d3.prepaid_receipts_detail'，definition_bundle_id 均非空，
--   reason ∈ {content_commit, content_commit, rematerialize}，created_at 均 2026-09-12

SELECT cr.wp_id, cr.item_id, length(cr.remark) AS remark_bytes
FROM checklist_responses cr
WHERE cr.item_id IN ('D3-det-rows','D3-rp-rows','D3-ana-credit-rows','D3-ana-debit-rows',
                      'D3-lt-rows','D3-vc-current-rows','D3-vc-post-rows');
-- → D3-vc-current-rows: 3601 字节 / D3-det-rows: 59 字节 / D3-lt-rows: 2 字节；其余 4 键真库 0 行
```

### 6.2 判据脚本（新增文件，判据/基线代码，不算生产代码改动）

```
$ python -m pytest tests/workpaper_sync/test_task5_d3_performance_baseline.py -v -s
（cwd=backend，7 passed，见 §三.3 完整输出）
```

### 6.3 manifest JSON 直读（确认 D3 capability 现状）

```
$ python -c "import json; d=json.load(open('backend/data/workpaper_sync_entry_manifest.json',
  encoding='utf-8')); ..."
-- → capability: "single_onlyoffice", adapter_id: null, migration_state: "legacy_fake_bidirectional"
```

---

## 七、结论汇总（回应「完成标准」逐项）

1. ✅ 整册 materialize 与三端点的定位：`wp_sync_router.py` 的 `create_pending_mutation`
   （:773）/ `read_store_projection`（:786）/ `materialize`（:826），共享前置门
   `_registration()`（:713）；"整册 materialize" = `MaterializeCoordinator.materialize()`
   （`materialize_coordinator.py:1770`），同一前置门。
2. ✅ 实测尝试结果：**真实尝试两次**（裸调 `register_from_manifest()` + 隔离跑 D3 自己的
   `attach_pilot_adapters`），均确认不可达真栈，具体失败原因已记录（D2 契约漂移
   `ContractDriftError` + D3 自身 manifest capability 非 bidirectional）；已给出引擎层合成
   基线替代口径（1/10/50/200 行，0.31ms~9.3ms），并明确标注"这不是端到端真栈耗时"。
3. ✅ `store_field_count` / `field_count` 实测值：`store_field_count` 真实测到（真实数据 27 /
   合成数据 27/270/1350/5400）；`field_count` 诚实登记为**不可测**（overlay 步骤依赖的
   registration 不可达），未做任何作差推断。
4. ✅ `adapter_registered` 现状复核：与 Task 0 结论（False）一致，但归因已更新为更精确的
   两条实测原因，处置原则不变。
5. ✅ 命令 + 实际输出摘录：见 §六。

本任务未修改任何生产代码文件。新增判据脚本
`backend/tests/workpaper_sync/test_task5_d3_performance_baseline.py`（7 用例，全部真实通过，
无 mock）。
