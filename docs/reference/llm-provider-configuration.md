# AI 模型与远程 OCR 配置指南

> 适用范围：本地 vLLM、外部 OpenAI-compatible 对话/Embedding，以及 PaddleX JSON `ocr` / `layout-parsing` 服务。
> 所有模型配置接口均为 **admin-only**；API Key 只写不读，以 Fernet 密文存储。

## 1. 配置权威源与前置条件

运行时优先级固定为：

1. `ai_model_config` 中该类型/能力的 active row；
2. 仅在没有 active row 时，回落 `.env` 的 `LLM_*` bootstrap 配置。

模型调用每次重新读取 active row，因此切换后不依赖当前 worker 内存，后端重启和多 worker 仍一致。系统设置通用接口不再允许改 LLM URL/Key，统一在 `/settings/ai-models` 管理。

### 必须先配置 ENCRYPTION_KEY

```env
ENCRYPTION_KEY=<每个环境独立的随机值>
```

生成命令（在 `backend` 目录）：

```powershell
..\.venv\Scripts\python.exe -c "from app.services.encryption_service import EncryptionService; print(EncryptionService.generate_key())"
```

修改后重启后端。未配置时，本地无 Key 模型仍可用，但保存任何 per-model Key 会返回 503；不会降级成明文。

## 2. 企业 OpenAI-compatible 对话模型

以下示例对应“自定义 OpenAI 兼容服务”，示例 Key 不能直接使用：

| 字段 | 配置值 |
|---|---|
| 模型类型 | 对话模型 |
| 供应商 | 自定义 OpenAI 兼容服务 |
| 模型名称 | `qwen3.8` |
| 端点 URL | `https://ai.gt-china.com.cn:10010/v1` |
| API Key | 在后台输入真实值（示例写作 `sk-placeholder`） |
| 上下文窗口 | `262144`（256K） |
| 思考强度 | 默认「未指定」（企业网关此时按 `xhigh` 处理）；网关只接受 `low` / `medium` / `xhigh`，传 `high` 返回 400 |

平台发送（以选择 `low` 为例；「未指定」时请求里不带 `reasoning_effort`，由模型服务端默认决定）：

```http
POST https://ai.gt-china.com.cn:10010/v1/chat/completions
Authorization: Bearer <decrypted-key>
Content-Type: application/json
```

```json
{
  "model": "qwen3.8",
  "messages": [{"role": "user", "content": "..."}],
  "temperature": 0.3,
  "max_tokens": 2000,
  "reasoning_effort": "low",
  "stream": false
}
```

外部服务不会收到本地 vLLM/Qwen 专用的 `chat_template_kwargs`。注意：模型宣称 256K 不会自动扩大平台输入预算；`AI_CHAT_MAX_CONTEXT_TOKENS` 默认仍是 32000，如需提高必须单独评估并发、RAG 截断和成本后修改。

### 管理页面操作

V194 已预置 `qwen3.8`，用户无需填写模型名、地址或上下文；V195 起思考强度默认「未指定」，由用户自行选择：

1. 进入“AI 模型配置”，找到带“企业预设”标签的 `qwen3.8`。
2. 点击“录入 Key”，输入真实 API Key；按需选择思考强度（未指定 / 低 / 中 / 极高，页面只列网关支持的取值；未指定 = 网关默认 xhigh，最慢、消耗最多）。模型名、端点、上下文仍锁定，后端对预设只接受 Key 与思考强度两项修改，并拒绝网关不支持的取值。
3. 保存后 Key 只显示“已配置”，不会回显掩码值。
4. 点击“测试连接”；成功后点击“激活”。测试与激活使用与生产相同的地址、鉴权和思考强度参数；推理模型在测试中只输出思考内容也算连通。
5. 后续编辑时 Key 留空表示保留；勾选“显式清除”才删除。若测试提示“请求参数被拒绝”，把思考强度改回「未指定」再试。

## 3. 企业远程 PaddleOCR/PaddleX

平台按 PaddleX Basic Serving JSON 协议接入；两个能力可以同时 active：

| 模型 | OCR 能力 | 基础地址 | 接口路径 | 建议超时 |
|---|---|---|---|---:|
| `paddleocrv6` | 文字识别 | `https://ai.gt-china.com.cn:10080` | `/ocr` | 60 秒 |
| `paddleocrvl-1.6` | 版面解析 | `https://ai.gt-china.com.cn:10080` | `/layout-parsing` | 120 秒 |

V194 已分别预置这两条模型，用户只需在 OCR 标签页找到“企业预设”并点击“录入 Key”；模型、地址、能力、接口路径、协议、认证方式和超时均已锁定。预设认证方式为：

```text
Authorization: Bearer <用户输入的 Key>
```

若内部网关实际不使用 Bearer，应新增非预设 OCR 配置并选择 `X-API-Key`、`api-key` 或自定义 Header，不能改写企业预设。

### OCR 请求与响应契约

平台读取服务器侧文件，校验大小后发送 Base64 JSON；不会把客户文件 URL暴露给服务端：

```json
{
  "file": "<base64>",
  "fileType": 1,
  "visualize": false
}
```

`fileType=0` 表示 PDF，`1` 表示图片。成功响应必须符合：

```json
{
  "errorCode": 0,
  "errorMsg": "Success",
  "result": {
    "ocrResults": []
  }
}
```

版面解析使用 `layoutParsingResults`。平台只保留规范化文字、区域和版面块，不保留响应中的可视化 Base64 大图。测试连接使用内置合成 PNG，不发送任何项目文件。若内部网关的字段名与 PaddleX 官方协议不同，需提供脱敏请求/响应样例后新增 adapter，不应在生产代码中猜字段。

正常附件 OCR 会优先使用 active `ocr` 能力；显式版面解析调用使用 active `layout_parsing` 能力。已选择远程模型时，网络/认证/响应错误会标记失败，不静默改成本地空文本“成功”。

## 4. 支持矩阵

| Provider | Base URL | 鉴权 | 状态 |
|---|---|---|---|
| 本地 vLLM | `http://localhost:8100/v1` | 可无 | 支持 chat/embedding |
| 自定义 OpenAI-compatible | 公网 HTTPS 或 allowlist 私网 | Bearer | 支持 chat/embedding |
| DeepSeek | `https://api.deepseek.com` | Bearer | 支持 |
| 阿里云百炼 | `https://<WorkspaceId>.<region>.maas.aliyuncs.com/compatible-mode/v1` | Bearer | 支持 |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | Bearer | 支持 |
| Azure OpenAI v1 | `https://<resource>.openai.azure.com/openai/v1` | `api-key` | 支持；模型名填 deployment name |
| Ollama | `http://localhost:11434/v1` | 无 | 支持 OpenAI-compatible 子集 |
| 本地 PaddleOCR | 无 URL | 无 | 支持文字 OCR |
| 远程 PaddleX | 自定义安全 HTTPS | 可选白名单认证头 | 支持 `ocr` / `layout_parsing` |

2026 官方资料核对：DeepSeek 当前文档使用 `https://api.deepseek.com`；阿里云百炼推荐 WorkspaceId 专属域名；Azure v1 使用 `/openai/v1/` 且 Key 模式要求 `api-key` header；Ollama 提供 `/v1/chat/completions`；PaddleX Basic Serving 的 OCR/版面解析采用 Base64 JSON。参见 [DeepSeek API](https://api-docs.deepseek.com/)、[阿里云 OpenAI 兼容接口](https://help.aliyun.com/en/model-studio/compatibility-of-openai-with-dashscope)、[Azure OpenAI v1](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/switching-endpoints)、[Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)、[PaddleOCR OCR pipeline](https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/pipeline_usage/OCR.html) 和 [PaddleOCR-VL](https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/pipeline_usage/PaddleOCR-VL.html)。Content was rephrased for compliance with licensing restrictions.

## 5. Endpoint 安全策略

- DeepSeek、百炼、智谱和 Azure 只能使用各自官方域名/后缀。
- 自定义公网服务必须使用 HTTPS；自定义端口（如 `10010`、`10080`）允许。
- 私网 IP、容器服务名或 HTTP 服务必须在服务端配置精确 allowlist：

```env
LLM_ENDPOINT_ALLOWLIST=http://vllm:8000/v1,http://ocr:8080
```

三个企业预设的两个精确 base URL 已作为内建可信端点登记，因此即使当前 VPN/TUN 将域名映射为 `198.18.0.224`，用户也无需再配置 `LLM_ENDPOINT_ALLOWLIST`。该放行只覆盖：

- `https://ai.gt-china.com.cn:10010/v1`
- `https://ai.gt-china.com.cn:10080`

其他 198.18/15 或私网地址仍必须进入环境 allowlist；metadata/link-local、多播和未指定地址始终拒绝。

- 保存时校验 scheme/host/path；每次出站前重新解析 DNS 并拒绝 metadata、link-local、多播、保留地址及未放行私网。
- 禁止 URL 中的 userinfo/query/fragment，禁止自动重定向，HTTP 客户端固定 `trust_env=False`。

## 6. 管理 API（全部 admin-only）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/ai-models` | 列表；不返回 Key/密文 |
| GET | `/api/ai-models/providers` | provider 元数据 |
| POST | `/api/ai-models` | 新增，Key 为 write-only |
| PUT | `/api/ai-models/{id}` | 更新、替换或显式清除 Key；企业预设只接受 Key 与（对话模型的）思考强度 |
| POST | `/api/ai-models/{id}/test` | 使用生产同一 transport 测试；返回 `{status, error_code, message}` |
| POST | `/api/ai-models/{id}/activate` | 验证后原子切换 active；验证失败返回 400 `{error_code, message}` |
| DELETE | `/api/ai-models/{id}` | 软删除；active/企业预设模型禁止删除 |
| GET | `/api/ai-models/health` | 当前 chat/embedding 健康状态 |
| POST | `/api/ai-models/seed` | 幂等初始化本地默认模型 |

### 对话模型创建示例

```json
{
  "model_name": "qwen3.8",
  "model_type": "chat",
  "provider": "custom",
  "endpoint_url": "https://ai.gt-china.com.cn:10010/v1",
  "api_key": "sk-placeholder",
  "context_window": 262144,
  "reasoning_effort": null
}
```

### OCR 模型创建示例

```json
{
  "model_name": "paddleocrv6",
  "model_type": "ocr",
  "provider": "paddleocr",
  "endpoint_url": "https://ai.gt-china.com.cn:10080",
  "api_key": "gt-placeholder",
  "ocr_capability": "ocr",
  "ocr_protocol": "paddlex_json",
  "api_path": "/ocr",
  "auth_scheme": "bearer",
  "request_timeout_seconds": 60
}
```

`layout_parsing` 记录将 `model_name` 改为 `paddleocrvl-1.6`、`api_path` 改为 `/layout-parsing`、超时建议 120。

## 7. 故障排查

| 现象 | 判断 |
|---|---|
| 保存 Key 返回 503 | 未配置或无法使用 `ENCRYPTION_KEY` |
| 422“官方 API 域名” | provider 与 endpoint 不匹配；代理服务请选择 custom |
| 422“重新输入 API Key” | 修改了凭据目的地，安全策略禁止沿用旧 Key |
| 测试返回认证失败 | 检查 Key，并确认 OCR 的 Bearer/X-API-Key/api-key 选择 |
| OCR 返回 schema error | 内部网关响应并非 PaddleX Basic Serving 格式，需脱敏 fixture |
| 模型 256K 但只注入约 32K | `AI_CHAT_MAX_CONTEXT_TOKENS` 仍为平台独立预算 |
| 修改 `.env` 未生效 | `.env` 只在无 active row 时回退，且修改后需重启 |
| 测试/激活提示“TLS 握手被中断 / 连接被对端重置”且带 fake-IP 198.18.x.x | 本机代理/VPN 截获了企业域名，见下方「本机代理导致企业端点不可达」 |
| 测试提示“请求参数被拒绝；若该模型不支持思考强度…” | 服务端不接受 `reasoning_effort`，把思考强度改回「未指定」 |
| 测试提示“模型或 API 路径不存在” | 端点应以 `/v1` 结尾，且模型名与服务端 `/v1/models` 返回的 id 一致 |
| 远程 OCR 返回 HTTP 422（文件格式或尺寸不被接受） | PaddleX 拒绝了该文件（如 1x1 图片会被判 `Invalid input file`）；连接测试已改用 240x64 文字图 |

测试连接与激活返回的是稳定错误码 + 具体原因（不含上游正文与 Key）：`provider_unreachable`（附 TLS / 拒连 / DNS / fake-IP 判断）、`provider_timeout`、`provider_auth_failed`、`model_not_found`、`provider_error`、`invalid_response`；远程 OCR 对应 `ocr_unreachable`、`ocr_timeout`、`ocr_auth_failed` 等。

### 本机代理导致企业端点不可达（2026-10-19 实测）

`ai.gt-china.com.cn` 在公网 DNS 不存在（AliDNS / DNSPod / Cloudflare 均返回 NXDOMAIN），只能由公司内网 DNS 解析。开启 TUN + fake-IP 的代理客户端（Clash / mihomo / Mesl 等）会拦截所有 DNS 查询：先把域名映射为 `198.18.x.x` 并接下 TCP 连接，再用公网 DNS 解析真实地址，解析失败后直接关闭连接。于是平台、`curl`、浏览器都只看到 TLS 握手失败，与 Key 是否正确无关。代理日志里的特征是：

```text
dial DIRECT (match DomainSuffix/cn) ... --> ai.gt-china.com.cn:10010 error: dns resolve failed: couldn't find ip
```

**平台已自动兼容（默认开启，`LLM_FAKE_IP_COMPAT=true`）。** 对 allowlist 端点（含三条企业预设），当系统解析结果全部是 `198.18/15` 或解析失败时，后端绕过代理 DNS，向本机网卡配置的 DNS（公司 DNS）查询真实地址，再直连该地址；URL、Host 头、TLS SNI 与证书校验仍按 `ai.gt-china.com.cn`。查询顺序：TCP 直连 → 经本机代理 HTTP CONNECT（Mesl/Clash 的 strict-route 会拦截普通进程的 DNS，但不拦代理自己）→ UDP。结果按 DNS TTL 缓存（30~300 秒）。系统 DNS 正常返回真实地址时（服务器、无代理的电脑）完全走原路径。2026-10-19 在开着 Mesl 的开发机上实测：qwen3.8 测试 / 激活 / 真实对话、两条 OCR 测试均通过，无需改 hosts 或代理配置。

可选配置（`.env`，一般不需要）：

| 变量 | 作用 |
|---|---|
| `LLM_FAKE_IP_COMPAT` | 总开关，默认 `true` |
| `LLM_ENDPOINT_HOST_OVERRIDES` | 显式钉选 `域名=内网地址`（逗号分隔），只在被 fake-IP 劫持或解析失败时使用，仍按安全策略复核 |
| `LLM_UPSTREAM_DNS_SERVERS` | 指定用来查询真实地址的 DNS（逗号分隔 IP）；默认读取本机网卡配置 |
| `LLM_UPSTREAM_DNS_PROXY` | 指定本机 HTTP 代理（只接受环回地址，如 `http://127.0.0.1:7897`）；默认读取 `HTTP(S)_PROXY` 与 Windows 系统代理设置 |

边界：企业 AI 不对公网开放（公网 DNS 无记录，`gt-china.com.cn` 的公网 IP 上 10010/10080 不提供服务），离开公司网络又没有 VPN 时无论是否有代理都无法连通；此时测试连接会提示「公司 DNS 也没有该域名的记录：当前网络可能不在公司内网」。

自动兼容失败时的手工处理（任选其一）：

1. 在代理客户端的 DNS 覆写 / 自定义配置里把企业域名交给系统 DNS 并排除 fake-IP（订阅生成的 `runtime.yaml` 会被覆盖，请用客户端自带的覆写功能）：

   ```yaml
   dns:
     fake-ip-filter:
       - "+.gt-china.com.cn"
     nameserver-policy:
       "+.gt-china.com.cn": system
   rules:
     - DOMAIN-SUFFIX,gt-china.com.cn,DIRECT
   ```

2. 在系统 hosts 文件（`C:\Windows\System32\drivers\etc\hosts`，需管理员权限）写入公司内网 DNS 的解析结果：`<内网地址> ai.gt-china.com.cn`。内网地址可在不经代理 DNS 劫持的路径查询，例如 WSL 内向公司 DNS 发起查询。该地址若在 `10/8`、`172.16/12`、`192.168/16` 内，代理 TUN 默认不接管，连接会直连。缺点是写死了地址，IT 调整后需同步修改。
3. 临时关闭代理的 TUN 模式后再测试（会影响本机所有经代理的流量）。

自检：`Resolve-DnsName ai.gt-china.com.cn` 应返回公司内网地址而不是 `198.18.x.x`；`curl.exe -sS -o NUL -w "%{http_code}" https://ai.gt-china.com.cn:10010/v1/models` 返回 `401`（未带 Key）即说明网络已通，再回平台点“测试连接”。

## 8. 数据与合规提醒

远程 OCR 会将原始凭证/附件内容发送到配置的服务端。生产启用前应完成事务所内部的数据边界、留存、传输加密和供应商审批。平台不会记录 API Key、请求正文或完整上游错误响应；测试连接只发送合成数据。本文示例中的 `sk-placeholder` / `gt-placeholder` 均不是可用密钥，也不应提交真实 Key 到 Git。
