/**
 * 四栏目录的附注大章标题与编辑器左侧树同源（spec disclosure-note-template-word-realignment Phase 3）：
 * 章行标题优先、内置名称兜底，且按项目准则区分（旧实现是国企 / 上市混在一起的写死映射）。
 */
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({ api: { get: (...a: unknown[]) => mockGet(...a) } }))
vi.mock('@/services/apiPaths', () => ({
  trialBalance: { get: () => '/mock-tb' },
  workpapers: { list: () => '/mock-wp' },
  projects: { list: '/mock-projects' },
}))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() } }))

import FourColumnCatalog from '../FourColumnCatalog.vue'

async function chapters(project: Record<string, unknown>, notes: unknown[]) {
  mockGet.mockImplementation(async (url: string) => (url.startsWith('/api/disclosure-notes/') ? notes : []))
  const wrapper = mount(FourColumnCatalog, {
    props: { project: { audit_year: 2025, ...project } },
    global: { stubs: { ElIcon: true, ElTag: true, ElEmpty: true } },
  })
  await flushPromises()
  return (wrapper.vm as any).noteChapters.map((c: { prefix: string; label: string }) => `${c.prefix}|${c.label}`)
}

describe('FourColumnCatalog 附注大章标题', () => {
  it('取章行标题（上市单体「五」是口径名）', async () => {
    expect(await chapters({ id: 'p1', template_type: 'listed' }, [
      { note_section: '五', section_title: '财务报表项目附注' },
      { note_section: '五、1', section_title: '货币资金' },
    ])).toEqual(['五|财务报表项目附注'])
  })

  it('没有章行时按项目准则取内置名称', async () => {
    const rows = [{ note_section: '一、1', section_title: '基本情况' }]
    expect(await chapters({ id: 'p2', template_type: 'soe' }, rows)).toEqual(['一|公司（企业）基本情况'])
    expect(await chapters({ id: 'p3', template_type: 'listed' }, rows)).toEqual(['一|公司基本情况'])
  })
})
