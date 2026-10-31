# 任务：10 月 21 日 AI 采纳与笔记恢复

> 范围固定为 `ai-chat-adopt-and-note-target-picker` R1 / R3 的丢失接线。所有恢复在隔离 detached worktree 中完成，禁止以整树 checkout 覆盖当前 origin。

- [x] 1. 建立事故证据与丢失清册
  - 以 `dae1129f5`、`112bfabec`、`434e87972` 三方比对，区分 82 个完整丢失文件、134 个已分叉文件和 24 个尚未入库的未跟踪文件。
  - 逐项写明 spec 归属与恢复 / rebase / owner 裁决 / 不取旧版 / 保持当前建议；表格校验 82 + 24 条完整。
  - _需求：R6_

- [x] 2. 编写恢复设计与登记索引
  - 记录强制 checkout 的时间线、最小恢复闭环、文件级三方合并边界、授权不变量、验证和清理计划。
  - 在 `INDEX.md` 登记进行中的恢复 spec；长期规则与开发历史的事故教训在提交前按目标树重放。
  - _需求：R4、R6_

- [x] 3. 恢复前端选择目标与笔记保存接线
  - 恢复 `PlatformAiChatPanel`、`useAiHostContext`、`useAiNoteCapture` 和既有测试；三方合并 `usePlatformAiChat`、`useDocAiChat`。
  - 只保留当前 `auditPlatformApi.getDisclosureNoteTree(..., config?)`、`AiContentPendingBanner` 和 typed `eventBus` 行为。
  - 已恢复 9 个完整丢失文件中的前端部分；`usePlatformAiChat` 将成功事件收敛为一次且使用目标项目 ID，面板不再重复发送无 payload 事件。诊断无错误，运行时验证见任务 5。
  - _需求：R1、R3、R4_

- [x] 4. 恢复后端跨宿主与位置授权接线
  - 恢复 `access.py`、`adopt.py`、`note_service.py` 和既有 fail-closed 测试；三方合并 `doc_ai_chat.py`。
  - 保留当前 SSE `get_db(scope="function")`，验证目标 adopt / 来源 history 的授权分流和所有拒绝零副作用。
  - 已恢复 9 个完整丢失文件中的后端部分，并把 router 的 `source_host`、笔记位置字段和授权分流合入当前 SSE 版本；静态诊断无错误，行为验证见任务 5。
  - _需求：R2、R3、R4_

- [x] 5. 验证、故障注入与浏览器验收
  - 跑前端跨语言契约、后端 HTTP / PG 契约、相关回归、区域 typecheck 和静态守卫；对 HEAD 逐用例比对新增失败。
  - 在隔离树完成四类针对性变异；用【测试】项目浏览器验证五条路径并清理新增数据。
  - 已完成非浏览器验证：前端 95 例由 HEAD 的 8 red → 候选 0 red；HTTP 契约由 18 passed / 6 failed → 24 passed；PG 语义由 23 passed / 19 failed → 42 passed（显式 PG 环境，0 skipped）；5 个变异全按预期打红并逐字节恢复；静态守卫 HEAD / 候选均 68 passed。区域 typecheck 在 ES2023 下只剩 HEAD 同有的 `apiProxy.ts` 两个类型债。
  - 浏览器验收五条路径全部通过（隔离上下文 + 候选前端 3031 + 镜像后端 9980，详见 design.md §7）；两页 console error 为 0。
  - 写入数据已按平台路径清理并逐表核对回基线（详见 design.md §8）。
  - _需求：R5_

- [ ] 6. 单一提交和安全收尾
  - 将通过验证的恢复代码、spec、INDEX 与长期教训作为一个提交；用 `push_version.py` 打版本并原子推送当前目标分支。
  - 主工作区只对齐已验证的后端和文档，前端不直接镜像；解锁并删除临时 worktree，执行 `git worktree prune`。
  - _需求：R4、R5、R6_
