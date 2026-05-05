# Refinement Round 4 — 审计助理视角（新人上手 + 单页自洽 + AI 就位）

## 起草契约

**起草视角**：某大型事务所审计助理（Associate，工作 0~2 年）。是系统真正的高频用户，每天花 6 小时以上在底稿编辑器、程序清单、试算表、序时账穿透、函证回收。本轮围绕"新人第一周如何独立工作、底稿编辑器是否自洽、AI 是否真的有用"展开。

**迭代规则**：参见 [`../refinement-round1-review-closure/README.md`](../refinement-round1-review-closure/README.md)。本轮 Round 4。

## 复盘背景（审计助理视角）

助理视角看系统，痛点和合伙人/经理完全不同——他们不关心归档和评级，只关心"这个单元格该填什么、公式为什么红了、AI 能不能帮我找到去年怎么做的"。以实习第 3 周的审计助理走一遍系统，问题集中在：

1. **底稿编辑器首屏无"这张底稿要做什么"说明**：打开 `WorkpaperEditor` 就是空 Univer 表格，助理不知道要填哪些列、应该去哪里取数、结论区的审计判断依据是什么。
   - 证据：`audit-platform/frontend/src/views/WorkpaperEditor.vue` 工具栏只有"保存/同步公式/版本/下载/PDF/上传"，无"程序要求"或"底稿说明"按钮。
   - `wp_manuals` router 存在（底稿使用说明），但编辑器未集成。

2. **AI 助手入口缺失**：后端 `wp_chat_service`、`wp_ai_service` 等齐全，前端 `AIChatPanel.vue` 存在，但**编辑器右侧没有常驻 AI 侧边栏**，助理遇到问题只能猜。
   - 证据：`WorkpaperEditor.vue` 结构 `toolbar + main + statusbar`，无 AI 侧栏。

3. **公式/检查错误不可点击定位**：编辑器底部状态栏的"smartTip"只显示文字，助理看到"D5 借贷不平"不知道怎么跳到 D5。
   - 证据：`WorkpaperEditor.vue` 的 `smartTip` 仅 div 显示，无 click 跳单元格。

4. **"我的审计程序"与底稿打开时脱节**：`MyProcedureTasks.vue` 列出 10 个程序，点击进入底稿后，**底稿里不知道"我刚才是从程序 D-01 进来的"**，无上下文提示。
   - 证据：`MyProcedureTasks.openWP` 只 `router.push` 不传 context；编辑器顶部无面包屑。

5. **去年底稿无法一键对比**：助理做续审时要参考上年同底稿，**编辑器无"对比上年"按钮**。
   - 证据：`continuous_audit_service.py` 存在续审服务，但 `WorkpaperEditor` 未集成。

6. **序时账穿透链路不完整**：`LedgerPenetration` 页面存在，但**底稿里的某个金额"右键→穿透到序时账"不存在**。助理看到 500 万元余额要找来源，必须手动切页面、重新搜索。
   - 证据：`WorkpaperEditor` 无上下文菜单；`ledger_penetration_service` 有 API 但底稿无调用。

7. **新人引导全靠师傅口传**：`useWorkflowGuide` composable 存在，但只在项目创建时用了一次。**首次登录、首次打开底稿编辑器、首次提交复核**都无引导。
   - 证据：`useWorkflowGuide.ts` 第 1 行注释"关键操作入口弹出友好提示"但实际集成点仅 `ProjectWizard`。

8. **预填充结果无"来源提示"**：助理点"预填充"后底稿填了一堆数据，但**不知道每个数是从试算表哪一行来的**，出问题时查不到源头。
   - 证据：`workpaper_fill_service` 的填充不带 `provenance` 元数据回写。

9. **移动端底稿编辑器是"开发中"占位**：`MobileWorkpaperEditor.vue` 只有一个 el-empty，外勤出差根本不能用。
   - 证据：`MobileWorkpaperEditor.vue` 第 12 行 `el-empty description="移动端底稿编辑器（开发中）"`。

10. **附件关联不方便**：助理在外勤拍到一张银行对账单照片，**从底稿内部不能直接"插入并关联"**，必须切到 `AttachmentManagement` 上传、再回底稿关联。
    - 证据：`AttachmentManagement` 上传流程独立，`WorkpaperEditor` 无内嵌上传入口。

## 本轮范围

Round 4 让助理在"单张底稿编辑器"这一个页面内完成 80% 的工作，不反复跳页面。AI 助手常驻，序时账穿透、对比上年、附件插入就地可做。

## 需求列表

### 需求 1：底稿编辑器新增"程序要求"侧栏

**用户故事**：作为助理，我打开底稿应能看到"这张底稿的审计目的、要执行哪些程序、参考去年怎么做的"。

**验收标准**：

1. The `WorkpaperEditor.vue` shall 在左侧新增可折叠侧栏"📋 程序要求"，默认展开。
2. The 侧栏内容 shall 来自三个来源合并：
   - `wp_manuals` API（底稿使用说明，若存在）
   - `procedures` 关联到本底稿的程序列表（`wp_dependencies` 查询）
   - `continuous_audit_service` 返回的上年同底稿结论摘要
3. When 助理从 `MyProcedureTasks` 点击进入，the URL query shall 带 `?from_procedure=<procedure_code>`，侧栏高亮对应程序条目。
4. The 侧栏 shall 支持"标记为已完成"每个程序条目，点击后调用 `updateProcedureTrim` 更新状态。
5. The 侧栏可手动收起让出屏幕空间，折叠状态记 `localStorage.wp_sidebar_collapsed`。

### 需求 2：底稿编辑器常驻 AI 助手侧栏

**用户故事**：作为助理，我卡住时能直接问 AI："这条凭证要不要作为重分类"。

**验收标准**：

1. The `WorkpaperEditor.vue` shall 在右侧新增可折叠侧栏"🤖 AI 助手"，嵌入 `AIChatPanel.vue`。
2. The AI 上下文 shall 自动包含当前底稿 `wp_id`、项目 `project_id`、当前选中单元格（如有）、程序编号（从 URL query 取）。
3. When 助理选中一个单元格再提问，the AI 请求 shall 带 `cell_context: {cell_ref, value, formula, row, column}`，后端 `wp_chat_service` 用其生成更精准的答复。
4. The 侧栏 shall 提供 3 个快捷 prompt 按钮：「解释这个字段」「上年是怎么做的」「是否需要扩大抽样」。
5. The AI 回复 shall 支持"插入到结论区"一键操作，将选中段落写入 `parsed_data.conclusion` 并触发 dirty 标记。
6. 侧栏宽度默认 320px，可拖拽调整，记 `localStorage`。
7. **敏感数据脱敏**：The `wp_chat_service` 在调用 LLM 前 shall 调用 `export_mask_service.mask_context(cell_context)` 对金额、客户名、身份证等敏感字段替换为占位符（如 `[amount]` / `[client]`），保留业务语义；脱敏映射表仅在本次会话内有效，LLM 返回后不回填（避免生成内容泄露真值）。

### 需求 3：错误与智能提示可点击定位

**用户故事**：作为助理，我看到"D5 借贷不平"应能点一下跳到 D5 并高亮。

**验收标准**：

1. The `WorkpaperEditor.vue` 底部状态栏的 `smartTip` 与 `fine_checks` 结果 shall 每条 finding 提供 `cell_reference`，点击后调用 Univer API 滚动到该单元格并闪烁 3 次。
2. The 状态栏多条 finding shall 聚合为小 badge "⚠ 3"，点击展开下拉列表。
3. When finding 跨 sheet（如引用"利润表!B5"），the 点击 shall 切换到对应 sheet 再定位。
4. The 阻断级 finding shall 红底、警告级黄底、提示级蓝底，颜色与 AI 侧栏 severity tag 统一。

### 需求 4：对比上年按钮

**用户故事**：作为助理，做续审时一键看上年同底稿长什么样，好照着做。

**验收标准**：

1. The `WorkpaperEditor.vue` 工具栏 shall 新增"📜 对比上年"按钮，仅当项目为续审（`continuous_audit_service.is_continuing_engagement(project_id) == true`）时显示。
2. 点击后 shall 打开双栏对比抽屉：左当前底稿只读 Univer 视图，右上年同底稿只读视图。
3. The 后端 shall 新增 `GET /api/projects/{project_id}/workpapers/{wp_id}/prior-year`，返回上年同 `wp_index_id` 的底稿文件 URL 和元数据；无对应底稿返回 404。
4. The 对比抽屉 shall 支持"复制上年结论到今年"一键操作（助理确认后写入，dirty 触发保存）。
5. The 对比 shall 记 `audit_logger_enhanced` 事件 `workpaper_prior_year_viewed`，质控视角可统计利用率。

### 需求 5：序时账穿透右键菜单

**用户故事**：作为助理，右键点击底稿里的 500 万元金额，直接看到这个数来自哪几笔凭证。

**代码锚定前置说明**：现有 `GET /api/projects/{project_id}/ledger/penetrate` 端点参数为 `account_code + drill_level + date_from/to + page/page_size`（代码锚定：`backend/app/routers/ledger_penetration.py:40-59`），**不支持按金额+容差检索**。本需求必须新增专用端点，不要混入现有端点避免破坏其缓存语义。

**验收标准**：

1. The `WorkpaperEditor.vue` shall 注册 Univer 单元格右键菜单项"🔍 穿透序时账"，仅金额单元格（值为数字且 > 0）可见。
2. The 后端 shall 新增 `GET /api/projects/{project_id}/ledger/penetrate-by-amount`，参数 `{year, amount, tolerance?(默认 0.01), account_code?, date_from?, date_to?, summary_keyword?}`，返回匹配的序时账条目。
3. The 匹配策略优先级：精确 amount → ±tolerance 金额 → 同金额+指定 account_code → 同金额+summary_keyword 模糊匹配。多策略独立返回条目段落，前端按层级显示。
4. The 抽屉 shall 支持"导出穿透结果到附件"作为审计证据，自动创建 `AuditEvidence` 并关联到底稿。
5. 穿透结果为空 shall 友好提示"未找到匹配凭证，可调整容差或科目范围"，并给出当前使用的参数供用户核对。
6. 性能要求：单次查询 P95 < 2s，匹配条数超过 200 时截断提示"结果过多，请增加过滤条件"。

### 需求 6：工作流引导三处增强

**用户故事**：作为新人，我首次做关键动作时希望有引导弹窗，不要让我自己摸索。

**验收标准**：

1. The 首次登录 shall 触发 `useWorkflowGuide({key: 'first_login'})` 弹窗：介绍顶部导航、工作台入口、联系谁求助。
2. The 首次打开 `WorkpaperEditor` shall 触发 `first_open_workpaper` 引导：左栏程序要求、右栏 AI、顶部工具栏关键按钮。
3. The 首次提交复核 shall 触发 `first_submit_review` 引导：提交前门禁会检查什么、退回怎么办、哪里能看进度。
4. The 引导存 `localStorage.gt_workflow_guide_dismissed`（已有机制），用户可在设置页一键"重置所有引导"重看。
5. The 每条引导 shall 附 60 秒以内的要点（文字），不放长视频。

### 需求 7：预填充带来源元数据

**用户故事**：作为助理，预填充后我想知道 D5 的值是从试算表 E 栏第 42 行来的。

**验收标准**：

1. The `workpaper_fill_service` 预填充时 shall 在 `parsed_data.cell_provenance` 记录每个填充单元格的来源：`{cell_ref: {source: 'trial_balance'|'prior_year'|'formula'|'ledger', source_ref: 'E42'|'wp_X!B3'|..., filled_at, filled_by_service_version}}`。
2. The `WorkpaperEditor.vue` shall 在单元格 hover 时显示来源 tooltip，或点击单元格在右侧 AI 面板下方显示"数据来源"卡片。
3. The 来源带跳转链接：`trial_balance` → 跳 `TrialBalance` 页高亮该行；`prior_year` → 打开对比上年抽屉；`ledger` → 打开序时账穿透抽屉。
4. 未预填充的单元格（用户手填）shall 标记 `source: 'manual'`，不显示跳转。

### 需求 8：移动端底稿编辑器替代方案

**用户故事**：作为外勤助理，出差在高铁上只能用手机，我希望至少能查看底稿和回复复核意见。

**验收标准**：

1. The `MobileWorkpaperEditor.vue` shall 替换为真实的只读查看 + 复核意见回复页：
   - 顶部：底稿编号/名称/状态
   - 中部：底稿内容（渲染为 HTML，调用 `excel_html_converter` 服务）
   - 下部：复核意见列表 + 回复输入框
2. The 后端 shall 新增 `GET /api/projects/{project_id}/workpapers/{wp_id}/html` 返回底稿 HTML 预览（只读、脱敏可选）。
3. 移动端**不做编辑**（受限于 Univer 移动端兼容性），只读 + 评论。移除现有"下载"按钮（移动端下载大 xlsx 体验差），改为"在电脑上编辑"灰色提示。
4. The 移动端 shall 能接收推送通知并跳转到对应底稿（复用 notification 系统 + mobile 路由）。
5. 保留 `meta.developing` 标记到位但改 label 为"简化查看版"，不要误导用户能编辑。

### 需求 9：附件就地插入

**用户故事**：作为助理，我想直接在底稿编辑器里拖拽一张照片进来，系统帮我上传并自动关联到当前底稿和选中单元格。

**验收标准**：

1. The `WorkpaperEditor.vue` shall 响应 `dragover/drop` 事件，接受图片/PDF/Word 文件。
2. The 拖入后 shall 调用现有 `attachment_service.upload` 上传，成功后自动创建 `workpaper_attachment_link(wp_id, attachment_id, cell_ref=当前选中单元格, type='evidence')`。
3. The 关联成功后 shall 在单元格右上角显示 📎 图标（Univer 自定义装饰），点击显示附件列表 popover，支持预览/下载/取消关联。
4. The 附件大小 > 20MB 或类型不允许 shall 友好拒绝并 toast 提示。
5. The OCR 可选：图片拖入后异步触发 OCR（若启用），OCR 结果作为 `attachment.ocr_text` 供 AI 侧栏引用。

### 需求 10：个人任务时间线页

**用户故事**：作为助理，我想看自己本周做了哪些底稿、花了多长时间，向经理汇报有据可依。

**代码锚定前置说明**：焦点时长数据敏感（可被用来"量化工作投入度"形成监控压力）。按 README 跨轮约束第 8 条，**焦点时长不落数据库**。

**验收标准**：

1. The `PersonalDashboard.vue` shall 新增第四列"本周时间线"，展示按日聚合：每日工作的底稿、每日完成数。**时长来源优先使用已落库的工时填报数据**（`WorkHourRecord`），焦点时长作为本地参考值。
2. The 前端 shall 在编辑器中静默追踪"页面聚焦时间"，**只写入 `localStorage.focus_tracker_<weekStart>`**（键按周归档，每周清零），不发送到后端任何端点。
3. The 助理填报工时时 shall 读取 localStorage 焦点数据做**本地预填建议**（客户端计算，服务端不感知），用户可修改后提交。
4. The 时间线 shall 显示两列"焦点时长（本地）"和"已填报（系统）"，让助理自行对比调整填报。
5. 异常检测：单底稿焦点时长超过 4 小时 shall 在编辑器本地提示"您已在这张底稿工作 4 小时，要休息下吗"，轻量化且可关闭。
6. 重装浏览器/清缓存后焦点数据丢失是可接受的（不是权威数据源），用户主张的工时以 `WorkHourRecord` 为准。

## UAT 验收清单（手动验证）

1. 清 localStorage，登录后验证首次登录引导弹窗出现，看完一次后不再弹。
2. 从 `MyProcedureTasks` 点击 D-01 进底稿，验证左栏程序要求高亮 D-01；折叠侧栏再刷新页面，折叠状态保留。
3. 打开一张续审项目底稿，点"对比上年"看到双栏；"复制上年结论"后检查当前底稿结论区已填入。
4. 右键点击数字单元格"穿透序时账"，验证返回凭证列表且可导出为审计证据。
5. AI 侧栏选一个单元格问"这个数合理吗"，验证 AI 回复带单元格上下文；点"插入到结论区"写入成功。
6. 拖拽一张 JPG 到底稿，验证上传成功且单元格出现 📎；hover 看到文件名列表。
7. 在底稿工作 2 小时后查 `PersonalDashboard` 本周时间线，验证焦点时长显示；手机访问 `/projects/xxx/workpapers/yyy/mobile-wp` 看到只读 HTML 和回复框。
8. 关闭所有引导再进设置页点"重置引导"，验证弹窗重新出现。

## 不在本轮范围

- 合伙人 / PM / 质控视角（其他轮）
- 移动端真正的编辑能力（留 Round 6+，涉及 Univer 移动端 SDK 调研）
- OCR 深度接入（现有 OCR 服务够用，不重构）

## 验收完成标志

需求 1~10 全部满足 + UAT 8 项完成，Round 4 关闭。

## 变更日志

- v1.2 (2026-05-05) 一致性校对修正：
  - 需求 2 新增验收 7：AI 调用前强制 `export_mask_service` 脱敏敏感字段，对齐 design.md 与 tasks 4
- v1.1 (2026-05-05) 跨轮交叉核验修正：
  - 需求 5 新增专用端点 `/ledger/penetrate-by-amount`，不改动现有 `/ledger/penetrate`（参数体系完全不同）
  - 需求 10 焦点时长按 README 跨轮约束第 8 条改为"仅 localStorage 不落库"，消除监控隐患
- v1.0 (2026-05-05) 审计助理视角首稿。

## 补充需求（v1.3，长期运营视角）

以下 2 条由合伙人第三轮深度复盘新增，聚焦"**多人协作锁 + OCR 就地填入**"——助理日常最头疼的"我改的被别人覆盖"和"重复抄发票数字"。

### 需求 11：底稿多人协作软锁

**用户故事**：作为助理，我打开一张底稿时，如果另一个同事正在编辑，我要立刻看到"张三正在编辑（5 分钟前开始）"，避免白工。

**代码锚定**：当前仅 `wp_download_service.check_version_conflict` 在**提交时**检测 `file_version` 冲突，返回 `VERSION_CONFLICT 409`。事前无锁，两人同时改都会进去，后提交的被拒，工作作废。

**验收标准**：

1. The 后端 shall 新增 `workpaper_editing_locks` 表：`id / wp_id / staff_id / acquired_at / heartbeat_at / released_at | null`（软锁，无数据库行锁）。
2. When 助理打开 `WorkpaperEditor` shall 调 `POST /api/workpapers/{wp_id}/editing-lock`；后端发现已有未 released 锁且 `heartbeat_at > now - 5min` 则返回 `{locked_by, acquired_at}`，前端弹窗"{同事} 正在编辑，是否仅查看"。
3. The 前端 shall 每 2 分钟调 `PATCH .../editing-lock/heartbeat` 续期；页面关闭前 `DELETE .../editing-lock` 释放；浏览器崩溃时锁 5 分钟内无 heartbeat 自动过期。
4. When 另一同事强制进入（选"仅查看"后又点"强制编辑"），the 系统 shall 警告并记 audit_log；原锁持有者收到 `Notification(type='workpaper_lock_overridden')`。
5. The 锁仅防"无意识并发"，真正冲突仍靠 `VERSION_CONFLICT` 兜底，不破坏既有机制。
6. The `ManagerDashboard` 看板新增"当前正在被编辑的底稿" 小工具（诊断用），展示锁列表。

### 需求 12：OCR 右键菜单填入

**用户故事**：作为助理，附件里有发票/银行回单 PDF，右键单元格点"从附件 OCR 提取"，系统帮我把金额/日期/对方名称填进去，不要再手抄。

**代码锚定**：`ocr_service_v2` 已实现 12 类单据字段提取（`sales_invoice / purchase_invoice / bank_receipt ...`），但 `WorkpaperEditor` 右键菜单无 OCR 入口。

**验收标准**：

1. The `WorkpaperEditor` Univer 右键菜单 shall 新增"📄 从附件 OCR 提取"项，仅当当前底稿关联附件时可见。
2. 点击后弹抽屉：列已关联附件，选一张后调 `POST /api/attachments/{id}/ocr-fields`（若 `ocr_status != 'completed'` 先异步触发 OCR 等待）。
3. 返回字段（如发票 `{buyer_name, amount, tax_amount, invoice_date, invoice_no}`）shall 在抽屉展示，每个字段旁有"填入到当前单元格 / 填入到某列"按钮。
4. 填入后单元格的 `cell_provenance`（R4 需求 7）shall 记 `source='ocr', source_ref='attachment:{id}:{field_name}'`。
5. The 同一附件多次 OCR 提取 shall 复用缓存结果，不重复调 OCR 引擎。
6. The 填入前显示差异预览（现值→新值），助理确认才写入 dirty。

## 变更日志（续）

- v1.3 (2026-05-05) 长期运营视角增强：
  - 新增需求 11：多人协作软锁（防白工）
  - 新增需求 12：OCR 右键菜单就地填入（复用既有 ocr_service_v2）
