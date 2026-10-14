/**
 * 生成 UUID v4（幂等键等）。
 *
 * `crypto.randomUUID` 只在安全上下文（HTTPS / localhost）可用；内网 HTTP 部署时为 undefined，
 * 直接调用会抛 TypeError ⇒ 回退 `getRandomValues` 拼 v4 形态，再不行才用 Math.random。
 * 不引入 `uuid` npm 包（R-23：package.json 未声明，靠传递依赖解析）。
 */
export function newUuid(): string {
  const c = globalThis.crypto as Crypto | undefined
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  const bytes = new Uint8Array(16)
  if (c && typeof c.getRandomValues === 'function') {
    c.getRandomValues(bytes)
  } else {
    for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256)
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
