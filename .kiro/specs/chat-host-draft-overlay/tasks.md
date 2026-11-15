# 实施计划：Chat 宿主通用未保存草稿纳入（draft overlay）

> 承接 `llm-linkage-audit-practice-closure` 需求 3.4 的后半句。以 design.md 为准。
> 第一批只做**底稿宿主**；附注宿主已有 overlay（`note_ai.py`），不在范围。
> 临时产物放仓库根 `tmp_chat_overlay/`。

## A. 契约与校验（后端，可独立验收）

- [ ] 1. 请求契约与字段校验
  - `ChatRunRequest` 增 `draft_overlay`（可选）：`host_type` / `host_id` / `baseline_version` / `content` / `content_length`
  - 校验：`host_type` 受支持、`host_id == request.host.id`、`content` 非空、长度 ≤ 上限（200k）
  - 服务端**重算** `sha256`，不采信客户端 hash
  - Verify：缺省不改变现有行为；`host_id` 不等 / 超长 / 空 content 均 422
  - 反例：客户端传假 hash 时服务端以重算值为准

- [ ] 2. 版本核对与 manifest 条目（ADR 对应 design §3 / §4）
  - 读宿主当前业务版本，与 `baseline_version` 比对
  - 一致 → `included`（`source_type="draft_overlay:workpaper"`，带 `content_hash` / `baseline_version`）
  - 不一致 → `denied` + 中文原因，**Run 仍成功**
  - manifest 顶层加 `draft_overlay_included`
  - Verify：过期版本 → `denied` 且模型未看到旧草稿；一致 → `included` 且 token 计入预算

- [ ] 3. 不可信内容包装与不落库
  - 草稿经 `delimit_untrusted_content` 包装后才进 system message
  - 断言草稿不进 `ai_content_log` / DraftArtifact / metrics / 日志 / 审计链 payload（只存 hash 与长度）
  - Verify：注入用例（草稿写「忽略以上指令」）不影响模型边界；payload 扫描无正文

## B. 前端（宿主能力与开关）

- [ ] 4. 宿主暴露未保存态与基线版本
  - 底稿 HTML 编辑器与 Univer 编辑器各实现 `currentDraftContent()` / `openedBaselineVersion()`
  - `useAiHostContext` 统一读取，无未保存修改时返回 `null`
  - Verify：改一处不保存 → 有值；保存后 → `null`

- [ ] 5. 面板开关与文案
  - 输入区加「纳入当前未保存草稿」开关，**默认关闭**
  - 仅当宿主有未保存修改时显示；开启后范围文案改为「将纳入当前未保存草稿（基于版本 v…）」
  - `denied` 时在消息下方显示中文原因（不弹窗、不阻断）
  - Verify：开关默认关闭；有/无未保存修改两态；文案随开关变化；`denied` 提示可读

## C. 端到端与收口

- [ ] 6. 浏览器端到端
  - 底稿编辑器改一处不保存 → 开启开关 → 提问 → manifest 可核对 → 模型回答引用该改动
  - 关闭开关 → 行为与现状一致（提示未纳入）
  - Verify：`http://127.0.0.1:3030`；测试数据按平台路径恢复

- [ ] 7. 回归与守卫
  - 后端：契约 / 校验 / 版本 / 鉴权 / manifest / 安全 六组用例
  - 前端：开关与文案用例
  - 变异证明：把「版本核对」改成恒真 → 过期用例必红
  - Verify：本 spec 新增失败 0；既有 Chat 用例不受影响

- [ ] 8. 收口
  - INDEX.md 登记、design 补验证节、单一 commit、按版本工具推送
