# P0 复盘：「确认后写入目标」调研结论与处置方案

> 2026-10-21 调研完毕。结论：**不做自动写入底稿，只做附注**；底稿路径改文案。

## 调研结论

### 现状

`ai_content_log_service.confirm()` 只把 `confirm_action` 从 `pending` 改成 `confirmed`，
写一条审计日志，**没有任何下游把内容写进底稿或附注**。

前端面板提示「请在本页 AI 生成内容待确认中确认后生效」，用户点「确认」后以为内容已写入，
实际什么都没发生。这个空洞自 `doc-level-ai-chat` R4（2026-05-31）起就存在。

### 底稿路径（不自动写入）

底稿的 `parsed_data.html_data[sheet_name]` 是按行列索引的结构化字典（`cells.A1`、`cells.B2` 等）。
AI 采纳的是一段自然语言文本（几十到几百字的审计结论 / 分析），没有对应的行列位置。

`target_cell` 字段在底稿采纳时的值是 `workpaper:<uuid>` 或 `workpaper:<uuid>:<用户填的位置>`，
「位置」是用户在对话框里随意填的字符串（如「E5」「正文第一段」「结论区域」），不保证对应
真实的单元格坐标，也没有 sheet_name 信息。

要把 AI 文本写进底稿需要：
1. 确定写入哪个 sheet
2. 确定写入哪个 cell（行列坐标）
3. 构造合法的 html_data 结构
4. 处理编辑锁（底稿可能被另一用户打开编辑）
5. 走 CAS commit 路径（content_revision 乐观锁）

这不是在 confirm 端点加几行代码能做到的——需要用户在底稿页面上选定目标格、确认写入方式
（追加/替换），本质上是一个编辑操作。

**处置**：底稿路径保持现状（confirm = 标记已审阅、可作后续引用依据），但修改文案，
不再说「确认后生效」：

- 面板提示改为「已进入待确认列表，请在底稿页面复制到目标位置后确认」
- 待确认抽屉「确认」按钮的语义改为「标记为已审阅」，旁边显示「复制到剪贴板」按钮
- 文案与按钮变化不需要后端改动，纯前端

### 附注路径（可以自动写入）

附注的 `text_content` 是 Markdown 正文，追加 AI 文本是自然的。
`DisclosureEngine.update_note(note_id, text_content=content, user_id=user_id)` 已经是成熟路径。

`target_cell` 在附注采纳时的值是 `note:<note_uuid>` 或 `note:<note_uuid>:<位置>`。
note_uuid 是 disclosure_notes 表的主键，可以直接反查到章节。

**处置**：后端 confirm 端点在 `confirm_action='confirmed'` 之后、commit 之前，
按 `target_cell` 前缀判断：
- `note:` → 把 `generated_content`（或 `revised_content`，如果有修订）追加到
  `DisclosureNote.text_content` 末尾，加分隔标记
- 其他前缀 → 不自动写入

这个改动集中在 `ai_content.py` 的 `confirm_ai_content` 端点，约 20~30 行。

### 编辑锁

附注编辑器有编辑锁（`editing_lock_service.acquire_lock`，`resource_type='disclosure_note'`）。
confirm 写入前应检查目标章节是否被锁，被锁时返回具体原因（谁在编辑），不静默跳过。

## 要做的事（追加到本 spec）

1. 后端 `ai_content.py` confirm 端点：附注类 target_cell 确认后追加 text_content
2. 前端 `AiContentPendingBanner.vue`：底稿类待确认项改文案 + 加「复制」按钮
3. 前端面板：底稿就地采纳的成功提示改文案
4. 测试：PG 测试确认附注写入 + 编辑锁拒绝 + 底稿不自动写入

## 裁定依据

- `doc-level-ai-chat` R4.3：「IF AI 生成内容未确认 THEN 不直接写入底稿/附注」——这是对
  未确认内容的约束（pending 不写），不是对确认后的自动写入的承诺。
- `disclosure-note-knowledge-ai-enrichment` R3.1：「经 wrap_ai_output_with_log / 现有采纳流处理，
  pending 状态不直接写 text_content」+ R3.2：「审计师确认采纳 THEN 才把内容落入 text_content」
  ——这里明确说了附注应该在确认后写入。
- 底稿无对应的 R3.2 类条款——在结构化数据的底稿里「自动写入」缺乏合理的目标位置。
