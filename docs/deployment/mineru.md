# MinerU 部署指南

## 概述

MinerU 是一个基于深度学习的文档解析工具，用于处理复杂文档（学术论文、技术文档、表格密集型文档）。

在审计系统中，MinerU 作为 OCR 的兜底方案：
- **PaddleOCR** → 发票/合同/回函（精度优先）
- **Tesseract** → 通用文档（速度优先）
- **MinerU** → PaddleOCR/Tesseract 失败后的兜底（复杂文档解析）

## 部署方式

### 方式一：CLI 模式（推荐用于打包部署）

**适用场景：**
- 将 MinerU 集成到应用程序中
- 打包部署（如 PyInstaller、Docker）
- 不需要独立服务

#### 前置要求

- Python 3.8+
- pip
- GPU: Volta+ 架构，8GB+ VRAM（可选，CPU 模式也可运行）

#### 安装

```bash
pip install mineru[core]>=2.7.0
```

#### 验证安装

```bash
mineru --version
```

#### 配置

在 `.env` 文件中添加：

```env
# 启用 MinerU
MINERU_ENABLED=true

# 使用 CLI 模式（直接调用本地 mineru 命令）
MINERU_USE_CLI=true

# MinerU API 地址（CLI 模式下不需要）
MINERU_API_URL=http://localhost:8000
```

#### 使用方式

MinerU 会自动作为 OCR 引擎的兜底选项：

```python
from app.services.unified_ocr_service import UnifiedOCRService

ocr_service = UnifiedOCRService()
result = await ocr_service.recognize("document.pdf")
# 如果 PaddleOCR 和 Tesseract 都失败，会自动使用 MinerU CLI
```

### 方式二：Docker 部署（独立服务）

**适用场景：**
- 多个应用共享 MinerU 服务
- 需要独立管理和扩展
- GPU 资源集中管理

#### 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- NVIDIA Driver（如需 GPU 支持）
- CUDA 12.9.1+（如需 GPU 支持）
- GPU: Volta+ 架构，8GB+ VRAM
- 共享内存: 32GB 推荐（处理大文档）

#### 构建镜像

**Linux/Mac:**
```bash
bash scripts/build-mineru.sh
```

**Windows:**
```cmd
scripts\build-mineru.bat
```

#### 启动服务

```bash
docker-compose -f docker-compose.mineru.yml up -d
```

#### 配置

在 `.env` 文件中添加：

```env
# 启用 MinerU
MINERU_ENABLED=true

# 使用 HTTP 模式（调用远程 MinerU API 服务）
MINERU_USE_CLI=false

# MinerU API 地址
MINERU_API_URL=http://mineru:8000
```

#### 验证健康状态

```bash
curl http://localhost:8000/health
```

## 模式对比

| 特性 | CLI 模式 | HTTP 模式 |
|------|---------|-----------|
| 部署复杂度 | 低 | 中 |
| 打包支持 | ✅ 支持 | ❌ 不支持 |
| 资源隔离 | ❌ 无 | ✅ 有 |
| 多应用共享 | ❌ 不支持 | ✅ 支持 |
| GPU 管理 | 应用内管理 | Docker 管理 |
| 适用场景 | 单应用部署 | 多应用共享 |

## 系统要求

### 硬件要求
- **GPU**: Volta 架构或更高（如 V100、A100、RTX 30/40 系列）
- **显存**: 8GB+ 可用显存
- **内存**: 16GB+ 系统内存
- **共享内存**: 32GB+（Docker 配置）

### 软件要求
- **NVIDIA Driver**: CUDA 12.9.1 或更高
- **Docker**: 20.10+
- **Docker Compose**: 2.0+

## 部署步骤

### 1. 构建 Docker 镜像

**Linux/Mac:**
```bash
cd /path/to/GT_workplan
bash scripts/build-mineru.sh
```

**Windows:**
```cmd
cd d:\GT_workplan
scripts\build-mineru.bat
```

### 2. 启动 MinerU 服务

```bash
docker-compose -f docker-compose.mineru.yml up -d
```

### 3. 验证服务

```bash
# 检查容器状态
docker ps | grep mineru

# 检查健康状态
curl http://localhost:8000/health

# 访问 API 文档
# http://localhost:8000/docs
```

## 配置

### 环境变量配置

在 `.env` 文件中添加：

```bash
# MinerU 配置
MINERU_ENABLED=true
MINERU_API_URL=http://mineru:8000
```

### Docker Compose 配置

`docker-compose.mineru.yml` 已配置以下端口：
- `30000`: OpenAI 兼容 API
- `7860`: Gradio WebUI
- `8000`: Web API
- `8002`: MinerU Router

## 使用

### 1. 通过 UnifiedOCRService 自动使用

系统会自动在 PaddleOCR/Tesseract 失败后使用 MinerU 作为兜底：

```python
from app.services.unified_ocr_service import UnifiedOCRService

ocr_svc = UnifiedOCRService()
result = await ocr_svc.recognize("document.pdf")
# 自动尝试 PaddleOCR → Tesseract → MinerU
```

### 2. 直接调用 MinerU 服务

```python
from app.services.mineru_service import MinerUService

mineru_svc = MinerUService()
result = await mineru_svc.parse_document("document.pdf")
```

### 3. 提取表格

```python
tables = await mineru_svc.extract_tables("document.pdf")
for table in tables:
    print(table["html"])  # HTML 格式表格
    print(table["data"])  # 表格数据
```

### 4. 提取公式

```python
formulas = await mineru_svc.extract_formulas("document.pdf")
for formula in formulas:
    print(formula["latex"])  # LaTeX 格式公式
```

## 监控

### 健康检查

```bash
curl http://localhost:8000/health
```

### 查看日志

```bash
docker logs -f mineru
```

### 停止服务

```bash
docker-compose -f docker-compose.mineru.yml down
```

## 故障排查

### 问题1：GPU 不可用

**症状**: 容器启动失败或无法使用 GPU

**解决**:
```bash
# 检查 NVIDIA Driver
nvidia-smi

# 检查 Docker GPU 支持
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
```

### 问题2：显存不足

**症状**: OOM (Out of Memory) 错误

**解决**:
- 减少并发处理数量
- 使用较小的模型
- 增加 GPU 显存或使用多 GPU

### 问题3：服务连接失败

**症状**: `MinerU health check failed`

**解决**:
```bash
# 检查服务是否运行
docker ps | grep mineru

# 检查网络连接
docker network inspect audit_network

# 检查端口是否被占用
netstat -tulpn | grep 8000
```

## 性能优化

### 1. 使用 GPU 加速

确保 Docker 容器可以访问 GPU：
```yaml
runtime: nvidia
environment:
  - NVIDIA_VISIBLE_DEVICES=all
```

### 2. 调整共享内存

处理大文档时需要更大的共享内存：
```yaml
shm_size: 32g
ipc: host
```

### 3. 批量处理

对于大量文档，使用批量处理 API 提高效率。

## 与现有架构集成

MinerU 作为独立服务运行，通过 HTTP API 与后端通信：

```
Backend (FastAPI)
    ↓ HTTP API
MinerU (Docker)
    ↓ GPU
NVIDIA GPU
```

## 成本估算

### 资源占用
- **显存**: ~8GB（单文档处理）
- **内存**: ~16GB
- **磁盘**: ~10GB（镜像 + 模型）

### 运行成本
- **GPU 成本**: 根据云服务商定价（如 AWS p3.2xlarge ~$3.06/小时）
- **存储成本**: ~$0.1/GB/月

## 参考资料

- [MinerU 官方文档](https://opendatalab.github.io/MinerU/)
- [MinerU GitHub](https://github.com/opendatalab/MinerU)
- [Docker 部署文档](https://opendatalab.github.io/MinerU/quick_start/docker_deployment/)
