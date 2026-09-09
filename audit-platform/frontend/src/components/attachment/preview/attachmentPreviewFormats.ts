/**
 * Format_Registry — 扩展名/Type_Hint → 渲染族单一真源
 * Spec: audit-evidence-attachment-preview-format-expansion Task 3
 */
export type PreviewFamily = 'archive' | 'email' | 'drawing' | 'legacy' | 'unsupported'
export type ByteChannel = 'preview' | 'download'
export type TypeHint = string | null | undefined
export type FamilyAdvice = 'cad_download_only' | 'generic'
export type FamilyEvidence = 'extension' | 'type_hint' | 'none'

export interface FamilyVerdict {
  family: PreviewFamily
  byteChannel: ByteChannel
  ext: string
  advice: FamilyAdvice
  evidence: FamilyEvidence
}

export interface FamilyDeclarations {
  archive: readonly string[]
  email: readonly string[]
  drawing: readonly string[]
  /** 仅 advice，永不入可渲染族 */
  cadDownloadOnly: readonly string[]
}

export const DEFAULT_FAMILY_DECLARATIONS: FamilyDeclarations = {
  archive: ['zip', 'tar', 'gz', 'tgz'],
  email: ['eml', 'msg'],
  drawing: ['dxf'],
  cadDownloadOnly: ['dwg'],
}

/** 宿主专属 legacy 能力矩阵 — 禁止求并集回灌 */
export const LEGACY_CAPABILITIES = Object.freeze({
  previewHost: Object.freeze({
    word: Object.freeze(['docx', 'doc'] as const),
    excel: Object.freeze(['xlsx', 'xls', 'csv'] as const),
    image: Object.freeze(['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'] as const),
    categoryHints: Object.freeze(['word', 'excel', 'image'] as const),
  }),
  drawerHost: Object.freeze({
    office: Object.freeze([
      '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp', '.rtf',
    ] as const),
    pdfSuffix: '.pdf',
    imageTypePrefix: 'image/',
  }),
  attachmentTab: Object.freeze({
    office: Object.freeze(['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'] as const),
    iconGroups: Object.freeze({
      pdf: Object.freeze(['.pdf'] as const),
      image: Object.freeze(['.png', '.jpg', '.jpeg', '.gif'] as const),
      word: Object.freeze(['.doc', '.docx'] as const),
      excel: Object.freeze(['.xls', '.xlsx'] as const),
      ppt: Object.freeze(['.ppt', '.pptx'] as const),
    }),
  }),
})

const KNOWN_MIME_TO_EXT: Record<string, string> = {
  'message/rfc822': 'eml',
  'application/vnd.ms-outlook': 'msg',
  'application/zip': 'zip',
  'application/gzip': 'gz',
  'application/x-tar': 'tar',
  'application/pdf': 'pdf',
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/gif': 'gif',
  'image/webp': 'webp',
  'image/bmp': 'bmp',
  'image/svg+xml': 'svg',
}

const CATEGORY_HINTS = new Set(['word', 'excel', 'image'])

function normalizeExtToken(raw: string): string {
  return raw.trim().toLowerCase().replace(/^\./, '')
}

function extFromFileName(fileName: string): string {
  const name = (fileName || '').trim()
  const dot = name.lastIndexOf('.')
  if (dot < 0 || dot === name.length - 1) return ''
  return normalizeExtToken(name.slice(dot + 1))
}

function byteChannelFor(family: PreviewFamily): ByteChannel {
  if (family === 'legacy') return 'preview'
  if (family === 'archive' || family === 'email' || family === 'drawing') return 'download'
  return 'download'
}

export function buildExtFamilyTable(decls: FamilyDeclarations): Map<string, PreviewFamily> {
  const table = new Map<string, PreviewFamily>()
  const assign = (exts: readonly string[], family: PreviewFamily) => {
    for (const raw of exts) {
      const ext = normalizeExtToken(raw)
      if (!ext) continue
      const prev = table.get(ext)
      if (prev && prev !== family) {
        throw new Error(`Format_Registry conflict: .${ext} in both ${prev} and ${family}`)
      }
      table.set(ext, family)
    }
  }
  assign(decls.archive, 'archive')
  assign(decls.email, 'email')
  assign(decls.drawing, 'drawing')

  for (const raw of decls.cadDownloadOnly) {
    const ext = normalizeExtToken(raw)
    if (table.has(ext)) {
      throw new Error(`Format_Registry fail-closed: cad-only .${ext} must not enter render family`)
    }
  }
  if (table.get('dwg')) {
    throw new Error('Format_Registry fail-closed: dwg must not enter render family')
  }
  return table
}

const DEFAULT_TABLE = buildExtFamilyTable(DEFAULT_FAMILY_DECLARATIONS)

function isLegacyExt(ext: string): boolean {
  const ph = LEGACY_CAPABILITIES.previewHost
  if ((ph.word as readonly string[]).includes(ext)) return true
  if ((ph.excel as readonly string[]).includes(ext)) return true
  if ((ph.image as readonly string[]).includes(ext)) return true
  if (ext === 'pdf') return true
  // Drawer/Tab office 扩展在 registry 层仍归 legacy（宿主矩阵各自消费）
  const drawerOffice = LEGACY_CAPABILITIES.drawerHost.office.map((e) => normalizeExtToken(e))
  if (drawerOffice.includes(ext)) return true
  return false
}

function resolveFromExt(ext: string, table: Map<string, PreviewFamily>): FamilyVerdict | null {
  if (!ext) return null
  if (DEFAULT_FAMILY_DECLARATIONS.cadDownloadOnly.map(normalizeExtToken).includes(ext)) {
    return {
      family: 'unsupported',
      byteChannel: 'download',
      ext,
      advice: 'cad_download_only',
      evidence: 'extension',
    }
  }
  const family = table.get(ext)
  if (family) {
    return {
      family,
      byteChannel: byteChannelFor(family),
      ext,
      advice: 'generic',
      evidence: 'extension',
    }
  }
  if (isLegacyExt(ext)) {
    return {
      family: 'legacy',
      byteChannel: 'preview',
      ext,
      advice: 'generic',
      evidence: 'extension',
    }
  }
  return null
}

function resolveTypeHintToken(typeHint: TypeHint): { ext: string; kind: 'mime' | 'category' | 'alias' } | null {
  if (typeHint == null) return null
  const raw = String(typeHint).trim().toLowerCase()
  if (!raw) return null
  if (KNOWN_MIME_TO_EXT[raw]) {
    return { ext: KNOWN_MIME_TO_EXT[raw], kind: 'mime' }
  }
  if (CATEGORY_HINTS.has(raw)) {
    return { ext: raw, kind: 'category' }
  }
  const alias = normalizeExtToken(raw)
  if (alias && !alias.includes('/') && !alias.includes(' ')) {
    return { ext: alias, kind: 'alias' }
  }
  return null
}

export function resolvePreviewFamily(
  fileName: string,
  typeHint?: TypeHint,
  decls: FamilyDeclarations = DEFAULT_FAMILY_DECLARATIONS,
  table: Map<string, PreviewFamily> = decls === DEFAULT_FAMILY_DECLARATIONS
    ? DEFAULT_TABLE
    : buildExtFamilyTable(decls),
): FamilyVerdict {
  const fromName = extFromFileName(fileName)
  if (fromName) {
    const byExt = resolveFromExt(fromName, table)
    if (byExt) return byExt
    // 未知扩展名：不得被 Type_Hint 覆盖
    return {
      family: 'unsupported',
      byteChannel: 'download',
      ext: fromName,
      advice: 'generic',
      evidence: 'extension',
    }
  }

  const hint = resolveTypeHintToken(typeHint)
  if (!hint) {
    return {
      family: 'unsupported',
      byteChannel: 'download',
      ext: '',
      advice: 'generic',
      evidence: 'none',
    }
  }

  if (hint.kind === 'category') {
    return {
      family: 'legacy',
      byteChannel: 'preview',
      ext: hint.ext,
      advice: 'generic',
      evidence: 'type_hint',
    }
  }

  const byHint = resolveFromExt(hint.ext, table)
  if (byHint) {
    return { ...byHint, evidence: 'type_hint' }
  }
  if (isLegacyExt(hint.ext)) {
    return {
      family: 'legacy',
      byteChannel: 'preview',
      ext: hint.ext,
      advice: 'generic',
      evidence: 'type_hint',
    }
  }
  return {
    family: 'unsupported',
    byteChannel: 'download',
    ext: hint.ext,
    advice: hint.ext === 'dwg' ? 'cad_download_only' : 'generic',
    evidence: 'type_hint',
  }
}

export function isExtendedFamily(family: PreviewFamily): boolean {
  return family === 'archive' || family === 'email' || family === 'drawing'
}

/** 剥 SFC/TS 注释，供单一真源扫描 */
export function stripComments(source: string): string {
  let out = source
  out = out.replace(/\/\*[\s\S]*?\*\//g, '')
  out = out.replace(/(^|[^:])\/\/.*$/gm, '$1')
  out = out.replace(/<!--[\s\S]*?-->/g, '')
  return out
}

const KNOWN_EXTS = new Set(
  [
    ...DEFAULT_FAMILY_DECLARATIONS.archive,
    ...DEFAULT_FAMILY_DECLARATIONS.email,
    ...DEFAULT_FAMILY_DECLARATIONS.drawing,
    ...DEFAULT_FAMILY_DECLARATIONS.cadDownloadOnly,
    ...LEGACY_CAPABILITIES.previewHost.word,
    ...LEGACY_CAPABILITIES.previewHost.excel,
    ...LEGACY_CAPABILITIES.previewHost.image,
    'pdf',
    'ppt',
    'pptx',
    'odt',
    'ods',
    'odp',
    'rtf',
    'svg',
    'doc',
    'docx',
    'xls',
    'xlsx',
    'csv',
  ].map(normalizeExtToken),
)

/**
 * 扫描宿主/消费方源码：registry 外私有扩展名清单报违规。
 * 从 registry 导入的常量/helper 消费豁免（调用方应传入已剥注释源码，并自行标注 import 豁免）。
 */
export function inlineExtensionListViolations(
  cleanSource: string,
  label: string,
  opts?: { exemptImportRegistry?: boolean },
): string[] {
  const violations: string[] = []
  if (opts?.exemptImportRegistry && /attachmentPreviewFormats|LEGACY_CAPABILITIES|resolvePreviewFamily/.test(cleanSource)) {
    // 仍检查 endsWith / === 私有判定
  }

  const arrayRe = /\[((?:[^\[\]]|'[^']*'|"[^"]*")+)\]/g
  let m: RegExpExecArray | null
  while ((m = arrayRe.exec(cleanSource))) {
    const body = m[1]
    const tokens = [...body.matchAll(/['"]\.?([a-z0-9]+)['"]/gi)].map((x) => normalizeExtToken(x[1]))
    const known = tokens.filter((t) => KNOWN_EXTS.has(t))
    if (known.length >= 2 && !/LEGACY_CAPABILITIES|DEFAULT_FAMILY_DECLARATIONS|office_exts_frozen|image_exts_frozen/.test(cleanSource.slice(Math.max(0, m.index - 80), m.index))) {
      // 启发式：含 ≥2 已知扩展名的字面量数组
      violations.push(`${label}: inline extension list ${JSON.stringify(known)}`)
    }
  }

  const endsWithRe = /\.endsWith\(\s*['"](\.[A-Za-z0-9]+)['"]\s*\)/g
  while ((m = endsWithRe.exec(cleanSource))) {
    violations.push(`${label}: private endsWith('${m[1]}')`)
  }

  return [...new Set(violations)]
}
