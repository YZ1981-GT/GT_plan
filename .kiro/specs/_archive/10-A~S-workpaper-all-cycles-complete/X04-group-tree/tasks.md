# Implementation Plan: Group Tree Architecture

## Overview

基于 projects 表三字段（company_code / parent_company_code / ultimate_company_code）实现集团架构树形动态构建。Phase 1 聚焦只读树形展示+搜索定位+批量导入。后端复用已有 `consol_tree_service.py` 扩展 `build_tree_by_codes` 方法（按三代码构建），暴露 `GET /api/projects/tree` 端点；前端 composable 只做渲染/搜索/筛选。批量导入端点用独立 prefix `/api/batch-projects/`。

## Tasks

- [x] 1. 扩展后端树形构建服务 + 前端渲染 composable
  - [x] 1.1 扩展 `backend/app/services/consol_tree_service.py`，新增 `build_tree_by_codes` 方法（按三代码构建，区别于现有 `build_tree` 的 parent_project_id 模式）
    - 按 ultimate_company_code 分组（森林，多棵树）
    - 按 parent_company_code → company_code 匹配建立父子关系
    - 按 audit_period_end 年份过滤
    - company_code 为空 → 排除进独立分组
    - ultimate_company_code 为空 → 独立分组
    - parent 指向不存在 → isDetached 挂 ultimate 根下
    - 循环引用检测（visited set）→ 打断 + isCycleBreak 标记
    - **扩展 TreeNode dataclass 加容错/展示标记字段**：isDetached/isIndependent/isCycleBreak/status/report_scope（现有 TreeNode 只有 project_id/company_code/company_name/parent_company_code/ultimate_company_code/consol_level/children）
    - **扩展 to_dict（或新增 to_dict_v2）输出这些新字段**，否则前端拿不到 isDetached 等标记
    - 保留现有 `build_tree`/`find_node`/`get_descendants`/`to_dict` 不动（11 个 consol 服务依赖，绝不改签名）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 2.3, 2.4_

  - [x] 1.2 新增 `GET /api/projects/tree?year=N&scope=consolidated|all` 端点并在 router_registry 注册
    - **注意：与现有 `consol_worksheet.py` 的 `GET /tree?project_id=X`（单合并项目内部树）不同**——本端点是全局森林（所有合并项目按 ultimate 分组成多棵树，无单一 root project_id），是新增端点不是复用
    - 查项目（可按 report_scope/year 过滤）→ 调 build_tree_by_codes → 返回树形 JSON
    - 静态路径 `tree` 在通配 `/{project_id}` 之前注册
    - _Requirements: 1.1, 3.1_

  - [x] 1.3 创建 `audit-platform/frontend/src/composables/useGroupTree.ts`（渲染/搜索/筛选）
    - 调 `GET /api/projects/tree` 获取构建好的树形 JSON（不重复 build）
    - 定义 TreeNode / GroupTree TS 接口（与后端 to_dict 输出对齐）
    - 确认前端 Project/TreeNode 类型含 company_code/parent_company_code/ultimate_company_code
    - filterTree 搜索方法 + 视图状态管理
    - _Requirements: 1.1, 5.1_

  - [x]* 1.4 Property test: All valid projects appear in tree (Property 1)
    - **Property 1: All valid projects appear in tree**
    - hypothesis (max_examples=5): 任意非空 company_code + 非空 ultimate 项目必出现在对应 GroupTree 中恰好一次
    - **Validates: Requirements 1.1**

  - [x]* 1.5 Property test: Ultimate grouping invariant (Property 2)
    - **Property 2: Ultimate grouping invariant**
    - hypothesis (max_examples=5): 同一 ultimate 的项目必在同一 GroupTree，不出现在其他树
    - **Validates: Requirements 1.2**

  - [x]* 1.6 Property test: Parent-child relationship correctness (Property 3)
    - **Property 3: Parent-child relationship correctness**
    - hypothesis (max_examples=5): parent_company_code 匹配 Q.company_code 且无循环 → P 是 Q 后代
    - **Validates: Requirements 1.3**

  - [x]* 1.7 Property test: Year filtering isolation (Property 4)
    - **Property 4: Year filtering isolation**
    - hypothesis (max_examples=5): 指定年份构建的树只含该年份项目
    - **Validates: Requirements 1.4, 1.5**

  - [x]* 1.8 Property test: Invalid field routing to independent group (Property 5)
    - **Property 5: Invalid field routing to independent group**
    - hypothesis (max_examples=5): company_code 空或 ultimate 空 → 进 independentNodes 不在 groupTrees 中
    - **Validates: Requirements 2.2, 2.4**

  - [x]* 1.9 Property test: Detached node handling (Property 6)
    - **Property 6: Detached node handling**
    - hypothesis (max_examples=5): parent 指向不存在企业 → isDetached=true 且为 ultimate 根直接子节点
    - **Validates: Requirements 2.1**

  - [x]* 1.10 Property test: Cycle detection terminates and marks (Property 7)
    - **Property 7: Cycle detection terminates and marks**
    - hypothesis (max_examples=5): 循环引用 → 函数终止 + 至少一个 isCycleBreak=true
    - **Validates: Requirements 2.3**

- [x] 2. Checkpoint - 确保树形构建核心逻辑测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. ConsolidationHub 树形展示改造
  - [x] 3.1 改造 `audit-platform/frontend/src/views/ConsolidationHub.vue`，替换卡片网格为 el-tree
    - 引入 useGroupTree composable
    - 按 ultimate 分组每棵树一个 el-tree 实例
    - 根节点显示最终控制方名称 + 企业代码
    - 节点显示企业名称、代码、状态标签
    - 节点点击导航到 `/projects/:id/consolidation`
    - 保留顶部统计概览区域（合并项目数、子公司数等）
    - 独立节点分组单独展示
    - UI 中文
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x]* 3.2 Property test: Tree node data preservation (Property 8)
    - **Property 8: Tree node data preservation**
    - fast-check: 树中节点的 companyName/companyCode/status 与源数据一致
    - **Validates: Requirements 3.4**

- [x] 4. Projects.vue 树形视图切换
  - [x] 4.1 在 `audit-platform/frontend/src/views/Projects.vue` 增加"树形"视图模式
    - viewMode radio-group 增加 'tree' 选项（与"列表"/"按客户"并列）
    - 树形视图使用 el-tree + useGroupTree
    - 视图模式持久化到 localStorage（key: `gt-project-view-mode`）
    - 节点点击导航到项目详情页
    - UI 中文
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [x]* 4.2 Property test: View mode persistence round-trip (Property 15)
    - **Property 15: View mode persistence round-trip**
    - vitest: 写入 localStorage 后读回值一致
    - **Validates: Requirements 4.5**

- [x] 5. 树形搜索与高亮定位
  - [x] 5.1 在 useGroupTree 中实现 filterTree 方法 + ConsolidationHub/Projects 接入搜索
    - el-tree filter-node-method 实时模糊匹配企业名称和代码（case-insensitive）
    - 匹配节点祖先自动展开
    - 匹配文字高亮（node label render-content）
    - 无匹配结果显示"未找到匹配企业"空状态
    - 清空搜索恢复默认展开状态
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 4.4_

  - [x]* 5.2 Property test: Search filter correctness (Property 9)
    - **Property 9: Search filter correctness**
    - fast-check: 节点可见 iff 自身或后代的 companyName/companyCode 含搜索串
    - **Validates: Requirements 5.1, 5.2**

- [x] 6. Checkpoint - 确保前端树形展示+搜索测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. 扩展现有批量建项模板 + 预校验（基于 `batch_project_service.py`）
  - **现状**：已有 `backend/app/services/batch_project_service.py`（generate_template/parse_and_import/export_projects）+ `backend/app/routers/batch_project.py`（prefix=/api/projects，已注册 batch-template/batch-import/batch-export）。前端 `BatchImportDialog.vue` 已接入。本组任务是**扩展**，不新建文件不改端点路径。
  - [x] 7.1 扩展 `batch_project_service.generate_template`：模板加"上级企业代码(parent)"/"最终控制方代码(ultimate)"两列
    - 在现有 7 列（客户名称/企业代码/项目简称/审计年度/项目类型/会计准则/报表类型）后追加 2 列
    - 说明事项 sheet 补充两代码字段填写规则
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 7.2 新增 `batch_project_service.validate_batch`（dry-run 预校验，不入库）
    - 复用 parse_and_import 的解析+USCC 校验逻辑（抽公共解析函数）
    - 解析 parent_company_code/ultimate_company_code
    - 同批次重复 company_code 检测
    - 同批次内 parent-child 互引解析 + 循环引用检测（调 consol_tree_service.build_tree_by_codes 构建预览）
    - 返回 tree_preview + 行级 errors，绝不写库
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 7.3, 7.6_

  - [x] 7.3 在 `batch_project.py` 新增 `POST /api/projects/batch-validate` 端点（同 router 内，复用 prefix）
    - _Requirements: 8.1_

  - [x]* 7.4 Property test: USCC format validation (Property 11)
    - **Property 11: USCC format validation**
    - hypothesis (max_examples=5): 复用现有 `uscc_validator.validate_uscc`，18字符合规→True 含 I/O/Z/S/V→False
    - **Validates: Requirements 7.3**

  - [x]* 7.5 Property test: Batch duplicate detection (Property 12)
    - **Property 12: Batch duplicate detection**
    - hypothesis (max_examples=5): 含重复 company_code 的批次 → 拒绝 + 报重复行号
    - **Validates: Requirements 7.6**

  - [x]* 7.6 Property test: Batch validation dry-run no persistence (Property 13)
    - **Property 13: Batch validation dry-run (no persistence)**
    - hypothesis (max_examples=5): validate_batch 调用后 DB project count 不变
    - **Validates: Requirements 8.1**

  - [x]* 7.7 Property test: Batch validation error blocking (Property 14)
    - **Property 14: Batch validation error blocking**
    - hypothesis (max_examples=5): 含非法 company_code 行 → valid=false + errors 非空
    - **Validates: Requirements 8.2, 8.4**

- [x] 8. 扩展 `parse_and_import` 支持三代码 + 自动建合并根项目
  - [x] 8.1 扩展 `batch_project_service.parse_and_import`
    - 解析并写入 parent_company_code/ultimate_company_code 到 Project
    - 同批次内 parent-child 互引（A.parent 指向 B.company_code，B 尚未入库——按 company_code 二次解析填 parent_project_id）
    - ultimate 对应 consolidated 项目不存在 → 自动创建（项目名默认取 ultimate 企业名）
    - 现有 batch-import 端点签名不变
    - _Requirements: 7.1, 7.2, 7.4, 7.5_

  - [x]* 8.2 Property test: Batch intra-batch parent-child resolution (Property 16)
    - **Property 16: Batch intra-batch parent-child resolution**
    - hypothesis (max_examples=5): 批次内 A.parent = B.company_code → 导入后树形 A 是 B 子节点
    - **Validates: Requirements 7.1, 7.2**

- [x] 9. （已合并入 Task 7.1 — 模板下载端点 `GET /api/projects/batch-template` 已存在，仅扩展列）

- [x] 10. Checkpoint - 确保后端批量建项扩展测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. 扩展现有 `BatchImportDialog.vue` 加预校验步骤
  - **现状**：`audit-platform/frontend/src/components/wizard/BatchImportDialog.vue` 已有（下载模板/上传/导入结果三步，调 /api/projects/batch-template 和 batch-import）。本任务是**扩展**，不新建。
  - [x] 11.1 在 BatchImportDialog 上传后增加预校验步骤
    - 上传 Excel → 先调 `POST /api/projects/batch-validate` → 展示树形预览 + 错误标注
    - 错误行红色标注 + 错误原因（复用现有 failures 表）
    - "确认导入"按钮预校验通过后才可用 → 调现有 batch-import
    - 导入成功后 emit success（Projects.vue 已监听刷新）
    - UI 中文
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 6.1_

  - [x] 11.2 ConsolidationHub 接入 BatchImportDialog
    - Projects.vue 已接入（无需改）；ConsolidationHub 添加"批量建项"按钮触发同一弹窗
    - 导入成功后刷新树形
    - _Requirements: 7.5_

- [x] 12. 合并范围校对功能
  - [x] 12.1 后端实现 `GET /api/consolidation/{project_id}/scope-diff` 和 `POST /api/consolidation/{project_id}/sync-scope`
    - scope-diff: 返回 in_tree_not_scope / in_scope_not_tree 集合差
    - sync-scope: **仅增量添加**树形子企业到 consol_scope 表（in_tree_not_scope），**不自动删除** scope 中多出条目（用户确认后执行）
    - 在 router_registry 注册
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x]* 12.2 Property test: Scope diff set-difference correctness (Property 10)
    - **Property 10: Scope diff set-difference correctness**
    - hypothesis (max_examples=5): T\S 和 S\T 计算正确
    - **Validates: Requirements 9.2, 9.3**

  - [x] 12.3 前端合并范围差异展示与同步
    - ConsolidationHub 根节点差异警示标签"⚠️ 合并范围差异"
    - 点击展示差异明细弹窗（待纳入 / 待移除）
    - "一键同步到合并范围"按钮（用户确认后执行）
    - 差异查询失败静默降级不阻塞树形
    - UI 中文
    - _Requirements: 9.2, 9.3, 9.4, 9.5_

- [x] 13. Final checkpoint - 全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Phase 2 — 体验增强（拖拽调整层级 + 持股比例/合并方式可视化）

- [x]* 14. 树形节点持股比例与合并方式可视化
  - [x]* 14.1 树形节点标签增加持股比例 badge 和合并方式 tag
    - 从 consolidation_company 表查 shareholding / consol_method
    - 节点右侧显示"100%"蓝色 badge + "全资/控股/权益法"小 tag
    - 无持股数据时不显示（graceful degradation）
    - UI 中文
    - _Requirements: Phase 2 增强_

  - [x]* 14.2 集团树根节点统计信息增强
    - 根节点下方显示：全资子公司 N 家 / 控股 N 家 / 权益法 N 家
    - 持股比例分布 mini 柱状图（可选）
    - _Requirements: Phase 2 增强_

- [x]* 15. 树形拖拽调整层级
  - [x]* 15.1 el-tree 启用 `draggable` + drop 规则校验
    - 拖拽节点到新父节点 → 修改该项目的 parent_company_code
    - drop 规则：不可拖到自己后代下（禁循环）、不可跨 ultimate 树拖拽
    - 拖拽完成后调 API 更新 parent_company_code
    - 成功后树形自动重建
    - _Requirements: Phase 2 增强_

  - [x]* 15.2 后端 `PATCH /api/projects/{project_id}/parent-code` 端点
    - 更新 parent_company_code 字段
    - 校验不形成循环引用（后端二次校验）
    - 在 router_registry 注册
    - _Requirements: Phase 2 增强_

  - [x]* 15.3 拖拽操作确认弹窗
    - 拖拽释放后弹确认："将 [企业A] 的上级调整为 [企业B]，是否确认？"
    - 取消则恢复原位
    - UI 中文
    - _Requirements: Phase 2 增强_

- [x]* 16. 集团架构变更历史
  - [x]* 16.1 记录 parent_company_code 变更日志
    - 每次修改 parent_company_code 写入 app_audit_log（who/when/old/new）
    - 树形节点右键菜单"查看层级变更历史"
    - _Requirements: Phase 2 增强_

- [x] 17. 侧边栏"合并"菜单条件显示
  - [x] 17.1 ThreeColumnLayout.vue navItems 中"合并"菜单增加 computed 条件
    - 查询是否存在 report_scope='consolidated' 的项目（复用 projectStore 或首次 API 调用缓存结果）
    - 无合并项目时：隐藏菜单 或 保留但点击后 ConsolidationHub 显示空态+引导新建
    - 有合并项目时：正常显示
    - _Requirements: 侧边栏合并菜单条件显示_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 前端测试用 vitest，后端测试用 python -m pytest
- hypothesis PBT 统一 max_examples=5
- 新后端端点必须在 router_registry 注册（静态路径在通配路径之前）
- 树形构建逻辑放后端（复用 consol_tree_service.build_tree_by_codes），前端 composable 只渲染/搜索/筛选；批量导入预校验树形预览由前端纯函数构建（数据来自 Excel 非 DB）
- 合并范围表是 consol_scope（非 companies）；不动 ConsolidationIndex 已有集团架构 Tab
- 批量导入端点沿用现有 prefix `/api/projects/batch-*`（batch_project.py router，已注册在通配 `/{project_id}` 之前，不另造独立 prefix）
- 所有 UI 组件中文化
