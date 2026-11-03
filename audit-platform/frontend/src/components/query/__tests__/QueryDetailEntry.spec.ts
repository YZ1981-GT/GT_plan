/**
 * QueryDetailEntry（advanced-query-linkage-closure 任务 47，design §4.3、§10.1；ADR-AQL-20，变异 #34）
 *
 * 判据：合计行与空目标置灰并显示原因、置灰时不发事件；点击发出带 `entry` 的 `open-custom-query` 并 emit `opened`；
 * `year` prop 变化后发出的 entry 年度随之变化（附注编辑器页内切年）；两种变体的落地元素。
 */
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const emitted: Array<[string, unknown]> = []
vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: (name: string, payload?: unknown) => { emitted.push([name, payload]) } },
}))

const route = { name: 'TrialBalance', params: { projectId: 'p-1' } as Record<string, unknown>, query: {} }
vi.mock('vue-router', () => ({ useRoute: () => route }))

import QueryDetailEntry from '../QueryDetailEntry.vue'
import { ENTRY_NO_PROJECT, ENTRY_TB_TOTAL_ROW, ENTRY_WP_NO_CODE } from '../queryEntryContext'

const stubs = {
  'el-button': {
    props: ['disabled'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
}

type EntryProps = InstanceType<typeof QueryDetailEntry>['$props']

function entryFor(props: EntryProps) {
  return mount(QueryDetailEntry, { props, global: { stubs } })
}

const TB_ROW = { standard_account_code: '1002', account_name: '银行存款' }

beforeEach(() => {
  emitted.length = 0
  route.params = { projectId: 'p-1' }
})

describe('点击发事件', () => {
  it('ctx 变体：发出带 entry 的 open-custom-query，并 emit opened 供宿主关右键菜单', async () => {
    const w = entryFor({ kind: 'tb_row', target: TB_ROW, variant: 'ctx', year: 2025 })
    const item = w.find('[data-testid="query-detail-entry"]')
    expect(item.classes()).toContain('gt-ucell-ctx-item')
    await item.trigger('click')

    expect(emitted).toHaveLength(1)
    expect(emitted[0][0]).toBe('open-custom-query')
    expect(emitted[0][1]).toEqual({
      entry: {
        kind: 'tb_row', projectId: 'p-1', year: 2025, source: 'ledger_entries',
        filters: { account_code: '1002' }, label: '试算表 1002 银行存款',
        switches: [
          { source: 'ledger_entries', label: '序时账' },
          { source: 'account_balance', label: '科目余额' },
          { source: 'aux_balance', label: '辅助余额' },
          { source: 'aux_ledger', label: '辅助明细' },
        ],
      },
    })
    expect(w.emitted('opened')).toHaveLength(1)
  })

  it('button 变体：渲染为按钮，可自定义文案', async () => {
    const w = entryFor({
      kind: 'workpaper', target: { wp_code: 'E1', wp_name: '货币资金' },
      variant: 'button', year: 2025, label: '查明细',
    })
    const button = w.find('[data-testid="query-detail-entry"]')
    expect(button.element.tagName).toBe('BUTTON')
    expect(button.text()).toContain('查明细')
    await button.trigger('click')
    expect((emitted[0][1] as any).entry.filters).toEqual({ wp_code: 'E1' })
  })
})

describe('不可用时置灰、不发事件、原因可见', () => {
  const cases: Array<[string, EntryProps, string]> = [
    ['合计行', { kind: 'tb_row', target: { ...TB_ROW, _isTotal: true } }, ENTRY_TB_TOTAL_ROW],
    ['空目标', { kind: 'workpaper', target: null }, ENTRY_WP_NO_CODE],
  ]

  it.each(cases)('%s', async (_name, props, expected) => {
    const w = entryFor({ ...props, variant: 'ctx', year: 2025 })
    const item = w.find('[data-testid="query-detail-entry"]')
    expect(item.attributes('title')).toBe(expected)
    expect(item.classes()).toContain('is-disabled')
    expect(item.attributes('aria-disabled')).toBe('true')
    await item.trigger('click')
    expect(emitted).toHaveLength(0)
    expect(w.emitted('opened')).toBeUndefined()
  })

  it('button 变体置灰时按钮 disabled 且 title 是原因', () => {
    route.params = {} // 非项目页
    const w = entryFor({ kind: 'tb_row', target: TB_ROW, variant: 'button', year: 2025 })
    const button = w.find('[data-testid="query-detail-entry"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.attributes('title')).toBe(ENTRY_NO_PROJECT)
  })
})

describe('年度来自宿主（§16 #7，变异 #34）', () => {
  it('year prop 变化后发出的 entry 年度随之变化（附注编辑器页内切年不写路由）', async () => {
    const w = entryFor({
      kind: 'note_section', target: { note_section: '八、1', section_title: '货币资金' },
      variant: 'ctx', year: 2025,
    })
    await w.find('[data-testid="query-detail-entry"]').trigger('click')
    expect((emitted[0][1] as any).entry.year).toBe(2025)

    await w.setProps({ year: 2024 })
    await w.find('[data-testid="query-detail-entry"]').trigger('click')
    expect((emitted[1][1] as any).entry.year).toBe(2024)
  })

  it('宿主年度为 null 时不带 year（交弹窗按项目审计年度解析，不按日历年兜底）', async () => {
    const w = entryFor({ kind: 'tb_row', target: TB_ROW, variant: 'ctx', year: null })
    await w.find('[data-testid="query-detail-entry"]').trigger('click')
    expect('year' in (emitted[0][1] as any).entry).toBe(false)
  })

  it('目标自带年度时优先于宿主年度（报表穿透用 drilldownData.year）', async () => {
    const w = entryFor({
      kind: 'report_row',
      target: { report_type: 'balance_sheet', row_code: 'BS-002', row_name: '货币资金', year: 2023 },
      variant: 'button', year: 2025,
    })
    await w.find('[data-testid="query-detail-entry"]').trigger('click')
    expect((emitted[0][1] as any).entry.year).toBe(2023)
    expect((emitted[0][1] as any).entry.filters).toEqual({ report_row: 'balance_sheet:BS-002' })
  })

  it('目标行变化后重新计算（同一组件实例换行）', async () => {
    const w = entryFor({ kind: 'tb_row', target: TB_ROW, variant: 'ctx', year: 2025 })
    await w.setProps({ target: { standard_account_code: '1001', account_name: '库存现金' } })
    await w.find('[data-testid="query-detail-entry"]').trigger('click')
    expect((emitted[0][1] as any).entry.filters).toEqual({ account_code: '1001' })
  })
})
