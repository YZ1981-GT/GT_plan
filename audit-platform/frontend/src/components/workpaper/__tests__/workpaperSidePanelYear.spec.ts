/**
 * 底稿面板的年度：公式 / 一致性子面板按项目审计年度取数、校验引用（spec formula-fetch-and-wp-generation-defect-closure，
 * 浏览器实测发现）。
 *
 * 原先面板恒取日历年 —— 2025 年度项目在 2026 年打开时，公式面板按 2026 求值，保存提取公式时按 2026 校验引用
 * ⇒ 本年试算表里有的科目也判「引用地址不存在」（和平 2025 实测：TB('1122','期末余额') 按 2025 校验有效、按 2026 无效）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue({}) } }))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() } }))

function stub(name: string) {
  return { default: defineComponent({ name, props: ['projectId', 'wpId', 'year'], template: '<div />' }) }
}
vi.mock('@/components/workpaper/FormulaStatusPanel.vue', () => stub('FormulaStatusPanel'))
vi.mock('@/components/workpaper/CrossCheckPanel.vue', () => stub('CrossCheckPanel'))
vi.mock('@/components/workpaper/AttachmentTabPanel.vue', () => stub('AttachmentTabPanel'))
vi.mock('@/components/workpaper/ProgramRequirementsSidebar.vue', () => stub('ProgramRequirementsSidebar'))
vi.mock('@/components/workpaper/ProcedurePanel.vue', () => stub('ProcedurePanel'))
vi.mock('@/components/workpaper/DependencyGraph.vue', () => stub('DependencyGraph'))
vi.mock('@/components/workpaper/CellAnnotationPanel.vue', () => stub('CellAnnotationPanel'))
vi.mock('@/components/workpaper/EvidenceLinkPanel.vue', () => stub('EvidenceLinkPanel'))
vi.mock('@/components/workpaper/PbcCollectionTab.vue', () => stub('PbcCollectionTab'))
vi.mock('@/components/workpaper/SnapshotCompare.vue', () => stub('SnapshotCompare'))
vi.mock('@/components/workpaper/WpVersionHistoryPanel.vue', () => stub('WpVersionHistoryPanel'))
vi.mock('@/components/workpaper/QualityScoreBadge.vue', () => stub('QualityScoreBadge'))
vi.mock('@/components/workpaper/WpDecisionTracePanel.vue', () => stub('WpDecisionTracePanel'))

import WorkpaperSidePanel from '../WorkpaperSidePanel.vue'

// 页签全部直接渲染（真实 el-tabs 懒加载，只渲染当前页签）
const passthrough = { template: '<div><slot name="label" /><slot /></div>' }
const STUBS = {
  ElTabs: passthrough, ElTabPane: passthrough, ElBadge: true, ElButton: true,
  ElRadioGroup: passthrough, ElRadioButton: true, ElTag: true,
}

function mountPanel(props: Record<string, unknown>) {
  return mount(WorkpaperSidePanel, {
    props: { projectId: 'p1', wpId: 'wp1', wpCode: 'D2', ...props },
    global: { stubs: STUBS, directives: { loading: {} } },
  })
}

function yearOf(wrapper: ReturnType<typeof mountPanel>, name: string): unknown {
  return wrapper.findComponent({ name }).props('year')
}

describe('底稿面板按项目审计年度传年度', () => {
  afterEach(() => { vi.useRealTimers() })

  it('宿主传了项目年度：公式面板与一致性面板都用它（不是日历年）', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-23T10:00:00Z'))
    const wrapper = mountPanel({ year: 2025 })
    expect(yearOf(wrapper, 'FormulaStatusPanel')).toBe(2025)
    expect(yearOf(wrapper, 'CrossCheckPanel')).toBe(2025)
    wrapper.unmount()
  })

  it('取不到项目年度：与编辑器其余子组件同一兜底（上一日历年）', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-23T10:00:00Z'))
    const wrapper = mountPanel({ year: null })
    expect(yearOf(wrapper, 'FormulaStatusPanel')).toBe(2025)
    wrapper.unmount()
  })

  it('底稿编辑器把项目审计年度传给面板', () => {
    const src = readFileSync(resolve(__dirname, '../../../views/WorkpaperEditor.vue'), 'utf-8')
    const tag = src.match(/<WorkpaperSidePanel\b[^>]*?\/>/)
    expect(tag, 'WorkpaperEditor.vue 里找不到 <WorkpaperSidePanel … />').not.toBeNull()
    expect(tag![0]).toMatch(/:year="projectYear"/)
  })
})
