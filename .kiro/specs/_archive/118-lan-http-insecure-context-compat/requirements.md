# 内网 HTTP 非安全上下文兼容 — 需求

> spec: `lan-http-insecure-context-compat`

## 背景

平台部署在内网时用户通过 `http://<内网 IP>:3030` 访问（非 localhost），浏览器不认为是安全上下文（Secure Context）。
以下 Web API 只在安全上下文可用，当前代码 **84 处裸调 `crypto.randomUUID()`**（无回退）、**38 处 `navigator.clipboard`**、
`newGenerationOperationId` 直接 throw。2026-10-31 `workpaper-multi-window-lock-gaps` 实测已修了 `clientInstance.ts` 和 `uuid.ts`，
但其余调用点仍在，用户打开对应底稿即 TypeError / 功能静默失效。

## 需求

### R1 `crypto.randomUUID` 统一入口

- R1.1 全仓前端代码（`src/**/*.{ts,vue}`，非测试）的 UUID 生成统一走 `utils/uuid.ts` 的 `newUuid()`（已有回退）。
- R1.2 禁止裸调 `crypto.randomUUID()`：ESLint 自定义规则或 AST 守卫在 CI / pre-commit 卡点。
- R1.3 `newGenerationOperationId` 改用 `newUuid()` + 前缀，去掉 throw。

### R2 `navigator.clipboard` 回退

- R2.1 剪贴板写入（`writeText`）统一走一个工具函数：优先 `navigator.clipboard.writeText`，不可用时回退 `document.execCommand('copy')`。
- R2.2 剪贴板读取（`readText`）：仅在安全上下文可用，不可用时给用户中文提示「请使用 Ctrl+V 粘贴」。
- R2.3 现有 38 处调用点全部改用工具函数。

### R3 其他安全上下文 API

- R3.1 排查 `navigator.locks`（已在 `clientInstance.ts` 处理）、`navigator.share`、`navigator.credentials`、`Notification`、
  `PushManager`、`ServiceWorker` 等在前端代码中的调用，逐个评估是否需要回退或提示。

### 非目标

- 不把平台改成 HTTPS 部署（那是运维侧的事，本 spec 只解决代码层面的回退）。
- 不改后端代码（后端不受安全上下文影响）。
