/**
 * 剪贴板工具函数（安全上下文回退）。
 *
 * `navigator.clipboard` 只在安全上下文（HTTPS / localhost）可用；
 * 内网 HTTP 部署时为 undefined，直接调用会 TypeError 或静默失败。
 *
 * spec: lan-http-insecure-context-compat R2
 */

/**
 * 复制文本到剪贴板。
 *
 * 优先 `navigator.clipboard.writeText`（安全上下文）；
 * 不可用时回退 `document.execCommand('copy')`（已废弃但仍被所有主流浏览器支持）。
 *
 * @returns 成功返回 `true`，失败返回 `false`（调用方决定是否提示用户）。
 */
export async function copyText(text: string): Promise<boolean> {
  // 优先 Clipboard API
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // 权限被拒或其他错误：继续尝试回退方案
    }
  }

  // 回退：execCommand('copy')
  try {
    const textarea = document.createElement('textarea')
    textarea.value = text
    // 放到屏幕外、不干扰布局
    textarea.style.cssText = 'position:fixed;left:-9999px;top:-9999px;opacity:0'
    document.body.appendChild(textarea)
    textarea.select()
    const ok = document.execCommand('copy')
    textarea.remove()
    return ok
  } catch {
    return false
  }
}

/**
 * 复制富文本（HTML + 纯文本）到剪贴板。
 *
 * 优先 `ClipboardItem`（安全上下文）；不可用时回退纯文本（`copyText`）。
 *
 * @param html HTML 格式的内容
 * @param text 纯文本格式的内容（回退用）
 * @returns `'rich'` 成功复制富文本，`'text'` 回退为纯文本，`false` 全部失败
 */
export async function copyRichText(html: string, text: string): Promise<'rich' | 'text' | false> {
  // ClipboardItem 只在安全上下文可用
  if (typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) {
    try {
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/html': new Blob([html], { type: 'text/html' }),
          'text/plain': new Blob([text], { type: 'text/plain' }),
        }),
      ])
      return 'rich'
    } catch {
      // 权限被拒：回退纯文本
    }
  }
  return (await copyText(text)) ? 'text' : false
}

/**
 * 从剪贴板读取文本。
 *
 * 只在安全上下文可用（`navigator.clipboard.readText` 还需要用户授权）。
 * 不可用时返回 `null`——调用方应显示「请使用 Ctrl+V 粘贴」提示。
 */
export async function readText(): Promise<string | null> {
  if (!navigator.clipboard?.readText) return null
  try {
    return await navigator.clipboard.readText()
  } catch {
    return null
  }
}
