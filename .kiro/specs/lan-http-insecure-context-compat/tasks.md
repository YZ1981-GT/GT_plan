# 内网 HTTP 非安全上下文兼容 — 任务

> spec: `lan-http-insecure-context-compat`

- [x] 1. 现状确认：grep `crypto.randomUUID` / `navigator.clipboard` / 其他安全上下文 API，逐个分类（裸调 / 已有回退 / 注释），确认 design §1 数字
- [x] 2. `crypto.randomUUID` 统一入口（R1）：84 处裸调 + 41 处已有回退全部改为 `newUuid()`；`newGenerationOperationId` 去掉 throw；AST 守卫 `cryptoRandomUuidBan.spec.ts`
- [x] 3. 剪贴板工具函数（R2）：新建 `clipboard.ts`（`copyText` / `readText`），38 处调用改用；AST 守卫 `clipboardDirectCallBan.spec.ts`
- [x] 4. 其他安全上下文 API 排查（R3）：`navigator.share` / `Notification` / `ServiceWorker` 等
- [x] 5. 单测 + 守卫验证 + 单区域 vue-tsc
- [x] 6. 浏览器实测（`http://192.168.20.60:3030`）：D4 增行、G7 新增投资成本行、复核对话发消息、公式复制 —— 全程无 TypeError
- [x] 7. 干净检出回归对比 HEAD、提交
