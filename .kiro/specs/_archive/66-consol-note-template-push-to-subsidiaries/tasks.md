# 集团级附注披露模板下推 — 实施任务

## Phase 1：数据模型与下推服务

- [x] 1. 迁移脚本 `V204__consol_note_template_push_log.sql`（2026-10-23）
  - 新建 `consol_note_template_push_log` 表 + 索引；R204 回滚

- [x] 2. 模板行 `category` 字段支持（2026-10-23）
  - `_validate_template_rows` 增加 `category` 校验（required/optional/dynamic_zone），默认 required
  - dynamic_zone 行允许空 canonical_name（自动填 `[动态行区]`）

- [x] 3. 下推服务 `consol_note_template_push_service.py`（2026-10-23）
  - `build_skeleton_rows` / `merge_rows` / `push_template_to_subsidiaries`
  - 14 例单元测试全绿

- [x] 4. 下推端点 `POST /consolidation/notes/{pid}/{year}/push-template`（2026-10-23）
  - edit 权限；支持指定章节或全部已绑定章节

## Phase 2：拉数时 row_id 精确匹配

- [x] 5. `suggest_template_rows` 第 0 级 `exact_id` 匹配（2026-10-23）
  - _pushed_row_id → target_row_id，confidence=1.0

- [x] 6. `apply_detail_refresh` 传递 row_id（2026-10-23）
  - source_by_rid 索引 + label fallback 到 rid

## Phase 3：前端

- [x] 7. 模板编辑器 `category` 字段（2026-10-23）
  - 每行增加类别下拉（必填/可选/动态行区），EditRow 接口扩展

- [x] 8. 下推按钮与结果弹窗（2026-10-23）
  - ConsolNoteTab 工具栏「📤 下推模板」+ 二次确认 + 成功/失败结果弹窗

- [x] 9. 子企业附注编辑器行级交互（2026-10-23）
  - isPushedLocked 判断 + 🔒图标（浅蓝底色）+ 锁定行不可删除提示

## Phase 4：集成测试与验收

- [x] 10. 后端 e2e：下推 → 子企业填数 → 合并拉数全链路（2026-10-23）
  - 6 例全绿：固定行 rid 匹配 / 可选行取消 / 动态行七级匹配 / 增量合并保值 / 结构 hash 一致 / 改名 rid 兜底
  - 加上单元测试共 20 例全绿

- [x] 11. 真库验证（2026-10-23）
  - 查到【测试】集团 3 项目（乙/甲/集团），子企业 0 条附注
  - 纯函数验证：骨架 5 行、固定行 rid 匹配 5 条 conf=1.0、改名行 rid 兜底、动态行 manual、增量合并保值、同骨架 hash 一致
  - 零残留（纯函数验证不写 DB）

- [x] 12. 浏览器全流程实测（2026-10-23 Playwright MCP）
  - 📤 下推模板按钮出现在工具栏（明细映射和模板管理之间）
  - 点击弹出二次确认弹窗（标题「下推集团模板」+ 说明 + 取消/确认下推按钮）
  - 确认下推后无 JS 错误（console 0 errors）、弹窗正常关闭
  - 截图：`consol-note-push-template-button.png` / `consol-note-push-after-confirm.png`

## 范围外

- P3（底稿动态行→附注行结构同步）：需改公式推送链路，另立 spec
- P4（统一 schema）：长期架构改造
