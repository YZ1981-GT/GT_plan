# Phase 10 — 任务清单

## 任务组 1：底稿下载与导入

### Task 1.1 底稿批量下载
- [x] `POST /api/projects/{id}/workpapers/download-pack` 打包下载 API
- [x] 下载前自动预填（调用 PrefillService）
- [x] ZIP 打包（zipfile 模块，目录结构：循环/编号_名称.xlsx）
- [x] 单个底稿下载（`GET /api/projects/{id}/workpapers/{wp_id}/download`）
- [x] 批量下载性能优化：>10个底稿时异步模式+进度轮询（design §25m）
- [x] 前端 WorkpaperList.vue 添加勾选+下载按钮+单个下载按钮

### Task 1.2 底稿导入（离线编辑回传）
- [x] `POST /api/projects/{id}/workpapers/{wp_id}/upload` 上传 API
- [x] 版本冲突检测（file_version 比对）
- [x] 冲突处理（409 + diff 摘要 / 覆盖 / 保留）
- [x] 导入后触发 ParseService + WORKPAPER_SAVED 事件
- [x] WORKPAPER_SAVED 事件处理器：解析审定数 → 与 trial_balance 比对 → 差异时自动同步（design §25a）
- [x] data/wp_parse_rules.json 底稿模板解析规则配置（先覆盖核心30个审定表）
- [x] 前端上传弹窗（版本冲突提示+选择操作）

---

## 任务组 2：连续审计

### Task 2.1 一键创建当年项目
- [x] `POST /api/projects/{id}/create-next-year` API
- [x] projects 表新增 prior_year_project_id 字段
- [x] adjustments 表新增 is_continuous BOOLEAN DEFAULT false 字段
- [x] 复制 basic_info/account_mapping/project_assignments/template_set
- [x] 上年 trial_balance.audited → 当年 opening
- [x] 上年 disclosure_note 期末 → 当年上期
- [x] 上年 adjustments(is_continuous=true) 结转
- [x] 上年 unadjusted_misstatements carry_forward
- [x] 上年底稿文件复制+openpyxl写入期初数+清空本期数（design §25d）
- [x] 上年 note_wp_mapping + procedure_instances + note_trim_schemes 结转（design §25j）
- [x] 前端项目详情面板"创建下年项目"按钮

### Task 2.2 跨年数据对比
- [x] 当年底稿中查看上年同科目数据（PREV 函数已支持，前端展示待实现）
- [x] 附注变动分析自动对比上年数据生成变动说明（复用 note_ai generate-analysis）

---

## 任务组 3：服务器存储与分区

### Task 3.1 私人库管理
- [x] PrivateStorageService（上传/下载/删除/容量检查）
- [x] `GET /api/users/{id}/private-storage` 文件列表
- [x] `POST /api/users/{id}/private-storage/upload` 上传
- [x] `GET /api/users/{id}/private-storage/quota` 容量查询
- [x] 容量上限 1GB，90% 提示清理
- [x] 附件分区存储路径确认（storage/projects/{project_id}/attachments/）
- [x] 前端 PrivateStorage.vue 页面

### Task 3.2 归档联动
- [x] 项目归档时锁定所有底稿为 archived
- [x] 自动生成归档清单
- [x] 触发 enrich_resume 更新人员简历
- [x] 前端归档确认弹窗

### Task 3.3 存储统计看板
- [x] `GET /api/admin/storage-stats` 存储统计 API
- [x] 按项目/用户/年度统计存储占用
- [x] 前端 ECharts 饼图/柱状图展示

---

## 任务组 4：过程记录与附件关联

### Task 4.1 底稿编辑记录
- [x] 底稿保存时记录编辑摘要到 logs 表
- [x] 前端底稿详情面板显示编辑历史

### Task 4.2 附件双向关联
- [x] 底稿详情面板显示关联附件列表
- [x] 附件详情显示关联底稿列表
- [x] 上传附件时可选择关联底稿

### Task 4.3 人机协同标注
- [x] AI 生成内容写入 ai_content 表（复用 Phase 4 定义）
- [x] 前端 AI 标签（紫色背景 + "AI 辅助-待确认"）
- [x] 人工确认后标签变为"已确认"
- [x] 关键底稿提交复核前检查未确认的 AI 内容

---

## 任务组 5：LLM 深度融合底稿

### Task 5.1 对话式底稿填充
- [x] `POST /api/workpapers/{wp_id}/ai/chat` SSE 流式对话 API
- [x] 对话上下文注入：parsed_data + 四表数据 + 知识库 RAG
- [x] 回复中包含 fill_suggestion（cell_ref + value）
- [x] 前端 WorkpaperEditor.vue 添加 LLM 对话侧边栏
- [x] 选中单元格 → 对话窗口显示上下文 → AI 回复填入

### Task 5.2 台账分析底稿生成
- [x] `POST /api/projects/{id}/ai/generate-ledger-analysis` 生成台账分析
- [x] LLM 根据序时账生成大额/异常/关联方交易分析
- [x] 自动生成审计说明
- [x] 保存为新底稿（wp_index + working_paper）

### Task 5.3 知识库双向关联
- [x] 底稿编辑时搜索知识库（复用 knowledge_retriever）
- [x] 知识库文档被底稿引用时记录关联关系
- [x] 双向查看：底稿→引用的知识库文档，知识库→被引用的底稿

---

## 任务组 6：抽样程序增强

### Task 6.1 截止性测试
- [x] `POST /api/projects/{id}/sampling/cutoff-test` API
- [x] 自动从 tb_ledger 提取期末前后 N 天交易
- [x] 填入截止性测试底稿模板（复用 §25g target_wp_id 机制，design §25l）
- [x] 前端截止性测试配置（天数/科目/金额阈值）

### Task 6.2 账龄分析
- [x] `POST /api/projects/{id}/sampling/aging-analysis` API
- [x] 用户自定义账龄区间段配置（前端 el-form 动态行：标签+起始天数+结束天数）
- [x] FIFO 先进先出核销算法（借方按日期正序形成，贷方按日期正序核销最早借方）
- [x] 从 tb_aux_ledger 按辅助维度分组计算未核销余额的账龄天数
- [x] 兜底：支持用户直接上传已有账龄分析 Excel
- [x] 按自定义区间分组汇总，填入账龄分析底稿
- [x] 前端账龄分析配置面板（科目选择+基准日+区间编辑+结果预览表格）

### Task 6.3 月度明细填充
- [x] `POST /api/projects/{id}/sampling/monthly-detail` API
- [x] 按月汇总 tb_ledger 数据
- [x] 自动填入月度明细分析底稿（复用 §25g target_wp_id 机制，design §25l）

### Task 6.4 抽样结果与底稿关联
- [x] sampling_config 新增 target_wp_id + target_cell_range 字段（design §25g）
- [x] 抽样选中的样本用 openpyxl 自动填入对应底稿
- [x] MUS 评价结果自动生成审计结论

---

## 任务组 7：合并报表增强

### Task 7.1 合并锁定同步
- [x] 合并项目开始时锁定单体试算表（consol_lock + consol_lock_by + consol_lock_at 字段）
- [x] consol_lock_check 依赖注入函数（Depends），拦截锁定期间的写操作返回 423（design §25c）
- [x] 锁定期间单体禁止修改试算表/调整分录/未更正错报（返回 423 Locked）
- [x] 合并完成后自动解锁
- [x] 解锁后自动刷新合并试算表+与快照对比差异（design §25i）
- [x] 前端锁定状态提示（el-alert 横幅 + 写操作按钮禁用）

### Task 7.2 外部单位报表导入
- [x] 导入其他审计师审计的单位报表（Excel）
- [x] 导入附注（Word），LLM 辅助解析
- [x] 导入数据纳入合并试算表

### Task 7.3 独立模块使用
- [x] 仅合并模块入口（无需单体项目）
- [x] 仅报告复核模块入口
- [x] 仅报告排版模块入口
- [x] 临时项目机制（auto_created=true，30天无操作自动清理）
- [x] 前端模块选择页面

---

## 任务组 8：复核对话系统

### Task 8.1 数据模型与后端
- [x] review_conversations + review_messages 表（Alembic 迁移）
- [x] review_conversations 新增 cell_ref VARCHAR 字段（精确到单元格的 deep link）
- [x] ORM 模型 + Pydantic Schema
- [x] `POST /api/review-conversations` 创建对话
- [x] `POST /api/review-conversations/{id}/messages` 发送消息
- [x] `PUT /api/review-conversations/{id}/close` 关闭对话（权限校验：仅发起人可关闭）
- [x] `POST /api/review-conversations/{id}/export` 导出 Word
- [x] SSE 推送新消息通知

### Task 8.2 前端对话组件
- [x] ReviewConversation.vue 对话页面
- [x] 消息列表（文字/图片/文件）
- [x] 发送消息输入框
- [x] 结束对话按钮（仅发起人可见）
- [x] 导出对话记录按钮
- [x] 通知点击 deep link 跳转到底稿/附注具体位置（design §25e）
- [x] 看板集成（进行中对话数）
- [x] 质量控制复核人员对话通道预留

### Task 8.3 LLM 底稿复核
- [x] `POST /api/workpapers/{wp_id}/ai/review` 复核 API
- [x] 复核时加载 TSJ/ 对应提示词
- [x] LLM 自动检查底稿（数据完整性/逻辑一致性/格式规范）
- [x] 生成结构化 findings（类型/严重度/位置/建议）
- [x] 前端复核结果面板

### Task 8.4 导出功能增强
- [x] 复核记录导出为 Word/PDF
- [x] 对话记录导出为 Word/PDF
- [x] 底稿复核报告导出（含所有 findings + 处理状态）

---

## 任务组 9：报告复核溯源

### Task 9.1 溯源 API
- [x] `GET /api/report-review/{project_id}/trace/{section_number}` 溯源查询
- [x] 返回：附注数据 + 底稿审定数 + 审计说明 + 大额交易明细
- [x] note_wp_mapping 自动初始化（项目底稿生成时根据模板规则自动创建映射，design §25f）
- [x] data/note_wp_mapping_rules.json 映射规则配置文件
- [x] 溯源页面复核意见统一写入 cell_annotations（design §25n）
- [x] `GET /api/projects/{id}/findings-summary` 统一 findings 视图（LLM+人工合并，design §25o）
- [x] 前端溯源面板（在报告复核页面中）

---

## 任务组 10：工时打卡与足迹

### Task 10.1 打卡签到
- [x] check_ins 表（Alembic 迁移）
- [x] `POST /api/staff/{id}/check-in` 打卡 API（含 GPS）
- [x] 打卡与工时联动
- [x] 前端打卡按钮 + 日历视图

### Task 10.2 足迹报告
- [x] 每半年 LLM 生成足迹+工作总结
- [x] 推送给成员和合伙人
- [x] 前端足迹展示页面

---

## 任务组 11：吐槽与求助专栏

### Task 11.1 论坛系统
- [x] forum_posts + forum_comments 表（Alembic 迁移）
- [x] CRUD API（发帖/评论/点赞/删除）
- [x] 匿名发帖支持
- [x] LLM 敏感内容过滤
- [x] 前端 ForumPage.vue

---

## 任务组 12：私人库与 LLM 对话

### Task 12.1 私人库
- [x] 复用 Task 3.1 的 PrivateStorageService（不重复创建）
- [x] 上传后自动向量化索引
- [x] 容量管理（1GB 上限 + 90% 提示，复用 Task 3.1）
- [x] 前端 PrivateStorage.vue 增强（向量化状态+RAG 入口）
- [x] ThreeColumnLayout navItems 添加"私人库"入口（最左侧第一栏，与项目/知识库同级）
- [x] 新生成底稿/分析报告可指定保存到私人库（Task 5.2/19.1 联动）
- [x] 私人库文档共享到项目知识库 API（`POST /api/users/{id}/private-storage/share`）

### Task 12.2 私人库 LLM 对话
- [x] 基于私人库的 RAG 对话
- [x] 对话记录导出 Word
- [x] 与项目知识库打通

---

## 任务组 13：辅助余额表汇总

### Task 13.1 明细汇总与匹配
- [x] `GET /api/projects/{id}/ledger/aux-summary` 汇总匹配 API
- [x] 匹配一致：折叠辅助明细
- [x] 不一致：红色高亮差异 + 原因提示
- [x] 前端可视化（饼图/柱状图展示辅助维度构成）

---

## 任务组 14：权限精细化

### Task 14.1 删除权限控制
- [x] 底稿/调整分录/附件删除时检查 created_by
- [x] 项目经理可删除项目内所有内容
- [x] 合伙人/管理员可删除任何内容
- [x] 删除操作记录审计日志

---

## 任务组 15：单元格级复核批注

### Task 15.1 批注系统
- [x] cell_annotations 表（Alembic 迁移）
- [x] ORM 模型 + Pydantic Schema
- [x] `POST /api/projects/{id}/annotations` 创建批注
- [x] `GET /api/projects/{id}/annotations` 批注列表（按对象/状态/优先级筛选）
- [x] `PUT /api/annotations/{id}` 更新状态（pending→replied→resolved）
- [x] 穿透关联：附注批注→底稿批注自动创建 linked_annotation
- [x] 批注升级为对话（关联 review_conversations）
- [x] 前端：单元格右键菜单"添加批注"+批注气泡+批注汇总面板

---

## 任务组 16：合并数据快照

### Task 16.1 快照管理
- [x] consol_snapshots 表（Alembic 迁移）
- [x] 合并报表生成时自动保存快照
- [x] `GET /api/consolidation/{id}/snapshots` 快照列表
- [x] `GET /api/consolidation/{id}/snapshots/{snapshot_id}/diff` 快照差异对比
- [x] 基于历史快照重新生成合并报表
- [x] 前端快照列表+差异对比面板

---

## 任务组 17：底稿智能推荐

### Task 17.1 LLM 推荐
- [x] `POST /api/projects/{id}/ai/recommend-workpapers` 推荐 API
- [x] 输入：materiality + industry + prior_year_findings
- [x] LLM 分析风险等级，推荐底稿优先级
- [x] 与 procedure_instances 联动（高风险→execute）
- [x] 前端推荐结果面板（在 ProcedureTrimming.vue 中集成）

---

## 任务组 18：知识库上下文感知

### Task 18.1 上下文注入
- [x] LLM 对话时自动注入底稿上下文（科目/循环/类型/试算表数据）
- [x] 知识库文档上传时 LLM 自动打标签（行业/科目/文档类型，design §25k）
- [x] 知识库检索按相关度排序（同行业/同科目优先，基于标签匹配）
- [x] 引用标注来源文档和页码
- [x] 前端"@知识库"触发精准检索

---

## 任务组 19：年度差异分析报告

### Task 19.1 差异报告生成
- [x] `POST /api/projects/{id}/ai/annual-diff-report` 生成 API
- [x] 全科目变动额/变动率计算
- [x] 重大变动筛选（>20% 或 >materiality）
- [x] LLM 逐科目生成分析说明
- [x] 保存为底稿 + 导出 Word

---

## 任务组 20：附件智能分类

### Task 20.1 智能分类
- [x] 上传附件时 OCR 提取文本
- [x] LLM 自动分类（合同/发票/对账单/函证/会议纪要）
- [x] 自动建议关联底稿（按科目关键词匹配 wp_index，design §25h）
- [x] 前端分类确认/修改界面

---

## 任务组 21：报告排版模板

### Task 21.1 模板管理
- [x] report_format_templates 表（Alembic 迁移）
- [x] 模板 CRUD API
- [x] 4 个内置模板（标准版/简化版/国企版/上市版）
- [x] 模板自定义（字体/页边距/页眉页脚/水印）
- [x] 排版实时预览（python-docx → HTML → iframe）
- [x] 模板版本管理+回滚
- [x] 前端 ReportFormatManager.vue

---

## 执行顺序

0. **迁移脚本**（统一创建 023/024/025 三个 Alembic 迁移脚本，所有新表+新字段一次性就绪）
1. **Task 1.1-1.2**（底稿下载导入）→ 2. **Task 2.1-2.2**（连续审计）
3. **Task 3.1-3.3**（存储分区+归档+统计）→ 4. **Task 4.1-4.3**（过程记录+附件+人机协同）
5. **Task 18.1 + Task 5.1-5.3**（知识库上下文感知 → LLM 底稿填充，合并执行）
6. **Task 6.1-6.4**（抽样+截止性+账龄+月度）
7. **Task 7.1-7.3**（合并增强）→ 8. **Task 8.1-8.4**（复核对话+LLM复核+导出）
9. **Task 15.1**（单元格级复核批注）→ 10. **Task 9.1**（报告溯源）
11. **Task 13.1**（辅助余额汇总）→ 12. **Task 14.1**（权限精细化）
13. **Task 16.1**（合并数据快照）→ 14. **Task 17.1**（底稿智能推荐）
15. **Task 19.1**（年度差异分析报告）→ 16. **Task 20.1**（附件智能分类）
17. **Task 21.1**（报告排版模板）
18. **Task 10.1-10.2**（打卡足迹）→ 19. **Task 11.1**（吐槽专栏）
20. **Task 12.1-12.2**（私人库+LLM对话）

## 数据库迁移规划

Phase 10 新增 8 张表，合并为 3 个迁移脚本：

| 迁移脚本 | 包含表 | 功能域 |
|---------|--------|--------|
| 023_review_and_forum.py | review_conversations + review_messages + forum_posts + forum_comments | 协作与社区 |
| 024_annotations_and_snapshots.py | cell_annotations + consol_snapshots + check_ins | 复核批注+合并快照+打卡 |
| 025_report_templates.py | report_format_templates + projects.prior_year_project_id + projects.consol_lock + projects.consol_lock_by + projects.consol_lock_at + adjustments.is_continuous 字段 | 排版模板+连续审计+合并锁定 |

---

## 任务组 22：前端集成（补充）

### Task 22.1 前端 API 服务层
- [x] phase10Api.ts 统一封装所有 Phase 10 后端 API（40+ 函数）
- [x] TypeScript 类型定义（ConversationItem/AnnotationItem/ForumPostItem/AgingBracket）

### Task 22.2 前端路由注册
- [x] router/index.ts 注册 10 条 Phase 10 路由
- [x] DefaultLayout.vue 排除 /forum 和 /private-storage 为全宽模式

### Task 22.3 前端页面实现
- [x] AnnotationsPanel.vue — 批注管理（表格+筛选+创建弹窗+状态流转）
- [x] ReportTracePanel.vue — 报告溯源（章节号查询+附注/底稿/试算表/序时账四层展示+findings汇总）
- [x] SamplingEnhanced.vue — 抽样增强（截止性测试/账龄分析/月度明细三Tab+表单+结果表格）
- [x] AuxSummaryPanel.vue — 辅助余额汇总匹配（科目余额vs辅助汇总+差异高亮+统计）
- [x] ConsolSnapshots.vue — 合并数据快照（列表+创建）
- [x] ReportFormatManager.vue — 排版模板管理（列表+创建弹窗+字体/字号配置）
- [x] CheckInsPage.vue — 打卡签到（打卡按钮+记录列表+上下班标签）
- [x] ReviewConversations.vue — 复核对话（已有，双栏布局+消息列表+发送+关闭+导出）
- [x] ForumPage.vue — 论坛（已有，分类筛选+发帖+评论+点赞+匿名）
- [x] PrivateStorage.vue — 私人库（已有）

### Task 22.4 导航集成
- [x] ThreeColumnLayout navItems 新增：私人库/吐槽求助/排版模板
- [x] 新增图标导入：ChatDotSquare/Suitcase/Document
