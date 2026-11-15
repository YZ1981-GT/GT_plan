# 设计文档：Chat 宿主通用未保存草稿纳入（draft overlay）

## 0. 设计结论

不新造上下文机制。在既有 `ContextPlan` 装配里增加一类**可选**上下文源：`draft_overlay`。
它的生命周期只有一轮 Run —— 不落库、不进 DraftArtifact、不进 metrics。

复用附注侧 `note_ai.py` 已有的 overlay 字段语义（`host_type` / `host_id` / `baseline_version` /
`content_hash` / `content_length` / `matches_saved`），使全平台只有一套 overlay 契约。

## 1. 现状基线（2026-11-15 现扫）

| 编号 | 当前事实 | 证据 | 判定 |
|---|---|---|---|
| B1 | 附注生成链路已有 overlay 绑定 | `routers/note_ai.py`：`overlay_content` / `overlay_matches_saved` → `metadata["draft_overlay"]` 含 `host_type`/`host_id`/`baseline_version`/`content_hash`/`content_length`/`matches_saved` | 已有，语义可复用 |
| B2 | Chat Run 侧 `ai_chat/` 全目录 **0 处** `overlay` | `grep -r overlay backend/app/services/ai_chat/` 无命中 | 未实现 |
| B3 | Chat 上下文装配唯一入口是 `context_plan.build_context_plan` | `context_plan.py`：host / review prompt / mentions / attachments / knowledge / relation → manifest | 可插入点明确 |
| B4 | 前端范围文案已提示「当前未保存修改不会纳入本轮」 | `useAiHostContext`；浏览器双态实测通过（`llm-linkage` design §12.2） | 前半句已交付 |
| B5 | 未保存正文只能从编辑器内存取，服务端拿不到 | 底稿 HTML 编辑器 / Univer 各自持有内存态；库里的 `checklist_responses` 是已保存值 | 必须由前端提交 |

## 2. 请求契约

`ChatRunRequest` 新增可选字段（向后兼容，缺省 `None` 表示不纳入）：

```text
draft_overlay?: {
  host_type: "workpaper" | "note"        # 第一批只接受 workpaper
  host_id: string                        # 必须等于 request.host.id
  baseline_version: string               # 编辑器打开时该宿主的业务版本
  content: string                        # 未保存正文（服务端重新算 hash，不信客户端 hash）
  content_length: number                 # 便于上限校验（服务端仍以实际长度为准）
}
```

**关键约束**：
- `host_id` 必须等于 `request.host.id`，否则 422（不允许借 overlay 塞别的宿主内容）。
- `content` 服务端重新算 `sha256`，**不采信客户端传来的 hash**（客户端 hash 只用于诊断比对）。
- `content_length` 超过上限（建议 200k 字符，与附注一致）直接 422，不裁剪（静默裁剪会让模型看到半截内容）。

## 3. 服务端校验顺序（fail-closed）

```text
1. request.host 已通过宿主鉴权（既有逻辑，先于 overlay）
2. draft_overlay 存在 → 校验 host_type 受支持
3. 校验 draft_overlay.host_id == request.host.id
4. 校验 content 非空、长度 <= 上限
5. 重算 content_hash = sha256(content)
6. 读该宿主当前业务版本 current_version
7. baseline_version == current_version ?
     是 → 纳入（status="included"，source_type="draft_overlay:workpaper"）
     否 → 不纳入（status="denied"，reason="草稿基于旧版本 v…，当前 v…，请先保存或刷新"）
8. 包装为不可信内容块（delimit_untrusted_content），再进 system message
```

任何一步失败都**不阻断整轮对话**：Run 继续，但 manifest 里记 `denied` + 中文原因，前端显示提示。

## 4. Manifest 契约

复用 `context-plan-v1`，新增条目：

```json
{
  "source_type": "draft_overlay:workpaper",
  "source_id": "<host_id>",
  "status": "included" | "denied",
  "label": "当前未保存草稿（底稿 B1-1）",
  "used_tokens": 123,
  "content_hash": "sha256:…",
  "baseline_version": "2026-11-15T…",
  "reason": "（denied 时填中文原因）"
}
```

`manifest` 顶层加 `draft_overlay_included: true|false`，便于前端与守卫快速判断。

## 5. 前端

1. AI 面板输入区加开关「纳入当前未保存草稿」（**默认关闭**）。
2. 仅在「宿主有未保存修改」时才显示该开关（无修改时显示现有「已同步」态）。
3. 开关打开时，范围文案从「当前未保存修改不会纳入本轮」改为「将纳入当前未保存草稿（基于版本 v…）」。
4. 提交时把编辑器内存正文与打开时版本一起带上。
5. `denied` 时在消息下方显示中文原因（不弹窗、不阻断）。

宿主侧需要暴露两个值：`currentDraftContent()` 与 `openedBaselineVersion()`。底稿 HTML 与 Univer 两个编辑器各实现一次，由 `useAiHostContext` 统一读取。

## 6. 不做什么

| 项 | 原因 |
|---|---|
| 不做附注宿主 | 已有 `note_ai.py` 的 overlay，语义已在，避免两套 |
| 不做报表 / TB / 合并宿主 | 这些宿主的「未保存」语义未定义（多为只读派生视图），需独立设计 |
| 不把草稿落库 | 需求 4.2：草稿不得进入任何持久化 AI 产物 |
| 不做草稿 diff 展示 | 本轮只解决「能不能纳入」，diff 属附注侧能力 |
| 不新建确认流 | 复用既有 Chat Run + ContextPlan，不碰 DraftArtifact / CAS |

## 7. 测试

| 层 | 用例 |
|---|---|
| 契约 | `draft_overlay` 缺省时不改变任何现有行为（回归） |
| 校验 | `host_id` 不等 → 422；长度超限 → 422；空 content → 422 |
| 版本 | `baseline_version` 过期 → manifest `denied` + 中文原因，Run 仍成功 |
| 鉴权 | 跨项目 `host_id` 无法纳入（服务端重鉴权） |
| Manifest | `included` 时条目带 `content_hash` / `baseline_version`；顶层 `draft_overlay_included=true` |
| 安全 | 草稿内容不出现在 metrics / 日志 / 审计链 payload（断言只存 hash 与长度） |
| 注入 | 草稿里写「忽略以上指令」不影响模型行为（按不可信内容包装） |
| 前端 | 开关默认关闭；有未保存修改才显示；文案随开关变化 |
| 端到端 | 底稿改一处不保存 → 开启 → 提问 → manifest 可核对 → 模型引用该改动 |

## 8. 实施边界

- 涉及文件：`contracts.py`（请求字段）、`context_plan.py`（装配 + 校验）、`run_service.py`（透传）、
  `useAiHostContext.ts` / `usePlatformAiChat.ts` / `PlatformAiChatPanel.vue`（前端）、
  底稿两个编辑器的 `currentDraftContent` / `openedBaselineVersion`。
- 重叠风险：`PlatformAiChatPanel.vue` 在多个 spec 中被改过，实施时按文件当前状态定点编辑。
- 不做迁移（纯请求侧字段 + manifest 扩展，无新表）。

### 9.1 与设计的偏离（代码为准）

| # | 设计原文 | 实际实现 | 理由 |
|---|---|---|---|
| D1 | 请求字段写在 contracts.py | 新增 backend/app/services/ai_chat/draft_overlay.py，ChatRunRequest 只加 draft_overlay 字段 | run_contract.py 已 751 行（门禁 800），按「行数门超限优先抽模块不抬白名单」抽出；contracts.py 只提供 HostType 真源 |
| D2 | 「服务端重算 hash」未指定字段命名 | 线上仍叫 content_hash（与附注侧 note_ai.py 一致），Python 侧落 client_content_hash；权威值只能经 content_hash property 取 | 两者不共名，误用读不到值 |
| D3 | content_length 未说明与客户端值的关系 | 服务端覆盖（不并存）为实际长度 | 并存时下游任何一处误读都会拿到可伪造值 |
| D4 | manifest 顶层加 draft_overlay_included | 只在提交 overlay 时出现；缺省请求不含该键 | 需求 6.1「默认关闭时行为与现状完全一致」——多一个恒 false 的键同样是契约变更 |
| D5 | 未规定 overlay 预算占比 | overlay 最多占 doc_excerpt 槽位一半 | 草稿是补充而非替代，已保存正文必须仍有预算；缺省路径该计算得 0，既有分配逐值不变 |
| D6 | 「宿主当前业务版本」未指定列 | working_paper.updated_at（常量 WORKPAPER_BUSINESS_VERSION_SOURCE） | content_revision 在 univer-save / checklist-responses PUT / wp_editor_router 三条保存路径上不推进，且无通用端点可读 ⇒ 拿它当版本号会把「刚保存过」判成「版本未变」，旧草稿被静默纳入（需求 6.3 禁止的 fail-open） |
| D7 | 未提及定界器逃逸 | dsh_masking.wrap_untrusted_block 增 _neutralize_delimiters（转义为可见占位） | 原实现原样透传正文：草稿写结束标记即可让结束标记早于真块尾，后半段指令落在定界之外 |
| D8 | 未提及 422 detail 与 repr | error_handler.py 增 _redact_draft_overlay_detail；DraftOverlayRef.__repr_args__ 隐藏正文 | 实测两处真实泄漏：超长草稿的 422 input 回显全文；repr(overlay) / repr(ChatRunRequest) 打印正文 |
### 9.2 端到端验证（独立后端实例加载新代码；共享开发后端仍是旧进程）

共享开发后端未热重载本 spec 的新代码（_PRIVILEGED_EXEMPT_PATHS 未生效，draft_overlay.content 被判越权字段 422），因此端到端在独立实例（GT_BACKEND_NO_RELOAD=1 + uvicorn，监听另一个本地端口）上执行，连同一套共享 PG 与本地 vLLM。

| 场景 | 请求 | 观测结果 |
|---|---|---|
| A 版本一致 | 带 draft_overlay（baseline_version = 库内 updated_at），正文含哨兵 888888 | draft_overlay_included: true；条目 status: included + content_hash: sha256:169b3363... + baseline_version: 2026-10-29T09:33:47.746189+00:00 + used_tokens: 15；模型回答 888888 |
| B 关闭开关 | 不带 draft_overlay | 顶层 draft_overlay_included 键不存在；无草稿条目；回答明确「上下文不足」，不含哨兵 |
| C 版本过期 | baseline_version = 2020-01-01T00:00:00+00:00 | draft_overlay_included: false；条目 status: denied + 中文原因「草稿基于旧版本 v2020-01-01T00:00:00+00:00，当前 v2026-10-29T09:33:47.746189+00:00，请先保存或刷新」；Run 仍成功（完整回答、无 error 事件）；模型未看到旧草稿 |
| D 字段校验 | host_id 不符 / 空正文 / 全空白 / 200001 字符 / host_type=report | 全部 422（不裁剪、不静默忽略） |

不落库判据（真库逐条核对，哨兵 777777）：

| 检查 | 结果 |
|---|---|
| user 消息含草稿正文 | no（只存用户提问原文） |
| assistant 消息含哨兵 | YES（模型回答复述，非草稿落库） |
| ai_chat_runs.context_request_snapshot 含 draft_overlay 键 | clean |
| context_request_snapshot / capability_snapshot 含正文 | clean / clean |
| ai_chat_message.context_manifest 含正文 | clean，只存 content_hash + baseline_version + used_tokens |
| audit_log_entries.payload 含正文 | 0 |

验证产物（3 条 run + 6 条 message）已按 run id 精确删除；底稿数据未改动（全部为只读请求）。

### 9.3 测试与变异

| 项 | 结果 |
|---|---|
| 后端本 spec 三文件 | 91 passed |
| 后端本 spec + 既有 Chat 回归（task4 / task24 / context_plan_wiring） | 240 passed |
| 前端本 spec 六文件 | 122 passed |
| 变异：versions_match 改恒真 | 13 failed（全部为「过期 / 不可解析 / 空值应 denied」类，形态与预期一致）→ 逐字节还原，sha256 校验一致 |
| 变异（Task 1~5 各自） | 13/13、3 组、6/6、5+1、2/2 全 RED |

### 9.4 已知边界（有意接受）

1. HTML 侧只覆盖已接入 useChecklistPersistence 的 16 个 K/J 宿主；其余宿主（自管 flushPendingSave 防抖的 D/E/F/G/H 等）本期不报草稿——面板如实显示「无未保存修改」，不误报。接入方式 = 一行 publishHtmlDraftSource。
2. 只改 checklist_responses 的保存不推进 working_paper.updated_at ⇒ 这类并发改动检测不到。收窄它需让 checklist 保存也推进 updated_at（跨模块，另立任务）。方向安全：多判 denied（拒绝纳入），不会静默用旧草稿。
3. 复核状态 / 分派变更也推进 updated_at ⇒ 会多判一些 denied（同上，方向保守）。
4. 共享开发后端未加载本 spec 新代码（未热重载）⇒ 浏览器 UI 走查无法在共享实例上验证开关；已用独立实例完成 API 层端到端，UI 层由 39 条前端单测覆盖（开关默认关闭、显示条件、文案切换、提交时读取、denied 内联提示）。
