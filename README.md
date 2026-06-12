# 致同审计作业平台（GT_plan）

基于 FastAPI + Vue 3 的现代化审计作业平台，面向会计师事务所全场景审计作业，支持多审计类型、多会计准则适配、AI 辅助审计、底稿/报表/合并/附注全链路联动、电子签名与质控复核等能力。

## 项目概述

本平台将传统审计工作流程数字化、智能化，覆盖「承接与计划 → 控制测试 → 实质性程序 → 完成与报告」全周期，以审定数为单一数据源，打通调整分录 → 审定试算表 → 财务报表 → 附注 → 出品物（审计报告）的双向数据流。

### 平台现状（codegraph 实测）

CodeGraph 索引统计：**3725 个文件 / 68280 个符号节点 / 140625 条关系边**。

| 维度 | 规模 |
|------|------|
| 后端路由文件（routers） | 300+ 个 |
| 后端服务文件（services） | 500+ 个 |
| 数据模型文件（models） | 73 个 |
| 后端测试文件 | 860+ 个 `test_*.py` |
| 前端 Vue 组件/视图 | 610 个 |
| 数据库迁移（V*.sql） | V001–V069（69 个版本 + R*.sql 回滚配对） |

> 数据来源：`codegraph status` 与仓库实际文件计数（2026-06-11）。

### 核心功能

- **多准则适配**：企业会计准则、小企业准则、政府会计准则、IFRS；准则解析（`resolve_applicable_standard`）按项目类型动态匹配报表配置
- **审计类型扩展**：年度审计、专项审计、IPO 审计、内控审计、验资、税审
- **账表数据智能导入**：试算表/余额表/序时账/明细账智能导入 v2（多企业表头适配 + 符号约定统一 + 借贷方向推导 + 导入诊断）
- **四表联查与穿透**：余额表 ↔ 序时账 ↔ 明细账 ↔ 凭证逐层穿透，金额反查
- **底稿管理**：致同 2025 修订版底稿模板库（按 A–S 循环分目录）、元数据批量生成、公式引擎预填、`=ADJ()`/`=TB()` 等自定义公式绑定、xlsx 导入导出
- **报表与附注**：四张报表生成（未审/审定）、报表公式、附注（disclosure notes）模板填充、多表格按表导出开关、Word/Excel 导出
- **合并报表**：合并范围、抵销分录、少数股东权益、合并工作底稿、合并附注
- **出品物溯源与回填**：审计报告正文模板（致同 17 套意见×企业类型）占位符替换、出品物章节级溯源、stale 感知刷新、文字回填（金额严禁倒灌）
- **AI 辅助审计**：文档级/文件夹级 LLM 对话（RAG 上下文注入）、底稿 AI 结论 copilot、OCR 识别（PaddleOCR/Tesseract/MinerU）、知识库上下文感知
- **协作与质控**：6 角色权限、复核对话、过程记录、工时打卡、EQCR 质控、单元格级复核批注、编辑锁
- **电子签名**：三级电子签名（用户名+密码 / 手写签名 / CA 证书）
- **数据可视化**：集成 Metabase 项目级看板
- **在线编辑**：Univer 纯前端表格编辑器（底稿）+ OnlyOffice（Word 报告正文/附注，JS API 集成）

## 技术栈

### 后端
- **框架**：FastAPI 0.135.x
- **数据库**：PostgreSQL 16（pgvector 扩展用于 RAG 向量检索）
- **缓存**：Redis 7
- **ORM**：SQLAlchemy（async）
- **迁移**：D6 版本化 SQL 脚本（`V*.sql` + `R*.sql` 回滚配对，启动时由 `MigrationRunner` 自动应用 + `schema_drift_detector` 漂移自检），当前最高 **V069**
- **AI/OCR**：PaddleOCR、Tesseract、MinerU（可选，需 GPU）、MarkItDown（本地文档转 markdown）
- **LLM**：本地 vLLM（OpenAI 兼容接口）+ 熔断器；RAG 走 pgvector，未起 embed 实例时降级 ilike
- **底稿模板**：致同 2025 修订版模板文件（xlsx/xlsm/docx），存于 `backend/wp_templates/`（按 A–S 循环分目录）
- **报告模板**：审计报告正文/财务报表/附注 Word/Excel 模板，存于 `backend/data/audit_report_templates/`
- **可观测性**：OpenTelemetry + Prometheus
- **测试**：pytest + Hypothesis（属性测试，`max_examples=5`）

### 前端
- **框架**：Vue 3 + TypeScript + Vite 6
- **UI 库**：Element Plus（GT 紫令牌主题 `styles/gt-tokens.css`）
- **状态管理**：Pinia
- **路由**：Vue Router
- **图表**：ECharts / vue-echarts / D3
- **表格编辑**：Univer（preset-sheets-core/advanced/drawing）
- **文档预览**：vue-office（docx/excel/pdf）、mammoth
- **富文本**：TipTap
- **测试**：Vitest（单测）+ Playwright（E2E）+ fast-check（属性测试）

### 基础设施
- **容器化**：Docker + Docker Compose
- **GPU 支持**：NVIDIA Docker（MinerU）
- **存储**：本地磁盘 + 云端存储（SFTP/S3/MinIO/阿里云 OSS）
- **附件管理**：Paperless-ngx

## 快速开始

### 本地开发（推荐）

Windows 一键启动后端（:9980）+ 前端（:3030）：

```bat
start-dev.bat
```

打包为可执行程序：

```bash
python build_exe.py
```

### 手动启动

**后端**（仓库根有 `.venv`）：

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 9980 --reload --reload-dir app
```

**前端**：

```bash
cd audit-platform/frontend
npm install
npm run dev
```

> 前端唯一路径是 `audit-platform/frontend/`（仓库根无 `frontend/`）。

### 访问地址

| 服务 | 地址 |
|------|------|
| 后端 API | http://localhost:9980 |
| API 文档 | http://localhost:9980/docs |
| 前端开发服务器 | http://localhost:3030 |
| Metabase 看板 | http://localhost:3000 |
| Paperless-ngx | http://localhost:8010 |
| vLLM（LLM 推理） | http://localhost:8100 |

测试账号：`admin / admin123`。

### Docker 服务

```bash
docker-compose up -d
```

常驻容器：`audit-postgres`(5432) / `audit-redis`(6379) / `audit-metabase`(3000) / `audit-pgbouncer`(6432，`DB_USE_PGBOUNCER=True` 时启用)；健康检查 `/api/health`。

### 可选：MinerU（需要 GPU）

```bash
bash scripts/build-mineru.sh    # Linux/Mac
scripts\build-mineru.bat        # Windows
docker-compose -f docker-compose.mineru.yml up -d
# 在 .env 中启用：MINERU_ENABLED=true
```

## 项目结构

```
GT_plan/
├── backend/                      # FastAPI 后端
│   ├── app/
│   │   ├── models/               # 数据模型（73 个，含 phase10~16 分期模型）
│   │   ├── services/             # 业务服务（500+，按领域分）
│   │   ├── routers/              # API 路由（300+）
│   │   ├── router_registry/      # 路由分组注册（新 router 必在此注册）
│   │   ├── middleware/           # 中间件（审计日志/限流/可观测/响应封装）
│   │   └── core/                 # 核心（migration_runner / schema_drift_detector / security 等）
│   ├── migrations/               # V*.sql + R*.sql 回滚（D6 版本化，V001–V069）
│   ├── wp_templates/             # 致同底稿模板库（A–S 循环分目录）
│   ├── data/                     # seed/模板/字体/映射 JSON（含 audit_report_templates/）
│   ├── scripts/                  # 工具脚本（check/seed/gen/analyze/ops/fix/migrate/e2e）
│   └── tests/                    # 测试（860+ test_*.py）
├── audit-platform/frontend/      # Vue 3 前端（唯一前端路径）
│   └── src/                      # views / components / composables（610 个 .vue）
├── storage/                      # 项目级 + 用户私人库存储
├── .kiro/
│   ├── specs/                    # Spec 三件套（active + _archive，详见 INDEX.md）
│   └── steering/                 # 项目记忆与规范（memory/architecture/conventions/dev-history）
├── docs/                         # 项目文档与提案
├── docker-compose.yml            # 主服务编排
├── docker-compose.mineru.yml     # MinerU 服务编排
├── start-dev.bat                 # 本地一键启动
└── build_exe.py                  # PyInstaller 打包
```

## 数据库迁移

项目使用 D6 版本化 SQL 脚本作为唯一迁移系统（非 alembic）。后端启动时 `MigrationRunner` 自动检测并应用未执行的 `V*.sql`。

铁律：
- 新增列写 `V0XX__*.sql` + 配对 `R0XX__*.sql`，`CREATE/ALTER` 必加 `IF NOT EXISTS`
- 按 version 数字去重（撞号字母序靠后者会静默丢失）
- ORM 用 `TimestampMixin` 的表，DDL 必须显式写 `created_at`/`updated_at` 列

**迁移号分配流程**（实施第一步才取号，避免 spec 快照撞号）：
1. `ls backend/migrations/V*.sql | sort -V | tail -1` 看当前最高版本（如 `V071`）
2. 下一对迁移用 **最高+1**（如 `V072__feature.sql` + `R072__rollback_feature.sql`）
3. 本地先跑 `python -m app.core.migration_runner` 验证通过，再提交 DDL+ORM+契约测试三层一致
4. 禁止在 requirements/design 阶段预占具体 V 号；tasks.md 可写「实施时分配」

手动执行（仅诊断用）：

```bash
cd backend
python -m app.core.migration_runner
```

## 配置说明

主要环境变量见 `.env.example`：

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接（DB 名 `audit_platform`） |
| `REDIS_URL` | Redis 连接 |
| `JWT_SECRET_KEY` | JWT 签名密钥（必填） |
| `CORS_ORIGINS` | 允许的前端源（前端 3030 必须在内） |
| `ATTACHMENT_PRIMARY_STORAGE` | 附件主存储（paperless/local） |
| `MINERU_ENABLED` | 是否启用 MinerU（需 GPU） |
| `CLOUD_STORAGE_TYPE` | 云端存储类型（sftp/s3/smb/local） |
| `ENCRYPTION_KEY` | 数据加密密钥 |
| `ONLYOFFICE_URL` | OnlyOffice 服务地址（Word 报告正文/附注在线编辑；有 URL 即启用） |
| `ONLYOFFICE_JWT_SECRET` | 生产环境启用 callback 签名校验 |

JWT 有效期（开发环境）：access_token 1440 分钟（24h）/ refresh_token 30 天。

### OCR 引擎

系统支持三种 OCR 引擎，自动选择与故障回退，无需手动配置：

1. **PaddleOCR**：高精度中文识别（发票/合同/回函）
2. **Tesseract**：多语言、速度快（通用文档）
3. **MinerU**（可选）：复杂文档/表格/公式识别

### 文档转换链

知识库上传文本提取采用三级降级：**MarkItDown 主**（17 种办公格式，纯本地）→ **MinerU OCR**（PDF 扫描件）→ **PyPDF2/python-docx 兜底**。

## 大文件导入说明

项目年度账表数据（`tb_balance`/`tb_ledger`/`tb_aux_balance`/`tb_aux_ledger`）导入规则：

- `POST /api/projects/{project_id}/import` 对 `generic` 类型的 `xlsx`/`xlsm`/`csv` 文件，达到 20MB 自动切流式模式（分块处理，避免全文件载入内存）
- `on_duplicate=overwrite` 先软删同年度旧数据再写新行，旧批次标记 `rolled_back`
- 智能导入清理对同 `project_id + year` 旧四表行执行软删

超大数据集上传建议：优先单 sheet/结构化导出；使用稳定的表头名（科目编码/日期/凭证字段）减少解析回退；整期刷新用 `on_duplicate=overwrite` 避免新旧混合。

## 故障排查

```bash
# 数据库连接失败
docker-compose logs postgres

# Redis 连接失败
docker-compose logs redis

# MinerU 不可用（先确认 GPU）
nvidia-smi
docker-compose -f docker-compose.mineru.yml logs mineru
```

常见运行时陷阱：
- `uvicorn --reload` 父子进程互拉，kill 不净 → 干净验证另起端口（如 9981）绕开 reloader
- FastAPI 改 router 不热加载，需重启；新 router 必须在 `router_registry/` 注册否则前端 404
- 含静态路径的 router 必须注册在同前缀通配 router（如 `/{project_id}`）之前
- 前端下载认证资源禁用 `window.open`（不带 token → 401），必须用 `downloadFile`（axios blob + Bearer）

## 文档导航

| 文档 | 用途 |
|------|------|
| `.kiro/specs/INDEX.md` | Spec 开发索引（active + archived，定位三件套） |
| `.kiro/steering/memory.md` | AI 持久记忆（项目上下文、技术决策、近期修复） |
| `.kiro/steering/architecture.md` | 架构、系统规模、数据流 |
| `.kiro/steering/conventions.md` | 编码规范、UI 视觉、操作铁律、PG 运维 |
| `.kiro/steering/dev-history.md` | append-only 开发历史与端点速查 |
| `docs/` | 提案、部署指南、可行性评估 |

## CI / pre-commit

### 本地 pre-commit

```bash
pip install pre-commit
pre-commit install
```

### CI 流水线

推送 `master` 或发起 PR 时 GitHub Actions 并发运行：

| Job | 内容 |
|-----|------|
| `backend-tests` | pytest（排除 integration/e2e） |
| `backend-lint` | ruff check + signature_level 用法检查 |
| `seed-validate` | seed JSON schema 校验 |
| `frontend-build` | npm ci + npm run build |
| `gitleaks` | 密钥泄露扫描（gitleaks-action@v2） |

## 贡献指南

1. 改动前先 `git fetch` 同步，评估 ahead/behind
2. 协作走 PR，不直推 `main`（默认分支为 `main`）
3. 单 commit 提交所有变更；commit 前确认无 `.env`/密钥文件
4. 大改动（>500 行 / 3+ 组件 / 跨前后端）先出 spec 三件套

## 许可证

本项目采用专有许可证。
