# 外部 LLM 提供商运行时闭环 — Tasks

- [x] 1. 审计现有 LLM 全链路并核对 live PG
  - 抓到明文 Key、越权/SSRF、provider 激活恒失败及 active row 未进入真实调用链。

- [x] 2. 重写 V192/R192 与 ORM
  - Fernet ciphertext + Key 更新时间；provider enum 与 partial unique indexes 已入 PG。

- [x] 3. 建立单一 provider registry
  - 默认 endpoint/header/类型/host policy/UI 元数据同源。

- [x] 4. 建立密钥服务与 endpoint policy
  - 保留/替换/清除三态、缺 ENCRYPTION_KEY fail-closed、URL+DNS/IP 双层校验。

- [x] 5. 建立统一 runtime resolver/transport
  - DB active > env fallback；chat sync/stream、embedding、validate/test 同实现。

- [x] 6. 改造 AIService 与 llm_client
  - 移除进程级 URL/Key/model 权威状态；多 worker/重启均重新读 DB。

- [x] 7. 接通 AI Chat NativeEngine
  - 经 AIServiceModelClient 使用同一 runtime；熔断/并发改用公开接缝。

- [x] 8. 收口模型管理 API
  - 全端点 admin、DTO 禁 is_active、Key write-only、原子 activate、目的地变更强制重输 Key。

- [x] 9. 完成前端管理闭环
  - 动态 provider、Key 状态/清除、测试、health、admin 路由与菜单。

- [x] 10. 修订 `.env.example` 与配置文档
  - ENCRYPTION_KEY、allowlist、支持矩阵、企业样例、当前官方 URL 与限制已写清。

- [x] 11. 后端针对性验证
  - 155 passed：密文、权限、SSRF、active DB runtime、NativeEngine、OCR fields、企业契约。

- [x] 12. 前端针对性验证
  - Vitest 4 passed；目标 ESLint 0 issue；diagnostics 0。
  - 单区域 tsc 本次文件 0 error；另有 15 条未改文件预存错误，未谎报全量通过。

- [x] 13. PG 与浏览器真实验收
  - V192/V193 MigrationRunner failed=[]，列/enum/index/schema_version 与 checksum 实查通过。
  - Playwright 完成 qwen/OCR 表单、真实 CRUD、test→activate→llm_client mock HTTP；已恢复原 active 并清除测试数据。

- [x] 14. 收尾复核
  - 一次性脚本/进程/测试行全部清理；并发会话文件未暂存、未提交、未覆盖。

- [x] 15. 接收并裁决企业模型样例
  - `qwen3.8` / 256K / reasoning_effort=low；PaddleOCR 两种 capability。

- [x] 16. 实施 V193 企业运行参数与 OCR 双 capability
  - reasoning_effort、protocol/path/auth/timeout 字段；ocr/layout_parsing 可同时 active。

- [x] 17. 实施远程 PaddleX adapter
  - 官方 Base64 JSON/fileType/响应归一；合成图 test；远程失败不再空文本假成功。

- [x] 18. 企业端点验收
  - MockTransport 逐值验证 10010 chat 与 10080 `/ocr`/`/layout-parsing` URL/header/payload/schema。
  - DNS=`198.18.0.224`，TCP 10010/10080 可达；需精确 allowlist。真实 Key未提供，未向企业端点发送 HTTP、Key 或项目数据。

- [x] 19. 增加 V194 企业预设迁移
  - 三条固定 preset_key/UUID 配置，全部 inactive、Key NULL；安全回滚保留已使用模型。

- [x] 20. 锁定预设参数与可信端点
  - 后端只允许录入/清除 Key且禁止删除；10010/v1 与 10080 精确内建信任。

- [x] 21. 完成预设前端 UX
  - “企业预设”“录入 Key”标签；Qwen/OCR 其他字段 disabled/readonly。

- [x] 22. 预设真库与浏览器验收
  - PG 3/3 无 Key inactive、V194 drift 0；后端 157 passed、前端 4 passed、ESLint/diagnostics 0；Playwright 三条展示及只读性通过。
- [x] 23. 修复 Key 保存导致页面崩溃
  - 根因：服务端 `ENCRYPTION_KEY` 为空 ⇒ PUT 503，axios 对 5xx 自动重试 3 次且无 catch ⇒ ErrorBoundary。已在 gitignored `.env` 生成稳定密钥（未打印），`aiModelApi.ts` 全部 `_silent`，页面五个动作 `handleApiError`；`/providers` 增加 `credential_encryption_ready`。
- [x] 24. 激活失败诊断与平台修复（ADR-LLM-011/012）
  - 现场为本机代理 fake-IP + 公网 DNS NXDOMAIN（见 design §10），非 Key 问题；内网 DNS 下真实连通性本机未验证。
  - 探针兼容推理模型；失败返回具体原因与 fake-IP 提示；`test_llm_validation_diagnostics.py` 11 例，4 条磁盘变异（探针回 max_tokens=1 / 激活回笼统文案 / 去 fake-IP 提示 / OCR 回 engine_unavailable）均以预期形态打红。
- [x] 25. 思考强度改为用户选择（ADR-LLM-013）
  - V195/R195 + 预设白名单 + 前端「未指定/低/中/高」；PG 实查 gt_qwen38 `reasoning_effort=NULL`、Key 保留；边界测试 3 条变异（白名单回旧值 / 预设全解锁 / OCR 预设放行思考强度）均打红。
- [x] 26. 清理 9980 上的旧后端实例
  - uvicorn --reload 的 spawn worker 在 supervisor 被无 `/T` 的 taskkill 杀掉后成孤儿，继续用旧 `.env`（无 ENCRYPTION_KEY）共享端口；`start-dev.bat :kill_port` 改按 netstat + `spawn_main(parent_pid=…)` 清理，守卫 `test_start_dev_kill_port_orphan_guard.py` 变异打红。
- [x] 27. 浏览器验收：预设录 Key + 选择思考强度 → 测试 → 激活，失败提示完整可读
  - Playwright（127.0.0.1:3030，admin）：qwen3.8 预设对话框思考强度可选「未指定/低/中/高」，模型名/上下文/备注 disabled；保存只发 `{"clear_api_key":false,"reasoning_effort":…}`（不带 Key），重开对话框回显 中（medium）/ 未指定，PG 逐次一致；测试连接与激活失败均以 15s 通知显示「模型端点不可达：TLS 握手被中断……fake-IP 198.18.0.224……」，无 ErrorBoundary、模型保持未激活、本地 active 不变；OCR 预设测试显示「远程 OCR 尚未配置 API Key」，对话框无思考强度。
  - 收尾状态：gt_qwen38 `reasoning_effort=NULL`、用户 Key 未变（`api_key_updated_at` 不变）、未激活。企业端点真实连通性需在内网 DNS 下复测（本机代理环境未验证）。
- [x] 28. 思考强度取值按企业网关实测收敛（ADR-LLM-014）
  - V196/R196 入 PG（CHECK 含 xhigh）；预设 options/server_default 元数据 + 后端 422 + 前端只列 未指定（服务端默认 xhigh）/低/中/极高；边界测试含 high 被拒，关闭校验的变异打红在 `assert 200 == 422`；浏览器实查选项与帮助文案。
  - 现场证据：内网地址直连时 Key / 模型名 / low 均通过，`high` 400；本机代理 DNS 仍是唯一阻断，修复需改 hosts / 代理配置 / 关闭 TUN 三选一（待用户决定）。
- [x] 29. 实现 fake-IP 兼容解析（ADR-LLM-015）：触发条件、地址来源优先级、校验、缓存与诊断结果
  - 新模块 `endpoint_dns_compat.py` + `llm_endpoint_policy.resolve_endpoint/SafeEndpoint`；`assert_endpoint_safe` 保留为兼容包装；四个可选配置（`LLM_FAKE_IP_COMPAT` 等）写入 config 与 `.env.example`。本机自动发现得到上游 DNS 两台、本机代理 127.0.0.1:7897。
- [x] 30. 钉选地址传输接入 LLM runtime 与远程 OCR（SNI/证书仍按域名）
  - `PinnedAddressTransport` 只改 `connect_tcp` 目标；`build_runtime_client` 与 `recognize_remote_bytes` 均传 `transport=safe.transport()`，系统 DNS 正常时为 None。
- [x] 31. 远程 OCR 连接测试图与 422 文案（ADR-LLM-016）
  - 459 字节 240x64 文字 PNG；钉选内网地址后两条企业 OCR 均 200 且识别出 `GT OCR 2026`。
- [x] 32. 兼容层测试与变异证明
  - `test_endpoint_dns_compat.py` 23 例（回环假 CONNECT 代理兼 DNS、模拟 strict-route、录制型网络后端核对 SNI/Host）；11 条磁盘变异全部以预期形态打红；相关 13 个测试文件 233 passed。
- [x] 33. Mesl 开启下真实验收：qwen3.8 测试/激活 + 两条 OCR 测试
  - 未改 hosts / 代理配置：运行中后端 `/test` 三条全部通过；用户本人在页面点激活 qwen3.8 成功（对话模型卡 healthy）；平台公共入口真实对话返回正文；两条 OCR 浏览器测试 status ok，按用户要求只测试未激活。外网无 VPN 不可达（企业 AI 不对公网开放），错误文案会如实提示。
