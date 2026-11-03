/**
 * QueryEntryBanner（advanced-query-linkage-closure 任务 46，design §4.3；N5 可访问性）
 *
 * 判据：没有上下文时不渲染；显示 label 与 `meta.entry_accounts`；当前源的切换按钮置灰；
 * 三个动作各自 emit；按钮带 aria-label。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import QueryEntryBanner from '../QueryEntryBanner.vue'
import type { QueryEntryRequest } from '../queryEntryContext'

const ENTRY: QueryEntryRequest = {
  kind: 'tb_row', projectId: 'p-1', year: 2025, source: 'ledger_entries',
  filters: { account_code: '1002' }, label: '试算表 1002 银行存款',
  switches: [
    { source: 'ledger_entries', label: '序时账' },
    { source: 'aux_ledger', label: '辅助明细' },
  ],
}

const stubs = {
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  // 只声明 disabled 为 prop：aria-label 要留在 attrs 里落到真实 <button> 上（否则 N5 判据测不到）；
  // 声明 emits: ['click'] 让父组件的 @click 不再作为透传属性重复触发一次
  'el-button': {
    props: ['disabled'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
}

function banner(props: Record<string, unknown> = {}) {
  return mount(QueryEntryBanner, { props: { entry: ENTRY, ...props }, global: { stubs } })
}

describe('QueryEntryBanner', () => {
  it('没有上下文时整块不渲染', () => {
    const w = mount(QueryEntryBanner, { props: { entry: null }, global: { stubs } })
    expect(w.find('[data-testid="query-entry-banner"]').exists()).toBe(false)
  })

  it('显示入口说明与后端解析出的科目', () => {
    const w = banner({ meta: { entry_accounts: ['1001', '1002', '1012'] } })
    expect(w.find('[data-testid="qeb-label"]').text()).toBe('试算表 1002 银行存款')
    expect(w.find('[data-testid="qeb-accounts"]').text()).toContain('1001')
    expect(w.find('[data-testid="qeb-accounts"]').text()).toContain('1012')
  })

  it('meta 没有 entry_accounts 时不显示科目区', () => {
    expect(banner({ meta: { column_types: {} } }).find('[data-testid="qeb-accounts"]').exists()).toBe(false)
    expect(banner({ meta: null }).find('[data-testid="qeb-accounts"]').exists()).toBe(false)
  })

  it('解析出的科目达到 50 个上限时提示只显示前 N 个（后端截断）', () => {
    const codes = Array.from({ length: 50 }, (_, i) => `${1000 + i}`)
    expect(banner({ meta: { entry_accounts: codes } }).find('[data-testid="qeb-accounts"]').text())
      .toContain('仅显示前 50 个')
  })

  it('当前数据源的切换按钮置灰，其他可点并 emit switch', async () => {
    const w = banner()
    const current = w.find('[data-testid="qeb-switch-ledger_entries"]')
    const other = w.find('[data-testid="qeb-switch-aux_ledger"]')
    expect(current.attributes('disabled')).toBeDefined()
    expect(other.attributes('disabled')).toBeUndefined()
    await other.trigger('click')
    expect(w.emitted('switch')?.[0]).toEqual([{ source: 'aux_ledger', label: '辅助明细' }])
  })

  it('「返回上一查询」只在可返回时出现，并显示层数', () => {
    expect(banner().find('[data-testid="qeb-back"]').exists()).toBe(false)
    expect(banner().find('[data-testid="qeb-depth"]').exists()).toBe(false)
    const deep = banner({ canGoBack: true, depth: 2 })
    expect(deep.find('[data-testid="qeb-back"]').exists()).toBe(true)
    expect(deep.find('[data-testid="qeb-depth"]').text()).toBe('第 2 层')
  })

  it('返回与清除各自 emit', async () => {
    const w = banner({ canGoBack: true, depth: 2 })
    await w.find('[data-testid="qeb-back"]').trigger('click')
    await w.find('[data-testid="qeb-clear"]').trigger('click')
    expect(w.emitted('back')).toHaveLength(1)
    expect(w.emitted('clear')).toHaveLength(1)
  })

  it('每个按钮都带 aria-label（N5）', () => {
    const w = banner({ canGoBack: true, depth: 2 })
    const labels = w.findAll('button').map((b) => b.attributes('aria-label'))
    expect(labels.every((x) => !!x && x.length > 0)).toBe(true)
    expect(labels).toContain('切换到辅助明细')
    expect(labels).toContain('返回上一查询')
    expect(labels).toContain('清除入口上下文')
  })
})
