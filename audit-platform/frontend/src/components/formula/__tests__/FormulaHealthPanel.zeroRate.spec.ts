import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get } }))
vi.mock('@/composables/formula/useFormulaSettings', () => ({ formulaErrorText: (_error: unknown, fallback: string) => fallback }))
import FormulaHealthPanel from '@/components/formula/FormulaHealthPanel.vue'

const wrappers: VueWrapper[] = []
beforeEach(() => { get.mockReset() })
afterEach(() => { wrappers.splice(0).forEach(wrapper => { wrapper.unmount() }) })
function healthy(crossCheck: unknown) {
  return { push_coverage: { percentage: 100 }, push_success_rate: { has_run: true, success_rate: 100 },
    formula_config_rate: { coverage_rate: 100 }, pending_conflicts: { pending: 0 },
    cross_check_pass_rate: crossCheck, stale_ratio: { report_stale_rate: 0 } }
}
async function render(data: unknown) {
  get.mockResolvedValue(data)
  const wrapper = shallowMount(FormulaHealthPanel, {
    props: { projectId: 'synthetic-project', year: 2025 },
    global: {
      directives: { loading: () => {} },
      stubs: { 'el-alert': true, 'el-table': true, 'el-table-column': true, 'el-tag': true },
    },
  })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}

describe('健康面板真实零通过率', () => {
  it.each([
    ['零通过率', { has_results: true, pass_rate: 0 }, 85, '0%'],
    ['有结果缺失通过率', { has_results: true }, 85, '0%'],
    ['有结果空通过率', { has_results: true, pass_rate: null }, 85, '0%'],
    ['半数通过', { has_results: true, pass_rate: 50 }, 93, '50%'],
    ['全部通过', { has_results: true, pass_rate: 100 }, 100, '100%'],
    ['无结果', { has_results: false, pass_rate: 0 }, 100, '—'],
    ['尚无维度', undefined, 100, '—'],
  ])('%s：显示真实维度并按原权重计分', async (_label, metric, score, dimension) => {
    const wrapper = await render(healthy(metric))
    expect(wrapper.get('.gt-fh-score-value').text()).toBe(`${score}%`)
    expect(wrapper.findAll('.gt-fh-card-value')[4].text()).toBe(dimension)
    expect(get).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ _silent: true }))
  })
})

it('公式配置率查询失败显示不可用而不是 0%', async () => {
  const wrapper = await render({
    ...healthy({ has_results: false }),
    formula_config_rate: {
      available: false,
      coverage_rate: null,
      message: '公式配置率暂时无法读取',
    },
  })
  expect(wrapper.findAll('.gt-fh-card-value')[2].text()).toBe('—')
  expect(wrapper.findAll('.gt-fh-card-desc')[2].text()).toBe('公式配置率暂时无法读取')
  expect(wrapper.get('.gt-fh-score-value').text()).toBe('—')
})
