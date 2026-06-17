# Implementation Plan

## P0: 核心渲染（必做）

- [x] 1. 后端: componentType 路由注册
  - 在 `_WP_CODE_OVERRIDE` 加 `"A1-15": "checklist-table"` 和 `"A1-16": "checklist-table"`
  - 在 `VALID_COMPONENT_TYPES` 加 `"checklist-table"`
  - 跑现有 `test_wp_classification_service.py` 确认无回归
  - 新增测试 `test_derive_component_type_a1_15/16_returns_checklist_table`
  - _Requirements: 1.1, 1.2, 2.1_

- [x] 2. 后端: docx 核对表解析器 (`backend/app/services/checklist_docx_parser.py`)
  - 解析 A1-15: 跳过表1封面，表2→toc(35章节)，表3→sections
  - 解析 A1-16: 跳过前9行，14物理列→3逻辑列(相邻去重)
  - 条目分类(精确判定规则):
    - actionable(主条目): 非合并行 + 有准则索引号(col0非空) → 需要填 Y/N（实证~570行）
    - guidance(子项): 合并单元格行且 a/b/c/d 开头 → 挂到最近上方 actionable 的 children
    - header(小节标题): 合并单元格且非 a~j 开头 → 纯结构分隔
  - 注意: "有数字编号开头"不是 actionable 的必要条件(如 `[CAS 30.2(1)] a. 资产负债表` 也是 actionable)，判定标准是"非合并行+有准则索引"
  - 输出: `{sections:[{id,title,items:[{id,type,standard_ref,content,children:[]}]}], toc, stats:{total_actionable,total_guidance,total_sections}}`
  - 全局 mtime 缓存
  - 单测: A1-15 解析出 35 章节, ~570 actionable 条目, ~145 guidance 子项; A1-16 类似
  - _Requirements: 2.1_

- [x] 3. 后端: DB 迁移 V085 + CRUD 端点
  - `backend/migrations/V085__checklist_responses.sql`: checklist_responses 表(wp_id+item_id 唯一)
  - `backend/app/routers/checklist_responses.py`: GET/PUT 端点
  - 章节适用性持久化: 用特殊 item_id 前缀 `TOC-S01` 存章节级 applicable(Y/N)，或存在 working_paper.parsed_data.section_applicability 中(轻量)
  - 注册到 `router_registry/workpaper.py`
  - _Requirements: 2.2, 2.3_

- [x] 4. 后端: render-config 集成
  - `wp_render_config.py` 的 componentType 分支加 `checklist-table` 逻辑
  - 返回 `{template: 全局缓存解析结果, responses: 该 wp 的用户填写数据}`
  - in-process httpx 验证端点返回正确数据
  - _Requirements: 2.1, 2.2_

- [x] 5. 前端: htmlRendererRegistry 注册
  - `HtmlComponentType` union 加 `'checklist-table'`
  - REGISTRY_LIST 加 entry: `{componentType:'checklist-table', component:lazy(GtChecklistTable), icon:'✅', label:'核对表', emits:['save']}`
  - 现有 vitest (`htmlRendererRegistry.spec.ts`) 更新
  - _Requirements: 2.1_

- [x] 6. 前端: GtChecklistTable.vue 组件
  - 布局: 左侧目录导航(35章节树) + 右侧核对表主体(当前章节)
  - 条目分类渲染:
    - **主条目**(type=actionable): 完整行 = 索引号 | 正文 | Y/N/NA 下拉 | 备注 | 底稿索引
    - **提示性子项**(children): 默认折叠在主条目下，点击展开灰色缩进显示，不可编辑不重复填写
    - **小节标题**(type=header): 加粗分隔行，不可交互
  - 章节适用性弹窗: 首次打开弹窗让用户勾选本项目适用章节(如无保险→跳 4.6)，不适用章节灰显折叠
  - 进度: 仅计算 actionable 条目的已填/总数（不含提示子项）
  - 自动保存: debounce 2s 调 PUT 端点
  - 适用性选择后变色(Y=绿底/N=红底/NA=灰底)
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 7. 集成验证
  - getDiagnostics 前后端无报错
  - Playwright: 打开 A1-15 底稿 → 看到目录导航 + 核对表内容 → 填写结论 → 刷新保持
  - 回归: 打开 A4(xlsx 程序表) 仍正常走 a-program-console
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

## P1: 搜索与批量（建议做）

- [x] 8. 全局搜索: 按条目文本/准则索引过滤+高亮
- [x] 9. 章节批量标记: 整章节"全部适用"按钮
- [x] 10. 筛选视图: 仅看未填/仅看"不适用"

## P2: 跨底稿联动（可选）

- [ ]* 11. 跨底稿联动服务
  - `checklist_linkage_service.py` 监听 WORKPAPER_SAVED
  - 匹配 `checklist_responses.linked_wp_code` 自动标记 auto_completed
  - 前端绿色徽章显示
