# Tasks — A1-12 重大事项决定程序双模式核查表

## 1. 注册与配置

- [x] 1.1 更新 `wp_code_overrides.json`：`"A1-12": "a1-12-dual-checklist"`
- [x] 1.2 后端 `VALID_COMPONENT_TYPES` 新增 `"a1-12-dual-checklist"`
- [x] 1.3 后端 `RENDERER_DISPATCH` 新增 `"a1-12-dual-checklist": render_a112_dual`
- [x] 1.4 `htmlRendererRegistry.ts` 注册 `a1-12-dual-checklist`（lazy import GtA112DualChecklist.vue）
- [x] 1.5 `useA1SubWorkpapers.ts` A1-12 componentType → `'a1-12-dual-checklist'`
- [x] 1.6 `GtA1Dashboard.vue` 新增 v-else-if 渲染分支

## 2. 后端 DOCX 解析

- [x] 2.1 实现 `_parse_a1_12_checklist(docx_path)` — 解析 A1-12 DOCX 为 A112ChecklistData
  - 头部信息从段落正则提取（被审计单位/截止日/业务分类/首次承接）
  - 表格按"一、"/"二、"分组为 categories
  - 每行解析为 A112CheckItem（seq/description/category_tag）
  - 第二类 allow_custom=true
  - 签字区从段落提取 4 角色

- [x] 2.2 实现 `render_a112_dual` 策略函数（注册到 RENDERER_DISPATCH）
  - 调用 _parse_a1_12_checklist 获取 checklistData
  - 合并 field_overrides 中的 responses
  - 返回 htmlData={checklistData, responses}

- [x] 2.3 实现 `format_to_docx(checklist_data)` round-trip 方法

## 3. 前端双模式组件

- [x] 3.1 创建 `GtA112DualChecklist.vue` — 顶层编排
  - Props: wpId, readonly
  - State: activeMode('html'|'docx'), checklistData, responses, loading, docxDirty
  - el-segmented 模式切换（默认"结构化视图"）
  - onMounted 加载 render-config

- [x] 3.2 实现 HTML 模式 — 头部信息卡
  - el-descriptions 渲染：被审计单位、截止日、业务分类(radio)、首次承接(radio)
  - 数据来源 checklistData.header + responses.header

- [x] 3.3 实现 HTML 模式 — 进度汇总条
  - 色块统计：适用 N 项(紫) / 不适用 N 项(灰) / 未标记 N 项(橙)
  - 完成度 = (已标记/总项数) 百分比

- [x] 3.4 实现 HTML 模式 — 核查卡片列表
  - 按 category 分组渲染，每组显示标题
  - 每项卡片：序号 + 描述 + 适用性 radio(适用/不适用) + 索引号区域
  - 适用时展开索引号输入(el-autocomplete + GtIndexChip)
  - 不适用时收起索引号区域，卡片半透明
  - 未标记时白底灰边框

- [x] 3.5 实现 HTML 模式 — 第二类动态添加
  - category[1].allow_custom=true 时显示"+ 添加事项"按钮
  - 添加后可编辑描述 + 标记适用性 + 填索引号
  - 存入 responses.custom_items

- [x] 3.6 实现 HTML 模式 — 签字区
  - 4 角色签字卡片（姓名+日期），只读展示
  - 从 project_assignments 自动填充（通过 responses 传入）

- [x] 3.7 实现 HTML 模式 — 自动保存
  - 适用性/索引号变更 debounce 2s 后 POST /workpapers/field-overrides
  - scope: `a112_checklist:{wpId}`

- [x] 3.8 实现 DOCX 模式 — OnlyOffice 编辑器渲染
  - activeMode='docx' 时加载 OnlyOfficeEditor
  - 监听 onDocumentSaved → docxDirty=true
  - OnlyOffice 不可用时 disabled + tooltip

- [x] 3.9 实现模式切换数据同步
  - docx→html 切换：若 docxDirty=true，重新请求 render-config 刷新
  - 刷新期间 loading=true 防重复操作
  - 失败保留上次 checklistData

## 4. Checkpoint

- [x] 4. Checkpoint — 前后端注册正确 + 模式切换渲染 + 适用性标记 + 索引跳转
  - Ensure all tests pass, ask the user if questions arise.

## 5. Property-Based Tests — 前端（fast-check）

- [x] 5. 前端 PBT
  - [ ]* 5.1 Property 1: 模式互斥渲染 — 任意 state 只渲染一个子视图
  - [ ]* 5.2 Property 2: 适用性→UI映射 — applicable='yes'→索引区可见，'no'/'null'→隐藏
  - [ ]* 5.3 Property 3: 索引号渲染一致性 — ref_index 非空→GtIndexChip 渲染
  - [ ]* 5.4 Property 4: DOCX→HTML 切换刷新 — docxDirty=true 时切回 html 必触发 API
  - [ ]* 5.5 Property 5: 响应持久化不丢失 — 切换前后 responses 等价
  - [ ]* 5.6 Property 6: 进度统计正确性 — progress = marked/total

## 6. Property-Based Tests — 后端（hypothesis）

- [x] 6. 后端 PBT
  - [ ]* 6.1 Property 7: 解析输出结构完整性 — 2 categories, cat[0] 14 items, unique IDs
  - [ ]* 6.2 Property 8: Round-Trip — parse→format→parse 等价

## 7. Unit Tests（vitest）

- [x] 7. vitest
  - [ ]* 7.1 注册契约 — htmlRendererRegistry 含 a1-12-dual-checklist，wp_code_overrides 映射正确
  - [ ]* 7.2 组件行为 — 默认 html 模式、模式切换、适用性 radio 交互、进度计算
  - [ ]* 7.3 索引号自动补全 — el-autocomplete fetchSuggestions 调用 wp-index API

## 8. 集成测试

- [x] 8. 集成测试
  - [ ]* 8.1 后端 `test_render_config_a112.py` — render-config 返回正确 A112ChecklistData
  - [ ]* 8.2 Playwright E2E — A1→A1-12 Tab→标记适用→填索引→切 DOCX→切回→验证数据

## 9. Final Checkpoint

- [x] 9. Final — 全部测试通过，前后端注册一致
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- **不复用 GtChecklistTable**：A1-12 是 14 项适用性核查，用专属卡片式 UI
- 后端 hypothesis PBT 使用 `@settings(max_examples=5)`
- 新增 componentType 必须同步更新 VALID_COMPONENT_TYPES
- OnlyOffice 开发环境 JWT_ENABLED=false
- 索引号自动补全复用 GtA1Dashboard 已实现的 getWpIndex + queryWpCodes 模式
- Tasks marked with `*` are optional
