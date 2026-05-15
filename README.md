# 审计作业平台

基于 FastAPI + Vue 3 的现代化审计作业平台，支持多种审计类型、多会计准则适配、AI 辅助审计、电子签名等高级功能。

## 项目概述

本平台是一个全场景审计作业平台，旨在将传统的审计工作流程数字化、智能化，提升审计效率和质量。

### 开发状态

- **Phase 0-7**：已完成开发（基础设施、核心功能、底稿管理、报表管理、合并报表、协作功能、AI 辅助、扩展功能、人员管理、深度增强）
- **Phase 8**：已完成规划（数据模型优化与性能提升，三件套文档已创建）
- **测试覆盖**：后端约 143 个测试（AI/OCR 相关用例受本地依赖版本影响）
- **数据库迁移**：34 个 Alembic 迁移脚本（001-034）
- **前端组件**：50+ Vue 组件
- **API 端点**：100+ REST API 端点

### 核心功能

- **多准则适配**：支持企业会计准则、小企业准则、政府会计准则、国际准则 IFRS
- **多语言支持**：中英双语界面和报表输出
- **审计类型扩展**：年度审计、专项审计、IPO 审计、内控审计、验资、税审
- **AI 辅助审计**：OCR 识别、智能分类、底稿复核、持续审计、LLM 深度融合
- **电子签名**：三级电子签名（用户名+密码、手写签名、CA 证书）
- **附件管理**：集成 Paperless-ngx 进行文档管理和 OCR 识别
- **数据可视化**：集成 Metabase 提供项目级数据可视化看板
- **致同底稿编码**：内置致同标准的底稿编码体系（B/C/D-N/A/S/Q/Z 类）
- **在线编辑**：集成 Univer 纯前端表格编辑器，支持在线文档编辑（已从 ONLYOFFICE 迁移）
- **连续审计**：支持跨年数据对比和审计项目连续管理
- **深度协作**：复核对话系统、过程记录、工时打卡、足迹记录
- **智能推荐**：底稿智能推荐、知识库上下文感知、年度差异分析报告
- **权限精细化**：三级权限控制（readonly/edit/review）、单元格级复核批注

## 技术栈

### 后端
- **框架**: FastAPI
- **数据库**: PostgreSQL 16
- **缓存**: Redis 7
- **ORM**: SQLAlchemy (async)
- **迁移**: Alembic（001-034 版本）
- **AI**: PaddleOCR、Tesseract、MinerU（可选）
- **文档编辑**: Univer 纯前端表格编辑器（原 ONLYOFFICE 已迁移）
- **底稿模板**: 致同 2025 修订版 476 个模板文件（xlsx/xlsm/docx），存储在 `backend/wp_templates/`

> **Univer xlsx 导入导出说明**
>
> 当前安装的是 Univer 开源版（`@univerjs/preset-sheets-core`），底稿模板通过后端 openpyxl 转换为 Univer JSON 格式加载。如需完整还原 xlsx 格式（条件格式/图表/数据验证），需安装 Univer Advanced Preset。
>
> **部署方式**：服务器一次性配置，所有用户通过浏览器直接使用（无需客户端安装）。
>
> ```bash
> # 1. 前端安装（构建时打入 bundle）
> cd audit-platform/frontend
> npm install @univerjs/preset-sheets-drawing @univerjs/preset-sheets-advanced
> ```
>
> 2. 在 WorkpaperEditor.vue 的 `createUniver` 中添加：
> ```typescript
> import { UniverSheetsDrawingPreset } from '@univerjs/preset-sheets-drawing'
> import { UniverSheetsAdvancedPreset } from '@univerjs/preset-sheets-advanced'
>
> presets: [
>   UniverSheetsCorePreset({ container }),
>   UniverSheetsDrawingPreset(),
>   UniverSheetsAdvancedPreset({ universerEndpoint: 'http://localhost:3010' }),
> ]
> ```
>
> 3. 部署 Univer 后端服务（提供 xlsx 解析能力）：
> ```yaml
> # docker-compose.yml 新增
> univer-server:
>   image: univer-server:latest
>   ports:
>     - "3010:3010"
> ```
> 详见 [Univer 官方部署文档](https://docs.univer.ai/guides/pro/deploy)。
>
> **不安装时**系统仍可正常使用（走后端 openpyxl 转换降级路径，丢失部分高级格式但数据完整）。
- **附件管理**: Paperless-ngx
- **性能监控**: Prometheus + prometheus-client
- **数据校验**: pandas
- **安全加密**: cryptography
- **测试**: pytest（143个测试）

### 前端
- **框架**: Vue 3 + TypeScript
- **UI 库**: Element Plus
- **文档预览**: vue-office
- **状态管理**: Pinia
- **路由**: Vue Router
- **图表**: ECharts
- **虚拟滚动**: vue-virtual-scroller
- **工具库**: @vueuse/core

### 基础设施
- **容器化**: Docker + Docker Compose
- **GPU 支持**: NVIDIA Docker（用于 MinerU）
- **存储**: 本地磁盘 + 云端存储（S3/MinIO/阿里云OSS）

## 快速开始

### 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- NVIDIA Driver（如需使用 MinerU）
- CUDA 12.9.1+（如需使用 MinerU）

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd GT_plan
```

2. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件，配置数据库密码、JWT 密钥等
```

3. **启动服务**
```bash
docker-compose up -d
```

4. **访问应用**
- 后端 API: http://localhost:8000
- API 文档: http://localhost:8000/docs
- 前端开发服务器: http://localhost:3030
- Metabase: http://localhost:3000
- Paperless-ngx: http://localhost:8010
- ONLYOFFICE: http://localhost:8080（向后兼容，底稿编辑已迁移至 Univer）

> 说明：`docker-compose.yml` 默认不包含前端容器，前端请按下文“前端开发”单独启动。

### 可选：启动 MinerU（需要 GPU）

```bash
# 构建 MinerU 镜像
bash scripts/build-mineru.sh  # Linux/Mac
scripts\build-mineru.bat      # Windows

# 启动 MinerU 服务
docker-compose -f docker-compose.mineru.yml up -d

# 启用 MinerU（在 .env 中设置）
MINERU_ENABLED=true
MINERU_API_URL=http://mineru:8000
```

## 项目结构

```
GT_plan/
├── backend/                 # FastAPI 后端
│   ├── app/               # 应用代码
│   │   ├── models/        # 数据模型
│   │   ├── services/      # 业务服务
│   │   ├── routers/       # API 路由
│   │   └── core/          # 核心配置
│   ├── alembic/           # 数据库迁移（001-034）
│   ├── tests/             # 测试文件（143个测试）
│   └── requirements.txt   # Python 依赖
├── audit-platform/         # 前端应用
│   ├── frontend/          # Vue 3 前端
│   │   ├── src/           # 源代码
│   │   └── package.json   # Node 依赖
├── storage/                # 存储目录
│   ├── projects/          # 项目级存储
│   └── users/             # 用户私人库
├── .kiro/                  # 项目规范文档
│   ├── specs/             # 各阶段规格文档
│   │   ├── phase0-infrastructure/  # Phase 0 基础设施
│   │   ├── phase1a-core/          # Phase 1a 核心功能
│   │   ├── phase1b-workpapers/    # Phase 1b 底稿
│   │   ├── phase1c-reports/       # Phase 1c 报表
│   │   ├── phase2-consolidation/  # Phase 2 合并
│   │   ├── phase3-collaboration/ # Phase 3 协作
│   │   ├── phase4-ai/             # Phase 4 AI
│   │   ├── phase8-extension/      # Phase 8 扩展
│   │   ├── phase9-staff/          # Phase 9 人员
│   │   ├── phase10-enhancement/   # Phase 10 增强
│   │   └── phase11/               # Phase 11 优化
│   └── steering/          # 项目记忆和决策
│       └── memory.md      # AI 持久记忆
├── docs/                   # 项目文档
│   └── mineru-deployment.md  # MinerU 部署指南
├── scripts/                # 构建脚本
├── docker-compose.yml      # 主服务编排
├── docker-compose.mineru.yml  # MinerU 服务编排
├── .env                    # 环境变量
├── .env.example            # 环境变量示例
└── README.md               # 项目说明
```

## 文档

### 开发阶段文档

项目采用分阶段开发模式，各阶段文档位于 `.kiro/specs/` 目录：

#### Phase 0：基础设施
- 基础架构搭建、Docker 容器化、数据库设计

#### Phase 1a：核心功能
- 科目体系、试算表、余额表、序时账、凭证表

#### Phase 1b：底稿管理
- 底稿模板、底稿解析、底稿预填、底稿导出

#### Phase 1c：报表管理
- 四张报表、报表公式、报表导出（PDF/Word）

#### Phase 2：合并报表
- 合并范围、抵消分录、少数股东、合并报表生成

#### Phase 3：协作功能
- 用户管理、权限控制、复核流程、过程记录

#### Phase 4：AI 辅助
- OCR 识别、智能分类、底稿复核、持续审计

#### Phase 8：扩展功能
- [架构优化文档](.kiro/specs/phase8-extension/architecture-optimization.md) - 架构重叠分析与优化方案
- [需求文档](.kiro/specs/phase8-extension/requirements.md) - Phase 8 需求定义
- [设计文档](.kiro/specs/phase8-extension/design.md) - Phase 8 设计方案
- [任务清单](.kiro/specs/phase8-extension/tasks.md) - Phase 8 任务分解

#### Phase 9：人员管理
- 人员简历、工时打卡、足迹记录、统计分析

#### Phase 10：深度增强
- [需求文档](.kiro/specs/phase10-enhancement/requirements.md) - Phase 10 需求定义
- [设计文档](.kiro/specs/phase10-enhancement/design.md) - Phase 10 设计方案
- [任务清单](.kiro/specs/phase10-enhancement/tasks.md) - Phase 10 任务分解
- **核心功能**：底稿下载与导入、连续审计、服务器存储与分区、过程记录与附件关联、LLM深度融合底稿、抽样程序增强、合并报表增强、复核对话系统、报告复核溯源、工时打卡与足迹、吐槽与求助专栏、私人库与LLM对话、辅助余额表汇总、权限精细化、单元格级复核批注、合并数据快照、底稿智能推荐、知识库上下文感知、年度差异分析报告、附件智能分类、报告排版模板

#### Phase 8：优化完善
- [README](.kiro/specs/phase8/README.md) - Phase 8 概述
- [需求文档](.kiro/specs/phase8/requirements.md) - Phase 8 需求定义
- [设计文档](.kiro/specs/phase8/design.md) - Phase 8 设计方案
- [任务清单](.kiro/specs/phase8/tasks.md) - Phase 8 任务分解
- **核心功能**：数据模型字段缺失修复、查询性能优化、底稿编辑体验优化、报表导出优化、移动端适配、审计程序精细化、数据校验增强、性能监控、用户体验优化、安全增强
- **数据模型优化**：trial_balance 新增 currency_code 字段支持多币种、5 个核心复合索引提升查询性能
- **查询性能**：EventBus debounce 去重（500ms 窗口合并事件）、FormulaEngine 超时控制（10s）、游标分页替代传统分页、GenericParser 流式解析（openpyxl read_only）、报表生成 Redis 缓存（TTL=10min）
- **安全增强**：bcrypt cost 从 12 升级到 14、Fernet 对称加密服务、权限查询 Redis 缓存（TTL=5min 降级查库）、安全监控（异常 IP 检测 + 会话管理）
- **前端性能**：Web Vitals 采集（FCP/LCP/TTI）+ 超阈值 ElNotification 告警、ECharts 性能趋势图 + 瓶颈分析面板
- **移动端适配**：响应式三栏布局（768px/1024px/1280px 断点）、移动端穿透查询 + 复核意见组件、触摸手势（左右滑动控制导航栏）
- **用户体验**：操作撤销（OperationHistory execute/undo + 通知栏撤销按钮）、13 个快捷键、审计程序执行进度可视化、模板共享机制

### 项目记忆
- [项目记忆文档](.kiro/steering/memory.md) - AI 持久记忆，包含项目上下文、技术决策、开发记录

### 部署文档
- [MinerU 部署指南](docs/mineru-deployment.md) - MinerU OCR 服务部署

## 开发指南

### 后端开发

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
pip install -r requirements.txt

# 运行迁移
alembic upgrade head

# 运行测试
pytest
```

### 前端开发

```bash
cd audit-platform/frontend
cp .env.example .env
# 若后端运行在 8000，请将 VITE_API_BASE_URL 改为 http://localhost:8000
npm install
npm run dev
```

## 配置说明

### 环境变量

主要配置项见 `.env.example`：

- `DATABASE_URL`: PostgreSQL 数据库连接
- `REDIS_URL`: Redis 连接
- `JWT_SECRET_KEY`: JWT 签名密钥（必填）
- `CORS_ORIGINS`: CORS 允许的前端源
- `ATTACHMENT_PRIMARY_STORAGE`: 附件主存储方式（paperless/local）
- `MINERU_ENABLED`: 是否启用 MinerU（需要 GPU）
- `CLOUD_STORAGE_TYPE`: 云端存储类型（sftp/s3/smb/local）
- `ENCRYPTION_KEY`: 数据加密密钥
- `ONLYOFFICE_URL`: 在线编辑服务地址（向后兼容，底稿编辑已迁移至 Univer 纯前端方案）

### OCR 引擎配置

系统支持三种 OCR 引擎：

1. **PaddleOCR**：高精度中文识别，用于发票/合同/回函
2. **Tesseract**：多语言支持，速度快，用于通用文档
3. **MinerU**（可选）：复杂文档解析，支持表格/公式识别

OCR 引擎会自动选择和故障回退，无需手动配置。

## 故障排查

### 数据库连接失败

检查 PostgreSQL 服务是否正常运行：
```bash
docker-compose logs postgres
```

### Redis 连接失败

检查 Redis 服务是否正常运行：
```bash
docker-compose logs redis
```

### MinerU 不可用

检查 GPU 是否可用：
```bash
nvidia-smi
```

检查 MinerU 容器状态：
```bash
docker-compose -f docker-compose.mineru.yml logs mineru
```

## Large File Import Notes

For project-year accounting data import (`tb_balance`, `tb_ledger`, `tb_aux_balance`, `tb_aux_ledger`), the backend now applies these rules:

- `POST /api/projects/{project_id}/import` automatically switches to streaming mode for `generic` uploads when file type is `xlsx`/`xlsm`/`csv` and size is at least `20MB`.
- Streaming mode processes rows in chunks and avoids router-level full-file loading into memory.
- `on_duplicate=overwrite` performs soft-delete of existing same-year data before writing new rows.
- Smart import cleanup now soft-deletes old four-table rows for the same `project_id + year` and marks previous completed batches as `rolled_back`.
- Run Alembic migrations to apply import hot-path indexes (including revision `035`) before benchmarking.

Recommended upload strategy for very large datasets:

- Prefer single-sheet or well-structured workbook exports.
- Use stable header names (account code/date/voucher fields) to reduce parser fallback costs.
- Use `on_duplicate=overwrite` for full-period refresh to avoid mixed old/new rows.

## 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 许可证

本项目采用专有许可证。

## 联系方式

如有问题或建议，请联系项目维护者。

## CI / pre-commit

### 本地 pre-commit 安装

```bash
pip install pre-commit
pre-commit install
```

安装后每次 `git commit` 会自动运行以下检查：

| Hook | 作用 | 触发文件 |
|------|------|----------|
| `check-json` | JSON 语法校验 | `backend/data/*.json` |
| `json-template-lint` | Seed 文件 schema 校验 | `backend/data/*.json` |

手动运行全部 hook（不提交）：

```bash
pre-commit run --all-files
```

### CI 流水线

推送到 `master` 或发起 PR 时，GitHub Actions 自动运行 4 个并发 job：

| Job | 内容 |
|-----|------|
| `backend-tests` | pytest（排除 integration/e2e） |
| `backend-lint` | ruff check + signature_level 用法检查 |
| `seed-validate` | validate_seed_files.py schema 校验 |
| `frontend-build` | npm ci + npm run build |

### CI 失败排查

| 失败 Job | 常见原因 | 排查步骤 |
|----------|----------|----------|
| `backend-tests` | 新代码引入测试失败 | 本地 `python -m pytest backend/tests/ --ignore=backend/tests/integration --ignore=backend/tests/e2e -x --tb=short` |
| `backend-lint` | ruff 规则违反或 `signature_level ==` 直接比较 | 本地 `python -m ruff check backend/` 修复；确认不直接比较 `signature_level` 字段 |
| `seed-validate` | seed JSON 格式错误或字段缺失 | 本地 `python scripts/validate_seed_files.py` 查看具体报错 |
| `frontend-build` | TypeScript 类型错误或依赖缺失 | 本地 `cd audit-platform/frontend && npm ci && npm run build` |
