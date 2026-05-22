# Requirements Document — Phase 1 体验断层修复

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-05-21 | 初始起草，基于《平台全局建议书》Phase 1 五项 |

## 依赖矩阵

| 依赖项 | 类型 | 状态 |
|--------|------|------|
| Vue Router | 前端 | ✅ 已有 |
| Element Plus (el-autocomplete/el-dialog) | 前端 | ✅ 已有 |
| useNavigationStack composable | 前端 | ✅ 已有 |
| displayPrefs store | 前端 | ✅ 已有 |
| GtToolbar / GtEditableTable | 前端 | ✅ 已有 |
| useEditingLock composable | 前端 | ✅ 已有 |
| WorkingPaper model (file_version 字段) | 后端 | ✅ 已有（含 409 冲突检测） |
| pypinyin (拼音首字母) | 后端新增依赖 | 🔲 需新增 |
| shortcuts.ts (快捷键管理) | 前端 | ✅ 已有 |
| apiPaths.ts | 前端 | ✅ 已有 |

---

## 一、为什么做（业务痛点）

### 1.1 全局搜索缺失（S-1）
- **痛点**：用户无法快速跳转到任意底稿/科目/报表行，需在侧边栏逐级展开或记住路由路径
- **影响角色**：全部 5 个角色（每天高频使用）
- **技术根因**：无全局 Command Palette 组件，无统一搜索 API 端点

### 1.2 表格字号控制不生效（G-2）
- **痛点**：displayPrefs 切换字号后部分表格不响应（`:style="{ fontSize }"` 被 Element Plus 内部样式覆盖）
- **影响角色**：审计助理（长时间看表格需要调字号）
- **技术根因**：el-table 内部 DOM 层级深，inline style 优先级不够，需 `!important` + `:deep()` 穿透

### 1.3 穿透面包屑导航缺失（A-3）
- **痛点**：TB→AUX→Ledger→AuxLedger→底稿 5 层穿透后，用户迷失位置，Backspace 返回链不直观
- **影响角色**：审计助理（日常穿透操作）
- **技术根因**：useNavigationStack 已实现 push/pop 但无可视化面包屑 UI

### 1.4 工具栏占用数据区域（UI-9）
- **痛点**：表格上方工具栏+信息栏+Tab 栏占 3 行，挤压数据显示区域
- **影响角色**：全部角色（数据密集型操作）
- **技术根因**：GtToolbar 独占一行，刷新/导出/保存按钮未合并到 Tab 栏右侧

### 1.5 并发编辑无版本保护（FE-4）— ✅ 已实现
- **现状**：`working_paper.file_version` 字段已存在，`univer-save` 端点已实现 `expected_version` 参数 + 409 冲突检测
- **残留问题**：前端 WorkpaperEditor 可能未完整消费 409 响应（缺 ConflictDialog 组件），需验证
- **本 spec 范围**：仅补前端 ConflictDialog + 验证前端是否已处理 409

---

## 二、范围边界

### 必做（In Scope）

**F1 全局搜索 Ctrl+K：**
- 全局快捷键 Ctrl+K 唤起 Command Palette 弹窗
- 支持搜索：底稿编号(wp_code) / 科目名称(account_name) / 报表行(report_line) / 项目名称
- 模糊匹配 + 拼音首字母匹配
- 搜索结果点击后跳转到对应页面
- 后端统一搜索 API（聚合多表查询）
- 最近访问记录（最多 10 条，localStorage 持久化）

**F2 表格字号统一：**
- 废弃所有 `:style="{ fontSize }"` 写法
- 统一为 `:class="'gt-tb-font-' + displayPrefs.fontSize"` 动态 class
- 全局 CSS 定义 4 档字号（xs=11px / sm=12px / md=13px / lg=14px）+ `!important` + `:deep()` 穿透
- 确保 el-table th/td .cell 均生效

**F3 穿透面包屑：**
- 在穿透页面顶部显示面包屑导航条
- 格式：`试算表 > 辅助余额 > 明细账 > 辅助明细账 > 底稿D2-1`
- 每个层级可点击直接跳回
- 与 useNavigationStack 联动（读取 stack 生成面包屑）
- 面包屑超过 5 层时折叠中间层级（显示 `...`）

**F4 工具栏合并：**
- GtToolbar 的"刷新/导出/保存"按钮合并到 Tab 栏右侧
- 减少表格上方非数据行数（目标：从 3 行减到 1-2 行）
- 仅影响简单 CRUD 页面（TrialBalance/WorkpaperList/Adjustments 等）
- 保留 GtToolbar 组件但增加 `compact` 模式（单行内联）

**F5 并发编辑版本锁（前端补全）：**
- 后端已实现：`working_paper.file_version` + `univer-save` 端点 409 冲突检测
- 前端需补全：ConflictDialog 组件（显示冲突信息+刷新/强制覆盖按钮）
- 验证 WorkpaperEditor 是否已处理 409 响应，如未处理则补 catch 逻辑
- "强制覆盖"选项（仅 manager/partner/admin 可用）

### 排除（Out of Scope）

- 不涉及全文搜索引擎（Elasticsearch/MeiliSearch），使用 PG LIKE + GIN 索引
- 不涉及暗色模式（Phase 3）
- 不涉及 WebSocket 实时冲突推送（仅保存时校验）
- 不涉及 GtPageHeader 紫色渐变的全局替换（仅工具栏合并）
- 不修改 useEditingLock 的 Redis 锁机制（版本锁是补充层，非替代）
- 不新增后端版本锁逻辑（已存在于 `univer-save` 端点，`file_version` + `expected_version` + 409）

---

## 三、功能需求（EARS 范式）

### F1 全局搜索

- **F1.1** WHEN 用户在任意页面按下 Ctrl+K（Mac: Cmd+K），THE 系统 SHALL 显示全局搜索弹窗（居中，宽度 600px，最大高度 400px）
- **F1.2** WHEN 用户在搜索框输入文字（≥2 字符），THE 系统 SHALL 在 300ms 防抖后调用后端搜索 API 并展示结果列表
- **F1.3** IF 搜索结果为空，THE 系统 SHALL 显示"无匹配结果"提示
- **F1.4** WHEN 用户点击搜索结果项或按 Enter 选中，THE 系统 SHALL 关闭弹窗并跳转到对应页面
- **F1.5** THE 系统 SHALL 在搜索结果中显示类型图标（📋底稿 / 📊科目 / 📄报表 / 📁项目）+ 名称 + 所属项目
- **F1.6** WHEN 搜索弹窗打开时，THE 系统 SHALL 显示最近 10 条访问记录（从 localStorage 读取）
- **F1.7** THE 系统 SHALL 支持键盘导航（↑↓ 选择 + Enter 确认 + Esc 关闭）
- **F1.8** THE 后端搜索 API SHALL 在 500ms 内返回结果（≤50 条，分页不需要）
- **F1.9** THE 搜索 SHALL 支持拼音首字母匹配（如输入 "yszkm" 匹配 "应收账款明细"）

### F2 表格字号统一

- **F2.1** THE 系统 SHALL 定义全局 CSS class `gt-tb-font-xs/sm/md/lg`，分别对应 11/12/13/14px
- **F2.2** WHEN displayPrefs.fontSize 变更时，THE 所有 el-table 的 th .cell 和 td .cell SHALL 立即响应新字号
- **F2.3** THE CSS 规则 SHALL 使用 `:deep()` + `!important` 确保穿透 Element Plus 内部样式
- **F2.4** THE 系统 SHALL 在字号变更后自动触发 el-table `doLayout()` 重新计算列宽

### F3 穿透面包屑

- **F3.1** WHEN 用户通过穿透操作进入子页面时，THE 系统 SHALL 在页面顶部显示面包屑导航条
- **F3.2** THE 面包屑 SHALL 显示完整穿透路径（从起点到当前位置）
- **F3.3** WHEN 用户点击面包屑中的任意层级，THE 系统 SHALL 直接跳转到该层级（跳过中间层）
- **F3.4** IF 面包屑层级超过 5 层，THE 系统 SHALL 折叠中间层级显示 `...`（hover 展开完整路径）
- **F3.5** THE 面包屑 SHALL 与 useNavigationStack 联动（读取 stack 数组生成层级）
- **F3.6** WHEN 用户按 Backspace 返回时，THE 面包屑 SHALL 同步更新（移除最后一层）

### F4 工具栏合并

- **F4.1** THE GtToolbar 组件 SHALL 新增 `compact` prop（Boolean，默认 false）
- **F4.2** WHEN compact=true 时，THE 工具栏 SHALL 渲染为单行内联模式（高度 ≤ 36px）
- **F4.3** THE compact 模式 SHALL 将操作按钮（刷新/导出/保存）渲染到右侧，标题/信息渲染到左侧
- **F4.4** THE 系统 SHALL 在 TrialBalance / WorkpaperList / Adjustments / Misstatements 页面启用 compact 模式
- **F4.5** THE compact 模式 SHALL 减少表格上方非数据行数（从 3 行减到 ≤ 2 行）

### F5 并发编辑版本锁（前端补全）

- **F5.1** ~~THE WorkingPaper 模型 SHALL 新增 `version: Integer` 字段~~ → 已存在 `file_version`
- **F5.2** WHEN 用户保存底稿时，THE 前端 SHALL 在 univer-save 请求 body 中携带 `expected_version`（当前 file_version）
- **F5.3** IF 后端返回 HTTP 409，THE 系统 SHALL 弹出 ConflictDialog（显示冲突者信息+最后修改时间）
- **F5.4** THE ConflictDialog SHALL 提供两个选项："刷新查看最新版" + "强制覆盖"（仅 manager/partner/admin 可见）
- **F5.5** WHEN 保存成功时，THE 前端 SHALL 用响应中的新 file_version 更新本地状态

---

## 四、非功能需求

| 维度 | 要求 |
|------|------|
| 性能 | F1 搜索 API ≤ 500ms（50 条结果）；F2 字号切换 ≤ 100ms 视觉响应 |
| 兼容性 | Chrome 90+ / Edge 90+ / Firefox 90+；1366×768 最小分辨率 |
| 可观测性 | F1 搜索调用记录到 audit_log（轻量级）；F5 版本冲突记录到 audit_log |
| 回归白名单 | displayPrefs 相关 5 个核心模块测试不能回归；useNavigationStack 现有测试不能回归 |

---

## 五、测试矩阵

| 功能 | 单测文件 | PBT | 集成测试 | UAT |
|------|---------|-----|---------|-----|
| F1 全局搜索 | test_global_search_endpoint.py + GlobalSearchDialog.spec.ts | — | Playwright 搜索+跳转 | P0 |
| F2 表格字号 | — | — | vitest snapshot | P0 |
| F3 穿透面包屑 | DrilldownBreadcrumb.spec.ts | — | Playwright 穿透链路 | P0 |
| F4 工具栏合并 | GtToolbar.spec.ts (compact mode) | — | vitest | P1 |
| F5 版本锁 | test_workpaper_version_lock.py + ConflictDialog.spec.ts | PBT-P1 并发保存 | — | P0 |

---

## 六、成功判据

| 指标 | 目标 |
|------|------|
| F1 搜索覆盖实体类型 | ≥ 4 类（底稿/科目/报表行/项目） |
| F2 字号生效页面数 | 全部含 el-table 的页面（≥ 20 个） |
| F3 面包屑显示正确率 | 穿透链路 100% 显示（无遗漏层级） |
| F4 数据区域增加 | 表格可见行数增加 ≥ 2 行（1366×768 分辨率下） |
| F5 冲突检测准确率 | 100%（版本不一致必须拦截） |
| 回归测试 | 现有 vitest + pytest 零新增失败 |

---

## 七、术语表

| 术语 | 定义 |
|------|------|
| Command Palette | 全局搜索弹窗，类似 VS Code 的 Ctrl+Shift+P |
| 穿透 (Drilldown) | 从汇总数据逐层下钻到明细数据的操作 |
| 版本锁 (Optimistic Lock) | 基于版本号的乐观并发控制，保存时校验版本一致性 |
| compact 模式 | GtToolbar 的紧凑单行布局模式 |
| displayPrefs | 全局显示偏好 Store（金额单位/字号/小数位等） |
