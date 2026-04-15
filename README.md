# 审计作业平台

基于 FastAPI + Vue 3 的现代化审计作业平台，支持多种审计类型、多会计准则适配、AI 辅助审计、电子签名等高级功能。

## 项目概述

本平台是一个全场景审计作业平台，旨在将传统的审计工作流程数字化、智能化，提升审计效率和质量。

### 核心功能

- **多准则适配**：支持企业会计准则、小企业准则、政府会计准则、国际准则 IFRS
- **多语言支持**：中英双语界面和报表输出
- **审计类型扩展**：年度审计、专项审计、IPO 审计、内控审计、验资、税审
- **AI 辅助审计**：OCR 识别、智能分类、底稿复核、持续审计
- **电子签名**：三级电子签名（用户名+密码、手写签名、CA 证书）
- **附件管理**：集成 Paperless-ngx 进行文档管理和 OCR 识别
- **数据可视化**：集成 Metabase 提供项目级数据可视化看板
- **致同底稿编码**：内置致同标准的底稿编码体系（B/C/D-N/A/S/Q/Z 类）

## 技术栈

### 后端
- **框架**: FastAPI
- **数据库**: PostgreSQL 16
- **缓存**: Redis 7
- **ORM**: SQLAlchemy (async)
- **迁移**: Alembic
- **AI**: PaddleOCR、Tesseract、MinerU（可选）
- **文档服务**: ONLYOFFICE Document Server
- **附件管理**: Paperless-ngx

### 前端
- **框架**: Vue 3 + TypeScript
- **UI 库**: Element Plus
- **文档预览**: vue-office
- **状态管理**: Pinia
- **路由**: Vue Router

### 基础设施
- **容器化**: Docker + Docker Compose
- **GPU 支持**: NVIDIA Docker（用于 MinerU）

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
cd GT_workplan
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
- 前端: http://localhost:5173
- Metabase: http://localhost:3000
- Paperless-ngx: http://localhost:8010
- ONLYOFFICE: http://localhost:8080

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
GT_workplan/
├── backend/                 # FastAPI 后端
│   ├── app/               # 应用代码
│   │   ├── models/        # 数据模型
│   │   ├── services/      # 业务服务
│   │   ├── routers/       # API 路由
│   │   └── core/          # 核心配置
│   ├── alembic/           # 数据库迁移
│   ├── tests/             # 测试文件
│   └── requirements.txt   # Python 依赖
├── frontend/              # Vue 3 前端
│   ├── src/               # 源代码
│   └── package.json       # Node 依赖
├── .kiro/                 # 项目规范文档
│   └── specs/             # 各阶段规格文档
│       └── phase8-extension/  # Phase 8 扩展功能
├── docs/                  # 项目文档
│   └── mineru-deployment.md  # MinerU 部署指南
├── scripts/               # 构建脚本
├── docker-compose.yml     # 主服务编排
├── docker-compose.mineru.yml  # MinerU 服务编排
└── .env.example           # 环境变量示例
```

## 文档

### Phase 8 扩展功能

- [架构优化文档](.kiro/specs/phase8-extension/architecture-optimization.md) - 架构重叠分析与优化方案
- [需求文档](.kiro/specs/phase8-extension/requirements.md) - Phase 8 需求定义
- [设计文档](.kiro/specs/phase8-extension/design.md) - Phase 8 设计方案
- [任务清单](.kiro/specs/phase8-extension/tasks.md) - Phase 8 任务分解

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
cd frontend
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
