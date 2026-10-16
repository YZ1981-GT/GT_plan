/**
 * 附注目录章标题（spec disclosure-note-template-word-realignment Phase 3）。
 *
 * 旧实现把章名写死在前端（国企「一、公司基本情况」「五、会计政策变更及差错更正」…），种子按四版 Word 改章名、
 * 存量项目按 Word 对齐后，目录树仍显示旧名。改为：章行（note_section 恰为章号）的标题优先，没有章行才用内置名称；
 * 内置名称逐条钉到种子章名，种子再改时这里先红，不会出现第三套章名。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { computed, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import {
  LISTED_CHAPTER_LABELS,
  SOE_CHAPTER_LABELS,
  chapterLabel,
} from '@/views/composables/noteChapterLabels'

const mockGetTree = vi.fn()
vi.mock('@/services/auditPlatformApi', () => ({ getDisclosureNoteTree: (...a: unknown[]) => mockGetTree(...a) }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/acnr/useAcnr', () => ({ useAcnr: () => ({ resolveRoute: vi.fn() }) }))

function seedChapters(std: 'soe' | 'listed'): Record<string, string> {
  const raw = readFileSync(resolve(__dirname, `../../../../../../backend/data/note_template_${std}.json`), 'utf-8')
  const sections = JSON.parse(raw.replace(/^\uFEFF/, '')).sections as Array<{
    section_number: string; section_title: string; level: number
  }>
  return Object.fromEntries(sections.filter(s => s.level === 1).map(s => [s.section_number, s.section_title]))
}

describe('chapterLabel', () => {
  it('章行标题优先（库内已按 Word / 口径对齐）', () => {
    const rows = [{ note_section: '五', section_title: '财务报表项目附注' }, { note_section: '五、1', section_title: '货币资金' }]
    expect(chapterLabel(rows, '五', 'listed')).toBe('财务报表项目附注')
  })

  it('没有章行才用内置名称；按准则区分', () => {
    const rows = [{ note_section: '一、1', section_title: '公司基本情况' }]
    expect(chapterLabel(rows, '一', 'soe')).toBe('公司（企业）基本情况')
    expect(chapterLabel(rows, '一', 'listed')).toBe('公司基本情况')
    expect(chapterLabel([{ note_section: '五', section_title: '  ' }], '五', 'soe')).toBe('会计政策、会计估计变更及差错更正')
    expect(chapterLabel([], '十八', 'soe')).toBe('')
  })

  it.each(['soe', 'listed'] as const)('内置名称与 %s 种子章名逐条一致', (std) => {
    const labels = std === 'soe' ? SOE_CHAPTER_LABELS : LISTED_CHAPTER_LABELS
    expect(labels).toEqual(seedChapters(std))
  })
})

describe('useNoteTree 章节点标题', () => {
  it('取章行标题而不是写死的旧章名', async () => {
    const { useNoteTree } = await import('@/views/composables/useNoteTree')
    mockGetTree.mockResolvedValue([
      { id: 'c1', note_section: '一', section_title: '公司（企业）基本情况', sort_order: 99 },
      { id: 'n1', note_section: '一、1', section_title: '公司（企业）基本情况', sort_order: 100 },
      { id: 'c14', note_section: '十四', section_title: '财务报表之批准', sort_order: 1399 },
      { id: 'n14', note_section: '十四、1', section_title: '财务报表之批准', sort_order: 1400 },
    ])
    const { fetchTree, treeData } = useNoteTree({
      projectId: computed(() => 'p1'), year: computed(() => 2025), templateType: ref('soe'),
      isEqcrRole: computed(() => false),
    })
    await fetchTree()
    expect(treeData.value.map(n => n.label)).toEqual(['一、公司（企业）基本情况', '十四、财务报表之批准'])
  })

  it('上市单体「五」取章行的口径名（内置名称是合并版）', async () => {
    const { useNoteTree } = await import('@/views/composables/useNoteTree')
    mockGetTree.mockResolvedValue([
      { id: 'c5', note_section: '五', section_title: '财务报表项目附注', sort_order: 499 },
      { id: 'n5', note_section: '五、1', section_title: '货币资金', sort_order: 500 },
    ])
    const { fetchTree, treeData } = useNoteTree({
      projectId: computed(() => 'p2'), year: computed(() => 2025), templateType: ref('listed'),
      isEqcrRole: computed(() => false),
    })
    await fetchTree()
    expect(treeData.value.map(n => n.label)).toEqual(['五、财务报表项目附注'])
  })
})
