/**
 * 私有 Email_Sanitizer + CID magic 门
 * Spec Task 9（安全模型；UI 切换在 Task 12）
 */
import DOMPurify from 'dompurify'
import { canonicalizeCid, detectRasterMime } from './emailLimits'
import type { ParsedInlinePart } from './emailParser'

export const EMAIL_CSP = [
  "default-src 'none'",
  "img-src blob: data:",
  "style-src 'unsafe-inline'",
  "font-src 'none'",
  "media-src 'none'",
  "connect-src 'none'",
  "frame-src 'none'",
  "form-action 'none'",
  "base-uri 'none'",
].join('; ')

export interface BlockedResource {
  kind: string
  host?: string
}

export interface SafeEmailBody {
  html: string
  blockedResources: BlockedResource[]
  generatedObjectUrls: string[]
}

const ALLOWED_TAGS = [
  'a', 'b', 'br', 'blockquote', 'code', 'div', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'hr', 'i', 'img', 'li', 'ol', 'p', 'pre', 'span', 'strong', 'table', 'tbody', 'td', 'th', 'thead', 'tr', 'u', 'ul',
]

const ALLOWED_ATTR = ['href', 'src', 'alt', 'title', 'colspan', 'rowspan', 'width', 'height']

function hostOf(url: string): string | undefined {
  try {
    if (url.startsWith('//')) return new URL(`https:${url}`).host
    return new URL(url).host
  } catch {
    return undefined
  }
}

function magicOk(bytes: ArrayBuffer, declaredMime: string): boolean {
  return detectRasterMime(bytes) === declaredMime.toLowerCase()
}

export function sanitizeEmailHtml(
  html: string | null | undefined,
  inlineParts: ParsedInlinePart[],
  createObjectUrl: (blob: Blob) => string = (b) => URL.createObjectURL(b),
): SafeEmailBody {
  const blockedResources: BlockedResource[] = []
  const generatedObjectUrls: string[] = []
  if (!html) return { html: '', blockedResources, generatedObjectUrls }

  const cidMap = new Map<string, ParsedInlinePart>()
  const ambiguousCids = new Set<string>()
  for (const p of inlineParts) {
    if (!magicOk(p.bytes, p.declaredMime)) {
      blockedResources.push({ kind: 'cid_magic_mismatch' })
      continue
    }
    if (ambiguousCids.has(p.canonicalCid)) continue
    if (cidMap.has(p.canonicalCid)) {
      blockedResources.push({ kind: 'cid_ambiguous', host: p.canonicalCid })
      cidMap.delete(p.canonicalCid)
      ambiguousCids.add(p.canonicalCid)
      continue
    }
    cidMap.set(p.canonicalCid, p)
  }

  const purify = DOMPurify(window as any)
  let svgDataRecorded = false
  const blockSvgData = () => {
    if (!svgDataRecorded) blockedResources.push({ kind: 'svg_data' })
    svgDataRecorded = true
  }
  const attributeHook = (_node: Element, data: { attrName?: string; attrValue?: string; keepAttr?: boolean }) => {
    if (
      data.attrName?.toLowerCase() === 'src' &&
      /^data:image\/svg(?:\+xml)?(?:[;,]|$)/i.test(String(data.attrValue || '').trimStart())
    ) {
      blockSvgData()
      data.keepAttr = false
    }
  }

  const hook = (node: Element) => {
    if (!(node instanceof Element)) return
    const tag = node.tagName.toLowerCase()
    if (tag === 'a') {
      const href = node.getAttribute('href') || ''
      if (/^https?:/i.test(href) || href.startsWith('//')) {
        blockedResources.push({ kind: 'external_link', host: hostOf(href) })
        const label = document.createElement('span')
        label.textContent = `[链接: ${hostOf(href) || href}]`
        node.replaceWith(label)
        return
      }
      node.removeAttribute('href')
    }
    if (tag === 'img') {
      const src = node.getAttribute('src') || ''
      if (/^cid:/i.test(src)) {
        const cid = canonicalizeCid(src.slice(4))
        const part = cid ? cidMap.get(cid) : null
        if (!part) {
          blockedResources.push({ kind: 'cid_missing' })
          node.replaceWith(document.createElement('span'))
          return
        }
        const url = createObjectUrl(new Blob([part.bytes], { type: part.declaredMime }))
        generatedObjectUrls.push(url)
        node.setAttribute('src', url)
        return
      }
      if (/^https?:/i.test(src) || src.startsWith('//') || /^data:text\/html/i.test(src)) {
        blockedResources.push({ kind: 'remote_img', host: hostOf(src) })
        node.removeAttribute('src')
        return
      }
      if (/^data:image\/svg(?:\+xml)?(?:[;,]|$)/i.test(src.trimStart())) {
        blockSvgData()
        node.removeAttribute('src')
      }
    }
    // 清掉自动加载属性
    for (const attr of [...node.attributes]) {
      const n = attr.name.toLowerCase()
      if (n.startsWith('on') || n === 'srcset' || n === 'poster' || n === 'style' || n === 'background') {
        node.removeAttribute(attr.name)
      }
    }
  }

  purify.addHook('uponSanitizeAttribute', attributeHook as any)
  purify.addHook('afterSanitizeAttributes', hook as any)
  try {
    const clean = purify.sanitize(html, {
      ALLOWED_TAGS,
      ALLOWED_ATTR,
      FORBID_TAGS: [
        'script', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'select', 'textarea',
        'link', 'meta', 'base', 'style', 'audio', 'video', 'source', 'picture', 'svg', 'math',
      ],
      FORBID_ATTR: ['srcset', 'poster', 'style', 'background', 'formaction'],
      ALLOW_DATA_ATTR: false,
    }) as string

    // FORBID 掉的外链/iframe 汇总：用粗略扫描原文补充
    for (const m of html.matchAll(/<(iframe|link|script|object|embed)\b[^>]*>/gi)) {
      blockedResources.push({ kind: `forbid_${m[1].toLowerCase()}` })
    }
    for (const m of html.matchAll(/\b(?:src|href)\s*=\s*["'](https?:\/\/[^"']+|\/\/[^"']+)["']/gi)) {
      blockedResources.push({ kind: 'external_url_scan', host: hostOf(m[1]) })
    }

    return { html: clean, blockedResources, generatedObjectUrls }
  } finally {
    purify.removeHook('uponSanitizeAttribute')
    purify.removeHook('afterSanitizeAttributes')
  }
}

export function wrapEmailSrcdoc(safeHtml: string): string {
  return `<!DOCTYPE html><html><head><meta http-equiv="Content-Security-Policy" content="${EMAIL_CSP}"></head><body>${safeHtml}</body></html>`
}
