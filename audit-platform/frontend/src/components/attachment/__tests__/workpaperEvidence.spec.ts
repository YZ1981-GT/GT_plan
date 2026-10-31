/**
 * workpaperEvidence — 底稿内上传证据的唯一写法（spec attachment-evidence-intake ADR-AEI-06/08）
 */
import { existsSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockPost = vi.fn()
const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    post: (...args: any[]) => mockPost(...args),
    get: (...args: any[]) => mockGet(...args),
  },
}))

import {
  EVIDENCE_TYPE_LABEL,
  EVIDENCE_TYPE_OPTIONS,
  associateCandidates,
  evidencePositionLabel,
  itemCellRef,
  uploadWorkpaperEvidence,
  voucherKeyLabel,
} from '../workpaperEvidence'
import { resetWpEvidenceLinksForTest } from '@/composables/useWpEvidenceLinks'

function repoRoot(): string {
  let dir = dirname(fileURLToPath(import.meta.url))
  for (let i = 0; i < 12; i += 1) {
    if (existsSync(resolve(dir, 'backend/app/services/workpaper_evidence_intake.py'))) return dir
    dir = resolve(dir, '..')
  }
  throw new Error('找不到仓库根目录')
}

/** 取 python ``NAME: frozenset[str] = frozenset({...})`` 字面量里的字符串成员（按括号配对截取）。 */
function pyFrozensetMembers(src: string, name: string): string[] {
  const at = src.indexOf(`${name}: frozenset[str] = frozenset({`)
  expect(at, `后端未找到 ${name}`).toBeGreaterThanOrEqual(0)
  const open = src.indexOf('{', at)
  let depth = 0
  let end = open
  for (; end < src.length; end += 1) {
    if (src[end] === '{') depth += 1
    else if (src[end] === '}') {
      depth -= 1
      if (depth === 0) break
    }
  }
  const body = src.slice(open + 1, end).replace(/#.*$/gm, '')
  return [...body.matchAll(/"([a-z_]+)"/g)].map((m) => m[1])
}

describe('证据类型选项', () => {
  it('与后端 EVIDENCE_TYPES 逐项一致，且都有中文标签', () => {
    const py = readFileSync(resolve(repoRoot(), 'backend/app/services/workpaper_evidence_intake.py'), 'utf-8')
    const backend = pyFrozensetMembers(py, 'EVIDENCE_TYPES')
    expect(backend.length).toBeGreaterThanOrEqual(8)
    expect([...EVIDENCE_TYPE_OPTIONS.map((o) => o.value)].sort()).toEqual([...backend].sort())
    for (const opt of EVIDENCE_TYPE_OPTIONS) {
      expect(opt.label).toMatch(/[\u4e00-\u9fa5]/)
      expect(EVIDENCE_TYPE_LABEL[opt.value]).toBe(opt.label)
    }
  })

  it('解析器自检：注释里的取值不算成员', () => {
    const sample = 'EVIDENCE_TYPES: frozenset[str] = frozenset({\n    "a_b",  # "not_me"\n    "c",\n})'
    expect(pyFrozensetMembers(sample, 'EVIDENCE_TYPES')).toEqual(['a_b', 'c'])
  })
})

describe('位置键与标签', () => {
  it('itemCellRef 生成 item:{序号}', () => {
    expect(itemCellRef(0)).toBe('item:0')
    expect(itemCellRef('3')).toBe('item:3')
  })

  it('evidencePositionLabel 覆盖槽位、行、单元格、页码与整稿', () => {
    expect(evidencePositionLabel({ sheet_name: 'D2A', cell_ref: 'item:3' })).toBe('D2A · 第 3 项')
    // 行槽位是内部行 id（uuid / 随机串）⇒ 不展示；纯数字才显示行号（spec attachment-inline-preview）
    expect(evidencePositionLabel({ sheet_name: 'F2-3', cell_ref: 'row:r-9', page_ref: '2' })).toBe('F2-3 · 行内证据 · 第 2 页')
    expect(evidencePositionLabel({ sheet_name: 'G8-6', cell_ref: 'row:3' })).toBe('G8-6 · 第 3 行')
    expect(evidencePositionLabel({ cell_ref: 'B5' })).toBe('B5')
    expect(evidencePositionLabel({})).toBe('整张底稿')
    // 凭证证据：前缀「凭证 日期 字-号」（spec attachment-voucher-evidence-binding 需求 1.5）；凭证级链接没有表页 / 单元格
    const VK = JSON.stringify(['2025', '重庆医药', '2025-01-07', 'FY', '0003'])
    expect(evidencePositionLabel({ voucher_key: VK, sheet_name: 'D2-4', cell_ref: 'row:r-1' })).toBe('凭证 2025-01-07 FY-0003 · D2-4 · 行内证据')
    expect(evidencePositionLabel({ voucher_key: VK })).toBe('凭证 2025-01-07 FY-0003')
    expect(evidencePositionLabel({ voucher_key: '不是凭证键', sheet_name: 'D2-4' })).toBe('D2-4')
  })

  it('voucherKeyLabel：五段键 ⇒「日期 字-号」，凭证字为空只写号；解析不了返回空串', () => {
    expect(voucherKeyLabel(JSON.stringify(['2025', 'c', '2025-03-01', '', '18']))).toBe('2025-03-01 18')
    expect(voucherKeyLabel(JSON.stringify(['2025', 'c', '2025-03-01']))).toBe('')
    expect(voucherKeyLabel('[')).toBe('')
    expect(voucherKeyLabel(null)).toBe('')
  })
})

describe('uploadWorkpaperEvidence', () => {
  beforeEach(() => {
    resetWpEvidenceLinksForTest()
    mockPost.mockReset()
    mockGet.mockReset()
  })

  it('整稿上传：不带位置字段，返回回执里的附件', async () => {
    mockPost.mockResolvedValueOnce({ data: { attachment: { id: 'a1', file_name: '对账单.pdf' }, evidence_link: null } })
    const file = new File(['%PDF'], '对账单.pdf', { type: 'application/pdf' })
    const res = await uploadWorkpaperEvidence({ projectId: 'p1', wpId: 'w1', file, evidenceType: 'bank_statement' })
    const [url, form, config] = mockPost.mock.calls[0]
    expect(url).toBe('/api/projects/p1/workpapers/w1/evidence/upload')
    expect((form as FormData).get('evidence_type')).toBe('bank_statement')
    expect((form as FormData).has('sheet_name')).toBe(false)
    expect((form as FormData).has('cell_ref')).toBe(false)
    expect(((form as FormData).get('file') as File).name).toBe('对账单.pdf')
    expect(config).toMatchObject({ _silent: true })
    expect(res.attachment.id).toBe('a1')
    expect(res.evidenceLink).toBeNull()
  })

  it('行级上传带表页与单元格；兼容未解包的信封', async () => {
    mockPost.mockResolvedValueOnce({
      data: { code: 200, message: 'ok', data: { attachment: { id: 'a2' }, evidence_link: { id: 'l2' } } },
    })
    const blob = new Blob(['x'])
    const res = await uploadWorkpaperEvidence({
      projectId: 'p1', wpId: 'w1', file: blob, fileName: '回单.png', sheetName: 'E1-3', cellRef: 'row:7', pageRef: '1',
    })
    const form = mockPost.mock.calls[0][1] as FormData
    expect(form.get('sheet_name')).toBe('E1-3')
    expect(form.get('cell_ref')).toBe('row:7')
    expect(form.get('page_ref')).toBe('1')
    expect(form.has('evidence_type')).toBe(false)
    expect((form.get('file') as File).name).toBe('回单.png')
    expect(res.attachment.id).toBe('a2')
    expect(res.evidenceLink).toEqual({ id: 'l2' })
  })

  it('凭证证据上传带 voucher_key（不带表页 / 单元格 = 凭证级）', async () => {
    mockPost.mockResolvedValueOnce({ data: { attachment: { id: 'a3' }, evidence_link: { id: 'l3' } } })
    const VK = JSON.stringify(['2025', 'c', '2025-01-07', '记', '0003'])
    await uploadWorkpaperEvidence({ projectId: 'p1', wpId: 'w1', file: new File(['x'], 'v.pdf'), evidenceType: 'voucher', voucherKey: VK })
    const form = mockPost.mock.calls[0][1] as FormData
    expect([form.get('voucher_key'), form.get('evidence_type'), form.has('sheet_name'), form.has('cell_ref')])
      .toEqual([VK, 'voucher', false, false])
  })

  it('回执没有附件编号时报错（不让调用方拿空 id 继续识别）', async () => {
    mockPost.mockResolvedValueOnce({ data: { ok: true } })
    const file = new File(['x'], 'a.pdf')
    await expect(uploadWorkpaperEvidence({ projectId: 'p1', wpId: 'w1', file })).rejects.toThrow('未返回附件编号')
  })

  it('缺项目或底稿直接报错，不发请求', async () => {
    const file = new File(['x'], 'a.pdf')
    await expect(uploadWorkpaperEvidence({ projectId: '', wpId: 'w1', file })).rejects.toThrow()
    expect(mockPost).not.toHaveBeenCalled()
  })
})

describe('associateCandidates — 附件管理「关联到底稿」候选取底稿 id（走查中发现：原先取索引 id，关联恒 404）', () => {
  // 形状照 GET /api/projects/{pid}/wp-index 的真实回执（id = 索引 id，wp_id = 底稿 id）
  const indexItems = [
    { id: 'idx-f3', wp_id: 'wp-f3', wp_code: 'F3', wp_name: '应付票据' },
    { id: 'idx-f4', wp_id: 'wp-f4', wp_code: 'F4', wp_name: '应付账款' },
    { id: 'idx-f5', wp_id: null, wp_code: 'F5', wp_name: '营业成本' },
  ]

  it('选项值是 wp_id，不是索引 id', () => {
    expect(associateCandidates(indexItems, 'F3')).toEqual([{ wpId: 'wp-f3', wpCode: 'F3', wpName: '应付票据' }])
  })

  it('按编号或名称匹配（不区分大小写），只列已生成底稿的条目', () => {
    expect(associateCandidates(indexItems, 'f').map((c) => c.wpId)).toEqual(['wp-f3', 'wp-f4'])
    expect(associateCandidates(indexItems, '应付账').map((c) => c.wpCode)).toEqual(['F4'])
    expect(associateCandidates(indexItems, '营业成本')).toEqual([])
  })

  it('空查询 / 非数组输入返回空；结果数受上限约束', () => {
    expect(associateCandidates(indexItems, '  ')).toEqual([])
    expect(associateCandidates({ items: indexItems }, 'F')).toEqual([])
    const many = Array.from({ length: 30 }, (_, i) => ({ id: `i${i}`, wp_id: `w${i}`, wp_code: `F${i}`, wp_name: 'x' }))
    expect(associateCandidates(many, 'F')).toHaveLength(20)
    expect(associateCandidates(many, 'F', 5)).toHaveLength(5)
  })
})
