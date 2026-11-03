/**
 * 响应式数据的结构化克隆（spec attachment-confirmation-evidence-loop 浏览器走查发现）
 *
 * Vue `reactive` / Pinia state 是 Proxy，`structuredClone` / `BroadcastChannel.postMessage` 遇到它抛 DataCloneError：
 * 新开标签页要不到会话（回执带了响应式的 user）、G7 权益法新增商誉 / 公允价值明细抛错（载荷里有响应式行）。
 */
import { describe, expect, it } from 'vitest'
import { reactive, ref } from 'vue'
import { clonePlain, toCloneable } from '../cloneable'
import { addGoodwillFvDetail } from '@/components/workpaper/composables/g7EquityMethodCrossSheet'
import { FRONTEND_SRC, readSource, stripJsComments, toSrcRelative, walkSourceFiles } from '@/__tests__/_helpers/frontendSourceScan'

describe('clonePlain / toCloneable', () => {
  it('裸 structuredClone 对响应式数据抛错（前提自检）', () => {
    expect(() => structuredClone(reactive({ a: { b: 1 } }))).toThrow(/could not be cloned/)
  })

  it('嵌套响应式（含普通对象里放了响应式数组）可克隆，结果与原数据断开', () => {
    const rows = reactive([{ id: 'r1', amount: 10 }])
    const state = reactive({ user: { name: '甲', roles: ['admin'] } })
    const payload = { rows: rows.map((r) => r), user: state.user, list: ref([1, 2]).value }
    const copy = clonePlain(payload)
    expect(copy).toEqual({ rows: [{ id: 'r1', amount: 10 }], user: { name: '甲', roles: ['admin'] }, list: [1, 2] })
    copy.rows[0].amount = 99
    expect(rows[0].amount).toBe(10)
  })

  it('Date 保留类型、环形引用按同一引用还原', () => {
    const node: any = reactive({ at: new Date('2026-10-28T03:00:00Z') })
    node.self = node
    const copy = clonePlain(node)
    expect(copy.at).toBeInstanceOf(Date)
    expect(copy.at.toISOString()).toBe('2026-10-28T03:00:00.000Z')
    expect(copy.self).toBe(copy)
  })

  it('toCloneable 不复制内置对象、原样返回基本类型', () => {
    const d = new Date()
    expect(toCloneable(d)).toBe(d)
    expect(toCloneable(null)).toBeNull()
    expect(toCloneable('a')).toBe('a')
  })

  it('G7 权益法：载荷里有响应式行时新增商誉明细不抛错', () => {
    const groups = reactive([{ investeeName: '甲公司', rows: [{ investeeName: '甲公司', goodwill: 0 }] }])
    const payload = { rows: groups.flatMap((g) => g.rows), groups: groups.map((g) => ({ investeeName: g.investeeName, rows: g.rows })) }
    const result = addGoodwillFvDetail(payload, { investeeName: '甲公司', kind: 'goodwill', amount: 100 } as any)
    expect(result.ok).toBe(true)
  })
})

describe('全仓克隆走 clonePlain', () => {
  it('除 utils/cloneable.ts 外，前端源码不直接调用 structuredClone', () => {
    const hits: string[] = []
    let scanned = 0
    for (const abs of walkSourceFiles(FRONTEND_SRC)) {
      if (!/\.(vue|ts)$/.test(abs) || /\.(spec|test)\.ts$/.test(abs) || /[\\/]__tests__[\\/]/.test(abs)) continue
      const rel = toSrcRelative(abs)
      if (rel === 'utils/cloneable.ts' || /\.worker\.ts$/.test(rel)) continue
      scanned++
      if (/\bstructuredClone\(/.test(stripJsComments(readSource(abs)))) hits.push(rel)
    }
    expect(scanned).toBeGreaterThan(1000)
    expect(hits, `请改用 utils/cloneable 的 clonePlain：${hits.join('、')}`).toEqual([])
  })
})
