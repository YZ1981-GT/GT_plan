/**
 * h0SummaryFromEntityVerify.spec.ts — H0-1 ← H0-2 带入行为守卫
 *
 * spec: h0-confirmation-source-fidelity-and-linkage
 *   Requirements 5.1~5.6；Property 14 / 15
 *
 * 与源模板 VLOOKUP 列序的**逐条交叉锁死**在
 * `backend/tests/test_h0_source_template_facts.py::test_frontend_pull_mapping_matches_vlookup`
 * （前端读不了 xlsx）；本文件负责映射自洽性与带入行为（手工优先 / 幂等 / 空索引跳过）。
 */
import { describe, it, expect } from 'vitest'
import {
  H0_PULL_FROM_ENTITY_VERIFY,
  buildEntityIndex,
  describeH0PullResult,
  pullH0SummaryFromEntityVerify,
  resolvePullValue,
} from '../h0SummaryFromEntityVerify'
import type { ConfirmationRow } from '../confirmationTypes'
import type { EntityVerifyRow } from '../entityVerify/entityVerifyTypes'

function sRow(p: Partial<ConfirmationRow>): ConfirmationRow {
  return { _row_id: `s-${Math.random().toString(36).slice(2)}`, ...p } as ConfirmationRow
}

function eRow(p: Partial<EntityVerifyRow>): EntityVerifyRow {
  return { _row_id: `e-${Math.random().toString(36).slice(2)}`, ...p } as EntityVerifyRow
}

const FULL_ENTITY = eRow({
  confirm_index: 'H0-001',
  entity_name: '甲供应商',
  first_send_method: '邮寄',
  entity_address: '北京市朝阳区XX路 1 号',
  address_match: 'consistent',
  reply_method: '纸质原件',
  reply_from_addr: '北京市朝阳区XX路 1 号',
  reply_addr_match: 'inconsistent',
})

// ─── 映射自洽性 ──────────────────────────────────────────────────────────────

describe('映射声明自洽', () => {
  it('7 条映射，targetColumn / sourceColumnIndex 均唯一', () => {
    expect(H0_PULL_FROM_ENTITY_VERIFY).toHaveLength(7)
    const cols = H0_PULL_FROM_ENTITY_VERIFY.map((s) => s.targetColumn)
    const idxs = H0_PULL_FROM_ENTITY_VERIFY.map((s) => s.sourceColumnIndex)
    expect(new Set(cols).size).toBe(7)
    expect(new Set(idxs).size).toBe(7)
  })

  it('col_index_num 与源模板一致（2/3/4/10/16/19/22）', () => {
    const map = Object.fromEntries(
      H0_PULL_FROM_ENTITY_VERIFY.map((s) => [s.targetColumn, s.sourceColumnIndex]),
    )
    expect(map).toEqual({ D: 2, G: 3, J: 4, K: 10, M: 16, Q: 19, R: 22 })
  })

  it('每条都有 label 与 sourceField', () => {
    for (const s of H0_PULL_FROM_ENTITY_VERIFY) {
      expect(s.label.trim().length).toBeGreaterThan(1)
      expect(s.sourceField.trim().length).toBeGreaterThan(1)
      expect(s.targetKey.trim().length).toBeGreaterThan(1)
    }
  })

  it('函证方式带入目标是 send_channel 而非 confirmation_method', () => {
    const targets = H0_PULL_FROM_ENTITY_VERIFY.map((s) => s.targetKey)
    expect(targets).toContain('send_channel')
    expect(targets).not.toContain('confirmation_method')
  })
})

// ─── 口径转换 ────────────────────────────────────────────────────────────────

describe('resolvePullValue 口径转换', () => {
  const addrSpec = H0_PULL_FROM_ENTITY_VERIFY.find((s) => s.targetKey === 'send_addr_match')!
  const nameSpec = H0_PULL_FROM_ENTITY_VERIFY.find((s) => s.targetKey === 'entity_name')!

  it('一致性三态 → 是/否；pending 不带入（宁缺勿造）', () => {
    expect(resolvePullValue(addrSpec, eRow({ address_match: 'consistent' }))).toBe('是')
    expect(resolvePullValue(addrSpec, eRow({ address_match: 'inconsistent' }))).toBe('否')
    expect(resolvePullValue(addrSpec, eRow({ address_match: 'pending' }))).toBeUndefined()
    expect(resolvePullValue(addrSpec, eRow({}))).toBeUndefined()
  })

  it('普通文本 trim 后带入；空白不带入', () => {
    expect(resolvePullValue(nameSpec, eRow({ entity_name: '  甲公司  ' }))).toBe('甲公司')
    expect(resolvePullValue(nameSpec, eRow({ entity_name: '   ' }))).toBeUndefined()
    expect(resolvePullValue(nameSpec, eRow({}))).toBeUndefined()
  })
})

describe('buildEntityIndex', () => {
  it('按索引号建表，同索引号取首条（与 VLOOKUP 语义一致）', () => {
    const map = buildEntityIndex([
      eRow({ confirm_index: 'H0-001', entity_name: '首条' }),
      eRow({ confirm_index: 'H0-001', entity_name: '次条' }),
      eRow({ confirm_index: ' H0-002 ', entity_name: '带空格' }),
      eRow({ confirm_index: '', entity_name: '无索引号' }),
    ])
    expect(map.get('H0-001')?.entity_name).toBe('首条')
    expect(map.get('H0-002')?.entity_name).toBe('带空格')
    expect(map.size).toBe(2)
  })
})

// ─── Property 15: 手工优先 / 幂等 / 空索引跳过 / 未匹配回报 ──────────────────

describe('Property 15: 带入行为', () => {
  it('全空行：7 列全部带入', () => {
    const rows = [sRow({ confirm_index: 'H0-001' })]
    const r = pullH0SummaryFromEntityVerify({ summaryRows: rows, entityRows: [FULL_ENTITY], mode: 'fill_blank' })
    expect(r.matched).toBe(1)
    expect(rows[0].entity_name).toBe('甲供应商')
    expect(rows[0].send_channel).toBe('邮寄')
    expect(rows[0].entity_address).toBe('北京市朝阳区XX路 1 号')
    expect(rows[0].send_addr_match).toBe('是')
    expect(rows[0].reply_method).toBe('纸质原件')
    expect(rows[0].reply_from_addr).toBe('北京市朝阳区XX路 1 号')
    expect(rows[0].send_reply_addr_match).toBe('否')
  })

  it('fill_blank 不覆盖已填值（手工优先）', () => {
    const rows = [sRow({ confirm_index: 'H0-001', entity_name: '我手工改过的名称', reply_method: '传真' })]
    pullH0SummaryFromEntityVerify({ summaryRows: rows, entityRows: [FULL_ENTITY], mode: 'fill_blank' })
    expect(rows[0].entity_name).toBe('我手工改过的名称')
    expect(rows[0].reply_method).toBe('传真')
    // 空的仍被补上
    expect(rows[0].entity_address).toBe('北京市朝阳区XX路 1 号')
  })

  it('overwrite 覆盖已填值，但源侧为空不清空目标', () => {
    const rows = [sRow({ confirm_index: 'H0-001', entity_name: '旧名称', reply_from_addr: '手工地址' })]
    const partial = eRow({ confirm_index: 'H0-001', entity_name: '新名称' }) // 无 reply_from_addr
    pullH0SummaryFromEntityVerify({ summaryRows: rows, entityRows: [partial], mode: 'overwrite' })
    expect(rows[0].entity_name).toBe('新名称')
    expect(rows[0].reply_from_addr).toBe('手工地址') // 未被清空
  })

  it('幂等：连续两次调用结果一致', () => {
    const rows = [sRow({ confirm_index: 'H0-001' })]
    const r1 = pullH0SummaryFromEntityVerify({ summaryRows: rows, entityRows: [FULL_ENTITY], mode: 'fill_blank' })
    const snapshot = JSON.stringify(rows)
    const r2 = pullH0SummaryFromEntityVerify({ summaryRows: rows, entityRows: [FULL_ENTITY], mode: 'fill_blank' })
    expect(JSON.stringify(rows)).toBe(snapshot)
    expect(r1.matched).toBe(1)
    expect(r2.matched).toBe(0) // 第二次无改动
    expect(r2.untouched).toBe(1)
  })

  it('overwrite 也幂等', () => {
    const rows = [sRow({ confirm_index: 'H0-001' })]
    pullH0SummaryFromEntityVerify({ summaryRows: rows, entityRows: [FULL_ENTITY], mode: 'overwrite' })
    const snapshot = JSON.stringify(rows)
    const r2 = pullH0SummaryFromEntityVerify({ summaryRows: rows, entityRows: [FULL_ENTITY], mode: 'overwrite' })
    expect(JSON.stringify(rows)).toBe(snapshot)
    expect(r2.matched).toBe(0)
  })

  it('空/空白索引号行被跳过且不被修改', () => {
    const blank = sRow({ confirm_index: '' })
    const spaces = sRow({ confirm_index: '   ' })
    const none = sRow({})
    const rows = [blank, spaces, none]
    const before = JSON.stringify(rows)
    const r = pullH0SummaryFromEntityVerify({ summaryRows: rows, entityRows: [FULL_ENTITY], mode: 'overwrite' })
    expect(r.skippedNoIndex).toBe(3)
    expect(r.matched).toBe(0)
    expect(JSON.stringify(rows)).toBe(before)
  })

  it('H0-2 未匹配的索引号全部回报且去重保序', () => {
    const rows = [
      sRow({ confirm_index: 'H0-009' }),
      sRow({ confirm_index: 'H0-009' }),
      sRow({ confirm_index: 'H0-007' }),
      sRow({ confirm_index: 'H0-001' }),
    ]
    const r = pullH0SummaryFromEntityVerify({ summaryRows: rows, entityRows: [FULL_ENTITY], mode: 'fill_blank' })
    expect(r.unmatchedIndexes).toEqual(['H0-009', 'H0-007'])
    expect(r.matched).toBe(1)
  })

  it('索引号两侧空白仍能匹配', () => {
    const rows = [sRow({ confirm_index: '  H0-001  ' })]
    const r = pullH0SummaryFromEntityVerify({ summaryRows: rows, entityRows: [FULL_ENTITY], mode: 'fill_blank' })
    expect(r.matched).toBe(1)
    expect(rows[0].entity_name).toBe('甲供应商')
  })

  it('逐字段写入计数按列中文名统计', () => {
    const rows = [sRow({ confirm_index: 'H0-001' })]
    const r = pullH0SummaryFromEntityVerify({ summaryRows: rows, entityRows: [FULL_ENTITY], mode: 'fill_blank' })
    expect(r.fieldWrites['被询证单位名称']).toBe(1)
    expect(r.fieldWrites['函证方式']).toBe(1)
    expect(Object.keys(r.fieldWrites)).toHaveLength(7)
  })

  it('空 entityRows：全部行落入未匹配，无写入', () => {
    const rows = [sRow({ confirm_index: 'H0-001' })]
    const before = JSON.stringify(rows)
    const r = pullH0SummaryFromEntityVerify({ summaryRows: rows, entityRows: [], mode: 'overwrite' })
    expect(r.matched).toBe(0)
    expect(r.unmatchedIndexes).toEqual(['H0-001'])
    expect(JSON.stringify(rows)).toBe(before)
  })

  it('updatedRowIds 只含真正被改写的行', () => {
    const a = sRow({ confirm_index: 'H0-001' })
    const b = sRow({ confirm_index: 'H0-002' }) // 未匹配
    const rows = [a, b]
    const r = pullH0SummaryFromEntityVerify({ summaryRows: rows, entityRows: [FULL_ENTITY], mode: 'fill_blank' })
    expect(r.updatedRowIds).toEqual([a._row_id])
  })
})

// ─── 摘要文案 ────────────────────────────────────────────────────────────────

describe('describeH0PullResult', () => {
  it('含命中数、跳过数与未匹配清单', () => {
    const msg = describeH0PullResult({
      matched: 3,
      untouched: 1,
      skippedNoIndex: 2,
      unmatchedIndexes: ['H0-008', 'H0-009'],
      updatedRowIds: [],
      fieldWrites: {},
    })
    expect(msg).toContain('已带入 3 行')
    expect(msg).toContain('无需更新 1 行')
    expect(msg).toContain('跳过 2 行')
    expect(msg).toContain('H0-008、H0-009')
  })

  it('未匹配超过 5 个时折叠显示总数', () => {
    const msg = describeH0PullResult({
      matched: 0,
      untouched: 0,
      skippedNoIndex: 0,
      unmatchedIndexes: ['a', 'b', 'c', 'd', 'e', 'f', 'g'],
      updatedRowIds: [],
      fieldWrites: {},
    })
    expect(msg).toContain('等 7 个')
  })

  it('无异常时只报命中数', () => {
    const msg = describeH0PullResult({
      matched: 2, untouched: 0, skippedNoIndex: 0,
      unmatchedIndexes: [], updatedRowIds: [], fieldWrites: {},
    })
    expect(msg).toBe('已带入 2 行')
  })
})
