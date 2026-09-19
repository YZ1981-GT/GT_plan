import { describe, expect, it } from 'vitest'
import {
  collectChecklistResponses,
  normalizeChecklistRemark,
  toChecklistPatch,
} from './checklistPersistenceHelpers'

describe('normalizeChecklistRemark（历史双层读兼容 + 新写单层）', () => {
  it('纯文本原样返回', () => {
    expect(normalizeChecklistRemark('完整性认定已核对')).toBe('完整性认定已核对')
  })

  it('null/undefined → null', () => {
    expect(normalizeChecklistRemark(null)).toBeNull()
    expect(normalizeChecklistRemark(undefined)).toBeNull()
  })

  it('单层 JSON 字符串幂等（不再二次包裹）', () => {
    const single = JSON.stringify({ rows: [{ id: 1, amount: 100 }] })
    expect(normalizeChecklistRemark(single)).toBe(single)
  })

  it('历史双层 {remark:"..."} 解一次 → 单层', () => {
    const inner = JSON.stringify({ rows: [{ id: 1 }] })
    const doubleWrapped = JSON.stringify({ remark: inner })
    // 解包后应等于内层单层 JSON，且不含 remark 包装
    expect(normalizeChecklistRemark(doubleWrapped)).toBe(inner)
  })

  it('业务对象直接序列化为单层', () => {
    const obj = { conclusion: 'ok', items: [1, 2, 3] }
    expect(normalizeChecklistRemark(obj)).toBe(JSON.stringify(obj))
  })
})

describe('collectChecklistResponses（多来源合并，后写胜出）', () => {
  it('合并数组与对象形态，normalize remark，空串 conclusion → null', () => {
    const snapshot = { 'K1-1-main': { remark: JSON.stringify({ a: 1 }), conclusion: '' } }
    const apiArray = [{ item_id: 'K1-1-main', remark: JSON.stringify({ a: 2 }), conclusion: 'B' }]
    const merged = collectChecklistResponses(snapshot, apiArray)
    expect(merged).toHaveLength(1)
    expect(merged[0].item_id).toBe('K1-1-main')
    // 后写（apiArray）胜出
    expect(merged[0].remark).toBe(JSON.stringify({ a: 2 }))
    expect(merged[0].conclusion).toBe('B')
  })

  it('空串 conclusion 归一为 null（规避后端白名单 422）', () => {
    const merged = collectChecklistResponses({ 'K3-2-x': { remark: 'txt', conclusion: '' } })
    expect(merged[0].conclusion).toBeNull()
  })

  it('对象形态以键作为 item_id 收集（与 k5Persistence 一致，permissive）', () => {
    const merged = collectChecklistResponses({ 'K1-1-main': { remark: 'txt' } })
    expect(merged).toHaveLength(1)
    expect(merged[0].item_id).toBe('K1-1-main')
    expect(merged[0].remark).toBe('txt')
  })
})

describe('toChecklistPatch（子组件 save 值 → Adapter patch，仅序列化一次）', () => {
  it('信封 {remark, conclusion} 解包', () => {
    const patch = toChecklistPatch({ remark: JSON.stringify({ x: 1 }), conclusion: 'C' })
    expect(patch.remark).toBe(JSON.stringify({ x: 1 }))
    expect(patch.conclusion).toBe('C')
  })

  it('信封 conclusion 空串 → null', () => {
    const patch = toChecklistPatch({ remark: 'r', conclusion: '' })
    expect(patch.conclusion).toBeNull()
  })

  it('裸值（无信封）作为 remark 处理，不含 conclusion 键', () => {
    const patch = toChecklistPatch('纯文本备注')
    expect(patch.remark).toBe('纯文本备注')
    expect('conclusion' in patch).toBe(false)
  })

  it('历史双层 remark 信封解一次 → 单层', () => {
    const inner = JSON.stringify([{ id: 1 }])
    const patch = toChecklistPatch({ remark: JSON.stringify({ remark: inner }) })
    expect(patch.remark).toBe(inner)
  })
})
