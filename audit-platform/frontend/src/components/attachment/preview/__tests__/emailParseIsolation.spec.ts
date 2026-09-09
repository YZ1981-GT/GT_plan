/**
 * 邮件解析资源门与异常隔离：底层解析器未知异常必须归一为 parse_failed，
 * 项目限额必须保留 limit，raw MIME 限额必须发生在 PostalMime 构造/parse 前。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  postalOptions: [] as unknown[],
  postalParse: vi.fn(),
  msgConstruct: vi.fn(),
  msgConstructError: null as Error | null,
  msgGetFileData: vi.fn(),
  msgGetAttachment: vi.fn(),
}))

vi.mock('postal-mime', () => ({
  default: class {
    constructor(options: unknown) {
      mocks.postalOptions.push(options)
    }

    parse(input: ArrayBuffer) {
      return mocks.postalParse(input)
    }
  },
}))

vi.mock('@kenjiuno/msgreader', () => ({
  default: class {
    constructor(input: ArrayBuffer) {
      mocks.msgConstruct(input)
      if (mocks.msgConstructError) throw mocks.msgConstructError
    }

    getFileData() {
      return mocks.msgGetFileData()
    }

    getAttachment(descriptor: unknown) {
      return mocks.msgGetAttachment(descriptor)
    }
  },
}))

import { EMAIL_LIMITS } from '../email/emailLimits'
import { parseEmailBytes } from '../email/emailParser'

const encode = (value: string) => new TextEncoder().encode(value).buffer
const emptyMail = () => ({ attachments: [], from: undefined, to: [], cc: [] })

function multipartWithTextParts(count: number): ArrayBuffer {
  const lines = [
    'MIME-Version: 1.0',
    'Content-Type: multipart/mixed; boundary="parts"',
    '',
  ]
  for (let index = 0; index < count; index += 1) {
    lines.push('--parts', 'Content-Type: text/plain', '', `body-${index}`)
  }
  lines.push('--parts--', '')
  return encode(lines.join('\r\n'))
}

beforeEach(() => {
  mocks.postalOptions.length = 0
  mocks.postalParse.mockReset().mockResolvedValue(emptyMail())
  mocks.msgConstruct.mockReset()
  mocks.msgConstructError = null
  mocks.msgGetFileData.mockReset().mockReturnValue({ attachments: [], recipients: [] })
  mocks.msgGetAttachment.mockReset()
})

describe('raw MIME 预扫与 PostalMime 限额', () => {
  it('root=1，499 个 text parts 可进入 PostalMime，501 个零附件 text parts 在构造/parse 前返回 limit', async () => {
    const atLimit = await parseEmailBytes(multipartWithTextParts(499), 'eml')
    expect(atLimit.status).toBe('ok')
    expect(mocks.postalParse).toHaveBeenCalledTimes(1)

    mocks.postalParse.mockClear()
    mocks.postalOptions.length = 0
    const overLimit = await parseEmailBytes(multipartWithTextParts(501), 'eml')
    expect(overLimit).toMatchObject({ status: 'limit', code: 'email_part_limit' })
    expect(mocks.postalOptions).toHaveLength(0)
    expect(mocks.postalParse).not.toHaveBeenCalled()
  })

  it('重复 Content-Type/参数与 quoted-pair boundary 不能让 501 parts 绕过预扫', async () => {
    const cases = [
      {
        headers: [
          'Content-Type: multipart/mixed; boundary="real"',
          'Content-Type: multipart/mixed; boundary="decoy"',
        ],
        boundary: 'real',
      },
      {
        headers: ['Content-Type: multipart/mixed; boundary="real"; boundary="decoy"'],
        boundary: 'real',
      },
      {
        headers: ['Content-Type: multipart/mixed; boundary="a\\b"'],
        boundary: 'ab',
      },
    ]

    for (const fixture of cases) {
      const lines = [...fixture.headers, '']
      for (let index = 0; index < 501; index += 1) {
        lines.push(`--${fixture.boundary}`, 'Content-Type: text/plain', '', `body-${index}`)
      }
      mocks.postalOptions.length = 0
      mocks.postalParse.mockClear()
      const result = await parseEmailBytes(encode(lines.join('\r\n')), 'eml')
      expect(result).toMatchObject({ status: 'limit', code: 'email_part_limit' })
      expect(mocks.postalOptions).toHaveLength(0)
      expect(mocks.postalParse).not.toHaveBeenCalled()
    }
  })

  it('累计 header bytes 超限时在 PostalMime 前返回 limit', async () => {
    const input = encode(`X-Fill: ${'a'.repeat(EMAIL_LIMITS.maxHeaderBytes)}\r\n\r\nbody`)
    const result = await parseEmailBytes(input, 'eml')
    expect(result).toMatchObject({ status: 'limit', code: 'email_header_limit' })
    expect(mocks.postalOptions).toHaveLength(0)
    expect(mocks.postalParse).not.toHaveBeenCalled()
  })

  it('declared boundary 超过 70 bytes 时在 PostalMime 前返回 limit', async () => {
    const boundary = 'b'.repeat(EMAIL_LIMITS.maxBoundaryBytes + 1)
    const result = await parseEmailBytes(encode(`Content-Type: multipart/mixed; boundary="${boundary}"\r\n\r\n`), 'eml')
    expect(result).toMatchObject({ status: 'limit', code: 'email_boundary_limit' })
    expect(mocks.postalOptions).toHaveLength(0)
    expect(mocks.postalParse).not.toHaveBeenCalled()
  })

  it('嵌套结构超过深度上限时在 PostalMime 前返回 limit', async () => {
    const lines = ['Content-Type: multipart/mixed; boundary="b0"', '']
    for (let index = 0; index < EMAIL_LIMITS.maxMimeNestingDepth; index += 1) {
      lines.push(`--b${index}`, `Content-Type: multipart/mixed; boundary="b${index + 1}"`, '')
    }
    const result = await parseEmailBytes(encode(lines.join('\r\n')), 'eml')
    expect(result).toMatchObject({ status: 'limit', code: 'email_nesting_limit' })
    expect(mocks.postalOptions).toHaveLength(0)
    expect(mocks.postalParse).not.toHaveBeenCalled()
  })

  it('显式配置 PostalMime 三项资源门，RFC822 递归深度为 0', async () => {
    const result = await parseEmailBytes(encode('From: a@x\r\n\r\nbody'), 'eml')
    expect(result.status).toBe('ok')
    expect(mocks.postalOptions).toEqual([{
      attachmentEncoding: 'arraybuffer',
      maxHeadersSize: EMAIL_LIMITS.maxHeaderBytes,
      maxNestingDepth: EMAIL_LIMITS.maxMimeNestingDepth,
      maxRfc822NestingDepth: 0,
    }])
  })

  it('PostalMime 已知限额异常保留 limit，未知异常才是 parse_failed', async () => {
    mocks.postalParse.mockRejectedValueOnce(
      new Error(`Maximum header size of ${EMAIL_LIMITS.maxHeaderBytes} bytes exceeded`),
    )
    const limited = await parseEmailBytes(encode('From: a@x\r\n\r\nbody'), 'eml')
    expect(limited).toMatchObject({ status: 'limit', code: 'email_header_limit' })

    mocks.postalParse.mockRejectedValueOnce(new Error('boom-postal-mime'))
    const failed = await parseEmailBytes(encode('From: a@x\r\n\r\nbody'), 'eml')
    expect(failed).toMatchObject({ status: 'parse_failed', message: 'boom-postal-mime' })
  })

  it('解析后二次 inline 字节门仍返回 limit，不降级为 parse_failed', async () => {
    mocks.postalParse.mockResolvedValueOnce({
      ...emptyMail(),
      attachments: [{
        filename: 'large.png',
        contentId: 'large@x',
        disposition: 'inline',
        mimeType: 'image/png',
        content: new Uint8Array(EMAIL_LIMITS.maxInlineRasterBytes + 1),
      }],
    })
    const result = await parseEmailBytes(encode('From: a@x\r\n\r\nbody'), 'eml')
    expect(result).toMatchObject({ status: 'limit', code: 'email_inline_raster_limit' })
  })
})

describe('MSG descriptor、recipient 与 CID 提取', () => {
  it('按 recipType 分 to/cc 并按 smtpAddress/email/name 回退，不产生 [object Object]', async () => {
    mocks.msgGetFileData.mockReturnValue({
      attachments: [],
      recipients: [
        { recipType: 'to', name: '收件人', smtpAddress: 'to@example.com' },
        { recipType: 'to', name: '空白SMTP', smtpAddress: '   ', email: 'fallback@example.com' },
        { recipType: 'to', name: '仅姓名' },
        { recipType: 'cc', name: '对象SMTP', smtpAddress: {}, email: 'cc@example.com' },
        { recipType: 'bcc', name: '密送', email: 'bcc@example.com' },
        { recipType: 'to' },
      ],
    })
    const result = await parseEmailBytes(new ArrayBuffer(8), 'msg')
    expect(result.status).toBe('ok')
    if (result.status !== 'ok') return
    expect(result.email.to).toEqual([
      '收件人 <to@example.com>',
      '空白SMTP <fallback@example.com>',
      '仅姓名',
    ])
    expect(result.email.cc).toEqual(['对象SMTP <cc@example.com>'])
    expect([...result.email.to, ...result.email.cc].join('')).not.toContain('[object Object]')
  })

  it('只对唯一 CID raster descriptor 取 bytes，并精确切出 Uint8Array 视图', async () => {
    const ordinary = { fileName: 'report.pdf', contentLength: 123, attachMimeTag: 'application/pdf' }
    const raster = {
      fileName: 'pixel.png',
      contentLength: 12,
      pidContentId: '<PIXEL@X>',
      attachMimeTag: 'image/png',
    }
    mocks.msgGetFileData.mockReturnValue({ attachments: [ordinary, raster], recipients: [] })
    const backing = new Uint8Array([9, 9, 0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0, 9])
    mocks.msgGetAttachment.mockReturnValue({ fileName: 'pixel.png', content: backing.subarray(2, 14) })

    const result = await parseEmailBytes(new ArrayBuffer(8), 'msg')
    expect(result.status).toBe('ok')
    if (result.status !== 'ok') return
    expect(mocks.msgGetAttachment).toHaveBeenCalledTimes(1)
    expect(mocks.msgGetAttachment).toHaveBeenCalledWith(raster)
    expect(result.email.attachments).toHaveLength(2)
    expect(result.email.inlineParts).toHaveLength(1)
    expect(result.email.inlineParts[0]).toMatchObject({ canonicalCid: 'pixel@x', declaredMime: 'image/png' })
    expect(result.email.inlineParts[0].bytes.byteLength).toBe(12)
    expect(new Uint8Array(result.email.inlineParts[0].bytes)[0]).toBe(0x89)
  })

  it('magic 与 declared MIME 不一致时不产生 inline part', async () => {
    const raster = {
      fileName: 'wrong.jpg',
      contentLength: 8,
      pidContentId: 'wrong@x',
      attachMimeTag: 'image/jpeg',
    }
    mocks.msgGetFileData.mockReturnValue({ attachments: [raster], recipients: [] })
    mocks.msgGetAttachment.mockReturnValue({
      fileName: 'wrong.jpg',
      content: new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0, 0, 0, 0]),
    })
    const result = await parseEmailBytes(new ArrayBuffer(8), 'msg')
    expect(result.status).toBe('ok')
    if (result.status !== 'ok') return
    expect(result.email.inlineParts).toEqual([])
  })

  it('仅匹配 PNG 短前缀但完整 signature 错误时拒绝 inline part', async () => {
    const raster = {
      fileName: 'near.png',
      contentLength: 8,
      pidContentId: 'near@x',
      attachMimeTag: 'image/png',
    }
    mocks.msgGetFileData.mockReturnValue({ attachments: [raster], recipients: [] })
    mocks.msgGetAttachment.mockReturnValue({
      fileName: 'near.png',
      content: new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0, 0, 0, 0]),
    })
    const result = await parseEmailBytes(new ArrayBuffer(8), 'msg')
    expect(result.status).toBe('ok')
    if (result.status !== 'ok') return
    expect(result.email.inlineParts).toEqual([])
  })

  it('重复 CID 全部剔除，且不为歧义项取 bytes', async () => {
    const first = { pidContentId: '<dup@x>', attachMimeTag: 'image/png', contentLength: 8 }
    const second = { pidContentId: 'DUP@X', attachMimeTag: 'image/png', contentLength: 8 }
    mocks.msgGetFileData.mockReturnValue({ attachments: [first, second], recipients: [] })
    const result = await parseEmailBytes(new ArrayBuffer(8), 'msg')
    expect(result.status).toBe('ok')
    if (result.status !== 'ok') return
    expect(result.email.ambiguousCids).toEqual(['dup@x'])
    expect(result.email.inlineParts).toEqual([])
    expect(mocks.msgGetAttachment).not.toHaveBeenCalled()
  })

  it('顶层与 embedded attachment descriptor 累计有界', async () => {
    const nested = Array.from({ length: EMAIL_LIMITS.maxParts }, () => ({}))
    mocks.msgGetFileData.mockReturnValue({
      attachments: [{ innerMsgContentFields: { attachments: nested } }],
      recipients: [],
    })
    const result = await parseEmailBytes(new ArrayBuffer(8), 'msg')
    expect(result).toMatchObject({ status: 'limit', code: 'email_part_limit' })
    expect(mocks.msgGetAttachment).not.toHaveBeenCalled()
  })

  it('MSG inline descriptor/实际字节超限保留 limit', async () => {
    const raster = {
      pidContentId: 'large@x',
      attachMimeTag: 'image/png',
      contentLength: EMAIL_LIMITS.maxInlineRasterBytes + 1,
    }
    mocks.msgGetFileData.mockReturnValue({ attachments: [raster], recipients: [] })
    const result = await parseEmailBytes(new ArrayBuffer(8), 'msg')
    expect(result).toMatchObject({ status: 'limit', code: 'email_inline_raster_limit' })
    expect(mocks.msgGetAttachment).not.toHaveBeenCalled()
  })

  it('MSGReader 错误/未知异常归一为 parse_failed，不 reject', async () => {
    mocks.msgGetFileData.mockReturnValueOnce({ error: 'bad-msg' })
    const reported = await parseEmailBytes(new ArrayBuffer(8), 'msg')
    expect(reported).toMatchObject({ status: 'parse_failed', message: 'bad-msg' })

    mocks.msgConstructError = new Error('boom-msgreader')
    const thrown = await parseEmailBytes(new ArrayBuffer(8), 'msg')
    expect(thrown).toMatchObject({ status: 'parse_failed', message: 'boom-msgreader' })
  })
})
