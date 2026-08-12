# Implementation Plan: 底稿导入导出全生命周期收口

## Overview

24 个任务分 6 波，收口「空白模板 → 填完导回 → 取数后二次编辑再导回 → 归档前后导出」四场景全链。

**本 spec 的性质是「接线 + 止损 + 真源统一」，不是重造导入导出。** 立项需求文档的量化台账经 2026-08-10 独立复算**推翻 7 处**（连库直查 / 运行期枚举 `app.routes` / 扫工厂调用 / 读 ACNR catalog），其中两处改变了设计方向：

- **场景④不是「零端点」** —— `bulk_tab/` 已有 **14 模块**、`wp_bulk_router.py` 已有 **11 端点**（模板/数据/异步/下载/回传/回滚/进度）+ `ZipAssembler`（sha256 + manifest.json）+ `conflict_resolver` + `snapshot_guard` + `workflow_gate`。缺的只是 UI 入口、归档时点门控、语义标注。
- **`checklist_responses` 不是「131 份 / 103 万行有内容」** —— 是 131 份有行、**全库仅 695 行非空**（103.37 万行双 NULL 空骨架，单份 C24 独占 103.32 万行）；非空行里 **JSON 数组 300 / JSON 对象 126 / 纯文本 269**，最长单行 181,056 字符。所以要接的是**每个 `item_id` 的 JSON 载荷**，不是「行」。

逐条对照见 design.md §核心事实修正。

**Wave 1（Task 1~3）必须先对当前状态打红** —— 三个守卫按「类 A 独立口径应全绿 / 类 B 被测实现应全红」分开写，红的消息带「尚未实现（Wave N Task M）」。预期打红：自证四档全缺、清单漏 `template_fallback`、registry 10/81 覆盖、孤儿 11 个。

**三条硬前置**：
- Task 4（自证真源扩档）→ Task 7（载荷接通），否则 L2 没有地方挂「已就绪但录入未写入 xlsx」这一档（R1.8）。
- Task 13（registry 真源换血）→ Task 19（模板库解引用迁移），因为迁移会改 `file_path`，而 registry 守卫要用「迁移前 verdict 分布」作对照基线（R6.7），顺序颠倒会让基线自身漂移。
- Task 7（载荷读取层）→ Task 10（场景③列级标注），列元数据由载荷层产出（R3.3）。

**Wave 5（Task 19~20）是唯一破坏性层**，须 `--confirm-destructive` 且放在全部守卫就位之后。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "name": "判据先行（守卫先打红）", "tasks": ["1", "2", "3"] },
    { "wave": 2, "name": "产物自证止损层", "tasks": ["4", "5", "6"] },
    { "wave": 3, "name": "导出数据源接通", "tasks": ["7", "8", "9"] },
    { "wave": 4, "name": "四场景统一入口 + registry 真源换血", "tasks": ["10", "11", "12", "13", "14", "15", "16", "17", "18"] },
    { "wave": 5, "name": "断开模板库引用（破坏性）", "tasks": ["19", "20"] },
    { "wave": 6, "name": "守卫收口与验收", "tasks": ["21", "22", "23", "24"] },
    { "wave": 7, "name": "单一实现收敛（用户裁决）", "tasks": ["25"] }
  ],
  "notes": "Wave 1 必须先对当前状态打红。Task 4 硬前置于 Task 7（自证需先扩出 entry_not_in_xlsx 档）。Task 13 硬前置于 Task 19（迁移会让 verdict 基线漂移）。Task 7 硬前置于 Task 10（列级标注依赖载荷层）。Wave 2 与 Wave 4 的 registry 部分无文件重叠可并行。Wave 5 破坏性，须全部守卫就位后执行。"
}
```

## Tasks

- [x] 1. 建产物自证守卫（先打红）
  - 新建 `backend/tests/services/test_wp_export_self_evidence.py`
  - 断言纯函数 `needs_self_evidence(...)` 四态齐备：`verdict` / `html_data_absent` / `entry_not_in_xlsx` / `None`
  - 断言 `stamp_self_evidence` 落盘范式：第 1 行 banner、第 2 行空、第 3 行起数据（数据首格行号恒为 3）
  - 文案真源扫描：全部调用方源码不得出现硬写中文自证字面量；先 `stripComments()` + 配「剥注释确实生效」自检（docstring 里的示例文案会冒充硬写）
  - 断言 `entry_not_in_xlsx` 与 `html_data_absent` 两档文案**逐字不同**
  - 类 A 自检（应全绿）：`VERDICT_LABELS` 四键齐备 / `WP_FILE_VERDICTS` 取值域非空 / 正常态替身必返 None
  - 预期：类 B 全红（`self_evidence.py` 尚不存在）
  - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.7, 1.8_

- [x] 2. 建批量清单与端点清册守卫（先打红）
  - 新建 `backend/tests/services/test_wp_download_manifest.py`：断言 `_未导出清单.txt` 列出 `verdict == 'template_fallback'`、按 verdict 分组、处置建议条数 ≥ 出现档位数
  - 新建 `backend/tests/test_ie_route_inventory.py`：**运行期** `app.routes` 分组，口径照抄 design §Data Models 的 `group_ie_routes`（**必须剔除 `{wp_id}`/`{wp_code}` 路径参数段** —— 立项的「87 组」含此误计）
  - 固化台账数字（design §核心事实修正 7 条）：`wp_render_strategies/` 模块 99 个 / 零 `@router.` 装饰器 63 个 / 工厂 `api_prefix` 62 个且全唯一 / 三态端点 308 条（106+102+100）/ 剔参数后三态齐全前缀 81 组
  - 反向自检：把任一数字改回立项旧数（102 模块 / 314 端点 / 36 组）必须打红
  - 预期：清单守卫红（当前仅列 `empty`/`missing`）；端点清册守卫绿（只读事实）
  - _Requirements: 1.4, 1.5, 7.1_

- [x] 3. 建 registry 三向与孤儿基线守卫（先打红）
  - 扩展 `components/workpaper/shared/__tests__/cycleImportExportRegistry.spec.ts`：catalog ↔ registry ↔ 真实 `app.routes` 快照**三向**锁死
  - 新建 `components/workpaper/__tests__/ieOrphanBaseline.spec.ts`：孤儿判定按 **import 路径**（非符号名），且**排除 `__tests__/` 与 `*.spec.ts`** —— `useG13`/`useG14` 当前唯一 import 方就是 spec 文件，算进消费方则基线永远清不掉
  - 基线钉死 11 个孤儿（含立项漏记的 `useF1ImportExport`）：`useF1/useG13/useG14/useH5/useH7/useK12/useK5/useL4/useK0/useL0/useK1Writeoff`
  - 反向自检：只加一个 spec 文件的 import 不得让基线缩短；仅改符号名不改路径判定结果不得变化
  - 全量扫描做 `(path, mtime_ns, size)` memoization（键含 mtime，否则变异检验假绿）
  - 预期：registry 覆盖断言红（10/81）、孤儿基线 11 条红
  - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.5, 5.6, 5.7_

- [x] 4. 建自证共享件（阻塞 Task 7）
  - 新建 `backend/app/services/wp_export/self_evidence.py`：`SelfEvidenceKind` 三档 + `_KIND_LABELS` + `build_self_evidence_banner()` + `stamp_self_evidence()` + 纯函数 `needs_self_evidence()`
  - 文案只取 `VERDICT_LABELS` 与 `_KIND_LABELS` 两个真源，调用方一律不得硬写中文（R1.3）
  - 落盘复用 `_build_failure_fallback_workbook` 既定范式（第 1 行加粗标红 / 第 2 行空 / 第 3 行起数据）
  - `verdict == 'file'` 且 `html_data` 非空时 `needs_self_evidence` 返 None（R1.6 禁给正常导出加噪声）
  - 验证：Task 1 守卫全绿
  - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.7, 1.8_

- [x] 5. 单份下载与 export-xlsx 接自证
  - `wp_download_service.download_single` / `download_pack`：`verdict != 'file'` 时产物内落自证 banner
  - `wp_xlsx_export_service._sync_export_workpaper_xlsx`：`html_data` 为空或缺 sheet 键时落 `html_data_absent` banner + 可操作提示
  - `verdict == 'file'` 但 `html_data` 空而 `checklist_responses` 有非空行 ⇒ 落 `entry_not_in_xlsx` banner（与前者文案逐字不同）
  - 反向自检：正常态（`file` + `html_data` 非空）产物不含任何自证文案
  - _Requirements: 1.1, 1.2, 1.6, 1.7, 1.8_

- [x] 6. 批量清单覆盖 template_fallback
  - `_render_skipped_manifest`：`template_fallback` 进清单（改造前 1670 份 `template_fallback` 全部遗漏，只列了 `empty`/`missing`）
  - 按 verdict 分组 + 每档给处置建议；文案取 `VERDICT_LABELS` 单一真源
  - `download_pack` 写入侧：`template_fallback` 的底稿既进 ZIP（带自证 banner）又进清单，两者不互斥
  - 验证：Task 2 清单守卫全绿
  - _Requirements: 1.4, 1.5_

- [x] 7. 建录入载荷读取层（阻塞 Task 10）
  - 新建 `backend/app/services/wp_export/entry_payload_reader.py`：`EntryPayload` dataclass + `read_entry_payloads()`
  - **双列都读**：`conclusion` 与 `remark` 各自可能承载 JSON（实测两者都在用），返回 `source_field` 标注
  - 形态判定：strip 后首字符 `[` → `json_array`；`{` → `json_object`；解析失败降级 `plain_text` 并**记 WARNING**（实测 269 行本就是纯文本，不能当异常，但要留痕以发现真损坏）
  - 全空行剔除（R2.4）：实测 1,033,715 / 1,034,515 行双 NULL
  - 上限保护（R2.7）：**条数与总字符数双阈值** —— 实测单行可达 181,056 字符、单份 103.32 万行，不设限必 OOM
  - 新建 `backend/tests/services/test_entry_payload_reader.py`：三形态 + 双列 + 空行剔除 + 双阈值截断；**替身须按实测量级构造**（用 1000 行替身测不出 103 万行的问题）
  - _Requirements: 2.1, 2.4, 2.7_

- [x] 8. 清单 sheet 两态渲染并追加进产物
  - 导出路径追加清单 sheet（**不改写模板既有 sheet 单元格** —— 模板单元格回填需 per-cycle 地址映射，`structure.json` 全库 0 个、`item_id` 形态 211 种，本 spec 不做）
  - 三态渲染：`json_array` 每 `item_id` 一区块（列名取载荷自身键集，不硬写）/ `json_object` 键值两列纵向 / `plain_text` 三列
  - **R2.2 列语义偏离须登记**：AC 字面写「值 / 结论 / 备注」四列，实测 `conclusion` 与 `remark` 是同一载荷的两个候选存放列（非两个业务字段）⇒ 改为标注 `source_field`，并在 sheet 内写明该列语义（R2.8 的「数据来源」由此列承担）
  - sheet 名不与模板既有 sheet 冲突（冲突则后缀递增 + 断言最终名唯一）；无非空行则不产生清单 sheet
  - 截断时在 sheet 内标注被截断条数；标注导出时点
  - _Requirements: 2.2, 2.3, 2.5, 2.6, 2.7, 2.8_

- [x] 9. 数据源接通的真实执行守卫
  - 新建 `backend/tests/services/test_export_entry_sheet.py`
  - **真实执行判据**：造一份只有 `checklist_responses`、无 `html_data` 的底稿，产物必须含其内容 —— 禁止只断言「代码里出现了表名」（memory：additive 注入即死代码是假绿三源之一）
  - 断言导出前后模板既有 sheet 全部单元格值**逐格相等**；反向自检：故意写一格必须打红
  - 真实库口径自检：103.37 万双 NULL 行必须全部被剔除，清单行数不受其影响；C24 那份必须触发截断且不 OOM
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 2.7_

- [x] 10. 建四场景语义真源（依赖 Task 7）
  - 新建 `backend/app/services/bulk_tab/scenario_registry.py`：`ScenarioSpec` dataclass（`key`/`label`/产物说明/适用时点/`endpoint`/`mode`/`direction`/`archived_allowed`）
  - 四场景 key：`blank_template` / `fill_back` / `refresh_edit` / `archive_export`
  - 每个 `endpoint` 复用既有 `wp_bulk_router` 路径，**不新造 per-cycle 实现**
  - 场景②③的 `endpoint` 必须相等（同一 `import-data` 通路）
  - 场景③列级标注：来源取 ACNR catalog 的 `formula_ref` 有无（有 = 四表取数不可直改 / 无 = 可编辑），是已有元数据复用不新增声明
  - 新建 `backend/tests/services/test_scenario_registry.py`：endpoint ⊆ 真实 `app.routes` + 四场景语义齐备 + `archived_allowed` 三态 + 端点总数与基线相比只许持平或按登记增加
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 11. 模板↔数据错用校验
  - 导入侧读 ZIP `manifest.json` 的 `mode` 字段（`manifest_builder` 实测已写入 `template|data`），与目标场景比对，不符则返可读错误且**零写入**
  - 这是零新增存储的做法 —— manifest 已带该字段，此前只是没人校验
  - 新建 `backend/tests/services/test_bulk_mode_mismatch.py`：错用拒绝 + 零写入；反向自检「撤掉校验必须让错位数据落库」
  - _Requirements: 3.5_

- [x] 12. 归档时点门控与场景④接线
  - 接既有 `bulk_tab/workflow_gate.py`：导入路径加归档态判据（拒绝 + 可读原因），导出路径不拦
  - 场景④归档前与归档后两时点各可执行；产物含 `manifest.json` + sha256（`ZipAssembler` 既有能力）
  - 断言归档态下导入端点返可读拒绝、导出端点仍 200
  - _Requirements: 3.6, 3.8_

- [x] 13. registry 真源换血为 ACNR catalog（阻塞 Task 19）
  - 新建生成脚本 + `cycleImportExportRegistry.generated.ts`：从 ACNR catalog 的 `import_export` 段派生（`apiPrefix`/`sheets[]`/`itemId`/`storageField`）
  - `cycleImportExportRegistry.ts` 改为门面：`CYCLE_IMPORT_EXPORT = { ...generated, ...MANUAL_OVERRIDES }`
  - `MANUAL_OVERRIDES` 只放 catalog 表达不了的（如 G0 的 `G0-3S` 传输键 —— 它是 `_SHEET_NAME_MAP` 的**键**不是 wp_code，改字面量会让三个端点 400）
  - **禁止从 `*_import_export.py` 源码提取**（ACNR 铁律 R18.6/R-ROUTE）：99 个模块里 63 个零装饰器，源码扫描会漏 2/3
  - characterization：既有 10 key（`f1/f2/f2-val/f2-spe/f2-st/f3/f4/f5/g0/h0`）的 `apiPrefix` 与 `sheets[]` 逐字节与基线相同
  - 验证：Task 3 registry 三向守卫全绿
  - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6_

- [x] 14. 补 catalog 缺口（后端工厂独有的 32 个前缀）
  - catalog 与后端工厂**两侧都不是全集**：catalog 独有 30 前缀（`d1`~`d7`/`f0`~`f3`/`g0`/`g4-*`/`g6-*`/`g7-*`/`g8`/`h0`/`h10`/`k0`），工厂独有 32 前缀（`h5`/`h7`/`h9`/`i1`~`i6`/`l1`~`l8`/`m1`~`m10`/`n1`~`n5`）
  - 本 spec 只补工厂独有那 32 个的 `import_export` 段（`api_prefix`/`item_id`/`storage_field`/`import_order`/`depends_on_sheets`），**`formula_ref` 等 cell 级元数据留待各循环 spec**
  - 幂等脚本带 `--dry-run` / `--check` / `--apply`；`--check` 归零是 CI 判据；round-trip 自检（`json.dumps` 不能逐字复现原文即 exit 2）
  - 改前查 mtime（`g7-*` 前缀与 `g7-column-alignment-…` spec 有交集，只读不改；若需改先协调）
  - _Requirements: 4.1, 4.4_

- [x] 15. registry 未登记打红与显式登记表
  - catalog 或工厂新增 prefix 而 registry 未登记 ⇒ 守卫红；反向自检：注入一个假 prefix 必须打红
  - registry 登记了后端不存在的 `apiPrefix` 或 sheet 键 ⇒ 守卫红
  - 新建 `EXEMPT_IE_PREFIXES` 显式登记表：每条含 `prefix` / `reason` / `evidence` / `stale_check`；条目数有上限且只许下调
  - **孤儿豁免项的 stale 检测**：处置为「豁免」的 composable 一旦出现真消费方（非 `__tests__`/`*.spec.ts`）即打红，提醒移出豁免表；反向自检 —— 给某豁免项加一个真实渲染宿主必须打红
  - 反向自检：把 `G0-3S` 改成 `G0-4` 必须打红
  - _Requirements: 4.3, 4.4, 4.5, 4.7, 5.4_

- [x] 16. 11 个孤儿处置 —— 删除组
  - `useF1ImportExport`（`f1` 已在 registry 且三态齐全 ⇒ 该 composable 是重复实现）
  - `useG13ImportExport` / `useG14ImportExport`（`g13`/`g14` 三态齐全，且 `G13TabDetail.vue`/`G14TabDetail.vue` **已挂 `CycleImportExportDropdown`** ⇒ 能力已覆盖，composable 是并存的第二条路）
  - 删除前证明：该 prefix 的端点仍被 dropdown 覆盖（不是端点一起消失）
  - **本组属「待用户裁决」项** —— 若用户倾向保留，则改为接线并说明与 dropdown 的分工
  - _Requirements: 5.1, 5.3_

- [x] 17. 9 个孤儿处置 —— 接线组（实证驳回原方案，改为「挂 dropdown + 删重叠 composable」）
  - **交付**：8 个 Tab 挂 `CycleImportExportDropdown`（h7×3 / k12×2 / k5×2 / l4×1）+ 4 个父宿主绑 `@imported="selfLoad()"`；删 3 个能力重叠的 composable（`useH7` / `useK12` / `useK5`）；孤儿基线 9 → 6
  - **新增守卫**：`ieWiringIntegrity.spec.ts`（11 例，前端接线闭环）+ `backend/tests/test_ie_prefix_reachability.py`（11 例，路由可达性 + sheet 参数一致性）
  - **变异检验 16 个全 RED**（M7/M16 二次复验；判定用测试名匹配，因 vitest 会把数组折叠成 `[Array(n)]` 使消息内容匹配失效）

  ### 原方案三处被实证驳回
  1. **原写「补 catalog + 挂 dropdown」6 个循环，实际只有 4 个能挂**。真实枚举 FastAPI 路由表（2113 条）后：registry 的 72 个前缀里 **70 个三态可达，h5 / n4 一条都不可达** —— 它们的端点是第三形态 `/api/{prefix}/*`（wp_id 在 body/Form），由 `app/routers/h5_oil_gas_assets.py` 之类提供，而 `_h5_import_export.py` 工厂虽声明了路径形态却从未 `include_router`。本轮曾误给 H5 两个 Tab 挂上 dropdown，`get_diagnostics` 与 vitest **双全绿**，已回退。
  2. **L4-3 撤销**：l4 后端三端点 `l4_export_data(wp_id, db, current_user)` **不接受 sheet 参数**，FastAPI 静默丢弃 ⇒ 在 L4-3 页导出会拿到与 L4-2 相同内容，不报错但结果错。实测 69 个多 sheet 前缀里**只有 l4** 如此（66 个接受，另 2 个不可达）。故 l4 只在主表 L4-2 留一个入口。
  3. **`useK1Writeoff` 不能靠 dropdown 接线**：它是**纯客户端 Excel**（`useExcelIO()`），三态后端端点一个都不调，自带 `REVERSAL_COLUMNS` 列定义 + 双区段 `SECTION_MAP` + 前端解析，目标 sheet 是 K1-9/K1-12（registry 的 k1 无这两个）⇒ dropdown 替代不了，删即丢能力。

  ### 核心认知：挂 dropdown ≠ 消除 composable 孤儿
  dropdown 自带 HTTP、只读 registry，**完全不 import 这些 composable**。故「接线」有两种落法，混淆会留下两套并存代码：
  - 能力重叠 ⇒ 挂 dropdown **并删** composable（h7/k12/k5，三态齐全且额外端点 0 个）
  - 能力不可替代 ⇒ 必须真接线该 composable（k1-writeoff）

  ### 顺带修的 3 个存量真缺陷
  - `F2TabOverallAnalysis.vue` 挂 `sheet="F2-18"`，而后端 `_SUPPORTED_SHEETS`（21 键）**不含 F2-18**（多区段分析表无适配器）⇒ 死按钮，且未绑 `@imported`。已删除并留因由。
  - registry 的 f2 漏 3 键（`F2-1` / `F2-note-listed` / `F2-note-soe`）—— 立项值 18 键恰好等于 `_F2_SHEET_CONFIGS`，漏了审定表与两个附注键，而附注页早已挂着下拉 ⇒ 批量场景枚举不到。已补。
  - registry 守卫的后端抽键**跳过附注模块**：`_f2_disclosure_import_export.py` 无自己的路由声明（沿用主模块三路由），`prefixes.size === 0` 就 `continue` ⇒ 它定义的附注键永远抽不到。已改为跟随一层相对 import。

  ### R4.6 零回归判据改写
  原「既有 10 个 key 逐字节不变」会**把修复打红、把缺陷锁死**（f2 立项值本身有缺口）—— 正是 memory 记的假绿第三源「守卫把错值当基线锁死」。改为「**不得丢键** + 新增须写进 `INTENTIONAL_ADDITIONS` 并注明后端依据」。

  ### j1 的裁决：保持豁免，不登记 registry
  勘查已核实后端那一半（三端点真注册、12 个合法键 = `SHEET_TYPES`、前端附注页已挂下拉且因自带 prefix 而功能正常），但 registry 有更硬约束「每个 apiPrefix 都能在 catalog 找到条目」，而 catalog 的 J1 条目全无 `import_export.api_prefix`。补 catalog 必须填 `item_id`，猜错 = 数据错位 ⇒ 沿用既定裁决「不猜 item_id」，维持 GAP_REGISTRY 豁免。前置条件已缩小为「人工核出 J1 各 sheet 的 item_id」。

  ### 剩余 6 个孤儿的阻塞原因（逐条写在 `ORPHAN_BASELINE` 注释里）
  `useH5`（端点非路径形态 + composable 自身 URL 也是坏的）· `useK1Writeoff`（纯客户端 Excel，缺 K1-9 宿主）· `useL4`（后端 sheet 无关，`L4_EXPORT_SEGMENTS` 分段能力两侧都不成立，待裁决）· `useK0`/`useL0`（函证族，sheet ↔ 区域映射待核，l0 已在 GAP_REGISTRY 豁免）· `useJ2`（孤儿链，需整链裁决）
  - 「尚未实现」那条断言**有意保持红色**：转绿要么真处置，要么往 `ORPHAN_EXEMPTIONS` 写明理由（上限 3 + stale 检测）。直接改成 `toBeLessThanOrEqual(6)` 会让「剩 6 个」变成新常态，不做。
  - _Requirements: 5.1, 5.2, 5.3, 5.6, 5.7_

- [x] 18. UI 四场景入口
  - **交付**：新增 `GET /api/projects/{project_id}/bulk-tab/scenarios`（下发四场景 + 当前状态下 `disabled`/`disabledReason`）；`WpBulkDialog.vue` 的三个硬写中文按钮改为 `v-for` 渲染的四场景卡片（2×2 网格，含「产物内容」「适用时点」两段说明 + 方向标签）；round_trip 场景加「本次操作」切腿单选
  - **守卫** `backend/tests/test_bulk_scenario_ui_single_source.py`（26 例，含 3 条真实 HTTP 实测）；**变异检验 14 个全 RED**（M17–M29，M18/M29 各二次复验）
  - **浏览器实测通过**：四卡片渲染 · 0 console error · 切腿联动（导回腿出现上传框+冲突策略+DryRun）· 归档态两导入类置灰两导出类可用 · tooltip 显示原因 · force click 被代码拦住

  ### 守卫为什么放后端
  判据要拿 `SCENARIOS` 的**真实文案值**比对前端源码。写在前端就得把中文句子再抄一份进测试 —— 那份自己就是第二份真源，后端改文案后守卫 stale 且**不打红**（假绿第三源）。放后端可直接 `import` 真源取值。

  ### 判据不是「有没有调接口」
  只查「前端有没有 fetch /scenarios」是 grep 式判据（加个调用但仍用硬写文案渲染照样绿）。实际查两件事：①真源每条文案的**特征片段**都不得出现在前端源码 ②三个字段**在场景卡片块内**真被渲染。

  ### 变异检验修正一处守卫缺陷（M18 GREEN → RED）
  初版「三字段已绑定」用全文正则 `\.timingNote\b`。变异删掉卡片里的 `{{ sc.timingNote }}` 后**仍绿** —— 因为 options 步骤的场景回显还在，全文判据足以命中，而用户在选择场景那一屏已经少看到一段说明。改为按**卡片块**判（`v-for` 锚点 + 标签配对截取，禁固定字符窗口），并加两条自检：锚点必须命中、截出的块不得退化成全文（占比 < 60%）。

  ### 浏览器实测抓到一个静态守卫查不出的真缺陷
  真源文案里写了 Markdown（`**不含**` / `` `manifest.json` `` / `**仍可导出**`），而消费方是纯文本插值 `{{ sc.artifactNote }}` ⇒ **用户看到字面量星号与反引号**。文案是合法字符串、类型正确、端点也通，四层守卫全绿。
  - 修法选「真源去掉标记」而非「前端加 Markdown 渲染」：单一真源的**值**必须是可直接呈现的文本 —— 否则每个消费方都要实现一套解析器（这份文案后续还要进 Word 导出说明页与 Excel 自证边车），且前端渲染需 `v-html`，凭空引入 XSS 面。
  - 已加 `test_copy_is_plain_text` + 反向自检把它变成可回归判据，并在 `ScenarioSpec` docstring 写明约束。

  ### 归档门控由后端下发，前端零判断
  真源是 `workflow_gate._BLOCKED_STATUSES`（含 `archived`/`review_passed`），在 `bulk_import_service` 的 `dry_run()`/`run()` 两侧 `classify()` 跳过写入。前端若自己判一次归档就是抄第二份规则，分叉后会出现「按钮亮着但导入被静默跳过」或「按钮灰着其实能导」。故端点直接下发 `disabled`+`disabledReason`，守卫断言前端源码**不得出现** `ProjectStatus` / `'archived'` 字面量。
  - 每次打开弹窗都重拉场景（不缓存）：`disabled` 取决于项目当前状态，缓存会让用户在别处归档后仍看到可点的导入入口。
  - 归档态实测用 Playwright 拦截响应注入 payload，**不写库**（postgres MCP 只读 + 不做破坏性操作）；后端归档行为另由 3 条真实 HTTP 实测 + M26~M28 三个变异覆盖。
  - `aria-disabled="true"` 让 Playwright 直接拒绝点击（`element is not enabled`）—— 无障碍语义正确，辅助技术亦可识别；再用 force click 验证代码层 `selectScenario()` 也拦得住。

  ### 一处 UI 文案实测后调整
  round_trip 场景的执行按钮原本拼场景 label，得到「开始导出已取数数据 → 编辑 → 导回」—— 把三步流程塞进一个按钮。改为只描述本次这一腿（「开始导出数据包」），完整语义由上方场景回显承担。
  - _Requirements: 3.7, 3.8_

- [x] 19. 模板库解引用迁移（破坏性）—— **已对真实库执行并复核**

  ### 执行结果
  `956/956 迁移成功 · 0 冲突 · 0 失败 · 125.4 MB 复制`，verdict 分布迁移前后守恒（`file:1063 / missing:181`）。
  独立复核（不读台账、直接查库+磁盘）：迁移文件磁盘存在 **956/956** · 抽样 12 份 sha256 与源一致 **12/12** · 模板库今日被改动 **0** · **仍指模板库 0 条** · **仍跨项目共享路径 0 条**（原 303 个共享源全部解除）。

  ### 迁移前实证（比立项台账更严重）
  956 份中 **955 份的 `file_path` 与其他项目共享** —— 304 个源路径被 2~4 个项目复用（159 个被 4 个项目共享）。后果两层：①写入直接污染 `wp_templates/`（运行时权威，`wp_template_init_service` 据它生成底稿）②A 项目改完 B 项目看到 A 的内容。

  ### 四个路径决策（均经实证，非随手定）
  1. **目标基准 = `backend/`** 而非仓库根：`wp_file_resolver._relative_bases()` 依次试 `Path.cwd()`/`BACKEND_ROOT`/`REPO_ROOT`，其注释写明「生产 cwd 就是 BACKEND_ROOT」⇒ 写这里生产第一个候选就命中，不依赖回退。（既成事实是分裂的：63 份在仓库根、38 份在 backend/，读取端靠三基准兜住。）
  2. **沿用既有命名** `workpapers/{audit_cycle}/{wp_code}.xlsx`（不加 wp_id 后缀）：实测 `(project_id, wp_code)` 在 956 份里 **956 组 × 1 完全唯一**，无需后缀去重；平台已有 101 份是此形态，换一套会让同目录两种命名并存。`audit_cycle` 15 个值零空值、全部与 wp_code 首字母一致。
  3. **存相对路径**而非绝对：绝对路径会把开发机盘符写进库，换机即失效。
  4. **回滚只反写 `file_path`，不删新文件** —— 删文件的回滚本身就是数据丢失风险。

  ### 有意留白（写进台账 `notes` / `out_of_scope`）
  空 `file_path` 的 **1564 份**（无源可复制，属 Task 5 自证层）· **181 份 `file_path` 指向不存在文件**（其中 30 份指向 `/tmp`、6 份硬编码 `D:/GT_plan/...`，属既存缺陷）· **C24 那份 1,033,230 行 checklist**（占全库 99.9%，疑似脏数据，本迁移只改 `file_path` 不动 checklist）。

  ### 安全流程实测
  `--check`（只读）→ `--dry-run`（全量台账 + 校验目标唯一性/共享拆分/路径越界）→ **门控验证**（无 `--confirm-destructive` 拒绝、exit 2、库未动 956 仍在）→ 用户确认 → `--apply --confirm-destructive`。
  - **幂等实测**：二次 `--check` 得 `to_migrate = 0`
  - **回滚闭环实测**：取 3 条 → 回滚 3/3（回到 wp_templates）→ 新文件保留 3/3 → 重新 apply 复原 3/3（走哈希相同的幂等路径，未重复复制）
  - _Requirements: 6.1, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_
  - 新建 `backend/scripts/fix/fix_wp_template_deref.py`：`--check` / `--dry-run` / `--apply --confirm-destructive` / `--rollback <ledger.json>`
  - 作业面 **956 份**（`file_path` 指向 `wp_templates/`，其中 90 份确有 `checklist_responses` 行）—— 立项写的 120 份是低估；**空 `file_path` 的 1564 份不在本迁移范围**（无可复制源，属 Task 5 自证层作业面），该边界须写进登记表
  - 复制目标 `storage/projects/{project_id}/workpapers/{wp_code}_{wp_id前8}.xlsx` ⇒ 每项目独立副本（实测 6 条 `A1x` 路径各被 **4 个项目**共享 ⇒ 迁移后产出 24 个互不相同的 `new_path`）
  - 台账 `{wp_id, old_path, new_path, sha256_before, sha256_after, ts}` 落 JSON；`--rollback` 只反写 `file_path`，**不删新文件**（避免回滚本身造成数据丢失）
  - 幂等（已不指向 `wp_templates/` 即跳过，二次执行零变更）+ 逐条隔离失败（单条异常记 `failed[]` 继续）+ 目标路径已存在且哈希不同则记冲突跳过
  - 迁移前后各跑一次 `resolve_wp_file` 全量 verdict 分布并 diff 落台账（`template_fallback` 应减少 / `file` 应增加 / 总数守恒）
  - 脚本内 `Path.write_text(encoding='utf-8')`（PS `>` 会把中文腌成乱码）；判成败查数据不看 exit code
  - _Requirements: 6.1, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

- [x] 20. wp_templates 只读守卫
  - `backend/tests/test_wp_templates_readonly.py`（7 例）：351 个 xlsx 的 `(相对路径, size, sha256)` 快照逐条相等 + 文件数/总字节双钉死 + `_index.json` 存在性 + 三条连库行为断言（0 条指模板库 / 0 条跨项目共享 / 迁移成果 ≥956）。基线落 `backend/tests/_snapshots/wp_templates_baseline.json`（351 条，53 KB）
  - `backend/tests/scripts/test_wp_template_deref.py`（26 例）：路径形态 / `..` 穿越与非法字符 / 多基准源解析 / 幂等跳过 / blocked 归类 / 目标撞名 / **共享源产出 4 个独立目标** / out_of_scope 登记 / 门控四档 / 台账回滚字段完整性
  - **变异检验 8 个全有效**（M30~M37）：真改模板库一字节 RED · 库里塞一条指模板库记录 RED · 去掉 cycle 段 RED · 破幂等 RED · 丢 project_id 致共享目标 RED · 门控放行 RED · `_safe_name` 放水 RED · **M37 反证**（把快照判据弱化成只比 size 后，单字节改动漏检 ⇒ 证实 sha256 不可省）

  ### 两处踩坑修正
  1. **连库守卫初版用两次 `asyncio.run`** ⇒ 第二个报 `Event loop is closed`，表现为「无关断言失败」。已合并为**一次 `asyncio.run` 取全部快照**的 module fixture（memory 铁律）。
  2. 🔴 **变异脚本第一版同样踩这个坑，且后果更重**：DB 变异「改→复原」两次 `asyncio.run` 共享连接池，复原时报 `NoneType has no attribute send` ⇒ **真把 1 条记录改坏没复原**。已从 apply 台账取回正确 `new_path` 修复（复查 0 条指模板库、磁盘文件存在），并把变异脚本改为**每次 DB 操作用独立 engine + 复原后立即查库验证**，验证失败就 assert 报错。
  - 教训：破坏性变异的复原路径必须**自证复原成功**，不能只写在 `finally` 里就当已复原。
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.8_

- [x] 21. 变异检验
  - **交付** `backend/scripts/diagnose/mutate_ie_lifecycle_guards.py`：`--list`（覆盖率 + 缺口）/ `--run`（可按 `--guard` / `--mid` 筛）/ `--include-destructive` / `--restore`
  - **实测 40/40 全 RED**（零 GREEN、零 WRONG-TEST、零 ANCHOR-MISS），报告落 `_mutation_reports/`
  - 覆盖 **16 个守卫文件 / 288 条判据**：9 个文件有变异（占判据 52.8%），7 个缺口**逐条登记理由**（`UNCOVERED_RATIONALE`）

  ### 变异清单（40 个，按守卫分组）
  `wiring_integrity` 5（M1~M4、M9）· `registry_lock` 3（M5、M6、M8）· `prefix_reachability` 5（M10、M11、M13、M14、M16）· `scenario_ui` 11（M17~M26、M28）· `templates_readonly` 2（M30、M31，破坏性）· `deref_script` 5（M32~M36）· `self_evidence` 3（M38、M39、M42）· `download_manifest` 3（M40、M43、M44）· `route_inventory` 3（M41、M45、M46）

  ### 缺口不是「忘了」，是登记过的裁决
  7 个零变异守卫各写明理由，共同模式是**变异与判据不成一对一**：纯解析函数（`entry_payload` 21 条）、结构断言（`scenario_registry` 28 条）改一处会让多条同时红，读断言表比变异更有效；`archive_gating` 的门控真源已由 `scenario_ui` 的 M26/M28 等价覆盖；`bulk_dialog` 的文案判据已由后端 M17~M25 覆盖。
  - `orphan_baseline` 的理由特殊：它有 1 条**有意保持红色**的占位断言，基线不干净会让该文件全部变异结论不可信 ⇒ 待遗留 6 个孤儿处置完再补。
  - `--list` 把「已登记缺口」与「未登记缺口」分开打印，未登记即 exit 1；另有 `stale_rationale` / `unknown_rationale` 两条反向自检（理由表里出现已有变异的守卫、或改名残留的键，都打红）。

  ### 🔴 修掉本脚本自己的一处判定缺陷
  首轮全量跑出 `37 RED + 3 WRONG-TEST`，而那 3 个（M5/M6/M8）**单独跑时明明是 RED**。
  真因：它们的 `expect` 填的是**断言消息**里的中文（如「丢了既有 sheet 键」），而判定按**测试名**（`fullName`）匹配 —— 名字里没有这些词，永远命中不了。
  - 这比漏判更危险：混在 40 个里只显示 3 个 WRONG-TEST，很容易被当成「守卫有问题」而去改守卫，**改错方向的代价远大于漏判**。
  - 已加 `_self_check_expect_fields()`：逐条校验 `expect` 能在对应守卫文件的测试名里找到，否则 `--list` 直接打红并指出「疑似把断言消息当成了测试名」。
  - 该自检本身也做了变异验证：故意把 M5 的 expect 改回消息片段 ⇒ exit 1 且报出精确原因。

  ### 其它设计要点
  - **判定一律不看退出码**：`vitest` 会把数组折叠成 `[Array(n)]`，消息内容匹配不可靠（本 spec 开发中真实踩过，M7 因此被误判）
  - **CRLF 归一**：`_read` 把文件按 LF 读进内存、落盘时还原原始换行；否则含 `\n` 的跨行锚点在 CRLF 仓库里必 ANCHOR-MISS
  - **基线扣除**：跑变异前先取该守卫的基线失败集，变异后的红扣掉基线项；若扣完为空则判 WRONG-TEST（红全来自基线，变异本身未触发）
  - **破坏性变异默认跳过**（M30 改模板库字节 / M31 改库记录），须显式 `--include-destructive`；两者的还原都**自证成功**（sha256 / 查库计数），不符即 `SystemExit` 大声报错
  - **DB 变异用独立 engine 并 dispose**，绝不复用 `app.core.database.engine` 的共享连接池 —— Task 20 开发时正因复用它导致「改了库但复原失败」
  - 实测零残留：`.mutbak` 0 个、`.mut_vitest_*.json` 0 个、生产代码里 `MUTATION` 标记 0 处
  - _Requirements: 7.2, 7.3_

- [x] 22. 守卫五类覆盖与 CI
  - **交付两个元守卫**：`test_ie_lifecycle_guard_coverage.py`（10 例，五类覆盖）+ `test_ie_lifecycle_ci_wiring.py`（12 例，CI 接线）
  - **CI 新增 2 个 job**：`wp-import-export-lifecycle`（后端 12 守卫 + 元守卫 + 2 个幂等脚本 `--check` + 变异清单自检）· `wp-import-export-lifecycle-frontend`（4 个前端 spec）
  - **变异 51/51 全 RED**（新增 M50~M57 共 8 个），覆盖率 13/18 守卫 / 310 条判据（68.4%）

  ### 元守卫立刻抓出一个真问题
  首次运行即打红：**「数据源接通」整类零变异** —— Task 21 把 `entry_payload` 与 `export_entry_sheet` 两个守卫**双双**登记进 `UNCOVERED_RATIONALE`，而它们正好是该类的全部守卫 ⇒ 这类不变量从未被证明有效。
  - 处置：补 M47/M48/M49 三个变异（JSON 解析失败不降级而丢内容 / 个体闸失效 / 录入 sheet 不追加），全部 RED，并把两条理由从登记表移除。
  - 教训写进代码注释：**缺口登记是给个别守卫开的口子，不能覆盖某一类的全部守卫**。已加 `test_uncovered_rationale_does_not_hide_whole_class` 把这条钉死。

  ### 五类划分与辅助守卫
  产物自证（self_evidence / download_manifest）· 数据源接通（entry_payload / export_entry_sheet）· registry 三向锁死（registry_lock / prefix_reachability / route_inventory）· 孤儿基线（orphan_baseline / wiring_integrity）· 模板库只读（templates_readonly / deref_script）。
  - 另有 7 个**辅助守卫**显式登记为不属五类并写明理由（四场景 UI 属「入口语义」、bulk 内部一致性由 registry 类间接覆盖、组件渲染管线属 UI 层、两个元守卫属治理层 —— 算进某类会自指）。
  - 反向断言三条：每个守卫必须归类或登记为辅助 · 辅助与五类互斥 · 同一守卫不得跨类重复计（否则「每类都有守卫」虚高）。

  ### CI 接线守的是三种静默失效
  往 4300+ 行的 workflow 加 job，本地全绿而线上失效的三条路径：
  1. **yaml 语法错** ⇒ 整个 workflow 停摆（不只是新 job）
  2. **job 名重复** ⇒ 后者静默覆盖前者，被覆盖的守卫从此不跑，CI 仍显示绿
  3. **引用路径写错** ⇒ pytest 报 not found，若该 step 被 `|| true` 消音则彻底静默
  - 故 job 名重复必须**按原文缩进层级数**，不能只看 `yaml.safe_load` 结果（重复键早被丢掉，看不出来）。
  - 另断言：16 个守卫全部挂载（漏一个即 CI 里全体缺席）· 幂等脚本只许 `--check`（`--apply` 会让流水线改版本库产物）· 变异脚本只许 `--list`（`--run` 改源文件，中断后残留 `.mutbak` 会污染后续 job）· 严格 step 不得 `|| true`。
  - `ieOrphanBaseline.spec.ts` 单列为 `continue-on-error`：它有 1 条**有意留红**的占位断言，严格挂载会让 job 长期红 —— 红久了没人看，比不挂更糟。已加断言强制它保持报告模式。

  ### 修掉一处误报（判据放宽后立即补变异）
  `test_no_guard_is_wholesale_skipped` 初版纯查子串 `allow_module_level=True`，把元守卫**自己 docstring 里解释这种手法的说明文字**当成违规。改为要求它出现在真实 `pytest.skip(` 调用行且非注释、非反引号包裹的说明。
  - 放宽判据后立刻验证仍能抓真违规：真给守卫加 `pytestmark = pytest.mark.skip` 与模块级 `pytest.skip` ⇒ 双 RED。**修误报时最容易顺手把判据改成空转**，故必须补这一步。

  ### M54 锚点失效的连带修正
  把元守卫 CI step 从单行 `run:` 改成多行 `run: |` 后，M54 的锚点（按单行匹配）失效判 ANCHOR-MISS。已改锚点并在注释里记下因由 —— 变异锚点与被守文件是耦合的，改 CI 结构要同步检查变异是否还命中。
  - _Requirements: 7.1, 7.4_
  - _Requirements: 7.1, 7.8_

- [x] 23. 真实库四场景往返验收
  - **交付** `backend/scripts/diagnose/verify_ie_lifecycle_live.py`（`--limit` / `--out`）+ 元守卫 6 条约束脚本自身行为
  - **真实库实测 12/12 全通过**：3 份真实底稿 × 4 场景，报告落 `_live_verify_reports/`

  ### 验收对象与结果（真实数据，非 fixture）
  | 底稿 | 库非空行 | 读到载荷 | 形态分布 | 产物逐条找回 |
  |---|---|---|---|---|
  | D1 | 46 | 46 | array 24 / object 1 / text 21 | 46/46 |
  | L1 | 33 | 33 | — | 全部 |
  | J2 | 25 | 25 | — | 全部 |
  - 模板原有 **21 个 sheet 一个不少**、第 1 行未被吃掉、追加 `_录入内容` 后 22 个
  - 场景④ 双向验：真实 file_path 判 `file` 且**不产自证**（内容完好无需自证）；伪造路径判 `missing` 且**必产中文自证**

  ### 与守卫的分工（为什么这条不能省）
  288 条守卫验的是**结构与契约**（函数返回什么、清单分几组），用的是构造数据、不碰真实库。它们全绿也不能说明「用户真导出来的那个文件里有东西」。本脚本验的是**真实产物**：逐条核对产物条目数 / sha256 / 落库行数。

  ### 三条硬约束都做了变异验证
  - **M60 无合法对象 ⇒ 报「无法验收」+ exit 2**：把挑选条件收紧到不可能，实测输出「无法验收」并明确写「不用 fixture 冒充」。用 fixture 造底稿再导出，验的是 fixture 而非平台真实状态 —— 那种「通过」比不验收更糟，因为给了错误信心。
  - **M62 探针必须下钻叶子**：改回容器 `str()` 立刻重现假红，证实修正必要。
  - **M63 零回归的库行数核对**：去掉后仍绿 ⇒ 证明读取路径本就无写副作用（该条是额外保险而非空转，这个结论本身有价值）。
  - 零回归一律「当前态 → 施加改动 → 对照」，**禁 HEAD-swap**；已加断言扫脚本源码，`git stash|checkout|reset` 出现在代码行即打红。

  ### 实测抓到一个探针缺陷（不是产物缺陷）
  首轮 11/12，D1 有 1 条载荷判「找不回」，探针是 `[{'rowId': 'dynamic-e081`。查库发现该载荷是**合法 JSON**（`{"bankRows":[{...}]}`，双引号）且已正确解析为 `json_object` —— 问题在我取 `next(iter(obj.values()))` 得到嵌套 list，`str()` 出来是 Python **repr**（单引号），与产物里的渲染文本对不上。
  - 改为递归下钻到第一个非容器标量（且长度 ≥4，避免 `True`/数字偶然命中）。
  - 这类假红最费时间：会让人以为导出丢了内容而去改导出逻辑。

  ### 又一次「判据只查字符串存在」的误报
  `test_live_verify_forbids_head_swap` 初版纯查 `git stash` 子串，把验收脚本 docstring 里**解释这条禁令的文字**当成违反禁令（与 Task 22 的 skip 检测同源）。改为只在「非注释、非反引号包裹」的代码行里查，并立即补变异（真写一行 `subprocess.run(["git","stash"])` ⇒ RED）确认放宽后仍有效。

  ### 已知数据现状（登记，不清理）
  `checklist_responses` 全表 **1,034,516 行**，两列全空 **1,033,820 行**，单份 **C24 占 1,033,230 行（99.9%）**。空骨架不影响产物正确性（读取侧已跳过空行，`test_blank_rows_are_skipped` 覆盖），清理属**数据治理**半径，本 spec 不做。
  - CI 里该 step 为 `continue-on-error`：CI 跑在空库上会正确地报「无法验收」exit 2，那是**期望行为**；挂载价值在于验证脚本本身可执行、import 不炸。
  - _Requirements: 7.4, 7.5, 7.7_

- [x] 24. 实测与数据复原 —— **抓到本 spec 最严重的一个缺陷**

  ### 🔴 批量 Tab 导出的 ZIP 里一份底稿都没有（既有缺陷，已修）
  真实 HTTP 调 `/bulk-tab/export-data` 拿到的 ZIP 只有报表/附注/试算表，`manifest.files = 0`、`skipped = 0`。三个真实项目实测：**1025 份 → 0、1017 份 → 0、340 份 → 0** 份底稿进 ZIP，且**无任何提示**。

  **根因链**（逐层实证，每层都排除了猜测）：
  1. `build_manifest` 本身正常 —— 直调得 `files=7 / skipped=74`
  2. 直调 `export()`（不传 `visible_filter`）得 `exported=9 skipped=0`，全部成功
  3. 差异只在路由多传了 `visible_filter=make_bulk_visible_filter(...)`
  4. 该闭包把 `sheet_code` 传给 `try_gate_wp` 的 `requested_sheet_key`
  5. 触发 `SheetBindingCatalog` 的 sheet 成员校验，拒绝原因 `DenialReason.sheet_unmapped`
  6. 该 catalog 候选集来自 **`ProcedureRowTask.sheet_key`**，实测**只覆盖 19 / 2802 个 wp_index（0.7%）**
  - ⇒ 99.3% 底稿判不可见；而「不可见项不泄露存在性」是有意设计 ⇒ 连 `skipped` 都不进 ⇒ 静默空壳。

  **修法**：`make_bulk_visible_filter` 改为按**整稿**（`wp_id`）判定，不传 `requested_sheet_key`。批量导出的粒度本就是整份文件（一个 `wp_id` → 一个 xlsx），传 sheet 维度属语义错位。sheet 级隔离仍由页面级入口负责，本改动不放宽那条路径（已加断言守住 `gate_wp` / `try_gate_wp` 的该参数不许被顺手删掉）。
  - **修后实测**：同项目 D 循环 ZIP 底稿条目 **0 → 7**、`manifest.files` **0 → 7**（各带 sha256）、`skipped` **0 → 74**（如实登记）。
  - 缺陷来源确认为既有 commit `6ac477b1`（wp-visibility fail-closed 隔离），非本轮引入；`entry_integration.py` 本会话此前未改过。

  ### 守卫 8 例 + 变异 3 个
  `backend/tests/services/test_bulk_visible_filter_granularity.py`：判据是**行为**（用 spy 替换 `try_gate_wp`，真调闭包看它实际传了什么），而非 grep 源码 —— 换成三元表达式或变量中转都逃不掉。
  - M65 传回 `requested_sheet_key` ⇒ RED · M66 去掉 wp_id 非法校验 ⇒ RED · M67 删掉「0.7% 覆盖率」说明 ⇒ RED
  - M67 不是形式主义：该缺陷回退后**没有任何信号**（产物变空壳而非报错），只能靠注释拦住「顺手把 sheet_key 补上」。

  ### 产物核对（真实 HTTP，非 fixture）
  四场景真源端点 200 · 文案**零 Markdown 标记**（Task 18 修复在真实响应里生效）· `manifest.json` 的 **`mode` 正确区分** `template`/`data`（R3.5 mode 错用防线的依据）· ZIP 结构完整（报表/附注/试算表/底稿目录 + manifest + README）。

  ### 实测前抓基线、测后逐项复原核实
  基线含：2 份底稿的 `file_path`/`status`/`parsed_data` md5 与 `jsonb_typeof`/`file_version`、94 行 checklist 的逐行 md5 与整体指纹、项目状态、全局行数、磁盘文件 sha256。
  - **复原核实 9/9 一致**（指纹 `bee828cf…` 前后相同）⇒ 证明实测全程只读。「以为只读」不等于「证明只读」，故必须重算指纹。

  ### 如实登记：浏览器 UI 层本轮未实测
  Playwright MCP 与 codegraph MCP 在本轮会话中不可用（工具列表中缺失）。
  - UI 层四场景入口的渲染已在 **Task 18 用 Playwright 实测过**并留截图：四卡片渲染 · 0 console error · round_trip 切腿联动（导回腿出现上传框+冲突策略+DryRun）· 归档态两导入类置灰两导出类可用 · tooltip 显示原因 · force click 被代码拦住 · Markdown 字面量消失。
  - 本轮的产物核对改用**真实 HTTP + ZIP 内部结构解析**，比浏览器更精确（浏览器只能验「点了有下载」，验不了字节与 ZIP 内部结构）。
  - 不用 fixture 冒充未做的部分。
  - _Requirements: 7.6_

- [-] 25. 删除 19 个从未注册的工厂模块（用户裁决「只留一套」）—— **阻塞：待前置立项完成，本任务有意驻留、非被中断**

  - 🔴 **阻塞说明（2026-08-12，用户裁决方案 B「先补齐再删」）** —— 下面一整块可独立读懂，编排器请勿把本任务当「被中断的任务」重新发起
    - **裁决**：用户在「方案 A 直接删」与「方案 B 先补齐再删」之间选 **方案 B**。原「同一前缀只留一套实现」的收敛方向**不变**，但**执行前置未满足**，故本 spec 内不动手删除。
    - **阻塞根因 —— tasks.md 与 design.md 的前提在 sheet 粒度上不成立**：原前提是「专属 router 已覆盖工厂能力」。实证结果是 19 个待删工厂模块里**只有 `h9` / `l7` / `l8` 三个**的 sheet 面被专属 router 完全覆盖；**其余 16 个的 `X-3 调整分录` sheet 只存在于待删的工厂模块里**。这 16 个前缀的专属 router 走自己的 service，sheet 面是 `X-2`/`X-4`/`X-5` 那类业务表（外币折算、股利测算等），**根本没有调整分录表** ⇒ 现在删等于丢掉 16 张 sheet 的导入导出能力（违反 R5.3）。
    - **16 个受影响 sheet（逐条留痕，前置立项可直接取用，不必重新勘查）**：`L2-3` · `L6-3` · `M1-3` · `M2-3` · `M3-3` · `M4-3` · `M5-3` · `M6-3` · `M7-3` · `M8-3` · `M9-3` · `M10-3` · `N1-3` · `N2-3` · `N3-3` · `N5-3`
    - **解除阻塞的前置条件**：把这 16 个 `X-3` 调整分录接到各自专属 router，或在 ACNR catalog 里把这些 sheet 置 `enabled=true` 并接 bulk adapter；**能力等价经实证确认后**方可删工厂模块。该前置已裁决**单独立项**，不在本 spec 半径内。
    - **删除本身不影响 bulk —— 推翻本轮一处判断**：编排器派发前判断「删模块 ⇒ `IE_ADAPTER_REGISTRY` 解析失败 ⇒ 批量四场景重新断掉」，**该判断不成立**。bulk 真实作业面来自 `list_sheets(import_export_only=True)`，过滤条件是 `import_export.enabled`（`acnr/catalog.py`）；这 19 个前缀在 catalog 里 sheet 数 = 0、`api_prefix` 全为 null ⇒ 对应的 19 个 `IE_ADAPTER_REGISTRY` 键是**不可达死条目**，删模块不会让批量少任何一个 sheet，`test_catalog_prefixes_have_bulk_adapters` 删后仍绿。
    - **删除后应下调的基线（已实测，前置满足后直接照用）**：`_BASE_IE_MODULES` 99 → 80 · `_BASE_FACTORY_PREFIXES` 62 → 43 · `_TRULY_DEAD_FACTORY_PREFIXES` → 空集 · `IE_ADAPTER_REGISTRY` 97 → 78 · `test_kfgh_cycle_adapters.py` 的 `EXPECTED_PREFIXES["CEIJL"]` 移除 19 项。**运行期 107 组 / 100 三态齐全 / 308 条端点这三个数不变**（这 19 个前缀本就零端点）。
    - **`_PREFIX_TO_MODULE` 处置方式已定**：删 19 个键，**不改指专属 router** —— 因为 `l2` / `m1` 的 6 个端点无 `sheet` 参数，改指后 `sheet_code` 会被 FastAPI 静默忽略（与 Task 17 里 L4-3 被撤销的缺陷同源）。
    - **7 个「同样未注册但绝不可删」的模块（防下一轮误伤）**：按模块路径判注册得 99 模块 / 70 已注册 / 26 未注册；`未注册 − 19` = `_h5` · `_h7` · `_l1` · `_l3` · `_l4` · `_l5` · `_n4`。这 7 个虽同样未被 `include_router`，但其前缀被 catalog 声明、adapter 经它们直调闭包 ⇒ **是活代码**。此条复证了下方 L1 那条铁律（判模块是否注册按**模块路径**、不按导入别名）。
    - **一处探针缺陷留痕**：形态 B 路径 `/api/h9-lease-liabilities/{wp_id}/export-data` 的 `{wp_id}` 夹在前缀段与后缀之间，用 `endswith("/{prefix}/{suffix}")` 判定永不命中 ⇒ 初版探针报了 **57 个假阻塞**；改 `/{seg}/…/{suffix}` 正则后归零。⇒ **判两种 URL 形态时不得假定同构**。
    - **一处先前判据撤回**：曾把「18 个专属 import 端点自行 `db.commit()`」列为违反「service 只 flush 不 commit」，核实后**撤回** —— `_cycle_import_export_common.upsert_json_payload` **同样** `await db.commit()`，两侧一致，不构成差异。

  - **用户 2026-08-10 明确要求**：同一前缀只留一套实现，避免出错
  - 作业面 = `_TRULY_DEAD_FACTORY_PREFIXES` 19 个模块：`_h9` / `_l2` / `_l6` / `_l7` / `_l8` / `_m1`~`_m10`（10 个）/ `_n1` / `_n2` / `_n3` / `_n5`
  - 判据：这 19 个模块的 `create_cycle_import_export_router` 产出的 router **从未被 `include_router`**，其 `api_prefix` 在运行期三态端点零命中 ⇒ 死代码
  - **收敛方向是删工厂模块、保留专属 router**（不是反过来）：专属 router 除三态端点外还带业务能力 —— `h9_lease_liabilities.py` 有 `generate-amortization`（实际利率法摊销表）· `l2_interest_payable.py` 有 `accrual-check`（L1/L3 vs L2 计提核对）· `m10_other_equity_instruments.py` 有 `validate-formulas` + `classification-summary`（CAS 37 负债权益区分）。为统一导入导出而搬迁这些能力属扩大半径
  - **删前逐个证明**：①该前缀在运行期有活端点（专属 router 提供）②`_PREFIX_TO_MODULE` 若指向被删模块须同步改指专属 router ③`IE_ADAPTER_REGISTRY` 对应键仍可解析（`bulk_tab` 批量通路不能因此断）
  - **L1 不在删除清单**：`l1` 已有完整三态端点（`/api/workpapers/{wp_id}/l1/*`，由 `l1_short_term_loans.py` 提供且已注册）。本轮曾误判「`l1` 是唯一真缺口」，成因是该专属 router 的导入别名恰好叫 `l1_import_export` 与工厂模块同名 ⇒ 按变量名匹配把两者混为一体。**判「模块是否注册」必须按模块路径而非导入别名**
  - 删后 `_TRULY_DEAD_FACTORY_PREFIXES` 基线降为 0，且 `test_dead_prefixes_are_covered_by_dedicated_routers` 须改为「不得再出现死前缀」（只许下调）
  - 变异自检：删除后故意恢复任一模块并注册，守卫须打红（防重新引入第二套）
  - _Requirements: 4.4, 4.7, 5.3_

## Notes

### 立项台账 7 处修正（本轮实证，判据可复算）

| # | 维度 | 立项 | 实证 | 判据 |
|---|---|---|---|---|
| 1 | `checklist_responses` 有内容 | 131 份 / 1,034,515 行 | 131 份有行，**非空仅 695 行**；双 NULL 1,033,715 行；单份 C24 占 1,033,230 行 | `mcp_postgres` 只读直查 |
| 2 | 录入形态 | 行含 `item_id`/值/结论/备注 | JSON 数组 300 / JSON 对象 126 / 纯文本 269；`wp_ref` 全库 0 条非空；单行最长 181,056 字符 | 同上 |
| 3 | 后端模块数 | 102 个 / 87 wp_code | **99 个**，其中 **63 个零 `@router.` 装饰器**（走工厂）；工厂 `api_prefix` **62 个**全唯一 | 扫 `wp_render_strategies/` 源码 |
| 4 | 三态端点 | 各 36 组 / 314 个 | `app.routes` 共 2288 条，I/E 相关 **308** 条（106+102+100）；按前缀 87 组、**剔路径参数后 81 组三态齐全** | 运行期枚举 |
| 5 | 孤儿数 | 10 个 | **11 个**（多出 `useF1ImportExport` —— F1 已在 registry 却仍是孤儿，暴露「registry 登记 ≠ composable 被消费」新缺陷模式）；`useG13`/`useG14` 唯一 import 方是 spec 文件 | 按 import 路径反查 |
| 6 | 场景④ | 11 个 archive 模块中零端点 | archive 确无底稿正文导出，但 **`bulk_tab` 14 模块 + `wp_bulk_router` 11 端点**完整覆盖模板/数据/回传/回滚/进度 | 目录实扫 + 装饰器枚举 |
| 7 | `file_path` 指模板库 | 1670 fallback / 120 份 | 全库 2802 份：空 **1564**、指 `wp_templates/` **956**（90 份有 checklist 行）；6 条 `A1x` 路径各被 4 项目共享 | 只读直查 |

### 与并发 spec 的边界

| spec | 交集 | 处置 |
|---|---|---|
| `k-cycle-…-closure`（5/25 在跑） | `useK5`/`useK12`/`useK1Writeoff` 三孤儿 | 处置前查 mtime；只碰 composable 与宿主，不碰 `k_cycle_specs.py` |
| `l-cycle-…`（3/26） | `useL4`/`useL0` 两孤儿 | 同上 |
| `h-cycle-…`（已归档） | `useH5`/`useH7` 两孤儿 | 无活动会话，可直接处置 |
| `g7-column-alignment-…`（4/24） | ACNR catalog 的 `g7-*` 三前缀 | 只读不改；需改先协调 |
| `e-cycle-…` / `procedure-trimming-…` | 无 | 不碰 |

### 五条已知不做

1. **模板单元格回填** —— 需 per-cycle 地址映射，`structure.json` 全库 0 个、`item_id` 形态 211 种（立项已裁决，沿用「附加 sheet」）
2. **空 `file_path` 的 1564 份补文件** —— 无可复制源，属自证层作业面，不进 Task 19 迁移
3. **`wp_templates/` 参考副本与权威副本差异对齐** —— memory 已记 G4/G5/G6 两处不一致，属另一半径
4. **catalog 补齐 32 前缀的 cell 级元数据** —— 本 spec 只补 `import_export` 段，`formula_ref` 留各循环 spec
5. **`checklist_responses` 103 万行空骨架清理** —— 数据治理议题（单份 C24 占 99.9%），破坏性且与本 spec 目标无关，只在验收脚本登记其存在

### 待用户裁决（不阻塞 Wave 1~3）

1. **孤儿 `useF1`/`useG13`/`useG14` 删还是接**（Task 16）—— 三者 prefix 都已有 dropdown 覆盖，倾向删（能力不丢，减一条并存路径）。若倾向保留需说明与 dropdown 的分工。
2. **R2.2 的「结论/备注」列语义偏离**（Task 8）—— 实测二者是同一载荷的两个候选存放列（非两个业务字段），设计改为标注 `source_field`。需确认该偏离可接受。
3. **场景④归档后导出是否需水印**（Task 12）—— `archive_manifest_service` 已有 `watermark` 概念，归档后导出的底稿包是否套用同一水印。

### Wave 1 实录（2026-08-10，2/24 + 一个平台级真缺陷已修）

**交付**：`backend/tests/services/test_wp_export_self_evidence.py`（Task 1，16 例）·
`backend/tests/services/test_wp_download_manifest.py` + `backend/tests/test_ie_route_inventory.py`（Task 2，22 例）·
`backend/scripts/fix/fix_acnr_dangling_api_prefix.py`（本轮抓到的真缺陷修复）。

**首跑符合「先打红」设计**：Task 1 类 B 12 红（`self_evidence.py` 尚不存在）/ 类 A 4 绿；
Task 2 清单守卫 3 红（`download_pack` 无 `template_fallback` 分支）/ 端点清册 22 绿。

#### 🔴 本轮修掉一个平台级真缺陷：catalog 的 5 个 `api_prefix` 指向不存在的适配器

守卫 `test_catalog_prefixes_have_bulk_adapters` 抓出 —— catalog 声明的 `api_prefix`
有 5 个在 `IE_ADAPTER_REGISTRY` 零命中，**后果是批量导出/回传静默跳过 15 个 sheet**
（`bulk_export_service` 对未注册 prefix 走 `except KeyError` → 标 `skip_reason=no_adapter`，
既不报错也不进用户可见清单）：

| 错误 `api_prefix` | 正确值 | 受影响 sheet |
|---|---|---|
| `d1-ecl` | `d1` | D1-15 |
| `g4` | `g4-main` | G4-1 / G4-2 / G4-3 |
| `g6` | `g6-main` | G6-2 / G6-3 |
| `g7` | `g7-main` | G7-2 / G7-3 |
| `g7-method` | `g7-equity-method` | G7-4 / G7-5 / G7-13 ~ G7-17 |

**目标前缀不靠名字相似判定**，靠三条证据（脚本内 `_verify_targets` 每次运行都重跑，
不通过则拒绝任何改动）：E1 目标前缀在 `IE_ADAPTER_REGISTRY` 有键 · E2 目标模块源码
确含该 sheet 键（`d1` 是**包** `_d1_import_export/`，须 `rglob('*.py')` 才扫得到 `_impl.py`）·
E3 该 `sheet_code` 在 catalog 唯一。15/15 全过后才写盘。

修复已 apply：`backend/data/acnr/global_catalog.json` md5 `4daec223` → `88d0408b`，
二次 apply md5 不变、`--check` 归零（幂等成立）。**只改 catalog 数据，零生产代码改动**。

#### 立项台账再修正 3 处（本轮实证，前两轮我自己也算错了）

| 维度 | 立项 | 我第 1 轮 | 我第 2 轮 | **实证（本轮）** |
|---|---|---|---|---|
| 三态齐全前缀 | 36 组 | 81 | 80 | **100 组** |
| I/E 端点分组 | — | 87 | 85 | **107 组** |
| 真死工厂模块 | — | 32（误） | 1（误） | **19 个** |

**根因**：真实 URL 有**两种形态**，我初版 `group_ie_routes` 只处理了形态 A。
- 形态 A `/api/workpapers/{wp_id}/k5/export-data` ⇒ 前缀在 `segs[-2]`（85 组）
- 形态 B `/api/h9-lease-liabilities/{wp_id}/export-data` ⇒ 前缀在 `segs[-3]`（22 组）

初版把形态 B 的 `{wp_id}` 当成「一个前缀」然后剔除，**连带丢掉 22 个真前缀**
（`h9-lease-liabilities`/`l2-interest-payable`/`m1`~`m10`/`n1`~`n3`/`n5`/`s-estimate` 等）。
`_SHAPE_B_SAMPLES` + `test_shape_ab_sum_consistent` 已钉死这两种形态都被覆盖。

#### 「19 个工厂模块是死代码」的实证与收敛裁决

`create_cycle_import_export_router` 造了 62 个 router，`router_registry` 只 include 36 个。
未注册的 26 个里 **19 个前缀在运行期零端点** —— 它们的能力由
`backend/app/routers/{name}.py` 专属 router 提供（自带 `prefix="/api/h9-lease-liabilities"`），
且**只有后者被注册**。所以这不是「两套并存」而是「一套活 + 19 个死模块」。

**用户裁决（2026-08-10）：一套最好，避免出错。** 收敛方向 = **保留专属 router、删掉 19 个死工厂模块** ——
因为专属 router 还带业务能力（`h9` 的 `generate-amortization` 实际利率法摊销 ·
`l2` 的 `accrual-check` 计提核对 · `m10` 的 `validate-formulas` + CAS 37 负债权益区分），
反向收敛会迫使这些能力搬家。已登记为新增 Task 25。

**两处我先前的误判已纠正，留痕防再犯**：
1. 「32 个前缀是 catalog 缺口」——按 `include_router` **变量名**匹配所致。真实是 19 个死 + 43 个有活端点覆盖。
2. 「`l1` 是唯一真缺口、短期借款没有导入导出」——**错**。L1 已有完整三态端点
   （`/api/workpapers/{wp_id}/l1/*`，由 `l1_short_term_loans.py` 提供且已注册）。
   误判成因：该专属 router 的导入别名恰好叫 `l1_import_export`，与工厂模块同名。
   ⇒ **判「某模块是否注册」必须按模块路径，不能按导入别名**（新增一条铁律）。

#### 变异检验教训：RED 0/3 → 3/3

首轮变异 **RED 0/3**（M1 GREEN、M2/M3 WRONG-TEST），暴露守卫两处缺陷：
1. `test_catalog_prefixes_resolve_to_live_routes` 里的 `startswith(f"{p}-")` **宽容分支**
   让 `g4`/`g6`/`g7`/`g7-method` 被 `g4-main`/`g6-main`/`g7-main` 冒充放过。
   我以为已改用适配器判据，实际是**新增了一条、旧的宽容判据还留在文件里**。
2. `d1-ecl` 改回后一条都没红 —— 它在运行期确有端点（只是没 bulk 适配器），
   三条判据全放过。⇒ 判据必须落在**适配器注册表**而非 URL 前缀相似。

另修 `_adapter_registry_keys` 被引用但未定义（会 NameError 假红）。
修正后 **22/22 全绿 + 变异 3/3 全 RED + md5 逐字节还原**。

#### 另一处「把错值锁成基线」已自纠

`test_both_sides_have_gaps` 初版写 `assert catalog_only`（断言 catalog 独有前缀非空），
而那 5 个独有前缀**正是本 spec 要修的缺陷** ⇒ 修好后守卫反而打红，且红的方向会诱导
下一轮把修复回退掉。已改为**单向**不变量：`catalog ⊆ 运行期活前缀`（本条）+
`运行期 ⊋ catalog`（差集 = Task 14 作业面，实测 41 个）。

**Wave 2 起点**：Task 4（建 `self_evidence.py`）。改完后 Task 1 的 12 条红应全部转绿。

### Wave 1 实录 —— Task 3（2026-08-10，3/25）

**交付**：`ieOrphanBaseline.spec.ts`（新建，17 例）+ `cycleImportExportRegistry.spec.ts`（扩展，20 例）。

**首跑符合「先打红」设计**：孤儿守卫 16 passed / **1 failed**（12 个孤儿未处置 = Wave 4 Task 16/17 作业面）· registry 守卫 19 passed / **1 failed**（catalog 59 前缀 vs registry 10 个，缺 49 = Task 13 作业面）。

**孤儿基线由 11 修正为 12** —— 递归判据抓出一条立项与我自己都漏掉的**孤儿链**：

| 发现 | 实证 |
|---|---|
| 第 12 个孤儿 | `composables/workpaper/j2/useJ2ImportExport.ts` |
| 为何漏判 | 它**有** direct consumer（`composables/workpaper/j2/index.ts`），按「是否被 import」判必然放过 |
| 为何仍是孤儿 | `j2/index.ts` 自身 **零消费方** —— J2 的 10 个 `.vue` 一个都没 import 它 |
| 链条规模 | `j2/` 下 **11 个 composable 全部**只被该 index 消费 ⇒ 整个 J2 composable 层用户不可达 |

这正是 R5.6「递归到有渲染宿主为止」要抓的形态，也印证了 memory 铁律「判某能力接没接要落到唯一消费方 + 有渲染宿主」。

**本轮修掉 4 处守卫自身缺陷**（全部属「判据写错导致假红/假绿」，逐条留痕防重犯）：

1. **import 形态判据错**：按 `@/` 别名前缀匹配，而前端实际是 **相对路径 296 处 vs `@/` 别名 30 处** ⇒ 报出 94 个假孤儿，连有 33 个消费方的 `useD4ImportExport` 都判孤儿。改为解析 import 说明符 → 绝对模块路径 → 递归找 `.vue`。
2. **`path.resolve` 在 Windows 补盘符**：`resolve('/' + dir, spec).slice(1)` 把 `/components/...` 变成 `D:\components\...` 再切首字符 ⇒ 得到 `:\components\...`，全部解析失败。改用**纯字符串段运算**（split/pop/push），不依赖平台相关 API。
3. **复合变体键判据用错真源**：断言 registry `sheets[]` ⊆ catalog `sheet_code` ⇒ F3/F4 的 11 个复合变体键（`F3-7-debit` / `F4-8-credit` / `F4-7-*` 等）全部假红。实证：这些键存在于**后端 specs**（`_f3_import_export` 16 键 / `_f4_import_export` 24 键），catalog 只登记基础 `sheet_code`。正确判据 = 「registry sheets ⊆ 后端 specs 键集」，catalog 只作**前缀**真源。
4. **`_adapter_registry_keys` 被引用但从未定义**（Task 2 遗留）⇒ NameError 假红。

**判据反向自检已配齐**：`useD4ImportExport`（33 消费方）必须判非孤儿 · 只加 spec 文件的 import 不得让基线缩短 · 替身自检覆盖「孤儿链」与「环形依赖不死循环」 · `reachesRenderHost` 函数体内不得出现任何 `useXxxImportExport` 字面量（结构上保证判据不依赖符号名）。

**Wave 2 起点**：Task 4（建 `self_evidence.py`）。完成后 Task 1 的 12 条红应全部转绿。

### Wave 2 实录 —— Task 4（2026-08-10，4/25）

**交付**：`backend/app/services/wp_export/self_evidence.py`（单一真源共享件）。
Task 1 守卫 **16/16 全绿**（Wave 1 首跑的 12 条红全部转绿），
本 spec 后端守卫合计 **38/38**，**变异检验 6/6 全 RED + md5 逐字节还原**。

**API 形态**（守卫逐条钉死）：

| 符号 | 作用 |
|---|---|
| `needs_self_evidence(verdict=, html_data=, has_entry_rows=, sheet_name=None)` | 纯函数判据，返四态（三档 + `None`） |
| `build_self_evidence_banner(kind=, verdict=None, detail="")` | 文案构造，只取两个真源 |
| `stamp_self_evidence(ws, banner)` | 落盘：1 行 banner 加粗标红 / 2 行留空 |
| `SELF_EVIDENCE_DATA_START_ROW = 3` | 共享常量，禁调用方各写行号 |
| `_KIND_LABELS` | 非 verdict 档文案唯一真源 |

**两处设计取舍**：

1. **`has_entry_rows` 的语义是「有非空行」而非「有行」** —— 真实库 103.37 万行里
   仅 695 行非空，按「有行」判会让几乎所有底稿都落进 `entry_not_in_xlsx` 档，
   自证反而变成噪声。已写进 docstring 的 Args 说明。
2. **`build_self_evidence_banner` 对未知 kind / 缺 verdict 实参 fail-fast 抛 `ValueError`** ——
   不做静默降级。理由：文案缺失比抛异常更难排查（产物看着正常、实则少了自证），
   属 memory 记的「fail-open 掩盖接线错误」同族风险。
3. **`stamp_self_evidence` 不移动既有内容** —— 直接覆写模板第 1 行会吃掉模板表头。
   带内容的模板走「另建自证 sheet」，该分支归 Task 5 接线时决定。

**本轮变异脚本自身有三处缺陷（已修，均属「脚本缺陷」而非守卫缺陷）**：

| 缺陷 | 症状 | 修法 |
|---|---|---|
| `write_text` 归一行尾 | CRLF → LF ⇒ **md5 恒 MISMATCH**（首轮误报「还原失败」） | 改 `read_bytes`/`write_bytes` |
| M2 变异插 `_dead` 键 | 只破坏 dict 结构、没让两档文案真相同 ⇒ **假 GREEN** | 改锚 `banner = _KIND_LABELS[kind]` 让两档取同一 label |
| M5 变异写成链式赋值 | `A = _X_REMOVED = "…"` 值没变 ⇒ **等于没变异，假 GREEN** | 直接替换短语字面量 |

第二处还额外暴露一条**锚点选取铁律**：`_KIND_LABELS` 的值是**多行括号形态**，
按 `'"entry_not_in_xlsx": "…'` 单行找必 0 命中（ANCHOR-MISS）。
⇒ 变异锚点要选**真实单行**，优先锚取值处（`banner = _KIND_LABELS[kind]`）
而非多行字面量内部。

**Wave 2 起点**：Task 5（`download_single` / `download_pack` / `_sync_export_workpaper_xlsx` 接自证）。

### Wave 2 实录 —— Task 5 / 6（2026-08-10，6/25）

**交付**：`wp_xlsx_export_service` 接自证 sheet · `wp_download_service` 接自证边车 +
清单覆盖 `template_fallback` + `_VERDICT_ADVICE` 单一真源。
后端守卫 **54/54 全绿**，另做**真实执行验证 8/8**（看产物不看源码）。

#### 🔴 关键裁决：批量打包不为盖章重写 xlsx（实证驱动）

R1.1 要求「批量打包产出的文件内含自证字样」。直觉做法是 openpyxl 读-改-写盖一行，
但先测了模板复杂度：`backend/wp_templates/` **351 个 xlsx** 里

| 风险部件 | 命中文件数 |
|---|---|
| `xl/drawings/`（图形/文本框） | **182** |
| `xl/media/`（图片） | **50** |
| `xl/charts/`（图表） | 1 |
| `xl/tables/` | 1 |
| pivot / VBA | 0 |

openpyxl 的 round-trip **会丢弃**这些部件 ⇒ 为盖一行说明把 182 个模板的图形削掉，
是拿「说明清楚」换「内容被削」，完全不划算。

**故批量路径保持 `zf.write` 原字节不动**，自证走两处无损通道：
① ZIP 内同名边车 `{底稿}.自证说明.txt`（紧邻可见）② `_未导出清单.txt` 一并列出。

#### export-xlsx 路径：另建 sheet 而非盖第 1 行

`_sync_export_workpaper_xlsx` 拿到的是**已加载的致同模板**，第 1 行通常是表头/单位名。
直接 `stamp_self_evidence(ws, ...)` 会覆写表头。改为 `create_sheet(index=0)` 插一张
`_导出说明`（`_` 前缀让它排最前）。真实执行验证已确认「表头完好未被覆写」。

#### 清单从「未导出清单」改成「内容提示清单」

`template_fallback` 的底稿**进了** ZIP，把它算进「未导出 N 份」会让计数与 ZIP 内
文件数矛盾、用户对不上账。改为分开计数：`未导出（无文件）` / `已导出但为空白模板`。

#### 处置建议改为单一真源逐档取（修一处结构性缺陷）

改造前是**写死的 2 条 bullet 覆盖 3 个档位** ⇒ 三档同时出现即「建议条数 < 档位数」，
等于有档位无处置指引。现在从 `_VERDICT_ADVICE` 按出现档位逐条取，条数恒等于档位数。

并补了 4 条**键集完整性守卫**（注释里承诺过就必须落地）：非 `file` 档全覆盖 ·
无 stale 键 · `file` 档不得登记（否则正常导出也带话术）· 每条建议含可操作动词。
理由：只断言「条数 ≥ 档位数」不够 —— 缺键会退到 `_VERDICT_ADVICE_FALLBACK`，
条数照样够但内容是「请联系管理员」，属 fail-open 掩盖接线错误。

#### 真实执行验证（产物级，8/8）

| 用例 | 断言 | 结果 |
|---|---|---|
| `html_data` 非空 | 产物**无** `_导出说明` sheet（R1.6 零噪声） | OK |
| `html_data` 空 + 无录入 | 有自证，文案含「录入内容未包含…请打开保存一次」 | OK |
| `html_data` 空 + 有录入 | 有自证，文案含「已有录入记录存于系统内…使用导出数据」 | OK |
| 三例 | 致同模板表头逐字完好 | OK |
| B vs C | 两档文案**逐字不同**（R1.8） | OK |

**签名扩展是 additive**：`has_entry_rows: bool = False` 默认值保持既有调用方零改动。

**Wave 3 起点**：Task 7（建 `entry_payload_reader.py`）。

### Wave 3 实录 —— Task 7 / 8 / 9（2026-08-10，9/25）

**交付**：`entry_payload_reader.py`（取值层）· `entry_sheet_writer.py`（渲染层）·
`test_entry_payload_reader.py`（21 例）· `test_export_entry_sheet.py`（17 例，**真实执行**）。
本 spec 后端守卫累计 **92 passed**。

#### 立项台账再修正一处：单行最长 866,845 字符（不是 181,056）

按「非空行 + 按形态」重新分组直查，得到更细的真源：

| 存放列 | json_array | json_object | plain_text | 单行最长 |
|---|---|---|---|---|
| `remark` | 284 | 120 | 194 | **866,845** |
| `conclusion` | 17 | 6 | 75 | 5,974 |

⇒ 三条设计结论（都已落进代码 + 守卫）：
① **必须读两列** —— 两列各自都承载全部三种形态，只读一列会丢数据；
② **必须剔空行** —— 99.93% 是空骨架（1,033,715 / 1,034,515）；
③ **三道闸** —— 条数闸 `MAX_ITEMS_PER_WP=500`（实测单份非空最多 49）/
总量闸 `MAX_TOTAL_CHARS=2_000_000`（容得下最大单行）/
个体闸 `MAX_ONE_CHARS=200_000`（**必须小于 866,845 否则永不触发**，守卫按此断言）。

#### 取值层的两条 fail-visible 设计

1. **查询异常记 ERROR 而非 WARNING** —— 这里失败意味着「导出少了录入内容」，
   而表现形式与「本底稿确实没录入」**完全一致**，只能靠日志级别区分。
   守卫用 `caplog` 断言 `levelno >= ERROR`。
2. **JSON 解析失败降级 `plain_text` 但计数 + 记 WARNING** —— 实测 269 行本就是
   纯文本（结论/备注的自然形态），当异常会让整份导出崩；但真损坏的 JSON 也必须留痕。
   产物内如实标注「N 项内容无法按结构解析」。

另钉死一条列名判据：SQL 必须用 `wp_id` **不是** `workpaper_id`
（平台已因写错这个列名踩过 P0：整条取值链被 `except` 吞成 WARNING，
而源码守卫 / 纯函数单测 / characterization 三层全绿）。守卫直接扫已执行的 SQL 串。

#### Task 9 的判据形态：真实执行，不看源码

只断言「代码里出现了 `checklist_responses`」对以下情形全部无效 ——
函数写好了但调用点传 `None`（本模块 `entry_payloads` 默认就是 `None`）·
sheet 建了但内容空 · 内容写了但覆盖了模板单元格。故 17 例判据一律是
**造载荷 → 真跑 `_sync_export_workpaper_xlsx` → 打开产物逐格核对**。

其中三条值得单列：

- **R2.3 配反向自检**：先断言模板 6 个单元格逐格相等，再**故意篡改 A1** 并断言
  同一判据必须发现 —— 否则「逐格相等」可能是恒真的。
- **列名取载荷键集须按并集保序**：两行键不同时（`{甲,乙}` / `{甲,丙}`）三个键都要
  出现。只取首行键集会静默丢列。
- **嵌套值必须压平**：openpyxl 写 dict/list 会抛 `ValueError`，一个嵌套字段就能让
  整份导出失败 ⇒ `_flatten` 转 JSON 串而非抛。

#### 两处「只追加不改写」的实证依据

- **模板单元格回填不做**（R2.3）：需要 per-cycle 的「item_id → 单元格地址」映射，
  而 `structure.json` 全库 **0 个**、`item_id` 形态 **211 种**，没有可用映射真源。
  硬按顺序塞会把数据写进错格子 —— **错数比无数更难发现**。
- **sheet 名冲突递增**（R2.5）：还要尊重 Excel 的 31 字符上限 ——
  超限 openpyxl 会**静默截断**，截断后可能又撞名，故截断后须重新判重。
  守卫含「模板里已有 `_录入内容`」的真实冲突场景。

**签名扩展仍是 additive**：`entry_payloads: Any = None` 默认不建 sheet，
既有调用方逐字不变（守卫 `test_none_payload_不建_sheet_保持既有行为` 钉死）。

**Wave 4 起点**：Task 10（建 `scenario_registry.py` 四场景语义真源）。

### Wave 4 实录 —— Task 10（2026-08-10，10/25）

**交付**：`backend/app/services/bulk_tab/scenario_registry.py` +
`test_scenario_registry.py`（28 例）。本 spec 后端守卫累计 **120 passed**。

#### 端点真源（运行期实证，非源码猜测）

`wp_bulk_router` 真实注册 11 个端点，四场景绑定如下：

| 场景 | export | import | mode | 归档态 |
|---|---|---|---|---|
| ① `blank_template` | `…/bulk-tab/export-templates` | — | `template` | ✅ 可用 |
| ② `fill_back` | — | `…/bulk-tab/import` | `template` | ❌ 拒绝 |
| ③ `refresh_edit` | `…/bulk-tab/export-data` | `…/bulk-tab/import` | `data` | ❌ 拒绝 |
| ④ `archive_export` | `…/bulk-tab/export-data` | — | `data` | ✅ 可用 |

②③ 的 `import_endpoint` **逐字相同**（R3.4），守卫直接断言两者相等 ——
分成两个端点会让冲突策略（overwrite / fill-empty / reject）与拓扑序无法统一。

#### 🔴 R3.8 的导入侧门控**已有实现**，Task 12 从「新建」缩为「核实 + 守卫」

读 `bulk_tab/workflow_gate.py` 发现 `_BLOCKED_STATUSES` **已含**
`WpFileStatus.archived` ⇒ 归档态底稿在批量导入时已被判 `blocked`。
故本轮直接补了**声明↔实现交叉锁死**守卫（`test_workflow_gate_treats_archived_as_blocked`）：
registry 声明 `archived_allowed=False` 是声明侧，真正拦下来的是 `WorkflowGate.classify`，
两侧必须一致 —— 只改声明不看实现，就是「additive 注入即死代码」的同族缺陷。
配反向自检 `test_workflow_gate_allows_draft` 防该断言恒真。

#### 命名偏离登记（design → 实现）

design.md 的 `ScenarioSpec` 草案用中文字段名（`产物说明` / `适用时点`）。
实现改英文标识符 + 中文取值（`artifact_note` / `timing_note`）——
中文标识符在 Python 合法，但会让 IDE 补全、JSON 序列化键名、前端 TS 类型
全部带中文，代价大于收益。**字段值仍是中文**，R3.7「文案单一真源」不受影响。

#### 守卫里三条「用户可见面」判据

不只验结构，还验**说明文案是否真的说清了那件事**：
- 场景①的 `artifact_note` 必须含「不含」（R3.2 的用户可见面）
- 场景③必须含「不可直接改」（R3.3：取数列会被下次取数覆盖）
- 场景④必须含 `sha256` 或「校验」（归档用途需完整性证据）

另有「四场景产物说明互不相同」—— 相同等于没区分，是 R3.7 的实质。

**Wave 4 剩余**：Task 11（manifest `mode` 错用校验）· Task 12（归档时点核实）·
Task 13~15（registry 真源换血）· Task 16/17（孤儿处置）· Task 18（UI 入口）。

### Wave 4 实录 —— Task 11（2026-08-10，11/25）

**交付**：`scenario_registry.validate_import_mode()` + `ModeMismatch` ·
`bulk_import_service._check_manifest_mode()` 接入 `run()` 与 `dry_run()` 两侧 ·
`test_bulk_mode_mismatch.py`（16 例）。后端守卫累计 **136 passed**。

#### 缺陷实证：`mode` 字段写了但从来没人读

grep `bulk_import_service` 确认它只取 `manifest.get("files")` 与
`manifest.get("cycles")`，**`mode` 键零读取**。而 `manifest_builder` 早已写入
（`BulkManifest` 的 dataclass 字段实测含 `mode`）⇒ R3.5 是纯接线缺口，
本次修复**零新增存储**。

#### 后果不对称，所以错误文案必须说后果

| 错用方向 | 后果 |
|---|---|
| 空白模板包 → 覆盖已录入底稿 | **用空单元格清空数据，不可撤销** |
| 数据包 → 当模板填 | 把别人的数据当自己的底稿，属数据串项目 |

只说「模式不匹配」用户判断不出严重性。故 `_MISMATCH_CONSEQUENCE` 按实际
mode 分档给后果说明，错误文案含四件事：所选场景 / 实际 ZIP / **后果** / 下一步。
守卫逐条断言这四个片段都在。

#### 三处 fail-closed

1. **`mode` 缺失也拒绝** —— 无法判断包性质就不能写库（`None` / `""` / 未知值全拒）。
2. **校验器自身出错仍拒绝** —— 场景键拼错时 `_check_manifest_mode` 捕获
   `KeyError`/`ValueError` 后**返回 ModeMismatch 而非 None**。若放行，一个拼错的
   键就让整条 R3.5 防线静默失效（memory：fail-open 掩盖接线错误最贵）。
3. **拿纯导出场景校验导入直接抛** —— `blank_template`/`archive_export` 无
   `import_endpoint`，用它们校验属调用方逻辑错，静默放行等于校验形同虚设。

#### 零写入用真实执行证明

只断言「返回了失败报告」不够 —— 可能先写了一半才失败。守卫给
`SnapshotGuard.__init__` 与 `import_tab` 两个副作用入口下探针，
断言 mode 不符时**调用次数为 0**（探针内直接 `raise AssertionError`）。
校验点放在 align / 快照 / 写入**之前**，`db=None` 也能走完并返回 ⇒ 本身即零写入的证据。

另配两条反向自检：**闸门恒拒**（mode 相符必须通过，否则功能全废）与
**additive 保证**（`scenario=None` 时完全跳过，既有调用方逐字不变）。

**Wave 4 剩余**：Task 12（归档时点核实）· Task 13~15（registry 真源换血）·
Task 16/17（孤儿处置，待用户裁决）· Task 18（UI 入口）。

### Wave 4 实录 —— Task 12（2026-08-10，12/25）

**交付**：`backend/tests/services/test_archive_gating.py`（16 例）。
**零生产代码改动** —— 本任务从「新建门控」缩为「核实 + 钉死」，因为实证发现两侧都已就位。

#### 实证：导入侧早已实现，导出侧本就无状态门

| 侧 | 现状 | 判据 |
|---|---|---|
| 导入 | **已拦** | `workflow_gate._BLOCKED_STATUSES` 含 `archived`；`dry_run()` 与 `run()` **两侧都**调 `gate.classify()`，对 `blocked` 标 `blocked_by_status` 并 `continue` |
| 导出 | **不拦** | `bulk_export_service` 里 `WorkflowGate` / `archived` / `status` **全部零命中** |

⇒ R3.8 的三态（归档态拒导入、准导出）结构上本已成立，缺的只是守卫。

#### 守卫的价值：防三种退化

① 有人从 `_BLOCKED_STATUSES` 摘掉 `archived`（归档后可改数据，破坏留痕）
② 有人给导出侧加状态过滤（归档后调阅不了，违背归档的意义 —— 守卫直接断言
   `bulk_export_service` 源码里不得出现 `WorkflowGate`/`_BLOCKED_STATUSES`/`blocked_by_status`）
③ 只改 registry 声明不动实现（声明↔实现分叉）

#### 三条容易写成假绿的判据，已按实现侧而非声明侧写

- **`classify` 必须真被消费**：`_BLOCKED_STATUSES` 含 `archived` 只是**声明**，
  真正拦下来靠 service 调用。守卫用 `inspect.getsource` 断言 `dry_run`/`run`
  两个入口都出现 `classify(` 与 `blocked_by_status`。
- **`run()` 必须真跳过**：标了记号还继续写等于没拦。判据是正则匹配
  `if item.blocked:` 之后的块里有 `continue`。
- **`under_review` 是 `revert_needed` 不是 `blocked`**：两者处置不同（前者有权限可回退），
  混为一谈会让复核中底稿永久不可导入。另断言两个状态集**不相交** ——
  相交会让分类结果取决于判断顺序。

#### R3.6 的判据选择：结构性保证优于跑两次

「归档前后两时点都可执行」没有去真跑两次归档流程（依赖真实项目 + 有副作用），
而是断言**导出通路不读任何工作流状态** —— 读不到 status，就不可能因 status
变化而失败。这比行为测试更强且更稳。另核实 `ZipAssembler` 确有 sha256 + manifest
（归档包的离线完整性证据）。

**Wave 4 剩余**：Task 13~15（registry 真源换血）· Task 16/17（孤儿处置，
`useF1`/`useG13`/`useG14` 删或接**待用户裁决**）· Task 18（UI 入口）。

### Wave 4 实录 —— Task 13（2026-08-10，13/25）

**交付**：`backend/scripts/fix/gen_cycle_import_export_registry.py`（生成器，`--check`/`--apply`）·
`cycleImportExportRegistry.generated.ts`（49 前缀，脚本产出）·
`cycleImportExportRegistry.ts` 改门面 · 守卫扩至 **27 例全绿**。

**覆盖面：10 → 59 前缀**（catalog 全量）。改造前 49 个前缀「后端有能力、用户点不到」。

#### 架构：generated + MANUAL_OVERRIDES，overrides 后置

```
CYCLE_IMPORT_EXPORT = { ...GENERATED_IMPORT_EXPORT, ...MANUAL_OVERRIDES }
```

**不能纯 catalog 生成** —— 既有 10 个 key 含 catalog 表达不了的**传输层键**：

| 类型 | 例 | catalog 有吗 |
|---|---|---|
| G0/H0 函证传输键 | `G0-3S` | ❌ 是后端 `_SHEET_NAME_MAP` 的键，非 `sheet_code` |
| F3/F4/F2 复合变体键 | `F3-7-debit` / `F4-8-credit` / `F2-24-count` | ❌ 只在后端 specs |

实测 catalog `f3` 仅 5 键（`F3-2`~`F3-6`）而后端 16 键；`f4` 4 vs 24。
纯生成会让下拉**少掉一半区段**。更关键：`F3-7` 基础码在 catalog **根本不存在**，
连「按 `startsWith(基础码+'-')` 认变体」的兜底也救不了。

**展开顺序不能反**：`{ ...MANUAL, ...GENERATED }` 会让 catalog 基础码覆盖手工传输键 ⇒ 键丢失 ⇒ 端点 400。已在门面 docstring 写明。

#### 本轮修掉三处自身缺陷

1. **生成的 TS 文件语法错误** —— 注释里写了 `f1/f2*/f3` 字样，其中 `*/`
   **提前闭合了块注释**，esbuild 报 `Unexpected "*"`，整个 spec 文件无法 collect。
   ⇒ 生成器模板里写死一条注释警示：该段不得出现 `f2` 后紧跟星号加斜杠。
2. **判据真源选错（假红 11 条）** —— sheets 只比 catalog 的 `sheet_code`，
   F3/F4 的 11 个复合变体键全部假红。改为比 **catalog ∪ 后端 specs 并集**。
3. **按命名约定猜模块名（假红 3 条）** —— 以为 `f2-st` → `_f2_st_import_export.py`，
   实际是 `_f2_stocktake_import_export.py`（`f2-val` → `_f2_valuation_…`、
   `f2-spe` → `_f2_special_…`）。约定不成立 ⇒ 改**反向扫描**：逐模块读出它自己
   声明的前缀（工厂族读 `api_prefix=`、手写族读 `@router` 路径段），
   再把该模块的 sheet 键归到该前缀下。带 mtime 无关的模块级缓存。

#### R4.6 零回归的判据形态

守卫内联**改造前 10 个 key 的完整 sheets 清单**（逐字抄录），断言 `apiPrefix`
与 `sheets` 数组逐元素相等。这比"比对文件 diff"更强：即便有人重排 registry
结构，只要这 10 条的取值没变就通过；一旦变了立刻红。

另配三条一致性断言：`MANUAL_OVERRIDES` 键集 ↔ 生成器 `MANUAL_PREFIXES` **双向锁死**
（防两处都有或都没有）· generated 与 MANUAL **键集互斥**（防同一前缀两处登记）·
门面 = 两者并集。

**Wave 4 剩余**：Task 14（补 catalog 缺口）· Task 15（未登记打红 + 豁免表）·
Task 16/17（孤儿处置，**待用户裁决**）· Task 18（UI 入口）。

### Wave 4 实录 —— Task 14（2026-08-10，14/25）

**交付**：`backend/scripts/fix/fix_acnr_catalog_ie_gap.py`（含 `GAP_REGISTRY` 显式登记表）。
**catalog 前缀 59 → 72**，registry generated **49 → 62**。后端守卫 82/82 · 前端 43/44（唯一红是 Task 16/17 预期红）。

#### 缺口实证与四档裁决

运行期三态齐全 **100** 个前缀 vs catalog 已登记 **59** ⇒ 缺口 **41**。按「能否安全补」分档：

| 档 | 数 | 判据 | 处置 |
|---|---|---|---|
| `SAFE` | **13** | 工厂 `specs` 可 AST 抽出逐 sheet 的 `item_id`，且有 bulk 适配器 | **已补**（38 sheet） |
| `NO_ADAPTER` | **23** | `IE_ADAPTER_REGISTRY` 无该前缀 | **禁止补**（见下） |
| `RISKY` | 4 | 有适配器但 `specs` 抽不出（`c24-journal`/`e1`/`j1`/`l0`） | 登记，人工核后另补 |
| `NO_MODULE` | 1 | `j2` 找不到声明模块 | 登记（属 J2 孤儿链） |

#### 🔴 原 task 描述的做法会重新制造刚修掉的缺陷

原文写「补工厂独有的 32 个前缀的 `import_export` 段」。若照做，那 23 个
**无 bulk 适配器**的前缀会进 catalog ⇒ `bulk_export_service` 走
`except KeyError` → `skip_reason=no_adapter` **静默跳过** ——
这正是本 spec Task 2 刚修掉的缺陷（当时 5 个前缀 / 15 个 sheet），
规模还大 4 倍。

⇒ 脚本内建前置校验：**无适配器的前缀一律拒绝写入**（不是警告，是拒绝）。
正确顺序是先建适配器、再登记 catalog。

#### 🔴 `item_id` 不猜 —— 猜错比不可用更糟

catalog 的 `item_id` 决定 bulk 从哪个 `checklist_responses.item_id` 读写。
猜错 ⇒ 导出读空、导入写进别的键（**数据错位**，且比"功能缺失"更难发现）。
故只补能从后端 specs 字典 **AST 直取**的 13 个前缀，其余 5 个显式登记待人工核。

#### 本轮修掉一处探针缺陷（把 SAFE 数从 0 报成 13）

首轮判定 **SAFE=0 / RISKY=17**，据此差点得出「Task 14 不可安全执行」的结论。
根因：`_I1_SPECS: dict[str, dict[str, Any]] = {...}` 是 **`ast.AnnAssign`**
（带类型注解的赋值），而我的常量收集只处理了 `ast.Assign` ⇒
`specs=_I1_SPECS` 这个 Name 解引用失败 ⇒ 13 个可抽模块全被误判成"抽不出"。

补上 `AnnAssign` 分支后 SAFE 从 0 变 13。**教训**：AST 取模块级常量必须同时收
`Assign` 与 `AnnAssign`，本仓库带类型注解的常量声明是主流写法。

#### 11 个区段变体未补（如实报告而非静默）

`I1-2-base` / `I1-2-cost` / `I2-2-input` / `I3-2-impair` / `I4-7` 等 11 个
**区段变体键**在 catalog 里**没有 sheet 条目**。脚本不新建 sheet ——
新建需要 `addr_id`/`domain`/`cycle`/`sheet_name` 一整套 ACNR 目录元数据，
属目录维护半径。已在 `--apply` 输出里逐条列出（`[NOTE]`），不静默吞掉。

#### 幂等与安全

`--check`/`--dry-run`/`--apply` 三态 · 二次 apply 归零（实测）·
写盘前 round-trip 自检（`json.dumps` 不能逐字复现原文即拒绝，防重排整个
1MB 文件与并发会话互相回退）· 已在 catalog 的 `sheet_code` 一律不动（防覆盖既有 `item_id`）·
`GAP_REGISTRY` 完整性校验（被挡下的前缀必须有登记理由，否则 exit 2 —— R4.7）。

**Wave 4 剩余**：Task 15（未登记打红 + 豁免表）· Task 16/17（孤儿处置，**待用户裁决**）· Task 18（UI 入口）。

### Wave 4 实录 —— Task 15（2026-08-10，15/25）

**交付**：registry 守卫 **35 例**（+8）· 孤儿守卫 **23 例**（+6，含 R5.4 stale 检测）·
**变异检验 4/4 全 RED**。前端合计 57/58（唯一红是 Task 16/17 预期红）。

#### 豁免表不在前端另抄一份

缺口裁决理由已在 `fix_acnr_catalog_ie_gap.py` 的 `GAP_REGISTRY`（28 条带理由）。
前端再抄一份就是两处真源 —— 正是本 spec 一直在修的病。
故守卫**直接读那个 Python 字典**做交叉核对：

```
运行期三态齐全前缀  ⊆  registry ∪ GAP_REGISTRY
```

少一个即打红 ⇒ 「后端新增能力但两边都没登记」无法静默逃逸（R4.4）。

#### 豁免理由的质量也被守卫检查

不只验「有理由」，还验理由**说清了何时可移出**：
- 必须含可归因关键词之一（适配器 / item_id / 模块 / 半径 / 覆盖 / 人工核 / 专用），
  纯空话（"暂不处理"）打红
- `h9-lease-liabilities` 等实证的「无适配器」类，理由里必须点明「适配器」——
  防理由与实情脱节

#### R5.4 孤儿豁免 stale 检测

`ORPHAN_EXEMPTIONS` 当前**空表**（12 个孤儿全走删除或接线，无需豁免），
但结构与 stale 检测已就位：豁免项一旦接上渲染宿主即打红，提醒移出并下调基线。

这与 memory 的「死代码立即删除，不留 DEPRECATED 注释，否则每次复盘重复提议」
是同一铁律的另一面：**登记表必须能自我失效**。配替身自检防判据恒绿。

#### 🔴 变异检验揪出我一处**文档写错**

M2 变异（反转 `{...GENERATED, ...MANUAL}` 展开顺序）首跑 **GREEN**。
我一度以为是守卫缺陷，核实后发现是**注释写错了**：

门面注释原写「顺序反了会让 catalog 基础码覆盖手工传输键 ⇒ 键丢失 ⇒ 端点 400」。
但生成器已把 `MANUAL_PREFIXES` 从产出中排除 ⇒ 两侧键集**互斥** ⇒
`{...A, ...B}` 与 `{...B, ...A}` 结果完全相同，那个"危险"根本不存在。

**真正的安全保障是互斥不变量**（已有守卫钉死），不是展开顺序。
已改正注释并说明：保持 MANUAL 后置只表达意图（手工优先），不承担正确性。

⇒ 教训：变异检验不只验守卫，也验**文档声称的因果关系是否成立**。
一条 GREEN 可能意味着「守卫漏了」，也可能意味着「你以为的风险不存在」。

M2 改为直接篡改 `f5` 的 `sheets`（R4.6 真正要守的东西）后 4/4 全 RED。

另修一处锚点缺陷：M2 初版用 `\n` 跨行锚点，本仓库 CRLF ⇒ ANCHOR-MISS（memory 已记该坑）。

**Wave 4 剩余**：Task 16/17（孤儿处置，**待用户裁决**）· Task 18（UI 入口）。

### Wave 4 实录 —— Task 16（2026-08-10，16/25）

**交付**：删 3 个重复源 composable + 3 个 spec 引用改指 registry。
孤儿基线 **12 → 9**。相关测试 64/65（唯一红是 Task 17 待接线的 9 个）。

#### 逐个孤儿的证据化裁决（先建判据再动手）

判据三条：**A** registry 含该 prefix（能力在目录里）· **B** 该循环目录下有 `.vue`
挂了 `CycleImportExportDropdown`（用户点得到）· **C** 该循环有**别的**可用 I/E composable。

裁决规则：`B 或 C` ⇒ 删（本 composable 是并存的第二条路）· 仅 `A` ⇒ 接线 · 都不成立 ⇒ 豁免。

实测结果 **DELETE 3 / WIRE 7 / EXEMPT 2**（我先前口头估的「8 删 + 4 接」是错的，按证据改）：

| 孤儿 | 行数 | 内容 | 裁决 |
|---|---|---|---|
| `useF1ImportExport` | 7 | 纯 `export {…} from './useWorkpaperImportExport'` re-export shim | **删** |
| `useG13ImportExport` | 6 | 只有 `G13_IMPORT_EXPORT_SHEETS` + `G13_API_PREFIX` 两个常量 | **删** |
| `useG14ImportExport` | 6 | 同上 | **删** |
| `useK1WriteoffImportExport` | 182 | 针对 **K1-9 / K1-12** | 改判 **接线** |
| 其余 6 + 2 | — | 见 Task 17 | 接线 / 豁免 |

#### 🔴 `useK1Writeoff` 从「删」改判「接线」—— 差一步就删错

初判 DELETE，理由是 K1 已有 `useK1ImportExport`（276 行、10 个消费方）。
但核实它针对的 sheet 后发现：

- `useK1Writeoff` 覆盖 **K1-9 / K1-12**
- registry 的 `k1` 只有 `K1-11 / K1-2 / K1-4 / K1-5 / K1-7 / K1-8`
- ⇒ **K1-12 无任何覆盖**

删了就是丢能力，违反 R5.3。⇒ 教训：**「同循环已有 I/E」不等于「该 sheet 已被覆盖」**，
必须比到 sheet 级。

#### 另修一处探针缺陷（差点让 K1 判错）

首版探针用 `p.name.lower().startswith(prefix)` 匹配循环文件，`prefix='k1'` 把
**K10/K11/K12/K13** 的文件全吞进来 ⇒ K1 的 `other_ie` 里出现
`useK10ImportExport`/`useK11ImportExport`，判定被别的循环污染。
加数字边界 `^k1(?![0-9])` 后才拿到真实结论（`other=['useK1ImportExport']`）。

#### 删除不是简单删文件 —— 是把重复源收敛成单一真源

`useG13`/`useG14` 被 **3 个 spec 文件** import（`g13FairValueChanges.integration.spec.ts`
/ `g14CreditImpairmentLoss.integration.spec.ts` / `g14ReviewFixes.spec.ts`）。
直接删会破坏测试。做法是把这 3 处引用**改指 registry**：

```ts
// 改前：import { G13_IMPORT_EXPORT_SHEETS } from '../composables/useG13ImportExport'
// 改后：import { CYCLE_IMPORT_EXPORT } from '../shared/cycleImportExportRegistry'
expect([...CYCLE_IMPORT_EXPORT.g13.sheets]).toEqual(['G13-2', 'G13-3'])
```

测试意图不变（G13 恰有 G13-2/G13-3），但现在校验的是**真源**而非一份副本。

#### 顺带纠正立项一处记载

立项记 `useG13`/`useG14` 是「import 路径与符号双 0 命中」—— 实测**有** import 方
（那 3 个 spec 文件）。它们是孤儿的真正原因是「唯一消费方是测试文件」，
不是「零命中」。

#### R5.3 的守卫形态：证明删除没丢能力

新增两条断言替代原「G13/G14 唯一 import 方是测试文件」（那两个文件已不存在）：
- **删除组能力仍被覆盖**：registry 必须仍有 `g13`/`g14` 条目，且 G13/G14 目录下
  确有 ≥2 个 `.vue` 挂了 dropdown（用户点得到）
- **F1 能力由 `useWorkpaperImportExport` 覆盖**：断言真实实现文件存在且导出
  `useF1ImportExport` 符号，且 F1 的 `.vue` 确实在用它
- 另加「删除组确已不在磁盘」防「标了删实际没删」

**Task 17 作业面（9 个）**：`useH5`/`useH7`/`useK12`/`useK5`/`useL4`/`useK1Writeoff`
（registry 已有 prefix，缺 dropdown 宿主）· `useK0`（registry 有 `k0`）·
`useL0`/`useJ2`（registry 无 prefix，需先补 catalog 或豁免）。

### Task 25 裁决与阻塞（2026-08-12，用户选方案 B）

**本 spec 交付状态 24/25**：Task 1~24 全部完成。**Task 25 转阻塞**（`[ ]` → `[-]`），
原因是 sheet 级能力缺口：19 个待删工厂模块里只有 `h9`/`l7`/`l8` 的 sheet 面被专属 router
完全覆盖，其余 16 个的 `X-3 调整分录` sheet **只存在于待删模块里**，现在删就是丢能力。
16 个 sheet 清单与全部实测基线记在 Task 25 正文的阻塞块里，前置立项可直接取用。

**用户裁决方案 B（先补齐再删）**：收敛方向「同一前缀只留一套实现」不变，但执行前置未满足。
后续工作「16 个 `X-3` 调整分录接入专属 router / catalog」**单独立项**，不在本 spec 半径内。
待能力等价经实证确认后，回到本任务执行删除并按阻塞块里记录的数字下调基线。

**`## Task Dependency Graph` 的 wave 7（`tasks: ["25"]`）现为阻塞态。**
JSON 结构**未改动**（wave 7 仍在图里、仍只含 Task 25），阻塞状态仅由本 Notes 小节与
Task 25 正文的阻塞块说明 —— 依赖图描述的是任务拓扑，不承载执行态。

**另留两条方法论**（详证见 Task 25 阻塞块）：①判两种 URL 形态时不得假定同构（初版探针用
`endswith` 判形态 B 报了 57 个假阻塞）②「未注册」≠「可删」，`_h5`/`_h7`/`_l1`/`_l3`/`_l4`/`_l5`/`_n4`
这 7 个同样未 `include_router` 但被 catalog 声明、adapter 直调闭包，是活代码。
