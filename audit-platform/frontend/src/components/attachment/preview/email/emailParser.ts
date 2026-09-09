/**
 * eml/msg → 归一 ParsedEmail
 */
import PostalMime from 'postal-mime'
import MsgReader from '@kenjiuno/msgreader'
import {
  EMAIL_LIMITS,
  canonicalizeCid,
  detectRasterMime,
  type EmailLimitError,
} from './emailLimits'

export interface ParsedEmailAttachment {
  filename: string
  size: number
  contentId: string | null
}

export interface ParsedInlinePart {
  canonicalCid: string
  declaredMime: string
  bytes: ArrayBuffer
}

export interface ParsedEmail {
  from: string
  to: string[]
  cc: string[]
  subject: string
  date: string | null
  html: string | null
  text: string | null
  attachments: ParsedEmailAttachment[]
  inlineParts: ParsedInlinePart[]
  ambiguousCids: string[]
}

export type EmailParseResult =
  | { status: 'ok'; email: ParsedEmail }
  | { status: 'limit'; code: EmailLimitError; message: string }
  | { status: 'parse_failed'; message: string }

const LIMIT_CODES = new Set<EmailLimitError>([
  'email_input_limit',
  'email_part_limit',
  'email_header_limit',
  'email_boundary_limit',
  'email_nesting_limit',
  'email_inline_raster_limit',
  'email_inline_total_limit',
])

const RASTER_MIMES = new Set(['image/png', 'image/jpeg', 'image/gif', 'image/webp'])
const latin1 = new TextDecoder('latin1')

type BoundaryScope = { value: string; ownerDepth: number }

function limitResult(code: EmailLimitError): EmailParseResult {
  return { status: 'limit', code, message: code }
}

function throwLimit(code: EmailLimitError): never {
  throw Object.assign(new Error(code), { code })
}

function limitCodeOf(error: unknown): EmailLimitError | null {
  if (error && typeof error === 'object' && 'code' in error) {
    const code = String((error as { code?: unknown }).code || '') as EmailLimitError
    if (LIMIT_CODES.has(code)) return code
  }
  const message = error instanceof Error ? error.message : ''
  if (/^Maximum header size of \d+ bytes exceeded$/.test(message)) return 'email_header_limit'
  if (/^Maximum MIME nesting depth of \d+ levels exceeded$/.test(message)) {
    return 'email_nesting_limit'
  }
  return null
}

function sniffExt(buf: ArrayBuffer): 'eml' | 'msg' {
  const u8 = new Uint8Array(buf)
  // OLE compound: D0 CF 11 E0
  if (u8.length >= 4 && u8[0] === 0xd0 && u8[1] === 0xcf && u8[2] === 0x11 && u8[3] === 0xe0) {
    return 'msg'
  }
  return 'eml'
}

function firstNonEmptyString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return ''
}

function formatNameAddress(nameValue: unknown, addressValue: unknown): string {
  const name = firstNonEmptyString(nameValue)
  const address = firstNonEmptyString(addressValue)
  if (name && address && name.toLowerCase() !== address.toLowerCase()) return `${name} <${address}>`
  return address || name
}

function asList(v: unknown): string[] {
  if (!v) return []
  if (Array.isArray(v)) {
    return v.flatMap((x) => {
      if (typeof x === 'string') return x ? [x] : []
      if (!x || typeof x !== 'object') return []
      const value = x as { name?: unknown; address?: unknown; group?: unknown }
      if (Array.isArray(value.group)) return asList(value.group)
      const formatted = formatNameAddress(value.name, value.address)
      return formatted ? [formatted] : []
    })
  }
  if (typeof v === 'string') return v ? [v] : []
  return []
}

function exactArrayBuffer(value: unknown): ArrayBuffer | null {
  if (value instanceof ArrayBuffer) return value
  if (ArrayBuffer.isView(value)) {
    const view = value as ArrayBufferView
    return view.buffer.slice(view.byteOffset, view.byteOffset + view.byteLength) as ArrayBuffer
  }
  return null
}

function stripMimeComments(value: string): string {
  let result = ''
  let depth = 0
  let escaped = false
  let quoted = false
  let commentStart = -1
  let inParameterValue = false
  const opensComment = () => !inParameterValue || !result.length || /[ \t]$/.test(result)

  for (let index = 0; index < value.length; index += 1) {
    const character = value[index]
    if (escaped) {
      if (depth === 0) result += character
      escaped = false
      continue
    }
    if (character === '\\') {
      escaped = true
      if (depth === 0) result += character
      continue
    }
    if (character === '"' && depth === 0) {
      quoted = !quoted
      result += character
      continue
    }
    if (!quoted) {
      if (character === '(' && opensComment()) {
        if (depth === 0) commentStart = index
        depth += 1
        continue
      }
      if (character === ')' && depth > 0) {
        depth -= 1
        continue
      }
      if (depth === 0) {
        if (character === '=') inParameterValue = true
        else if (character === ';') inParameterValue = false
      }
    }
    if (depth === 0) result += character
  }

  if (depth === 0) return result
  return value.indexOf(';', commentStart) < 0 ? result : value
}

function firstBoundaryParameter(contentType: string): string | null {
  const value = stripMimeComments(contentType)
  const mediaType = value.split(';', 1)[0].trim().toLowerCase()
  if (!mediaType.startsWith('multipart/')) return null
  const match = value.match(/(?:^|;)\s*boundary\s*=\s*(?:"((?:\\.|[^"])*)"?|([^;\s]*))/i)
  if (!match) return null
  if (match[1] !== undefined) return match[1].replace(/\\(.)/g, '$1')
  return (match[2] || '').trim()
}

/**
 * MIME 资源预扫：逐 byte 前进一次；boundary 查找为 Map O(1)，活跃栈深受硬上限约束。
 * 仅解码累计受限的 header 和长度至多 maxBoundaryBytes 的 delimiter 候选行。
 */
function preScanRawMime(input: ArrayBuffer): EmailLimitError | null {
  const bytes = new Uint8Array(input)
  const scopes: BoundaryScope[] = []
  const positions = new Map<string, number[]>()
  let partCount = 1 // root entity
  let currentDepth = 1
  let headerBytes = 0
  let inHeaders = true
  let currentHeaderName = ''
  let currentHeaderValueParts: string[] = []
  let seenContentType = false
  let pendingBoundary: string | null = null

  const truncateScopes = (length: number) => {
    while (scopes.length > length) {
      const removed = scopes.pop()!
      const indexes = positions.get(removed.value)!
      indexes.pop()
      if (indexes.length === 0) positions.delete(removed.value)
    }
  }

  const pushScope = (value: string) => {
    const index = scopes.length
    scopes.push({ value, ownerDepth: currentDepth })
    const indexes = positions.get(value) || []
    indexes.push(index)
    positions.set(value, indexes)
  }

  const flushHeader = (): EmailLimitError | null => {
    if (currentHeaderName === 'content-type' && !seenContentType) {
      seenContentType = true
      const boundary = firstBoundaryParameter(currentHeaderValueParts.join('').trim())
      if (boundary) {
        if (boundary.length > EMAIL_LIMITS.maxBoundaryBytes) return 'email_boundary_limit'
        pendingBoundary = boundary
      }
    }
    currentHeaderName = ''
    currentHeaderValueParts = []
    return null
  }

  let offset = 0
  while (offset < bytes.length) {
    const lineStart = offset
    while (offset < bytes.length && bytes[offset] !== 0x0a && bytes[offset] !== 0x0d) offset += 1
    const lineEnd = offset
    if (offset < bytes.length && bytes[offset] === 0x0d) offset += 1
    if (offset < bytes.length && bytes[offset] === 0x0a) offset += 1
    const rawLineBytes = offset - lineStart
    const line = bytes.subarray(lineStart, lineEnd)

    if (inHeaders) {
      headerBytes += rawLineBytes
      if (headerBytes > EMAIL_LIMITS.maxHeaderBytes) return 'email_header_limit'
      if (line.length === 0) {
        const code = flushHeader()
        if (code) return code
        if (pendingBoundary) {
          pushScope(pendingBoundary)
          pendingBoundary = null
        }
        inHeaders = false
        continue
      }
      const continuation = line[0] === 0x20 || line[0] === 0x09
      if (continuation && currentHeaderName) {
        if (currentHeaderName === 'content-type') currentHeaderValueParts.push(latin1.decode(line))
        continue
      }
      const code = flushHeader()
      if (code) return code
      const decoded = latin1.decode(line)
      const colon = decoded.indexOf(':')
      if (colon > 0) {
        currentHeaderName = decoded.slice(0, colon).trim().toLowerCase()
        currentHeaderValueParts = currentHeaderName === 'content-type'
          ? [decoded.slice(colon + 1).trim()]
          : []
      }
      continue
    }

    // RFC delimiter 为 "--" + 70-byte boundary + "--"，尾部 LWSP 可任意长但不参与 token。
    if (line.length < 3 || line[0] !== 0x2d || line[1] !== 0x2d) continue
    let markerEnd = line.length
    while (markerEnd > 2 && (line[markerEnd - 1] === 0x20 || line[markerEnd - 1] === 0x09)) markerEnd -= 1
    if (markerEnd > EMAIL_LIMITS.maxBoundaryBytes + 4) continue
    const closing = markerEnd >= 4 && line[markerEnd - 1] === 0x2d && line[markerEnd - 2] === 0x2d
    const valueEnd = closing ? markerEnd - 2 : markerEnd
    const boundary = latin1.decode(line.subarray(2, valueEnd))
    const indexes = positions.get(boundary)
    if (!indexes?.length) continue
    const scopeIndex = indexes[indexes.length - 1]

    if (closing) {
      truncateScopes(scopeIndex)
      continue
    }

    truncateScopes(scopeIndex + 1)
    partCount += 1
    if (partCount > EMAIL_LIMITS.maxParts) return 'email_part_limit'
    currentDepth = scopes[scopeIndex].ownerDepth + 1
    if (currentDepth > EMAIL_LIMITS.maxMimeNestingDepth) return 'email_nesting_limit'
    inHeaders = true
    currentHeaderName = ''
    currentHeaderValueParts = []
    seenContentType = false
    pendingBoundary = null
  }

  if (inHeaders) return flushHeader()
  return null
}

export async function parseEmailBytes(input: ArrayBuffer, hintExt?: string): Promise<EmailParseResult> {
  if (input.byteLength > EMAIL_LIMITS.maxInputBytes) return limitResult('email_input_limit')
  const kind = hintExt === 'msg' || hintExt === 'eml' ? hintExt : sniffExt(input)
  try {
    if (kind === 'msg') return parseMsg(input)
    return await parseEml(input)
  } catch (error) {
    const code = limitCodeOf(error)
    if (code) return limitResult(code)
    return { status: 'parse_failed', message: error instanceof Error ? error.message : 'parse_failed' }
  }
}

async function parseEml(input: ArrayBuffer): Promise<EmailParseResult> {
  const scanLimit = preScanRawMime(input)
  if (scanLimit) return limitResult(scanLimit)

  const parser = new PostalMime({
    attachmentEncoding: 'arraybuffer',
    maxHeadersSize: EMAIL_LIMITS.maxHeaderBytes,
    maxNestingDepth: EMAIL_LIMITS.maxMimeNestingDepth,
    maxRfc822NestingDepth: EMAIL_LIMITS.maxRfc822NestingDepth,
  })
  const mail = await parser.parse(input)
  const mailAttachments = Array.isArray(mail.attachments) ? mail.attachments : []
  if (mailAttachments.length > EMAIL_LIMITS.maxParts) return limitResult('email_part_limit')

  const attachments: ParsedEmailAttachment[] = []
  const inlineParts: ParsedInlinePart[] = []
  const cidCount = new Map<string, number>()
  let inlineRasterBytes = 0

  for (const att of mailAttachments) {
    const filename = att.filename || att.contentId || 'attachment'
    const contentId = att.contentId ? String(att.contentId) : null
    const bytes = exactArrayBuffer(att.content)
    const size = bytes?.byteLength ?? (typeof att.content === 'string' ? att.content.length : 0)
    attachments.push({ filename, size, contentId })

    const cid = canonicalizeCid(contentId)
    if (cid) cidCount.set(cid, (cidCount.get(cid) || 0) + 1)

    const disposition = String(att.disposition || '').toLowerCase()
    const declared = String(att.mimeType || '').split(';')[0].trim().toLowerCase()
    const wantInline = disposition === 'inline' || declared.startsWith('image/')
    if (!wantInline || !bytes || !cid) continue
    if (bytes.byteLength > EMAIL_LIMITS.maxInlineRasterBytes) throwLimit('email_inline_raster_limit')
    inlineRasterBytes += bytes.byteLength
    if (inlineRasterBytes > EMAIL_LIMITS.maxInlineTotalBytes) throwLimit('email_inline_total_limit')
    const magic = detectRasterMime(bytes)
    if (magic && RASTER_MIMES.has(declared) && magic === declared) {
      inlineParts.push({ canonicalCid: cid, declaredMime: declared, bytes })
    }
  }

  const ambiguousCids = [...cidCount.entries()].filter(([, count]) => count > 1).map(([cid]) => cid)
  const ambiguousSet = new Set(ambiguousCids)
  const from = asList(mail.from).join(', ') || formatNameAddress((mail.from as any)?.name, (mail.from as any)?.address)
  return {
    status: 'ok',
    email: {
      from,
      to: asList(mail.to),
      cc: asList(mail.cc),
      subject: String(mail.subject || ''),
      date: mail.date ? String(mail.date) : null,
      html: mail.html || null,
      text: mail.text || null,
      attachments,
      inlineParts: inlineParts.filter((part) => !ambiguousSet.has(part.canonicalCid)),
      ambiguousCids,
    },
  }
}

function countMsgAttachmentDescriptors(root: any): boolean {
  const stack = [root]
  const seen = new Set<object>()
  let count = 0
  while (stack.length) {
    const message = stack.pop()
    if (!message || typeof message !== 'object' || seen.has(message)) continue
    seen.add(message)
    const descriptors = Array.isArray(message.attachments) ? message.attachments : []
    count += descriptors.length
    if (count > EMAIL_LIMITS.maxParts) return false
    for (const descriptor of descriptors) {
      if (descriptor?.innerMsgContentFields) stack.push(descriptor.innerMsgContentFields)
    }
  }
  return true
}

function msgRecipient(recipient: any): string {
  const address = firstNonEmptyString(recipient?.smtpAddress, recipient?.email, recipient?.name)
  return formatNameAddress(recipient?.name, address)
}

function parseMsg(input: ArrayBuffer): EmailParseResult {
  const reader = new (MsgReader as any)(input)
  const data = reader.getFileData?.() || reader
  if (data?.error) return { status: 'parse_failed', message: String(data.error) }
  if (!countMsgAttachmentDescriptors(data)) return limitResult('email_part_limit')

  const attachmentsRaw = Array.isArray(data.attachments) ? data.attachments : []
  const attachments: ParsedEmailAttachment[] = attachmentsRaw.map((descriptor: any) => ({
    filename: descriptor.fileName || descriptor.name || 'attachment',
    size: Number.isFinite(descriptor.contentLength) && descriptor.contentLength >= 0
      ? descriptor.contentLength
      : 0,
    contentId: descriptor.pidContentId || descriptor.contentId || null,
  }))

  const cidCount = new Map<string, number>()
  for (const descriptor of attachmentsRaw) {
    const cid = canonicalizeCid(descriptor.pidContentId || descriptor.contentId)
    if (cid) cidCount.set(cid, (cidCount.get(cid) || 0) + 1)
  }
  const ambiguousCids = [...cidCount.entries()].filter(([, count]) => count > 1).map(([cid]) => cid)
  const ambiguousSet = new Set(ambiguousCids)
  const inlineParts: ParsedInlinePart[] = []
  let inlineRasterBytes = 0

  for (const descriptor of attachmentsRaw) {
    const cid = canonicalizeCid(descriptor.pidContentId || descriptor.contentId)
    const declared = String(descriptor.attachMimeTag || '').split(';')[0].trim().toLowerCase()
    if (!cid || ambiguousSet.has(cid) || !RASTER_MIMES.has(declared)) continue
    if (Number(descriptor.contentLength) > EMAIL_LIMITS.maxInlineRasterBytes) {
      throwLimit('email_inline_raster_limit')
    }
    const extracted = reader.getAttachment(descriptor)
    const bytes = exactArrayBuffer(extracted?.content)
    if (!bytes) continue
    if (bytes.byteLength > EMAIL_LIMITS.maxInlineRasterBytes) throwLimit('email_inline_raster_limit')
    inlineRasterBytes += bytes.byteLength
    if (inlineRasterBytes > EMAIL_LIMITS.maxInlineTotalBytes) throwLimit('email_inline_total_limit')
    const magic = detectRasterMime(bytes)
    if (magic === declared) inlineParts.push({ canonicalCid: cid, declaredMime: declared, bytes })
  }

  const recipients = Array.isArray(data.recipients) ? data.recipients : []
  const to = recipients
    .filter((recipient: any) => String(recipient?.recipType || '').toLowerCase() === 'to')
    .map(msgRecipient)
    .filter(Boolean)
  const cc = recipients
    .filter((recipient: any) => String(recipient?.recipType || '').toLowerCase() === 'cc')
    .map(msgRecipient)
    .filter(Boolean)

  return {
    status: 'ok',
    email: {
      from: formatNameAddress(
        data.senderName,
        firstNonEmptyString(data.senderSmtpAddress, data.senderEmail, data.senderName),
      ),
      to: recipients.length ? to : asList(data.to),
      cc: recipients.length ? cc : asList(data.cc),
      subject: String(data.subject || ''),
      date: data.messageDeliveryTime ? String(data.messageDeliveryTime) : null,
      html: data.bodyHtml || null,
      text: data.body || data.bodyText || null,
      attachments,
      inlineParts,
      ambiguousCids,
    },
  }
}
