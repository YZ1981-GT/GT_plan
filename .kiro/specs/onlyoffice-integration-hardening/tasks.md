# 任务清单：OnlyOffice 集成优化（onlyoffice-integration-hardening）

## Sprint 1：P0 后端核心修复（5 任务）

- [x] 1.1 新增 `_load_wp_or_404` 统一 helper：查底稿+wp_code+项目软删守卫（`SELECT is_deleted FROM projects`），三端点（config/wopi/callback）统一替换现有查询块 — _Requirements: R7_
- [x] 1.2 单文件共享重构 `_resolve_wp_file`：按 `{wp_code}.xlsx` 命名单一文件（去掉 per-sheet `_{sheet_name}` 后缀），首次从模板整本复制一次，后续复用；删除原 `_resolve_sheet_file` — _Requirements: R4_
- [x] 1.3 修复 `_generate_doc_key`：改为 `hash(wp_code + file_mtime_ns)`，同 wp_code 所有 sheet 共享同一 doc_key；更新 config 端点中的调用签名 — _Requirements: R5_
- [x] 1.4 席位接入 config 端点：编辑模式（mode=edit）时调 `acquire_session(user_id, doc_key)`，返回 False → 429；只读不占席位 — _Requirements: R1, R2_
- [x] 1.5 席位释放 callback 端点：status=2/6 写回成功后 + status=3/4/7 关闭时调 `release_session`；从 body `actions[].userid`/`users[0]` 提取 user_id，从 `key` 提取 doc_key；缺失时跳过依赖 TTL 兜底 — _Requirements: R3_

## Sprint 2：后端补强（4 任务）

- [x] 2.1 WOPI JWT 鉴权：`get_sheet_wopi_contents` 新增 `_verify_wopi_jwt(request)` 校验 Authorization header 或 `?token=` 查询参数；无 secret 测试环境直通；失败返回 403 — _Requirements: R6_
- [x] 2.2 新增 `GET /api/workpapers/onlyoffice/health` 端点：复用 `OnlyOfficeCallbackService.health_check()` + `get_active_count()`，返回 `{healthy, active_sessions, max_sessions}`；路由注册在 `/{wp_id}` 通配之前 — _Requirements: R9_
- [x] 2.3 config 端点构建 `editorConfig.actionLink`：携带 `{"action":{"type":"bookmark","data":sheet_name}}` 定位目标 sheet — _Requirements: R4_
- [x] 2.4 `MAX_SESSIONS` 配置化：从 `settings.ONLYOFFICE_MAX_SESSIONS` 读取（环境变量，默认 10），`onlyoffice_session_limiter.py` 改引 settings 而非 getattr 硬编码 — _Requirements: R2, R15_

## Sprint 3：前端改动（4 任务）

- [x] 3.1 `GtOnlyOfficeSheet.vue` 注册 `events.onError/onWarning/onDocumentReady`：onError → `emit('fallback')` 降级；onDocumentReady → 关闭 loading（不再 new 之后立即关）；onWarning → console.warn 记录 — _Requirements: R8_
- [x] 3.2 `GtOnlyOfficeSheet.vue` 主动健康预检：mounted 时先 `GET /api/workpapers/onlyoffice/health`，不健康直接降级不加载 api.js — _Requirements: R9_
- [x] 3.3 只读模式 `type:"embedded"`：readonly 或 mode=view 时设 `editorConfig.type='embedded'`；编辑模式保持 `desktop` 保留公式/数据 Tab — _Requirements: R10_
- [x] 3.4 底稿列表页 preload：mounted 时 `<link rel="preload" as="script">` 预热 api.js（仅 preload 不初始化 DocsAPI） — _Requirements: R11_


## Sprint 4：OnlyOffice 插件骨架（3 任务，可选增强）

- [x]* 4.1 创建 `backend/onlyoffice_plugins/audit-legend/` 目录：`config.json`（guid/name/EditorsSupport:["cell"]/variations）+ `index.html` + `scripts/code.js`（window.Asc.plugin.init 骨架，叠加 √/ⓒ/➜ 审计符号）+ `resources/icons/` — _Requirements: R12_
- [x]* 4.2 创建 `backend/onlyoffice_plugins/tb-fetch/` 目录：`config.json`（onContextMenuClick 事件）+ `scripts/code.js`（选中单元格 → fetch auto_data_resolvers API → 回填值，复用平台鉴权不硬编码密钥） — _Requirements: R13_
- [x]* 4.3 docker-compose.yml 挂载插件：添加 volume 映射 `./backend/onlyoffice_plugins/{plugin}:/var/www/onlyoffice/documentserver/sdkjs-plugins/{plugin}:ro`；确认 `JWT_SECRET=onlyoffice-dev-2026` 三处一致 — _Requirements: R14, R15_

## Sprint 5：测试与验证（5 任务）

- [x] 5.1 后端 pytest — 席位生命周期：测试 acquire→release 流程、满额 429、幂等续期、status=3/4/7 释放、缺 user_id 跳过；mock Redis — _Requirements: R1, R2, R3_
- [x] 5.2 后端 pytest — WOPI 鉴权 + 软删守卫：无 JWT → 403；有效 JWT → 200 返回文件；底稿软删 → 404；项目软删 → 404 — _Requirements: R6, R7_
- [x] 5.3 后端 pytest — 单文件 + doc_key：同 wp_code 不同 sheet 返回相同 doc_key；文件首次复制后存在；mtime 变化 → key 变 — _Requirements: R4, R5_
- [x] 5.4 PBT（property-based testing）— 席位守恒性质：∀ 随机 acquire/release 序列，活跃席位 = acquire成功数 - release数；活跃数恒 ≤ MAX_SESSIONS — _Requirements: R1, R2, R3_
- [x] 5.5 render-config 冒烟 + Playwright 端到端：1101+ 冒烟零回归；Playwright 实测 D0 底稿非白名单 tab OnlyOffice iframe 可见 + 编辑 + 降级（容器 down 时自动 GtGridSheet） — _Requirements: R16_

## 验收门槛

- V1: 席位限制器接入生效：编辑模式占席位，满额返回 429 + 前端降级只读
- V2: callback status=2/3/4/6/7 均正确释放席位（无僵尸会话）
- V3: 同 wp_code 多 sheet 共享单一 `{wp_code}.xlsx`，不再 per-sheet 整本复制
- V4: WOPI contents 端点有效 JWT 校验（无 JWT → 403）
- V5: 三端点均有项目软删守卫（已删项目 → 404）
- V6: 前端 DocEditor onError 触发时自动降级到 GtGridSheet（用户不见 OO 报错页）
- V7: 1101+ render-config 冒烟测试零回归 + Playwright D0 实测通过
- V8: 交付模块 OnlyOffice 功能不受影响（共享容器零回归）
