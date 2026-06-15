# 审计平台分布式部署方案 v2.0（瘦客户端 + 内网全栈服务器）

> 版本：v2.0 | 日期：2026-06-15 | 状态：方案设计（基于代码实际分析修正）

## 一、总体架构

### 1.1 设计理念

- 客户端极轻：用户电脑只装 Electron 壳 + PaddleOCR（~600MB），无 PG/无 FastAPI
- 全部走 API：客户端不直连数据库，所有业务操作通过 FastAPI RESTful API
- 文件存储在服务器：附件/底稿/导出文件统一存服务器（MinIO/NAS），用户电脑无需 500GB SSD
- GPU 集中：vLLM + LibreOffice 留在服务器，客户端零重型依赖
- 安全：内网部署不上公网，VPN 支持远程接入

### 1.2 架构总览

```
+-----------------------------------------------------------+
|              用户电脑（轻量客户端 ~600MB）                    |
|                                                             |
|  [Electron / Tauri 桌面端]                                  |
|   +- Vue 3 前端（Element Plus / GT 紫主题）                 |
|   +- PaddleOCR（CPU 版，本地识别 1-2s）                     |
|   +- 规则引擎（ocr_rule_engine.py，毫秒级分类+提取）        |
|   +- 嵌入式 Python 3.12（运行 OCR + 规则引擎）             |
|   +- 本地临时缓存（OCR 结果/离线队列，重启可清）            |
|                                                             |
|  【无数据库 / 无文件存储 / 无 FastAPI】                     |
+-----------------------------+-------------------------------+
                              |  内网 HTTPS（JSON + OCR 文本）
                              |  全部走 FastAPI API
                              v
+-----------------------------------------------------------+
|              内网服务器（全栈）                               |
|                                                             |
|  [Nginx]          反向代理 + HTTPS + 静态资源                |
|  [FastAPI]        业务逻辑层 x 4 workers（端口 9980）        |
|  [PostgreSQL 16]  全部业务数据                               |
|  [Redis 7]        Session / 缓存 / SSE 事件                 |
|  [vLLM]           Qwen 27B GPU 推理（端口 8100）             |
|  [LibreOffice]    xlsx 公式重算 / Office→PDF（并发限 2）     |
|  [MinIO]          对象存储：附件/底稿文件/导出文件            |
|  [PGBouncer]      连接池（50人以上启用）                     |
|                                                             |
+-----------------------------------------------------------+
```

### 1.3 与 v1.0 方案的关键变化

| 维度 | v1.0（本地全栈） | v2.0（瘦客户端+服务器） |
|------|-----------------|----------------------|
| 文件存储 | 用户本地磁盘 | 服务器 MinIO |
| 数据库 | 客户端直连 PG | 全走 FastAPI API |
| LibreOffice | 未提及 | 服务器部署 |
| 安装包 | ~350MB | ~600MB（PaddlePaddle 实际偏大） |
| 用户硬盘需求 | 500GB SSD | 普通 256GB 即可 |
| 离线能力 | 95% 功能 | OCR+规则引擎可用，业务操作需联网 |


## 二、组件分布与职责

### 2.1 用户电脑（瘦客户端）

| 组件 | 技术栈 | 大小 | 职责 |
|------|--------|------|------|
| 桌面壳 | Electron 或 Tauri | ~80MB | 窗口/系统托盘/自动更新/证书信任 |
| 前端 | Vue 3 + Vite 打包 | ~15MB | 全部 UI 交互 |
| PaddleOCR | paddleocr + PaddlePaddle CPU | ~300MB | 本地 OCR（零延迟） |
| OCR 模型 | det + rec + cls | ~150MB | 文字检测/识别/方向 |
| 规则引擎 | ocr_rule_engine.py | <1MB | 分类+字段提取+金额校验 |
| Python | 嵌入式 3.12 + pypdf | ~50MB | OCR 运行时 + PDF 文本层 |
| **总安装包** | — | **~600MB** | 双击安装，零命令行 |

减包优化路径（可选）：
- PaddlePaddle → ONNX Runtime 替换：模型转 ONNX，runtime ~30MB（省 270MB）
- 模型按需下载：首次安装 ~300MB，模型联网时自动拉取
- 如选 ONNX 方案，安装包可压到 ~200MB

用户电脑最低配置：
- CPU：Intel i5 / AMD R5（4 核+）
- 内存：8GB（OCR 峰值约 2GB）
- 硬盘：256GB（仅装程序 + 临时缓存，项目文件在服务器）
- 系统：Windows 10/11
- 网络：内网百兆+（上传附件走服务器）

### 2.2 内网服务器

| 组件 | 配置 | 职责 |
|------|------|------|
| FastAPI | uvicorn x 4 workers, 8 核 | API 层（全部业务逻辑） |
| PostgreSQL 16 | 32GB RAM, SSD 1TB | 全部业务数据 |
| Redis 7 | 4GB RAM | Session/缓存/SSE |
| vLLM | 1x RTX 4090 24GB | Qwen 27B 推理 |
| LibreOffice | CPU, 并发限 2 | xlsx 重算/Office→PDF |
| MinIO | 2TB+ SSD (可扩) | 附件/底稿文件/导出 |
| Nginx | — | 反代/HTTPS/限流/静态 |
| PGBouncer | — | 连接池（50 人+） |

服务器配置：
- CPU：16 核（FastAPI + LibreOffice + PG）
- 内存：64GB（PG 32G + FastAPI 16G + Redis 4G + 系统 12G）
- GPU：RTX 4090 24GB 或 A100 40GB
- SSD：2TB（PG 500G + MinIO 1T + 模型 200G + 系统 300G）
- 网络：千兆内网 + VPN 出口（远程接入）


## 三、数据流与通信

### 3.1 核心原则：全部走 FastAPI API

客户端不直连任何后端组件：
- 不直连 PG（无 asyncpg/psycopg2 驱动）
- 不直连 Redis
- 不直连 vLLM（通过 FastAPI 转发）
- 不直连 MinIO（通过 FastAPI 签名 URL 上传/下载）

好处：
- 安全：服务器只开一个端口（9980/443）
- 简单：客户端只需 HTTP 库
- 可控：服务端统一做限流/鉴权/审计日志

### 3.2 附件上传流程（文件存服务器 MinIO）

```
用户拖入文件
  |
  v
[客户端] PaddleOCR 本地识别（1-2s）
  |
  v
[客户端] 规则引擎分类+字段提取（毫秒）
  |
  v
[客户端] 弹出 OcrConfirmDialog（原件对照+可编辑字段）
  |   用户确认
  v
[客户端] POST /api/projects/{pid}/attachments/upload
         Body: multipart（文件二进制 + OCR 文本 + 提取字段 JSON）
  |
  v
[服务端] FastAPI 接收 → 写入 MinIO + 元数据入 PG
  |
  v
[服务端] 如 needs_llm=true → 调 vLLM 补全字段
  |
  v
[服务端] 自动核对序时账（金额匹配）
  |
  v
[服务端] 返回 { id, ledger_matches, final_fields }
  |
  v
[客户端] 列表刷新 + 显示匹配结果
```

### 3.3 底稿文件操作流程

```
打开底稿
  [客户端] GET /api/workpapers/{wp_id}/render-config → 返回渲染配置
  [客户端] GET /api/workpapers/{wp_id}/download → MinIO 签名 URL → 浏览器下载

编辑底稿（Univer/HTML 渲染器）
  [客户端] 前端本地编辑 → POST /api/workpapers/{wp_id}/save → 服务端入库

导出底稿
  [客户端] POST /api/export/workpapers → 服务端 LibreOffice 重算 → 返回 xlsx 二进制
```

### 3.4 离线工作流

```
网络断开时：
  +- OCR 识别：完全可用（本地 PaddleOCR）
  +- 规则分类+字段提取：完全可用
  +- 确认弹窗：可用（结果暂存本地 IndexedDB）
  +- 业务操作（保存/调整/复核）：不可用（需 API）

网络恢复时：
  +- 自动提交离线 OCR 结果到服务器
  +- 低置信度项批量调 vLLM
  +- 推送 toast "离线数据已同步"
```

### 3.5 通信端点汇总

| 通信方向 | 协议 | 内容 | 备注 |
|---------|------|------|------|
| 客户端 → FastAPI | HTTPS | JSON + multipart 文件 | 唯一对外端口 443/9980 |
| 客户端 ← FastAPI | SSE | 实时事件推送 | EventSource 长连接 |
| FastAPI → PG | TCP 5432 | SQL | 内部，不暴露 |
| FastAPI → Redis | TCP 6379 | Cache/Pub | 内部 |
| FastAPI → vLLM | HTTP 8100 | prompt + response | localhost |
| FastAPI → MinIO | HTTP 9000 | S3 协议 | 内部 |
| FastAPI → LibreOffice | subprocess | 文件转换 | 本机进程 |


## 四、文件存储方案（MinIO 对象存储）

### 4.1 为什么不存用户本地

- 避免用户电脑需要 500GB SSD（审计项目附件量大）
- 多人协作需要共享文件（不能 A 电脑的附件 B 看不到）
- 服务器集中备份（避免个人电脑硬盘损坏丢数据）
- 统一权限控制（不能绕过 API 直接读文件）

### 4.2 MinIO 存储结构

```
minio-bucket: audit-platform/
  +- projects/{project_id}/
  |   +- attachments/{attachment_id}/{filename}
  |   +- workpapers/{wp_id}/{filename}
  |   +- exports/{export_id}/{filename}
  |   +- templates/{template_code}/{filename}
  +- global/
      +- report_templates/{template_manifest.json, *.docx, *.xlsx}
      +- wp_templates/{A~S 循环目录}
```

### 4.3 文件上传/下载走预签名 URL

```python
# 服务端生成 MinIO 预签名 URL（10 分钟有效）
@router.get("/api/attachments/{id}/download-url")
async def get_download_url(id: UUID):
    url = minio.presigned_get_object("audit-platform", f"projects/{pid}/attachments/{id}/{name}", expires=600)
    return {"url": url}

# 大文件上传用预签名 PUT
@router.get("/api/attachments/upload-url")
async def get_upload_url(project_id: UUID, filename: str):
    url = minio.presigned_put_object("audit-platform", f"projects/{pid}/attachments/{uuid}/{filename}", expires=600)
    return {"url": url}
```

客户端直接用预签名 URL 上传/下载 MinIO（走内网，不经过 FastAPI 转发大文件）：
- 小文件（<5MB）：直接 POST multipart 到 FastAPI
- 大文件（>=5MB）：获取预签名 URL → 客户端直传 MinIO → 回调 FastAPI 确认

### 4.4 存储容量规划

| 项目规模 | 预估容量 | MinIO 配置 |
|---------|---------|-----------|
| 10 个项目 | ~50GB | 单节点 1TB SSD |
| 50 个项目 | ~250GB | 单节点 2TB SSD |
| 200 个项目 | ~1TB | 双节点 EC 纠删 |
| 500+ 项目 | ~3TB | 分布式 4 节点 |

每个审计项目约 5GB（底稿 500MB + 附件 4GB + 导出 500MB）


## 五、客户端打包与分发

### 5.1 安装包构建

```
构建产物：GT_AuditPlatform_Setup_v1.0.exe（~600MB）

结构：
  +- electron.exe（Electron 壳）
  +- resources/
  |   +- app.asar（Vue dist 打包）
  +- python-embed/（嵌入式 Python 3.12）
  |   +- python.exe
  |   +- Lib/site-packages/paddleocr/...
  |   +- ocr_rule_engine.py
  +- models/（PaddleOCR 模型文件）
  |   +- ch_PP-OCRv4_det/
  |   +- ch_PP-OCRv4_rec/
  |   +- ch_ppocr_mobile_v2.0_cls/
  +- config.yaml（服务器地址配置）
```

### 5.2 前端 API 基地址注入

Electron main 进程启动时读 config.yaml 注入全局变量：

```javascript
// electron/main.js
const config = yaml.load(fs.readFileSync('config.yaml'))
mainWindow.webContents.executeJavaScript(
  `window.__GT_CONFIG__ = ${JSON.stringify(config)}`
)
```

前端 http.ts 适配：
```typescript
// src/utils/http.ts
const API_BASE = (window as any).__GT_CONFIG__?.server?.api_url || '/'
const http = axios.create({ baseURL: API_BASE, timeout: 120000 })
```

### 5.3 本地 OCR 调用方式

Electron 通过 child_process 调用嵌入式 Python：

```javascript
// electron/ocr-bridge.js
const { execFile } = require('child_process')
const PYTHON = path.join(__dirname, 'python-embed/python.exe')

function runOcr(filePath) {
  return new Promise((resolve, reject) => {
    execFile(PYTHON, ['-m', 'ocr_local', filePath], { timeout: 30000 }, (err, stdout) => {
      if (err) reject(err)
      else resolve(JSON.parse(stdout))
    })
  })
}
```

`ocr_local.py` 入口脚本：
```python
import sys, json
from ocr_rule_engine import run_rule_pipeline
from paddleocr import PaddleOCR

ocr = PaddleOCR(lang='ch', use_angle_cls=True, use_gpu=False, show_log=False)
result = ocr.ocr(sys.argv[1], cls=True)
text = '\n'.join(line[1][0] for page in result for line in page if line)
pipeline_result = run_rule_pipeline(text)
print(json.dumps(pipeline_result, ensure_ascii=False))
```

### 5.4 自动更新

```yaml
# 更新检查端点
GET /api/system/client-version
Response: {
  "latest": "1.2.0",
  "min_required": "1.1.0",
  "download_url": "/updates/GT_AuditPlatform_Patch_1.2.0.exe",
  "changelog": "修复 OCR 数电票识别问题"
}

策略：
  - latest > current → 提示更新（可跳过）
  - min_required > current → 强制更新（API 拒绝旧版本）
  - 增量补丁：只更新变更文件（非全量 600MB 重装）
```

### 5.5 HTTPS 证书信任（Electron 内网自签）

```javascript
// electron/main.js
// 内网环境信任自签证书（仅限内网部署场景）
app.commandLine.appendSwitch('ignore-certificate-errors-spki-list', INTERNAL_CA_FINGERPRINT)
// 或者注入内网 CA
session.defaultSession.setCertificateVerifyProc((request, callback) => {
  if (request.hostname === '192.168.1.100') callback(0) // 信任内网服务器
  else callback(-2) // 其他拒绝
})
```


## 六、多人协作

### 6.1 数据全在服务端，天然支持多人

与 v1.0 不同，v2.0 所有数据（PG + MinIO）在服务器：
- 不存在"A 电脑的文件 B 看不到"的问题
- 不需要 P2P 同步/CouchDB 方案
- 与当前 Web 版完全一致的协作体验

### 6.2 并发控制（复用已有机制）

| 机制 | 表/组件 | 说明 |
|------|--------|------|
| 底稿编辑锁 | workpaper_editing_locks | 同一底稿同时只能一人编辑 |
| 章节编辑锁 | editing_locks | 附注/报告章节级锁 |
| 调整分录审批 | review_status 状态机 | draft→pending→approved |
| 复核链 | WpReviewStatus | 多级审批 |
| SSE 实时通知 | /api/projects/{pid}/events/stream | 他人操作实时推送 |

新增：
- 客户端心跳：每 30s POST /api/heartbeat → 服务端记录在线状态
- 编辑锁超时：60s 无心跳自动释放锁
- 在线状态：侧边栏显示"张三 在线 · 正在编辑 D2-1"

### 6.3 Web 版与桌面端双轨并行

- 同一服务器同时支持 Web 浏览器 + Electron 桌面端
- 数据完全互通（同一 PG + MinIO）
- 桌面端优势：本地 OCR 零延迟
- Web 端优势：零安装（合伙人/QC 偶尔使用）

## 七、安全设计

### 7.1 网络

| 措施 | 说明 |
|------|------|
| 内网部署 | 服务器不开放公网端口 |
| HTTPS | 自签证书（内网 CA） |
| VPN | 远程/出差通过 VPN 接入 |
| 防火墙 | 仅开放 443/9980 给客户端网段 |

### 7.2 认证授权

| 措施 | 说明 |
|------|------|
| JWT | 24h access + 30d refresh（已有） |
| RBAC | 6 角色权限矩阵（已有） |
| 审计日志 | 全部 API 操作记录 app_audit_log |
| 设备绑定 | 可选：device_id 绑定限制登录设备数 |

### 7.3 LLM 数据安全

传给 vLLM 的数据控制：
- 仅 OCR 文本前 500 字（分类）或前 2000 字（字段提取）
- 不传原始文件二进制
- 可选脱敏规则（正则替换公司名/税号后再发 LLM）
- vLLM 本地部署，数据不出内网

### 7.4 文件安全

| 措施 | 说明 |
|------|------|
| MinIO 访问 | 预签名 URL（10 分钟过期） |
| 传输加密 | MinIO 启用 TLS |
| 静态加密 | MinIO SSE-S3 服务端加密 |
| 备份 | 每日增量备份到异地 NAS |


## 八、实施路线图（修正版）

### Phase 1：服务器侧准备（1 周）

| 任务 | 产出 |
|------|------|
| MinIO 部署 + S3 桶创建 | 文件存储就绪 |
| attachment_service 改为 MinIO 后端（替换本地磁盘） | 新 storage_type="minio" |
| 预签名 URL 上传/下载端点 | 大文件直传 MinIO |
| FastAPI 增加 /api/system/client-version 端点 | 自动更新支持 |
| Nginx HTTPS 配置（自签 CA） | 安全通信 |

### Phase 2：客户端壳搭建（2 周）

| 任务 | 产出 |
|------|------|
| Electron 项目初始化 + Vue dist 打包加载 | 基础桌面端 |
| config.yaml 读取 + window.__GT_CONFIG__ 注入 | 可配置服务器地址 |
| http.ts baseURL 改为读取全局配置 | 连接内网服务器 |
| HTTPS 证书信任逻辑 | 内网自签证书可用 |
| Python embed + PaddleOCR 集成 | 本地 OCR 就绪 |
| ocr-bridge.js 封装 | Electron ↔ Python IPC |

### Phase 3：OCR 流程对接（1 周）

| 任务 | 产出 |
|------|------|
| 前端 AttachmentManagement 识别走本地 OCR（不调服务端） | 零延迟体验 |
| OcrConfirmDialog 确认后 POST 到服务端（带文件+字段） | 数据入库 |
| BatchUploadResultDialog 批量结果走本地 OCR | 文件夹上传毫秒出结果 |
| 离线队列（IndexedDB）+ 联网恢复同步 | 断网可用 |

### Phase 4：体验与运维（1 周）

| 任务 | 产出 |
|------|------|
| 自动更新机制（检查+增量下载+热重启） | 运维零成本 |
| 心跳 + 编辑锁超时释放 | 多人无冲突 |
| electron-builder 打包 + 安装包签名 | Setup.exe 分发 |
| 安装向导（首次运行填服务器地址） | 用户友好 |

### Phase 5：验证（1 周）

| 任务 | 产出 |
|------|------|
| 10 人并发功能测试 | 协作验证 |
| OCR 识别准确率对比（本地 vs 服务端） | 质量基线 |
| 大项目压测（1000+ 附件上传） | 性能基线 |
| 安全审计（端口扫描/权限渗透） | 安全报告 |

总计：约 6 周 MVP，第 1 批 10 人试用。

## 九、成本估算

### 9.1 服务器（一次性）

| 项目 | 规格 | 预算 |
|------|------|------|
| GPU 服务器 | 16核/64GB/RTX 4090/2TB SSD | 3-5 万 |
| MinIO 扩容盘 | 额外 2TB SSD | 1500 元 |
| UPS | 防断电 | 2000 元 |
| 网络交换机 | 千兆管理型 | 1000 元 |
| **合计** | — | **约 4-6 万** |

### 9.2 客户端（每人）

| 项目 | 预算 |
|------|------|
| 硬件 | 0（现有电脑 8GB+ RAM 即可，无需 500GB SSD） |
| 软件 | 0（安装包内网分发） |
| 代码签名证书 | 2000 元/年（可选，避免 SmartScreen） |

### 9.3 运维月度

| 项目 | 工时 |
|------|------|
| PG 备份验证 | 0（自动脚本） |
| MinIO 容量监控 | 0（Prometheus 告警） |
| 客户端推送更新 | 0.5h/次 |
| vLLM 模型更新 | 2h/季度 |

## 十、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| 服务器宕机 | 全部在线功能中断 | PG 主从热备 + MinIO 纠删 + 客户端离线模式兜底 |
| 内网带宽拥塞 | 大文件上传慢 | 预签名直传 MinIO + 分片上传 + 压缩 |
| vLLM GPU 故障 | LLM 不可用 | 规则引擎兜底（conf>=0.8 已覆盖 80%+ 票据） |
| PaddleOCR 模型过大 | 安装包 600MB | ONNX 替代（远期优化 → 200MB） |
| Windows 安全策略 | exe 被拦截 | 代码签名 + IT 白名单 |
| 用户忘记 VPN | 出差无法使用 | 离线 OCR + 回来后自动同步 |
| MinIO 磁盘满 | 新附件上传失败 | Prometheus 告警 80% 阈值 + 自动归档旧项目 |

## 十一、与现有系统的兼容

### 双轨运行策略

```
现有 Web 版（浏览器）  ──────> [同一 FastAPI + PG + MinIO]
新桌面端（Electron）   ──────>
```

- 两种客户端共用后端，数据完全互通
- Web 版无需任何修改（继续 Vite dev proxy 或 Nginx 反代）
- 桌面端是增量能力（本地 OCR + 离线），不破坏 Web 版
- 建议先给"高频 OCR 用户"（审计助理/实习生处理差旅票据）发桌面端
- 合伙人/质控/经理继续用 Web 版（无安装负担）

### 服务端代码改动清单（最小化）

| 改动 | 文件 | 影响 |
|------|------|------|
| MinIO 存储后端 | attachment_service.py | storage_type 新增 "minio" 分支 |
| 预签名 URL 端点 | attachments.py | 新增 2 个 GET 端点 |
| client-version 端点 | system.py | 新增 1 个 GET |
| heartbeat 端点 | system.py | 新增 1 个 POST |
| CORS 允许 Electron origin | main.py | 加 `app://` 到 CORS |
| **前端改动** | http.ts | baseURL 读全局配置（5 行） |
