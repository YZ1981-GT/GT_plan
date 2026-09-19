import { describe, it, expect } from 'vitest'
import {
  resolvePreviewFamily,
  buildExtFamilyTable,
  isExtendedFamily,
  stripComments,
  inlineExtensionListViolations,
  LEGACY_CAPABILITIES,
  DEFAULT_FAMILY_DECLARATIONS,
} from '../attachmentPreviewFormats'

describe('Format_Registry resolvePreviewFamily', () => {
  it('扩展名优先且大小写/空白稳定', () => {
    const a = resolvePreviewFamily('  Archive.ZIP  ', 'image')
    const b = resolvePreviewFamily('archive.zip')
    expect(a).toEqual(b)
    expect(a.family).toBe('archive')
    expect(a.byteChannel).toBe('download')
    expect(a.evidence).toBe('extension')
  })

  it('未知扩展名不被 Type_Hint 覆盖', () => {
    const v = resolvePreviewFamily('evil.exe', 'image')
    expect(v.family).toBe('unsupported')
    expect(v.ext).toBe('exe')
  })

  it('无扩展名时 Type_Hint MIME/分类词/别名受限回退', () => {
    expect(resolvePreviewFamily('noext', 'application/zip').family).toBe('archive')
    expect(resolvePreviewFamily('noext', 'word').family).toBe('legacy')
    expect(resolvePreviewFamily('noext', 'eml').family).toBe('email')
    expect(resolvePreviewFamily('noext', 'totally-unknown/x').family).toBe('unsupported')
  })

  it('dwg 仅 cad_download_only，不入可渲染族', () => {
    const v = resolvePreviewFamily('plan.dwg')
    expect(v.family).toBe('unsupported')
    expect(v.advice).toBe('cad_download_only')
    expect(isExtendedFamily(v.family)).toBe(false)
  })

  it('legacy 走 preview 通道', () => {
    expect(resolvePreviewFamily('a.docx').byteChannel).toBe('preview')
    expect(resolvePreviewFamily('a.pdf').family).toBe('legacy')
  })

  it('重复判定确定', () => {
    for (let i = 0; i < 5; i++) {
      expect(resolvePreviewFamily('m.eml', 'msg')).toEqual(resolvePreviewFamily('m.eml', 'msg'))
    }
  })
})

describe('Format_Registry fail-closed table', () => {
  // DEFAULT 声明在模块装载期冲突时，变异器应记录 <file-level>:attachmentPreviewFormats.spec.ts。
  it('跨族冲突 fail closed', () => {
    expect(() =>
      buildExtFamilyTable({
        ...DEFAULT_FAMILY_DECLARATIONS,
        archive: ['zip', 'eml'],
        email: ['eml', 'msg'],
      }),
    ).toThrow(/conflict/)
  })

  it('dwg 入族 fail closed', () => {
    expect(() =>
      buildExtFamilyTable({
        ...DEFAULT_FAMILY_DECLARATIONS,
        drawing: ['dxf', 'dwg'],
      }),
    ).toThrow(/dwg/)
  })
})

describe('LEGACY_CAPABILITIES 宿主专属不求并集', () => {
  it('Preview 图片不含 svg；Drawer Office 10 项；Tab 6 项', () => {
    expect([...LEGACY_CAPABILITIES.previewHost.image]).not.toContain('svg')
    expect(LEGACY_CAPABILITIES.drawerHost.office).toHaveLength(10)
    expect(LEGACY_CAPABILITIES.attachmentTab.office).toHaveLength(6)
    expect([...LEGACY_CAPABILITIES.attachmentTab.office]).not.toContain('.odt')
  })
})

describe('inlineExtensionListViolations', () => {
  it('合成坏源码打红，剥注释后仍可见', () => {
    const dirty = `
      // const OFFICE = ['.doc', '.docx']
      const OFFICE = ['.doc', '.docx', '.xls']
      if (name.endsWith('.pdf')) {}
    `
    const clean = stripComments(dirty)
    expect(clean).not.toMatch(/\/\/ const OFFICE/)
    const v = inlineExtensionListViolations(clean, 'synthetic')
    expect(v.some((x) => x.includes('inline extension list'))).toBe(true)
    expect(v.some((x) => x.includes("endsWith('.pdf')"))).toBe(true)
  })

  it('反向自检：干净源码无违规', () => {
    const clean = stripComments(`
      import { LEGACY_CAPABILITIES } from './attachmentPreviewFormats'
      const x = LEGACY_CAPABILITIES.previewHost.image
    `)
    expect(inlineExtensionListViolations(clean, 'ok')).toEqual([])
  })
})
