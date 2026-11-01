/**
 * useQueryEntry（advanced-query-linkage-closure 任务 46，design §4.3；ADR-AQL-20）
 *
 * 判据：应用入口会写项目 / 年度 / 数据源并执行一次；切换保留筛选（switch 自带 filters 时按它换）；
 * 下钻压栈最多 5 层、返回出栈；手动换源自动清除；清除后筛选为空。
 */
import { describe, expect, it, vi } from 'vitest'

import { MAX_ENTRY_DEPTH, useQueryEntry } from '../useQueryEntry'
import type { QueryEntryRequest } from '@/components/query/queryEntryContext'

const LEDGER_SWITCHES = [
  { source: 'ledger_entries', label: '序时账' },
  { source: 'account_balance', label: '科目余额' },
  { source: 'aux_balance', label: '辅助余额' },
  { source: 'aux_ledger', label: '辅助明细' },
]

function entryOf(over: Partial<QueryEntryRequest> = {}): QueryEntryRequest {
  return {
    kind: 'tb_row', projectId: 'p-1', year: 2025, source: 'ledger_entries',
    filters: { account_code: '1002' }, label: '试算表 1002 银行存款',
    switches: LEDGER_SWITCHES, ...over,
  }
}

function harness() {
  const apply = vi.fn()
  return { apply, ctl: useQueryEntry({ apply }) }
}

describe('应用入口', () => {
  it('写项目 / 年度 / 数据源并执行一次', async () => {
    const { apply, ctl } = harness()
    await ctl.applyEntry(entryOf())
    expect(apply).toHaveBeenCalledTimes(1)
    expect(apply).toHaveBeenCalledWith({ projectId: 'p-1', year: 2025, source: 'ledger_entries' })
    expect(ctl.active.value).toBe(true)
    expect(ctl.filters.value).toEqual({ account_code: '1002' })
    expect(ctl.depth.value).toBe(1)
    expect(ctl.canGoBack.value).toBe(false)
  })

  it('入口没有年度时不传 year（交弹窗按项目审计年度解析）', async () => {
    const { apply, ctl } = harness()
    const { year: _drop, ...noYear } = entryOf()
    await ctl.applyEntry(noYear as QueryEntryRequest)
    expect(apply).toHaveBeenCalledWith({ projectId: 'p-1', source: 'ledger_entries' })
    expect(ctl.entry.value?.year).toBeUndefined()
  })

  it('应用新入口会清空下钻栈（这是一条新的查询链）', async () => {
    const { ctl } = harness()
    await ctl.applyEntry(entryOf())
    await ctl.drillDown(entryOf({ label: '下钻', filters: { account_code: '100201' } }))
    expect(ctl.canGoBack.value).toBe(true)
    await ctl.applyEntry(entryOf({ label: '新入口' }))
    expect(ctl.canGoBack.value).toBe(false)
    expect(ctl.depth.value).toBe(1)
  })
})

describe('切换数据源', () => {
  it('沿用当前筛选换源', async () => {
    const { apply, ctl } = harness()
    await ctl.applyEntry(entryOf())
    await ctl.switchSource({ source: 'aux_ledger', label: '辅助明细' })
    expect(apply).toHaveBeenLastCalledWith({ projectId: 'p-1', year: 2025, source: 'aux_ledger' })
    expect(ctl.filters.value).toEqual({ account_code: '1002' })
    expect(ctl.entry.value?.source).toBe('aux_ledger')
    expect(ctl.entry.value?.label).toBe('试算表 1002 银行存款')
  })

  it('switch 自带 filters 时按它换（附注章节 → 相关科目）', async () => {
    const { ctl } = harness()
    await ctl.applyEntry(entryOf({
      kind: 'note_section', source: 'disclosure_note:八、1', filters: {},
      switches: [
        { source: 'disclosure_note:八、1', label: '附注表格', filters: {} },
        { source: 'tb_detail', label: '相关科目（试算表）', filters: { note_section: '八、1' } },
      ],
    }))
    await ctl.switchSource({ source: 'tb_detail', label: '相关科目（试算表）', filters: { note_section: '八、1' } })
    expect(ctl.filters.value).toEqual({ note_section: '八、1' })
    expect(ctl.entry.value?.source).toBe('tb_detail')
  })

  it('切到当前源不重复执行；没有上下文时什么都不做', async () => {
    const { apply, ctl } = harness()
    await ctl.switchSource({ source: 'aux_ledger', label: '辅助明细' })
    expect(apply).not.toHaveBeenCalled()
    await ctl.applyEntry(entryOf())
    await ctl.switchSource({ source: 'ledger_entries', label: '序时账' })
    expect(apply).toHaveBeenCalledTimes(1)
  })
})

describe('下钻与返回', () => {
  it('压栈后可逐层返回，回到的是上一层那次查询', async () => {
    const { apply, ctl } = harness()
    await ctl.applyEntry(entryOf({ source: 'tb_detail', filters: { report_row: 'balance_sheet:BS-002' } }))
    await ctl.drillDown(entryOf({ label: '1002 银行存款 序时账' }))
    expect(ctl.depth.value).toBe(2)
    expect(ctl.entry.value?.label).toBe('1002 银行存款 序时账')

    await ctl.goBack()
    expect(ctl.depth.value).toBe(1)
    expect(ctl.filters.value).toEqual({ report_row: 'balance_sheet:BS-002' })
    expect(apply).toHaveBeenLastCalledWith({ projectId: 'p-1', year: 2025, source: 'tb_detail' })
    expect(ctl.canGoBack.value).toBe(false)
  })

  it(`层数上限 ${MAX_ENTRY_DEPTH}：到顶后仍执行但不再压栈`, async () => {
    const { ctl } = harness()
    await ctl.applyEntry(entryOf())
    for (let i = 0; i < MAX_ENTRY_DEPTH + 3; i += 1) {
      await ctl.drillDown(entryOf({ label: `第 ${i} 跳` }))
    }
    expect(ctl.depth.value).toBe(MAX_ENTRY_DEPTH)
    expect(ctl.entry.value?.label).toBe(`第 ${MAX_ENTRY_DEPTH + 2} 跳`)
  })

  it('栈空时返回不做任何事', async () => {
    const { apply, ctl } = harness()
    await ctl.applyEntry(entryOf())
    await ctl.goBack()
    expect(apply).toHaveBeenCalledTimes(1)
  })
})

describe('清除', () => {
  it('清除后没有上下文、筛选为空', async () => {
    const { ctl } = harness()
    await ctl.applyEntry(entryOf())
    ctl.clear()
    expect(ctl.active.value).toBe(false)
    expect(ctl.filters.value).toEqual({})
    expect(ctl.switches.value).toEqual([])
    expect(ctl.depth.value).toBe(0)
  })

  it('用户手动换到上下文不认识的源 ⇒ 自动清除（筛选键带到不认它的源会 400）', async () => {
    const { ctl } = harness()
    await ctl.applyEntry(entryOf())
    ctl.onSourceChangedByUser('report_balance_sheet')
    expect(ctl.active.value).toBe(false)
  })

  it('换到切换列表里的源 / 当前源 ⇒ 保留上下文（经切换按钮走的就是这条）', async () => {
    const { ctl } = harness()
    await ctl.applyEntry(entryOf())
    ctl.onSourceChangedByUser('aux_ledger')
    expect(ctl.active.value).toBe(true)
    ctl.onSourceChangedByUser('ledger_entries')
    expect(ctl.active.value).toBe(true)
  })

  it('没有上下文时手动换源不报错', () => {
    const { ctl } = harness()
    expect(() => ctl.onSourceChangedByUser('tb_detail')).not.toThrow()
  })
})
