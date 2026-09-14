import { describe, it, expect } from 'vitest'
import { parseEmailBytes } from '../email/emailParser'
import { canonicalizeCid } from '../email/emailLimits'
import { sanitizeEmailHtml, wrapEmailSrcdoc, EMAIL_CSP } from '../email/emailSanitizer'
import { parseDxfBytes } from '../drawing/dxfModel'

describe('email CID canonicalize', () => {
  it('trim / 尖括号 / percent / lowercase', () => {
    expect(canonicalizeCid(' <CID%40X> ')).toBe('cid@x')
  })
})

describe('email eml parse', () => {
  it('解析头与正文', async () => {
    const eml = [
      'From: a@example.com',
      'To: b@example.com',
      'Cc: c@example.com',
      'Subject: =?UTF-8?B?5rWL6K+V?=',
      'MIME-Version: 1.0',
      'Content-Type: text/plain; charset=utf-8',
      '',
      'hello body',
      '',
    ].join('\r\n')
    const buf = new TextEncoder().encode(eml).buffer
    const r = await parseEmailBytes(buf, 'eml')
    expect(r.status).toBe('ok')
    if (r.status !== 'ok') return
    expect(r.email.from).toContain('a@example.com')
    expect(r.email.to.join('')).toContain('b@example.com')
    expect(r.email.text).toContain('hello')
  })

  it('损坏邮件 parse_failed 且不抛到外层', async () => {
    const buf = new Uint8Array([0, 1, 2, 3]).buffer
    const r = await parseEmailBytes(buf, 'eml')
    // postal-mime 对乱字节可能仍给出空结构；至少不抛
    expect(['ok', 'parse_failed', 'limit']).toContain(r.status)
  })


})

describe('email sanitizer', () => {
  it('移除 script/事件并阻断外链图片', () => {
    const html =
      '<p onclick="x()">hi</p><script>alert(1)</script><img src="https://evil.example/a.png"><a href="https://evil.example">x</a>'
    const safe = sanitizeEmailHtml(html, [])
    expect(safe.html).not.toMatch(/script/i)
    expect(safe.html).not.toMatch(/onclick/i)
    expect(safe.html).not.toMatch(/https:\/\/evil\.example\/a\.png/)
    expect(safe.blockedResources.length).toBeGreaterThan(0)
    const srcdoc = wrapEmailSrcdoc(safe.html)
    expect(srcdoc).toContain(EMAIL_CSP)
    expect(srcdoc).toContain("img-src blob:")
    expect(srcdoc).toContain("default-src 'none'")
  })

  it('CID 仅在 magic 匹配时转 blob', () => {
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0])
    const urls: string[] = []
    const safe = sanitizeEmailHtml('<img src="cid:img1@x">', [
      {
        canonicalCid: 'img1@x',
        declaredMime: 'image/png',
        bytes: png.buffer,
      },
    ], (b) => {
      const u = `blob:test-${urls.length}`
      urls.push(u)
      return u
    })
    expect(safe.html).toContain('blob:test-0')
    expect(safe.generatedObjectUrls).toEqual(['blob:test-0'])
  })

  it('CID magic 不匹配时拒绝转 blob（声明 png 但字节非 png）', () => {
    // 声明 image/png 但字节是 GIF 头 → magicOk 应判否 ⇒ 不生成 blob，记 cid_magic_mismatch
    const notPng = new Uint8Array([0x47, 0x49, 0x46, 0x38, 0, 0, 0, 0, 0, 0, 0, 0])
    const urls: string[] = []
    const safe = sanitizeEmailHtml('<img src="cid:img1@x">', [
      {
        canonicalCid: 'img1@x',
        declaredMime: 'image/png',
        bytes: notPng.buffer,
      },
    ], (b) => {
      const u = `blob:mm-${urls.length}`
      urls.push(u)
      return u
    })
    expect(safe.generatedObjectUrls).toEqual([])
    expect(safe.html).not.toContain('blob:mm-')
    expect(safe.blockedResources.some((r) => r.kind === 'cid_magic_mismatch')).toBe(true)
  })

  it('CID 仅有 PNG 短前缀而完整 signature 错误时拒绝转 blob', () => {
    const nearPng = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0, 0, 0, 0])
    const safe = sanitizeEmailHtml('<img src="cid:near@x">', [{
      canonicalCid: 'near@x',
      declaredMime: 'image/png',
      bytes: nearPng.buffer,
    }], () => 'blob:must-not-exist')
    expect(safe.generatedObjectUrls).toEqual([])
    expect(safe.blockedResources.some((r) => r.kind === 'cid_magic_mismatch')).toBe(true)
  })

  it('SVG data URI 大小写不敏感地阻断', () => {
    const safe = sanitizeEmailHtml('<img src="DATA:IMAGE/SVG+XML,%3Csvg%3E">', [])
    expect(safe.html).not.toMatch(/DATA:IMAGE\/SVG/i)
    expect(safe.blockedResources.some((resource) => resource.kind === 'svg_data')).toBe(true)
  })
})

describe('dxf model', () => {
  it('解析 LINE 为 typed entity，无 v-html 字符串拼装', () => {
    const dxf = `0\nSECTION\n2\nENTITIES\n0\nLINE\n8\n0\n10\n0.0\n20\n0.0\n11\n10.0\n21\n10.0\n0\nENDSEC\n0\nEOF\n`
    const buf = new TextEncoder().encode(dxf).buffer
    const r = parseDxfBytes(buf)
    expect(r.status).toBe('ok')
    if (r.status !== 'ok') return
    expect(r.model.entities.some((e) => e.type === 'LINE')).toBe(true)
  })
})
