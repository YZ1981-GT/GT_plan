# Requirements Document

## Introduction

通用审计复核对话组件（GtReviewDialog），为所有D~N循环底稿的"审计说明"和"审计结论"区域提供即时通讯式复核对话能力。组件参照微信聊天交互模式，支持审计助理（编制人）与复核人（现场经理/合伙人）之间围绕底稿特定区域的实时对话，并提供AI生成辅助文本、多选导出到复核记录等完整工作流。

已有 `ReviewPanel.vue`（表格式复核意见+时间线）和 `ReviewConversations.vue`（项目级复核对话页面），本组件是嵌入底稿编辑区域的轻量即时对话面板，与现有复核记录体系打通。

## Glossary

- **GtReviewDialog**: 通用审计复核对话Vue组件，嵌入底稿审计说明/结论区域
- **Review_Thread**: 复核对话线程，按 `{wp_id}:{section_id}` 唯一标识
- **Review_Message**: 单条对话消息，含发送者、内容、时间戳、角色标识
- **Message_Bubble**: 消息气泡UI元素，区分自己/对方，显示头像+内容+时间
- **Close_Confirm_Dialog**: 关闭前确认弹窗，提供三选项（关闭/继续/导出）
- **Multi_Select_Mode**: 多选模式，消息左侧出现圆形选择框（类微信选择多条消息）
- **Export_Edit_Dialog**: 导出前二次编辑弹窗，支持AI润色和手动修改
- **AI_Generate_Button**: 🤖按钮，调用LLM为审计说明/结论自动生成文本
- **Review_Record**: 复核记录，存储于 checklist_responses，item_id 前缀 `{wp_code}-review-record-`
- **Section_Id**: 区域标识，取值 `audit-note`（审计说明）或 `audit-conclusion`（审计结论）
- **useReviewDialog**: 组件逻辑composable，封装消息CRUD、SSE订阅、导出流程
- **EventBus_SSE**: 现有SSE实时推送机制，通过 `sse:sync-event` 分发后端事件

## Requirements

### Requirement 1: 复核对话面板基础交互

**User Story:** As a 审计助理, I want to 在底稿任意位置打开复核对话面板与复核人沟通, so that 我能围绕当前底稿的具体内容与复核人实时交流审计意见。

#### Acceptance Criteria

1. THE GtReviewDialog SHALL 以抽屉（el-drawer）或弹出面板形式展示，宽度400px，从右侧滑入
2. THE GtReviewDialog SHALL 接收Props：wpId（底稿ID）、sectionId（上下文标识，如'audit-note'/'D1-adj-row-bank'/'D1-cat-row-3'等任意字符串）、sectionLabel（显示标题如"银行承兑汇票-期末审定数"）、currentUser（当前用户信息）、relatedData（当前上下文数据）
3. WHEN 用户通过以下任一方式激活对话时, THE GtReviewDialog SHALL 打开面板并加载对应线程：
   - 点击固定入口按钮（审计说明/结论区的对话图标）
   - 右键菜单中选择"发起复核对话"（在表格单元格/行/子节上右键）
   - 选中文本后通过浮动工具栏的"复核"按钮
4. THE GtReviewDialog SHALL 以气泡消息形式展示对话内容，当前用户消息靠右（绿色气泡），对方消息靠左（白色气泡）
5. THE Message_Bubble SHALL 显示：用户头像（圆形首字母）、消息内容、时间戳（HH:mm格式）、发送者角色标签（如"审计助理"/"经理"）
6. THE GtReviewDialog SHALL 在底部显示消息输入区：textarea（可多行）+ 发送按钮，支持Enter发送、Shift+Enter换行
7. WHEN 新消息到达时, THE GtReviewDialog SHALL 自动滚动到底部显示最新消息
8. THE GtReviewDialog SHALL 在面板顶部显示对话标题（含 sectionLabel，如"D1-1 银行承兑汇票-期末审定数 复核对话"）和在线状态指示
9. THE GtReviewDialog SHALL 在面板顶部显示上下文摘要卡片（当前位置的数据快照：如金额/公式结果/变动率等），帮助复核人快速了解讨论背景

### Requirement 2: 消息发送与实时接收

**User Story:** As a 审计助理, I want to 发送消息后对方能即时收到, so that 复核沟通效率接近面对面交流。

#### Acceptance Criteria

1. WHEN 用户点击发送或按Enter时, THE useReviewDialog SHALL 调用 `POST /api/review-threads/{thread_id}/messages` 发送消息
2. WHEN 消息发送成功时, THE GtReviewDialog SHALL 立即在本地追加该消息气泡（乐观更新）
3. THE useReviewDialog SHALL 通过 EventBus SSE 订阅 `review_message.created` 事件，接收对方发送的新消息
4. WHEN 收到SSE新消息事件且 thread_id 匹配当前线程时, THE GtReviewDialog SHALL 将新消息追加到消息列表
5. IF 消息发送失败, THEN THE GtReviewDialog SHALL 在该消息气泡旁显示红色感叹号和"重发"按钮
6. WHEN 用户点击"重发"按钮时, THE useReviewDialog SHALL 重新发送该条失败消息

### Requirement 3: 关闭前确认弹窗

**User Story:** As a 审计助理, I want to 关闭对话时有确认提示防止误操作, so that 我不会意外丢失需要导出的对话内容。

#### Acceptance Criteria

1. WHEN 用户点击关闭按钮或面板外区域时, THE Close_Confirm_Dialog SHALL 弹出确认弹窗
2. THE Close_Confirm_Dialog SHALL 显示三个操作按钮："关闭对话"（灰色）、"继续对话"（默认蓝色）、"导出到复核记录"（绿色）
3. WHEN 用户点击"关闭对话"时, THE GtReviewDialog SHALL 直接关闭面板不做任何保存
4. WHEN 用户点击"继续对话"时, THE Close_Confirm_Dialog SHALL 关闭弹窗返回对话面板
5. WHEN 用户点击"导出到复核记录"时, THE GtReviewDialog SHALL 进入多选模式（Multi_Select_Mode）
6. IF 当前对话无任何消息, THEN THE GtReviewDialog SHALL 直接关闭不弹确认窗

### Requirement 4: 多选导出模式

**User Story:** As a 审计助理, I want to 像微信一样选择多条消息进行导出, so that 我能精确选择有价值的对话内容保存到复核记录。

#### Acceptance Criteria

1. WHEN 进入多选模式时, THE GtReviewDialog SHALL 在每条消息气泡左侧显示圆形选择框（未选中空心圆/选中实心蓝色对勾）
2. THE GtReviewDialog SHALL 在多选模式顶部显示"选择消息"标题和"全选"/"取消"按钮
3. WHEN 用户点击消息气泡或其左侧选择框时, THE GtReviewDialog SHALL 切换该消息的选中状态
4. THE GtReviewDialog SHALL 在多选模式底部显示已选数量和"导出"按钮
5. WHILE 未选中任何消息时, THE GtReviewDialog SHALL 禁用"导出"按钮（灰色不可点击）
6. WHEN 用户点击"导出"按钮时, THE GtReviewDialog SHALL 打开导出前编辑弹窗（Export_Edit_Dialog）
7. THE GtReviewDialog SHALL 支持按住Shift点击实现范围选择（选中两次点击之间的所有消息）

### Requirement 5: 导出前二次编辑弹窗

**User Story:** As a 审计助理, I want to 在导出前对选中的消息内容进行编辑和AI润色, so that 导出到复核记录的内容格式规范、表述专业。

#### Acceptance Criteria

1. THE Export_Edit_Dialog SHALL 以el-dialog形式展示（宽度600px），标题为"编辑导出内容"
2. THE Export_Edit_Dialog SHALL 将选中消息按时间顺序拼接为初始文本，格式为"[角色 HH:mm] 内容"每条一段
3. THE Export_Edit_Dialog SHALL 提供可编辑的textarea（至少10行高度），用户可自由修改内容
4. THE Export_Edit_Dialog SHALL 在textarea上方显示"🤖 AI润色"按钮
5. WHEN 用户点击"AI润色"按钮时, THE Export_Edit_Dialog SHALL 调用AI接口对textarea内容进行专业化润色（system prompt指定审计复核记录风格）
6. WHILE AI润色请求进行中时, THE Export_Edit_Dialog SHALL 显示加载动画并禁用AI润色按钮
7. WHEN AI润色返回结果时, THE Export_Edit_Dialog SHALL 用润色后的文本替换textarea内容（用户可继续编辑或撤销）
8. THE Export_Edit_Dialog SHALL 在底部显示"取消"和"保存到复核记录"按钮
9. IF AI润色请求失败, THEN THE Export_Edit_Dialog SHALL 显示友好提示"AI服务暂时不可用，请手动编辑"且不清空原内容

### Requirement 6: 保存到复核记录

**User Story:** As a 审计助理, I want to 编辑完成的对话内容保存到复核记录, so that 复核过程有据可查且在ReviewPanel时间线中可追溯。

#### Acceptance Criteria

1. WHEN 用户在Export_Edit_Dialog点击"保存到复核记录"时, THE useReviewDialog SHALL 调用 `POST /api/workpapers/{wp_id}/checklist-responses` 保存内容
2. THE useReviewDialog SHALL 使用 item_id 格式 `{wp_code}-review-record-{timestamp}` 存储导出内容
3. WHEN 保存成功时, THE GtReviewDialog SHALL 关闭Export_Edit_Dialog和多选模式，显示"已保存到复核记录"成功提示
4. THE Review_Record SHALL 在 ReviewPanel 时间线中以"复核对话导出"标签可查看
5. IF 保存请求失败, THEN THE Export_Edit_Dialog SHALL 显示错误提示并保留编辑内容不关闭弹窗
6. THE Review_Record SHALL 存储以下元数据：导出时间、导出人、源线程thread_id、选中消息ID列表

### Requirement 7: AI生成审计文本

**User Story:** As a 审计助理, I want to 点击🤖按钮让AI基于当前底稿数据自动生成审计说明/结论文本, so that 我能快速获得专业的初稿再做微调。

#### Acceptance Criteria

1. THE AI_Generate_Button SHALL 在每个textarea旁显示🤖图标按钮，tooltip为"AI生成"
2. WHEN 用户点击AI_Generate_Button时, THE useReviewDialog SHALL 调用 `POST /api/workpapers/{wp_id}/review-dialog/ai-generate` 并传入 sectionId 和 relatedData（审定表数据变动context）
3. THE useReviewDialog SHALL 构建AI请求context：包含审定表三区块数据摘要、变动比例、差异信息、当前section类型
4. WHEN AI返回生成文本时, THE GtReviewDialog SHALL 将生成内容填入对应textarea（替换原有内容前弹确认）
5. WHILE AI生成请求进行中时, THE AI_Generate_Button SHALL 显示加载旋转动画并禁用按钮
6. IF AI服务不可用, THEN THE GtReviewDialog SHALL 显示友好提示"AI服务暂时不可用，请手动填写"
7. WHEN AI生成内容将覆盖非空textarea时, THE GtReviewDialog SHALL 弹出确认框"当前内容将被替换，是否继续？"

### Requirement 8: 权限控制

**User Story:** As a 现场经理, I want to 只有适当角色才能参与复核对话, so that 对话权限与审计复核层级一致。

#### Acceptance Criteria

1. THE GtReviewDialog SHALL 允许审计助理（编制人）发起和参与对话
2. THE GtReviewDialog SHALL 允许现场经理和业务合伙人以复核人身份参与对话
3. THE GtReviewDialog SHALL 允许质量控制复核合伙人和EQCR以只读模式查看对话
4. WHILE 用户角色为只读时, THE GtReviewDialog SHALL 隐藏消息输入区和发送按钮
5. THE useReviewDialog SHALL 在加载消息前验证当前用户对该底稿的访问权限

### Requirement 9: 消息存储与后端API

**User Story:** As a 开发者, I want to 有标准的后端API和存储结构支撑复核对话功能, so that 数据持久化可靠且API设计与现有模式一致。

#### Acceptance Criteria

1. THE Review_Thread SHALL 存储于 `review_threads` 表，字段包含：id(UUID)、project_id、wp_id、section_id、thread_key(`{wp_id}:{section_id}`)、status(open/closed)、created_by、created_at、updated_at
2. THE Review_Message SHALL 存储于 `review_messages` 表，字段包含：id(UUID)、thread_id(FK)、sender_id、sender_role、content(text)、message_type(text/system)、created_at
3. THE Review_Thread SHALL 通过 thread_key 唯一索引保证每个底稿每个区域只有一个活跃线程
4. WHEN 收到 `POST /api/review-threads/{thread_id}/messages` 时, THE 后端 SHALL 保存消息并通过EventBus发布 `review_message.created` 事件（payload含thread_id、message内容、sender信息）
5. THE 后端 SHALL 提供 `GET /api/review-threads?wp_id={wp_id}&section_id={section_id}` 查询线程及其消息列表
6. THE 后端 SHALL 提供 `POST /api/review-threads` 创建新线程（如不存在则自动创建）
7. IF 线程已关闭（status=closed）, THEN THE 后端 SHALL 拒绝新消息发送并返回400错误

### Requirement 10: SSE实时推送集成

**User Story:** As a 审计助理, I want to 不刷新页面就能收到对方的新消息, so that 对话体验流畅接近即时通讯。

#### Acceptance Criteria

1. THE 后端 SHALL 在消息创建成功后通过 EventBus publish `review_message.created` 事件，事件类型注册到SSE事件列表
2. THE useReviewDialog SHALL 通过 `eventBus.on('sse:sync-event', handler)` 订阅SSE事件
3. WHEN 收到 `review_message.created` 事件且 thread_id 匹配当前打开的线程时, THE useReviewDialog SHALL 将消息追加到本地列表
4. WHEN 收到 `review_message.created` 事件但对话面板未打开时, THE GtReviewDialog SHALL 在对话入口按钮上显示未读消息数红色角标
5. THE useReviewDialog SHALL 在组件卸载时取消SSE事件订阅（eventBus.off）

### Requirement 11: 组件代码架构

**User Story:** As a 开发者, I want to 组件结构清晰、可维护, so that 代码易于理解和后续扩展。

#### Acceptance Criteria

1. THE GtReviewDialog SHALL 实现为单文件Vue组件 `GtReviewDialog.vue`，控制在400行以内
2. THE useReviewDialog SHALL 实现为独立composable `useReviewDialog.ts`，控制在300行以内，封装：消息CRUD、SSE订阅、多选状态、导出流程、AI调用
3. THE GtReviewDialog SHALL 作为通用组件放置于 `audit-platform/frontend/src/components/collaboration/` 目录
4. THE GtReviewDialog SHALL 通过Props接口与父组件解耦，不依赖特定底稿类型的内部实现
5. THE useReviewDialog SHALL 提供 `openDialog`/`closeDialog`/`sendMessage`/`enterSelectMode`/`exportSelected` 等方法供模板调用
6. THE GtReviewDialog SHALL 在D1TabAdjudication.vue的"1.审计说明"和"2.审计结论"区域通过 `<GtReviewDialog :wp-id="wpId" :section-id="'audit-note'" />` 形式集成

### Requirement 12: 全局右键菜单激活

**User Story:** As a 审计助理, I want to 在底稿中任意位置右键发起复核对话, so that 我能针对具体的数据点或检查项与复核人讨论，而不限于固定的审计说明区域。

#### Acceptance Criteria

1. THE GtReviewDialog SHALL 提供全局注入能力（provide/inject 或 Pinia store），任何底稿子组件均可调用 `openReviewDialog(options)` 激活对话面板
2. THE GtReviewDialog SHALL 支持通过右键菜单（el-dropdown + contextmenu 事件）激活，菜单项为"📝 发起复核对话"
3. WHEN 用户在 el-table 的单元格上右键选择"发起复核对话"时, THE GtReviewDialog SHALL 自动生成 sectionId（如 `D1-adj-{rowKey}-{field}`）和 sectionLabel（如"银行承兑汇票 - 期末审定数: ¥1,234,567"）
4. WHEN 用户选中文本后通过浮动工具栏点击"复核"按钮时, THE GtReviewDialog SHALL 将选中文本作为对话的初始上下文引用（显示在上下文摘要卡片中）
5. THE GtReviewDialog SHALL 对同一个 sectionId 的多次打开复用同一个线程（不创建重复线程）
6. THE GtReviewDialog SHALL 在底稿编辑器顶部工具栏显示"复核对话"图标按钮，点击打开当前底稿的对话线程列表（el-popover 列出所有活跃线程，点击进入对应对话）
7. WHEN 底稿中某个位置有活跃的复核对话线程时, THE GtReviewDialog SHALL 在该位置旁显示小圆点标记（蓝色，表示有对话；红色，表示有未读消息）

### Requirement 13: 上下文感知与自动引用

**User Story:** As a 现场经理, I want to 打开复核对话时能立即看到讨论的上下文数据, so that 我不需要切换来回查看底稿内容就能做出复核判断。

#### Acceptance Criteria

1. THE GtReviewDialog SHALL 在面板顶部固定显示一个"上下文摘要"卡片（浅蓝色背景，不可编辑）
2. THE 上下文摘要 SHALL 根据 sectionId 和 relatedData 自动展示相关数据快照：
   - 审计说明区：显示审定表三区块小计+变动率+差异数
   - 单元格级：显示该单元格的字段名+当前值+上期值+变动
   - 检查项级：显示检查项编号+内容摘要+当前结论
3. WHEN 发送消息时, THE GtReviewDialog SHALL 允许用户通过"引用"按钮将上下文摘要中的数据片段嵌入消息（显示为引用区块样式）
4. THE GtReviewDialog SHALL 在每条带引用的消息中保留引用数据的快照时间戳（标注"引用时数据"），即使原数据后续变更也不影响历史消息中的引用值
