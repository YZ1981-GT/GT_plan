# Implementation Plan: 底稿 HTML 渲染器（通用组件）

## Overview

将 1788 单体真底稿（A/B/C/D/E 共 1346 sheet）从 Univer Sheets 切换为纯 HTML 通用组件渲染。按 Week 1-15 分阶段实施：P0 数据模型 → A 程序表 → B 目录 → E 控制测试 → D 检查表 → C 附注 → 联调。后端 Python（FastAPI + openpyxl），前端 TypeScript（Vue 3 + Element Plus）。

## Tasks

- [x] 1. Phase 1：P0 数据模型与基础端点（Week 1-2）
  - [x] 1.1 创建 Alembic 迁移：新建 workpaper_template_version 表
    - 按 design §4.2 DDL ① 创建表 + UNIQUE INDEX `uq_workpaper_template_version_current`
    - 插入初始版本记录 `v2025-R5`（is_current=TRUE）
    - _Requirements: 3.0.4（模板版本管理）_

  - [x] 1.2 创建 Alembic 迁移：扩展 workpaper_sheet_classification 表 + 6 字段
    - 按 design §4.2 DDL ③ 添加 class/is_real_workpaper/exclude_from_archive/exclude_from_progress/is_static_doc/scope/delegated_module/template_version_id/render_schema_path
    - 创建索引 idx_wpsc_class_scope / idx_wpsc_template_version_real / idx_wpsc_wp_code_version
    - _Requirements: 3.0.2（真假底稿）+ 3.0.5（合并剔除 scope）_

  - [x] 1.3 创建 Alembic 迁移：projects 表加列 template_version_id + project_workpaper_sheet_override 表
    - 按 design §4.2 DDL ② ④ 创建 projects.template_version_id FK + project_workpaper_sheet_override 表 + UNIQUE 约束
    - _Requirements: 3.0.3（项目实例层级 L5）+ 3.0.4_

  - [x] 1.4 创建 Alembic 迁移：workpaper_sheet_version_mapping 表（P1 预留）
    - 按 design §4.2 DDL ⑤ 创建表结构（本阶段仅建表不填数据）
    - _Requirements: 3.0.4（跨版本映射 P1）_

  - [x] 1.5 创建 ORM 模型：WorkpaperTemplateVersion + ProjectWorkpaperSheetOverride
    - `backend/app/models/workpaper_template_version.py`（新）
    - `backend/app/models/project_wp_sheet_override.py`（新）
    - 扩展 `backend/app/models/workpaper_models.py` 添加 6 字段 Mapped 声明
    - _Requirements: 3.0.2, 3.0.3, 3.0.4_

  - [ ] 1.6 实现 wp_classification_service 扩展
    - 扩展 `backend/app/services/wp_classification_service.py`
    - 新增 `get_classification(wp_code, project_id, template_version_id)` 方法
    - 新增 `derive_component_type(classification)` 方法（9 类 → componentType 白名单映射）
    - 支持 project_workpaper_sheet_override 优先级合并
    - _Requirements: 1.2（9 类全覆盖）+ 3.9（决策树禁止 Univer 兜底）_

  - [x]* 1.7 Property 1 PBT 测试：9 类全覆盖归类 → componentType 路由
    - **Property 1: 9 类全覆盖归类 → componentType 路由**
    - **Validates: Requirements 1.2 + 3.0.1 + 3.9**
    - `backend/tests/properties/test_classification_coverage.py`
    - hypothesis 生成 (sheet_name, sheet_features) → 断言 class ∈ 白名单 + componentType ∈ 白名单

  - [x] 1.8 实现 wp_template_version_service
    - `backend/app/services/wp_template_version_service.py`（新）
    - `get_current_version()` / `list_versions()` / `get_version_by_id()`
    - _Requirements: 3.0.4_

  - [x] 1.9 实现 wp_render_schema_service
    - `backend/app/services/wp_render_schema_service.py`（新）
    - `load_schema(wp_code, template_version_id)` 从 `backend/data/wp_render_schema/{wp_code}.yaml` 加载
    - `merge_with_override(schema, project_override)` 项目级覆盖合并
    - _Requirements: 2.2 原则 2（配置驱动）_

  - [x] 1.10 创建 render-config 路由端点
    - `backend/app/routers/wp_render_config.py`（新）
    - `GET /api/workpapers/{wp_id}/render-config` 按 design §5.1.1 实现
    - 注册到 `backend/app/router_registry/workpaper.py`
    - _Requirements: 1.2, 3.0.3, 3.0.5_

  - [x] 1.11 创建 wp-classifications 路由端点
    - `backend/app/routers/wp_classification.py`（新）
    - `GET /api/wp-classifications` 按 design §5.1.4 实现
    - 注册到 router_registry
    - _Requirements: 1.2_

  - [x] 1.12 创建 wp-template-versions 路由端点
    - `backend/app/routers/wp_template_version.py`（新）
    - `GET /api/wp-template-versions` + `GET /api/wp-template-versions/current`
    - 注册到 router_registry
    - _Requirements: 3.0.4_

  - [x]* 1.13 Property 7 PBT 测试：项目实例覆盖与 scope 路由
    - **Property 7: 项目实例覆盖与 scope 路由**
    - **Validates: Requirements 3.0.3 + 3.0.5**
    - `backend/tests/properties/test_render_config_merge.py`
    - hypothesis 生成 (override, base_classification) → 断言合并函数确定性 + scope 路由正确

  - [x]* 1.14 Property 5 PBT 测试：真假底稿与完成率派生
    - **Property 5: 真假底稿与完成率派生**
    - **Validates: Requirements 3.0.2**
    - `backend/tests/properties/test_real_workpaper.py`
    - hypothesis 生成 sheet_name → is_real_workpaper 确定性映射 + 完成率分母不含假底稿

- [x] 2. Checkpoint - Phase 1 验证
  - 确保所有迁移可正常 upgrade/downgrade，ORM 模型与 DDL 一致
  - 确保 render-config / wp-classifications / wp-template-versions 端点返回正确数据
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Phase 2：A 程序表中控台 + GtIndexChip + 导出 xlsx（Week 3-4）
  - [x] 3.1 创建 wp_render_schema YAML 样本（A 类）
    - `backend/data/wp_render_schema/D2A.yaml`（应收账款实质性程序表，按 design §6.1 格式）
    - 至少覆盖 3 个 A 类样本（D2A / G7A / E1A）
    - 定义 fixed_cells / dynamic_table / static_text / formulas / merged_cells / cross_refs
    - _Requirements: 2.2 原则 2（配置驱动）+ 4.3.1（方案 C 还原约束）_

  - [x] 3.2 实现前端 useWpRenderer composable
    - `audit-platform/frontend/src/composables/useWpRenderer.ts`（新）
    - 按 design §3.11 实现：load renderConfig / componentType computed / SSE 订阅 cross-ref:updated / onUnmounted 清理
    - _Requirements: 1.2（路由分发）+ 3.11.4（跨底稿引用传播）_

  - [x] 3.3 实现前端 useWpClassification composable
    - `audit-platform/frontend/src/composables/useWpClassification.ts`（新）
    - 按 design §3.11 实现：9 类归属 + scope 路由判定 + isRealWorkpaper / excludeFromArchive 派生
    - _Requirements: 1.2, 3.0.2, 3.0.5_

  - [x] 3.4 实现前端 GtWpRenderer 顶层路由组件
    - `audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue`（新）
    - 按 design §3.2 实现 Props/Emits + componentType 分发到对应子组件
    - 接入 useWpDetailGuard 三态（loading/error/ready）
    - 遵循 setup const 声明顺序铁律 + 不加顶层 v-if 守卫
    - _Requirements: 1.2（9 类路由）_

  - [x] 3.5 实现前端 parseIndexRef 工具函数
    - `audit-platform/frontend/src/utils/parseIndexRef.ts`（新）
    - 11 命名空间路由解析（wp/sheet/cell/Note/TB/Adj/Att/EQCR/Calc/Sample/Confirm）
    - 4 层级跳转语义（cell→1, sheet→2, wp→3, module→4）
    - 9 种边缘 case 处理（中文索引/空格/大小写/多目标/不存在/被裁剪/跨项目/GT_Custom/空 sheet）
    - _Requirements: 3.11.8 + 3.11.9 + 3.11.10_

  - [ ]* 3.6 Property 6 PBT 测试：跨底稿索引解析与跳转语义
    - **Property 6: 跨底稿索引解析与跳转语义**
    - **Validates: Requirements 3.11.8 + 3.11.9 + 3.11.10**
    - `audit-platform/frontend/src/utils/__tests__/parseIndexRef.test.ts`
    - fast-check 生成 ref 字符串 → 断言合法输入返回 {ns, layer, target} + 非法输入返回 null + layer 由 ns 决定性派生

  - [x] 3.7 实现前端 GtIndexChip 组件
    - `audit-platform/frontend/src/components/workpaper/GtIndexChip.vue`（新）
    - 按 design §3.8 实现 Props/Emits + 调用 parseIndexRef + 调 /api/wp-index-resolve 校验
    - 灰显/tooltip/hover 菜单/路由跳转
    - _Requirements: 3.11.8（4 层级跳转）+ 3.11.10（9 边缘 case）_

  - [x] 3.8 实现后端 wp-index-resolve 端点
    - `GET /api/wp-index-resolve` 按 design §5.1.6 实现
    - 解析 ref → 查 wp_index 校验存在性 → 返回 resolved 结构
    - _Requirements: 3.11.9（11 命名空间）_

  - [x] 3.9 实现前端 GtAProgramConsole 组件
    - `audit-platform/frontend/src/components/workpaper/GtAProgramConsole.vue`（新）
    - 按 design §3.3 实现：程序行展开/状态切换/类别筛选/批量裁剪/进度条
    - 关联底稿索引号渲染为 GtIndexChip
    - 裁剪决策写回 ProcedureInstance.status='not_applicable'
    - _Requirements: 1.1（D2A 痛点 7 项）+ 3.2（A 程序表详细需求）_

  - [x] 3.10 实现后端 save 端点
    - `POST /api/workpapers/{wp_id}/save` 按 design §5.1.2 实现
    - JSON Schema 校验 + merge 到 parsed_data['html_data'] + cross_ref_service.detect_changes + SSE 发布
    - schema_version 冲突返回 409
    - _Requirements: 2.2 原则 4（决策可追踪）+ 3.11.4（跨底稿引用传播）_

  - [x]* 3.11 Property 4 PBT 测试：跨底稿引用传播
    - **Property 4: 跨底稿引用传播**
    - **Validates: Requirements 3.11.4 + 3.11.5 + 3.11.6**
    - `backend/tests/properties/test_cross_ref_propagation.py`
    - hypothesis 生成 (wp_code, cell, value_change) → 断言 SSE 发布 + affected 列表包含所有引用目标

  - [x] 3.12 实现 wp_xlsx_export_service
    - `backend/app/services/wp_xlsx_export_service.py`（新）
    - 按 design §6.2 实现 4 路径写入策略（fixed_cells / dynamic_table / formulas 跳过 / static_text 跳过）
    - openpyxl 加载模板 + BytesIO 复制 + 保留 styles/formulas/merged_cells
    - asyncio.run_in_executor 包装（6000 并发安全）
    - _Requirements: 4.3.1.a-g（方案 C 还原 7 项约束）_

  - [x] 3.13 实现 export-xlsx 路由端点
    - `POST /api/workpapers/{wp_id}/export-xlsx` 按 design §5.1.3 实现
    - 返回 attachment xlsx / 模板缺失 500 / 必填字段空 422
    - _Requirements: 2.1（一键导出 Excel）_

  - [x]* 3.14 Property 2 PBT 测试：方案 C 字符级还原
    - **Property 2: 方案 C 字符级还原（导出 xlsx ≡ 致同模板手填）**
    - **Validates: Requirements 4.3.1.a-g + 5.3**
    - `backend/tests/exports/test_xlsx_diff.py`
    - hypothesis 生成 html_data → 导出 xlsx → 与 fixture 字符级 diff = 空集

  - [x]* 3.15 Property 3 PBT 测试：公式与合并单元格保留不变量
    - **Property 3: 公式与合并单元格保留不变量**
    - **Validates: Requirements 4.3.1.b + 4.3.1.c**
    - `backend/tests/exports/test_invariants.py`
    - 加载模板 → 导出 → 重载 → 断言 formula_cells 集合恒等 + merged_ranges 集合恒等

- [x] 4. Checkpoint - Phase 2 验证
  - A 程序表中控台可正常渲染 + 程序裁剪写回 + 导出 xlsx 字符级 diff 通过
  - GtIndexChip 11 命名空间 × 9 边缘 case 全覆盖
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Phase 3：B 底稿目录（Week 5）
  - [x] 5.1 创建 wp_render_schema YAML（B 类）
    - `backend/data/wp_render_schema/B-template.yaml`（B 类共享模板）
    - 定义 preparation_info_fields + navigation_table columns
    - _Requirements: 3.3（B 底稿目录详细需求）_

  - [x] 5.2 实现前端 GtBIndex 组件
    - `audit-platform/frontend/src/components/workpaper/GtBIndex.vue`（新）
    - 按 design §3.4 实现：编制信息自动填充（project meta + user profile）+ 索引导航行跳转 + "无需打印"批量切换
    - 索引导航行渲染 GtIndexChip（同底稿 sheet 切换 / 跨底稿 router.push）
    - _Requirements: 3.3（B 类 148 sheet）_

  - [x]* 5.3 B 类单元测试
    - 编制信息自动填充测试（project meta 缺失时友好降级）
    - 索引导航行跳转测试
    - _Requirements: 3.3_

- [x] 6. Phase 4：E 控制测试（Week 6-7）
  - [x] 6.1 创建 wp_render_schema YAML（E 类）
    - 至少覆盖 3 种 test_type（summary / single / evaluation_step）
    - 定义 steps / hints / conclusion 结构
    - _Requirements: 3.6（E 控制测试详细需求）_

  - [x] 6.2 实现前端 GtEControlTest 组件
    - `audit-platform/frontend/src/components/workpaper/GtEControlTest.vue`（新）
    - 按 design §3.7 实现：3 种结构路由 + el-steps stepper 6 步骤 + 4 互斥结论 radio
    - 控制有效结论 → emit trigger-procedure-trimming-suggestion → 写入 ProcedureTrimming 建议
    - 风险说明长段折叠展开
    - _Requirements: 3.6（E 类 322 sheet）_

  - [x]* 6.3 E 类单元测试
    - 6 步骤决策树 stepper 校验测试
    - 4 互斥结论测试
    - ProcedureTrimming 联动建议写回测试
    - _Requirements: 3.6_

- [x] 7. Checkpoint - Phase 3+4 验证
  - B 目录编制信息自动填充 + 索引导航跳转正常
  - E 控制测试 stepper + 结论 + ProcedureTrimming 联动正常
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Phase 5：D 检查表 5 子模式（Week 8-10）
  - [x] 8.1 创建 wp_render_schema YAML（D 类 5 子模式）
    - D-table / D-paragraph / D-qa / D-confirmation / D-review 各 1 份样本 YAML
    - 定义 form_type 字段决定子模式路由
    - _Requirements: 3.5（D 类 449 sheet 5 子模式）_

  - [x] 8.2 实现前端 GtDForm 顶层组件 + 子模式路由
    - `audit-platform/frontend/src/components/workpaper/GtDForm/` 目录（新）
    - GtDForm.vue 按 form_type 分发到 5 个子组件
    - 统一 Props/Emits 按 design §3.6
    - _Requirements: 3.5_

  - [x] 8.3 实现 GtDFormTable 子组件（表格型检查）
    - 行项目矩阵 + 关联方/项目动态增删 + 字典下拉
    - ~250 sheet 适用
    - _Requirements: 3.5（D 子模式 1）_

  - [x] 8.4 实现 GtDFormParagraph 子组件（段落型政策）
    - markdown 富文本 + 占位符提示 + 引用文档链接
    - ~19 sheet 适用
    - _Requirements: 3.5（D 子模式 2）_

  - [x] 8.5 实现 GtDFormQA 子组件（是否问答型）
    - radio 选项 + 自动判定（业务模式 → 报表项目分类）
    - ~9 sheet 适用
    - _Requirements: 3.5（D 子模式 3）_

  - [x] 8.6 实现 GtDFormConfirmation 子组件（函证/盘点/访谈）
    - 专属子组件（询证函生成 / 盘点队伍 / 访谈记录）
    - ~109 sheet 适用
    - _Requirements: 3.5（D 子模式 4）_

  - [x] 8.7 实现 GtDFormReview 子组件（复核记录）
    - 电子签 + 时间戳 + 复核状态机
    - ~27 sheet 适用
    - _Requirements: 3.5（D 子模式 5）_

  - [x]* 8.8 D 类单元测试
    - 5 子模式分发测试
    - 业务模式判定（D2-13）输出测试
    - 函证/盘点/访谈专属子组件交互测试
    - _Requirements: 3.5_

- [x] 9. Checkpoint - Phase 5 验证
  - D 类 5 子模式全部可渲染 + 保存 + 导出
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Phase 6：C 附注披露嵌套表 + 附注双源同步（Week 11-13）
  - [x] 10.1 创建 wp_render_schema YAML（C 类）
    - 定义 applicable_standard / sub_tables（4-7 张子表）/ inheritance_rules（子表合计 → 主表行）
    - 覆盖 static_rows / dynamic_rows 两种子表类型
    - _Requirements: 3.4（C 附注披露详细需求）_

  - [x] 10.2 实现前端 GtCNoteTable 组件
    - `audit-platform/frontend/src/components/workpaper/GtCNoteTable.vue`（新）
    - 按 design §3.5 实现：子表增删 + 上市/国企版本切换 + 子表合计 ↔ 主表行实时联动
    - 切换 standard 时保留共有字段值 + 差异字段 ElMessageBox 提示
    - hidden_subtables "不适用"软标记
    - _Requirements: 3.4（C 类 166 sheet）_

  - [x] 10.3 实现附注双源单向同步端点
    - `POST /api/projects/{pid}/disclosure-notes/sync-from-workpaper`（新）
    - C 类 sheet 保存时触发 push 到 disclosure_notes 模块对应 section
    - disclosure_notes 模块加 banner 提示"此数据由底稿同步"
    - _Requirements: 3.11.5 §4.2（附注双源问题）+ design §12.1 推荐选项 A_

  - [x]* 10.4 Property 8 PBT 测试：附注双源单向同步
    - **Property 8: 附注双源单向同步**
    - **Validates: Requirements 3.11.5 §4.2 + design §12.1**
    - `backend/tests/integration/test_disclosure_sync.py`
    - C sheet 保存 → 断言 disclosure_notes 更新 + disclosure_notes 编辑不反向写回 C sheet

  - [x]* 10.5 C 类单元测试
    - 上市 ↔ 国企版本切换时共有字段保留 / 差异字段提示
    - 子表合计变化 → 主表行实时更新（inheritance_rules 校验）
    - _Requirements: 3.4_

- [x] 11. Checkpoint - Phase 6 验证
  - C 附注嵌套表渲染 + 版本切换 + 子表联动 + 附注同步正常
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Phase 7：H 静态展示 + I 跳过 + 辅助组件（Week 14）
  - [x] 12.1 实现前端 GtHStaticDoc 组件
    - `audit-platform/frontend/src/components/workpaper/GtHStaticDoc.vue`（新）
    - 只读 markdown 渲染（marked + dompurify）
    - 104 sheet 适用
    - _Requirements: 3.7（H 辅助说明）_

  - [x] 12.2 实现 SkippedSheetPlaceholder 组件
    - I 类 243 sheet 跳过渲染 + 提示"此 sheet 不参与渲染"
    - _Requirements: 3.8（I 占位跳过）_

  - [x] 12.3 实现前端 GtTraceabilityDialog 组件
    - `audit-platform/frontend/src/components/workpaper/GtTraceabilityDialog.vue`（新）
    - 按 design §3.9 实现：反向溯源 + 正向影响双路调用
    - _Requirements: 3.11.6（报表附注溯源链路）_

  - [x] 12.4 实现后端 trace 端点
    - `GET /api/workpapers/trace` 按 design §5.1.7 实现
    - source=report/disclosure/workpaper + direction=upstream/downstream
    - _Requirements: 3.11.6_

  - [x] 12.5 实现前端 GtFormulaPopover 组件
    - 公式溯源 popover（"此值由 X+Y 计算"）
    - 复用既有 advanced-query-enhancements-p1p2 spec 的公式 popover 模式
    - _Requirements: 3.11.5 Layer 1（sheet 内联动）_

  - [x] 12.6 实现前端 useWpRenderSchema composable
    - `audit-platform/frontend/src/composables/useWpRenderSchema.ts`（新）
    - schema 加载 + 校验 + 项目级覆盖合并
    - _Requirements: 2.2 原则 2（配置驱动）_

  - [x]* 12.7 Property 9 PBT 测试：行业特定 sheet 可见性派生
    - **Property 9: 行业特定 sheet 可见性派生**
    - **Validates: Requirements 6.5 待决策点 4 选项 A**
    - `backend/tests/properties/test_industry_visibility.py`
    - hypothesis 生成 (industry_type, sheet_industry_tag) → 断言 visibility 确定性派生

- [x] 13. Phase 8：WorkpaperEditor 集成 + 联调（Week 15）
  - [x] 13.1 扩展 WorkpaperEditor.vue 接入 GtWpRenderer
    - 按 componentType 分发：HTML 类 → GtWpRenderer / Univer 类 → 既有 UniverHost
    - 保留 F/G 类 558 sheet Univer 渲染不动
    - 遵循 setup const 声明顺序铁律 + useWpDetailGuard 三态
    - _Requirements: 1.2（9 类路由分发）_

  - [x] 13.2 扩展 cross-ref:updated 订阅到 A~E 类组件
    - 所有 HTML 类组件接入 eventBus cross-ref:updated 监听
    - onUnmounted 清理监听器（避免内存泄漏）
    - 复用既有 useStaleImpact composable
    - _Requirements: 3.11.4（跨底稿引用传播）+ 3.11.5（联动 4 层架构）_

  - [x] 13.3 实现 generate_wp_render_schema.py 自动化工具
    - `backend/scripts/generate_wp_render_schema.py`（新）
    - 从模板 xlsx 反向解析 schema 草稿（减少手工维护成本）
    - 输出 YAML 到 `backend/data/wp_render_schema/`
    - _Requirements: 2.2 原则 2 + design §10.1 H1 风险缓解_

  - [x] 13.4 批量生成 A~E 类 wp_render_schema YAML
    - 使用 generate_wp_render_schema.py 批量生成
    - 人工审核 + 修正关键字段（dynamic_table 边界 / cross_refs 引用）
    - 目标覆盖 1346 sheet 的 schema（按 wp_code 去重后约 50-80 份 YAML）
    - _Requirements: 2.2 原则 2_

  - [x]* 13.5 集成测试：9 类组件 + 真实模板 + 4 项目数据
    - 使用 4 项目实测数据（陕西华氏/和平药房/辽宁卫生/宜宾大药房）
    - 验证 A/B/C/D/E 5 类组件渲染 + 保存 + 导出完整链路
    - _Requirements: 全篇_

  - [x]* 13.6 性能基准测试
    - HTML 渲染冷启动 ≤ 500ms（D2 18 sheet 整套）
    - 导出 xlsx ≤ 5s（含模板加载 + openpyxl 写入）
    - openpyxl asyncio.run_in_executor + 信号量 ≤ 10 并发
    - _Requirements: design §9.6 性能基准_

- [x] 14. Final Checkpoint - 全量验证
  - 9 类组件全部可路由 + 渲染 + 保存 + 导出
  - 9 条 PBT 属性全部通过
  - 跨底稿引用传播 + 附注双源同步 + 溯源链路正常
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from design §7
- 实施顺序严格按 design §14 优先级：A（最高用户价值）→ B（简单）→ E（中等）→ D（5 子模式）→ C（最复杂）
- F/G 类 558 sheet 保留 Univer 不动，仅扩展 cross-ref:updated 订阅
- 后端 Python 使用 FastAPI + openpyxl + hypothesis（PBT）
- 前端 TypeScript 使用 Vue 3 + Element Plus + fast-check（PBT）
- 所有新 router 必须注册到 `backend/app/router_registry/` 对应分组
