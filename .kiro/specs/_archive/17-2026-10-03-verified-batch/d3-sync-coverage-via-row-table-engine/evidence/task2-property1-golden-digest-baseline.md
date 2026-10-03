# Task 2 Property 1 零回归基线证据

**执行日期**：2026-09-26　**HEAD**：`614b0b900f8c1ece469b32e9f869428d32ba88d4`
（分支 `work/2026-09-14-d4-dual-mode-p0-fixes`，工作树相对该 HEAD 有大量未提交改动——本任务
只运行既有脚本/测试、读取其输出，未依赖也未修改任何未提交的生产代码差异）

**结论先行**：8 个 contract（D3-2 + 其余 7 家）的 golden digest 基线**此时全部为绿**（脚本报
「零回归」，其自带 pytest 套件 5/5 通过），与 tasks.md 原文「此时必绿」的预期完全一致。未修改
任何生产代码文件；Requirement 6.5 的合成 payload 机制发现**已由上游脚本内建**，本任务无需新增
注入点，只需运行验证并如实记录其构造方式。

---

## 一、脚本定位 + 工作原理

### 1.1 位置

- 主脚本：`backend/scripts/check/check_sync_provider_golden_digest.py`
- 自测：`backend/tests/scripts/test_check_sync_provider_golden_digest.py`
- 基线存盘：`backend/scripts/check/_sync_provider_golden_digest.json`（随代码入库）

来源：上游 spec `d1-sync-row-table-engine-and-d1-coverage` · Task 1 · Requirements 4.1/4.2/4.5
交付（本 spec Task 2 直接复用，不重造）。

### 1.2 工作原理（读脚本源码 + docstring 得出）

对每个已交付的 sync provider，取三段 **canonical JSON 的 sha256**：

1. **`build_contract_payload()`** —— per-entry 契约的 canonical payload（整体 digest +
   🔴 P1-4 复盘后追加的 **sheet 粒度 digest**：按 `sheet_key`/`excel_name` 拆分，理由是
   「扩容一张 sheet 只应改动那一张的 digest，其余 sheet 逐字节不变才是零回归的干净证明；
   整体 digest 无法区分『扩容新 sheet』与『改动已有 sheet』，sheet 粒度才能」）。
2. **`build_store_projection(合成 payload, contract=...)`** —— HTML store → Projection 投影
   结果的 canonical 形态（`contract_id`/`semantic_version`/`document_type`/按 stable_key 排序
   的 `values`/`row_keys`）。**B60**（`simple_checklist` 形态）没有这条路径，如实记 `null`，
   不假造。
3. **`instrumentation_spec(s)()`** —— Excel 注入几何声明（单数或复数，D4/E1 多受管 sheet
   取复数）。

首次跑 `--update` 把当前 digest 写为**基线**（此时必绿，不是判据，是抽取前的快照）；之后每次
跑（不带 `--update`）是**过门**：把现算 digest 与磁盘基线比较，`_compare()` 逐字段找漂移——
若某 provider 已有 sheet 的 digest 变了才报 drift，**新增 sheet**（基线里没有该 sheet key）
不算回归（additive，是扩容的预期形态，这正是本 spec 后续接入 D3-6/D3-4/D3-5/D3-7 后应该发生
的事）。

### 1.3 Requirement 6.5「合成 payload」机制 —— 🔴 已由脚本内建，本任务未新增代码

脚本内部 `_synthetic_rows(mod)` 函数**已经**按 provider 的字段清单（`MANAGED_FIELD_SPECS` 或
新引擎的 `managed_row_table_specs()`）现造两行占位数据来驱动 `build_store_projection`，
不依赖真库任何数据。**这正是需求 6.5 要求的机制，且已经在 D3 provider 身上被验证过**——
脚本自己的测试文件里有一条专门针对 D3 的用例：

```python
def test_synthetic_payload_drives_projection_for_zero_row_provider() -> None:
    """D3 真库 0 行，但合成 payload 必须驱动出非空 projection（Requirement 4.5）。"""
    mod = _load_module()
    d3 = mod._import_provider("phase5_d3_prepaid_receipts")
    rows = mod._synthetic_rows(d3)
    assert len(rows) == 2
    assert all(r.get("rowId") for r in rows)
    assert isinstance(rows[0].get("agingPrior"), dict), "nested 账龄路径应被逐级建 dict"
```

⇒ **完成标准里预留的「若脚本不支持合成 payload 注入点，只记录发现不擅自改动」这一分支不适用**
——脚本已经支持，且已经对 D3 验证过。本任务不需要、也没有对生产代码或脚本本身做任何改动。

---

## 二、D3 当前已有的 contract 清单（本任务运行范围）

脚本内置的 `PROVIDERS` 表（`check_sync_provider_golden_digest.py` 模块级常量）当前登记 **9 家**
provider：

| label | 模块 | adapter_id | 有 projection | instrumentation 复数 |
|---|---|---|---|---|
| b60 | `pilot_simple_checklist` | `b60.hour_budget` | 否（simple_checklist 无此路径） | 否 |
| d1 | `phase5_d1_notes_receivable` | `d1.notes_receivable_detail` | 是 | 否 |
| d2 | `pilot_d2_large_json` | `d2.receivable_detail` | 是 | 否 |
| **d3** | `phase5_d3_prepaid_receipts` | `d3.prepaid_receipts_detail` | 是 | 否 |
| d4 | `phase5_d4_revenue_detail` | `d4.revenue_detail` | 是 | 是 |
| d5 | `phase5_d5_receivables_financing` | `d5.receivables_financing_detail` | 是 | 否 |
| d6 | `phase5_d6_contract_assets` | `d6.contract_assets_detail` | 是 | 否 |
| d7 | `phase5_d7_contract_liabilities` | `d7.contract_liabilities_detail` | 是 | 否 |
| e1 | `phase5_e1_monetary_fund` | `e1.monetary_fund_detail` | 是（复数 instr） | 是 |

🔴 **如实登记一处任务文本与脚本现状的偏差，不隐藏**：

- 本 spec **requirements.md 需求 6.3 原文**枚举的「其余 7 个 contract」是
  `b60/d1/d2/d4/d5/d6/d7`（**不含 e1**）——这与 tasks.md Task 2 标题「D3-2 与其余 7 contract」
  逐字对应，合计 **8 个**（D3 本身 1 个 + 其余 7 个）。
- 但脚本当前的 `PROVIDERS` 表**已经登记了第 9 家 `e1`**（该模块 docstring 自述：
  「E1（2026-09-26 纳入）：spec `e1-sync-coverage-and-first-canary` 交付的第 9 个 contract」）。
  e1 是本 spec（`d3-sync-coverage-via-row-table-engine`）编写需求文档**之后**才由另一个平行
  spec 加入这个**跨 spec 共享**的基线脚本/基线文件的，requirements.md 需求 6.3 的「7 家」
  枚举因此没有、也不可能提到它。
- **处置**：本任务按 tasks.md/requirements.md 原文的字面范围（D3 + 7 家 = **8 个 contract**）
  逐一核对并在下表中标注结果；同时如实记录脚本现在实际跑的是 9 家（多出 e1 一家，属
  **additive、非本 spec 范围内的既存事实**，e1 的 digest 是否零回归不是本 spec Requirement 6.3
  的判据对象，但它与 D3 共用同一个基线文件——脚本整体报「零回归」自然也隐含 e1 此时不变，
  一并记录供交叉参照，不作为本 spec 的判据）。

**本 spec Requirement 6.3 判据对象（8 个 contract）逐一列出**：

1. `d3.prepaid_receipts_detail`（D3，`D3-det-rows`，已接 D3-2） —— 本 spec 主体
2. `b60.hour_budget`
3. `d1.notes_receivable_detail`
4. `d2.receivable_detail`
5. `d4.revenue_detail`
6. `d5.receivables_financing_detail`
7. `d6.contract_assets_detail`
8. `d7.contract_liabilities_detail`

---

## 三、合成 payload 的构造方式（针对 D3，实测打印）

D3 真库 `D3-det-rows` 全库 0 行（Task 0 证据已确认），`build_store_projection` 若无数据驱动，
digest 只能对着空数组算、覆盖不到任何字段路径。脚本 `_synthetic_rows(mod)` 的构造逻辑：

1. 先取该 provider 的字段清单（`_field_specs_and_row_key`）：D3 走的是**未声明化的旧形态**
   （`MANAGED_FIELD_SPECS` 模块级常量存在），实测共 **27 条 field spec**，行身份键
   `row_identity_key = 'rowId'`（与 D3-2 明细表的 UUID 动态行一致）。
2. 逐字段按 `value_type` 现造占位值：`amount`/`integer` 填 `(i+1)*100`（数值占位），其余
   （`text`/`enum`）填 `f"v{i}"`（字符串占位）；`json_key` 若是 nested 路径（如
   `priorAging/within1`）则逐级建 `dict`。
3. 造两行（`i=0,1`），每行带各自的 `rowId`（`synthetic-0`/`synthetic-1`）。

**实测打印 D3 的合成 payload 前 5 条字段 spec + 完整第 1 行**（一次性探针脚本跑完即删，命令与
输出见下）：

```
row_identity_key = 'rowId'
field_specs 数量 = 27
field_specs 前 5 条:
   ('customer_name', 'A', 'editable', 'text', 'customerName', '对方单位名称')
   ('company_code', 'B', 'editable', 'text', 'companyCode', '公司代码')
   ('nature', 'C', 'editable', 'enum', 'nature', '款项性质')
   ('relation_type', 'D', 'editable', 'enum', 'relationType', '关联方类型')
   ('prior_unadjusted', 'E', 'editable', 'amount', 'priorUnadjusted', '期初未审余额')

合成 payload 第 1 行:
{
  "rowId": "synthetic-0",
  "customerName": "v0", "companyCode": "v0", "nature": "v0", "relationType": "v0",
  "priorUnadjusted": 100, "priorAdjustment": 100, "priorReclass": 100, "priorAudited": 100,
  "agingPrior": {"within1": 100, "y1to2": 100, "y2to3": 100, "over3": 100},
  "debit": 100, "credit": 100, "endBalance": 100, "entityReclass": 100,
  "endUnadjusted": 100, "endAje": 100, "endRje": 100, "endAudited": 100,
  "agingAudited": {"within1": 100, "y1to2": 100, "y2to3": 100, "over3": 100},
  "isConfirmed": "v0", "postPeriodSettlement": 100, "remark": "v0"
}
```

27 个字段 = 19 标量（含 `isConfirmed`/`postPeriodSettlement`/`remark` 等收尾字段）+ 8 个 nested
账龄字段（`agingPrior`/`agingAudited` 各 4 段：`within1`/`y1to2`/`y2to3`/`over3`），与
requirements.md「D3-2 明细表」记录的「27 个受管字段」逐字对应，未发现遗漏或多造字段。

**这条机制对 Requirement 6.5「D3 store 全库 0 行 ⇒ 用合成 payload 驱动」是完全满足的**——
脚本对 D3 走的正是这条路径（`has_projection=True` 且用合成两行驱动 `build_store_projection`），
不是「因无数据而跳过」。

---

## 四、8 个 contract 的实测 golden digest 结果（此时全部必绿）

### 4.1 过门结果（脚本主判据）

```
$ python backend/scripts/check/check_sync_provider_golden_digest.py
✅ golden digest 零回归：26 个 digest 逐个不变
```

**全绿，无漂移。** `26` 是脚本当前 9 家 provider（含 e1）的总 digest 数（contract + instr 必有
+ projection 除 b60 外都有：9×2 + 8 = 26），本 spec 判据对象的 8 家全部包含在这 26 个里且全部
不变。

### 4.2 逐 contract 实测 digest 值（`--json` 输出，本 spec 判据对象的 8 家）

| contract | sheet_digests（`sheet_key`: sha256 前 16 位） | store_projection_sha256（前 16 位） | instrumentation_sha256（前 16 位） |
|---|---|---|---|
| **d3**（D3-2） | `d32-managed`: `621527ec5b826f0b` | `0b6bbd9db876f550` | `8b89c700797da577` |
| b60 | `b601-managed`: `299b30f8d7dade49` | `null`（simple_checklist 无此路径，诚实边界） | `5a29ef8e2bff9f55` |
| d1 | `d13-managed`: `5ae1032ee1b1a481` | `a2c53c66aa954e70` | `3d81292d83211914` |
| d2 | `d22-managed`: `31f1458f39fb5687` / `d23-managed`: `b5b8f846bfb6d3ed` / `d21-managed`: `73863915b2db1cfa` | `0108dd8681a27d9c` | `fc03d1d438132cc1` |
| d4 | 34 个 sheet key（篇幅所限，见「附：完整 JSON」；均以 `d4*-managed` 命名） | `417877adea186980` | `63bc66288b777ef1` |
| d5 | `d52-managed`: `082abbb59ae589a8` | `c8b6c72ac05ea864` | `78efa0cef3459565` |
| d6 | `d62-managed`: `18e8757cb34f21c1` | `25eba0577460f820` | `b2deb8916cfb2f1b` |
| d7 | `d72-managed`: `7560a4793aa396b7` | `9d316b8dac90f9fc` | `14107e421e338a88` |

（参照登记，非本 spec 判据对象但脚本同批跑出：e1 — `e12-managed`:`8f84297305ca5bb0` /
`e14-managed`:`2d70eae841bb7443`，projection `26c5ef52db466754`，instr `8735a14b2d502167`）

**这些值与脚本自身已提交的基线文件（`backend/scripts/check/_sync_provider_golden_digest.json`）
逐字节完全一致**——即脚本报告的「零回归」不是空话，是逐 contract、逐 sheet 比对后的结果。

### 4.3 是否有红？—— 无，如实说明为何预期如此

**本次运行全绿，没有需要分析原因的红项。** 这与 tasks.md 原文「此时必绿」的预期完全一致，
理由：

- D3 当前的生产代码（`phase5_d3_prepaid_receipts.py`）虽然工作树里存在一处**未提交**的重构
  差异（把 D3-2 的既有声明改写为上游新引擎的 `RowTableSheetSpec` 形态，`SPEC_D32`，属另一项
  并行中的工作，非本任务改动、非 D3-6/D3-4/D3-5/D3-7 的新增），但该重构**尚未新增任何受管区**
  ——`ADAPTER_ID`/`STORE_ITEM_ID`/`ENTRY_ID` 三个关键常量与受管 sheet 数（仍只有 `d32-managed`
  一个）都未变，digest 覆盖的是 `build_contract_payload()`/`build_store_projection()`/
  `instrumentation_spec()` 的**输出结果**而非源码文本，只要输出的 canonical JSON 逐字节不变，
  过程中怎么重构都不影响 digest。
- 其余 7 家（b60/d1/d2/d4/d5/d6/d7）在本 spec 范围内完全没有被触碰，理应不变。
- D3-6/D3-4/D3-5/D3-7 四张 sheet 尚未被声明进 D3 的受管清单（本 spec 阶段 1~3，Task 6~12 才做
  这件事）——这正是本任务要取的「扩容前」基线，扩容后（Task 7/10/12 验收时）应该看到：
  ①D3 的 `sheet_digests` 新增对应 sheet key（additive，不算漂移）②D3 现有的 `d32-managed`
  digest 与 ③其余 7 家的 digest 三者均逐字节不变，才是「零回归」成立的证明。**本次记录的
  digest 值就是那次对比的基准点。**

### 4.4 脚本自带 pytest 套件运行结果

```
$ python -m pytest backend/tests/scripts/test_check_sync_provider_golden_digest.py -v --tb=short
============================= test session starts =============================
collected 5 items
test_all_delivered_providers_produce_three_sections PASSED [ 20%]
test_digest_count_matches_provider_capabilities PASSED [ 40%]
test_current_matches_committed_baseline PASSED [ 60%]
test_mutation_sheet_digest_drift_is_detected PASSED [ 80%]
test_synthetic_payload_drives_projection_for_zero_row_provider PASSED [100%]
============================== 5 passed in 3.69s ==============================
```

5/5 全绿，包括：
- `test_current_matches_committed_baseline`：现状与已入库基线零漂移（本任务的核心判据）。
- `test_mutation_sheet_digest_drift_is_detected`：**变异反证**——脚本篡改 d1 某个 sheet 的
  digest 后 `_compare()` 必须报出该 sheet 漂移，验证这个门不是永绿装饰（呼应本 spec 需求 8.1
  「未能打红的判据重写而非保留」的纪律，虽然这条变异测试属于上游脚本自带、非本任务新写，但
  它证明了本任务复用的判据本身经得住变异检验）。
- `test_synthetic_payload_drives_projection_for_zero_row_provider`：D3 专属，见「三」节。

---

## 五、运行命令 + 输出证据汇总（可复现）

```powershell
# 1. 过门（主判据，比对现状 vs 已入库基线）
PS D:\GT_plan> python backend/scripts/check/check_sync_provider_golden_digest.py
✅ golden digest 零回归：26 个 digest 逐个不变

# 2. 落全量 JSON 报告（供逐 contract 核对，本文档第四节表格来源）
PS D:\GT_plan> python backend/scripts/check/check_sync_provider_golden_digest.py --json _tmp_task2_d3_digest_report.json
✅ golden digest 零回归：26 个 digest 逐个不变
（读取 _tmp_task2_d3_digest_report.json 内容后已删除，一次性用完即删）

# 3. 脚本自带 pytest 自测
PS D:\GT_plan\backend> python -m pytest tests/scripts/test_check_sync_provider_golden_digest.py -v --tb=short
============================= test session starts =============================
platform win32 -- Python 3.12.8, pytest-9.0.2, pluggy-1.6.0
hypothesis profile 'fast' -> deadline=None, max_examples=5, ...
collected 5 items
tests/scripts/test_check_sync_provider_golden_digest.py::test_all_delivered_providers_produce_three_sections PASSED [ 20%]
tests/scripts/test_check_sync_provider_golden_digest.py::test_digest_count_matches_provider_capabilities PASSED [ 40%]
tests/scripts/test_check_sync_provider_golden_digest.py::test_current_matches_committed_baseline PASSED [ 60%]
tests/scripts/test_check_sync_provider_golden_digest.py::test_mutation_sheet_digest_drift_is_detected PASSED [ 80%]
tests/scripts/test_check_sync_provider_golden_digest.py::test_synthetic_payload_drives_projection_for_zero_row_provider PASSED [100%]
============================== 5 passed in 3.69s ==============================

# 4. 合成 payload 内容实测打印（一次性探针，跑完即删，用于本文档第三节）
PS D:\GT_plan> python _tmp_task2_synthetic_probe.py
row_identity_key = 'rowId'
field_specs 数量 = 27
...（完整输出见第三节）
```

**运行环境**：本地 Python 3.12.8（`backend/` 目录内 venv 之外的系统解释器，脚本内部
`os.environ.setdefault("DB_DISABLE_SSL", "True")` 自处理无库环境），未连接真实 PostgreSQL，
全程离线（digest 计算不依赖真库数据，Requirement 6.5 合成 payload 机制正是为此设计）。

---

## 六、未修改任何生产代码文件的确认

本任务全程只执行了：
1. 读取既有脚本源码（`check_sync_provider_golden_digest.py`）与既有测试
   （`test_check_sync_provider_golden_digest.py`）——未编辑。
2. 运行既有脚本（两种模式：默认过门 + `--json` 落报告）——不带 `--update`，未写入/覆盖基线
   文件 `_sync_provider_golden_digest.json`。
3. 运行既有 pytest 套件——只读操作。
4. 新建并运行一次性探针脚本 `_tmp_task2_synthetic_probe.py`（打印合成 payload 内容用于本证据
   文档第三节），**运行后已删除**，不留存于仓库。
5. 新建并读取一次性 JSON 报告 `_tmp_task2_d3_digest_report.json`，**读取后已删除**。

**未发现「golden digest 脚本本身需要一个可选的合成 payload 注入点而目前没有」的情况**——
完成标准里预留的这一分支不适用：脚本的 `_synthetic_rows()` 机制已经内建且已经对 D3 验证过
（脚本自带测试 `test_synthetic_payload_drives_projection_for_zero_row_provider` 专门覆盖此
场景）。本任务未对任何生产代码或脚本代码做任何修改，也未新增测试文件（完成标准里预留的
「若脚本设计成 pytest 用例需要新建驱动测试文件」这一分支同样不适用——脚本本身是独立可执行的
CLI，且已有的 `test_check_sync_provider_golden_digest.py` 已完整覆盖包括 D3 合成 payload 的
全部场景，重复新写一份是不必要的重复判据）。

---

## 七、结论汇总（回应「完成标准」逐项）

1. ✅ 脚本定位（`backend/scripts/check/check_sync_provider_golden_digest.py`）+ 工作原理简述：
   见「一」
2. ✅ D3 当前已有的 8 个 contract 清单：见「二」（如实记录了 requirements.md「7 家」枚举与
   脚本现登记「9 家」之间的偏差，e1 不计入本 spec 判据）
3. ✅ 合成 payload 的构造方式（实测打印 D3 的 27 字段 + 完整合成行）：见「三」
4. ✅ 每个 contract 的实测 golden digest 结果（此时全部必绿，无红项，附原因分析）：见「四」
5. ✅ 运行命令 + 实际输出摘录（4 条命令，逐条可复现）：见「五」
6. ✅ 未修改任何生产代码文件（含探针脚本已删除的说明）：见「六」
