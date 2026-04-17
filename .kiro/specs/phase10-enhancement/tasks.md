# Phase 10 — 任务清单

## 任务组 1：底稿下载与导入

### Task 1.1 底稿批量下载
- [ ] `POST /api/projects/{id}/workpapers/download-pack` 打包下载 API
- [ ] 下载前自动预填（调用 PrefillService）
- [ ] ZIP 打包（zipfile 模块，目录结构：循环/编号_名称.xlsx）
- [ ] 单个底稿下载（`GET /api/projects/{id}/workpapers/{wp_id}/download`）
- [ ] 前端 WorkpaperList.vue 添加勾选+下载按钮+单个下载按钮

### Task 1.2 底稿导入（离线编辑回传）
- [ ] `POST /api/projects/{id}/workpapers/{wp_id}/upload` 上传 API
- [ ] 版本冲突检测（file_version 比对）
- [ ] 冲突处理（409 + diff 摘要 / 覆盖 / 保留）
- [ ] 导入后触发 ParseService + WORKPAPER_SAVED 事件
- [ ] 前端上传弹窗（版本冲突提示+选择操作）

---

## 任务组 2：连续审计

### Task 2.1 一键创建当年项目
- [ ] `POST /api/projects/{id}/create-next-year` API
- [ ] projects 表新增 prior_year_project_id 字段
- [ ] 复制 basic_info/account_mapping/project_assignments/template_set
- [ ] 上年 trial_balance.audited → 当年 opening
- [ ] 上年 disclosure_note 期末 → 当年上期
- [ ] 上年 adjustments(is_continuous) 结转
- [ ] 上年 unadjusted_misstatements carry_forward
- [ ] 前端项目详情面板"创建下年项目"按钮

### Task 2.2 跨年数据对比
- [ ] 当年底稿中查看上年同科目数据（PREV 函数已支持，前端展示待实现）
- [ ] 附注变动分析自动对比上年数据生成变动说明（复用 note_ai generate-analysis）

---

## 任务组 3：服务器存储与分区

### Task 3.1 私人库管理
- [ ] PrivateStorageService（上传/下载/删除/容量检查）
- [ ] `GET /api/users/{id}/private-storage` 文件列表
- [ ] `POST /api/users/{id}/private-storage/upload` 上传
- [ ] `GET /api/users/{id}/private-storage/quota` 容量查询
- [ ] 容量上限 1GB，90% 提示清理
- [ ] 前端 PrivateStorage.vue 页面

### Task 3.2 归档联动
- [ ] 项目归档时锁定所有底稿为 archived
- [ ] 自动生成归档清单
- [ ] 触发 enrich_resume 更新人员简历
- [ ] 前端归档确认弹窗

### Task 3.3 存储统计看板
- [ ] `GET /api/admin/storage-stats` 存储统计 API
- [ ] 按项目/用户/年度统计存储占用
- [ ] 前端 ECharts 饼图/柱状图展示

---

## 任务组 4：过程记录与附件关联

### Task 4.1 底稿编辑记录
- [ ] 底稿保存时记录编辑摘要到 logs 表
- [ ] 前端底稿详情面板显示编辑历史

### Task 4.2 附件双向关联
- [ ] 底稿详情面板显示关联附件列表
- [ ] 附件详情显示关联底稿列表
- [ ] 上传附件时可选择关联底稿

### Task 4.3 人机协同标注
- [ ] AI 生成内容写入 ai_content 表（复用 Phase 4 定义）
- [ ] 前端 AI 标签（紫色背景 + "AI 辅助-待确认"）
- [ ] 人工确认后标签变为"已确认"
- [ ] 关键底稿提交复核前检查未确认的 AI 内容

---

## 任务组 5：LLM 深度融合底稿

### Task 5.1 对话式底稿填充
- [ ] `POST /api/workpapers/{wp_id}/ai/chat` SSE 流式对话 API
- [ ] 对话上下文注入：parsed_data + 四表数据 + 知识库 RAG
- [ ] 回复中包含 fill_suggestion（cell_ref + value）
- [ ] 前端 WorkpaperEditor.vue 添加 LLM 对话侧边栏
- [ ] 选中单元格 → 对话窗口显示上下文 → AI 回复填入

### Task 5.2 台账分析底稿生成
- [ ] `POST /api/projects/{id}/ai/generate-ledger-analysis` 生成台账分析
- [ ] LLM 根据序时账生成大额/异常/关联方交易分析
- [ ] 自动生成审计说明
- [ ] 保存为新底稿（wp_index + working_paper）

### Task 5.3 知识库双向关联
- [ ] 底稿编辑时搜索知识库（复用 knowledge_retriever）
- [ ] 知识库文档被底稿引用时记录关联关系
- [ ] 双向查看：底稿→引用的知识库文档，知识库→被引用的底稿

---

## 任务组 6：抽样程序增强

### Task 6.1 截止性测试
- [ ] `POST /api/projects/{id}/sampling/cutoff-test` API
- [ ] 自动从 tb_ledger 提取期末前后 N 天交易
- [ ] 填入截止性测试底稿模板
- [ ] 前端截止性测试配置（天数/科目/金额阈值）

### Task 6.2 账龄分析
- [ ] `POST /api/projects/{id}/sampling/aging-analysis` API
- [ ] 自动从 tb_aux_balance 生成账龄分析表
- [ ] 按账龄区间（1年内/1-2年/2-3年/3年以上）分组
- [ ] 填入账龄分析底稿

### Task 6.3 月度明细填充
- [ ] `POST /api/projects/{id}/sampling/monthly-detail` API
- [ ] 按月汇总 tb_ledger 数据
- [ ] 自动填入月度明细分析底稿

### Task 6.4 抽样结果与底稿关联
- [ ] 抽样选中的样本自动填入对应底稿
- [ ] MUS 评价结果自动生成审计结论

---

## 任务组 7：合并报表增强

### Task 7.1 合并锁定同步
- [ ] 合并项目开始时锁定单体试算表（consol_lock 字段）
- [ ] 锁定期间单体禁止修改试算表/调整分录
- [ ] 合并完成后自动解锁
- [ ] 前端锁定状态提示

### Task 7.2 外部单位报表导入
- [ ] 导入其他审计师审计的单位报表（Excel）
- [ ] 导入附注（Word），LLM 辅助解析
- [ ] 导入数据纳入合并试算表

### Task 7.3 独立模块使用
- [ ] 仅合并模块入口（无需单体项目）
- [ ] 仅报告复核模块入口
- [ ] 仅报告排版模块入口
- [ ] 前端模块选择页面

---

## 任务组 8：复核对话系统

### Task 8.1 数据模型与后端
- [ ] review_conversations + review_messages 表（Alembic 迁移）
- [ ] ORM 模型 + Pydantic Schema
- [ ] `POST /api/review-conversations` 创建对话
- [ ] `POST /api/review-conversations/{id}/messages` 发送消息
- [ ] `PUT /api/review-conversations/{id}/close` 关闭对话
- [ ] `POST /api/review-conversations/{id}/export` 导出 Word
- [ ] SSE 推送新消息通知

### Task 8.2 前端对话组件
- [ ] ReviewConversation.vue 对话页面
- [ ] 消息列表（文字/图片/文件）
- [ ] 发送消息输入框
- [ ] 结束对话按钮（仅发起人可见）
- [ ] 导出对话记录按钮
- [ ] 看板集成（进行中对话数）
- [ ] 质量控制复核人员对话通道预留

### Task 8.3 LLM 底稿复核
- [ ] `POST /api/workpapers/{wp_id}/ai/review` 复核 API
- [ ] 复核时加载 TSJ/ 对应提示词
- [ ] LLM 自动检查底稿（数据完整性/逻辑一致性/格式规范）
- [ ] 生成结构化 findings（类型/严重度/位置/建议）
- [ ] 前端复核结果面板

### Task 8.4 导出功能增强
- [ ] 复核记录导出为 Word/PDF
- [ ] 对话记录导出为 Word/PDF
- [ ] 底稿复核报告导出（含所有 findings + 处理状态）

---

## 任务组 9：报告复核溯源

### Task 9.1 溯源 API
- [ ] `GET /api/report-review/{project_id}/trace/{section_number}` 溯源查询
- [ ] 返回：附注数据 + 底稿审定数 + 审计说明 + 大额交易明细
- [ ] 前端溯源面板（在报告复核页面中）

---

## 任务组 10：工时打卡与足迹

### Task 10.1 打卡签到
- [ ] check_ins 表（Alembic 迁移）
- [ ] `POST /api/staff/{id}/check-in` 打卡 API（含 GPS）
- [ ] 打卡与工时联动
- [ ] 前端打卡按钮 + 日历视图

### Task 10.2 足迹报告
- [ ] 每半年 LLM 生成足迹+工作总结
- [ ] 推送给成员和合伙人
- [ ] 前端足迹展示页面

---

## 任务组 11：吐槽与求助专栏

### Task 11.1 论坛系统
- [ ] forum_posts + forum_comments 表（Alembic 迁移）
- [ ] CRUD API（发帖/评论/点赞/删除）
- [ ] 匿名发帖支持
- [ ] LLM 敏感内容过滤
- [ ] 前端 ForumPage.vue

---

## 任务组 12：私人库与 LLM 对话

### Task 12.1 私人库
- [ ] PrivateStorageService + API
- [ ] 上传后自动向量化索引
- [ ] 容量管理（1GB 上限 + 90% 提示）
- [ ] 前端 PrivateStorage.vue

### Task 12.2 私人库 LLM 对话
- [ ] 基于私人库的 RAG 对话
- [ ] 对话记录导出 Word
- [ ] 与项目知识库打通

---

## 任务组 13：辅助余额表汇总

### Task 13.1 明细汇总与匹配
- [ ] `GET /api/projects/{id}/ledger/aux-summary` 汇总匹配 API
- [ ] 匹配一致：折叠辅助明细
- [ ] 不一致：红色高亮差异 + 原因提示
- [ ] 前端可视化（饼图/柱状图展示辅助维度构成）

---

## 任务组 14：权限精细化

### Task 14.1 删除权限控制
- [ ] 底稿/调整分录/附件删除时检查 created_by
- [ ] 项目经理可删除项目内所有内容
- [ ] 合伙人/管理员可删除任何内容
- [ ] 删除操作记录审计日志

---

## 执行顺序

1. **Task 1.1-1.2**（底稿下载导入）→ 2. **Task 2.1**（连续审计）
3. **Task 3.1-3.2**（存储分区+归档）→ 4. **Task 4.1-4.2**（过程记录+附件关联）
5. **Task 5.1-5.3**（LLM 底稿填充）→ 6. **Task 6.1-6.3**（抽样+截止性+账龄）
7. **Task 7.1-7.3**（合并增强）→ 8. **Task 8.1-8.3**（复核对话+LLM复核）
9. **Task 9.1**（报告溯源）→ 10. **Task 13.1**（辅助余额汇总）
11. **Task 14.1**（权限精细化）→ 12. **Task 10.1-10.2**（打卡足迹）
13. **Task 11.1**（吐槽专栏）→ 14. **Task 12.1-12.2**（私人库+LLM对话）
