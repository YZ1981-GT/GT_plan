# Task 10 证据：阶段 2 验收（D3-6 / D3-4 / D3-5 统一接入）

> 分三段执行。第 1 段 = 地基核实 + 基线判据迁移（§1~§5）；第 2/3 段从 §6 起追加。
> 执行环境：Windows，cwd=backend，Python = 仓库根 `.venv`。

## §1 接手审计

Task 10 此前两次整体派发未返回（第一次半途中断、改动留在工作树且未跑测试未写证据；第二次无改动）。
本段接手时工作树（`git status --short`，仅列 D3 相关）：

- 已修改（M）：`phase5_d3_prepaid_receipts.py`（Task 6/8 的扩容面契约装配 `_expansion_sheets_payload`，
  按 sheet_key 分组）、`phase5_row_table_sheet.py`（Task 8 新增 `footer_carries_total_formula` 字段，
  默认 True）、`backend/data/workpaper_sync_contracts/d3.prepaid_receipts_detail.json`（+491 行）。
- 未跟踪（??）：整个 spec 目录、`phase5_d3_04_analysis.py` / `phase5_d3_05_long_term.py` /
  `phase5_d3_06_related_party.py` / `phase5_d3_expansion.py` 及 7 个 `test_d3_*` / `test_task5_d3_*` 测试文件。
- 上一次运行遗留、本段需核实的改动：
  1. `phase5_d3_expansion.py` 三个灰度开关 `_INCLUDE_D306_RELATED_PARTY` / `_INCLUDE_D304_ANALYSIS` /
     `_INCLUDE_D305_LONG_TERM` 已翻为 `True`（Task 7/8/9 明确留给 Task 10 统一批量翻，**保持 True**）。
     注：该文件注释声称"那 3 个文件的现状必红断言已随本次接入更新"——接手时**并不属实**
     （三个基线文件自 Task 4/5/6 起未改动），由本段 §4 兑现。
  2. `phase5_d3_04_analysis.py` 几何 `LAST_DATA_ROW_DEBIT` 16→15、`LAST_DATA_ROW_CREDIT` 24→23（BP-21 理由），见 §3 独立核实。
  3. 磁盘契约已被重生成（未验证），见 §2。
- 并发会话在途改动（**不碰**）：`evidence.py` / `pilot_harness.py` / milestones json /
  `test_task29*` / `test_task30*` / `test_task39*` / `test_task40~43*` / `pilot_g7_store_merge.py` /
  `pilot_h1_store_merge.py` / `test_evidence_schema_representability.py` / `test_v165_authorization_reject_pg.py`。

## §2 契约一致性

命令（cwd=backend）：

```
..\.venv\Scripts\python.exe -c "from app.services.workpaper_sync import phase5_d3_prepaid_receipts as m, phase5_d3_expansion as e; c=m.assert_contract_file_matches_source(); ...; e.assert_specs_align_with_contract_sheets(c)"
```

输出（关键行）：

```
OK assert_contract_file_matches_source
sheets= [('d32-managed', '预收账款明细表D3-2', ['prepaid_receipts_detail_rows']),
         ('d36-managed', '关联关系及交易检查表D3-6', ['related_party_rows']),
         ('d34-managed', '预收账款分析表D3-4', ['analysis_debit_rows', 'analysis_credit_rows']),
         ('d35-managed', '账龄1年以上的预收账款检查表D3-5', ['long_term_rows'])]
managed_zone_count= 5
align OK
store_items= ('D3-det-rows', 'D3-rp-rows', 'D3-ana-debit-rows', 'D3-ana-credit-rows', 'D3-lt-rows')
switches= True True True
```

HEAD vs 工作树契约 JSON 结构对比（python 解析两版，非逐行 diff）：

```
top keys same: True
non-sheets top-level diffs: []          ← review/entry 等顶层字段零变化
head sheets: ['d32-managed']
d32 unchanged: True                      ← D3-2 那一项逐字段相等（Property 1 零回归面）
新增 sheets：
  d36-managed  关联关系及交易检查表D3-6  related_party_rows   footer=合计/True   10 fields  mask=['F12:F16']  store=D3-rp-rows
  d34-managed  预收账款分析表D3-4        analysis_debit_rows  footer=差异/True    4 fields  mask=[]          store=D3-ana-debit-rows
                                          analysis_credit_rows footer=差异合理性分析/False 4 fields mask=[]   store=D3-ana-credit-rows
  d35-managed  账龄1年以上的预收账款检查表D3-5 long_term_rows footer=合计/True    8 fields  mask=[]          store=D3-lt-rows
```

结论：✅ 磁盘契约 == 源码现算 payload；新增内容恰为 d36 / d34(两 table) / d35，无意外项；对齐守卫通过。

补充观察：扩容面 table payload 只含 `anchor`（表头行）与 `source_ref`（首数据行坐标），**不含
`last_data_row`**（D3-4 两区 formula_mask 为空），故 D3-4 末行 16→15 / 24→23 的几何修正**不改变契约
JSON 字节**——契约 mtime 晚于/早于几何修改都不影响一致性，契约无需因 §3 结论重生成（除非 §3 改了首行/表头/字段）。

## §3 BP-21 几何核实

### 3a 门禁真源与调用点

- 真源 `excel_typography_rows.py`：`is_typography_placeholder(text)` = 含 ≥1 个 U+2026 **且**除
  `{…, '.', '。', ' '}` 外无其它字符（空串 False）；`trailing_typography_rows` 只认区间**尾部连续**占位行；
  `assert_last_data_row_is_not_typography_placeholder` 读受管区首列（`MANAGED_LABEL_COLUMN="A"`）
  全部非空格文本（`read_column_text` 内部 `decode_cell_text` 会 strip），尾部命中即抛 `TypographyRowError`
  （`error_code=managed_last_row_is_typography_placeholder`）并给出应声明值。
- 唯一生产调用点：`excel_instrumentation._inject_managed_sheet`（L1231-1243），先
  `assert_label_column_matches_spec(spec.table_ref)` 再调本门，`TypographyRowError` 翻译为
  `InstrumentationError` 上抛；`instrument_workbook_bytes_multi` 对每个 spec 逐个调用（L1459）。

### 3b 原几何复现 vs 当前几何（真实注入路径）

探针（一次性脚本 `backend/_task10_bp21_probe.py`，已删）：specs = `[instrumentation_spec()] +
[_instrumentation_of(s) ...]`，走 `instrument_workbook_bytes_multi(read_authoritative_template(), specs,
gate=ExcelIdentityCarrierGate.load())`。

```
[原 DEBIT=16 + 现 CREDIT=23] InstrumentationError: entry xlsx/gt-d3-prepaid-accounts / sheet '预收账款分析表D3-4':
  声明的受管行区间末行 16 落在**排版占位行**上（标签列 A 取值 {16: '……'}）…应声明 last_data_row=15
  （剔除尾部 1 行占位行），footer 行保持不变。…（BP-21）
    __cause__=TypographyRowError error_code=managed_last_row_is_typography_placeholder
[现 DEBIT=15 + 原 CREDIT=24] InstrumentationError: … 声明的受管行区间末行 24 落在**排版占位行**上
  （标签列 A 取值 {24: '……'}）…应声明 last_data_row=23（剔除尾部 1 行占位行）…
    __cause__=TypographyRowError error_code=managed_last_row_is_typography_placeholder
[原 DEBIT=16 + 原 CREDIT=24] InstrumentationError: …末行 16 落在排版占位行上…（段①先抛，fail-fast）
[当前 managed_row_table_specs()] PASS
```

### 3c/3d A 列实际文本（OOXML 直读，与门禁同一读法 `read_column_text`）

```
D3-4 段① first=13 last=15 footer=17:  A12='对方科目：' A13='资产处置损益' A14='固定资产' A15='增值税'
                                      A16='……' placeholder=True   A17='差异'
D3-4 段② first=22 last=23 footer=25:  A21='本期贷方发生额合计' A22='其中：银行存款收款' A23='应收票据'
                                      A24='……' placeholder=True   A25='差异合理性分析'
D3-5 first=11 last=13 footer=14:      A10='对方单位名称' A11..A14=None（全空）
D3-6 first=12 last=16 footer=17:      A11='关联方名称' A12..A16=None（全空） A17='合计'
A24 前导空格核查：is_typography_placeholder('         ……')=True（空格 ∈ TYPOGRAPHY_CHARS，且 decode_cell_text 先 strip）
```

结论：
- ✅ 上一次运行的 16→15 / 24→23 **正确**，与门禁给出的应声明值逐字一致；A24（带前导空格）判为占位成立，不回滚。
- ✅ D3-6（末行 16）/ D3-5（末行 13）数据区 A 列为空格（`None`），空串按定义不是占位行 ⇒ 不命中 BP-21
  （结论来自 A 列实读，非"注入没报错"推断）。
- ✅ 契约 JSON 不含 `last_data_row`（§2 补充观察），无需重生成。

### 3e 旁证发现（非 BP-21，登记给后续段，本段不修）

🔴 **D3-5 footer marker 在模板上不存在**：契约声明 `footer_anchor={marker:'合计', search_column:'A'}`，但
D3-5 第 14 行实测只有 `B14='=SUM(B11:B13)'` / `F14='=SUM(F11:F13)'`，A14 为空；整个 A 列非空格为
`{1..8 页眉/目标/过程, 10:'对方单位名称', 15:'三、审计说明', 19:'四、审计结论'}`，**没有任何「合计」**。
`excel_materialize._find_marker_row(xml, column='A', marker='合计', min_row=11)` 实测返回 `None`。
`assert_footer_anchor_stable`（materialize 计划期 L1724 对每个 dynamic region 调用）在 `observed is None`
时抛 `FooterAnchorDriftError("契约声明的 footer marker '合计' 在列 A 上一处都找不到…")`。
⇒ 推断：第 2 段整册 materialize 一旦规划 D3-5 region 即 fail closed（代码路径推断 + 模板实测，**未端到端跑**）。
`phase5_d3_05_long_term.py` docstring 称"A14 本身也是 None——marker 由 footer_marker 声明…由框架层扫描定位"，
与框架层"marker 必须真实存在于 search_column"的语义不符。修法需要裁决（row 14 无任何文本，纯文本 marker
无从表达），留给 orchestrator。

## §4 基线判据迁移

### 4.0 迁移前失败清单（Step 3 首跑，`-k "d3 or D3"`，cwd=backend）

```
8 failed, 70 passed, 1 skipped, 9003 deselected, 1 xfailed, 4 errors in 28.47s
```

| 用例 | 现象 | 归因 |
|---|---|---|
| `test_d3_expansion.py::test_switches_off_equals_current_state` | `assert True is False` | 开关翻转（断言默认值 False） |
| `test_d3_expansion.py::test_enabling_d306_adds_one_managed_region` | `assert 4 == 1` | 开关翻转（D3-4/D3-5 默认也开） |
| `test_d3_expansion.py::test_store_item_ids_have_no_duplicates` | 期望 2 项实得 5 项 | 开关翻转 |
| `test_d3_expansion.py::test_alignment_guard_reports_exact_diff` | DID NOT RAISE | 开关翻转（"关开关时的契约"变成了全开契约，D3-6 再开无差集） |
| `test_d3_expansion.py::test_build_contract_payload_unchanged_when_switch_off` | `assert True is False` | 开关翻转 |
| `test_d3_property3_4_dual_zone_baseline.py::test_current_d3_managed_region_count_is_pre_expansion_baseline` | 期望 1 实得 5 | 开关翻转（红基线按设计转变） |
| `test_d3_property3_4_dual_zone_baseline.py::test_d3_4_dual_zone_not_yet_reaching_target_count_of_four` | `count < 4` 实得 5 | 开关翻转（Property 3 转绿信号） |
| `test_d3_06_offline_materialize_and_verify.py` 4 个 ERROR（fixture `contract_with_d306`） | `assert 4 == 2`（契约 sheet 数） | 开关翻转（fixture 只 monkeypatch D3-6，D3-4/D3-5 默认已开） |
| `test_d3_04_dual_zone_shift_and_verify.py::…::test_cumulative_two_pass_insertion_still_verifies_correctly` | `UnmanagedRegionDriftError: workbook_and_styles: 9527179c812a… → 78be9a7ccc41…` | **第 2 段范围**，本段只记录不改 |

无契约导致的失败（§2 已证一致）；无并发会话文件落在 `-k "d3 or D3"` 范围内导致的失败。
`test_task5_d3_performance_baseline.py` 7 条全过（见 4.3）。

### 4.1 `test_d3_property3_4_dual_zone_baseline.py`

改名前 grep：两个旧函数名在仓库代码中只出现于本文件自身；另见于 task4/7/8 证据文档（append-only 历史，不回改）。

- `test_current_d3_managed_region_count_is_pre_expansion_baseline`（==1）→
  `test_current_d3_managed_region_count_after_stage2_is_five`：按 sheet_key 钉死分布
  `{d32:1, d36:1, d34:2, d35:1}` + 总数 ==5（互相抵消的多/少也会红）。
- `test_d3_4_dual_zone_not_yet_reaching_target_count_of_four`（<4）→
  `test_d3_4_dual_zone_both_keys_declared_in_one_sheet`：**Property 3 转绿** —— 计数 ≥4；
  excel_name=`预收账款分析表D3-4` 的契约 sheet 条目恰 1 个、sheet_key=`d34-managed`、table 恰
  `[analysis_debit_rows, analysis_credit_rows]`（Excel 行序）、各表字段 `store_item_id` 分别恰为
  `{D3-ana-debit-rows}` / `{D3-ana-credit-rows}`（store 键字面量逐字取前端 `useD3Analysis.ts`
  `ITEM_ID_DEBIT_ROWS`/`ITEM_ID_CREDIT_ROWS`，已 grep 核对）。
- `test_d3_7_dual_zone_not_yet_reaching_target_count_of_seven`：**保持红基线**（计数 <7；
  `D3-vc-current-rows`/`D3-vc-post-rows` 未出现；`预收账款检查表D3-7` 不在契约 sheets）。
  🔴 修掉一处**空转**：原判据用子串查 `stable_field_key`，而其真实形态是
  `{table_key}/{row_uuid}/{column_key}`（实测 53 个键，例 `analysis_debit_rows/{row_uuid}/label`），
  永不含 store 键片段——D3-4 已接入时 `"ana-debit" in stable_field_key` 实测 **0 命中**，即原 D3-4/D3-7
  两处"键未出现"断言从 Task 4 起就恒真。改为读 canonical payload 的字段 `store_item_id`（解析后的
  `FieldSpec` 不携带该属性），并加"查法非空转见证"：已接入的 D3-4 两键必须能被同一查法查到。
- §2 三组合成变异用例**原样保留**（未改一行）。

### 4.2 `test_d3_expansion.py`

- 新增 `_ALL_SWITCHES` / `_switch_all_off(monkeypatch)` / `_STAGE2_STORE_ITEMS`。
- 新增 `test_default_state_has_d306_d304_d305_enabled`：三开关 True；扩容面 ==
  `(SPEC_D306, SPEC_D304_DEBIT, SPEC_D304_CREDIT, SPEC_D305)`；instrumentation sheet_key 序列
  `[d36, d34, d34, d35]`；store items == 5 项；磁盘契约一致且对齐守卫通过。
- `test_switches_off_equals_current_state` → `test_switches_off_reverts_to_d3_2_only`：显式关三开关再断言
  扩容面空 / store 只剩 `D3-det-rows`（不再依赖默认值）。
- `test_enabling_d306_adds_one_managed_region` / `test_alignment_guard_passes_when_switch_and_contract_are_both_on`：
  先全关再只开 D3-6（保持"1→2"原意图）。
- `test_store_item_ids_have_no_duplicates`：默认态 == 5 项且无重复（D3-4 两区若串成同一 store 键会掉到 4 项）；
  只开 D3-6 态 == 2 项。
- `test_alignment_guard_reports_exact_diff`：全关契约 + 开 D3-6 ⇒ 精确报 `d36-managed`（原逻辑）。
- 新增反方向变异 `test_alignment_guard_catches_disk_contract_missing_a_sheet_when_one_more_switch_on`：
  磁盘契约（monkeypatch **之前**用 `load_contract_from_disk()` 取）+ 关 D3-5 ⇒ 报
  `契约有而 spec 缺: ['d35-managed']`。
- `test_build_contract_payload_unchanged_when_switch_off`：显式全关 ⇒ 1 张 sheet；并加"全关时 D3-2 项 ==
  全开时 D3-2 项"（扩容面只追加不改 D3-2）。
- monkeypatch 关开关的用例均**不调** `assert_contract_file_matches_source()`。

### 4.3 `test_task5_d3_performance_baseline.py`（未改动，7 passed）

`-s` 实测输出：

```
[real-stack] register_from_manifest() 现状真抛出：ContractDriftError: contract d2.receivable_detail: 结构漂移，
  首个不一致位置 sheet='d21-managed' table='adjudication_cells' field='adjudication_cells/aging_b' locator='B:static:10'
  —— 不得继续按旧坐标写格；必须按 template → instrumentation → contract → bundle → representation 显式发布新 definitions
[isolated] manifest 里 D3 现状 capability='single_onlyoffice'  adapter_id=None ；attach_pilot_adapters() 返回：()
[synthetic-engine] n_rows=1/10/50/200 store_field_count=27/270/1350/5400 elapsed_ms=0.340/0.638/2.546/11.850
[real-db-payload] item='D3-det-rows' payload_bytes=59 store_field_count=27 elapsed_ms=0.205
```

`test_real_registration_path_fails_before_reaching_d3` **仍真实抛错**（本地 PG `audit-postgres` 可连）：共享注册
仍在 D2（`d2.receivable_detail` / `d21-managed` 审定表 `aging_b` B:static:10）契约漂移处先炸，D2 lane
`be8bb7c86`/`441a93b7f` 的修复没有消除这处漂移（真库 published 与现算契约仍不一致）。断言与现状相符，保持原逻辑。
合成基线用例经 `assert_contract_file_matches_source()` 通过（§2 契约已一致）。

### 4.4 `test_d3_06_offline_materialize_and_verify.py`

fixture `contract_with_d306`：删掉 `MonkeyPatch.context()` 只开 D3-6 + `len(sheets)==2` 的权宜形状，改为
真实磁盘契约 `assert_contract_file_matches_source()`，断言 `d36-managed` 在场且 D3-2 仍为第一张（不按总张数，
总数随 D3-7/D3-1 接入还会变）。6 条用例在 4-sheet 真实契约上全过（D3-6 region 定位 / verify 覆盖计数非零 /
改 D3-1 无关 sheet 必判不等价）。

### 4.5 三文件迁移后单跑

```
python -m pytest tests/workpaper_sync/test_d3_expansion.py tests/workpaper_sync/test_d3_property3_4_dual_zone_baseline.py
  tests/workpaper_sync/test_d3_06_offline_materialize_and_verify.py -q --tb=short
21 passed, 1 warning in 2.14s
```

## §5 D3 范围测试结果

命令（cwd=backend）：`..\.venv\Scripts\python.exe -m pytest tests/workpaper_sync -k "d3 or D3" -q --tb=no -rsxf`

| 轮次 | 结果 |
|---|---|
| Step 3 首跑（迁移前） | 8 failed, 70 passed, 1 skipped, 1 xfailed, 4 errors |
| Step 5 复跑（迁移后） | **2 failed, 82 passed, 1 skipped, 1 xfailed, 0 errors**（9003 deselected, 28.50s） |

仍失败 2 条，逐条归因：

1. `test_d3_04_dual_zone_shift_and_verify.py::TestVerifyUnmanagedRegionsAccumulatesAcrossMultipleInsertions::test_cumulative_two_pass_insertion_still_verifies_correctly`
   —— `UnmanagedRegionDriftError: workbook_and_styles: 9527179c812a… → 78be9a7ccc41…`。**第 2 段范围**，本段未改。
   同文件其余 6 条通过。
2. `test_row_table_engine_core_equivalence.py::test_fail_closed_behaviours_match[d3]`
   —— `AssertionError: D1 尚未声明化，应仍导出 iter_store_rows`（L155）。**并发会话导致**：Step 3 首跑时本条
   是通过的；两次运行之间 `phase5_d1_notes_receivable.py` 被另一会话改动（mtime 09:20:16，本段复跑 09:20:37 前
   21 秒；`git diff --stat` +57/−135，删除了 `iter_store_rows`/`store_row_identity`/`split_store_row`，即 D1 Task 15
   声明化）。该断言是参数化用例末尾对 **D1** 的共享断言（`[d3]` 参数也会执行），与 D3 本身无关；`[d1]` 参数不含
   "d3" 故被 `-k` 过滤掉。本段不在范围、不修（属 D1 lane 在途改动，需由该 lane 把判据改成纯引擎断言）。

跳过/预期失败（均与本段无关，如实登记）：
- SKIPPED `test_d3_property2_store_item_id_exact_match.py:281`：`phase5_d3_07_voucher_check` 尚未声明（Task 11）。
- XFAIL(strict) `test_store_payload_error_stays_domain_error.py::test_d3_bad_store_payload_should_also_raise_domain_error`：
  D3 与 D5/D6/D7 同缺 `RowTableStorePayloadError → StorePayloadError` 转译（xfail 原因文本明写"D3 lane 修好后会 XPASS
  而红，届时删 xfail 并把 d3 并入 `_DOMAIN_ERROR_PROVIDERS`"）。**未在本段修**（不在第 1 段指令范围），登记给 orchestrator。

附带核验（只读，不 `--update`）：
- 双区位移链参数化判据 `test_sibling_table_ref_row_shift.py::test_all_multi_region_sheets_shift_sibling_table_refs`：
  `[重要客户结构分析D4-9] PASSED` / `[预收账款分析表D3-4] PASSED` —— D3-4 已自动进入参数化覆盖清单并通过。
- `python scripts/check/check_sync_provider_golden_digest.py`：`✅ golden digest 零回归：75 个 digest 逐个不变`。

第 1 段结论：契约一致（5 受管区）；BP-21 几何修正经真实注入路径复核正确；三个基线文件 + D3-6 离线验收 fixture
已按"已接入"语义迁移；D3 范围内除第 2 段文件与并发会话导致的 1 条外全绿。**§3e 的 D3-5 footer marker 缺失是
第 2 段整册 materialize 的潜在阻塞，需先裁决。**

---

> 第 2b 段（D3-4 双区位移链验收）从此处起追加。D3-5 相关（`phase5_d3_05_long_term.py` /
> `_INCLUDE_D305_LONG_TERM` / `d35-managed`）与整册 materialize 由并行的第 2a 段 / 用户裁决负责，本段不碰。

## §6 两趟累积插行漂移诊断（`workbook_and_styles`）

### 6.1 复现 + 定位到 part

`python -m pytest tests/workpaper_sync/test_d3_04_dual_zone_shift_and_verify.py -k cumulative` ⇒ 复现
`UnmanagedRegionDriftError: workbook_and_styles: 9527179c812a… → 78be9a7ccc41…（before 覆盖 3 项，after 覆盖 3 项）`。

aspect 定义（`excel_extract._classify_parts` L1956）：`workbook_and_styles` 桶 = `xl/workbook.xml` + `xl/styles.xml` +
`xl/theme/*`，D3 册实测 3 个 part；被 `propagation` 声明点名的 part 走 `_propagation_normalised_digest`
（= `excel_workbook_row_change.normalise_propagated_part` 逐条逆替换后再 hash），其余逐字节。

一次性探针（`backend/_task10_2b_probe.py`，用完即删；驱动手法与本测试同款：真实注入产物 + 合成 definitions +
`build_excel_adapter(sibling_bindings=…)` + `adapter.materialize` + `adapter.verify_unmanaged_regions`）逐 part 比对：

```
n_up=5 n_lo=5  declared=7 reverted=8  per_part_equal={'xl/workbook.xml': False, 'xl/styles.xml': True, 'xl/theme/theme1.xml': True}
```

⇒ **只有 `xl/workbook.xml` 变了**，styles.xml / theme1.xml 逐字节相等（不是 xf 条目增减）。逐个 definedName 对照：

```
GT_MANAGED_REGION_D34CREDIT  before=$A$22:$D$23  after=$A$27:$D$28  norm=$A$17:$D$23   <== 归一化后 != before
（其余 6 个 D3-4 definedName：norm == before）
声明链：GT_FOOTER_ANCHOR_D34DEBIT  $A$17 -> $A$22        （段①趟）
        GT_MANAGED_REGION_D34CREDIT $A$22:$D$23 -> $A$27:$D$28（段①趟）
        GT_FOOTER_ANCHOR_D34CREDIT $A$25 -> $A$30 -> $A$35  / Print_Area $39 -> $44 -> $49（两趟链）
```

### 6.2 根因：`normalise_propagated_part` 逐条 `str.replace` 的**跨条目子串碰撞**（引擎缺陷，非测试构造错误）

`ref_after`/`ref_before` 是**整段 token**（`'预收账款分析表D3-4'!$A$22`），verify 侧按「链深度、长度」排序后对**整份
workbook.xml 文本**逐条 `str.replace`。段①插 5 行时：

1. 先还原 `GT_MANAGED_REGION_D34CREDIT`：`'…'!$A$27:$D$28` → `'…'!$A$22:$D$23`（正确）；
2. 再还原 `GT_FOOTER_ANCHOR_D34DEBIT`：`'…'!$A$22` → `'…'!$A$17` —— `'…'!$A$22` 恰好是**上一步刚还原出来的**
   `'…'!$A$22:$D$23` 的**前缀子串** ⇒ 被误改成 `$A$17:$D$23`，`reverted` 计 8（声明 7，多 1 次）。

碰撞条件 = 「上区 footer 行 + 插入行数 == 下区首行」（17+5=22）。它**与趟数无关**，只与行数有关：

| 段①行数 n_up / 段②行数 n_lo | declared / reverted | verify |
|---|---|---|
| 6 / 0 | 5 / 5 | PASS |
| **5 / 0**（单趟） | 5 / **6** | **FAIL workbook_and_styles** |
| 4 / 0 | 5 / 5 | PASS |
| **5 / 5**（本测试） | 7 / **8** | **FAIL workbook_and_styles** |
| 5 / 2 | 7 / 8 | FAIL workbook_and_styles |
| 0 / 5 | 2 / 2 | PASS |
| **3 / 5** | — | **materialize 期即抛 `PropagationDriftError: 声明 5 处传播，实际只改了 6 处`** |

- 「单趟不漂、两趟才漂」**不成立**：同文件单趟用例用的是 6 行（22 碰撞点被越过），换 5 行单趟同样红；两趟用例恰好选了 5。
- **apply 侧有同一缺陷**（`excel_materialize._apply_workbook_propagation`，同款整文本逐条 `str.replace`，
  长的先替换）：段①插 3 行时 `GT_MANAGED_REGION_D34CREDIT` 先被改成 `$A$25:$D$26`，随后 `GT_FOOTER_ANCHOR_D34CREDIT`
  的 `'…'!$A$25 → $A$28` 又命中它的前缀 ⇒ 多改 1 处，apply 期对账 fail closed（没有产出坏文件，但**正常业务行数下
  物化直接失败**）。`n_up=3` 是 D3-4 段①填满 6 行这种很普通的数据量。

### 6.3 对照 D4 已验证路径（commit `91f2ef584`）为什么没覆盖到

`91f2ef584` 修的是 ③-2「链式声明按链尾往前还原」（`_chain_depth` 排序），解决的是**同一 definedName 被两趟各改一次**
的中间态问题；它**没有**处理「**不同** definedName 的 token 互为前缀」——D4-1 两区的 definedName 行号组合恰好不撞，
判据 5（`test_verify_unmanaged_regions_passes_after_row_insertion`，主营 7 / 其他 6）也就从没走到这条路径。D3-4 的
几何（段① footer 17 与段② 首行 22 只差 5，且都用 `$A$` 列）把它暴露了出来。

测试构造核对（排除「测试写错了」）：`verify` 的 7 个入参取的是 `materialize` 结果随产物带出的同一份
（`row_shift` / `total_formula_rows` / `workbook_row_change` / `per_table_shift`），`sibling_bindings=(lower_binding,)`
完整，合成 definitions 的写法与 D4 判据 `_make_definitions` 逐字段同构；上表 `n_up=5` 单趟也红，进一步排除双 projection
合并的写法问题。⇒ **判定：引擎真实缺陷**，修主代码。

### 6.4 附带发现：两区都插行时的 `managed_sheet_unmanaged_cells` 红是**进程内 before-digest 缓存串味**

同一探针进程里，先跑某形状（如 `4/0`）再跑另一形状（`4/5`）会报 `managed_sheet_unmanaged_cells` 漂移；**单独新进程**
跑 `4/5` / `6/5` 均 PASS，`clear_all_parse_caches()` 后也 PASS。逐格 diff（探针复刻 `_managed_sheet_cell_digest`
的逐格口径，用该进程真实的 `CompositeRowShift`）before/after 记录**逐条相等**（120/120、112/112）。

根因：`verify_unmanaged_regions` 的 before 侧 LRU 键 = `before_sha | contract_id | sheet_part | table_key |
extra_parts | extra_coords`，**不含本 binding 自己的 managed 坐标集**。而 before 侧 digest 用的 `region` 是从
**after** 文件解析出来的（`adapters/excel.verify_unmanaged_regions` 只对 `after` 调 `resolve_managed_region`）——
同一 before 字节、同一 sibling 坐标，本区 region 行数随本次插行数变化 ⇒ 键相同、内容应不同 ⇒ 命中旧 digest。
生产上同一 published substrate 在进程内被多次 materialize（行数各不同）是常态 ⇒ **会误报 `adapter_unmanaged_region_drift`**。
本条红**不在** pytest 默认执行顺序里出现（本文件两条 verify 用例恰好都是首次命中），但它是真实缺陷，与 6.2 同属
「verify 门误判」一族，一并修（修法见 6.5，**未实施**）。

### 6.5 补测 + 修复方案（**未实施**）

补测：单趟（段②不插行）n_up 取 4..15，只有两个行数失败，其余都 PASS。
- **5**：verify 期 `workbook_and_styles` 误判。
- **8**：apply 期抛 `PropagationDriftError: 声明 5 处传播，实际只改了 6 处`。这是**第二类碰撞：整段相等**。段① footer 先改成 `'…'!$A$17 → $A$25`，
  接着段② footer 的声明 `'…'!$A$25 → $A$33` 一次命中两处。verify 侧 `_chain_depth` 按**文本相等**推断链，也会把这两条不同 definedName
  误连成一条链、还原错。

两类碰撞同一病根：**整份文本逐条顺序 `str.replace`**。后面的条目会扫到前面条目的替换产物，匹配也不看 token 边界。

框架文件：`git status` 确认 `excel_materialize.py` / `excel_row_shift.py` / `excel_extract.py` / `adapters/excel.py` /
`excel_workbook_row_change.py` 都没有他人未提交的改动，可以改。本段在动手前被中断，**没有改任何代码或测试**。建议修法：

1. apply 侧 `excel_materialize._apply_workbook_propagation`（每趟）：改成**单趟同时替换**，用一个 alternation 正则加 `re.sub` 回调，
   替换产物不会再被扫描。同时加**整 token 边界**：左边界同 `_left_boundary_ok`，右侧不得紧跟 `[0-9A-Za-z_$:]`。
2. verify 侧 `normalise_propagated_part`：做 apply 的**精确逆**，按趟倒序，每趟单趟同时逆替换（同一边界）。
   废弃按文本相等推断链的 `_chain_depth`。依赖第 3 条。
3. `merge_workbook_row_change_propagations` / `MaterializeWorkbookChangeSet`：保留**趟序**，新增 `trips`，扁平的 `propagations` 保持鸭子兼容。
   `(part, ref_before)` 冲突守卫收窄到同趟内（推断，未实测）。
4. `excel_extract.verify_unmanaged_regions` 的 before 侧 LRU 键补上本 binding 的 region 几何（`region.table_ref`）。

防御测试（待写）：
- 两类碰撞在 apply 和 normalise 两侧的纯函数判据；
- D3-4 真实 adapter 判据：单趟 `n_up∈{3,5,8}`，加两趟 5/5；
- 同进程先 `(4,0)` 后 `(4,5)` 的缓存串味判据。

触类旁通（推断，未实测）：碰撞只取决于几何和行数，D4 同 sheet 多区（D4-1/9/20/34/36）在特定行数下也可能中招。
失败都是 fail closed（500），不会产出坏文件。

## §7 需用户知晓的引擎边界：footer 散落单格差异公式不随插行扩张

> 第 3c 段收口。**不修**（用户没要求；且它与本次修的两处 SUM 缺陷是不同性质——SUM 冒号区间能扩、
> 散落单格相减不能）。仅登记：是全平台既有边界而非 D3 独有，写清业务后果。

### 7.1 边界性质

引擎的 footer 公式区间归一化（`excel_materialize.assert_footer_formula_covers_managed_rows` +
`excel_row_shift` 的 `extend_end_at`）只认 `_RANGE_IN_FORMULA_RE` 匹配的 **`A1:B2` 式冒号区间**
（如 `SUM(B7:B25)`）。D3-4 段①借方差异公式 `B17=B11-B13-B14-B15-B16` 是**散落单格引用相减**、
不含任何冒号区间 ⇒ 检测器空 match 集：既不报错、也不扩张。插行后单格引用被 `propagate_reference_side`
正确重映射（`B16→B19` 跟随物理下移），但公式**不覆盖**新插入的业务行 ⇒ 差异数漏算新增行、且两道门
静默放行（`test_d3_04` 的 `TestFooterFormulaRangeNormalizationRealBoundary` 已钉住此真实行为）。

### 7.2 grep 全平台同类（非 SUM 冒号区间的 footer 聚合/差异公式）

grep `app/services/workpaper_sync/phase5_*.py`（footer 层、非 per-row formula_columns）：

- **数据行级差异公式**（`formula_templates`/`formula_mask`，**逐行随插行自动扩张**，非本边界）：
  D1-15 `E=B{r}-D{r}`/`F=D{r}-E{r}`、D4-6 `D/G` 差异率、D4-10 `J/M`、D4-11 `J/L`、D4-adjudication
  `E/I` 审定 SUM。这些是"数据区内哪列逐行有公式"，插行时按模板逐行铺，**不属**本边界。
- **footer 层散落单格聚合/差异公式**（= 本边界：非 `SUM(range)`，引擎不扩张）——实测命中 **3 处**：
  1. **D3-4 段①借方**（本次）：footer R17 `B17=B11-B13-B14-B15-B16`（散落单格相减）。
  2. **D4-1 审定表**（`phase5_d4_adjudication_sheet.py`）：footer 三行 合计 R19 / TB 核对 R20 /
     **差异 R21**，`_FORMULA_ROWS` 声明 B–I 全为 Excel 内部公式；差异行 R21 = 合计−TB核对（footer
     行间相减，非数据区 SUM 冒号区间）。
  3. **D1-07 备忘**（`phase5_d1_07_memo.py`）：R25 合计"公式引用 Q18+Q24 等"（散落 footer 小计相加，
     非单一 `SUM(range)`）。
  （E1 现金：delivered provider 未见此类 footer 散落差异公式；E1 footer 多为标准 `SUM`。）

### 7.3 业务后果 + 登记

后果：这类 footer 差异/聚合格在用户插入超出模板占位的业务行时，**差异数漏算新增行且不报错**——引擎
产出一张"差异计算漏算"的审计底稿而 fail closed 两道门都放行。是"footer 公式区间归一化只覆盖结构化
`SUM(range)`"这一既有设计的普遍后果，**非 D3 独有**（至少 D3-4 / D4-1 / D1-07 三家共此边界）。
**本段不改引擎、不改模板**（与本次修的 D3-6 SUM 区间可扩 / D3-5 marker 缺失属不同性质）。登记给
orchestrator/用户知晓：若要根治需扩展 `_RANGE_IN_FORMULA_RE` 支持散落单格引用集的插行重映射扩张，
影响面覆盖全平台 footer 差异公式，应另起 spec 评估。

## §8 `_GT_SYNC` footer 坐标重冻结（D3-4 段①插行后）

> 第 3c 段收口。补一条离线判据读产物 `_GT_SYNC` 的 `GT_FOOTER_ROW_D34DEBIT`。

新增判据 `test_d3_04_dual_zone_shift_and_verify.py::TestGtSyncFooterRowReFrozenAfterD34DebitInsertion::
test_footer_row_key_shifts_by_inserted_count`（**passed**）：走唯一读侧入口
`excel_extract.read_runtime_binding_pairs`（不手搓第二份）。

- 前提：产物 `_GT_SYNC` 存在键 `GT_FOOTER_ROW_D34DEBIT`（= `GT_FOOTER_ROW_{TEMPLATE_ID_D304}DEBIT`），
  插行前冻结值 == 段① footer 行 `UPPER.footer_row`（17）。
- 段①经真实 `build_excel_adapter` + `adapter.materialize` 插 5 行（`result.row_shift.count` 取实际插入数），
  读产物 `_GT_SYNC`：`GT_FOOTER_ROW_D34DEBIT` == 17 + row_shift.count（重冻结为下移后行号，声明与物理同源）。

⇒ D3-4 段①插行后 `_GT_SYNC` footer 坐标**能读到且已按插行数重冻结**，断言通过。
（旁证：definedName 侧 `GT_FOOTER_ANCHOR_D34DEBIT` 17→22 等亦随声明位移，见 §6.1；本条钉住的是
`_GT_SYNC` 本体的 `GT_FOOTER_ROW_*` 键，与 definedName 是两处。）

## §9 整册 materialize 判据 + D3 范围回归（第 3c 段）

### 9.1 整册 materialize 判据（新增，模板修好后能真跑）

新增 `test_d3_04_dual_zone_shift_and_verify.py::TestFullBookMaterializeAfterTemplateFooterFix::
test_all_managed_regions_materialize_and_verify_equivalent`（**passed**）。离线驱动照抄本文件
`_synthetic_definitions` + `build_excel_adapter(sibling_bindings=…)` + `adapter.materialize` +
`verify_unmanaged_regions`：

- substrate = 权威模板 `instrument_workbook_bytes_multi([D3-2 单数声明] + P.instrumentation_specs() 扩容面全部)`
  （🔴 关键修正：`P.instrumentation_specs()` 只覆盖扩容面不含 D3-2，整册必须显式补 D3-2 primary 的 Table，
  否则 `resolve_managed_region('GT_D32_ROWS')` 抛 `IdentityCarrierMissingError`）。
- primary = D3-2（`GT_D32_ROWS`/uuid AB），siblings = D3-6 / D3-4借 / D3-4贷 / D3-5（Excel 行序）。
- 每区给 5 行真实行数（全新 rowId → orphan → 触发插行）。
- 断言：materialize 成功产出 staged 工作簿（`PK` 头）+ `per_table_shift` 非空（各区插行）+
  `verify_unmanaged_regions.equivalent is True`。

⇒ **D3-5/D3-6 模板缺陷修复后，D3 整册 materialize（5 受管区一次 materialize）verify equivalent=True**。
这是 §3e/§6.4/§2.2 一直说的"整册 materialize"，模板修好后离线整册链路真跑通过。
（真栈端到端仍受 adapter capability 限制不可测——§2.1 实测 D3 manifest capability=single_onlyoffice、
attach 不带 sibling、substrate 只注 D3-2；本条是离线整册链路，如实标注。）

### 9.2 D3 范围回归（cwd=backend，`-k "d3 or D3" -p no:cacheprovider`）

```
1 failed, 102 passed, 1 skipped, 9074 deselected, 2 xfailed, 4 warnings in 72.00s
```

对比 §5 的 2 failed/82 passed：passed 从 82→102（+20 = 本段新增 3 条 D3-04 判据被 `-k d3` 命中 +
3a/3b 引擎修复后一批转绿），failed 从 2→1。

**唯一失败逐条确认（非本段新引入）**：
- `test_task5_d3_performance_baseline::test_real_registration_path_fails_before_reaching_d3` —— `DID NOT
  RAISE`。**本段前即红**（§10.1 命令 B / §10.8 / §10.10 均已登记为并发会话导致：真注册路径不再先于 D3
  失败，是别 lane 把更早 entry 的契约漂移收敛了）。该测试断言 `register_from_manifest` **应抛**（在到达
  D3 之前的其他 entry 契约漂移处先炸）；本段的 D3 模板/契约改动只会让 D3 契约**更**脱离 store（若有影响是
  增加失败不是消除），**不可能**把"应抛"变成"没抛"（那发生在 D2 等更早 entry，本段没碰 D2）。⇒ 非本段回归。
- §5 曾红的 `test_d3_04...test_cumulative_two_pass_insertion_still_verifies_correctly` 已在 3b 转绿（§10.8）。

**本段新增失败 = 0。**

### 9.3 模板连带 + 定向回归

| 组 | 结果 | 备注 |
|---|---|---|
| `test_sibling_table_ref_row_shift` + `test_d3_04`（含本段新增 3c 判据）+ `test_workbook_propagation_ref_collision`（3a/3b） | **63 passed** | D3-4 已入参数化位移覆盖；整册 + §8 GT_FOOTER_ROW 判据全绿 |
| `test_workbook_row_change_wiring` + `test_workbook_row_change_verification` + `test_multi_sheet_workbook_change_merge` + `test_d3_06_offline_materialize_and_verify` + `test_d3_expansion` + `test_d3_property3_4_dual_zone_baseline` | **58 passed** | apply/verify/merge 引擎判据 + D3 扩容/基线判据零回归 |
| `test_wp_templates_readonly`（模板只读守卫） | **本段前即红，仍红** | 净化波 D3/D5/D6/D7 + D4 改名/新增全未同步基线（§11.0）；本段只同步了 D3 一条 sha/size，D4/D5/D6/D7 仍红（非本段范围，别 lane 处理）。且此守卫本存 D3=净化前 `8a27614b`，比净化值还旧一代 |
| `test_task46_d_cycle_migration`（manifest slice digest） | **本段前即红，仍红** | slice 是 Task 46 lane owned frozen slice，triage 标 BLOCKED（§11.3 #5），本段未碰 |
| `test_excel_row_insertion_scope_closure::…carried_by_the_definition_store` | **本段前即红，仍红** | definition_store 内容寻址链，§11.4 停下报告未改 |
| `test_workbook_row_change_zero_regression::test_behaviour_matches_frozen_baseline` | **本段前即红，仍红** | 5 处漂移仅 D3 一处是本段的（合理），其余 4 处 D4/D7 别 lane；`--apply` 会掩盖别 lane 漂移故不做（§11.3 #6） |

### 9.4 golden digest（不 --update）

`python scripts/check/check_sync_provider_golden_digest.py`：`✅ golden digest 零回归：73 个 digest 逐个不变`。
⇒ **无需 --update**：该门比对 per-sheet contract payload + store projection + instrumentation 几何 digest，
footer SUM 区间 / A14 文字 / template_sha256 / normalized_structure_hash **都不进**这三项（契约 sheets
payload 无 footer 公式、instrumentation footer_row 未变：D3-6 仍 17 / D3-5 仍 14）。D3 几何 digest 未变，
其余家不变，无漂移。

### 9.5 D4 真栈（confirm 模板修复没碰坏 D4 生产路径）

仓库根 `.venv\Scripts\python.exe backend/scripts/e2e/verify_d4_full_book_real_stack.py`（`audit-postgres` healthy）：
**退出码 0**，`[④] materialize OK 5.7s / [⑤] extract OK 1.6s / [⑥] verify OK equivalent=True`。D4 用不同模板
（`D4 收入底稿.xlsx`），本段只改 `D3 预收账款.xlsx`，D4 生产闭环不受影响。

### 9.6 探针清理

一次性探针 `_probe_3c_inspect.py` 已删。`.prefooterfix.bak` 保留（gitignore，安全回滚用）。

## §10 引擎修复（第 3 段：跨 sheet 引用改写碰撞 + verify 缓存键）

> 第 3 段执行记录。只改框架层 `excel_materialize.py` / `excel_workbook_row_change.py` / `excel_extract.py` /
> `parse_cache.py`（如需）+ 新测试文件。§1~§9 不改。

### 10.0 开工核查（git status / 调用点 grep）

- `git status --porcelain`：四个框架文件（`excel_materialize.py` / `excel_workbook_row_change.py` / `excel_extract.py` /
  `parse_cache.py`）**没有**未提交改动，可以改。`test_d3_04_dual_zone_shift_and_verify.py` 是未跟踪文件（第 2b 段产物），本段不改它的断言。
  工作树里还有别的会话的改动（`phase5_d3_prepaid_receipts.py` / `phase5_row_table_sheet.py` / 契约 JSON 等），所以基线只能在改代码前先跑一次，不用 stash。
- 调用点：`merge_workbook_row_change_propagations` 共两处，都在 `adapters/excel.py`。一处是逐趟链式路径：`trip_changes` 按 binding 顺序 append，
  **趟序在这里是可得的**，进 merge 后按去重键 `sorted` 才丢掉。另一处是单趟路径：单趟遇到插行就 decline，所以该路径的 workbook_row_change 应该全是 None。
  `MaterializeWorkbookChangeSet` 的消费方只读 `.propagations`：`excel_extract.unmanaged_region_digest`（取 part 集合）→
  `_propagation_normalised_digest` → `normalise_propagated_part`。
- 既有判据钉住的旧语义（改动必须兼容，或按新语义改写）：
  - `test_multi_sheet_workbook_change_merge.py`：`test_conflict_same_before_two_afters_raises`（两个 plan 同 before、不同 after 必须抛）、
    `test_dedup_identical_entries`、重复条目守卫。
  - `test_workbook_row_change_wiring.py` 的 AST 判据：apply 源码里不能有 `scan_reference_carriers`，必须有 `plan.sheet_part` + `continue`，
    而且要排在 `patch_sheet_xml_indexed` 之前。
  - `test_workbook_row_change_verification.py`：「按出现次数计量」；`_propagation_normalised_digest` 源码里必须有 `normalise_propagated_part`。

读码结论（实施依据，**均未实施**）：
1. apply 本来就是**逐趟**执行的：每趟 `apply_plan_zip_with_report` 只消费本趟的 `plan.workbook_row_change`。§6 的两类碰撞都发生在
   **同一趟内**（D3-4 段①这一趟同时声明了 D34DEBIT footer、D34CREDIT region、D34CREDIT footer、Print_Area）。所以 apply 侧改成
   「每趟每个 part 一次同时替换」就能根治，不依赖趟序。
2. verify 侧拿到的是合并后的扁平清单，所以必须在 merge 里保留 `trips`。只靠文本推断链不可行，反例：单趟 8 行时，
   D34DEBIT `$A$17→$A$25` 和 D34CREDIT `$A$25→$A$33` 在同一趟。一次同时逆替换就是对的；如果迭代到不动点，会把 D34CREDIT 的
   `$A$25` 再退成 `$A$17`。`_chain_depth` 的误连是同一个问题。
3. merge 新语义草案：冲突只在**同一趟内**成立。同一趟里同一个 `(part, ref_before)` 却给出不同的 `ref_after`，等于同一个改写器对同一输入给出不同输出，
   不可能合法。跨趟同 before、不同 after 可以是合法的（链式声明，或不同 definedName 文本恰好相同）。跨趟逐字相同的条目去重：apply 期不可能
   真改两次，否则第二次 count=0 时就已经 fail closed 了。⚠ 这会改变 `test_conflict_same_before_two_afters_raises` 的期望（两个 plan
   就是两趟），需要按新语义改写这条判据。
4. 边界设计（待写进 docstring）：
   - 左边界：用 `_LEFT_BOUNDARY_BLOCK` 生成 lookbehind，与 `_left_boundary_ok` 是同一个字符集合，保证和扫描器同口径（含 `]`，挡住外部工作簿）。
   - 右边界：必须与扫描器 `_REF_TOKEN_RE` 贪婪匹配的 token 终点一致。数字、字母、`_$.` 阻断。`:` **只在后面跟 `$?[A-Za-z0-9]` 时阻断**；否则像
     `'S'!A1:'S'!B2` 这种被扫描器拆成两条声明的写法会少替换，变成 fail closed 回归。`#` 不阻断：`A1#` 是溢出引用，锚格应该随位移。
5. 缓存串味机理（按 §6.4 推算，**未实测**）：before 侧 `_managed_coordinates` 用的是 `region.row_span` + `region.uuid_column`，而 region
   是从 after 解析出来的。`before_key` 包含兄弟区的 `extra_coords`，却不包含**本区**几何。(4,0)→(4,5) 时，lower binding 的 extra_coords
   （upper 13..16）两次相同，本区却分别是 23..24 和 23..27，于是命中旧 digest。修法：键补 `region.table_ref/first_row/last_row/first_column/
   last_column/uuid_column`。同一 region 的键仍然逐字相同，所以本应命中的场景不会 miss。

### 10.1 修复前基线（失败清单）

第 3a 段执行（apply 侧同时替换 + verify before 缓存键）。改代码前 `git status --porcelain --
excel_materialize.py excel_extract.py` 为空（两文件干净）。cwd=backend，`..\.venv\Scripts\python.exe`。

**命令 A**（五个定向文件）：`python -m pytest tests/workpaper_sync/test_workbook_row_change_wiring.py
tests/workpaper_sync/test_workbook_row_change_verification.py tests/workpaper_sync/test_multi_sheet_workbook_change_merge.py
tests/workpaper_sync/test_sibling_table_ref_row_shift.py tests/workpaper_sync/test_d3_04_dual_zone_shift_and_verify.py -q --tb=line`

```
1 failed, 59 passed in 15.44s
FAILED test_d3_04_dual_zone_shift_and_verify.py::TestVerifyUnmanagedRegionsAccumulatesAcrossMultipleInsertions::test_cumulative_two_pass_insertion_still_verifies_correctly
  UnmanagedRegionDriftError: workbook_and_styles: 9527179c812a… → 78be9a7ccc41…（before 覆盖 3 项，after 覆盖 3 项）
```

（= §6.1 已复现的 verify 侧碰撞，5/5 两趟；属 3b 范围。）

**命令 B**（`python -m pytest tests/workpaper_sync -k "d3 or D3 or d4 or D4" -q --tb=line -p no:cacheprovider`）：

```
2 failed, 492 passed, 1 skipped, 8592 deselected, 2 xfailed, 5 warnings in 227.31s (0:03:47)
FAILED test_d3_04_dual_zone_shift_and_verify.py::...::test_cumulative_two_pass_insertion_still_verifies_correctly
  （同命令 A，verify 侧碰撞，3b 范围）
FAILED test_task5_d3_performance_baseline.py::test_real_registration_path_fails_before_reaching_d3
  Failed: DID NOT RAISE any of (RegistryError, SyncDomainError)
```

第二条与本段无关（真注册路径不再先于 D3 失败，疑为并行会话的注册/契约改动所致，§5 时尚为 7 passed）；
本段不碰，只作基线登记。之后只对本段**新引入**的失败负责。

### 10.2 趟序保留（`merge_workbook_row_change_propagations` / `MaterializeWorkbookChangeSet`）

✅ 已实施（第 3b 段）。只改 `excel_workbook_row_change.py`。

- `MaterializeWorkbookChangeSet` 新增 `trips: tuple[tuple[PropagationEntry, ...], ...] = ()`。扁平
  `propagations` 保留为去重后的稳定排序并集——三个只读消费方不变：`excel_extract.py:2051`
  （`{entry.part for entry in propagation.propagations}` 取 part 集合）、`excel_materialize.py`
  apply（读 `change.propagations`）、`assert_propagation_declared_exactly`（按出现次数对账）。
  `__post_init__` 的 `assert_no_mutation_surface`（零写入面）+ 重复条目守卫**保留**（只对 `propagations`）。
- `merge_workbook_row_change_propagations` 按**输入顺序**把每个 plan 的 `propagations` 作为一趟放进
  `trips`（输入顺序 = `adapters/excel.py:544` 的 `trip_changes.append`，即 binding 顺序；`:689` 单趟路径
  同样保序）。扁平 `propagations` 仍按去重键 `sorted` 去重并保持稳定排序。空趟（无 propagations 的 plan）
  跳过不进 trips。
- **冲突守卫改语义**：由「跨全部输入的同 `(part, ref_before)` 两个不同 `ref_after`」收窄为**只在同一趟内**
  才抛 `PropagationDriftError`。跨趟同 before 不同 after 合法（链式，或不同 definedName 文本恰好相同）。
- 新增 `_trips_of(plan)` helper：`MaterializeWorkbookChangeSet` 有 `trips` 用之（空则退化为整个扁平集当
  一趟）；裸 `WorkbookRowChangePlan` ⇒ `(plan.propagations,)`。merge 与 verify 共用它。

一句话新语义：**冲突只在同一趟内成立；跨趟同 before 不同 after 合法（链式 / 文本巧合）；扁平 propagations
仍去重排序供三个只读方，趟序单独存进 trips 供 verify 精确逆。**

### 10.3 apply 侧单趟同时替换（`_apply_workbook_propagation`）

✅ 已实施（第 3a 段）。只改 `excel_materialize._apply_workbook_propagation` 函数体 + docstring。

- **做法**：每个 part 先对每个去重后的 `(ref_before, ref_after)` 按四种形态既定顺序
  （`_apos(_escape(x))` → `_escape(x)` → `_apos(x)` → `x`）选**第一个在原文里有边界命中**的形态
  （保留旧 `break` 语义：每个 before 只用一个形态），建「命中文本 → 改后文本」表；合成
  `lookbehind + (?:候选按长度降序、逐个 re.escape) + lookahead` 一个正则，`re.subn` 回调查表一次性替换。
  `applied` = 正则命中次数，仍与 `declared = len(part_entries)` 对账，两条既有消息原样保留。
- **边界**：左 = `(?<![…_LEFT_BOUNDARY_BLOCK…])`（由集合逐字符 `re.escape` 生成，与 `_left_boundary_ok`
  同一集合）；右 = `(?![A-Za-z0-9_$.]|:\$?[A-Za-z0-9])`。`#` 不阻断。字符集与理由写进 docstring。
- **形态预选的边界判定**用 `in`/`find` 预筛 + 逐位置判左右边界，不用正则 `search`：以 lookbehind 开头
  的正则没有字面量前缀，一次性基准实测 2.3MB 文本 × 50 候选逐个 `search` ≈ 0.98s，alternation 一次
  `subn` ≈ 0.02s，`str.count` ≈ 0.015s（探针已删）。
- **新增一条 fail closed**：同一趟同一 part 里同一命中文本被声明成两个不同 after ⇒ 抛
  `PropagationDriftError`（查表只能取一个，静默取一个等于替计划裁决）。正常计划不可能触发
  （`build_propagation_entry` 对同一 `ref.raw` 由同一改写器生成 after）。
- **AST 判据**：源码不含 `scan_reference_carriers`；保留 `plan.sheet_part` + `continue`；
  `apply_plan_zip_with_report` 未改 ⇒ 调用顺序不变。
- **右边界的语料核查**（一次性脚本，已删）：`backend/wp_templates/` 369 份、3,272 个 sheet/workbook part
  里，「限定单格后紧跟字母/`_`/`$`/`.`」与「`:` 后跟字母数字但不是区间续接」两种会被新边界阻断、
  而扫描器会在此处切 token 的写法**均为 0 处** ⇒ 新边界不会在真实模板上少替换。

**D3-4 真实 adapter，段①单趟插 k 行**。本趟 5 条声明全在 `xl/workbook.xml`，计划期顺序（探针直调
`plan_workbook_row_change_for_insert` 实测）= `Print_Area $A$1:$H$39` / `FOOTER_ANCHOR_D34DEBIT $A$17` /
`MANAGED_REGION_D34CREDIT $A$22:$D$23` / `FOOTER_ANCHOR_D34CREDIT $A$25` / `ROW_UUID_RANGE_D34CREDIT $K$22:$K$23`。
旧实现按长度降序（同长保持该顺序）逐条替换：k=3 时 CREDIT region 先成 `$A$25:$D$26`，CREDIT footer 的 `$A$25`
再命中其前缀；k=8 时 DEBIT footer 先成 `$A$25`，与 CREDIT footer 的 before 逐字相等。

| k | 旧实现（探针替回） | 新实现 | 新实现 workbook.xml（DEBIT footer / CREDIT region / CREDIT footer / Print_Area） |

| k | 旧实现（探针替回） | 新实现 | 新实现 workbook.xml（DEBIT footer / CREDIT region / CREDIT footer / Print_Area） |
|---|---|---|---|
| 3 | ❌ `声明 5 实改 6`（前缀碰撞） | ✅ | `$A$20` / `$A$25:$D$26` / `$A$28` / `$A$1:$H$42` |
| 4 | ✅ | ✅ | `$A$21` / `$A$26:$D$27` / `$A$29` / `$A$1:$H$43` |
| 5 | ✅ | ✅ | `$A$22` / `$A$27:$D$28` / `$A$30` / `$A$1:$H$44` |
| 6 | ✅ | ✅ | `$A$23` / `$A$28:$D$29` / `$A$31` / `$A$1:$H$45` |
| 8 | ❌ `声明 5 实改 6`（整段相等碰撞） | ✅ | `$A$25` / `$A$30:$D$31` / `$A$33` / `$A$1:$H$47` |

全部 = 模板值 + k，逐一核对无误。k 值与 `per_table_shift['analysis_debit_rows'].count` 实测相等
（派生行数 = 插入行数，全部是 orphan 身份）。verify 侧：k=5、8 仍判 `workbook_and_styles` 漂移，k=3/4/6 判等价
—— k=5/8 是 verify 侧 `normalise_propagated_part` 的同类碰撞（17+5=22；k=8 时 `$A$25` 链误连），留 3b。

### 10.4 verify 侧精确逆（`normalise_propagated_part`）

✅ 已实施（第 3b 段）。

- **共享原语放哪**：`excel_workbook_row_change.py` 新增 `_simultaneous_rewrite(text, pairs, *,
  conflict_message) -> (text, hits)`——「选形态（四形态既定顺序、每 source 只用第一个边界命中形态、
  旧 `break` 语义）+ 拼 alternation 正则（候选按长度降序 `re.escape`）+ 左右边界（左 = `_LEFT_BOUNDARY_BLOCK`
  lookbehind；右 = `(?![A-Za-z0-9_$.]|:\$?[A-Za-z0-9])`）+ `re.subn`」的**单一真源**。`_apos` 提到模块级供
  两侧共用。`_LEFT_BOUNDARY_BLOCK` 从 `excel_row_shift` import——已确认 `excel_row_shift` 不 import
  `excel_workbook_row_change`（只在注释/docstring 里字面提到），**不成环**。
- **apply 改为调共享原语，行为逐字不变**：`excel_materialize._apply_workbook_propagation` 删掉自带的
  `_apos`/`left_boundary`/`right_boundary`/`_has_bounded_hit`/swap 构建/subn，改为 `_simultaneous_rewrite(
  text, [(before, after)…], conflict_message=…)`。fail closed 两条消息逐字保留（同趟同段引用两个 after
  「声明自相矛盾，不得写盘」；`声明 N 处传播，实际只改了 M 处`）；AST 判据（无 `scan_reference_carriers`、
  有 `plan.sheet_part`+`continue`、`_apply_workbook_propagation` 排在 `patch_sheet_xml_indexed` 之前）
  全保留。3a 的 25 条防御测试 + wiring/verification/apply 共 **63 passed**（§10.8）。
- **verify 精确逆**：`normalise_propagated_part` 接受 `WorkbookRowChangePlan | MaterializeWorkbookChangeSet`；
  用 `_trips_of(plan)` 取趟序，按趟**倒序**，每趟一次同时逆替换（pairs = apply 的逆 `(after, before)`），
  用同一个 `_simultaneous_rewrite`（同边界、同形态选择、与 apply 对称）。`reverted` 仍计「命中次数」
  （链式条目两趟各命中一次，合计 = 扁平 `propagations` 该 part 条数），`assert_propagation_declared_exactly`
  按出现次数对账不变。**废弃 `_chain_depth`**——逐趟倒序本身就是精确链还原，不迭代到不动点（k=8 反例：
  同趟 `$A$17→$A$25` 与 `$A$25→$A$33` 并存，不动点会退错）。
- `_propagation_normalised_digest`（`excel_extract`）源码里仍调 `normalise_propagated_part`（AST 判据），
  `&apos;` 对称、按出现次数计量的既有判据（`test_workbook_row_change_verification.py`）全绿。

### 10.5 before-digest 缓存键补 region 几何

✅ 已实施（第 3a 段）。`excel_extract.verify_unmanaged_regions` 的 `before_key` 在 `binding.table_key` 之后插入
`region_key = table_ref,first_row,last_row,first_column,last_column,uuid_column`（逐字取 `ManagedRegion` 的真实属性名，
定义见 `excel_extract.py` `class ManagedRegion`）。旁注释改写为串味机理。`before_sha` 仍在键里
（`test_single_pass_verify_not_relaxed` 的 AST 判据只查它）。

**机理实测**（一次性探针，已删；同一进程、同一 base、`clear_all_parse_caches()` 后顺序 verify）：

| 键 | (4,0) | 随后 (4,5) | 再 (4,0) |
|---|---|---|---|
| 旧键（探针把几何段剥掉模拟） | 等价 | ❌ `managed_sheet_unmanaged_cells`（before 覆盖 140 项 / after 120 项） | — |
| 新键 | 等价（miss 2） | ✅ 等价（miss 2，没有误命中） | 等价（hit 2，本应命中的仍命中） |

after 侧解析出的下区 region：(4,0) = `A26:K27`（26..27），(4,5) = `A26:K32`（26..32）；上区两次都是 `A13:J19`。
下区 binding 的 `extra_coords`（上区坐标）两次逐字相同 ⇒ 旧键相同 ⇒ (4,5) 拿到 (4,0) 的 before digest（排除 26..27
而非 26..32 ⇒ 多出 20 格）。§10.0 第 5 条推算的「23..24 / 23..27」行号不准，机理成立。

新键下 (4,5) 是 miss、按自己的 region 重算 before digest 后判等价 ⇒ 这组形状本身不碰 verify 侧碰撞
（17+4≠22，也没有 k=8 式的链误连），可以直接用来钉缓存键，不必换 (4,6)/(6,4)。

### 10.6 防御测试 + 变异反证

✅ 新文件 `backend/tests/workpaper_sync/test_workbook_propagation_ref_collision.py`，**25 passed / 6.7s**。

| 组 | 判据 | 条数 |
|---|---|---|
| ① apply 纯函数（`_bare_plan` 手法，照抄 wiring 判据） | `test_apply_rewrites_each_declared_reference_exactly_once` 参数化：前缀碰撞（产物前缀 / before 前缀两种）、数字边界前缀碰撞、整段相等碰撞、D3-4 真实 definedName 全集 `&apos;` 形态 k=3/5/8、左边界（`XS!` / `[1]S!`）、右边界（数字 / `:$D`，字面量里的更长 token 不被碰）、`'S'!A20:'S'!B30`（引号 / `&apos;` 两种）冒号不误阻断、`A20#` 溢出 | 13 |
| | 同趟同命中文本两个 after ⇒ fail closed；同一 before 混用两种形态 ⇒ 只用第一个命中形态（旧 `break` 语义）⇒ 对账 fail closed | 2 |
| ② 变异反证（局部复刻） | `_legacy_apply` = 旧替换循环逐字照抄；13 条参数化判据在旧实现上**逐条**对齐 `legacy_red` 期望：**8 红 / 5 绿**（红：两类碰撞最小化 ×3 + D3-4 k=3/k=8 + 左边界 + 右边界 ×2；绿：before 前缀 / D3-4 k=5 / 冒号 ×2 / `#`，即旧实现本来就对的条目） | 1 |
| ③ D3-4 真实 adapter | 前提（合成表 = 真实模板 definedName、插入点 16）+ 段①单趟 k=3/4/5/6/8 materialize 成功且 5 条声明逐条 = 模板值 +k（`per_table_shift` 核对插行数 = k）+ 真实 adapter 上 monkeypatch 回旧 apply，k=3/8 必抛 `声明 5 处传播，实际只改了 6 处` | 1+5+2 |
| ④ 缓存键 | 同进程同 base：(4,0)→(4,5)→(4,0) 三次等价，(4,5) 不命中、重复 (4,0) 命中；变异 `_GeometryBlindCache`（按形态剥掉几何段 = 旧键）⇒ (4,5) 抛 `managed_sheet_unmanaged_cells` | 1 |

**文件级变异反证**（一次性脚本把两份框架文件换回 `HEAD` 版本跑本文件，跑完按 sha256 核对恢复，脚本已删）：
**13 failed / 12 passed**。红 = ① 中 8 条 `legacy_red` + 冲突 fail closed（旧实现不检测）+ ② 汇总判据（旧实现下
`current` 也不全绿）+ ③ k=3、k=8 + ④ 缓存键（真实键判据先跑，旧键下 (4,5) 当场抛 `managed_sheet_unmanaged_cells`，
before 覆盖 140 / after 120）。绿 = 旧实现本来就对的 5 条 + 混用形态（两实现同语义）+ ③ 前提 / k=4/5/6 + ③ 两条
monkeypatch 变异（自带旧实现，不依赖文件版本）。

### 10.7 D3-4 真实 adapter 各行数结果

段①单趟（段② 0 行），新实现，真实 `build_excel_adapter` → `materialize()`：

| k | materialize | definedName 位移 | verify（本段不断言，仅记录） |
|---|---|---|---|
| 3 | ✅（旧实现 ❌ 前缀碰撞） | 5 条全 +3 | 等价 |
| 4 | ✅ | 5 条全 +4 | 等价 |
| 5 | ✅ | 5 条全 +5 | ❌ `workbook_and_styles`（verify 侧 17+5=22 碰撞，3b） |
| 6 | ✅ | 5 条全 +6 | 等价 |
| 8 | ✅（旧实现 ❌ 整段相等碰撞） | 5 条全 +8 | ❌ `workbook_and_styles`（verify 侧，3b） |

两趟 5/5（`test_cumulative_two_pass_insertion_still_verifies_correctly`）materialize 成功、verify 仍红，与基线相同（3b）。

### 10.8 回归（修复前后失败清单对比）

第 3a 段（只含本段相关对比）。命令同 §10.1。

| 命令 | 修复前（§10.1） | 修复后 | 失败清单 |
|---|---|---|---|
| A 五个定向文件 | 1 failed / 59 passed | 1 failed / 59 passed | 相同：`test_cumulative_two_pass_insertion_still_verifies_correctly`（verify 侧，3b） |
| B `-k "d3 or D3 or d4 or D4"` | 2 failed / 492 passed / 1 skipped / 2 xfailed / 8592 deselected | 2 failed / **502** passed / 1 skipped / 2 xfailed / 8607 deselected | 相同两条：上面那条 + `test_task5_d3_performance_baseline::test_real_registration_path_fails_before_reaching_d3`（基线已红，与本段无关） |

B 多出的 10 passed = 新文件 25 条里名字 / 参数 id 命中 `d3`/`d4` 的 10 条（`d34_k*` 参数化 3 + `test_d34_*` 5 +
`test_mutation_legacy_apply_fails_d34_*` 2），deselected 多 15 = 其余 15 条。**本段新增失败 = 0。**

附加定向回归（不在 A/B 内，覆盖 apply 与 `before_key` 的其它判据）：
- `test_workbook_row_change_apply.py` / `test_excel_row_insertion_wiring.py` / `test_single_pass_parse_reuse.py` /
  `test_workbook_row_change_upstream_gate.py`（含 Property 27「A1 改写入口唯一」）：**86 passed / 1 skipped**。
- `test_single_pass_verify_not_relaxed.py`（含 `before_key` 必含 `before_sha` 的 AST 判据）+
  `test_excel_row_insertion_scope_closure.py`：49 passed / 1 skipped / 1 failed。失败项
  `TestStructuralAbsence::test_published_contracts_are_carried_by_the_definition_store`（`d3.prepaid_receipts_detail`
  契约 digest 不被 definition store 承载）是**既有**的：把两份框架文件临时换回 `HEAD` 后照样红；工作树里
  `backend/data/workpaper_sync_contracts/d3.prepaid_receipts_detail.json` 有别的会话的未提交改动，本段不碰。

**第 3b 段（append，3a 原文不改）**。开工核查：`git status --porcelain` 里 `excel_workbook_row_change.py` /
`test_multi_sheet_workbook_change_merge.py` 无改动；`excel_materialize.py` / `excel_extract.py` 的 `git diff` 逐行核对只有
3a 的两处（`_apply_workbook_propagation` 同时替换 + `before_key` 补 region 几何），无别人的改动；
`test_workbook_propagation_ref_collision.py` 为 3a 新建的未跟踪文件。cwd=backend，`..\.venv\Scripts\python.exe`。

改动前基线（重跑 §10.1 命令 A / B，3a 之后的工作树）：

| 命令 | 3b 改动前 | 失败清单 |
|---|---|---|
| A 五个定向文件 | 1 failed / 59 passed（15.1s） | `test_cumulative_two_pass_insertion_still_verifies_correctly`（`workbook_and_styles` 漂移） |
| B `-k "d3 or D3 or d4 or D4"` | 2 failed / 502 passed / 1 skipped / 2 xfailed / 8607 deselected（211.6s） | 上面那条 + `test_task5_d3_performance_baseline::test_real_registration_path_fails_before_reaching_d3` |

与 3a 修复后逐条相同 ⇒ 3a 之后工作树里没有并发改动影响这两组判据。

#### 3b 修复后回归（改动前后失败清单对比）

改动 = `excel_workbook_row_change.py`（`trips` 字段 / `merge` 趟序 + 同趟冲突语义 / `_trips_of` /
`_simultaneous_rewrite` 共享原语 / `normalise_propagated_part` 按趟倒序精确逆、废 `_chain_depth`）+
`excel_materialize._apply_workbook_propagation`（改调共享原语，行为逐字不变）+ `test_workbook_propagation_ref_collision.py`
（+12 条 3b 判据）+ `test_multi_sheet_workbook_change_merge.py`（冲突判据按新语义改写 + 新增跨趟合法判据）。

**定向文件组**（A 五文件 + 3b 追加的定向文件，共 12 文件，cwd=backend，`-p no:cacheprovider`）：

| 文件组 | 3b 改动前 | 3b 改动后 | 失败清单 |
|---|---|---|---|
| A 五文件 + collision + apply/wiring/parse-reuse/upstream-gate/verify-not-relaxed/scope-closure（12 文件） | —（3a 已知 `test_cumulative...` 红 + `scope_closure::definition_store` 红） | **1 failed / 233 passed / 2 skipped** | 唯一红 = `test_excel_row_insertion_scope_closure::…test_published_contracts_are_carried_by_the_definition_store`（既有基线红，见下） |

`test_cumulative_two_pass_insertion_still_verifies_correctly`（3a 起一直红的那条 verify 侧 5/5 碰撞）
**在不改其断言的前提下随本段转绿**，同文件其余全绿。

**`-k "d1 or D1 or d2 or D2 or e1 or E1 or d3 or D3 or d4 or D4"` 全量**（cwd=backend，350s）：
`10 failed / 1023 passed / 1 skipped / 8125 deselected / 3 xfailed`。10 条红逐条归因（**全为既有基线红，非本段引入**）：
- `test_task5_d3_performance_baseline::test_real_registration_path_fails_before_reaching_d3`（1 条）——
  基线已红（§10.1 命令 B 即红），并行会话的注册/契约改动所致，与本段无关。
- `test_d2_sync_retirement.py`（9 条）—— D2 sync router 退役 lane 的在途状态（`d2_sync_router.py` /
  `useD2SyncBridge.ts` 未删、`d2-sync` 路由未摘、`pre_delete` 阶段未推进）。本段没碰任何 D2 router /
  前端桥 / `d2-sync` 字面量。**把本段三份改动 `git stash` 后单跑该文件照样 9 failed / 1 passed** ⇒ 确认与本段无关。

**本段新增失败 = 0。**

附加只读核验：
- `python scripts/check/check_sync_provider_golden_digest.py`：`✅ golden digest 零回归：73 个 digest 逐个不变`。
- 既有基线红（逐条对比确认非本段引入）：
  - `test_excel_row_insertion_scope_closure::…test_published_contracts_are_carried_by_the_definition_store`
    —— `d3.prepaid_receipts_detail` 契约 digest 不被 definition store 承载。**把本段三份改动 stash 后照样红**；
    工作树里 `d3.prepaid_receipts_detail.json` 有并行会话的未提交改动，本段不碰（§10.8 3a 已登记同一条）。
  - `test_workbook_row_change_zero_regression::test_behaviour_matches_frozen_baseline`（`-k` 范围外，本段
    定向补跑发现）—— `_rewrite_formula_refs` 偏离冻结基线 4 处。**根因在 `excel_row_shift.py`（本段未改，
    git status 干净）**，冻结基线 / 并行会话所致；**stash 本段改动后照样红** ⇒ 非本段引入，登记给相应 lane。

### 10.9 D4 真栈整册脚本

✅ 已跑（第 3b 段）。`audit-postgres` 容器 `Up 4 days (healthy)`。仓库根运行：

```
.venv\Scripts\python.exe backend/scripts/e2e/verify_d4_full_book_real_stack.py   （退出码 0）
```

输出（关键行）：

```
[①] attach=('d4.revenue_detail',) adapter_id='d4.revenue_detail'
[②] generation=164 substrate=000000164-98656478027d.xlsx size=259689
[③a] store item=46 有载荷=43 store values=1885
[③b] overlay_applied=True values=1185 表数=43 行数=433
[④] materialize OK 5.4s size=259689 row_shift=None
[⑤] extract OK 1.5s values=1185 表数=38
[⑥] verify OK 5.3s equivalent=True
[总计] materialize 5.4s + extract 1.5s + verify 5.3s = 12.2s
✅ D4 整册真栈闭环全绿（materialize + extract + verify equivalent）
```

⇒ 唯一已注册 adapter 的生产路径 materialize + extract + **verify equivalent=True**，退出码 0。共享原语
（apply 与 verify 精确逆）在真栈 D4-26 Print_Area / FOOTER_ANCHOR 的 `&apos;` definedName 位移上闭环。

### 10.10 意外 / 遗留

本段在读码和设计阶段就被要求收尾：**没有改任何框架代码，没有写测试，没有跑基线、回归或 D4 真栈**。10.1~10.9 全部未开始，
下次从 10.1（改代码前先跑基线失败清单）接着做，实施依据见 10.0 的读码结论 1~5。

**第 3a 段收尾（append，上一段原文不改）**：10.1 / 10.3 / 10.5 / 10.6 / 10.7 / 10.8 已完成；10.2 / 10.4（verify 侧趟序 +
精确逆）与 10.9（D4 真栈）留给 3b。本段改动 = `excel_materialize._apply_workbook_propagation` +
`excel_extract.verify_unmanaged_regions` 的 `before_key` + 新测试文件；`excel_workbook_row_change.py` 未碰。
一次性脚本 / 日志已全部删除，两份框架文件在变异反证后按 sha256 核对恢复。

**给 3b 的交接**：
1. verify 仍红的形状：单趟 k=5（`17+5=22`，DEBIT footer 的 `$A$22` 命中已还原的 CREDIT region 前缀）、单趟 k=8
   （`$A$25` 同时是 DEBIT footer 的 after 与 CREDIT footer 的 before，`_chain_depth` 把两条误连成链）、两趟 5/5。
   apply 侧这三种都已正确写盘（§10.7），红全在 `normalise_propagated_part`。
2. 精确逆可以直接复用本段的原语：逆表是 `after 形态 → before 形态`，用同一组左右边界、同一种「在原文上选形态、
   alternation 一次 subn」写法；形态选择要跟 apply 对称（apply 选中哪种形态写盘，产物就是那种形态的 after）。
   跨趟链必须按 `trips` 逆序、每趟一次同时逆替换，不能迭代到不动点（k=8 反例见 §10.0 第 2 条）。
3. 3b 完成后，把 `test_workbook_propagation_ref_collision.py` 里 D3-4 k=3/4/5/6/8 的判据加上 verify 等价性断言，
   并让 `test_d3_04_dual_zone_shift_and_verify.py` 的两趟 5/5 转绿；缓存键判据用的 (4,0)/(4,5) 与 verify 碰撞无关，无需改。
4. 本段新增一条 apply 侧 fail closed：同一趟同一 part 同一命中文本声明两个 after ⇒ 抛。3b 改 merge 的冲突语义
   （同趟冲突才算冲突）时与之一致。

**第 3b 段收尾（append，3a 原文不改）**：10.2 / 10.4 / 10.6（3b 增补节）/ 10.7（verify 列）/ 10.8（3b 回归）/
10.9 已完成。本段改动 = `excel_workbook_row_change.py`（`MaterializeWorkbookChangeSet.trips` 字段 + `merge`
趟序保留 + 冲突语义收窄到同趟 + `_trips_of` helper + `_simultaneous_rewrite` 共享原语 + `_apos` 提模块级 +
`normalise_propagated_part` 按趟倒序精确逆、废 `_chain_depth`、接受 ChangeSet）、`excel_materialize.py`
（`_apply_workbook_propagation` 改调 `_simultaneous_rewrite`，外部行为逐字不变 —— fail closed 两条消息、
AST 判据全保留）、`test_workbook_propagation_ref_collision.py`（+12 条 3b 判据）、
`test_multi_sheet_workbook_change_merge.py`（冲突判据按新语义改写 + 新增跨趟合法/趟序保序判据）。

- **新语义一句话**：冲突只在**同一趟内**成立；跨趟同 before 不同 after 合法（链式 / 不同 definedName 文本
  巧合）；扁平 `propagations` 仍去重排序供三个只读方，趟序单独存 `trips` 供 verify 精确逆。
- **共享原语放哪 / apply 行为**：`_simultaneous_rewrite` 在 `excel_workbook_row_change.py`，apply 与 verify
  精确逆共用；apply 改为调它后**外部行为逐字不变**（3a 的 25 条防御测试 + wiring/verification/apply 共 63 passed）。
- **防御测试新增 12 条**（single_trip round-trip 1 / multi_trip round-trip 3 / mutation_legacy_normalise 1 /
  d34 verify 等价 k3~k8 共 5 / 两趟 5-5 与 3-5 共 2）；**变异反证（旧 normalise = `_chain_depth` + 逐条 replace）
  打红 5 条**（whole-token-equal 单趟 / d34 k5 / d34 k8 / 跨趟链前缀 / 同趟整段相等 k8）。
- **D3-4 各形状 verify 结果**：单趟 k=3/4/5/6/8 全 `equivalent=True`（含 3a 修复前 verify 侧仍红的 k=5/8）；
  两趟 5/5 与 3/5 全 `equivalent=True`。`test_cumulative_two_pass_insertion_still_verifies_correctly` 在
  **不改断言**的前提下随本段转绿。
- **回归前后对比**：本段新增失败 = 0。`-k d1/d2/e1/d3/d4` 的 10 红全为既有基线（1 条 `test_task5` task-edge +
  9 条 `test_d2_sync_retirement` D2 退役 lane），stash 本段改动后照样红。
- **D4 真栈退出码 0**（`verify equivalent=True`）。
- **意外**：`test_workbook_row_change_zero_regression::test_behaviour_matches_frozen_baseline`（`-k` 范围外，
  定向补跑发现）红——根因在 `excel_row_shift._rewrite_formula_refs`（本段未改，git status 干净），stash 后照样红，
  非本段引入，登记给相应 lane。一次性探针 / 脚本无（本段未用临时脚本，机理靠现成测试驱动）。

## §11 模板缺陷修复（第 3c 段：修 D3-5 / D3-6 模板）

> 第 3c 段执行记录。用户明确批准"修引擎 + 修模板"，引擎（3a/3b）已定稿，本段修模板并收口。
> 只改：新脚本 `scripts/fix/fix_d3_template_footer_defects.py`、权威模板 `D/D3 预收账款.xlsx`（+.bak）、
> 哨兵/基线/契约、`test_d3_04_dual_zone_shift_and_verify.py` 或新测试、两个 phase5_d3_05/06 docstring、tasks.md（仅追加）。

### 11.0 开工核查

- `git status --short`：权威模板 `D/D3 预收账款.xlsx` **不在**工作树改动里（干净，可改）；phase5_d3_05/06 是未跟踪文件（可加 docstring）。
- **🔴 既有基线红（本段动手前先坐实，非本段引入）**：`test_wp_templates_readonly.py` 的
  `test_template_count_and_size_match_baseline` / `test_snapshot_matches_baseline` **已经红**：
  报「xlsx 数 351→352」+「新增 1 个 D/D4 收入底稿.xlsx」+「内容被改 4 个：D3/D5/D6/D7」。
  = 净化那一波（D3/D5/D6/D7 外链净化 + D4 改名/新增）改了模板但从未更新 `wp_templates_baseline.json` /
  `EXPECTED_XLSX_COUNT` / `EXPECTED_TOTAL_BYTES`。这批漂移属**其它 lane**，本段不接管；本段**只**把该基线里
  D3 那一条 sha/size 更新为本段修复后的新值（不动 D4/D5/D6/D7 条目、不动 EXPECTED_* 常量，以免掩盖那批漂移）。
  ⇒ 本条 readonly 守卫在本段前后都红（D4/D5/D6/D7 未处理），本段不对它转绿负责，只保证不新引入 D3 相关红。
- 模板旧 sha（净化后）：`699a9be0e7da639f3e5cd3a2d3bfdf38f7e777b330f9ec6959f5cc390fb6c2d2`，size 74402。
  另 `workpaper_sync_d_cycle_manifest_slice.json` L873 存的是**净化前**旧值 `8a27614b…`/133116（stale，见 §11.3）。

### 11.1 sheet part 定位 + 现状实读（探针 `_probe_3c_inspect.py`，已删）

workbook.xml r:id + rels 映射：D3-5 `账龄1年以上的预收账款检查表D3-5` = **sheet9.xml**，
D3-6 `关联关系及交易检查表D3-6` = **sheet10.xml**。

- **D3-6 行 17 现状**（OOXML 直读）：
  - `C17`：`<c r="C17" s="26"><f>SUM(C12:C14)</f><v>0</v></c>`（**独立公式**）
  - `D17`：`<f t="shared" ref="D17:F17" si="1">SUM(D12:D14)</f>`（**共享公式 master**，si=1 覆盖 D17:F17）
  - `E17`/`F17`：`<f t="shared" si="1"/>`（**slave**，靠列偏移派生，无公式文本）
  - openpyxl 展开读：C17/D17/E17/F17 = `SUM(C12:C14)`/`SUM(D12:D14)`/`SUM(E12:E14)`/`SUM(F12:F14)`。
    ⇒ 只需改 C17 独立公式 + D17 master 两处文本，E17/F17 自动派生 12:16。
- **D3-5 行 14 现状**：`A14 = <c r="A14" s="12"/>`（**空自闭合**，style 12）；
  `B14 = <f>SUM(B11:B13)</f>`、`F14 = <f>SUM(F11:F13)</f>`；页眉文字（A10/A15）用 sharedStrings（`t="s"`）。
  ⇒ A14 用 **inlineStr** 写「合计」（保留 s="12"），不动 sharedStrings.xml 索引。

### 11.2 修复脚本 + --check 判据

新建 `backend/scripts/fix/fix_d3_template_footer_defects.py`（正式工具，无 `_` 前缀，照抄净化脚本范式：
zip 级精准改 part → openpyxl 全 12 sheet 逐格 diff + merged 判据 → `--check`/`--apply` 两模式 → `--apply`
备份 `.prefooterfix.bak`（新后缀，不覆盖净化的 `.preclean.bak`）+ 写盘 + 打印新 sha）。改法：
- D3-6：`<c r="C17"…><f>SUM(C12:C14)</f>` → `SUM(C12:C16)`；`<f t="shared" ref="D17:F17" si="1">SUM(D12:D14)</f>`
  → `SUM(D12:D16)`（逐格精确正则，命中数各断言 ==1，否则拒写盘）。
- D3-5：`<c r="A14" s="12"/>` → `<c r="A14" s="12" t="inlineStr"><is><t>合计</t></is></c>`（命中数断言 ==1）。

`--check` 输出（判据全过）：

```
before sha256=699a9be0…  size=74402
after  sha256=33165493b95e0ae10f576e31ae72a37b5a07796db9714f389ccb95af4ba21ef1  size=74431
== 逐 sheet 变动 ==
  [账龄1年以上的预收账款检查表D3-5] 1 格:  A14: None -> '合计'
  [关联关系及交易检查表D3-6] 4 格:
    C17: '=SUM(C12:C14)' -> '=SUM(C12:C16)'
    D17: '=SUM(D12:D14)' -> '=SUM(D12:D16)'
    E17: '=SUM(E12:E14)' -> '=SUM(E12:E16)'   ← 共享 slave 自动派生
    F17: '=SUM(F12:F14)' -> '=SUM(F12:F16)'   ← 共享 slave 自动派生
other sheets untouched: 10/12
merged ranges changed sheets: (none)
```

⇒ 恰只 D3-5 A14（空→合计）+ D3-6 四格公式（12:14→12:16），其余 10 张 sheet 零 diff、两张 merged 不变。新 sha `33165493…`。

### 11.3 哨兵/基线同步（逐处说清依据；改 sha `699a9be0`→`33165493`）

新 sha `33165493b95e0ae10f576e31ae72a37b5a07796db9714f389ccb95af4ba21ef1`（size 74431）。逐处处理：

| # | 引用点 | 处理 | 依据 |
|---|---|---|---|
| 1 | `phase5_d3_prepaid_receipts.py` `TEMPLATE_SHA256` | ✅ 已改为新 sha（+注释旧值） | 冻结哨兵，`read_authoritative_template()` 门比对；不改则重生成契约时 `EntrySelectionError` |
| 2 | `data/workpaper_sync_contracts/d3.prepaid_receipts_detail.json` | ✅ `generate_phase5_d3_contract.py --apply` 重生成（不手改哈希）；`assert_contract_file_matches_source()` 通过 | 生成脚本重生成。新值：`template_sha256=33165493…` / `normalized_structure_hash=020a0be3…`（旧 `d1532efd…`）/ `template_definition_sha256=bf08720a…`（旧 `8e3177b8…`）/ canonical_digest=`54ffa5f5…` |
| 3 | `definition_store/contracts/2cfdb859….json` + `definition_store/instrumentation/15370ee8….json` + `bundles/15aadca6….json`（内容寻址） | 🔴 **停下报告，未改** | 见 §11.4 |
| 4 | `tests/_snapshots/wp_templates_baseline.json` 的 D3 条目 | ✅ 只改 D3 一条 `sha/size` → `33165493…`/74431（不动 D4/D5/D6/D7 条目、不动 `EXPECTED_*` 常量） | 该 readonly 守卫**本段前即红**（净化波 D3/D5/D6/D7 + D4 改名/新增全未同步基线；且此处 D3 存的还是**净化前** `8a27614b`/133116，比净化值还旧一代）。只同步 D3 是我这次改动的诚实足迹，不掩盖其它 lane 的漂移（它们仍被列红）。改后本守卫仍红（D4/D5/D6/D7 未处理，非本段范围） |
| 5 | `data/workpaper_sync_d_cycle_manifest_slice.json` D3 `sha256`（现存 `8a27614b`/133116 = 净化前旧值） | 🔴 **未改，判为 Task 46 lane owned** | 该 slice 是**手工 frozen slice**，`test_task46_d_cycle_migration.py` 的 `test_authoritative_templates_digests_recompute` / `test_every_entry_template_ref_is_registered_with_digest` 消费它。这两条**本段前即红且被 triage 文档标 BLOCKED（"D 循环 owner 重裁决"，并发会话进行中）**；`migration_paradigm.json` 明写 D3 entry owner = "Task 46 D 循环回填（并发会话进行中）"。改它会干扰该 lane 的 blocked 态且修不好它的红。登记给 Task 46 lane 一并处理（届时取新值 `33165493…`/74431） |
| 6 | `tests/workpaper_sync/data/workbook_row_change_zero_regression_baseline.json`（含 D3 三 digest） | 🔴 **未 --apply，登记** | 生成器 `--check` 现算：**5 处漂移，仅 D3 一处是我的**（filldown/insert_ctx/insert_no_ctx 三 digest 因 footer 几何变而变，合理）；其余 4 处（新增 `D/D4`、`D/D7` digest+formulas 206→200、xlsx_total 351→352、external_sites 2908→2902）**全非本段**，属净化/D4 lane。`--apply` 会重生成整册基线、把那 4 处别 lane 漂移一并吸收（掩盖它们），违反"不掩盖其它 lane 漂移"。且 `test_behaviour_matches_frozen_baseline` 本段前即红（根因在 `excel_row_shift`，另 lane）。故不 --apply，登记：D3 三 digest 变化合理，整册重取需等 D4/D7 等 lane 收敛后统一做 |

**.bak 备份**：`fix_d3_template_footer_defects.py --apply` 写了 `D3 预收账款.xlsx.prefooterfix.bak`（新后缀，不覆盖净化的 `.preclean.bak`）。
`.bak` 被 `.gitignore:139:*.bak` 忽略（不入库）。注：task46 `test_authoritative_templates_digests_recompute` 按
`root.iterdir()` 扫目录，`.preclean.bak`（净化 lane 遗留）已让它 `registered != on_disk` 恒红；本段 `.prefooterfix.bak`
只是再加一项到那个**已红**比对里（与净化 `.preclean.bak` 同范式、同 gitignore），非本段引入该测试的红。

### 11.4 🔴 definition_store 内容寻址链：停下报告（需 orchestrator/用户裁决）

契约重生成后 canonical_digest 由（HEAD 的）`…` 变为 `54ffa5f5…`。`test_excel_row_insertion_scope_closure::
test_published_contracts_are_carried_by_the_definition_store` 现算每份**已交付**契约的 canonical digest 必须被
`backend/definition_store/` 承载（同名 blob 或被某 bundle json 引用）。实跑：**唯一孤儿 = `d3.prepaid_receipts_detail
digest=54ffa5f5…`**（其余 9 份都 carried）。

- **本段前该测试即红**：§10.8/§10.10 已登记（并发会话把工作树契约原地改了 `+491` 行但没走发布链）。git HEAD
  的契约引用 `template_definition_sha256=8e3177b8…`，`definition_store/contracts/2cfdb859….json` 也引用同一 `8e3177b8…`
  ⇒ **HEAD 态本是 carried 的**；是工作树的未提交契约改动（另一会话）先让它脱链，本段的 footer 重生成只是再换一次 digest。
- **修法（测试自带提示）= 跑 `fix_task76_provision_projection_definitions.py --apply`**：读该脚本头，它**写真实
  PostgreSQL 的 V151/V153 表**（`if not DATABASE_URL.startswith("postgresql"): raise`）+ 经 `publish_definition_blob()`
  往 `definition_store/` 写**新的内容寻址 blob**（template→instrumentation→contract→bundle 四段），是**跨泳道共享发布链
  + 活库写入 + 新增内容寻址文件**，blast radius 大，且会踩到并发会话在途的 D 循环 provisioning 状态。
- **裁决**：按指令"内容寻址 definition_store 若不确定就停下报告，不硬改"——**未跑 `--apply`、未手改那三个内容寻址文件**
  （`2cfdb859…`/`15370ee8…`/`15aadca6…`）。需要 orchestrator/用户拍板：是否（在合适时机、与 Task 46/76 lane 协调后）
  跑 `fix_task76_provision_projection_definitions.py --apply` 重发 D3 定义链把 `54ffa5f5…` 入库承载。在此之前该测试对
  D3 保持红（本段前即红，非本段新引入）。
