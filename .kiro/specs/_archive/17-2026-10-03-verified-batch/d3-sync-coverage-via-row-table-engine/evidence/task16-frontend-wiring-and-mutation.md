# Task 16 证据：前端受管集合派生 + Property 1~12 变异总表 + 真栈

spec: `d3-sync-coverage-via-row-table-engine` · Task 16
Requirements: 6.6, 7.3, 8.1, 8.2, 8.3, 8.4, 8.5
日期: 2026-09-26

---

## §1 段 A：前端受管 sheet 集合派生（Requirements 6.6）

### §1.1 实施产出

| 产物 | 路径 | 说明 |
|---|---|---|
| 单一来源清单 | `frontend/src/components/workpaper/sync/d3ManagedSheets.ts` | 6 张受管 sheet（5 rows + 1 adjudication），每项带 code/sheetKey/kind/excelName |
| 单元判据 | `frontend/src/components/workpaper/sync/__tests__/d3ManagedSheets.spec.ts` | 6 条，**6 passed** |
| 后端一致性契约 | `backend/tests/workpaper_sync/test_d3_frontend_managed_sheet_parity.py` | 7 条，**7 passed** |
| 宿主改造 | `frontend/src/components/workpaper/GtD3PrepaidAccounts.vue` | 从 d3ManagedSheets 派生判定 |

### §1.2 消灭的反模式

| 反模式 | 改前 | 改后 |
|---|---|---|
| `isD3DetailSheet` 单张写死 | `currentSheet === 'D3-2'` 字面量 | `isD3OoWiredRowsSheet(currentSheet.value)` 从清单派生 |
| `isD3AdjudicationSyncSheet` 单张写死 | `currentSheet === 'D3-1'` 字面量 | `isD3ManagedAdjudicationSheet(currentSheet.value)` 从清单派生 |
| `syncSheetKey` 写死 | `ref('d32-managed')` 常量 | `computed(() => d3ManagedSheetOf(currentSheet.value)?.sheetKey ?? 'd32-managed')` 随 sheet 动态解析 |
| `syncCapability` 构造时字面量 | `capabilityForEntry(D3_SYNC_ENTRY_ID)` 调一次 | `computed(() => capabilityForEntry(syncEntryId.value))` 随 entry Ref 现算 |
| `flushHtml` 写死字面量 | `entryId: D3_SYNC_ENTRY_ID` / `sheetKey: 'd32-managed'` | `entryId: syncEntryId.value` / `sheetKey: syncSheetKey.value` 读 Ref |

### §1.3 非受管 sheet 处理

| sheet | 处理 | UI 说明（中文） |
|---|---|---|
| D3-3 调整分录（single_html） | 保持结构化视图、不落 legacy 假双向 | 工具条无「在线编辑」选项 |
| D3A 程序表 | 沿用 `dualMode.ooAvailable` | — |
| 附注上市/附注国企 | 沿用 `dualMode.ooAvailable` | — |
| D3-4/5/6/7（受管行表但未接 OO 宿主） | `isD3OoWiredRowsSheet=false`、禁切 OO | `el-tooltip` "本表未纳入单元格级双向回写受管范围，仅提供结构化视图（不支持在线编辑双向）" |
| D3-1 审定表（adapter 未注册） | `renderModeOptions` 第二档 disabled | `el-tag` "审定表在线编辑待接入" |

### §1.4 诚实边界

D3 六张受管 sheet 中，**只有 D3-2** 在宿主挂了 `WorkpaperSyncEditorHost`（OO 直写桥）。其余
四张行表（D3-4/5/6/7）虽是**契约受管**（store-projection 出/回两方向），但仍走结构化 `D3Tab*`
视图。D3-1 审定表走第二套桥（逐格 mask）且 adapter 未注册。清单里 `D3_OO_WIRED_ROWS_CODES`
只含 `['D3-2']`，不假称其余可切 OO。

### §1.5 两套桥不合并

D3-2（rows kind）走 `useWorkpaperSyncBridge` + store-projection 桥；D3-1（adjudication kind）
走独立的逐格 mask 桥。`d3ManagedSheets.ts` 每项带 `kind` 字段，分派到哪套桥按 kind 区分。
`d3AdjudicationGatingBoundary.spec.ts`（**4 passed**）源码级钉住「不得并进 isD3DetailSheet」。

---

## §2 段 B：Property 1~12 变异打红总表（Requirements 8.1, 8.2）

| Property | 名称 | 判据文件 | 总用例 | 变异用例 | 打红? | 说明 |
|---|---|---|---|---|---|---|
| P1 | 零回归 golden digest | `test_d3_expansion.py` + `check_sync_provider_golden_digest.py` | 7+ | — | ✅ 基线恒绿 | 87 digest 逐个不变（Task 12 证据） |
| P2 | store_item_id 逐字实测 | `test_d3_property2_store_item_id_exact_match.py` | 15 | 7 | ✅ 变异 7/7 红 | `D3-6-rows` 推演必红（设计 F2） |
| P3 | D3-4 双区 | `test_d3_property3_4_dual_zone_baseline.py` | 6 | 3 | ✅ 变异 3/3 红 | 只声明单区必红 |
| P4 | D3-7 双区 | `test_d3_property3_4_dual_zone_baseline.py`（同文件） | (同上) | (同上) | ✅ 变异含 D3-7 | 只声明单区必红 |
| P5 | formula_mask 引擎现算 | `test_d3_06_related_party_spec.py` | 4+ | 1 | ✅ | `formula_columns` 少一列必红（Task 7 证据） |
| P6 | D3-1 sections/row_mode 实测 | `test_d3_01_adjudication_spec.py` | 22 | 2 | ✅ 变异 2/2 红 | D1-1 三区推演必红 |
| P7 | D3-1 editable 格不被 mask | `test_d3_01_coverage_and_property7.py` | 7 | 1 | ✅ | 把 B17 塞进 mask 必红 |
| P8 | 四态覆盖标记 | `d3CellOverrideRender.spec.ts` | 8 | 2 | ✅ fc+composable | 纯函数反证 + 跑同步器 |
| P9 | 下游 computed 重算 | `useD3CrossSheet.spec.ts` | 8 | 1+ | ✅ | 回写后 postPeriodSettlementSync 重算 |
| P10 | 整册 materialize verify | `test_d3_07_dual_zone_shift_and_verify.py` 等 | 14+ | — | ✅ | verify equivalent（Task 10/12 证据） |
| P11 | D3-3 核不改代码 | `test_d3_03_single_html_adjudication.py` | 19 | 2 | ✅ 变异 2/2 红 | 塞进受管契约必红 |
| P12 | 前端受管清单一致性 | `test_d3_frontend_managed_sheet_parity.py` + `d3ManagedSheets.spec.ts` | 13 | 3 | ✅ 变异 3/3 红 | 假 sheet/漏 sheet/游离字面量 |

**总计**：Property 1~12 全部验通过，变异检验全部打红（未能打红 = 0，无需重写）。

### §2.1 变异用例详细清单

| 变异 | 测试方法 | 结果 |
|---|---|---|
| `D3-rp-rows` → `D3-6-rows` 按编号推演 | `test_wrong_by_number_pattern_is_detected_as_mismatch[D3-6]` | ✅ 红 |
| D3-4 只声明一个受管区 | `test_mutation_d3_4_declaring_only_debit_zone_loses_credit_key_visibility` | ✅ 红 |
| D3-7 只声明一个受管区 | `test_mutation_d3_7_declaring_only_current_zone_loses_post_key_visibility` | ✅ 红 |
| D3-1 区块数改成 D1-1 的 3 区 | `test_mutation_d1_style_three_sections_is_detected` + `test_mutation_run_real_geometry_asserts_would_fail` | ✅ 红 |
| 四态用 `stored ≠ derived` 错法 | `d3CellOverrideRender.spec.ts` fc 反证 | ✅ 红（S2/S4 正确区分） |
| 前端硬编码假 sheet 名 | `test_mutation_inject_fake_sheet_name_makes_parity_red` | ✅ 红 |
| 前端漏声明受管 sheet | `test_mutation_frontend_drops_a_managed_sheet_makes_parity_red` | ✅ 红 |
| 受管契约塞进 D3-3 | `TestMutationRegisteringD303WouldGoRed` (2 条) | ✅ 红 |
| B17 手工格塞进 mask | `test_p7_mutation_masking_a_manual_amount_cell_would_be_caught` | ✅ 红 |

---

## §3 段 C：真栈（Requirements 7.3, 8.3, 8.4, 8.5）

### §3.1 adapter_registered 现状

```
adapter_registered = False（confirmed 2026-09-26）
裁决 F5：真库 register_from_manifest() 只注册 {d2,d4,g7,h1}。
D3 因 store 全库 0 行、无 current published representation 而未注册。
test_task5_d3_performance_baseline.py::test_real_registration_path_fails_before_reaching_d3
  ⇒ 真抛出 RegistryError / SyncDomainError，证实 adapter 未注册。
```

### §3.2 `[ ]*` 真栈整段标记

**代码已改但未实测，卡 adapter 未注册（裁决 F5）。**

真栈脚本骨架（不跑，不以合成冒充）：

```
1. page.goto(`/workpaper/${wpId}?sheet=D3-2`)
2. 切「在线编辑」（el-segmented 第二选项）
3. 等 OO canvas 加载（waitForSelector('.cell-editor') 或 WorkpaperSyncEditorHost mount）
4. 逐值断言：OO canvas 内 D3-2 数据行值 == 结构化视图值
5. 改一格（#ce-cell-name → keyboard.type → Enter）—— 🔴 不能用 asc_* API 写格
6. forcesave（syncEditorHostRef.forceSave()）—— 🔴 不能用 page.on('response') 判 callback
7. 回读结构化视图（切回 html mode → 重载 allResponses → 断言等值）
8. --workers=1（避免 OO 并发冲突）
```

**三陷阱沿用上游结论**：
- 不能用 `page.on('response')` 判 callback（OO 容器直接 POST 后端，须读 `application_bound_at`）
- 不能用 `asc_*` API 写格（未经协同通道 ⇒ `cs_error=4` no_changes）
- 模式切换条选择器须实测确认（D3 的须现场读，照抄 D4 会找不到元素）

---

## §4 测试结果汇总

### §4.1 前端

| 测试文件 | 用例数 | 结果 |
|---|---|---|
| `d3ManagedSheets.spec.ts` | 6 | ✅ 6 passed |
| `d3AdjudicationGatingBoundary.spec.ts` | 4 | ✅ 4 passed |
| `d3CellOverrideRender.spec.ts` | 8 | ✅ 8 passed |
| `useD3CrossSheet.spec.ts` | 8 | ✅ 8 passed |
| **小计** | **26** | **26 passed** |

`vue-tsc --noEmit`：OOM（已知环境限制，仓库体量超出当前 session heap 上限，非本任务引入）。

### §4.2 后端

| 测试文件 | 用例数 | 结果 |
|---|---|---|
| `test_d3_frontend_managed_sheet_parity.py` | 7 | ✅ 7 passed |
| `test_d3_property2_store_item_id_exact_match.py` | 15 | ✅ 15 passed |
| `test_d3_property3_4_dual_zone_baseline.py` | 6 | ✅ 6 passed |
| `test_d3_01_adjudication_spec.py` | 22 | ✅ 22 passed |
| `test_d3_01_coverage_and_property7.py` | 7 | ✅ 7 passed |
| `test_d3_03_single_html_adjudication.py` | 19 | ✅ 19 passed |
| **小计** | **76** | **76 passed** |

### §4.3 已知基线红（非本任务引入）

- `test_task5…real_registration`：adapter 未注册（裁决 F5，Task 5 起即红）
- `test_fail_closed_behaviours_match[d3]`：xfailed
- `test_current_d3_managed_region_count_after_stage2_is_five`：别 lane 在途 d31-managed（已排除）
- `test_sibling_table_ref_row_shift[D1-8]`：并发 lane 未提交 phase5_d1_11
- definition_store 内容寻址重发布：同 Task 10 §11.4 不跑

---

## §5 改动文件清单

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `frontend/src/components/workpaper/sync/d3ManagedSheets.ts` | **新建** | 受管 sheet 单一来源清单 |
| `frontend/src/components/workpaper/sync/__tests__/d3ManagedSheets.spec.ts` | **新建** | 单元判据 6 条 |
| `frontend/src/components/workpaper/GtD3PrepaidAccounts.vue` | **改造** | 5 处字面量→派生 |
| `backend/tests/workpaper_sync/test_d3_frontend_managed_sheet_parity.py` | **新建** | Property 12 后端一致性契约 7 条 |

---

## §6 停下报告裁决点

1. **adapter_registered=False 未解除**（裁决 F5 同 Task 5/7/10/12/14）：D3 真栈端到端实测
   全线阻塞。需先造 seed 数据走通发布链（approved bundle + published representation +
   entry_state），否则三端点（store-projection / pending-mutations / materialize）均 500。
   **建议**：随 umbrella Task 76/77 的 finalize gate 统一解锁，不在循环 spec 各自重做。

2. **在途冲突（Task 14 已报）**：另一会话把 D3-1（固定行审定表）接进**行表契约**，而本 spec
   按 `AdjudicationSheetSpec` 独立口径处理。两条路线对「D3-1 是不是行表」判定相反，
   该 lane 当前磁盘契约非法（`parse_contract` 抛错）。建议裁决：D3-1 固定行逐格 mask
   走 AdjudicationSheetSpec 独立口径（同 D4-1），协调该 lane 修复。

3. **后端下发受管短码集合（改进项）**：理想形态是后端把受管 sheet 的短码集合下发进 manifest
   生成物（新增字段 `managedSheetCodes`），前端从生成物读取、彻底去掉手写清单。需
   `generate_workpaper_sync_manifest.py` 增加「Excel 名→短码」映射入口，属跨前后端建设。
