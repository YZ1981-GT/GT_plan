# AI 基础设施选型评估与部署建议

> 评估日期：2026-07-04 | 状态：技术调研阶段
> 涵盖：OCR / 向量数据库 / Embedding / 文档解析 / LLM 推理演进

本文档统一评估审计平台 AI 基础设施的技术选型，覆盖 5 个核心组件的候选方案。

| # | 组件 | 候选方案 | 章节 |
|---|------|----------|------|
| 1 | 结构化 OCR | baidu/Unlimited-OCR | 一~七 |
| 2 | 向量数据库 | alibaba/zvec | 八 |
| 3 | Embedding 模型 | bge-m3 / gte-Qwen3-embedding | 九 |
| 4 | 复杂文档解析 | MinerU | 十 |
| 5 | LLM 推理框架演进 | vLLM Phase3 | 十一 |

---

## 组件一：Unlimited-OCR 结构化 OCR

> 模型版本：baidu/Unlimited-OCR (2026-06-22 开源)
> 论文：arXiv:2606.23050 | 许可证：MIT | GitHub Stars: 10,000+ (5天)

---

## 一、模型核心事实

| 项目 | 数值 |
|------|------|
| 总参数量 | 3.3B（MoE 架构） |
| 每 token 激活参数 | ~500M |
| 架构 | SAM-ViT-B + CLIP-L DeepEncoder（视觉塔） + DeepSeek-V2 MoE Decoder（文本） |
| 核心创新 | R-SWA（Reference Sliding Window Attention）+ Constant KV Cache |
| 上下文长度 | 32K tokens |
| 单次处理能力 | 40+ 页文档（单次 forward pass） |
| 输出格式 | Markdown + HTML 表格 + LaTeX 公式 + Bbox 坐标 |
| 精度（OmniDocBench v5） | 93.23%（SOTA，比 DeepSeek-OCR 高 6 个百分点） |
| 推理 VRAM 需求（BF16） | ≥ 8 GB |
| 推理速度参考 | ~79 tok/s（M4 Max / CoreML），GPU 端预估 150-300 tok/s |
| 支持框架 | Transformers / vLLM / SGLang / ONNX / GGUF / MLX |

### R-SWA 机制价值

传统 OCR 模型处理长文档时 KV Cache 线性膨胀，导致显存爆炸和速度递减。R-SWA 将视觉 token 作为固定参考锚点，文本解码用滑动窗口，KV Cache 大小恒定。意味着：
- 处理第 1 页和第 40 页时显存占用相同
- 无需分页切片 → 保留跨页上下文（表格跨页、合同条款引用）
- 适合审计场景的长合同/多页凭证批量识别

---

## 二、与现有 OCR 方案对比

### 当前平台 OCR 架构

```
UnifiedOCRService
├── HTTP 远程模式（OCR_SERVICE_URL → Docker 容器 8200 端口）
│   └── PaddleOCR 容器（POST /recognize）
├── In-process 降级（未配置远程时）
│   ├── PaddleOCR（发票/合同/回函 → 结构化文档优先）
│   ├── Tesseract（通用文档 → 速度优先）
│   └── MinerU（兜底 → 复杂版面）
└── D4 合同 OCR 专用路径
    └── PaddleOCR → LLM 二次提取 20 字段
```

### 方案对比矩阵

| 维度 | PaddleOCR（当前） | Tesseract（当前） | Unlimited-OCR（候选） |
|------|-------------------|-------------------|----------------------|
| 精度 | 中高（中文结构文档 85-90%） | 中（中文 75-85%） | 极高（93.23% SOTA） |
| 表格保留 | 无（纯文本） | 无 | 原生 HTML 表格 |
| 公式识别 | 无 | 无 | LaTeX 输出 |
| 多页连续 | 逐页分片，无跨页上下文 | 逐页 | 40+ 页单次，有上下文 |
| 延迟（单页） | 1-3s（CPU） | 0.2-0.5s（CPU） | 5-15s（GPU），取决于文档密度 |
| 并发能力 | CPU 横扩，几乎无限 | CPU 横扩 | 受 GPU 显存限制，需 batching |
| VRAM 占用 | 0（CPU 模式） | 0 | 8-10 GB（BF16） |
| 部署复杂度 | Docker 镜像，开箱即用 | pip install | 需 CUDA GPU + 模型下载 6.5GB |
| 结构化提取 | 需 LLM 二次提取 | 需后处理 | 一步到位（Markdown 结构化） |

---

## 三、审计平台场景适配分析

### 强烈推荐使用 Unlimited-OCR 的场景

| 场景 | 当前痛点 | Unlimited-OCR 价值 |
|------|----------|-------------------|
| D4 合同 OCR | PaddleOCR → LLM 两步，延迟高、成本高 | 一步输出结构化 Markdown，省掉 LLM 调用 |
| 凭证附件批量识别 | 逐页调用，无上下文 | 多页一次性，保留凭证间逻辑 |
| 函证回函（D05/D06） | 表格丢失，需人工还原 | 表格→HTML 原生保留 |
| 银行对账单 | 多页表格断裂 | 跨页表格连续识别 |
| 审计报告/附注 PDF 解析 | 公式丢失，版面错乱 | 公式→LaTeX，版面→结构化 |

### 不建议替换的场景

| 场景 | 原因 |
|------|------|
| 实时 OCR 预览（用户上传即显） | 延迟 5-15s 不可接受，PaddleOCR 1-3s 更合适 |
| 简单文本提取（单行凭证摘要） | 过度工程，Tesseract 0.2s 足够 |
| 高并发轻量请求（>50 QPS） | GPU 资源瓶颈，CPU 方案横扩更经济 |

---

## 四、部署方案建议

### 方案 A：云服务器部署（生产环境，推荐）

#### 硬件配置

| 组件 | 最低配置 | 推荐配置 |
|------|----------|----------|
| GPU | 1× RTX 4090 24GB | 1× A100 40GB（或 L40S 48GB） |
| CPU | 8 核 | 16 核 |
| 内存 | 32 GB | 64 GB |
| 存储 | 50 GB SSD（模型 + 缓存） | 100 GB NVMe |
| 网络 | 内网互联 | 内网万兆 |

#### 推荐架构

```
                    ┌─────────────────────────────────────────┐
                    │           GPU 服务器                      │
                    │                                         │
  ┌─────────┐      │  ┌──────────────────────────────────┐   │
  │ 后端    │ HTTP │  │  vLLM (Unlimited-OCR)            │   │
  │ 9980   ├──────┼──┤  端口: 8300                       │   │
  │         │      │  │  模型: baidu/Unlimited-OCR        │   │
  └─────────┘      │  │  显存: ~8GB                       │   │
                    │  └──────────────────────────────────┘   │
                    │                                         │
                    │  ┌──────────────────────────────────┐   │
                    │  │  vLLM (Qwen3.5-27B-NVFP4)       │   │
                    │  │  端口: 8100                       │   │
                    │  │  显存: ~20GB                      │   │
                    │  └──────────────────────────────────┘   │
                    │                                         │
                    │  剩余显存: 用于 KV Cache + Batch         │
                    └─────────────────────────────────────────┘
```

#### 显存规划（单卡 24GB 场景，如 RTX 4090）

| 模型 | 显存占用 | 备注 |
|------|----------|------|
| Qwen3.5-27B-NVFP4 | ~18GB（0.93 利用率） | 当前已部署 |
| Unlimited-OCR BF16 | ~8GB | 无法同时部署在同一张卡 |

**结论：单卡 24GB 无法同时运行两个模型。** 选项：

1. **双卡方案**（推荐）：卡 0 跑 Qwen，卡 1 跑 Unlimited-OCR
2. **分时复用**：OCR 请求时动态加载（冷启动 ~30s，不推荐）
3. **云端独立实例**：OCR 专用 GPU 实例（L40S 48GB 约 $0.61/hr）
4. **量化方案**：使用 NVFP4 量化版（~2GB），可与 Qwen 共卡

#### vLLM 部署命令

```bash
# 独立 vLLM 实例（端口 8300）
python -m vllm.entrypoints.openai.api_server \
  --model baidu/Unlimited-OCR \
  --trust-remote-code \
  --logits_processors vllm.model_executor.models.unlimited_ocr:NGramPerReqLogitsProcessor \
  --no-enable-prefix-caching \
  --mm-processor-cache-gb 0 \
  --port 8300 \
  --gpu-memory-utilization 0.85 \
  --max-model-len 32768 \
  --dtype bfloat16
```

#### SGLang 替代方案（更高并发）

```bash
python -m sglang.launch_server \
  --model baidu/Unlimited-OCR \
  --served-model-name Unlimited-OCR \
  --attention-backend fa3 \
  --page-size 1 \
  --mem-fraction-static 0.8 \
  --context-length 32768 \
  --enable-custom-logit-processor \
  --disable-overlap-schedule \
  --host 0.0.0.0 \
  --port 8300
```

---

### 方案 B：单机版部署（开发/小型事务所）

#### 硬件要求

| 项目 | 最低 | 推荐 |
|------|------|------|
| GPU | RTX 3060 12GB | RTX 4060 Ti 16GB / RTX 4070 12GB |
| 内存 | 16 GB | 32 GB |
| 磁盘 | 20 GB 可用 | SSD 50 GB |
| 系统 | Windows 10/11 + CUDA 12.x | Windows 11 + CUDA 12.9 |

#### 安装步骤（Windows，无 Docker）

```powershell
# 1. 创建独立虚拟环境（避免污染审计平台 Python 环境）
python -m venv D:\unlimited-ocr-env
D:\unlimited-ocr-env\Scripts\activate

# 2. 安装 PyTorch（CUDA 12.x）
pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cu129

# 3. 安装推理依赖
pip install transformers==4.57.1 Pillow==12.1.1 einops==0.8.2 ^
  addict==2.4.0 easydict==1.13 pymupdf==1.27.2.2 psutil==7.2.2

# 4. 下载模型（首次约 6.5GB，后续使用缓存）
python -c "from transformers import AutoModel, AutoTokenizer; AutoTokenizer.from_pretrained('baidu/Unlimited-OCR', trust_remote_code=True); AutoModel.from_pretrained('baidu/Unlimited-OCR', trust_remote_code=True, use_safetensors=True)"
```

#### 单机显存冲突解决

当前开发环境 GPU 被 Qwen3.5 占满（0.93 利用率）。解决方案：

| 方案 | 操作 | 适用场景 |
|------|------|----------|
| A. 按需切换 | 停 vLLM → 启 OCR 服务 → 用完停 OCR → 重启 vLLM | 开发调试 |
| B. NVFP4 量化 | 使用 `sahilchachra/Unlimited-OCR-NVFP4`（~2GB） | 日常共存 |
| C. GGUF + llama.cpp | 使用 Q4_K_M 量化（~2GB），CPU+GPU 混合 | 低显存机器 |
| D. 降低 Qwen 显存 | `VLLM_GPU_MEM=0.70`（释放 ~5GB）→ 足够加载 OCR | 开发环境 |

#### 推荐：NVFP4 量化版共存方案

```python
# 使用 FP4 量化版，显存仅需 ~2GB
model_name = 'sahilchachra/Unlimited-OCR-NVFP4'
model = AutoModel.from_pretrained(
    model_name,
    trust_remote_code=True,
    use_safetensors=True,
    torch_dtype=torch.bfloat16,  # 视觉塔保持 BF16
).eval().cuda()
```

---

## 五、集成改动评估

### 后端改动（约 200 行）

```python
# 1. unified_ocr_service.py — 新增 engine
class OCREngine(str, Enum):
    PADDLE = "paddle"
    TESSERACT = "tesseract"
    MINERU = "mineru"
    UNLIMITED = "unlimited"  # 新增
    AUTO = "auto"

# 2. 新增 _unlimited_recognize 方法
async def _unlimited_recognize(self, image_path: str, multi_page: bool = False) -> dict:
    """调用 Unlimited-OCR vLLM 实例（OpenAI 兼容 API）"""
    # POST /v1/chat/completions with image base64
    ...

# 3. config.py 新增配置
UNLIMITED_OCR_URL: str = ""  # http://localhost:8300/v1
UNLIMITED_OCR_ENABLED: bool = False
```

### 路由决策逻辑

```python
# _select_engine 增强
if file_name matches 合同/PDF/多页:
    if unlimited_available:
        return OCREngine.UNLIMITED  # 结构化文档优先走 Unlimited
    elif paddle_available:
        return OCREngine.PADDLE
```

### D4 合同 OCR 简化

```python
# 当前：PaddleOCR → LLM 提取 20 字段（两步）
# 改造后：Unlimited-OCR 一步 → 正则/结构化解析 Markdown
# 省掉 LLM 调用，降低延迟和成本
```

### 前端无需改动

OCR 结果仍走现有 API 返回给前端，结构不变。

---

## 六、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| GPU 显存不足 | 无法与 Qwen 共存 | NVFP4 量化（2GB）/ 双卡 / 云端独立 |
| 推理延迟高（5-15s/页） | 用户等待体验差 | 仅用于异步批量场景，实时仍走 PaddleOCR |
| 模型刚开源 12 天 | 生产稳定性未验证 | 先 D4 试点，保留 PaddleOCR 降级路径 |
| Windows 兼容性 | CUDA/torch 版本可能冲突 | 独立 venv，pin 版本 |
| 输出含 grounding tokens | 需后处理 `<|ref|>/<|det|>` | 统一 post-processor 清洗 |
| 中文竖排/手写体 | 模型主攻印刷体/版面 | 手写场景保留 PaddleOCR |

---

## 七、结论与行动建议

### 总体判断

Unlimited-OCR 在审计场景具有高价值（结构化输出 + 多页连续 + 高精度），但不适合全面替换现有方案。推荐**混合部署、渐进引入**。

### 分阶段路线图

| 阶段 | 时间 | 目标 |
|------|------|------|
| P0 试点 | 1-2 周 | 本地安装 NVFP4 量化版，用审计合同样本测试精度 |
| P1 D4 集成 | 2-3 周 | 替换 D4 合同 OCR 的 PaddleOCR+LLM 两步流程 |
| P2 批量模式 | 1 个月 | 凭证附件批量识别、函证回函表格提取 |
| P3 生产部署 | 2 个月 | 云服务器独立 GPU 实例，高并发 SGLang 方案 |

### 立即可做

1. 在当前开发机降低 `VLLM_GPU_MEM=0.70`，释放 ~5GB 显存
2. 安装 NVFP4 量化版到独立 venv
3. 用 3-5 份真实审计合同 PDF 做精度对比测试
4. 若精度满意，出 `unlimited-ocr-integration` spec 三件套

---

## 附录：依赖清单

### Python 包（Unlimited-OCR 专用）

```
torch==2.10.0
torchvision==0.25.0
transformers==4.57.1
Pillow==12.1.1
matplotlib==3.10.8
einops==0.8.2
addict==2.4.0
easydict==1.13
pymupdf==1.27.2.2
psutil==7.2.2
```

### 系统依赖

- NVIDIA Driver ≥ 550
- CUDA Toolkit ≥ 12.4（推荐 12.9）
- Python 3.12

### 模型权重来源

| 变体 | 大小 | 用途 |
|------|------|------|
| `baidu/Unlimited-OCR` | 6.5 GB | 官方 BF16（精度最优） |
| `sahilchachra/Unlimited-OCR-NVFP4` | ~2 GB | FP4 量化（共存方案） |
| `sahilchachra/Unlimited-OCR-GGUF` | 1.8-6.5 GB | llama.cpp 部署 |
| `vimalnakrani/unlimited-ocr-6bit-mlx` | 3.2 GB | Apple Silicon（参考） |

### 参考链接

- [HuggingFace 模型卡](https://huggingface.co/baidu/Unlimited-OCR)
- [GitHub 仓库](https://github.com/baidu/Unlimited-OCR)
- [vLLM 部署 Recipe](https://recipes.vllm.ai/baidu/Unlimited-OCR)
- [arXiv 论文](https://arxiv.org/abs/2606.23050)
- [NVFP4 量化版](https://huggingface.co/sahilchachra/Unlimited-OCR-NVFP4)


---

## 组件二：Zvec 向量数据库

> alibaba/zvec v0.5.0 (2026-06-12) | Apache 2.0 | GitHub Stars: 6000+

### 概述

Zvec 是阿里巴巴通义实验室开源的嵌入式（in-process）向量数据库，定位"向量数据库界的 SQLite"。进程内运行、零网络延迟、pip install 即用，在 VectorDBBench Cohere 10M 数据集上 QPS 是此前第一名 ZillizCloud 的 2 倍以上。

### 核心能力

| 能力 | 说明 |
|------|------|
| 向量搜索 | Dense + Sparse 向量，HNSW / DiskANN / 量化索引 |
| 全文检索（v0.5） | 原生 FTS，无需 Elasticsearch |
| 混合检索 | 单次 MultiQuery 融合：向量 + 全文 + 标量过滤 |
| DiskANN 索引 | 大数据集低内存模式（索引存磁盘） |
| 持久化 | WAL 保证崩溃不丢数据 |
| 并发 | 多进程并发读，单进程写独占 |
| SDK | Python / Node.js / Go / Rust / Dart |
| 平台 | Linux / macOS / Windows（x86_64） |

### 与竞品对比

| 维度 | Zvec | ChromaDB | Qdrant | Milvus Lite |
|------|------|----------|--------|-------------|
| 部署模式 | 进程内嵌入 | 进程内/CS | Client-Server | 进程内 |
| 网络开销 | 零 | 低 | 有（HTTP/gRPC） | 低 |
| 混合检索 | 原生（v0.5） | 需拼装 | 原生 | 原生 |
| DiskANN | ✅ | ❌ | ❌ | ❌ |
| 全文搜索 | 原生 FTS | ❌ | 需 payload index | ❌ |
| QPS（10M 768d） | 极高（benchmark 第一） | 中 | 高 | 中 |
| 内存效率 | 高（量化+DiskANN） | 高内存占用 | 中 | 中 |
| 生产验证 | 阿里十亿级 | 社区 | 社区+企业 | Zilliz 企业 |
| 成熟度 | 2026-02 开源（较新） | 2022（成熟） | 2021（成熟） | 2019（最成熟） |

### 审计平台适用场景

| 场景 | 方案 | 价值 |
|------|------|------|
| 底稿语义搜索 | bge-m3 embedding → Zvec 存储/检索 | 按语义找相关底稿/准则，替代关键词搜索 |
| 审计知识库 RAG | 准则/法规/模板分块 → Zvec + 混合检索 | LLM 生成审计意见时检索相关依据 |
| 凭证相似度匹配 | 凭证摘要 embedding → 相似凭证聚类 | 异常检测、批量抽凭辅助 |
| 跨年度续审 | 上年底稿向量 → 语义对比变化点 | v3.0 愿景方向的技术基础 |
| 全文+向量混合 | wp_code/金额精确匹配 + 语义模糊搜索 | 审计助理搜索体验提升 |

### 安装与集成

```bash
# 安装（Python 3.10-3.14）
pip install zvec

# 基本用法
import zvec

schema = zvec.CollectionSchema(
    name="audit_knowledge",
    vectors=zvec.VectorSchema("embedding", zvec.DataType.VECTOR_FP32, 1024),  # bge-m3 维度
    fields=[
        zvec.FieldSchema("wp_code", zvec.DataType.STRING),
        zvec.FieldSchema("content", zvec.DataType.STRING, fts=True),  # 全文索引
        zvec.FieldSchema("category", zvec.DataType.STRING),
    ],
)

collection = zvec.create_and_open(path="./data/zvec_audit", schema=schema)

# 混合查询：向量相似 + 全文关键词 + 标量过滤
results = collection.query(
    zvec.MultiQuery(
        vector=zvec.VectorQuery("embedding", vector=query_embedding),
        text=zvec.TextQuery("content", "存货 减值 跌价准备"),
        filter=zvec.Filter("category", "==", "CAS"),
    ),
    topk=10,
)
```

### 与 Unlimited-OCR 的协同

```
PDF/图片 → Unlimited-OCR（结构化提取） → 文本分块 → bge-m3 embedding → Zvec 存储
                                                                          ↓
用户查询 → bge-m3 → Zvec 混合检索 → Top-K 上下文 → Qwen3.5 生成审计意见
```

### 部署建议

| 环境 | 方案 |
|------|------|
| 云服务器 | Zvec 进程内嵌入后端，数据目录 `/data/zvec/`，DiskANN 索引 |
| 单机版 | 同上，数据随应用目录，无额外服务 |
| 数据规模 | <100 万向量用 HNSW 内存索引；>100 万用 DiskANN 降内存 |
| Embedding | 复用现有 vLLM 8101 端口的 bge-m3 服务 |

### 风险

| 风险 | 缓解 |
|------|------|
| 开源仅 5 个月 | 阿里内部已生产验证；MIT/Apache 许可无锁定 |
| 写入单进程独占 | 审计平台单后端进程写入，不影响 |
| Python SDK 版本要求 3.10+ | 当前环境 Python 3.12，满足 |
| 无管理 UI | 有 Zvec Studio 可视化工具 |

### 参考链接

- [GitHub 仓库](https://github.com/alibaba/zvec)
- [PyPI](https://pypi.org/project/zvec/)
- [Zvec vs Qdrant vs Milvus 对比](https://www.f22labs.com/blogs/zvec-vs-qdrant-vs-milvus-vector-database-comparison-for-rag/)
- [Zvec 组织主页](https://github.com/zvec-ai)


---

## 组件三：Embedding 模型评估

> 当前方案：BAAI/bge-m3 @ vLLM 8101 端口

### 现状

| 项目 | 配置 |
|------|------|
| 模型 | BAAI/bge-m3（1024 维，多语言） |
| 部署 | vLLM 独立实例，端口 8101 |
| 用途 | 底稿 AI / 知识库检索（当前仅 chat 调用，embedding 端点待接入） |
| 显存 | ~2GB（0.12 利用率，Qwen 启动后加载） |

### 候选升级方案

| 模型 | 维度 | 语言 | 特点 | 状态 |
|------|------|------|------|------|
| BAAI/bge-m3（当前） | 1024 | 多语言 | Dense + Sparse + ColBERT 三模式 | 已部署 |
| Alibaba/gte-Qwen3-embedding | 1024 | 多语言 | Qwen3 基座，instruction-following 更强 | 候选 |
| BAAI/bge-reranker-v2.5-gemma2-lightweight | - | 多语言 | 重排序模型（配合 embedding 提升精度） | 补充 |

### 建议

当前 bge-m3 满足需求，短期无需替换。待 Zvec 接入后，如果检索精度不足再考虑：
1. 加入 reranker 二阶段重排
2. 评估 gte-Qwen3-embedding（同系模型，减少 tokenizer 碎片化）
3. 利用 Zvec 原生 Sparse 向量支持，发挥 bge-m3 的 Sparse + Dense 混合能力

---

## 组件四：MinerU 复杂文档解析

> 当前状态：config 中 `MINERU_ENABLED=false`，已有 `MinerUService` 代码框架

### 概述

MinerU 是面向复杂版面（双栏论文、杂志、扫描件）的文档解析引擎，互补 OCR：
- OCR 解决"识别文字"
- MinerU 解决"理解版面结构"（段落/表格/图片/页眉页脚分离）

### 当前集成状态

```python
# unified_ocr_service.py 已有 MinerU 降级路径
async def _mineru_fallback(self, image_path: str) -> dict:
    """MinerU 兜底方案 - 用于复杂文档解析"""
```

### 与 Unlimited-OCR 的关系

| 维度 | Unlimited-OCR | MinerU |
|------|---------------|--------|
| 定位 | 文字识别 + 结构化输出 | 版面分析 + 区域分割 |
| 输出 | Markdown/HTML/LaTeX | 结构化 JSON（区域坐标 + 类型） |
| 表格 | 原生 HTML 表格 | 表格区域检测 → 需后续 OCR |
| GPU | 必须（≥8GB） | 可选（CPU 可运行，GPU 加速） |
| 适用 | 印刷体文档识别 | 复杂版面理解（扫描件、混合排版） |

### 建议

- Unlimited-OCR 在表格/公式/结构化方面已覆盖 MinerU 的主要价值
- MinerU 保留作为特殊场景降级（扫描质量极差的老旧文件）
- 短期优先级低：P3 或更后，等 Unlimited-OCR 试点验证后再决定是否保留

---

## 组件五：vLLM 推理框架演进

> 当前版本：vLLM 运行 Qwen3.5-27B-NVFP4 @ 端口 8100

### 现状

| 项目 | 配置 |
|------|------|
| 模型 | Kbenkhaled/Qwen3.5-27B-NVFP4 |
| 端口 | 8100（chat）/ 8101（embedding） |
| 显存利用率 | 0.93（几乎占满单卡） |
| 上下文 | 32K tokens |
| 用途 | 底稿 AI 章节生成 / 合同字段提取 / 审计判断辅助 |

### Phase3 演进方向

| 方向 | 内容 | 前置条件 |
|------|------|----------|
| 多模型共存 | Qwen3.5 + Unlimited-OCR 同卡/多卡 | 双卡或 NVFP4 量化 OCR |
| Speculative Decoding | 小模型草稿 + 大模型验证，提速 2-3x | vLLM 支持（已有） |
| APC（Automatic Prefix Caching） | 底稿模板重复 prompt 缓存 | 已配置 |
| 结构化输出 | JSON mode / guided decoding | 已支持，B60 LLM 策略依赖 |
| 流式 + 工具调用 | Agent 模式，LLM 调用审计 API | v3.0 愿景方向 |

### B60 LLM 辅助策略（待 Phase3）

需要的基础设施：
1. 结构化 JSON 输出（vLLM guided decoding）→ 底稿字段自动填充
2. 长上下文（32K+）→ 合同全文分析
3. 多轮对话 → AI 追问模式
4. Tool calling → 审计 API 集成

### 建议

- Phase3 核心是"多模型编排"：chat (Qwen) + OCR (Unlimited-OCR) + embedding (bge-m3) 三路并行
- 硬件瓶颈在单卡显存，推荐双卡（RTX 4090 × 2 或 A100 40GB）
- 软件层 vLLM 已满足需求，无需更换框架

---

## 总体路线图

```
2026-07 (P0)                    2026-08 (P1)                    2026-09 (P2)
├─ Unlimited-OCR NVFP4 试点     ├─ D4 合同 OCR 替换             ├─ 批量凭证 OCR
├─ Zvec pip install 验证        ├─ Zvec 接入知识库 RAG          ├─ 混合检索上线
├─ bge-m3 维持现状              ├─ bge-m3 Sparse+Dense 混合     ├─ reranker 补充
├─ MinerU 保持 disabled         ├─ MinerU 评估是否移除          ├─ 决定保留/移除
└─ vLLM 单模型                  └─ 双模型共存验证               └─ 三路并行生产

2026-10+ (P3)
├─ B60 LLM 辅助策略落地
├─ AI 对话追问模式
├─ v3.0 跨年度续审知识继承（Zvec 存储上年向量）
└─ 双卡/云部署定型
```

---

## 依赖关系图

```
                         ┌────────────────────┐
                         │  Qwen3.5-27B       │
                         │  (chat/generation)  │
                         │  vLLM:8100         │
                         └────────┬───────────┘
                                  │
    ┌─────────────┐    ┌──────────┴──────────┐    ┌─────────────────┐
    │ Unlimited-  │    │   FastAPI 后端       │    │  bge-m3         │
    │ OCR         │◄───┤   :9980             ├───►│  (embedding)    │
    │ vLLM:8300   │    │                     │    │  vLLM:8101      │
    └─────────────┘    └──────────┬──────────┘    └────────┬────────┘
                                  │                         │
                       ┌──────────┴──────────┐    ┌────────┴────────┐
                       │  PaddleOCR          │    │  Zvec           │
                       │  (轻量实时 OCR)     │    │  (进程内向量DB) │
                       │  Docker:8200        │    │  ./data/zvec/   │
                       └─────────────────────┘    └─────────────────┘
```


---

## 组件六：GitHub Top 20 AI 项目借鉴分析

> 数据来源：GitHub Stars 排名（2026-04），fungies.io / medium / opendatascience 交叉验证

### Top 20 概览

| # | 项目 | Stars | 语言 | 定位 | 审计平台相关度 |
|---|------|-------|------|------|---------------|
| 1 | AutoGPT | 183K | Python | 自主 Agent 框架 | ⭐ 低 |
| 2 | Langflow | 146K | Python | 可视化 Agent 工作流 | ⭐⭐ 中 |
| 3 | Dify | 136K | TypeScript | 生产级 Agent+RAG 平台 | ⭐⭐⭐ 高 |
| 4 | LangChain | 132K | Python | Agent 工程基础平台 | ⭐⭐ 中 |
| 5 | Gemini CLI | 100K | TypeScript | 终端 AI Agent | ⭐ 低 |
| 6 | Browser-use | 86K | Python | AI 浏览器自动化 | ⭐⭐⭐ 高 |
| 7 | RAGFlow | 77K | Python | 深度文档 RAG 引擎 | ⭐⭐⭐⭐ 极高 |
| 8 | LobeHub | 74K | TypeScript | 多 Agent 协作平台 | ⭐⭐ 中 |
| 9 | MetaGPT | 66K | Python | 角色扮演多 Agent | ⭐⭐ 中 |
| 10 | OpenBB | 65K | Python | 金融数据分析平台 | ⭐⭐⭐ 高 |
| 11 | AutoGen | 56K | Python | 多 Agent 对话框架 | ⭐⭐ 中 |
| 12 | AI Agents for Beginners | 56K | Jupyter | Microsoft 教程 | ⭐ 低 |
| 13 | Mem0 | 52K | Python | AI 持久记忆层 | ⭐⭐⭐⭐ 极高 |
| 14 | Flowise | 51K | TypeScript | 无代码 Agent 构建 | ⭐⭐ 中 |
| 15 | CrewAI | 48K | Python | 角色分工协作 Agent | ⭐⭐⭐ 高 |
| 16 | LocalAI | 44K | Go | 本地模型运行引擎 | ⭐⭐⭐ 高 |
| 17 | Cherry Studio | 42K | TypeScript | AI 生产力工具 | ⭐⭐ 中 |
| 18 | Agno | 39K | Python | Agent 编排框架 | ⭐⭐ 中 |
| 19 | MindsDB | 38K | Python | SQL 驱动 AI 分析 | ⭐⭐⭐ 高 |
| 20 | ToolJet | 37K | JavaScript | 内部工具构建平台 | ⭐⭐ 中 |

### 行业趋势洞察

1. **可视化/低代码 Agent 构建器称霸**：Top 5 中 3 个是可视化工具（Langflow/Dify/Flowise）
2. **多 Agent 编排是新前沿**：MetaGPT/LobeHub/CrewAI/AutoGen 聚焦多 Agent 协作
3. **持久记忆成为刚需**：Mem0 (52K) 解决 Agent 跨 session 记忆问题
4. **浏览器自动化爆发**：Browser-use (86K) 让 AI 像人一样操作网页
5. **本地/私有部署趋势**：LocalAI (44K) 无 GPU 运行任意模型，隐私+成本驱动

### 重点借鉴项目

#### RAGFlow（77K ⭐）— 知识检索架构

RAGFlow 核心是"深度文档理解 + RAG"，直接对标审计知识库：

| RAGFlow 能力 | 审计平台对应 |
|-------------|-------------|
| 文档解析（表格/标题/OCR） | 底稿模板解析、合同 OCR |
| 知识库分块 + 向量检索 | 准则/法规/底稿语义搜索（用 Zvec） |
| 引用溯源（citation） | ref_index chip 跨底稿引用 |
| Agent + RAG 融合 | B60 LLM 辅助策略 |
| GraphRAG | 跨底稿关系图谱 |

借鉴点（不引入整体，太重）：
- 分块策略：按标题层级 + 表格边界切分
- 引用回溯 UI：AI 生成内容可点击跳转到原始证据
- Reranker 二阶段：粗检索 → 精排序

#### Mem0（52K ⭐）— 跨年度续审记忆

Mem0 解决的问题正是 v3.0 愿景"项目级知识自动提取 + 跨年度续审继承"：

| Mem0 概念 | 审计场景映射 |
|-----------|-------------|
| 持久记忆层 | 项目审计历史（关键判断/风险点/前期发现） |
| 跨 session 记忆 | 跨年度——今年自动知道去年的重点 |
| 记忆提取/合并/更新 | 底稿结论自动提取为知识条目 |
| 用户偏好记忆 | 合伙人偏好（关注点/模板/签字习惯） |

借鉴点：
- 记忆提取 pipeline：对话/文档 → 结构化记忆条目
- 用 Zvec 做底层存储（替换 Mem0 默认的 Qdrant）
- 设计 `audit_memory` 表：project_id + year + memory_type + embedding + raw_text

#### Browser-use（86K ⭐）— 数据自动采集

| 场景 | 实现 |
|------|------|
| 银行对账单下载 | AI 登录网银 → 选日期 → 下载 PDF |
| ERP 余额导出 | 进入财务模块 → 筛选 → 导出 Excel |
| 税务数据抓取 | 电子税务局 → 申报表 → 下载 |
| 工商查询 | 天眼查 → 批量查询关联方 |

优先级 P3（Electron 客户端发布后），安全风险高需严格权限控制。

#### CrewAI（48K ⭐）— 5 角色协作

```
CrewAI 概念         →    审计平台映射
Agent (角色)        →    审计助理 / 经理 / 合伙人 / QC / EQCR
Task (任务)         →    底稿编制 / 一级复核 / 签字 / 质控检查
Crew (团队)         →    project_assignments 项目组
Process (流程)      →    sequential (底稿→复核→签字)
```

不引入框架，借鉴"角色具有记忆+工具+目标"的抽象：AI 辅助根据角色调整输出。

#### OpenBB（65K ⭐）— 金融分析 UI

借鉴：Dashboard 仪表盘布局、数据透视 drill-down、多年度并排对比视图。适用于 A1 Dashboard 和试算表可视化。

#### MindsDB（38K ⭐）— SQL 驱动分析

借鉴"SQL 驱动异常检测"思路：将分析规则写成 PG 视图/函数，如自动标记方差超 50% 的科目。不引入框架。

### 借鉴路线图

| 优先级 | 项目 | 借鉴内容 | 对应阶段 |
|--------|------|----------|----------|
| P1 | RAGFlow | 分块策略 + 引用溯源 UI + Reranker | Zvec 接入后 |
| P2 | Mem0 | 持久记忆架构 → 跨年度续审知识继承 | v3.0 愿景 |
| P3 | Browser-use | 审计数据自动采集 Agent | Electron 后 |
| 参考 | CrewAI/OpenBB/MindsDB | UI/UX + 概念借鉴 | 持续 |

---

## 组件七：上线部署与用户体验保障建议

### 一、云服务器部署方案

#### 推荐架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      Nginx / Caddy 反向代理                      │
│               SSL 终结 + gzip + 静态资源 CDN 缓存                │
└────────┬───────────────────────────────────┬────────────────────┘
         │                                   │
┌────────▼────────┐                 ┌────────▼────────┐
│  前端 SPA       │                 │  后端 API       │
│  Nginx :443     │                 │  uvicorn :9980  │
│  dist/ 静态文件 │                 │  4 workers      │
└─────────────────┘                 └────────┬────────┘
                                             │
         ┌───────────────────────────────────┼──────────────────┐
         │                                   │                  │
┌────────▼────────┐  ┌──────────────────┐  ┌▼───────────────┐  │
│  PostgreSQL 16  │  │  Redis           │  │  vLLM          │  │
│  PgBouncer 6432 │  │  6379            │  │  8100(chat)    │  │
│  max_conn=200   │  │  session+cache   │  │  8101(embed)   │  │
└─────────────────┘  └──────────────────┘  └────────────────┘  │
                                                                │
┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  OnlyOffice 9.4 │  │  PaddleOCR       │  │  Unlimited-OCR │  │
│  8080           │  │  8200            │  │  8300 (P1后)   │  │
└─────────────────┘  └──────────────────┘  └────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

#### 硬件推荐（6000 并发目标）

| 组件 | 配置 | 数量 | 说明 |
|------|------|------|------|
| Web/API 服务器 | 16C 64G | 2 台 | Nginx + uvicorn，前端+后端共存 |
| 数据库服务器 | 8C 32G NVMe | 1 台 | PG 16 + PgBouncer + Redis |
| GPU 服务器 | 8C 32G + A100 40GB | 1 台 | vLLM (chat+embed) + OCR |
| 对象存储 | - | - | 附件/底稿文件（MinIO 或云 OSS） |

#### 关键性能优化

```yaml
# 1. 数据库连接池
PG max_connections: 200
PgBouncer pool_mode: transaction
PgBouncer default_pool_size: 50

# 2. Redis 缓存策略
session_ttl: 86400        # 24h session
render_config_cache: 300  # 5min 渲染配置缓存
tb_summary_cache: 60      # 1min 试算表汇总缓存

# 3. 后端 Worker
uvicorn workers: 4        # CPU 核数
uvicorn backlog: 2048
uvicorn timeout: 120

# 4. 前端优化
gzip: on
static_cache: 30d
chunk_split: route-level lazy loading
```

#### 高可用建议

| 层级 | 措施 |
|------|------|
| 接入层 | Nginx 双机 + keepalived VIP |
| 应用层 | 2 台 uvicorn 实例，负载均衡轮询 |
| 数据层 | PG streaming replication（主从），自动 failover |
| 缓存层 | Redis Sentinel 或单机（审计场景可接受短暂丢失） |
| GPU 层 | 单点（AI 功能降级不影响核心业务） |
| 备份 | PG pg_dump 每日 + WAL 归档，保留 30 天 |

---

### 二、单机版（Electron 瘦客户端）部署方案

#### 目标用户

中小事务所、驻场审计团队，5-20 人使用，无专业运维。

#### 硬件最低要求

| 项目 | 最低 | 推荐 |
|------|------|------|
| CPU | i5-12400 / Ryzen 5 5600 | i7-13700 / Ryzen 7 7700 |
| 内存 | 16 GB | 32 GB |
| 磁盘 | 256 GB SSD | 512 GB NVMe |
| GPU | 无（AI 功能禁用） | RTX 4060 Ti 16GB（AI 全功能） |
| 网络 | 仅局域网 | 局域网 + 互联网（模型下载） |

#### 安装包结构

```
AuditPlatform-Setup-v2.0.exe
├── Electron 客户端（前端 SPA 内嵌）
├── Python 3.12 Embedded（免安装 Python）
├── PostgreSQL 16 Portable
├── Redis Windows 版
├── uvicorn 后端（打包为 PyInstaller 或 embedded）
├── OnlyOffice DocumentServer（可选，200MB）
├── 模型文件（可选下载）
│   ├── bge-m3 (~1.5GB)
│   └── Unlimited-OCR-NVFP4 (~2GB)
└── start-all.bat / stop-all.bat
```

#### 一键启动脚本

```batch
@echo off
title 审计平台 v2.0

echo [1/4] 启动数据库...
start /B pgsql\bin\pg_ctl start -D data\pgdata -l logs\pg.log
start /B redis\redis-server.exe redis\redis.conf

echo [2/4] 等待数据库就绪...
:wait_pg
pgsql\bin\pg_isready -q || (timeout /t 1 /nobreak >nul & goto wait_pg)

echo [3/4] 启动后端...
start /B python\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 9980 --workers 2

echo [4/4] 启动前端...
start electron\AuditPlatform.exe

echo ✅ 审计平台已启动
echo    后端: http://localhost:9980
echo    前端: http://localhost:3030
pause
```

#### AI 功能分级

| 级别 | GPU 要求 | 功能 |
|------|----------|------|
| L0 基础版 | 无 GPU | 全部底稿功能，AI 禁用，OCR 用 Tesseract |
| L1 轻量 AI | RTX 3060 12GB | bge-m3 embedding + 语义搜索 |
| L2 完整 AI | RTX 4060 Ti 16GB | Qwen-7B + OCR + embedding |
| L3 旗舰 AI | RTX 4090 24GB | Qwen3.5-27B + Unlimited-OCR + embedding |

---

### 三、用户体验保障清单

#### 首次启动体验

| 环节 | 措施 |
|------|------|
| 安装 | 单 EXE 安装包，<5 分钟完成 |
| 首次启动 | 进度条显示各服务启动状态 |
| 初始化 | 自动创建 admin 账号，引导修改密码 |
| 数据导入 | 向导式：选择 Excel 试算表 → 自动解析 → 确认导入 |
| 示例项目 | 预置一个演示项目（虚构数据），用户可体验全流程 |

#### 性能体验

| 指标 | 目标 | 措施 |
|------|------|------|
| 页面首屏 | <1.5s | 前端路由级 lazy loading + gzip |
| 底稿打开 | <2s | render-config 缓存 + 组件 defineAsyncComponent |
| 试算表加载 | <1s | Redis 缓存 + 分页加载 |
| AI 响应（首 token） | <3s | vLLM streaming + SSE |
| OCR 识别 | <5s/页 | PaddleOCR 实时 + Unlimited-OCR 后台队列 |
| 搜索 | <500ms | Zvec 进程内 + PG GIN 索引 |

#### 离线能力

| 场景 | 方案 |
|------|------|
| 无网络环境 | Electron 本地全栈，所有功能离线可用 |
| 模型离线 | 首次联网下载后本地缓存，永不再需网络 |
| 数据同步 | 回到网络后增量同步到云端（P2 功能） |

#### 错误处理与降级

| 异常 | 降级策略 | 用户感知 |
|------|----------|----------|
| vLLM 挂掉 | AI 按钮灰色 + tooltip "AI 服务暂不可用" | 核心功能不受影响 |
| OCR 服务挂掉 | 返回 503 + 前端提示"请稍后重试" | 不阻塞底稿编辑 |
| Redis 挂掉 | 跳过缓存直查 PG | 略慢但不报错 |
| OnlyOffice 挂掉 | 自动切换到 HTML 渲染模式 | 用户可能无感知 |
| PG 连接池耗尽 | 队列等待 30s + 友好提示 | 避免直接 500 |

#### 数据安全

| 措施 | 说明 |
|------|------|
| 传输加密 | HTTPS（云）/ localhost 免 TLS（单机） |
| 数据库加密 | PG TDE（生产可选）/ 文件系统加密（BitLocker） |
| 备份 | 自动每日备份 + 7 天滚动保留 |
| 审计日志 | 所有底稿操作记录 who/when/what |
| 权限隔离 | 项目 RLS 行级安全 + 角色权限矩阵 |

#### 升级策略

| 环境 | 方案 |
|------|------|
| 云端 | 蓝绿部署：新版本启动验证 → Nginx 切流 → 旧版本保留 1h |
| 单机 | 增量更新包（仅 diff 文件）+ migration_runner 自动跑迁移 |
| 数据库 | V*.sql 迁移幂等（IF NOT EXISTS），支持跨多版本升级 |
| 回滚 | 保留前一版本备份，一键恢复脚本 |

#### 监控与告警（云端）

```yaml
# 关键指标
- API P95 响应时间 > 3s → 告警
- PG 连接使用率 > 80% → 告警
- GPU 显存 > 95% → 告警
- 磁盘使用 > 85% → 告警
- uvicorn worker restart → 告警
- 错误率 > 1% → 告警

# 工具选择
- Prometheus + Grafana（云端监控）
- 或 Metabase 内置仪表盘（轻量方案，已部署 :3000）
```

---

### 四、上线前 Checklist

#### 基础设施

- [ ] PG 连接池压测通过（150 并发连接持续 10 分钟无超时）
- [ ] Redis 内存上限设置（maxmemory 2GB + allkeys-lru）
- [ ] 前端 dist 构建无警告，gzip 后 < 5MB
- [ ] SSL 证书配置（云端）
- [ ] 备份脚本 cron 验证
- [ ] migration_runner 从 V001 到 V097 全量跑通

#### 功能验证

- [ ] 5 角色各自登录、权限隔离正确
- [ ] 试算表导入 → 底稿生成 → 审定表回写 完整链路
- [ ] OnlyOffice 编辑 → callback 保存 → 版本记录
- [ ] AI 章节生成（有 GPU）/ AI 禁用降级（无 GPU）
- [ ] OCR 上传 → 识别 → 字段提取
- [ ] 导入导出（模板下载 / 数据导出 / 数据导入）

#### 性能验证

- [ ] Locust 压测：200 并发用户，持续 5 分钟，P95 < 3s
- [ ] 大项目测试：1000+ 底稿、50 万行试算表加载无卡顿
- [ ] 前端 Lighthouse Performance > 80

#### 安全验证

- [ ] SQL 注入测试通过
- [ ] XSS 测试通过
- [ ] 未授权访问（无 token / 错误 token / 跨项目）返回 401/403
- [ ] 文件上传类型校验 + 大小限制
- [ ] 密码强度策略启用
