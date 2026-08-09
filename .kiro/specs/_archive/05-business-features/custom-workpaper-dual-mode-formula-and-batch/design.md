# Design Document

## Overview

本设计把自定义底稿从「只读空壳」改造为「xlsx 权威 + HTML 投影可编辑 + 双模式 + 可导出 + 可批量」的完整链路。

### 核心口径（用户 2026-08-06 裁决）

**xlsx 文件是唯一权威，`parsed_data.html_data[sheet]` 是它的投影。**

这与平台既有双模式（N1/N2/F2/I1/G14 等）的口径**有意不同**，必须显式登记理由：

| | 标准循环底稿 | 自定义底稿（本 spec） |
|---|---|---|
| HTML 侧数据 | 结构化表单字段（`checklist_responses`，字段有确定审计语义） | 自由网格单元格（无字段语义） |
| OO 侧数据 | xlsx 文件本体 | xlsx 文件本体 |
| 两侧关系 | **各自独立**，切回 HTML 靠 `reloadAll()` 重拉表单值 | **同一批单元格**，必须同源 |
| 权威 | HTML 侧（表单是审计结论载体） | **xlsx** |

标准循环能「两侧独立」是因为 HTML 表单与 xlsx 网格编的是不同东西（表单字段 vs 模板格）。自定义底稿两侧编的是同一批格，若照抄「各自独立」，用户在 OO 改完切回 HTML 看到旧值 = 数据打架。

### 三条链路的当前断点与修法

```
① 可见性链路（W1）✅ 已交付（2026-08-06，62 例守卫全绿）
   create_custom_workpaper ──✗ 不调 populate_parsed_data──→ parsed_data 为空
   write_cell_to_parsed_data ──✗ 只写 cells 不写 max_row──→ hasData 恒 false
   修法：建底稿时投影一次；投影层统一维护 max_row/max_col
   🔴 遗留：**存量**自定义底稿（parsed_data 已为空）需 render 时补齐 → Property 22 / Task 27

② 编辑链路（W2/W3）
   GtGridSheet ──强制只读（40+ 只读消费方，不改它）──→ 新建可编辑网格
   HTML 编辑 ──✗ 无写回──→ 新端点 PUT /custom-cells → openpyxl 写 xlsx → 重投影
   OO 编辑 ──✓ 已有 WOPI+forcesave──→ 回调后重投影（新增挂载点）

③ 导出链路（W5）
   export-xlsx ──✗ load_schema 500──→ custom 分支直接下发 xlsx 本体
   determine_export_format ──✗ "custom" 无映射──→ 归入 xlsx
```

#### 🔴 导出有**两条**独立路径，只改一条等于没修（2026-08-06 实证，立项漏登记）

| 路径 | 入口 | 现状对 custom |
|---|---|---|
| ① `POST /api/workpapers/{wp_id}/export-xlsx` | `wp_xlsx_export.py:41` | 第一步 `load_schema`（L80）→ `FileNotFoundError` → **500** |
| ② `WpExportEngine.export_single`（`export_engine.py:82`）→ `_export_xlsx`（`:438`） | `wp_export_import_router.py`（单份 + 批量两处调用） | `except (TemplateNotFoundError, Exception)`（`:460`）→ **回退空白 workbook**，只 WARNING |

路径 ② 更隐蔽：它**不报错**，用户拿到一个「只有 wp_code 当 sheet 名的空白 xlsx」并以为导出成功
（`except (TemplateNotFoundError, Exception)` 里 `Exception` 已覆盖前者，写法冗余但行为是「吞掉一切」）。
且它是**归档 / 批量导出**的入口 ⇒ 自定义底稿进归档包会是空表。
⇒ Task 17 必须同时分流两条路径，Task 18 的守卫必须**分别**断言（R7.9~7.11）。

#### 🔴 `determine_export_format` 对 `"custom"` 是「隐式兼容」不是「无映射」

实测它对未登记类型走最后一条 `return "xlsx"`，故 custom **当前结果已经是正确的** ——
加进 `_XLSX_TYPES` 是「把对的结果从默认兼容变成显式声明」（防将来默认改 docx 时静默变向），
**不是修一个当前可见的 bug**。⇒ 守卫不得拿「导出格式为 xlsx」当判据（变异后仍绿），
必须直接断言 `"custom" in _XLSX_TYPES`，否则该守卫是空转的。
同族：`backend/tests/test_pbt_export_format.py` 有自己的 `XLSX_TYPES` 副本清单，
改 `_XLSX_TYPES` 后要同步它（否则那份 PBT 的「已知类型」集合与生产不一致）。

### 与 `formula-management-runtime-closure` 的边界

两 spec 同时在跑，交集在公式。**边界按「存储/引擎 vs 选址/可见」切分**：

| 事项 | 归属 |
|---|---|
| `COLUMN_ALIASES` 补键、消除静默回退 | formula-management-runtime-closure R3 |
| `wp_formula` ↔ `parsed_data['user_formulas']` 存储收敛 | formula-management-runtime-closure R4 |
| 两份 `WP()` 实现一致性守卫 | formula-management-runtime-closure R5 |
| 三类型执行链接通、`cross_check_results` 落库 | formula-management-runtime-closure R6 |
| `apiPaths` 收敛公式端点 | formula-management-runtime-closure R7 |
| **自定义底稿公式选址列表可用（cells 非空）** | **本 spec R4**（由 W1 投影产出） |
| **公式求值结果双写 xlsx + 投影** | **本 spec R4**（xlsx 权威的必然要求） |
| **自定义底稿公式清单展示与删除** | **本 spec R4** |

本 spec **不改** `formula_engine.py` / `prefill_engine.py` / `wp_formula_service.save` 的求值与存储逻辑，只在 `save_formula` 的**回填段**追加 xlsx 写入（加法式，一个函数调用）。

## Architecture

### 组件全景

🔴 **命名以磁盘既有事实为准**（2026-08-06 实证：Wave 1 已交付，模块名为
`custom_workpaper_projection.py`）。本节名字与 tasks.md 逐字一致，两处不得再分叉。

```
┌─ 前端 ────────────────────────────────────────────────────────┐
│ GtCustomWpEditor.vue（宿主，改造）                             │
│  ├─ el-segmented（:model-value/@change，禁 v-model）           │
│  ├─ [html 模式] custom/GtCustomGridSheet.vue（新建，可编辑网格）│
│  ├─ [oo 模式]   GtOnlyOfficeSheet.vue（既有，@fallback）        │
│  ├─ custom/GtCustomWpFormulaList.vue（新建，公式清单）          │
│  └─ FormulaEditDialog.vue（既有）                              │
│                                                                │
│ custom/customWpCellEdit.ts（✅ 已交付，纯函数层）               │
│  ├─ normalizeCellRef / parseCellRef / colLetterToIndex         │
│  ├─ colIndexToLetter / MAX_CELL_UPDATES                        │
│  ├─ buildCellPatch（脏格收集，去重，返回键 `updates`）          │
│  └─ gridHasContent / classifyEmptyGrid（三态空网格成因）        │
│                                                                │
│ custom/GtCustomWpBatchDialog.vue（新建，批量创建）              │
│ custom/customWpBatchParse.ts（新建，纯函数解析+校验）           │
└────────────────────────────────────────────────────────────────┘
                              │
┌─ 后端 ────────────────────────────────────────────────────────┐
│ services/custom_workpaper_projection.py（✅ 已交付，投影单一入口）│
│  ├─ project_custom_workpaper(file_path, sheet_name) -> dict    │
│  ├─ write_projection_to_parsed_data(wp, sheet_name, grid)      │
│  ├─ refresh_custom_projection(wp, sheet_name) -> dict          │
│  ├─ write_cells_to_xlsx(file_path, sheet_name, updates) -> int │
│  ├─ ensure_grid_bounds(grid) -> dict   # max_row/max_col 兜底  │
│  └─ parse_cell_ref / normalize_cell_ref / col_letter_to_index  │
│                                                                │
│ routers/custom_workpaper_cells.py（新建）                      │
│  ├─ PUT  /api/workpapers/{wp_id}/custom-cells                  │
│  └─ POST /api/workpapers/{wp_id}/custom-refresh-projection     │
│                                                                │
│ routers/wp_template.py（改造）                                  │
│  ├─ create_custom_workpaper       → ✅ 已接投影                 │
│  ├─ _create_one_custom_workpaper（抽共享，单条与批量共用）      │
│  ├─ create_custom_workpapers_batch（新增，per-item savepoint）  │
│  └─ preview_custom_workpapers_batch（新增，只读预览）           │
│                                                                │
│ services/wp_parsed_data_service.write_cell_to_parsed_data       │
│  └─ 改造：调 ensure_grid_bounds 维护 max_row/max_col            │
│                                                                │
│ routers/wp_formula.save_formula（改造，加法式）                 │
│  └─ 求值回填后：write_cells_to_xlsx（仅 custom 底稿）           │
│                                                                │
│ onlyoffice_callback_service（改造，加法式）                     │
│  └─ forcesave 落盘后：custom 底稿重投影                         │
│                                                                │
│ wp_render_config.py（改造）                                     │
│  └─ "custom" 加入 _ONLYOFFICE_HTML_WHITELIST                   │
│                                                                │
│ wp_export/export_engine.determine_export_format（改造）         │
│  └─ _XLSX_TYPES 加 "custom"                                    │
│                                                                │
│ routers/wp_xlsx_export.py（改造）                              │
│  └─ custom 分支：跳过 load_schema，直下 xlsx 本体               │
└────────────────────────────────────────────────────────────────┘
```

### 数据流：xlsx 权威 + 单向投影

```
                    ┌──────────────┐
                    │  xlsx 文件   │ ◄── 唯一权威
                    └──────┬───────┘
                           │ project_custom_workpaper（✅ 已交付，恒等坐标）
                           │ 🔴 不用 extract_grid（它重编行号，见下）
                           ▼
              ┌────────────────────────────┐
              │ parsed_data.html_data[wp]  │ ◄── 投影（可重建、可丢弃）
              │  {cells, max_row, max_col, │
              │   col_widths, merged_cells,│
              │   header_rows}             │
              └────────────┬───────────────┘
                           │ render-config
                           ▼
                    GtCustomGridSheet

三个写入点全部「先写 xlsx，再重投影」：
  ① HTML 格编辑 → PUT /custom-cells → openpyxl → 重投影
  ② 公式求值   → save_formula 回填 → openpyxl → 重投影
  ③ OO 保存    → forcesave 落盘   → （已是 xlsx）→ 重投影
```

**关键不变式**：投影永不作为权威被单独修改。任何「只改投影不改 xlsx」的路径都是缺陷 —— 这正是现状 `write_cell_to_parsed_data` 的问题（它只写投影）。

### 双模式选型

用**参数化工厂** `composables/factories/createDualMode.ts`（取值 `'html' | 'onlyoffice'`）。

🔴 **不用 `useD1DualMode`**：它的取值是 `'html' | 'oo'`，与其余 40+ 处的 `'onlyoffice'` 不统一，选错会与既有 localStorage 持久化值冲突（用户在别的底稿存过 `'onlyoffice'`，到这里读不出来）。

`persistKey` 用 `custom-wp-mode:` + wpId。`onSwitchToHtml` 回调里调重投影 + reload —— 这是 OO 改动能被 HTML 侧看见的唯一通路。

### 批量创建：预览-确认两段式

```
输入（两形态）
 ├─ 粘贴文本 ──┐
 └─ 上传 xlsx ─┴──→ POST /create-custom-batch/preview（只读，不写库）
                        │
                        ├─ 逐行解析 + 校验（编号格式/重号/表内重复/名称空）
                        ├─ 返回 {rows: [{wp_code, wp_name, cycle, status, reason}]}
                        │        status ∈ ok | duplicate_db | duplicate_input | invalid
                        ▼
                   前端预览表格（可逐行剔除/改名）
                        │ 用户确认
                        ▼
              POST /create-custom-batch（items 形态，per-item savepoint）
                        │
                        └─ 返回 {created, skipped, failures[]}
```

**为什么必须预览**：批量建 50 条时若中途撞重号，用户得知道是哪几条、为什么。这与 memory 记的「重复抽凭必须弹窗要求审计师手动确认」同源 —— 系统能自动处置但涉及判断的场景一律留痕不静默。

**per-item savepoint** 复用 `generate_from_codes` 已有范式（`async with db.begin_nested()` 逐条 + `try/except` 记 failures 后继续，最外层一次 commit）。

## Components and Interfaces

### 1. `backend/app/services/custom_workpaper_projection.py`（✅ Wave 1 已交付，投影单一真源）

**交付状态（2026-08-06 实证）**：模块已存在（14.8 KB），`backend/tests/test_custom_workpaper_projection.py`
62 例全绿。函数签名以磁盘为准，本节据实校正（原设计稿写的 `project_identity_grid` /
`custom_wp_projection.py` 从未存在）。

```python
def project_custom_workpaper(file_path: str | Path | None, sheet_name: str) -> dict:
    """从 xlsx 提取**恒等坐标**网格（纯函数，无 DB）。

    🔴 为什么不复用 `extract_grid`（立项假设已被实证推翻，2026-08-06 探针）：
      ① 它 `row_offset = data_start_row - 1` 重编行号 —— xlsx `B6` 投影成 `B2`。
         自定义底稿要「读投影 → 编辑 → 写回 xlsx」，坐标一位移，写回就写到别的格。
      ② `data_start_row` 是启发式（首个含「项目」/「序号」的行），用户录入过程中会
         跳变 ⇒ 同一投影坐标在两次加载间指向不同 xlsx 行。
      ③ 它裁空列/裁尾部空行 —— 自定义底稿是自由网格，用户可能先在 D10 落一个值。
      ④ 空/失败路径只返 5 键（无 `header_rows`），键集守卫在 fail-open 路径必红。
    `extract_grid` 有 11 个既有调用方依赖其现行为，**保持零改动**。

    本函数：坐标恒等（键 == openpyxl coordinate）、不剥表头、不重编号、不裁列行。
    复用 `extract_grid_from_sheet` 的样式规则（bold/font_size/font_color/align/
    numeric）—— 抽 `_cell_style(cell)` 共享，不抄第二份。

    返回六键恒定：{cells, max_row, max_col, col_widths, merged_cells, header_rows}。
    文件不存在/sheet 缺失/解析失败 → 返回**六键齐备的空网格**（fail-open，
    🔴 不是 5 键、也不是 None，否则键集守卫在该路径打红）。
    """

def write_projection_to_parsed_data(wp, sheet_name: str, grid: dict) -> None:
    """整块替换 parsed_data['html_data'][sheet_name] 并 flag_modified。

    🔴 整块替换而非合并：投影是 xlsx 的派生物，合并会留下 xlsx 里已删除的残留格。
    🔴 必须 flag_modified —— JSONB 列就地改嵌套 dict 不标脏则 UPDATE 不发出。
    """

def refresh_custom_projection(wp, sheet_name: str) -> dict:
    """从 xlsx 重投影并写回 parsed_data（三个写入点共用的收口动作）。"""

def ensure_grid_bounds(grid: dict) -> dict:
    """按 cells 的键补齐 max_row / max_col（就地不修改入参，返回新 dict）。

    🔴 为什么必需：GtGridSheet.hasData 要求 maxRow > 0，只写 cells 的路径
    （write_cell_to_parsed_data）会让网格恒显示「暂无内容」。
    """

def write_cells_to_xlsx(
    file_path: str | Path, sheet_name: str, updates: dict[str, Any]
) -> int:
    """把单元格补丁写入 xlsx（openpyxl，keep_vba=False）。返回实际写入格数。

    updates: {"B5": 123.45, "C7": "文字"}
    🔴 sheet 不存在**抛 KeyError 不创建**（自定义底稿 sheet 名恒等于 wp_code，
       对不上说明上游有 bug，静默创建会掩盖）。
    🔴 写盘失败**抛异常不 fail-open**（xlsx 是权威，写不进去就不能报成功）。
    写入前后不动其他格与样式。
    """

def parse_cell_ref(cell_ref: str) -> tuple[int, int]      # "B5" → (5, 2)；非法 → (0, 0)
def normalize_cell_ref(cell_ref: str) -> str | None       # "$b$5" → "B5"；非法 → None
def col_letter_to_index(letters: str) -> int              # "AA" → 27；非法 → 0
```

🔴 **前后端各有一份单元格引用解析**（后端 `parse_cell_ref` / 前端 `customWpCellEdit`），
这是有意的（前端要在本地做即时校验，不能每敲一格都往后端跑）。
守卫必须做**跨前后端交叉锁死**：对同一组样本两侧结果一致（Property 4）。

**为什么单独建模块**：三个写入点（HTML 编辑 / 公式回填 / OO 回调）都要用它，放在任一 router 里都会造成另两处 import 环。

### 2. `backend/app/routers/custom_workpaper_cells.py`（新建）

```
PUT /api/workpapers/{wp_id}/custom-cells
body: {
  sheet_name: str,
  updates: {"B5": <value>, ...},   # 最多 500 格/次（MAX_CELL_UPDATES）
}
→ 200 {updated: int, grid: {...}}   # grid = 重投影结果，前端直接替换本地状态
→ 403 底稿已归档/只读
→ 404 底稿不存在 / xlsx 文件缺失
→ 409 底稿非 custom 类型（防误用到标准底稿上）
→ 422 单元格引用非法 / updates 超限（含 `overflow` 标记）

POST /api/workpapers/{wp_id}/custom-refresh-projection
body: {sheet_name?: str}            # 缺省取 wp_code
→ 200 {grid: {...}}
→ 409 / 404 同上
```

**409 而非静默放行**：标准底稿的 HTML 侧是结构化表单，往它的 xlsx 直写格会绕过审计语义校验。
🔴 错误码以本节为准（tasks.md 原写 400，已统一为 409）。

### 3. `custom/GtCustomGridSheet.vue`（新建）

不改 `GtGridSheet.vue`（40+ 只读消费方共享件，改它半径过大）。新组件复用其视觉规则（合并格 / 粘顶表头 / 冻结首列 / 金额格式 / 分组表头着色），追加：

- 单击选中格（选中态传给 FormulaEditDialog 作目标格）
- 双击进入编辑（`el-input`，`@input` 回写本地态 —— 🔴 只绑 `@change` 会被 EP 在 nextTick 重置回 `modelValue`，抹掉用户键入）
- 公式格只读 + `ƒ` 角标 + tooltip 展示表达式（`formula_hint` 既有机制）
- 脏格收集 → 800ms 防抖 → `PUT /custom-cells`（body 键 `updates`）→ 用返回的 grid 替换本地态
- 保存失败 `ElMessage.error` + 保留脏格（🔴 纯 `catch {}` 会让数据丢了没人发现）

金额显示走 `displayPrefs.fmtAmount`（🔴 store 成员，`inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()` 在 setup 顶层取，写成模块级命名导入会整页崩）。

### 4. `custom/customWpCellEdit.ts`（新建，纯函数）

```typescript
export function normalizeCellRef(raw: string): string | null
  // "b5" → "B5"；"$B$5" → "B5"；"B" / "5" / "" → null

export function parseCellRef(ref: string): { row: number; col: number } | null
  // "B5" → {row: 5, col: 2}（1-based，与 openpyxl 一致）

export function colLetterToIndex(letters: string): number
  // "A"→1, "Z"→26, "AA"→27

export function buildCellPatch(
  dirty: Map<string, unknown>, opts?: { maxCells?: number }
): { updates: Record<string, unknown>; overflow: boolean; invalid: string[] }
  // 归一化键 + 去重（后写覆盖先写）+ 超限标记
```

零 Vue 依赖，便于 PBT。

### 5. `custom/customWpBatchParse.ts`（新建，纯函数）

```typescript
export interface BatchRowInput { wp_code: string; wp_name: string; audit_cycle?: string }
export type BatchRowStatus = 'ok' | 'duplicate_input' | 'duplicate_db' | 'invalid'
export interface BatchRowChecked extends BatchRowInput {
  status: BatchRowStatus
  reason?: string
  audit_cycle: string   // 缺省时由 wp_code 首字母派生
}

export function parseTextList(text: string): BatchRowInput[]
  // 分隔符：Tab / 逗号 / 全角逗号 / 连续空格（≥2）；跳过空行与表头行

export function parseExcelRows(rows: unknown[][]): BatchRowInput[]
  // 识别表头行（含「编号」「名称」字样）并按列名映射；无表头时按位置
  // 列名归一化后匹配（去空格 + 全角→半角），识别失败给明确错误不静默跳整列

export function validateItems(
  rows: BatchRowInput[], existingCodes?: Iterable<string>
): BatchRowChecked[]
  // 编号格式（^[A-Za-z][A-Za-z0-9-]{0,31}$）+ 名称非空 + 输入内重号
  // existingCodes 由后端 preview 端点提供；缺省时不产出 duplicate_db
```

**为什么解析放前端**：粘贴文本的分隔符歧义要即时反馈；上传 xlsx 由前端 SheetJS 读成
二维数组后走同一 `parseExcelRows`。两条路最终汇成同一 `BatchRowInput[]` 交 preview 端点，
由后端补 `duplicate_db`（库内重号只有后端知道）。

### 6. `custom/GtCustomWpFormulaList.vue`（新建）

`GET /api/workpapers/{wp_id}/formulas`（既有端点，返回键 **`items`** 不是 `formulas`）→ 表格展示 `target_cell` / 表达式 / 中文类型标签 / `last_computed_at` / 删除。

中文标签复用 `formulaEngineInventory.FORMULA_TYPE_LABEL`（🔴 单一真源，不新建第二份）。

**删除的完整语义（R6.4）**：删公式后该格必须恢复可手工编辑，故不能只删 `wp_formula` 行 ——
xlsx 里那格还留着上次求值结果。删除流程 = `DELETE /formulas/{id}`（既有端点）
→ 若底稿为 custom 则 `write_cells_to_xlsx(..., {target_cell: None})` 清格 → 重投影。
🔴 加法式门控（仅 custom），非 custom 底稿的 `delete_formula` 路径逐字节不变。

### 7. 批量端点（`wp_template.py` 新增两个）

```
POST /api/projects/{pid}/working-papers/create-custom-batch/preview
body: {items: BatchRowInput[]}
→ 200 {rows: BatchRowChecked[]（含 duplicate_db）, summary: {ok, invalid, duplicate}}
（🔴 只读，不写库；库内已存在编号由本端点标 duplicate_db）

POST /api/projects/{pid}/working-papers/create-custom-batch
body: {items: [{wp_code, wp_name, audit_cycle?}], year?}
→ 200 {created, skipped, failed, results: [{wp_code, status, reason?}]}
   status ∈ created | skipped | failed（三态可分）
```

🔴 **既有单条端点 `POST .../create-custom` 保留不动**：`CreateCustomWorkpaperRequest{wp_code, wp_name, ...}`
有前端调用方。批量另开路径（`create-custom-batch`）而非在单条端点加 `items` 键 ——
后者会让单条端点的请求 schema 变成联合类型，既有调用方的 422 行为可能改变。
**两条路径共用底层 `_create_one_custom_workpaper`**（R8.7/R8.9：表头填充 / dataset 绑定 /
`parsed_data` 投影三件不得遗漏，也不得出现两份创建逻辑各自漂移）。

## Data Models

### 无 DB 迁移

本 spec **不新增表、不加列**。`wp_formula`（V052/V100/V104）已够用。

### `parsed_data.html_data[sheet_name]` 投影结构（既有键集，不变更）

| 键 | 类型 | 来源 | 说明 |
|---|---|---|---|
🔴 键名与 `GtGridSheet` 消费键一致（这是复用其视觉规则的前提），但**值的坐标语义不同** ——
自定义底稿是恒等坐标（投影 `B6` ≡ xlsx `B6`），标准底稿走 `extract_grid` 是重编号坐标。

| 键 | 类型 | 来源 | 说明 |
|---|---|---|---|
| `cells` | `dict[str, dict]` | `project_custom_workpaper` | `{"B6": {v, r, c, style}}`，`r`/`c` 为 **xlsx 真实 1-based 行列**；公式格另带 `formula` 原文 |
| `max_row` | `int` | `project_custom_workpaper` / `ensure_grid_bounds` | 🔴 必须 > 0 否则 `hasData` 判无内容 |
| `max_col` | `int` | 同上 | |
| `col_widths` | `dict[str, number]` | `project_custom_workpaper` | |
| `merged_cells` | `list[dict]` | `project_custom_workpaper` | 🔴 不做行偏移（恒等坐标） |
| `header_rows` | `int` | `project_custom_workpaper` | 恒 `0`：自定义底稿不剥表头，标准表头本身就是可编辑内容 |

🔴 **这六键在任何路径都必须齐备**（含 fail-open 空网格），否则「投影键集 ⊇ 消费键集」的
守卫在异常路径必红 —— `extract_grid` 的空路径只返 5 键，这正是不能直接复用它的第二个理由。

🔴 **不产出 `column_meta`**（2026-08-06 实证校正）：`GtGridSheet` 实际消费的
`htmlData.*` 键恰为上表六个，`column_meta` 只出现在其类型声明里、不参与渲染分支；
而自定义底稿无固定列语义，产出 `_COL_SEMANTICS` 推断结果只会误导。
原设计稿要求「六键 + `column_meta` 齐备」是错的 —— 按它写守卫会把已交付的正确实现打红。

### `wp_formula` 相关字段（既有，只读引用）

`sheet_name` + `target_cell` 唯一索引 `uq_wp_formula_wp_sheet_cell` ⇒ 一格一公式、同键覆盖。`formula_type ∈ auto_calc | logic_check | reasonability`。

### 批量导入 xlsx 格式（新增约定）

| 列 | 必填 | 说明 |
|---|---|---|
| A 底稿编号 | ✅ | `^[A-Za-z][A-Za-z0-9-]{0,31}$` |
| B 底稿名称 | ✅ | 非空 |
| C 审计循环 | ❌ | 缺省取编号首字母 |

首行为表头（按内容识别，含「编号」「名称」字样即跳过）。模板下载端点复用既有 blob 下载范式。

## Error Handling

| 场景 | 处置 | 理由 |
|---|---|---|
| xlsx 文件缺失/损坏 | 投影返 `None`，render 下发空 grid + 前端提示「底稿文件异常，请重新上传」 | fail-open 不阻断整个 render；但**必须有可见提示**，否则与「空底稿」不可区分 |
| `PUT /custom-cells` 写 xlsx 失败 | 500 + 前端保留脏格 + `ElMessage.error` | 静默丢弃 = 用户以为存了 |
| OO 不健康 | `GtOnlyOfficeSheet` 自身 `@fallback` → 回 html | 既有机制 |
| OO 保存后重投影失败 | 记 WARNING，投影保持旧值 | xlsx 已是权威且已落盘，下次打开会重新投影 |
| 公式求值成功但 xlsx 写入失败 | 回滚投影写入 + 返回告警 | 🔴 若只回滚 xlsx 不回滚投影，两者分叉，违反权威口径 |
| 批量中单条失败 | savepoint 回滚该条 + 计入 `failures` + 继续 | `generate_from_codes` 既有范式 |
| 批量全部失败 | 200 + `created=0` + `failures` 全量 | 不用 4xx（部分成功语义无法用状态码表达） |
| 单元格引用非法 | 422 + 指明是哪个键 | |
| `updates` 超 500 格 | 422 + `overflow` 标记 | 防单次请求写爆 xlsx |
| 非 custom 底稿调 `/custom-cells` | 409 | 见 §Components 2 |

## Testing Strategy

🔴 **文件名以 tasks.md 与磁盘既有事实为准**（本表原写的 `test_custom_wp_*.py` /
`customWpDualModeWiring.spec.ts` / `customWpGridEditorContract.spec.ts` 从未存在，
照它建会与已交付的守卫并存成两套）。

| 层 | 文件 | 覆盖 | 状态 |
|---|---|---|---|
| 后端单测 | `backend/tests/test_custom_workpaper_projection.py` | 投影键集完整性 / `ensure_grid_bounds` / xlsx 写入不破坏其他格 / fail-open | ✅ 62 例 |
| 后端单测 | `backend/tests/test_custom_workpaper_cells.py` | 端点顺序 / 409·403·404·422 四闸 / 重投影返回 / 存量补齐幂等 / 跨前后端 `hasData` 锁死 | ✅ 43 例 |
| 后端单测 | `backend/tests/test_custom_workpaper_batch.py` | per-item savepoint 隔离 / preview 只读 / 单条形态零回归 / 共用底层函数 | Task 22 |
| 后端单测 | `backend/tests/test_custom_workpaper_export.py` | 两条路径各自分流 / 不调 `load_schema` / 往返可逆 / `_XLSX_TYPES` 显式 | Task 18 |
| 前端单测 | `custom/__tests__/customGridEditing.spec.ts` | 纯函数 PBT（往返可逆 / 补丁去重 / 超限）+ 编辑交互 + Property 23 跨前后端解析锁死 | Task 8 |
| 前端单测 | `custom/__tests__/customWpBatchParse.spec.ts` | 4 种分隔符 / 表头跳过 / 重号 / PBT | Task 22 |
| 前端守卫 | `custom/__tests__/customDualModeWiring.spec.ts` | 🔴 用 `createDualMode` 不用 `useD1DualMode` + `el-segmented` 用 `:model-value` 不用 `v-model` + `@fallback` 已绑 | Task 11 |
| 前端守卫 | `custom/__tests__/customFormulaWiring.spec.ts` | 清单读 `items` 键 / 类型标签单一真源 / 选址 label 有语义 / `evaluated_value` 已读 | Task 15 |
| 前端守卫 | 并入 `customGridEditing.spec.ts` | 编辑绑 `@input` 不只绑 `@change` / 保存失败有 `ElMessage.error` / `GtGridSheet.vue` 未被改 | Task 8 |

**变异检验必做**（memory 铁律）：每个守卫写完真改一字看是否变红；打红的 message 必须是预期那一条（前置校验先触发会掩盖真正要验的断言）。

## Correctness Properties

### Property 1: xlsx 权威不变式
任何单元格写入路径完成后，`parsed_data.html_data[sheet].cells[ref]` 的值 SHALL 等于 xlsx 文件中同一格的值。不存在只写投影不写 xlsx 的生产路径。

**Validates: Requirements 1.1, 1.3, 1.4, 5.4**

### Property 2: 投影键集完整性
`project_custom_workpaper` 产出的 grid SHALL 包含 `cells` / `max_row` / `max_col` / `col_widths` / `merged_cells` / `header_rows` 六键；当 `cells` 非空时 `max_row > 0` 且 `max_col > 0`。

**Validates: Requirements 1.2, 1.5, 1.7**

### Property 3: `ensure_grid_bounds` 幂等且单调
对同一 grid 重复调用 `ensure_grid_bounds` 结果不变；补齐后的 `max_row` 不小于 `cells` 中任一格的行号，`max_col` 同理。

**Validates: Requirements 1.2, 2.3, 2.5**

### Property 4: 单元格引用往返可逆
对任意合法单元格引用 `r`，`parseCellRef(normalizeCellRef(r))` SHALL 产出与 openpyxl 一致的 1-based 行列；非法引用 SHALL 返回 `null` 而非抛错或返回 0。

**Validates: Requirements 1.3, 3.2**

### Property 5: 脏格补丁去重与超限
`buildCellPatch` SHALL 对同一格的多次修改保留最后一次；键归一化后不得出现重复键；超过上限时 SHALL 置 `overflow` 而非静默截断。

**Validates: Requirements 3.2, 3.5**

### Property 6: 双模式取值域一致性
自定义底稿双模式的取值 SHALL 为 `'html' | 'onlyoffice'`，与平台 40+ 处一致；源码中不得引用 `useD1DualMode`（其取值为 `'oo'`）。

**Validates: Requirements 4.2, 4.9**

### Property 7: OO 编辑可被 HTML 侧看见
OO 模式保存（forcesave 落盘）后切回 HTML 模式，HTML 网格 SHALL 显示 OO 中修改后的值。

**Validates: Requirements 4.5, 4.6**

### Property 8: 公式结果双写原子性
公式求值成功后，xlsx 与投影 SHALL 同时更新；若 xlsx 写入失败，投影 SHALL 不保留该值（回滚），并返回告警。

**Validates: Requirements 5.4, 5.6**

### Property 9: 公式选址列表非空性
对已完成投影的自定义底稿，`FormulaEditDialog` 的目标格选址列表 SHALL 非空。

**Validates: Requirements 5.1, 5.2**

### Property 10: 导出不依赖 render schema
自定义底稿导出 SHALL 不调用 `load_schema`，不因缺少 yaml 返回 500；产出文件 SHALL 可被 openpyxl 打开且包含全部单元格。

**Validates: Requirements 7.1, 7.2, 7.3**

### Property 11: 批量失败隔离与预览只读
批量创建中单条失败 SHALL 不影响其他条目落库；`preview` 端点调用前后 `wp_index` / `working_paper` 行数 SHALL 不变。

**Validates: Requirements 8.4, 8.6, 8.7**

### Property 12: 零回归
标准底稿的 render-config 输出、既有单条 `create-custom` 响应形状、`GtGridSheet.vue` 内容 SHALL 逐字不变；`formula_engine._REGISTRY` 与 `prefill_engine._FORMULA_RESOLVERS` 键集不变；`wp_grid_extract.extract_grid` / `extract_grid_from_sheet` SHALL 逐字节不变（11 个既有调用方依赖其重编号行为）。

**Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5**

### Property 13: 存量底稿投影补齐
对 `parsed_data` 为空的既有自定义底稿，render 时 SHALL 按 xlsx 投影补齐，不要求用户重建底稿；补齐 SHALL 幂等（重复 render 不产生差异）。

**Validates: Requirements 2.1, 2.6**

### Property 14: 公式格不可手工覆盖
存在对应 `wp_formula` 记录的单元格 SHALL 不可进入编辑态；该判定 SHALL 由 `formulaCells` 数据驱动而非 CSS，且底稿只读态下全部格不可编辑。

**Validates: Requirements 3.4, 3.5**

### Property 15: 公式清单键与标签单一真源
公式清单 SHALL 读 `GET /api/workpapers/{wp_id}/formulas` 响应的 `items` 键（非 `formulas`）；类型中文标签 SHALL 取自 `formulaEngineInventory.FORMULA_TYPE_LABEL`，源码中不得出现第二份标签映射；端点路径 SHALL 取自 `apiPaths`。

**Validates: Requirements 6.1, 6.5, 6.6, 6.7, 6.8**

### Property 16: 不侵入并发 spec 范围
本 spec 的改动集合 SHALL 不含 `formula_engine.py` 的 `COLUMN_ALIASES` 与求值回退、`wp_user_formulas.py` 的存储落点、`wp_formula_service.save` 的存储语义、`useFormulaStatus.ts`；新增 `apiPaths` 键 SHALL 与对侧 spec 互不重叠。

**Validates: Requirements 9.1, 9.2, 9.3, 9.5, 9.6**

### Property 17: 实测数据可复原
真实库验收脚本 `--apply` 后的复原 SHALL 使 `parsed_data` 的 `jsonb_typeof` / `md5(col::text)` / `length` 三项与基线逐一相等；实测创建的自定义底稿 SHALL 被软删且其 xlsx 文件被删除。

**Validates: Requirements 12.1, 12.4, 12.5**

### Property 18: 两条导出路径都被分流
自定义底稿经 `POST /export-xlsx` **与** `WpExportEngine.export_single` 两条路径导出，SHALL 都产出含真实单元格的 xlsx；路径 ② 的 `except (TemplateNotFoundError, Exception)` 空白 workbook 兜底 SHALL NOT 被自定义底稿触发（分流必须在兜底之前）。守卫 SHALL 对两条路径**各有一条**断言，构造「只分流其中一条」的替身时必须打红。

**Validates: Requirements 7.3, 7.4, 7.9, 7.10**

### Property 19: 导出格式判定显式
`"custom" in _XLSX_TYPES` SHALL 成立；`backend/tests/test_pbt_export_format.py` 自带的 `XLSX_TYPES` 副本 SHALL 同步含 `"custom"`。🔴 该判据只能靠集合成员断言 —— `determine_export_format` 对未登记类型走默认 `return "xlsx"`，故拿返回值当判据的守卫在变异后仍绿（空转）。

**Validates: Requirements 7.7, 7.8**

### Property 20: 导出往返可逆
导出产出的字节流 SHALL 可被 `openpyxl.load_workbook` 打开；再经 `project_custom_workpaper` 读回的 `cells` SHALL 逐格覆盖导出前投影的 `cells`（键与值相等）。

**Validates: Requirements 7.9**

### Property 21: 删除公式恢复可编辑
删除自定义底稿的一条公式后，该目标格 SHALL 从 xlsx 与投影**双方**清除求值结果，并恢复可手工编辑；非 custom 底稿的删除路径 SHALL 逐字节不变。

**Validates: Requirements 6.4, 3.4**

### Property 22: 存量底稿 render 时补齐
对 `parsed_data` 为空（或该 sheet 键缺失）的既有自定义底稿，render-config SHALL 按 xlsx 投影补齐并下发非空 grid；补齐 SHALL 幂等且**不得**污染非 custom 底稿的 render 路径。

**Validates: Requirements 2.6, 11.1**

### Property 23: 前后端单元格解析一致
对同一组样本（含 `$B$5` / 小写 / 多字母列 / 非法串），前端 `customWpCellEdit.parseCellRef` 与后端 `custom_workpaper_projection.parse_cell_ref` SHALL 给出一致结果（合法者行列相等、非法者两侧都判非法）。

**Validates: Requirements 1.3, 3.2**

## Notes

### 顺带修掉的既有缺陷（非本 spec 主线但同源）

1. **`GtGridSheet` 的 `user_input` tooltip 写「双击编辑」但无实现** + CSS `cursor:text` —— 误导性 UI。本 spec 不改该共享件，改为在 `GtCustomGridSheet` 里真正实现双击编辑；`GtGridSheet` 的误导文案归属另立（R11.2 要求其既有只读消费方行为不变）。

2. **`GtCustomWpEditor.onFormulaSave` 只读 `eval_warnings` 不读 `evaluated_value`** —— 保存后无本地即时反馈。本 spec R4.6 修。

3. **`useFormulaStatus` 请求不存在的端点**（`/api/projects/{pid}/workpapers/{wpId}/formulas`）—— 归 `formula-management-runtime-closure` R1，本 spec 的 `CustomWpFormulaPanel` 直接用正确端点 `GET /api/workpapers/{wp_id}/formulas` 并读 `items` 键。

### 潜伏风险登记

1. **custom 变多 sheet 会被静默改写成 `onlyoffice-sheet`** —— `wp_render_config.py` L873-875 的 E 分支要求 `_is_multi_sheet`，当前 custom 恒单 sheet 故不触发。本 spec 把 `"custom"` 加进 `_ONLYOFFICE_HTML_WHITELIST` 预防（R3.6）。

2. **`strip_standard_header` 把 `header_rows` 硬编码回 1** —— 两级表头 sheet 在 skip>0 时被压成 1。既有遗留，自定义底稿多为单级表头故影响小，不在本 spec 修，登记待办。

3. **两条自定义链路并存不交汇** —— `create-custom`（建 `WpIndex`+`working_paper`+xlsx）vs `custom-with-template`（建 `ProcedureInstance`+`WpIndex` 占位，靠指派时 `ensure_working_paper` 补）。本 spec 只改前者；后者若也要双模式需另立。

### 范围外（明确不做）

- `formula_engine` / `prefill_engine` 的求值逻辑与 `COLUMN_ALIASES`（归 formula-management-runtime-closure）
- `wp_formula` ↔ `parsed_data['user_formulas']` 存储收敛（同上）
- `GtGridSheet.vue` 任何改动（40+ 只读消费方）
- 3 份 DualMode 工厂收敛（半径覆盖 40+ 薄壳，另立）
- 标准底稿的双模式口径变更（它们「两侧独立」是有意设计）
- docx 类自定义底稿（当前 custom 恒 xlsx）
- `custom-with-template` 链路
