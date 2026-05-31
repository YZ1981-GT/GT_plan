# 实施计划：vLLM / httpx 链路 3 bug 修复

## 概述

3 个精确定位的 bug，逐个修复 + 测试。约 1 天。

## 任务

- [ ] 1. Bug 1 — httpx 系统代理绕过
  - [ ] 1.1 修复 `llm_client.py` 中所有 httpx client 创建
    - 加 `mounts={}, trust_env=False`
    - _Bugfix: Bug 1_
  - [ ] 1.2 修复 `ai_service.py` 中 3 处 client 创建
    - `_get_ollama_client` / `_get_llm_client` / `_get_chromadb_client`
    - _Bugfix: Bug 1_
  - [ ] 1.3 修复 `availability_fallback_service.py` 中 `check_llm_available`
    - _Bugfix: Bug 1_
  - [ ] 1.4 修复 `routers/system_settings.py` 中 `check_url`
    - _Bugfix: Bug 1_
  - [ ] 1.5 触类旁通 grep 全仓确认无遗漏
    - `grep -rn "httpx.AsyncClient\(\|httpx.Client\(" backend/app/ --include="*.py"` 排除测试
    - 每处确认含 `trust_env=False`
    - _Bugfix: Bug 1; Property 1_
  - [ ]* 1.6 编写单元测试
    - mock httpx.AsyncClient 构造函数，断言 trust_env=False + mounts={} 被传入
    - _Property 1_

- [ ] 2. Bug 2 — chat_template_kwargs 提升到顶层
  - [ ] 2.1 修改 `llm_client.py` payload 构建
    - `chat_template_kwargs` 从 `extra_body` 内移到顶层 dict
    - 删除空的 `extra_body`（如无其他字段）
    - _Bugfix: Bug 2_
  - [ ]* 2.2 编写单元测试
    - mock httpx.post，捕获 payload，断言 `chat_template_kwargs` 在顶层且值正确
    - _Property 2_

- [ ] 3. Bug 3 — finish_reason=length 处理
  - [ ] 3.1 修改 `llm_client.py` 的 `_sync_completion` 返回值处理
    - `finish_reason=length` + `content=None` → 返回中文提示字符串
    - `content=None`（其他原因）→ 返回通用提示
    - 禁止 fallback 到 `reasoning` 字段
    - _Bugfix: Bug 3_
  - [ ]* 3.2 编写单元测试
    - 构造 finish_reason=length + content=None → 断言返回中文提示（非 None）
    - 构造正常响应 → 断言返回 content 原值
    - 构造 content=None + reasoning 有值 → 断言不返回 reasoning
    - _Property 3_

- [ ] 4. Checkpoint — 单测全绿
  - `python -m pytest backend/tests/ -v --tb=short -k "llm or ai_service"`
  - 确认 0 fail / 0 error

- [ ] 5. 集成验证（需 vLLM 服务可用）
  - [ ] 5.1 启动 vLLM（端口 8100）
  - [ ] 5.2 设置 `WP_AI_SERVICE_ENABLED=True`
  - [ ] 5.3 调用 `/ai/suggest` 端点，断言返回非 stub 内容
  - [ ] 5.4 调用 `/ai/analytical-review` 端点，断言返回非 stub 内容
  - [ ] 5.5 验证系统代理开启时仍能正常调用（Bug 1 验证）

- [ ] 6. Final Checkpoint
  - pytest 全量 0 回归
  - 3 个 bug 的修复点 grep 确认到位
  - WP_AI_SERVICE_ENABLED=False 时仍返回 stub（门控不受影响）

## 说明

- 标 `*` 为可选（单元测试），核心修复任务必需
- Bug 1 的触类旁通 grep（1.5）是必需的——发现一处反模式 grep 全仓找同类
- 集成验证（Task 5）依赖 vLLM 服务可用（端口 8100），不可用时标 skip
- 修复后 6 个 stub 对话框自动切换到真实 LLM（由门控变量控制，无需额外代码）
