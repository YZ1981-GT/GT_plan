# 内网 HTTP 非安全上下文兼容 — 设计

> spec: `lan-http-insecure-context-compat`

## §1 现状（2026-10-31 grep）

| API | 文件数 | 调用数 | 裸调（无回退） | 已有回退 |
|-----|--------|--------|----------------|----------|
| `crypto.randomUUID()` | 99 | 180 | 84 | 41 |
| `navigator.clipboard` | 26 | 38 | 待逐个判断 | — |
| `newGenerationOperationId` (throw) | 2 | — | 1 (定义) | — |
| `navigator.locks` | 1 | — | 0（`clientInstance.ts` 已处理） | 1 |

裸调形态举例：
- `id: crypto.randomUUID()` — G7 投资成本、控制判断、未确认损失；内网 http 下新增行即 TypeError
- `const tempId = crypto.randomUUID()` — 复核对话；内网 http 下发消息即 TypeError
- `navigator.clipboard.writeText(text)` — 公式复制、地址复制、编号复制；内网 http 下无提示、静默失败

## §2 D1 `newUuid` 统一入口

`utils/uuid.ts` 已有 `newUuid()`：`crypto.randomUUID` → `crypto.getRandomValues` 拼 v4 → `Math.random` 拼。

改动：
1. 全仓 84 处裸调改为 `import { newUuid } from '@/utils/uuid'` + `newUuid()`。
2. 41 处已有回退的改为 `newUuid()`（去掉各自的回退代码，减少重复）。
3. `generationOperationStore.newGenerationOperationId` 改用 `newUuid()`，去掉 throw。

守卫：AST 扫描守卫 `cryptoRandomUuidBan.spec.ts`——在 `src/**/*.{ts,vue}` 非测试文件中搜索 `crypto.randomUUID`，只允许 `uuid.ts` 里出现。

## §3 D2 剪贴板工具函数

新建 `utils/clipboard.ts`：

```ts
export async function copyText(text: string): Promise<boolean>
export async function readText(): Promise<string | null>
```

- `copyText`：`navigator.clipboard?.writeText` 优先；不可用时创建隐藏 `<textarea>`、`document.execCommand('copy')`；成功返回 `true`，失败返回 `false`（调用方决定是否提示）。
- `readText`：`navigator.clipboard?.readText` 优先；不可用时返回 `null`（调用方显示「请 Ctrl+V」提示）。

守卫：AST 扫描守卫 `clipboardDirectCallBan.spec.ts`——在 `src/**/*.{ts,vue}` 非测试文件中搜索 `navigator.clipboard`，只允许 `clipboard.ts` 里出现。

## §4 D3 其他安全上下文 API 排查

逐个 grep：
- `navigator.locks` — 已在 `clientInstance.ts` 处理 ✅
- `navigator.share` / `navigator.credentials` / `Notification` / `PushManager` / `ServiceWorker` — 预计不用或不存在

## §5 涉及文件

**新建**：
- `audit-platform/frontend/src/utils/clipboard.ts`
- `audit-platform/frontend/src/utils/__tests__/cryptoRandomUuidBan.spec.ts`
- `audit-platform/frontend/src/utils/__tests__/clipboardDirectCallBan.spec.ts`

**改动**：
- 约 99 个文件的 `crypto.randomUUID` 调用
- 约 26 个文件的 `navigator.clipboard` 调用
- `services/generationOperationStore.ts`

## §6 风险

- 改动面广（~125 文件）但每处改动极小（换一个函数调用），逐文件变异验证不现实，靠 AST 守卫 + 内网 IP 浏览器实测。
- `document.execCommand('copy')` 已废弃但仍被所有主流浏览器支持，是非安全上下文下唯一的剪贴板写入方案。
