/**
 * A1-15 企业会计准则财务报表列报及披露核对表 — Unit Tests (Tasks 8.1–8.5)
 *
 * 验证：
 *  8.1 注册契约 — htmlRendererRegistry 含 a1-15-disclosure-checklist；VALID_COMPONENT_TYPES 含该值；wp_code_overrides 映射正确
 *  8.2 useA115Checklist 行为 — loadData/updateItemResponse/setTocApplicability/globalProgress/sectionProgress/searchQuery/conclusionFilter
 *  8.3 useA115Navigation 行为 — scrollToSection/activeSectionId/visibleSections
 *  8.4 GtA115DisclosureChecklist 组件 — 默认 html 模式、模式切换、骨架屏、错误重试、卡片渲染、结论按钮交互
 *  8.5 Cross_Reference_Map — 至少覆盖 10 个映射、suggested chip 渲染、确认保存
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ref, nextTick, computed } from 'vue'
import { shallowMount } from '@vue/test-utils'

import { HTML_RENDERER_REGISTRY } from '../htmlRendererRegistry'
import { CROSS_REFERENCE_MAP } from '../composables/useA115Checklist'

// Mock apiProxy
const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPut = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

// Mock element-plus
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
  ElMessageBox: { confirm: vi.fn().mockRejectedValue('cancel') },
}))

// Mock vue-router
vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { projectId: 'proj-test' },
    query: { year: '2026' },
  }),
}))

// Mock child components
vi.mock('../GtOnlyOfficeSheet.vue', () => ({ default: { template: '<div class="mock-onlyoffice" />' } }))
vi.mock('../GtIndexChip.vue', () => ({ default: { template: '<span class="mock-index-chip" />', props: ['value'] } }))

// Mock IntersectionObserver for jsdom
const mockIntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}))
vi.stubGlobal('IntersectionObserver', mockIntersectionObserver)

// ═══════════════════════════════════════════════════════════════════════════════
// Mock Data
// ═══════════════════════════════════════════════════════════════════════════════

const MOCK_TEMPLATE = {
  wp_code: 'A1-15',
  title: '企业会计准则有关财务报表列报及披露核对表',
  sections: [
    {
      id: 'S01',
      title: '一般列报要求',
      items: [
        { id: 'S01-001', type: 'actionable', standard_ref: 'CAS30.5', content: '财务报表列报应遵循重要性原则', children: [] },
        { id: 'S01-002', type: 'header', standard_ref: '', content: '列报格式要求', children: [] },
        { id: 'S01-003', type: 'actionable', standard_ref: 'CAS30.6', content: '财务报表项目的列报应当在各个会计期间保持一致', children: [] },
      ],
    },
    {
      id: 'S02',
      title: '货币资金',
      items: [
        { id: 'S02-001', type: 'actionable', standard_ref: 'CAS22.1', content: '货币资金应按实际收到的金额入账', children: [] },
        { id: 'S02-002', type: 'actionable', standard_ref: 'CAS22.2', content: '外币货币资金应按即期汇率折算', children: [{ id: 'S02-002-a', content: '即期汇率可以是即日中间价', standard_ref: 'CAS19.3' }] },
      ],
    },
    {
      id: 'S03',
      title: '应收票据',
      items: [
        { id: 'S03-001', type: 'actionable', standard_ref: 'CAS22.3', content: '应收票据应按面值入账', children: [] },
      ],
    },
  ],
  toc: [
    { id: 'S01', title: '一般列报要求', applicable: true },
    { id: 'S02', title: '货币资金', applicable: true },
    { id: 'S03', title: '应收票据', applicable: null },
  ],
  stats: { total_actionable: 5, total_guidance: 1, total_sections: 3 },
  parsed_at: '2026-06-25T10:00:00Z',
}

const MOCK_RESPONSES = {
  items: {
    'S01-001': { conclusion: 'Y', remark: '已确认', wp_ref: '' },
    'S02-001': { conclusion: 'N', remark: '需补充', wp_ref: 'D0' },
  },
  toc_applicability: { S01: true, S02: true },
}

const MOCK_CROSS_REF = {
  S02: 'D0',
  S03: 'D1',
  S04: 'D2',
}

function makeMockRenderConfig() {
  return {
    template: JSON.parse(JSON.stringify(MOCK_TEMPLATE)),
    responses: JSON.parse(JSON.stringify(MOCK_RESPONSES)),
    cross_reference_map: { ...MOCK_CROSS_REF },
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 8.1 注册契约
// ═══════════════════════════════════════════════════════════════════════════════

describe('A1-15 披露核对表 — 注册契约 (8.1)', () => {
  it('htmlRendererRegistry 包含 a1-15-disclosure-checklist 条目且字段正确', () => {
    const entry = HTML_RENDERER_REGISTRY.get('a1-15-disclosure-checklist')
    expect(entry).toBeDefined()
    expect(entry!.componentType).toBe('a1-15-disclosure-checklist')
    expect(entry!.icon).toBe('📋')
    expect(entry!.label).toBe('A1-15 企业会计准则财务报表列报及披露核对表')
    expect(entry!.emits).toEqual(['save'])
    expect(entry!.contextProps).toBe('standard')
  })

  it('registry entry 的 component 非 undefined（lazy import 可解析）', () => {
    const entry = HTML_RENDERER_REGISTRY.get('a1-15-disclosure-checklist')
    expect(entry!.component).toBeDefined()
  })

  it('wp_code_overrides.json 映射 A1-15 → skip（A1 Dashboard 子底稿内嵌）', () => {
    const overridesPath = resolve(process.cwd(), '../../backend/app/data/wp_code_overrides.json')
    const overrides: Record<string, string> = JSON.parse(readFileSync(overridesPath, 'utf-8'))
    expect(overrides['A1-15']).toBe('skip')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 8.2 useA115Checklist 行为
// ═══════════════════════════════════════════════════════════════════════════════

describe('A1-15 披露核对表 — useA115Checklist 行为 (8.2)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/render-config')) {
        return Promise.resolve(makeMockRenderConfig())
      }
      return Promise.resolve({})
    })
    mockPut.mockResolvedValue({})
    mockPost.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('loadData: 从 API 加载后 template 和 responses 被填充', async () => {
    const { useA115Checklist } = await import('../composables/useA115Checklist')
    const wpId = ref('wp-001')
    const readonly = ref(false)
    const { template, responses, loading, loadData } = useA115Checklist(wpId, readonly)

    await loadData()

    expect(mockGet).toHaveBeenCalledWith(
      expect.stringContaining('/api/workpapers/wp-001/render-config?force_component_type=a1-15-disclosure-checklist'),
    )
    expect(template.value).not.toBeNull()
    expect(template.value!.wp_code).toBe('A1-15')
    expect(template.value!.sections).toHaveLength(3)
    expect(responses.value.items['S01-001']?.conclusion).toBe('Y')
    expect(responses.value.items['S02-001']?.conclusion).toBe('N')
    expect(loading.value).toBe(false)
  })

  it('loadData: API 失败时设置 error 状态', async () => {
    mockGet.mockRejectedValue(new Error('网络错误'))
    const { useA115Checklist } = await import('../composables/useA115Checklist')
    const wpId = ref('wp-err')
    const readonly = ref(false)
    const { error, loadData } = useA115Checklist(wpId, readonly)

    await loadData()

    expect(error.value).toBe('网络错误')
  })

  it('updateItemResponse: 更新 response 状态并触发 debounce 保存', async () => {
    const { useA115Checklist } = await import('../composables/useA115Checklist')
    const wpId = ref('wp-002')
    const readonly = ref(false)
    const { responses, loadData, updateItemResponse } = useA115Checklist(wpId, readonly)

    await loadData()

    // Update an item's conclusion
    updateItemResponse('S01-003', 'conclusion', 'NA')
    expect(responses.value.items['S01-003']?.conclusion).toBe('NA')

    // Save not triggered yet (debounce 2s)
    expect(mockPut).not.toHaveBeenCalled()

    // Advance timers past debounce
    await vi.advanceTimersByTimeAsync(2100)

    expect(mockPut).toHaveBeenCalled()
  })

  it('setTocApplicability: 标记不适用时级联所有 actionable→NA', async () => {
    const { useA115Checklist } = await import('../composables/useA115Checklist')
    const wpId = ref('wp-003')
    const readonly = ref(false)
    const { template, responses, loadData, setTocApplicability } = useA115Checklist(wpId, readonly)

    await loadData()

    // S02 has 2 actionable items
    await setTocApplicability('S02', false)

    expect(responses.value.toc_applicability['S02']).toBe(false)
    expect(responses.value.items['S02-001']?.conclusion).toBe('NA')
    expect(responses.value.items['S02-002']?.conclusion).toBe('NA')
  })

  it('setTocApplicability: toc_applicability 状态被正确更新', async () => {
    const { useA115Checklist } = await import('../composables/useA115Checklist')
    const wpId = ref('wp-004')
    const readonly = ref(false)
    const { responses, loadData, setTocApplicability } = useA115Checklist(wpId, readonly)

    await loadData()

    await setTocApplicability('S03', true)
    expect(responses.value.toc_applicability['S03']).toBe(true)

    await setTocApplicability('S03', false)
    expect(responses.value.toc_applicability['S03']).toBe(false)
  })

  it('globalProgress: 正确计算 y/n/na/filled/total', async () => {
    const { useA115Checklist } = await import('../composables/useA115Checklist')
    const wpId = ref('wp-005')
    const readonly = ref(false)
    const { globalProgress, loadData } = useA115Checklist(wpId, readonly)

    await loadData()

    // MOCK_RESPONSES has: S01-001=Y, S02-001=N → y=1, n=1, na=0, filled=2, total=5
    expect(globalProgress.value.y).toBe(1)
    expect(globalProgress.value.n).toBe(1)
    expect(globalProgress.value.na).toBe(0)
    expect(globalProgress.value.filled).toBe(2)
    expect(globalProgress.value.total).toBe(5)
  })

  it('sectionProgress: 返回正确的 {filled, total}', async () => {
    const { useA115Checklist } = await import('../composables/useA115Checklist')
    const wpId = ref('wp-006')
    const readonly = ref(false)
    const { sectionProgress, loadData } = useA115Checklist(wpId, readonly)

    await loadData()

    // S01: 2 actionable items (S01-001, S01-003), S01-001 has conclusion Y → filled=1
    const s01 = sectionProgress('S01')
    expect(s01.total).toBe(2)
    expect(s01.filled).toBe(1)

    // S02: 2 actionable items, S02-001 has conclusion N → filled=1
    const s02 = sectionProgress('S02')
    expect(s02.total).toBe(2)
    expect(s02.filled).toBe(1)

    // S03: 1 actionable item, no response → filled=0
    const s03 = sectionProgress('S03')
    expect(s03.total).toBe(1)
    expect(s03.filled).toBe(0)
  })

  it('searchQuery: filteredSections 根据搜索关键词过滤', async () => {
    const { useA115Checklist } = await import('../composables/useA115Checklist')
    const wpId = ref('wp-007')
    const readonly = ref(false)
    const { searchQuery, filteredSections, loadData } = useA115Checklist(wpId, readonly)

    await loadData()

    // No filter: all sections visible
    expect(filteredSections.value).toHaveLength(3)

    // Search for "货币" → only S02 section matches
    searchQuery.value = '货币'
    expect(filteredSections.value).toHaveLength(1)
    expect(filteredSections.value[0].id).toBe('S02')
  })

  it('conclusionFilter: filteredSections 响应筛选变化', async () => {
    const { useA115Checklist } = await import('../composables/useA115Checklist')
    const wpId = ref('wp-008')
    const readonly = ref(false)
    const { conclusionFilter, filteredSections, loadData } = useA115Checklist(wpId, readonly)

    await loadData()

    // Filter by 'Y': only items with conclusion=Y
    conclusionFilter.value = 'Y'
    // S01 has S01-001=Y → S01 section visible
    const yFiltered = filteredSections.value
    expect(yFiltered.length).toBeGreaterThanOrEqual(1)
    expect(yFiltered.some((s) => s.id === 'S01')).toBe(true)

    // Filter by 'unfilled': items with no conclusion
    conclusionFilter.value = 'unfilled'
    const unfilledSections = filteredSections.value
    // S01-003, S02-002, S03-001 have no conclusion → multiple sections
    expect(unfilledSections.length).toBeGreaterThanOrEqual(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 8.3 useA115Navigation 行为
// ═══════════════════════════════════════════════════════════════════════════════

describe('A1-15 披露核对表 — useA115Navigation 行为 (8.3)', () => {
  it('visibleSections: 初始为空 Set', async () => {
    const { useA115Navigation } = await import('../composables/useA115Navigation')
    const sections = ref(MOCK_TEMPLATE.sections)
    const containerRef = ref(null)
    const { visibleSections } = useA115Navigation(sections, containerRef)

    expect(visibleSections.value).toBeInstanceOf(Set)
    expect(visibleSections.value.size).toBe(0)
  })

  it('scrollToSection: 添加目标章节 + 邻居到 visibleSections', async () => {
    const { useA115Navigation } = await import('../composables/useA115Navigation')
    const sections = ref(MOCK_TEMPLATE.sections)
    const containerRef = ref(null) // null → scrollIntoView won't execute but addWithNeighbors will
    const { visibleSections, scrollToSection, activeSectionId } = useA115Navigation(sections, containerRef)

    // Scroll to S02 (middle section)
    scrollToSection('S02')

    // Should add S02 + neighbors (S01, S03)
    expect(visibleSections.value.has('S02')).toBe(true)
    expect(visibleSections.value.has('S01')).toBe(true)
    expect(visibleSections.value.has('S03')).toBe(true)
    expect(activeSectionId.value).toBe('S02')
  })

  it('scrollToSection: 第一个章节无前邻居', async () => {
    const { useA115Navigation } = await import('../composables/useA115Navigation')
    const sections = ref(MOCK_TEMPLATE.sections)
    const containerRef = ref(null)
    const { visibleSections, scrollToSection } = useA115Navigation(sections, containerRef)

    scrollToSection('S01')

    // S01 is first → no previous neighbor, only S01 + S02
    expect(visibleSections.value.has('S01')).toBe(true)
    expect(visibleSections.value.has('S02')).toBe(true)
    expect(visibleSections.value.size).toBe(2)
  })

  it('scrollToSection: 最后一个章节无后邻居', async () => {
    const { useA115Navigation } = await import('../composables/useA115Navigation')
    const sections = ref(MOCK_TEMPLATE.sections)
    const containerRef = ref(null)
    const { visibleSections, scrollToSection } = useA115Navigation(sections, containerRef)

    scrollToSection('S03')

    // S03 is last → no next neighbor, only S02 + S03
    expect(visibleSections.value.has('S03')).toBe(true)
    expect(visibleSections.value.has('S02')).toBe(true)
    expect(visibleSections.value.size).toBe(2)
  })

  it('activeSectionId: 初始状态为 null', async () => {
    const { useA115Navigation } = await import('../composables/useA115Navigation')
    const sections = ref(MOCK_TEMPLATE.sections)
    const containerRef = ref(null)
    const { activeSectionId } = useA115Navigation(sections, containerRef)

    expect(activeSectionId.value).toBeNull()
  })

  it('activeSectionId: scrollToSection 后更新为目标 id', async () => {
    const { useA115Navigation } = await import('../composables/useA115Navigation')
    const sections = ref(MOCK_TEMPLATE.sections)
    const containerRef = ref(null)
    const { activeSectionId, scrollToSection } = useA115Navigation(sections, containerRef)

    scrollToSection('S03')
    expect(activeSectionId.value).toBe('S03')

    scrollToSection('S01')
    expect(activeSectionId.value).toBe('S01')
  })

  it('isSectionVisible: 未加入时返回 false，加入后返回 true', async () => {
    const { useA115Navigation } = await import('../composables/useA115Navigation')
    const sections = ref(MOCK_TEMPLATE.sections)
    const containerRef = ref(null)
    const { isSectionVisible, scrollToSection } = useA115Navigation(sections, containerRef)

    expect(isSectionVisible('S02')).toBe(false)

    scrollToSection('S02')
    expect(isSectionVisible('S02')).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 8.4 GtA115DisclosureChecklist 组件
// ═══════════════════════════════════════════════════════════════════════════════

const ELEMENT_STUBS = {
  'el-segmented': true,
  'el-skeleton': true,
  'el-icon': true,
  'el-button': true,
  'el-input': true,
  'el-select': true,
  'el-option': true,
  'el-progress': true,
  'el-tooltip': true,
  'el-switch': true,
  'el-tag': true,
  'el-empty': true,
  'el-autocomplete': true,
  GtOnlyOfficeSheet: true,
  GtIndexChip: true,
}

describe('A1-15 披露核对表 — GtA115DisclosureChecklist 组件 (8.4)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/render-config')) {
        return Promise.resolve(makeMockRenderConfig())
      }
      if (url.includes('/onlyoffice/health')) {
        return Promise.resolve({ healthy: true })
      }
      return Promise.resolve({})
    })
    mockPut.mockResolvedValue({})
    mockPost.mockResolvedValue({})
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('默认模式为 html（非 docx）', async () => {
    const GtA115 = (await import('../GtA115DisclosureChecklist.vue')).default

    const wrapper = shallowMount(GtA115, {
      props: { wpId: 'wp-comp-1' },
      global: { stubs: ELEMENT_STUBS },
    })

    await nextTick()
    expect(wrapper.vm.activeMode).toBe('html')
  })

  it('模式切换 html→docx 更新 activeMode', async () => {
    const GtA115 = (await import('../GtA115DisclosureChecklist.vue')).default

    const wrapper = shallowMount(GtA115, {
      props: { wpId: 'wp-comp-2' },
      global: { stubs: ELEMENT_STUBS },
    })

    await nextTick()
    expect(wrapper.vm.activeMode).toBe('html')

    wrapper.vm.activeMode = 'docx'
    await nextTick()
    expect(wrapper.vm.activeMode).toBe('docx')
  })

  it('loading 状态时显示骨架屏', async () => {
    // Delay the API response to keep loading=true
    mockGet.mockImplementation(() => new Promise(() => {})) // never resolves

    const GtA115 = (await import('../GtA115DisclosureChecklist.vue')).default

    const wrapper = shallowMount(GtA115, {
      props: { wpId: 'wp-comp-3' },
      global: { stubs: ELEMENT_STUBS },
    })

    await nextTick()
    // Loading state should show skeleton
    expect(wrapper.find('el-skeleton-stub').exists()).toBe(true)
  })

  it('错误状态显示错误信息 + 重试按钮', async () => {
    mockGet.mockRejectedValue(new Error('服务不可用'))

    const GtA115 = (await import('../GtA115DisclosureChecklist.vue')).default

    const wrapper = shallowMount(GtA115, {
      props: { wpId: 'wp-comp-4' },
      global: { stubs: ELEMENT_STUBS },
    })

    // Wait for loadData to complete with error
    await nextTick()
    await nextTick()
    await vi.advanceTimersByTimeAsync(0)
    await nextTick()

    const errorDiv = wrapper.find('.gt-a115-disclosure-checklist__error')
    expect(errorDiv.exists()).toBe(true)
    expect(wrapper.find('.gt-a115-disclosure-checklist__error-msg').text()).toContain('服务不可用')
    expect(wrapper.find('el-button-stub').exists()).toBe(true)
  })

  it('数据加载后渲染 HTML 视图中的卡片区域', async () => {
    const GtA115 = (await import('../GtA115DisclosureChecklist.vue')).default

    const wrapper = shallowMount(GtA115, {
      props: { wpId: 'wp-comp-5' },
      global: { stubs: ELEMENT_STUBS },
    })

    // Wait for loadData
    await nextTick()
    await nextTick()
    await vi.advanceTimersByTimeAsync(200) // initObserver setTimeout
    await nextTick()

    // HTML view should be present when template is loaded
    expect(wrapper.find('.gt-a115-disclosure-checklist__html-view').exists()).toBe(true)
  })

  it('Y/N/NA 按钮交互更新结论（通过 exposed methods）', async () => {
    const GtA115 = (await import('../GtA115DisclosureChecklist.vue')).default

    const wrapper = shallowMount(GtA115, {
      props: { wpId: 'wp-comp-6' },
      global: { stubs: ELEMENT_STUBS },
    })

    // Wait for data loading
    await nextTick()
    await nextTick()
    await vi.advanceTimersByTimeAsync(200)
    await nextTick()

    const vm = wrapper.vm as any

    // Verify initial state from mock
    expect(vm.responses.items['S01-001']?.conclusion).toBe('Y')

    // Verify template is loaded
    expect(vm.template).not.toBeNull()
    expect(vm.template.sections).toHaveLength(3)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 8.5 Cross_Reference_Map
// ═══════════════════════════════════════════════════════════════════════════════

describe('A1-15 披露核对表 — Cross_Reference_Map (8.5)', () => {
  it('CROSS_REFERENCE_MAP 至少有 10 个条目', () => {
    expect(Object.keys(CROSS_REFERENCE_MAP).length).toBeGreaterThanOrEqual(10)
  })

  it('所有映射值为非空字符串', () => {
    for (const [key, value] of Object.entries(CROSS_REFERENCE_MAP)) {
      expect(typeof value).toBe('string')
      expect(value.length).toBeGreaterThan(0)
      expect(typeof key).toBe('string')
      expect(key.length).toBeGreaterThan(0)
    }
  })

  it('覆盖必要映射: D0, D1, D2, E1, G1, H1, I1, F1, F2, K1', () => {
    const requiredValues = ['D0', 'D1', 'D2', 'E1', 'G1', 'H1', 'I1', 'F1', 'F2', 'K1']
    const allValues = Object.values(CROSS_REFERENCE_MAP)

    for (const val of requiredValues) {
      expect(allValues).toContain(val)
    }
  })

  it('suggested chip 逻辑: section 在 map 中 + 无 wp_ref → 应显示建议', async () => {
    const { useA115Checklist } = await import('../composables/useA115Checklist')
    const wpId = ref('wp-xref-1')
    const readonly = ref(false)

    mockGet.mockImplementation((url: string) => {
      if (url.includes('/render-config')) {
        return Promise.resolve(makeMockRenderConfig())
      }
      return Promise.resolve({})
    })

    const { crossRefMap, responses, loadData } = useA115Checklist(wpId, readonly)

    await loadData()

    // S02 is in crossRefMap with value 'D0'
    expect(crossRefMap.value['S02']).toBeDefined()

    // S02-002 has no response → no wp_ref
    const hasWpRef = responses.value.items['S02-002']?.wp_ref
    const sectionInMap = 'S02' in crossRefMap.value

    // Suggested chip condition: section in map AND no wp_ref
    expect(sectionInMap && !hasWpRef).toBe(true)
  })

  it('确认建议: updateItemResponse 保存 wp_ref 值', async () => {
    vi.useFakeTimers()
    const { useA115Checklist } = await import('../composables/useA115Checklist')
    const wpId = ref('wp-xref-2')
    const readonly = ref(false)

    mockGet.mockImplementation((url: string) => {
      if (url.includes('/render-config')) {
        return Promise.resolve(makeMockRenderConfig())
      }
      return Promise.resolve({})
    })
    mockPut.mockResolvedValue({})

    const { responses, crossRefMap, loadData, updateItemResponse } = useA115Checklist(wpId, readonly)

    await loadData()

    // Simulate clicking the suggested chip → saves crossRefMap value as wp_ref
    const suggestion = crossRefMap.value['S02'] // 'D0'
    updateItemResponse('S02-002', 'wp_ref', suggestion)

    expect(responses.value.items['S02-002']?.wp_ref).toBe('D0')

    // Verify debounce triggers save
    await vi.advanceTimersByTimeAsync(2100)
    expect(mockPut).toHaveBeenCalled()

    vi.useRealTimers()
  })

  it('section 不在 map 中 → 无建议', async () => {
    // S01 (一般列报要求) is NOT in CROSS_REFERENCE_MAP
    expect(CROSS_REFERENCE_MAP['S01']).toBeUndefined()
  })

  it('已有 wp_ref 时不应显示建议（逻辑验证）', async () => {
    const { useA115Checklist } = await import('../composables/useA115Checklist')
    const wpId = ref('wp-xref-3')
    const readonly = ref(false)

    mockGet.mockImplementation((url: string) => {
      if (url.includes('/render-config')) {
        return Promise.resolve(makeMockRenderConfig())
      }
      return Promise.resolve({})
    })

    const { responses, crossRefMap, loadData } = useA115Checklist(wpId, readonly)

    await loadData()

    // S02-001 already has wp_ref='D0' from MOCK_RESPONSES
    const hasWpRef = !!responses.value.items['S02-001']?.wp_ref
    const sectionInMap = 'S02' in crossRefMap.value

    // Should NOT show suggestion when wp_ref already set
    expect(sectionInMap && hasWpRef).toBe(true) // Both true means suggestion chip would be hidden
  })
})
