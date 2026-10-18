# 交付件回填 / 在线编辑保存 / 签发清单完整性

## 1. 背景与实测结论

承接 `deliverable-trio-generation-accuracy` tasks.md「未修（如实登记）」六条，设计阶段现状 grep + 真库核验（2026-10-17，
重药安徽 0ec33ac9 附注交付件 f2238a0d，最新 v16）又补出若干同源缺陷。探针在仓库外、只读。

### 1.1 签发一致性清单（合伙人签字页）在真实 PG 上恒「可签发」
- 9 条裸 SQL 有 8 条对真实 schema 无效：`trial_balance.is_stale`（无此列）；调整分录 `NOT IN ('approved','cancelled')`
  （枚举只有 draft / pending_review / approved / rejected，且漏 `is_deleted`）；`cross_module_conflicts.target_type / conflict_type` ×2
  （真名 `target_module` / `target_field`）；`event_cascade_health` ×2（表不存在）；`projects.opinion_type`（在 `audit_report`）；
  用 `financial_report` 判「报告正文已生成」（应为 `audit_report`）；`ai_generated_content`（表不存在，真表 `ai_content` /
  `ai_content_governance`）。
- 9 项共用一个会话、无 SAVEPOINT：首条失败即事务中止，其余全部失败 → 各自 `except` 记 info「暂不可用」→ 没有 blocking →
  `can_signoff = true`（fail-open）。
- 端点只校验登录，不校验项目成员；年度缺省回落「今年 - 1」；跳转路由 `/report`、`/workpapers/{id}`、`/ai-content` 前端不存在。

### 1.2 交付件回填（在线编辑 → 附注 / 报告正文）
- 路由没有 `db.commit()`（`get_db` 不自动提交）⇒ 写入随会话关闭回滚，界面却提示「已成功回填 N 个章节」。
- 章节数 > 100 转异步：`create_job(params=...)` 与真实签名不符（TypeError → 500），全仓也没有 worker 处理
  `deliverable_writeback`。真实附注交付件 100+ 节 ⇒ 恒走这条分支。
- 提取口径错：块内段落（除 `##` 行与 `_is_title_paragraph` 判中的行）全部拼成正文 ⇒ 编号标题、子标题、表题、【…】指引
  写进 `text_content`；「1、」「（一）」开头的正文行被当标题丢弃；markdown 表格、交付过滤掉的编制提示、加粗等标记全部丢失。
- 冲突判定用含试算表金额的 `source_snapshot_hash` ⇒ 金额一变就误报冲突；`baseline_value` 是「[生成时基线 hash=…]」占位；
  「保留上游」计入已回填；写回不更新 `rendered_block_hash`；`NOTE_SECTION_SAVED` 在提交前发布。
- 护栏 `_classify_change` 只要块内有数字表就判 TABLE 拒绝（不看表格改没改）⇒ 只改正文也收到「金额须走调整分录」。
- 附注写入不记编辑人；前端展示 `item.reason`（后端字段是 `rejection_reason`，拒绝原因恒空）、年度回落日历年（2026 年库内
  无附注 ⇒ 全部「写入失败」）、未带 `_silent`（错误弹两次）；冲突弹窗不看回执就提示「回填完成」。
- 回填读「最近一次保存的版本」，而在线编辑的修改要到关闭编辑器才落版本 ⇒ 编辑器里点回填看不到本次会话的修改。

### 1.3 在线编辑保存（OnlyOffice 回调）
- 只处理 status 2；`customization.forcesave = true` 使「保存」按钮触发 status 6，被忽略（不落版本），却释放了编辑席位。
- 不比对回调体 `key`（下发的 `deliverable-{task}-{版本}`）：编辑期间他人刷新 / 再生成，关闭时以旧底版覆盖新版本内容，无标记。
- 不幂等：Document Server 重试 / 同内容重复回调各生成一个新版本。
- 编辑人校验只查 `project_users`；admin 不在其中（安徽项目 project_users 0 行）⇒ v15 在线编辑 `edited_by` 为空。
- OnlyOffice 保存时给 90 个编号级别写 `<w:isLgl w:val="false"/>`，LibreOffice 按「开启」处理 ⇒「七、财务报表主要项目注释」
  渲染成「7、」。探针实证：剥掉显式 false 后恢复「七、」，与生成版 v14 一致。

### 1.4 历史版本文件被后续生成覆盖
- 附注 / 报表生成用固定文件名 `disclosure_notes_{year}.docx`、`financial_reports[_unadjusted]_{year}.xlsx`（路由 2 处 + 全套生成
  3 处）⇒ 每次生成覆盖上一版文件。真库：19 个版本共用 3 个文件，其中 16 个版本记录的 SHA-256 与磁盘不符（安徽附注 v2~v12、
  两份报表 v2/v4/v5/v9/v10）。
- 下载与 OO 签名下载不校验指纹 ⇒ 下载历史版本拿到的是最新内容；`verify_version_immutability` 只查记录存在（恒 True）。
- 版本号 `max+1` 无锁、`(word_export_task_id, version_no)` 无唯一索引 ⇒ 并发保存可得重复版本号并互相覆盖文件。

### 1.5 裸 SQL 列契约盲区
- `test_raw_sql_column_contract` 只校验带别名限定的列，单表语句里的无限定列不查；表级契约按「ORM ∪ 迁移」判表存在，
  ORM/迁移有而真库无的表查不出。上一轮 AST 扫描（实施时重算为准）发现 80+ 处无限定列在真实 PG 不存在，含：
  - `working_paper.quality_score / procedure_completion_rate`（ORM 与迁移均无）⇒ 程序「标记完成 / 裁剪」端点每次 500，
    质量评分 / 健康看板读同两列；
  - linkage_service 一致性检查、EQCR 读 `trial_balance.debit/credit_amount`、若干渲染策略与取数器、报表溯源、M 循环
    `checklist_responses`、附注自定义章节 / 数据锁、导出完整性、重分类等；幽灵表 4 张。

### 1.6 溯源面板
- 财务报表 xlsx 打开溯源面板提示「该出品物版本不支持溯源，请重新生成」——报表本就没有章节溯源，重新生成也不会有。

## 2. 用户故事与验收标准

### US-1 签发清单如实（fail-closed）
- AC-1.1 每项检查只引用真实 schema 的表 / 列 / 枚举值，优先复用既有权威实现（`stale_summary_aggregate.get_full_summary`、
  `conflict_resolution_service.count_pending / list_pending`、`TrialBalanceService.check_consistency`）。
- AC-1.2 每项检查在独立 SAVEPOINT 内执行；某项执行失败 ⇒ 产出 blocking「X 检查执行失败，无法确认」，其余检查照常出结果，
  `can_signoff = false`。
- AC-1.3 口径：未完成审批的调整分录（draft / pending_review，未删除）、未调解跨模块冲突（与签字门禁规则同口径）、无审计报告、
  试算表审定数公式不一致 ⇒ blocking；报表行 / 附注 / 底稿过期、报告正文过期 ⇒ warning；AI 内容未确认在 strict 下 blocking、
  否则 warning。
- AC-1.4 端点按项目成员鉴权（`require_project_access("readonly")`）；年度缺省取项目审计年度，取不到返回 422；签字页显式传年度。
- AC-1.5 跳转路由只用前端真实存在的路由；没有页面可跳的项 `route = null`。
- AC-1.6 表级契约 `_KNOWN_PHANTOM_DEBT` 删除 `ai_generated_content`、`event_cascade_health`。

### US-2 附注回填下线（数据流向裁定，2026-10-17 用户确认）
- 背景：附注数据的唯一权威来源是**底稿披露表的单项推送**（底稿 → 附注）。交付中心是附注模块的**只读下游出口**
  （附注 → 交付 docx）。原设计让审计师在交付 Word 里改文字再「回填附注模块」是**逆流**：绕过「底稿→附注」唯一链、
  让下游改上游，交付件里的改动可能与底稿事实不符，污染权威源。即使做了行级补丁 + 双校验不误写，方向本身仍错。
- AC-2.1 **移除附注回填**：下线 `WritebackResultPanel`「回填到附注模块」入口、`DeliverableWritebackService` 的附注写回路径、
  `DisclosureNoteAdapter.write_upstream`；`/writeback` 端点对 `disclosure_notes` 返回 400「附注不支持从交付件回填，
  请回底稿修改后同步到附注」。`supports_writeback(disclosure_notes)` 置为 False。
- AC-2.2 删除「> 100 节转异步」分支与 `_delegate_to_async_job`（全仓无 worker，走到即 500）。
- AC-2.3 附注要改内容 ⇒ 回**底稿**改（源头），不在交付 Word 改。在线编辑保存（US-5）仍可把交付 docx 另存为新版本，
  但那只是交付件版本，不触碰附注模块。

### US-3 报告正文回填保留（不涉上游联动）
- AC-3.1 报告正文（`audit_report`）段落文字就在交付件里、不来自底稿 / 试算表的单项推送，回填不构成逆流 ⇒ **保留**。
  `supports_writeback(audit_report)` 维持 True，写 `AuditReport.report_body_json.sections`，派生 / 模板固定段落仍拒绝（需求 9.4）。
- AC-3.2 报告正文回填成功后路由提交事务；回执按「已回填 / 已拒绝 / 未回填」分组，拒绝原因显示 `rejection_reason`。
- AC-3.3 报告正文冲突判定与写入口径不变（现状已按段落哈希，不涉试算表金额）。

### US-4 导出前一致性确认闸门（附注）
- AC-4.1 交付中心「生成 / 导出附注」前比对**附注模块当前内容** vs **底稿披露表应推送内容**，列出不一致章节：
  ①有对应底稿披露表但从未同步到附注（`needs_sync`）；②附注章节标记为过期（`is_stale`，上游变更后未刷新）。
- AC-4.2 存在不一致时返回**待确认**结构（HTTP 可导出但带 `requires_confirmation=true` + 不一致章节清单 + 建议动作），
  前端弹确认框列出章节并提供「去底稿同步」跳转；用户显式确认「仍要导出」或先去同步后，才真正落交付件。
- AC-4.3 前端确认框全中文：标题「附注与底稿可能不一致」，正文列出章节（章节号 + 名称 + 原因），两个动作「返回同步」/「仍要导出」。
- AC-4.4 一致性数据复用 `note_readiness_service.build_readiness`（`needs_sync` / `is_stale`），不新造判定；查询失败 fail-open
  （放行导出，不因看板故障阻断已完成的编制）。
- AC-4.5 报告正文 / 财务报表导出不受此闸门影响（它们不走底稿→附注推送链）。

### US-5 在线编辑保存可信
- AC-5.1 回调体 `key` 必须是本交付物的 doc_key，否则拒绝并写安全日志。
- AC-5.2 status 2 与 status 6 都落版本；下载内容与最新版本指纹相同 ⇒ 不新建版本（幂等）。
- AC-5.3 新版本记录底版版本号与会话 key；底版之后存在非本会话产生的版本 ⇒ 版本链标「基于第 N 版编辑，覆盖了第 M 版」并写
  审计日志；不拒绝保存（不丢编辑）。
- AC-5.4 编辑人校验与项目权限同口径（在册、未停用；admin 或项目成员）；仍不回退创建人。
- AC-5.5 编辑席位只在会话结束（status 2 / 3 / 4）释放。
- AC-5.6 OO 保存的 docx 落库前去掉 `<w:isLgl w:val="false|0|off"/>`（与缺省等价），LibreOffice 不再把「七、」渲染成「7、」。

### US-6 版本文件不可覆盖
- AC-6.1 每个版本的物理文件名唯一（`{主名}_v{版本号}{后缀}`），后缀按调用方给的文件类型（xlsx 不再按默认写成 .docx）。
- AC-6.2 同一交付物的新版本创建串行化（任务行 `FOR UPDATE`）；`(word_export_task_id, version_no)` 唯一索引兜底。
- AC-6.3 下载 / OO 签名下载前校验大小与 SHA-256；不一致返回 409「该版本文件已被后续生成覆盖（历史缺陷），无法提供原始内容」。
- AC-6.4 `verify_version_immutability` 改为真校验指纹。

### US-7 裸 SQL 无限定列契约
- AC-7.1 新增 pg_only 守卫：单表语句的无限定列 ⊆ 真实 PG 表的列；`FROM/JOIN/UPDATE/INSERT INTO` 的表 ⊆ 真实 PG 表；现存违规冻结为
  基线，只许减少，基线条目必须仍真实存在（不得虚高）。
- AC-7.2 高影响点逐条修复（以实施时重算为准），修一条删一条基线；`working_paper.quality_score / procedure_completion_rate`
  按「补迁移 + ORM」修（三个读方、两个写方都在用）。

### US-8 溯源提示
- AC-8.1 能力单一真源新增 `supports_lineage`（附注、报告正文）；不支持的类型面板说明「财务报表按报表行取数，没有章节溯源」，
  不再提示重新生成。

## 3. 非目标与约束
- 不改附注导出的渲染 / 过滤规则本身（只在正文区两侧加书签、把上下文落库）；不改报告正文的提取与写入口径。
- 已被覆盖的历史文件无法恢复：只保证不再发生、下载如实拒绝；已落库的 OO 版本文件不回改（会破坏其指纹）。
- 不自动合并「在线编辑」与「刷新 / 再生成」的内容，只标记 + 留痕。
- 并发会话未提交的文件不碰；service 只 flush、router 提交；hypothesis `max_examples=5`；UI 全中文。
