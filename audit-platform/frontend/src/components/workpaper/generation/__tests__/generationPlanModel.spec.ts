/**
 * 生成计划弹窗纯函数（spec trim-generation-plan-linkage R2）：循环顺序、默认勾选、发送的编码只取「将生成」、
 * 未保存粗裁提醒、按程序行分组、粗裁状态文字。
 */
import { describe, it, expect } from 'vitest'
import type { GenerationPlan, PlanCycle, PlanItem } from '@/services/generationPlanApi'
import { fmtDate, parseServerTime } from '@/utils/formatters'
import {
  codesToGenerate, cycleLabel, defaultSelectedCycles, groupItemsByProgram, isCycleSelectable,
  orderCycles, pendingTrimCycles, selectedSummary, trimStateText,
} from '../generationPlanModel'

function item(wp_code: string, state: PlanItem['state'], extra: Partial<PlanItem> = {}): PlanItem {
  return {
    wp_code, wp_name: `底稿${wp_code}`, state, decided_by: null, follows_children: false,
    category_applicable: true, category_reason: null, category_conflict: false, ...extra,
  }
}

function cycle(code: string, items: PlanItem[], extra: Partial<PlanCycle> = {}): PlanCycle {
  const counts = { total: items.length, to_create: 0, existing: 0, in_recycle: 0, trimmed: 0, category_excluded: 0 }
  for (const it of items) counts[it.state] += 1
  return { cycle: code, trim_state: 'confirmed', confirmed_at: null, confirmed_by: null, counts, programs: [], items, ...extra }
}

function plan(cycles: PlanCycle[]): GenerationPlan {
  return {
    template_set: { id: 's1', set_name: '标准年审', code_count: 0 },
    business_category: { code: 'C', defaulted: true },
    totals: { total: 0, to_create: 0, existing: 0, in_recycle: 0, trimmed: 0, category_excluded: 0 },
    cycles,
  }
}

const D = cycle('D', [
  item('D2', 'trimmed', { decided_by: 'D2-1至D2-4', follows_children: true }),
  item('D2-1', 'trimmed', { decided_by: 'D2-1至D2-4' }),
  item('D0', 'existing', { decided_by: 'D0' }),
  item('D4', 'to_create'),
  item('D4-5', 'to_create', { decided_by: 'D4-5' }),
], {
  programs: [
    { code: 'D0', name: '收入循环函证', status: 'execute', skip_reason: null, origin: 'catalog' },
    { code: 'D2-1至D2-4', name: '应收账款审定表明细表', status: 'not_applicable', skip_reason: '无', origin: 'catalog' },
    { code: 'D4-5', name: '营业收入-会计政策', status: 'execute', skip_reason: null, origin: 'catalog' },
  ],
})
const A = cycle('A', [item('A17', 'category_excluded'), item('A1', 'to_create')], { trim_state: 'unconfirmed' })
const B = cycle('B', [item('B5-1', 'in_recycle')], { trim_state: 'not_initialized' })
const Z = cycle('Z', [item('ZZ9', 'to_create')], { trim_state: 'not_initialized' })

describe('generationPlanModel', () => {
  it('循环按裁剪页页签顺序（B…N、A、S），其他排最后', () => {
    expect(orderCycles([Z, A, D, B]).map((c) => c.cycle)).toEqual(['B', 'D', 'A', 'Z'])
    expect(cycleLabel('D')).toBe('D 收入')
    expect(cycleLabel('Z')).toBe('Z')
  })

  it('默认勾选：给了初始循环只勾它；它没有可生成的就一个不勾；否则勾全部可生成的', () => {
    const p = plan([D, A, B, Z])
    expect(isCycleSelectable(B)).toBe(false)
    expect(defaultSelectedCycles(p, 'D')).toEqual(['D'])
    expect(defaultSelectedCycles(p, 'B')).toEqual([])
    expect(defaultSelectedCycles(p)).toEqual(['D', 'A', 'Z'])
    expect(defaultSelectedCycles(null)).toEqual([])
  })

  it('发送的编码只取所选循环里「将生成」的，保持计划顺序', () => {
    const p = plan([D, A, B, Z])
    expect(codesToGenerate(p, ['A', 'D'])).toEqual(['D4', 'D4-5', 'A1'])
    expect(codesToGenerate(p, [])).toEqual([])
    expect(selectedSummary(p, ['D', 'Z'])).toEqual({ cycles: 2, codes: 3 })
  })

  it('未保存粗裁、且有会生成 / 按业务分类不生成的循环才提醒', () => {
    const p = plan([D, A, B, Z])
    expect(pendingTrimCycles(p).map((c) => c.cycle)).toEqual(['A', 'Z'])
  })

  it('按程序行分组：科目审定表单列在最前，程序行按裁剪页顺序，尚无程序行的最后', () => {
    const groups = groupItemsByProgram(D)
    expect(groups.map((g) => g.key)).toEqual(['__follow__', 'D0', 'D2-1至D2-4', 'D4-5', '__none__'])
    expect(groups[0]).toMatchObject({ code: null, status: null, label: '科目审定表（跟随本科目的程序行）' })
    expect(groups[0].items.map((i) => i.wp_code)).toEqual(['D2'])
    expect(groups[2]).toMatchObject({ code: 'D2-1至D2-4', status: 'not_applicable', label: 'D2-1至D2-4 应收账款审定表明细表' })
    expect(groups[4].items.map((i) => i.wp_code)).toEqual(['D4'])
  })

  it('粗裁状态文字：已保存带人和本地日期', () => {
    const ts = '2026-10-27T17:30:00+00:00'
    expect(trimStateText({ trim_state: 'confirmed', confirmed_by: '王经理', confirmed_at: ts }))
      .toBe(`已保存（王经理 ${fmtDate(parseServerTime(ts))}）`)
    expect(trimStateText({ trim_state: 'confirmed', confirmed_by: null, confirmed_at: null })).toBe('已保存')
    expect(trimStateText({ trim_state: 'unconfirmed', confirmed_by: null, confirmed_at: null })).toBe('未保存')
    expect(trimStateText({ trim_state: 'not_initialized', confirmed_by: null, confirmed_at: null })).toBe('未打开')
  })
})
