# Implementation Plan: 自定义底稿双模式、公式与批量创建

## Overview

按「xlsx 为权威」口径收口自定义底稿（`componentType=custom`）的三条断链：可见性、双模式与编辑、导出；
并新增批量创建（粘贴清单 + Excel 清单双入口）。

**范围红线**：本 spec 不碰 `wp_formula` 存储收敛、不碰 `COLUMN_ALIASES`、不碰求值引擎两条路径的静默回退 ——
那三块归并发 spec `formula-management-runtime-closure`（已有完整三件套）。本 spec 的公式部分只做
「选址列表可用」+「求值结果双写 xlsx 与投影」+「已有公式清单可见」。

**交付状态（2026-08-06 实证复核，勿信复选框以外的记载）**：
Wave 1（Task 1/2/3/4）与 Task 5 **已真实交付**（`custom_workpaper_projection.py` 14.8 KB +
`backend/tests/test_custom_workpaper_projection.py` **62 passed / 0 failed**），
此前 tasks.md 全 `[ ]` 是假红。剩余 Wave 2~7。

**本轮三件套审查修掉的 8 处缺陷**（下个会话不必重查）：
① **design 与 tasks 对同一产物用两套完全不同的名字**（投影模块 / cells router / 可编辑网格 /
批量端点 / 解析函数 / 公式清单组件，逐项分叉）⇒ 照 design 干与照 tasks 干会产出两套文件；
已统一到磁盘既有事实
② **tasks 的 Property 编号自成一套**（其 Property 4 = 网格编辑，而 design Property 4 =
单元格引用往返；且引用了 design 不存在的 Property 18/19）⇒ 已全量重映射到 design 编号，
并给 design 补 Property 18~23
③ **R2.6 无任务覆盖** —— Task 1 只在**新建时**投影，库里既有自定义底稿的 `parsed_data`
已经是空的，不补齐永远看不见 ⇒ 新增 **Task 27**（render 时补齐）
④ **批量预览端点无任务** —— R8.2 要求「不得直接开始创建」、Task 20 的
`validateItems(items, existingCodes)` 却没有 existingCodes 来源 ⇒ 新增 **Task 28**
⑤ **R6.4 只写了「删除按钮」** —— xlsx 权威下只删 `wp_formula` 行会让该格残留上次求值结果，
恢复可编辑后显示旧值 ⇒ 新增 **Task 29**（删除时清 xlsx 格 + 重投影）
⑥ **前端纯函数层 `customWpCellEdit.ts` 无任务**而 design Property 4/5 validate 它
⇒ 并入 Task 7，并加 Property 23 做前后端解析交叉锁死
⑦ **错误码与 body 键分叉**（409 vs 400 / `patches` vs `updates`）⇒ 统一为 409 + `updates`
⑧ **design 要求「六键 + `column_meta` 齐备」是错的** —— `GtGridSheet` 实测只消费六键，
按它写守卫会把已交付的正确实现打红 ⇒ 已改为「不产出 `column_meta`」并写明理由

**开工前必读**：`.kiro/steering/memory.md` 的以下条目与本 spec 直接相关 ——
「Vue 组件传不存在的 prop = 静默失效」/「宿主漏传 prop = 静默锁死」/
「additive 注入即死代码」/「读源码型守卫必先 stripComments」/
「变异检验必须比对失败测试名集合而非退出码」/「`--apply` 被 Ctrl+C 中断但写入已提交」。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "可见性修复（其余全部波次的前置）",
      "tasks": ["1", "2", "3", "4"],
      "rationale": "不修这四项，后面所有功能在界面上都看不见；Task 4 守卫必须先对当前状态打红"
    },
    {
      "wave": 2,
      "name": "投影单一入口与网格可编辑",
      "tasks": ["5", "6", "7", "8", "27"],
      "depends_on": [1],
      "rationale": "投影服务是双模式与编辑的共同前置；可编辑网格必须新建组件不改共享只读件；Task 27 补齐存量底稿（Task 1 只覆盖新建）"
    },
    {
      "wave": 3,
      "name": "双模式接线",
      "tasks": ["9", "10", "11"],
      "depends_on": [2],
      "rationale": "切回 HTML 时要调 Wave 2 的投影刷新，故必须在其之后"
    },
    {
      "wave": 4,
      "name": "公式可用性（选址 + 结果双写 + 清单 + 删除清格）",
      "tasks": ["12", "13", "14", "29", "15"],
      "depends_on": [2],
      "rationale": "选址列表依赖 Wave 1 的投影非空；结果双写与删除清格依赖 Wave 2 的 xlsx 写回件"
    },
    {
      "wave": 5,
      "name": "导出",
      "tasks": ["16", "17", "18"],
      "depends_on": [2],
      "rationale": "导出读 xlsx 本体，依赖 Wave 2 确立的权威口径"
    },
    {
      "wave": 6,
      "name": "批量创建",
      "tasks": ["19", "28", "20", "21", "22"],
      "depends_on": [1],
      "rationale": "只依赖 Wave 1 的单条创建已能产出可见底稿；Task 28 预览端点是 Task 21 预览表格的数据来源"
    },
    {
      "wave": 7,
      "name": "收口（CI + 回归 + 真实库与浏览器实测）",
      "tasks": ["23", "24", "25", "26"],
      "depends_on": [3, 4, 5, 6]
    }
  ]
}
```

## Tasks

### Wave 1 — 可见性修复

- [x] 1. 抽 `custom_workpaper_projection.py`（恒等坐标）并让 `create-custom` 产出可见投影
  - 新建 `backend/app/services/custom_workpaper_projection.py`
  - `project_custom_workpaper(file_path, sheet_name) -> dict`：**恒等坐标**投影
    （不剥表头、不重编行号、不裁空列），键集 `{cells, max_row, max_col, col_widths,
    merged_cells, header_rows, column_meta}`，失败/文件缺失返 `None`
  - 🔴 **不调 `extract_grid`**（2026-08-06 探针实证：`extract_grid_from_sheet` 的
    `row_offset = data_start_row - 1` 会重编行号 —— xlsx `B6=123.45` 投影成 **`B2`**；
    且 `data_start_row` 是启发式（首个含「项目」/「序号」的行），用户录入过程中会跳变。
    自定义底稿要按投影坐标写回 xlsx，重编号会**写进表头区覆盖别的格**）
  - 🔴 `extract_grid` / `extract_grid_from_sheet` **保持零改动**（11 个既有调用方依赖
    其重编号行为，对只读渲染是有意设计）；可复用其 `_col_letter` / `_cell_value` /
    `_resolve_font_color` / `_is_accounting_format` 与样式规则
  - 🔴 空/失败路径也必须返回**完整键集**（`extract_grid` 的 empty 分支只返 5 键、
    缺 `header_rows`/`column_meta`，照抄会让「键集 ⊇ 六键」的守卫在 fail-open 路径必红）
  - `write_projection_to_parsed_data(wp, sheet_name, grid)`：整块替换
    `parsed_data['html_data'][sheet_name]`，`flag_modified(wp, 'parsed_data')`
  - 🔴 `sheet_name` 必须等于 `wp_code`（`_maybe_custom_classifications` 合成的
    `ClassificationResult.sheet_name = wp_code`，不一致则 render 取不到 `html_data`）
  - `create_custom_workpaper`（`wp_template.py:491`）在 `fill_workpaper_header` **之后**、
    `db.commit()` **之前**调投影（表头写进 xlsx 后再提取，否则投影里没有表头）
  - 投影失败 fail-open + WARNING，不阻断创建
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2_

- [x] 2. `write_cell_to_parsed_data` 维护 `max_row` / `max_col`
  - 改 `backend/app/services/wp_parsed_data_service.py`
  - 新增纯函数 `_cell_ref_to_rc(cell_ref) -> tuple[int, int]`（`B5` → `(5, 2)`，
    多字母列 `AA3` → `(3, 27)`）
  - 写入后 `sheet_data['max_row'] = max(既有 or 0, row)`、`max_col` 同理
  - 🔴 只增不减（删公式不缩边界，避免把用户其他内容挤出可见范围）
  - _Requirements: 2.3, 2.4_

- [x] 3. `"custom"` 加入 `_ONLYOFFICE_HTML_WHITELIST`
  - 改 `backend/app/routers/wp_render_config.py` 的 `_ONLYOFFICE_HTML_WHITELIST`
  - 加注释说明理由：防将来 custom 变多 sheet 时被 E 分支（L873-875）静默改写成
    `onlyoffice-sheet`，导致 `GtCustomWpEditor` 永不渲染
  - _Requirements: 4.8_

- [x] 4. Wave 1 守卫（先对当前状态打红）
  - 新建 `backend/tests/test_custom_workpaper_projection.py`
  - Property 2（投影键集完整性）：`create_custom_workpaper` 源码级断言调用了投影函数，
    且调用点在 `fill_workpaper_header` 之后、`commit` 之前（按行号断言顺序）；
    投影产出的键集 ⊇ `{cells, max_row, max_col, col_widths, merged_cells, header_rows}`
    （前端 `hasData` 的硬依赖），**含 fail-open 空网格路径**
  - Property 3（`ensure_grid_bounds` 幂等且单调）：对替身 wp 调
    `write_cell_to_parsed_data(cell_ref='C7')` 后 `max_row >= 7 and max_col >= 3`；
    再写 `A1` 后两值**不缩小**；多字母列 `AA3` → `max_col >= 27`
    （PBT，hypothesis `max_examples=20`）
  - Property 6（双模式取值域）前置项：`"custom" in _ONLYOFFICE_HTML_WHITELIST`
  - Property 1（xlsx 权威不变式，R1.9）：源码级断言 `custom_workpaper_projection.py`
    内不存在「只写投影不写 xlsx」的导出函数，且模块 docstring 写明 xlsx 权威口径
    与「改口径须另立 spec」
  - Property 12（零回归）：`wp_grid_extract.extract_grid` / `extract_grid_from_sheet`
    逐字节不变（11 个既有调用方依赖其重编号行为）
  - 🔴 **变异检验（比对失败测试名集合，不看退出码）**：①删掉投影调用 ②把投影调用挪到
    `fill_workpaper_header` 之前 ③`max_row` 改成无条件覆盖（`= row`）④从白名单删 `"custom"`
    —— 四条各自必须产出**新增**失败测试名；若某条不打红即守卫缺陷，先修守卫
  - **交付实证（2026-08-06）**：`custom_workpaper_projection.py` 14.8 KB 已在磁盘；
    `wp_template.py` 的 `create_custom_workpaper` 已调 `refresh_custom_projection(wp, data.wp_code)`
    （在 `fill_workpaper_header` 之后、`db.commit()` 之前，fail-open + WARNING）；
    `wp_parsed_data_service` 已有 `_cell_ref_to_rc` + 单调 `max_row`/`max_col` 维护；
    `_ONLYOFFICE_HTML_WHITELIST` 已含 `"custom"` 且带 spec 引用注释；
    `backend/tests/test_custom_workpaper_projection.py` **62 passed / 0 failed**
  - _Requirements: 1.7, 1.8, 1.9, 2.5, 10.1, 10.2, 10.3, 10.6, 10.7, 10.9_

### Wave 2 — 投影单一入口与网格可编辑

- [x] 5. xlsx 单元格写回服务
  - **交付实证（2026-08-06）**：随 Task 1 一并落在 `custom_workpaper_projection.py`，
    签名 `write_cells_to_xlsx(file_path, sheet_name, updates) -> int`（返回写入格数），
    sheet 缺失抛 `KeyError`、引用非法抛 `ValueError`、文件缺失抛 `FileNotFoundError`
  - `custom_workpaper_projection.py` 新增
    `write_cells_to_xlsx(file_path, sheet_name, updates: dict[str, Any]) -> int`
  - openpyxl `load_workbook(keep_vba=False)` → 逐格赋值 → `save`
  - 🔴 sheet 不存在时**不创建**，抛显式异常（自定义底稿的 sheet 名恒等于 wp_code，
    对不上说明上游有 bug，静默创建会掩盖）
  - 🔴 写盘失败必须抛异常（不 fail-open）—— xlsx 是权威，写不进去就不能报成功
  - _Requirements: 1.3, 3.2, 3.3_

- [x] 6. 单元格编辑端点
  - 新建 `backend/app/routers/custom_workpaper_cells.py`
  - `PUT /api/workpapers/{wp_id}/custom-cells`
    body `{sheet_name, updates: {"B5": "值", ...}}`（🔴 body 键是 `updates`，
    与 `write_cells_to_xlsx` 参数名一致；design 原写 `patches` 已统一）
  - 顺序：校验 componentType 为 custom（**非 custom 返 409**，design §Components 2 为准；
    本任务原写 400 已统一）→ 只读态返 403 → `write_cells_to_xlsx`
    → `refresh_custom_projection` → `file_version += 1` → commit
  - 返回 `{updated: N, grid: {...}}`（grid = 重投影结果，前端直接替换本地态）
  - 🔴 上限 `MAX_CELL_UPDATES = 500`，超限返 422 且带 `overflow` 标记（design Error Handling）
  - 🔴 **先写 xlsx 再刷投影**，顺序反了会让投影领先于权威
  - 挂进 router 注册（🔴 真实注册点是 `app/router_registry/workpaper.py` 的
    `groups["渲染"]`，**不是** `app/main.py`；只 import 不加进分组 = 端点仍 404）
  - **交付实证（2026-08-06）**：新建 `backend/app/routers/custom_workpaper_cells.py`
    （`PUT /custom-cells` + `POST /custom-refresh-projection`）+ 新建判定真源
    `backend/app/services/custom_workpaper_context.py`（`resolve_is_custom` /
    `load_custom_context` / `READ_ONLY_FILE_STATUSES`）；`app.main` 实测两条路由已注册
  - 🔴 **`WorkingPaper` 表没有 `component_type` 列** —— `custom` 是 render 期由
    `_maybe_custom_classifications` 合成的，故「是不是 custom」必须另建判定真源；
    该真源**有意不 import `wp_render_config_helpers`**（它正被并发 spec 高频改动），
    改为直接复用更底层的 `app.services.acnr.grammar.is_standard_wp_code`
    + 一条 `ProcedureInstance` 计数查询（与 `_has_custom_procedure` 逐字同构，守卫锁死）
  - 🔴 判不出是否 custom 时 `resolve_is_custom` 返回 **False**（拒绝写入）而非 True ——
    fail-closed 方向，宁可 409 也不能往标准底稿的 xlsx 直写格
  - 🔴 `sheet_name` 恒以 wp_code 为准（前端传不一致值时按 wp_code 处理 + WARNING）——
    写到别的 sheet 上 render 取不到 `html_data[wp_code]`，表现为「保存成功但界面没变」
  - _Requirements: 3.2, 3.3, 3.5_

- [x] 7. 可编辑网格组件（新建，不改 `GtGridSheet`）
  - 新建 `audit-platform/frontend/src/components/workpaper/custom/GtCustomGridSheet.vue`
  - 🔴 **不改 `GtGridSheet.vue`** —— 它是 40+ 处只读消费方的共享件，且其
    `withDefaults(..., {readonly: true})` 的 `readonly` prop 只输出到 `data-readonly`
    属性、不参与任何渲染分支，改它半径过大
  - 复用 `GtGridSheet` 的合并单元格 / 粘顶表头 / 冻结首列 / 金额格式化视觉规则
  - 双击进入编辑：`el-input` + `@blur`/`Enter` 提交，`Esc` 取消
  - 公式格（在 `formulaCells` prop 中）**只读**，鼠标悬停显示表达式
  - 批量提交（防抖 800ms 聚合多格）→ `PUT /custom-cells`（body 键 `updates`）
  - `readonly` prop 为真时不进入编辑态（OO 模式下 / 底稿已归档）
  - 🔴 编辑用 `el-input` 且**必须绑 `@input`**（只绑 `@change` 会被 EP 在 nextTick
    重置回 `modelValue`，抹掉用户键入 —— 平台既有铁律）
  - 🔴 保存失败 `ElMessage.error` + **保留脏格**，禁纯 `catch {}`（数据丢了没人发现）
  - 🔴 金额显示走 `displayPrefs.fmtAmount`，取法必须是 setup 顶层
    `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()` ——
    写成模块级命名导入 `import { fmtAmount } from '@/stores/displayPrefs'` 会整页崩
  - **同时新建纯函数层** `custom/customWpCellEdit.ts`（零 Vue 依赖，便于 PBT）：
    `normalizeCellRef` / `parseCellRef` / `colLetterToIndex` / `buildCellPatch(dirty, {maxCells})`
    —— 与后端 `custom_workpaper_projection.parse_cell_ref` 同语义，由 Task 8 守卫交叉锁死
  - _Requirements: 3.1, 3.4, 3.5, 3.6, 3.8_

- [x] 8. Wave 2 守卫
  - 新建 `backend/tests/test_custom_workpaper_cells.py`：端点顺序（源码级断言
    `write_cells_to_xlsx` 调用行号 < `project_custom_workpaper` 行号）、非 custom 返 400、
    sheet 不存在抛异常、写盘失败不被吞
  - 新建 `audit-platform/frontend/src/components/workpaper/custom/__tests__/customGridEditing.spec.ts`：
    Property 14（双击进编辑 / Esc 取消 / 公式格不可编辑 / readonly 时不进编辑）
  - 🔴 Property 14 必须断言「公式格不可编辑」用的是**真实 `formulaCells` prop 驱动**，
    不是靠 CSS
  - Property 4 / Property 5（`customWpCellEdit` 纯函数，Task 7）：
    `normalizeCellRef` ∘ `parseCellRef` 往返可逆、非法引用返 `null` 而非 0；
    `buildCellPatch` 同格保留最后一次 + 键归一化后无重复 + 超限置 `overflow`
    而非静默截断（PBT，`numRuns=20`）
  - Property 23（前后端解析一致）：读后端 `custom_workpaper_projection.py` 源码，
    对同一组样本（`$B$5` / 小写 / `AA3` / `B` / `5` / `B5C` / 空串）两侧结论一致
    —— 合法者行列相等、非法者两侧都判非法
  - Property 13 / Property 22（存量补齐，Task 27）：`parsed_data` 为空的 custom 底稿 render 时被补齐；
    已有非空投影时不重投影（幂等）；非 custom 底稿的 render 路径无该调用
  - 🔴 反向自检：`GtGridSheet.vue` 源码**未被修改**（断言其 `defineProps<...>(), { readonly: true }`
    仍在且全文 `emit(` 与 `defineEmits` 计数均为 0）—— 防后续会话为省事去改共享件
  - 变异检验：①端点里把两步顺序调换 ②公式格改成可编辑 ③`readonly` 时仍可编辑
    ④Task 27 的补齐去掉 custom 门控（应打红「污染非 custom 路径」）
  - **后端部分已交付（2026-08-06）**：`backend/tests/test_custom_workpaper_cells.py`
    43 例（端点顺序 / 上限与 overflow / 409·403·404 三闸 / 判定真源 / 存量补齐幂等 /
    `source_unavailable` 三态 / 跨前后端 `hasData` 口径锁死 / router 注册双断言）。
    与 Wave 1 守卫合跑 **105 passed / 0 failed**；
    **6 个变异逐条 RED 且还原完整**（M1 顺序反转 / M2 409→400 / M3 去 custom 门控 /
    M4 去幂等短路 / M5 超限分支 `if False` / M6 删 `source_unavailable`）；
    零回归 `test_render_config_smoke` + custom 全量 **1816 passed / 0 failed**
  - 🔴 **变异检验顺带修掉一处自造的弱判据**：`test_overflow_branch_exists` 初版只断言
    「`MAX_CELL_UPDATES` 与 `overflow` 出现在函数体里」，把 `if len(updates) > MAX...`
    改成 `if False:` **仍然通过**（常量与 `overflow` 字面都还在）⇒ 最核心的变异静默逃逸。
    已改为断言**条件形态** `if\s+len\(\s*updates\s*\)\s*>\s*MAX_CELL_UPDATES\s*:`
  - **前端部分（`customGridEditing.spec.ts` / Property 4·5·14·23）待 Task 7 落地后补**
  - _Requirements: 3.7, 10.4, 10.6, 10.8, 2.6_

### Wave 3 — 双模式接线

- [x] 9. `GtCustomWpEditor` 接双模式
  - 改 `audit-platform/frontend/src/components/workpaper/GtCustomWpEditor.vue`
  - 🔴 用参数化工厂 `composables/factories/createDualMode.ts`（取值 `'html' | 'onlyoffice'`）
    —— **禁用 `useD1DualMode`**，它的取值是 `'html' | 'oo'`，与其余 40+ 处不统一，
    选错会与既有 localStorage 持久化值冲突
  - `persistKey: 'custom-wp-mode-' + wpId`
  - `onSwitchToHtml`：调 `POST /custom-refresh-projection`（Task 10）再 reload
  - `el-segmented` 用 `:model-value` + `@change="dualMode.onModeChange"`
    —— 🔴 **禁用 `v-model`**（v-model 会先改值使 `switchMode` 的
    `if (target === currentMode.value) return` 守卫短路，N1 注释已明确记载）
  - OO 侧渲染 `GtOnlyOfficeSheet` + `@fallback` 回落 HTML
  - HTML 侧渲染 Task 7 的 `GtCustomGridSheet`
  - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.7_

- [x] 27. 存量自定义底稿 render 时投影补齐
  - 改 `backend/app/routers/wp_render_config.py`：componentType 为 `custom` 且
    `parsed_data.html_data[sheet_name]` 缺失/空（`cells` 为空或 `max_row<=0`）时，
    调 `refresh_custom_projection(wp, sheet_name)` 补齐并下发
  - 🔴 **加法式门控**：仅 custom 生效，非 custom 底稿的 render 路径逐字节不变（Property 12）
  - 🔴 幂等：已有非空投影时**不重投影**（避免每次 render 都读 xlsx 拖慢 render-config）
  - 🔴 fail-open + WARNING：xlsx 缺失/损坏时下发 `empty_grid()` 并置可见提示标记
    （前端据此提示「底稿文件异常」以区别于「空底稿」，R1.4）
  - 🔴 **本任务是立项漏掉的真缺口**（R2.6 / Property 22）：Task 1 只在**新建时**投影，
    而库里既有自定义底稿的 `parsed_data` 已经是空的 —— 不补齐它们永远看不见内容，
    也就永远选不了公式目标格
  - **交付实证（2026-08-06）**：`custom_workpaper_projection` 新增
    `grid_has_content(grid)`（与前端 `hasData` 同口径，守卫跨前后端锁死）
    + `project_if_empty(wp, sheet_name, existing)`（有内容即短路、不落库、
    空投影时带 `source_unavailable` 区分「文件异常」与「空底稿」）；
    `wp_render_config.py` 在 `if component_type == "custom":` 门控内调它，
    位置在 `component_type == "skip"` 早退**之前**
  - 🔴 **不落库**（GET 端点不写库）—— 用户编辑一格后投影由 `PUT /custom-cells` 持久化，
    此后 `project_if_empty` 直接短路，无额外 IO
  - _Requirements: 2.6, 1.4, 11.1_

- [x] 10. 投影刷新端点 + OO forcesave 后刷新
  - `custom_workpaper_cells.py` 新增
    `POST /api/workpapers/{wp_id}/custom-refresh-projection`（从 xlsx 重提取投影）
  - `OnlyOfficeCallbackService` 的 forcesave 落盘成功后，若该 wp 的 componentType 为
    custom 则调同一投影服务
  - 🔴 加法式接线：非 custom 底稿的回调路径**逐字节不变**（用 `if` 门控，不改既有分支）
  - 🔴 投影刷新失败 fail-open + WARNING（不能因投影失败而让 OO 保存报错）
  - _Requirements: 4.4, 4.6, 11.1_

- [x] 11. Wave 3 守卫
  - 新建 `.../custom/__tests__/customDualModeWiring.spec.ts`
  - Property 6：`GtCustomWpEditor` 源码含 `createDualMode` 且**不含** `useD1DualMode`；
    `el-segmented` 用 `:model-value` 且**不含** `v-model="`
  - Property 6 反向自检：断言 `createDualMode.ts` 的取值确为 `'html'|'onlyoffice'`
    且 `useD1DualMode.ts` 确为 `'oo'`（证明这条禁令有实际差异，非空转）
  - Property 7：切回 HTML 时调了投影刷新（断言 `onSwitchToHtml` 回调体里有该端点引用）
  - 后端：非 custom 底稿的 OO 回调路径零改动（源码级断言门控存在）
  - 🔴 **标签存在性断言必须带边界** —— 用 `new RegExp('<GtOnlyOfficeSheet(?=[\\s/>])')`，
    写 `toContain('<GtOnlyOfficeSheet')` 会被 `<GtOnlyOfficeSheetREMOVED` 骗过
  - 变异检验：①换成 `useD1DualMode` ②`el-segmented` 改 `v-model` ③删投影刷新调用
    ④把 OO 组件标签改名加后缀
  - _Requirements: 4.9, 10.4, 10.6, 10.8_

### Wave 4 — 公式可用性

- [x] 12. 公式选址列表修复
  - `GtCustomWpEditor.wpContext` 的 `cells` 派生：Wave 1 后 `htmlData.cells` 非空即自然可用
  - 补 label 派生：优先取该格**同行首列**或**同列首行**的文本作为语义标签
    （现实现直接用 `cell` 引用当 label，选址列表全是 `A1`/`B2` 无语义）
  - 空投影时 `el-empty` 提示「底稿暂无内容，请先在网格中录入或切换在线编辑」
    —— 不给空列表
  - _Requirements: 5.1, 5.2_

- [x] 13. 公式求值结果双写 xlsx
  - 改 `backend/app/routers/wp_formula.py::save_formula` 的 custom 分支
  - 现流程只 `write_cell_to_parsed_data`（单写投影）→ 追加 `write_cells_to_xlsx`
  - 🔴 顺序：先写 xlsx（权威）再写投影；xlsx 写失败必须让整个保存失败（不能只有投影有值）
  - 🔴 **只对 custom 底稿双写**：非 custom 底稿的 `save_formula` 路径逐字节不变
    （用 componentType 门控）
  - 前端 `onFormulaSave` 读 `res.evaluated_value` 并本地即时回显（现只读 `eval_warnings`）
  - `eval_warnings` 展示**明细**而非只提示条数（现文案是「部分引用求值告警: N」，
    用户看不到是哪个引用出的问题）
  - _Requirements: 5.3, 5.4, 5.5, 5.6, 5.7, 11.4_

- [x] 14. 公式清单面板
  - `GtCustomWpEditor` 工具栏加「公式清单」按钮 → 抽屉展示
    `GET /api/workpapers/{wp_id}/formulas`（真实存在的端点）
  - 🔴 响应键是 **`items`** 不是 `formulas`（`list_formulas` 实证），
    读错键会恒空且被 catch 吞掉
  - 每条显示：目标格 / 表达式 / 类型中文标签 / 最后计算时间 / 删除按钮
  - 类型中文标签复用既有单一真源 `formulaEngineInventory.FORMULA_TYPE_LABEL`，
    **不新建第二份标签表**（并发 spec `formula-management-runtime-closure` R2.5 同此要求）
  - 端点路径登记进 `services/apiPaths.ts`（🔴 真实路径，原写 `apiPaths/workpaper.ts` 不存在），
    不在组件内硬编码模板字符串
  - 🔴 **删除的完整语义见 Task 29** —— 只删 `wp_formula` 行不够，xlsx 里那格还留着上次
    求值结果，该格恢复可编辑后会显示旧值（R6.4）
  - 点击清单某条 → 在网格中定位并高亮该目标格（R6.3）；清单为空显示 `el-empty` 而非空表格
  - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6, 6.7, 9.4, 9.5_

- [x] 29. 删除公式时清除该格求值结果（R6.4 的完整语义）
  - 改 `backend/app/routers/wp_formula.py::delete_formula`
  - 删 `wp_formula` 行后，若底稿 componentType 为 `custom`：
    `write_cells_to_xlsx(file_path, sheet_name, {target_cell: None})` 清格
    → `refresh_custom_projection` 刷投影 → commit
  - 🔴 **加法式门控**：非 custom 底稿的 `delete_formula` 路径逐字节不变（Property 12）
  - 🔴 清格失败不得让删除整体失败（公式定义已删是用户意图），记 WARNING 并在响应里
    带 `cell_clear_failed: true` 让前端提示「公式已删除，但该格残留值清理失败」
  - 🔴 **立项漏登记**：只删定义会让 xlsx 里残留上次求值结果，该格恢复可手工编辑后
    显示的是旧公式值 —— 在 xlsx 权威口径下这是数据错误不只是显示问题（Property 21）
  - _Requirements: 6.4, 3.4_

- [x] 15. Wave 4 守卫
  - 新建 `.../custom/__tests__/customFormulaWiring.spec.ts`
  - Property 9：选址 label 非纯 cell 引用（替身投影验证语义标签派生）；空投影时渲染 `el-empty`
  - Property 15：清单面板读 `items` 键、**不含** `data?.formulas` 形态、
    类型标签 import 自 `formulaEngineInventory`
  - Property 8（双写原子性）：后端 `test_custom_workpaper_cells.py` 补 ——
    custom 公式保存后 xlsx 与投影**双方**都有值；xlsx 写失败时投影**不保留**该值；
    非 custom 底稿的 save_formula 不触发 xlsx 写入
  - Property 21（删除清格，Task 29）：custom 底稿删公式后 xlsx 与投影双方该格为空、
    该格恢复可编辑；非 custom 底稿的 `delete_formula` 无 xlsx 写入
  - 🔴 反向自检：构造「只写投影不写 xlsx」的替身实现，守卫必须打红
  - 变异检验：①清单读 `formulas` 键 ②公式只写投影 ③label 退回纯 cell 引用
    ④新建第二份类型标签表 ⑤删公式不清 xlsx 格
  - _Requirements: 5.8, 6.8, 6.4, 10.6_

### Wave 5 — 导出

- [x] 16. custom 独立导出路径
  - 新建 `backend/app/services/custom_workpaper_export.py`
  - `export_custom_workpaper(wp, project_meta) -> BytesIO`：直接读 xlsx 文件本体
    → `MetadataCodec` 嵌元数据 → 返回
  - 🔴 **不调 `load_schema`**（自定义 wp_code 在 `wp_render_schema/` 下无 yaml，
    现流程第一步就 500）
  - 🔴 **不套 `dynamic_table` schema**（导出服务读 `html_data[sheet]['rows']`，
    而 custom 是 `{cells: {...}}` 形态，两者结构不兼容）
  - 复用 `WpExportEngine` 的元数据嵌入 + `compute_snapshot_hash` + `wp_export_snapshot` 落库外壳
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.8_

- [x] 17. 导出端点分流
  - 改 `backend/app/routers/wp_xlsx_export.py`：componentType 为 custom 时走 Task 16 路径
  - 🔴 分流判定必须在 `load_schema` **之前**（否则仍会 500）
  - 🔴 **第二条导出路径也要分流（立项漏登记，2026-08-06 实证）**：
    `wp_export_import_router` 走 `WpExportEngine.export_single` → `_export_xlsx`，
    其 `except (TemplateNotFoundError, Exception)` **吞掉一切异常并回退空白 workbook**
    → 自定义底稿从这条路导出会静默产出「只有 wp_code 一个 sheet 名的空表」而**返回 200**
    （比 `/export-xlsx` 的 500 更坏：用户拿到空文件却以为导成功了）
  - 🔴 `determine_export_format` 的 `_XLSX_TYPES` 加 `"custom"`
    —— 当前它落「默认 xlsx」这条隐式兜底，与显式映射行为相同但**判据不可断言**
  - 非 custom 底稿的两条导出路径逐字节不变
  - _Requirements: 7.1, 7.2, 7.9, 7.10, 11.1_

- [x] 18. Wave 5 守卫
  - 新建 `backend/tests/test_custom_workpaper_export.py`
  - Property 10：custom 导出**不引用** `load_schema` / `export_workpaper_xlsx`
    （源码级断言，先 `stripComments` 防注释里的说明被数成真实调用）
  - Property 10 反向自检：断言标准底稿导出路径**仍然**引用 `load_schema`
    （证明这条禁令有区分度）
  - Property 10（续）：分流判定行号 < `load_schema` 行号
  - Property 10（续）反向自检：对无 schema 的 custom wp_code 走导出**不抛 500**
  - Property 20（往返可逆）：导出产出的字节流经 `openpyxl.load_workbook` 可打开，
    且再经自定义投影函数读回的 `cells` ⊇ 导出前的 `cells`（键与值逐格相等）
  - Property 18（两条路径都分流）：`WpExportEngine._export_xlsx` 对 custom 底稿
    不进入 `export_workpaper_xlsx`；且断言其 `except (TemplateNotFoundError, Exception)`
    的空白 workbook 回退**不会**被自定义底稿触发
  - Property 18 反向自检：构造「只分流 `/export-xlsx` 不分流 `export_single`」的替身，
    守卫必须打红（证明两条路径各有断言，不是一条覆盖两条）
  - Property 19（格式判定显式）：`"custom" in _XLSX_TYPES`；
    反向自检 = 从 `_XLSX_TYPES` 移除 `"custom"` 后**行为仍是 xlsx**（默认兜底），
    故该断言只能靠集合成员判定、不能靠 `determine_export_format` 返回值
    —— 🔴 这正是「隐式兜底不可断言」的证据，必须在守卫注释里写明
  - 变异检验：①custom 导出改回走 `load_schema` ②分流挪到 `load_schema` 之后
    ③只分流 `/export-xlsx` 漏掉 `export_single` ④从 `_XLSX_TYPES` 移除 `"custom"`
  - _Requirements: 7.6, 7.7, 7.11, 10.5, 10.6_

### Wave 6 — 批量创建

- [x] 19. 批量创建端点
  - `wp_template.py` 新增 `POST /api/projects/{project_id}/working-papers/create-custom-batch`
    body `{items: [{wp_code, wp_name, audit_cycle?}], year}`
  - 🔴 **per-item savepoint**（`async with db.begin_nested()` + per-item try/except 记
    failures 后继续，最外层一次 commit）—— 范式取自同文件 `generate_from_codes`
  - 返回 `{created, skipped, failed, results: [{wp_code, status, reason?}]}`
    —— 三态可分（成功 / 编号已存在跳过 / 失败带原因）
  - 单条 `create-custom` 端点**保留不动**（既有前端调用方零改动）
  - 每条内部复用与单条完全相同的创建逻辑（抽共享函数，避免两份实现漂移）
  - _Requirements: 8.4, 8.5, 8.6, 8.7, 8.10, 11.1_

- [x] 28. 批量预览端点（只读，补齐库内重号判定）
  - `wp_template.py` 新增
    `POST /api/projects/{project_id}/working-papers/create-custom-batch/preview`
    body `{items: [{wp_code, wp_name, audit_cycle?}]}`
  - 逐行返回 `{wp_code, wp_name, audit_cycle, status, reason}`，
    `status ∈ ok | duplicate_input | duplicate_db | invalid` + `summary` 计数
  - 🔴 **只读不写库** —— 调用前后 `wp_index` / `working_paper` 行数必须不变（Property 11）
  - 🔴 `duplicate_db` 只有后端能判（查 `wp_index` 该项目下已存在的 `wp_code`）；
    前端 `validateItems` 只负责格式与清单内重号
  - 🔴 **本任务是 Task 21 预览表格的数据来源**，R8.2「不得直接开始创建」靠它成立；
    立项时漏登记该端点（Task 20 的 `validateItems(items, existingCodes)` 无 existingCodes 来源）
  - _Requirements: 8.2, 8.3, 8.8_

- [x] 20. 清单解析（粘贴文本 + Excel 双入口）
  - 新建 `audit-platform/frontend/src/components/workpaper/custom/customWpBatchParse.ts`
  - `parseTextList(text) -> ParsedItem[]`：按行切，每行按 Tab/多空格/逗号切列
    （`wp_code`、`wp_name`、可选 `audit_cycle`）；空行跳过
  - `parseExcelRows(rows) -> ParsedItem[]`：识别表头行（含「编号」「名称」字样）
    并按列名映射，无表头时按位置
  - `validateItems(items, existingCodes) -> {valid, errors}`：编号非空 / 名称非空 /
    清单内不重复 / 与既有底稿编号不冲突 / 编号字符集合法
  - 🔴 纯函数、零 Vue 依赖，便于 PBT
  - _Requirements: 8.1, 8.8, 8.10_

- [x] 21. 批量创建 UI
  - 新建 `.../custom/GtCustomWpBatchDialog.vue`
  - 两个 Tab：「粘贴清单」（textarea + 格式说明）/「上传 Excel」（`el-upload` + SheetJS 解析）
  - 解析后**预览表格**：逐行显示校验结果（✅ 可创建 / ⚠️ 编号已存在将跳过 / ❌ 错误+原因）
  - 🔴 有 ❌ 时禁用「确认创建」按钮 + tooltip 说明原因
    （门控必须前置为 disabled，不能点了才提示 —— 平台既有铁律）
  - 创建后展示结果摘要（成功 N / 跳过 N / 失败 N + 失败明细）
  - 挂载入口：底稿列表页工具栏
  - _Requirements: 8.1, 8.2, 8.3, 8.5_

- [x] 22. Wave 6 守卫
  - 新建 `backend/tests/test_custom_workpaper_batch.py`：per-item 隔离
    （一条失败其余仍创建）、编号已存在返 skipped 非 failed、三态齐备、
    单条端点响应形状未变
  - Property 11（预览只读，Task 28）：调 preview 前后 `wp_index` / `working_paper`
    行数不变；库内已存在编号被标 `duplicate_db`
  - 🔴 R8.7/R8.9 交叉锁死：断言批量路径与单条路径**共用**
    `_create_one_custom_workpaper`（变异「批量另写一份创建逻辑」必须打红）
  - 新建 `.../custom/__tests__/customWpBatchParse.spec.ts`：Property 11
    （两种输入解析出同构结果 + PBT 校验幂等 + 清单内重复检出）
  - R8.2 / R8.3 门控：有错误项时确认按钮 disabled（源码级断言 + 带 tooltip）
  - 🔴 反向自检：构造「无 savepoint 的替身实现」，一条失败导致整批回滚 → 守卫必须打红
  - 变异检验：①去掉 per-item savepoint ②skipped 归入 failed ③有错误时按钮仍可点
  - _Requirements: 8.9, 10.6_

### Wave 7 — 收口

- [x] 23. CI job
  - `.github/workflows/governance-checks.yml` 新增两个 job：
    `custom-workpaper-backend`（Task 4/8/15/18/22 的后端守卫）
    `custom-workpaper-frontend`（Task 8/11/15/22 的前端守卫）
  - 🔴 对齐既有主流形态（补 npm 缓存），改完用 `yaml.safe_load` 验证可解析 + 断言
    双方 job 名全在、无重名
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 24. 零回归回归
  - 后端：`-k "custom or formula or export or render_config"` 全量
  - 前端：`npx vitest run custom formula export`（多子串取并集，**不用 `-t ""`**
    —— 会把全部用例判 skipped）
  - 🔴 判「失败是否自己造成」用 **traceback 行号是否落在自己改动的行上**；
    可疑时用「`git show HEAD:` 换单个文件跑同一组、比对失败集合差集」，
    **禁用 `git stash`**
  - 🔴 若某既有测试锁定了被修复的错误行为，诚实改写并在 Notes 说明，
    不用跳过/放宽断言绕过
  - Property 12（零回归）+ Property 16（不侵入并发 spec）：断言改动集合不含
    `formula_engine.py` 的 `COLUMN_ALIASES` 与求值回退、`wp_user_formulas.py` 的存储落点、
    `wp_formula_service.save` 的存储语义、`useFormulaStatus.ts`；
    新增 `apiPaths` 键与对侧 spec 互不重叠
  - Vite transform 200 检查：所有改动的 `.vue` / `.ts`
  - _Requirements: 9.1, 9.2, 9.3, 9.6, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

- [x] 25. 真实库验收脚本
  - 新建 `backend/scripts/diagnose/verify_custom_workpaper_live.py`（默认 dry-run，
    `--apply` 真跑并按快照自动复原）
  - 输出：创建 → 投影键集与 `max_row`/`max_col` → 编辑一格后 xlsx 与投影双方值 →
    保存一条公式后双方值 → 导出字节数与元数据可解出 → 批量创建三态计数
  - 🔴 每步区分四态（成功 / 前置缺失 / 端点不存在 / 数据为空），不混同
  - Property 17（实测数据可复原）：`--apply` 前抓完整基线（含 `parsed_data` 的
    `md5(col::text)` + `jsonb_typeof` + `length`），复原后三项逐一比对；
    🔴 复原时给 JSONB 列赋 **dict** 不赋 `json.dumps` 字符串
    （后者会写成 JSON 字符串标量，`jsonb_typeof` 变 `string`、下游 `->>` 全失效，
    而脚本仍报 `[OK]`）
  - 🔴 控制台输出禁 emoji（GBK 会 `UnicodeEncodeError` 且崩在写盘之后），用 `[OK]`/`[ERR]`
  - _Requirements: 12.1, 12.4, 12.5_

- [x] 26. 浏览器实测 + 清理
  - 项目/底稿：新建一个自定义底稿实测（不碰既有项目数据）
  - 覆盖：①新建后网格**有内容**（不再是「暂无内容」）②双击编辑一格 → 刷新后仍在
    → postgres 查 xlsx 与投影双方 ③切「在线编辑」→ 改一格 → 切回「结构化视图」看到新值
    ④公式选址列表有语义标签 → 加一条公式 → 目标格显示求值结果
    ⑤导出 xlsx 能打开且内容正确 ⑥批量粘贴 3 条（含 1 条重号）→ 预览三态正确 → 创建后计数吻合
  - 🔴 实测三件套：**录真实数据 + 看目标区域真出数 + postgres 查落库**，缺一不算实测
  - 🔴 实测后**按基线逐字节复原**，并清掉本会话 `tmp_*` 诊断产物
  - _Requirements: 12.2, 12.3, 12.4, 12.5, 12.6_

## Notes

### 与并发 spec 的边界（`formula-management-runtime-closure`）

该 spec 已有完整三件套（2026-08-06 建）。**本 spec 明确不做**：

| 归属它 | 理由 |
|---|---|
| `wp_formula` ↔ `parsed_data['user_formulas']` 存储收敛（其 R4） | 半径覆盖全平台公式存储，本 spec 的自定义底稿公式**已经**走 `wp_formula`，方向一致无冲突 |
| `COLUMN_ALIASES` 补 4 键 + 消除两条路径静默回退（其 R3） | 求值引擎级改动，自定义底稿是**受益方**不是改动方 |
| `useFormulaStatus` 端点错配（其 R1） | 那是另一个 composable；本 spec Task 14 新建的清单面板直接用正确端点与 `items` 键 |
| 三类型执行链接通（其 R6） | 运行层改造 |

**共享判据**：类型中文标签单一真源 `formulaEngineInventory.FORMULA_TYPE_LABEL` —— 两个 spec
都要求复用它、都禁止新建第二份。若两 spec 并行推进，Task 14 与其 R2 会碰同一个常量的**消费方**
（不碰常量本身），风险低；但 **`apiPaths/workpaper.ts` 两侧都要改** → 按平台铁律
「多 spec 改同一批文件时不要并行推进」，Task 14 落地前先看该文件 mtime。

### 已实证的事实基线（写代码前不必重查）

- 🔴🔴 **原第一条「`extract_grid` 键集恰好覆盖 `GtGridSheet`，投影层零新造」已被实证推翻，
  勿再照它实现**（2026-08-06 探针）：①`extract_grid_from_sheet` 的
  `row_offset = data_start_row - 1` **重编行号**（xlsx `B6=123.45` 投影成 `B2`，列不变只有行位移），
  且 `data_start_row` 是启发式（首个含「项目」/「序号」的行）会在录入过程中跳变；
  ②它的空/失败路径**只返 5 键**（无 `header_rows`）。
  ⇒ 自定义底稿走 `custom_workpaper_projection.project_custom_workpaper` 的**恒等坐标**投影，
  `extract_grid` 保持零改动。
- `GtGridSheet` 实际消费的 `htmlData.*` 键**恰为六个**：
  `cells` / `max_row` / `max_col` / `col_widths` / `merged_cells` / `header_rows`。
  `column_meta` 只在其类型声明中出现、不参与渲染分支 ⇒ **自定义底稿不产出 `column_meta`**
- `GtGridSheet.hasData = Object.keys(cells).length > 0 && maxRow > 0`；
  `defineProps<{...}>(), { readonly: true }`；全文 `emit(` 与 `defineEmits` 计数均为 **0**
  ⇒ 传 `readonly=false` 也不可编辑，必须新建组件
- `createDualMode.ts` 在 `components/workpaper/composables/factories/`；
  `useD1DualMode.ts` 在 `components/workpaper/composables/`；
  `apiPaths.ts` 在 `services/`；`formulaEngineInventory.ts` 在 `components/workpaper/composables/`
- `wp_formula.py`：`list_formulas` 在 L563 返回 `{"items": [...]}`；`save_formula` L594；
  `write_cell_to_parsed_data` 调用点 L721；`delete_formula` L770
- `export_engine.py`：`_XLSX_TYPES = {"univer","form","hybrid","table","audit_sheet","program_sheet"}`（L45，
  无 `"custom"`）；`export_single` L82；`_export_xlsx` L438；宽捕获 `except (TemplateNotFoundError, Exception)` L460
- `wp_xlsx_export.py`：`@router.post("/{wp_id}/export-xlsx")` L41，`load_schema` 在 L80（第一步）
- `create_custom_workpaper` 在 `wp_template.py:491`，同文件 `generate_from_codes`
  L464 有 `populate_parsed_data` 调用可作范式
- `wp_formula` 唯一索引 `uq_wp_formula_wp_sheet_cell(wp_id, sheet_name, target_cell)`
- `PUT /formulas` 只放行 `TB` / `SUM_TB` / `WP` 三个函数，其余 422
  `FORMULA_UNSUPPORTED_FUNCTION`
- `_maybe_custom_classifications` 合成的 `ClassificationResult.sheet_name = wp_code`
- custom 恒单 sheet → `_is_multi_sheet=False` → render 的 E/F/G 三个 elif 全不进
  ⇒ `html_data` 完全来自 `parsed_data`，render 阶段零加工
- `createDualMode` 取值 `'html'|'onlyoffice'`；`useD1DualMode` 取值 `'html'|'oo'`（不统一）
- `determine_export_format` 的 `_XLSX_TYPES` / `_DOCX_TYPES` 均无 `"custom"`

### 范围外（不做，登记备查）

- `GtGridSheet` 的 `user_input` tooltip 写「双击编辑」但无实现（误导性 UI）——
  归共享件清理，本 spec 只在新建的 `GtCustomGridSheet` 里真做编辑
- 3 份 DualMode 工厂 + 40+ 薄壳的收敛 —— 独立 spec
- custom 底稿的 docx 导出方向 —— 无源模板依据，宁缺勿造
- `custom-with-template` 链路（`ProcedureInstance` + `WpIndex` 占位、不建
  `working_paper`）与 `create-custom` 链路的合并 —— 两条自定义链路并存不交汇，
  合并属独立议题

### 浏览器实测实录（26 收口，2026-08-08，六项覆盖全通过 + 修 2 个 P0）

实测目标：项目 `b39809ed`（重庆医药集团和平物流有限公司_2025）新建自定义底稿
`ZZT26A`（wp `e64b1122`），**不碰任何既有项目数据**；另经批量路径新建 `ZZT26B`/`ZZT26C`。

| 覆盖 | 判据 | 结果 |
|---|---|---|
| ① 新建后网格有内容 | render-config `cells=15` / `max_row=5` / `header_rows=0`，`A1` 就是 xlsx 的 `A1` | ✅ 恒等坐标，无行位移 |
| ② 格编辑往返 | 双击 B4 → 填「T26实测编制人」→ Enter → 状态条「1 处待保存」→ 500ms 落盘 → 刷新仍在 | ✅ xlsx 与投影**双方**均为该值 |
| ③ OO ↔ 结构化视图 | 改 xlsx 本体 `D5`（模拟 OO 直编）→ 投影仍无 `D5` → 切「表格视图」→ `D5` 出现 | ✅ 切回刷投影通路成立 |
| ④ 公式选址 + 求值 | 选址列表带语义标签（`致同会计师事务所（特殊普通合伙） (A1)` / `编制单位： (A2)`）；`TB('1001','期末余额')`→`D4=0`、字面量 `1234.56`→`F4` | ✅ xlsx `D4=0`/`F4=1234.56` + 投影同步（20 格） |
| ⑤ 导出 xlsx | `POST /export-xlsx` → 200 / 正确 MIME / 5601 B / ZIP 魔数 `PK` | ✅ 不再是 `load_schema` 500 |
| ⑥ 批量创建 | 3 条（含 1 条重号）→ 预览 `ok 2 / duplicate_db 1` → 创建 `created 2 / skipped 1 / failed 0`；两张新底稿投影各 15 键且与 A 的骨架逐字一致 | ✅ 计数吻合，理由中文 |

#### 🔴 P0-1：自定义底稿的「在线编辑」从上线起打不开（已修）

点「在线编辑」→ `onlyoffice-config` **404**。根因 = `_resolve_wp_file` 只认
① OO 缓存副本 ② **模板文件**；而自定义底稿**没有模板**，其 xlsx 在
`working_paper.file_path` 指的业务存储下 ⇒ 两来源都不命中 ⇒ `FileNotFoundError` ⇒ 404。

更深一层：即便复制一份到缓存也不对 —— callback 落盘写缓存，而
`refresh_custom_projection` 读 `wp.file_path`（业务文件）⇒ OO 改动**永远进不了 HTML 侧**，
且「xlsx 本体唯一权威」退化成两份 xlsx 打架。

修法：新增 `_resolve_custom_wp_file(wp, wp_code)`（custom → 业务文件本体，其余返 None
退回既有路径 = 零回归方向），接进 **config / WOPI 下载 / callback 落盘** 三处，与投影读取同源；
`custom_workpaper_context` 增 `resolve_is_custom_sync`（OO 路径同步、只判「manual + 非标准编号」
这一支，**有意比异步版窄** —— 漏判退回旧路径，误判会把标准底稿本体暴露给 OO 直编）。
实测 404 → **200**（`fileType=xlsx` + doc key + WOPI url），OO iframe（9.4.0）正常起来。

#### 🔴 P0-2：公式格可被手工改写、改完被静默覆盖（已修）

配好公式后 `D4`/`F4` **没有 ƒ 标记、仍标 `--editable`、双击能进编辑态**。
根因 = `formulaCells` 从 `htmlData.cells[*].formula` 派生，而自定义底稿的公式存在
`wp_formula` 表、xlsx 里写的是**求值结果**（`D4` 存数字 `0`，不是 `=TB(...)`）⇒ 该 computed 恒空。

修法：`formulaCells` 改由 `wp_formula` 清单（`formulaList`）派生 + `onMounted` 静默拉一次 +
公式保存后同步刷新（xlsx 的 `formula` 键保留作补充来源）。
实测修后：`ƒ 0` / `ƒ 1234.56`、`--formula` 类、tooltip「该格由公式计算：TB('1001','期末余额')」、
双击被拒并提示「该单元格由公式计算，如需手工填写请先删除该公式」；B4 仍可编辑（未误伤普通格）。

#### 新增守卫与变异检验

- `backend/tests/test_custom_workpaper_oo_file_resolution.py`（10 例）——
  含**行为级**断言（真跑 helper 比对返回路径，不只做源码字样断言）+ 4 条反向自检
- `.../custom/__tests__/customFormulaCellReadonly.spec.ts`（11 例）——
  含 helper 三形态自检与「参数内联类型字面量」自检
- **变异检验 5/5 全 RED**（M1 分流失效 / M2 目标改指 OO 缓存 / M3 不消费清单 /
  M4 删挂载拉取 / M5 保存后不刷新），备份落 `.bak` + md5 还原核验，残留为 0

#### 零回归与清理

- 后端本 spec 守卫 **130 passed / 0 failed**；前端 `custom/__tests__` **30 文件 139 passed / 0 failed**
- 前端 `-k custom` 另有 5 个失败全在 `custom-query`（高级查询模板库，`CustomQueryTab.vue`
  的 `canDo is not a function`），两文件 git 干净且上次改动来自无关 commit ⇒ **预存在，非本 spec**
- 实测数据已清零：`ZZT26A/B/C` 的 `wp_index`/`working_paper`/`wp_formula` 行与 3 个 xlsx 全删，
  计数回到基线（`wp_index`=2789 / `working_paper`=2789 / `wp_formula`=0），另清 62 个 `_wip_t26*` 产物

#### 本轮沉淀的两条判据（已随 memory 记录）

1. **「四层验证全绿、只有浏览器能发现」再增两例** —— 两个 P0 都满足：`get_diagnostics` 零诊断 /
   既有单测全绿（后端测的都是「有模板」的标准 wp_code；前端只验保存端点不验网格只读态）/
   Vite transform 200。
2. **源码字样断言挡不住「字面还在、行为已错」** —— M2 变异（把 `raw` 改指 OO 缓存）在只有
   「出现 `wp.file_path` 字样」判据时 **GREEN**，补了行为级断言（真跑 helper 比对返回路径）才转 RED。
