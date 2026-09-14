/**
 * useOcrAttachmentCache — 属性测试
 *
 * Spec: .kiro/specs/c-control-test-popup-enhance/  Task 7.2
 *
 * Property 3: OCR 可识别性分类
 *   对任意文件名字符串，isOcrEligible 返回 true 当且仅当（大小写不敏感）扩展名
 *   属于 .pdf/.png/.jpg/.jpeg/.tiff/.bmp/.gif。
 *   **Validates: Requirements 4.2**
 *
 * Property 4: OCR 缓存避免重复调用
 *   对任意已 OCR 处理并缓存的 attachment ID，后续对同一 ID 的 runOcr 返回缓存文本，
 *   不发起额外 HTTP 调用。
 *   **Validates: Requirements 4.3, 6.1, 6.2, 6.3**
 *
 * 实施方案：vitest + fast-check。mock @/utils/http 的 post，统计 POST 调用次数；
 *   mock 返回 { data: { extracted_fields: { full_text: '...' } } } 以匹配 composable
 *   的解包路径（http 拦截器已解包信封，composable 读 res.data.data ?? res.data 再取
 *   extracted_fields.full_text）。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import * as fc from 'fast-check'

// ── Mock http（factory 内变量必须以 mock 前缀，规避 vitest hoisting 限制）──
const mockPost = vi.fn()
const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    post: (...args: any[]) => mockPost(...args),
    get: (...args: any[]) => mockGet(...args),
  },
}))

import { useOcrAttachmentCache, isOcrEligible } from '@/composables/useOcrAttachmentCache'

// ─── Property 3: OCR 可识别性分类 ─────────────────────────────────────────────

const OCR_EXTS = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif']

/** 参考实现（独立于被测代码）：文件名 → 是否可 OCR */
function referenceEligible(fileName: string): boolean {
  if (!fileName || typeof fileName !== 'string') return false
  const parts = fileName.split('.')
  if (parts.length < 2) return false
  const ext = '.' + (parts[parts.length - 1].toLowerCase())
  return OCR_EXTS.includes(ext)
}

describe('Property 3: OCR 可识别性分类 (isOcrEligible)', () => {
  // ── 代表性用例：可识别扩展名（含大写 / 混合大小写 / 多点名） ──
  it('可识别扩展名（小写）返回 true', () => {
    for (const ext of OCR_EXTS) {
      expect(isOcrEligible(`evidence${ext}`)).toBe(true)
    }
  })

  it('大写 / 混合大小写扩展名返回 true', () => {
    expect(isOcrEligible('REPORT.PDF')).toBe(true)
    expect(isOcrEligible('scan.JPG')).toBe(true)
    expect(isOcrEligible('img.JpEg')).toBe(true)
    expect(isOcrEligible('photo.Png')).toBe(true)
    expect(isOcrEligible('doc.TIFF')).toBe(true)
    expect(isOcrEligible('x.Bmp')).toBe(true)
    expect(isOcrEligible('anim.GIF')).toBe(true)
  })

  it('多点文件名按最后一段扩展名判定', () => {
    expect(isOcrEligible('report.final.pdf')).toBe(true)
    expect(isOcrEligible('2025.q1.summary.jpeg')).toBe(true)
    expect(isOcrEligible('report.pdf.docx')).toBe(false) // 最后一段是 docx
    expect(isOcrEligible('archive.tar.gz')).toBe(false)
  })

  it('非可识别 / 边界用例返回 false', () => {
    expect(isOcrEligible('notes.docx')).toBe(false)
    expect(isOcrEligible('data.txt')).toBe(false)
    expect(isOcrEligible('noextension')).toBe(false)
    expect(isOcrEligible('')).toBe(false)
    expect(isOcrEligible('file.')).toBe(false) // 空扩展名
    // @ts-expect-error 显式测试非字符串输入的健壮性
    expect(isOcrEligible(null)).toBe(false)
    // @ts-expect-error
    expect(isOcrEligible(undefined)).toBe(false)
  })

  // ── fast-check：任意文件名，isOcrEligible 与参考实现等价 ──
  it('对任意生成的文件名，isOcrEligible 等价于参考实现', () => {
    // 生成器：基础名（可能含点/中文/空）+ 从常见扩展名池或随机后缀
    const baseArb = fc.oneof(
      fc.string(),
      fc.constantFrom('report', 'evidence.final', '2025.q1', '合同扫描件', 'a.b.c', ''),
    )
    const extArb = fc.oneof(
      // 可识别扩展名的各种大小写变体
      fc.constantFrom(
        ...OCR_EXTS,
        '.PDF', '.Pdf', '.JPG', '.JpEg', '.PNG', '.TIFF', '.BMP', '.GIF',
      ),
      // 不可识别扩展名
      fc.constantFrom('.docx', '.txt', '.xlsx', '.csv', '.zip', '.tar', '.', ''),
      // 完全随机的短后缀
      fc.string({ minLength: 0, maxLength: 5 }).map((s) => (s ? '.' + s : s)),
    )
    fc.assert(
      fc.property(baseArb, extArb, (base, ext) => {
        const fileName = base + ext
        expect(isOcrEligible(fileName)).toBe(referenceEligible(fileName))
      }),
      { numRuns: 300 },
    )
  })
})

// ─── Property 4: OCR 缓存避免重复调用 ─────────────────────────────────────────

describe('Property 4: OCR 缓存避免重复调用 (runOcr)', () => {
  beforeEach(() => {
    mockPost.mockReset()
    mockGet.mockReset()
  })

  it('首次 runOcr 发起 1 次 POST，第二次同 ID 命中缓存 0 次额外 POST 且返回相同文本', async () => {
    mockPost.mockResolvedValue({ data: { extracted_fields: { full_text: '识别文本-A' } } })

    const { runOcr, ocrCache } = useOcrAttachmentCache()
    const wpId = 'wp-1'
    const attId = 'att-1'
    const file = new Blob(['dummy'], { type: 'application/pdf' })

    const first = await runOcr(wpId, attId, file)
    expect(first).toBe('识别文本-A')
    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(ocrCache.value.get(attId)).toBe('识别文本-A')

    // 第二次同 ID：命中缓存，无额外 HTTP
    const second = await runOcr(wpId, attId, file)
    expect(second).toBe('识别文本-A')
    expect(second).toBe(first)
    expect(mockPost).toHaveBeenCalledTimes(1) // 仍是 1，无额外调用
  })

  it('对任意 attachment ID 序列，唯一 ID 数 == POST 调用次数（缓存去重）', async () => {
    await fc.assert(
      fc.asyncProperty(
        // 生成一串会重复的 attachment id 访问序列
        fc.array(fc.constantFrom('a1', 'a2', 'a3', 'a4', 'a5'), { minLength: 1, maxLength: 30 }),
        async (idSequence) => {
          mockPost.mockReset()
          // 每个 id 返回可区分的文本，便于校验缓存正确性
          mockPost.mockImplementation(() =>
            Promise.resolve({ data: { extracted_fields: { full_text: 'ocr-text' } } }),
          )

          const { runOcr, ocrCache } = useOcrAttachmentCache()
          const wpId = 'wp-x'
          const file = new Blob(['x'])

          for (const id of idSequence) {
            const text = await runOcr(wpId, id, file)
            expect(text).toBe('ocr-text')
          }

          const uniqueIds = new Set(idSequence)
          // 属性核心：HTTP 调用次数 == 唯一 ID 数（每个 ID 只 OCR 一次）
          expect(mockPost).toHaveBeenCalledTimes(uniqueIds.size)
          // 缓存包含全部唯一 ID
          expect(ocrCache.value.size).toBe(uniqueIds.size)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('不同 attachment ID 各触发一次 POST', async () => {
    mockPost.mockResolvedValue({ data: { extracted_fields: { full_text: 't' } } })
    const { runOcr } = useOcrAttachmentCache()
    const file = new Blob(['x'])

    await runOcr('wp', 'id-1', file)
    await runOcr('wp', 'id-2', file)
    await runOcr('wp', 'id-1', file) // 重复 id-1 → 命中缓存
    expect(mockPost).toHaveBeenCalledTimes(2)
  })

  it('缓存独立于实例内，ocrCache 在同一 composable 生命周期内持久', async () => {
    mockPost.mockResolvedValue({ data: { extracted_fields: { full_text: 'persist' } } })
    const cache = useOcrAttachmentCache()
    const file = new Blob(['x'])

    await cache.runOcr('wp', 'k', file)
    // resetListCache 只清列表，不清 ocrCache
    cache.resetListCache()
    await cache.runOcr('wp', 'k', file)
    expect(mockPost).toHaveBeenCalledTimes(1) // resetListCache 后仍命中 OCR 缓存
  })
})
