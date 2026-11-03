/**
 * D2 披露表逐项明细的来源派生（spec note-table-structure-formula-pull-closure R7）。
 *
 * 判据：①四张表（单项计提 / 转回 / 核销 / 前五名）在用户没录入行时，快照按 D2-3 / D2-11 / D2-5 的来源派生
 * ②派生只进快照不落库（不调 save / 不写 checklist）③用户录过行就一律用用户的行（派生不混进来、删掉的行不回来）
 * ④「带入」按钮与派生同一份映射：带入后快照与派生结果逐字节相同 ⑤离屏（headless）与 Tab 的载荷相同
 * ⑥变异反证：拿掉派生兜底，这四张表在快照里就是空的。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiGet: vi.fn(), detail: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: h.apiGet } }))
vi.mock('@/services/auditPlatformApi', () => ({ getDisclosureNoteDetail: h.detail }))

import {
  deriveIndividualRows,
  deriveReversalRows,
  deriveTop5Rows,
  deriveWriteOffRows,
  missingByName,
} from '../d2DisclosureDerive'
import { useD2DisclosureNote } from '../useD2DisclosureNote'
import { clearAgingConfigCache, PRESET_SEGMENTS } from '@/composables/useAgingConfig'
import type { ChecklistResponse } from '../useD2FormData'

const BAD_DEBT = [
  { rowId: 'b0', label: '按单项计提坏账准备', isSubRow: false, currentAudited: 300, priorAudited: 200 },
  { rowId: 'b1', label: '甲公司', isSubRow: true, currentAudited: 180, priorAudited: 120 },
  { rowId: 'b2', label: '乙公司', isSubRow: true, currentAudited: '120', priorAudited: null },
  { rowId: 'b3', label: '   ', isSubRow: true, currentAudited: 1 },
]
const REVERSAL = [
  { debtorName: '甲公司', reason: '客户回款', recoveryMethod: '银行转账', originalBasis: '单项评估',
    cumulativeProvision: 90, amount: 60 },
  { debtorName: '', reason: '', amount: 0 },
]
const WRITEOFF = [
  { debtorName: '丙公司', receivableType: '货款', amount: 45, reason: '破产清算', approvalDoc: '董事会决议',
    isRelatedParty: '否' },
]
const TOP10 = [
  { customerName: '丁公司', endBalance: 100 },
  { customerName: '戊公司', endBalance: 900 },
  { customerName: '己公司', endBalance: 500 },
  { customerName: '庚公司', endBalance: 400 },
  { customerName: '辛公司', endBalance: 300 },
  { customerName: '壬公司', endBalance: 200 },
]

const RESPONSES: ChecklistResponse[] = [
  { item_id: 'D2-bd-individual-rows', remark: JSON.stringify(BAD_DEBT), conclusion: null },
  { item_id: 'D2-writeoff-reversal-rows', remark: JSON.stringify(REVERSAL), conclusion: null },
  { item_id: 'D2-writeoff-writeoff-rows', remark: JSON.stringify(WRITEOFF), conclusion: null },
  { item_id: 'D2-analysis-top10', remark: JSON.stringify(TOP10), conclusion: null },
] as ChecklistResponse[]

function makeNote(extra: ChecklistResponse[] = [], opts: { save?: (id: string, v: any) => void } = {}) {
  const map = new Map<string, ChecklistResponse>([...RESPONSES, ...extra].map((r) => [r.item_id, r]))
  const scope = effectScope(true)
  const api = scope.run(() => useD2DisclosureNote({
    allResponses: ref(map),
    wpId: ref('wp-d2'),
    projectId: ref('p1'),
    variant: 'soe',
    save: opts.save ?? (() => {}),
    isReadonly: ref(false),
  }))!
  return { api, stop: () => scope.stop() }
}

describe('d2DisclosureDerive — 纯映射', () => {
  it('单项计提：只取子行、名称去空白、金额走 parseNum', () => {
    expect(deriveIndividualRows(BAD_DEBT)).toEqual([
      { name: '甲公司', endAmount: 0, priorAmount: 0, provision: 180, priorProvision: 120, aging: '', basis: '' },
      { name: '乙公司', endAmount: 0, priorAmount: 0, provision: 120, priorProvision: 0, aging: '', basis: '' },
    ])
  })

  it('转回 / 核销：名称与金额都空的行跳过，字段按 D2-11 列名取', () => {
    expect(deriveReversalRows(REVERSAL)).toEqual([
      { companyName: '甲公司', reversalReason: '客户回款', recoveryMethod: '银行转账', originalBasis: '单项评估',
        cumulativeProvision: 90, amount: 60 },
    ])
    expect(deriveWriteOffRows(WRITEOFF)).toEqual([
      { companyName: '丙公司', nature: '货款', amount: 45, reason: '破产清算', procedure: '董事会决议',
        relatedParty: '否' },
    ])
  })

  it('前五名：按期末余额倒序取 5 名（合同资产 / 减值准备留 0 待手工）', () => {
    const got = deriveTop5Rows(TOP10)
    expect(got.map((r) => [r.companyName, r.arAmount])).toEqual([
      ['戊公司', 900], ['己公司', 500], ['庚公司', 400], ['辛公司', 300], ['壬公司', 200]])
    expect(got.every((r) => r.contractAssetAmount === 0 && r.provision === 0)).toBe(true)
  })

  it('非数组 / 脏数据不抛', () => {
    for (const bad of [null, undefined, '[]', 0, {}, [null, 1, 'x']]) {
      expect(deriveIndividualRows(bad)).toEqual([])
      expect(deriveTop5Rows(bad)).toEqual([])
    }
  })

  it('missingByName：按名称去重，名称为空的一律算新增', () => {
    const existing = [{ companyName: '甲公司' }]
    const derived = [{ companyName: '甲公司' }, { companyName: '乙公司' }, { companyName: '' }]
    expect(missingByName(existing, derived, (r: any) => String(r.companyName ?? ''))).toEqual([
      { companyName: '乙公司' }, { companyName: '' }])
  })
})

describe('buildSnapshot — 用户没录入时按来源派生（R7）', () => {
  beforeEach(() => {
    clearAgingConfigCache()
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 1, push_kept: [] })
    h.apiGet.mockResolvedValue({ preset: 'THREE_YEAR', effective_segments: PRESET_SEGMENTS.THREE_YEAR, subject_overrides: {} })
    h.detail.mockResolvedValue({ table_data: { _tables: [] } })
  })

  it('四张表都按底稿来源派生，且不落库（原先离屏推出去是空表）', async () => {
    const saved: string[] = []
    const { api, stop } = makeNote([], { save: (id) => saved.push(id) })
    await nextTick()
    const snap = api.buildSnapshot()
    expect(snap.individualRows.map((r) => r.name)).toEqual(['甲公司', '乙公司'])
    expect(snap.reversalRows.map((r) => r.companyName)).toEqual(['甲公司'])
    expect(snap.writeOffRows.map((r) => r.companyName)).toEqual(['丙公司'])
    expect(snap.top5Rows.map((r) => r.companyName)).toEqual(['戊公司', '己公司', '庚公司', '辛公司', '壬公司'])
    // 派生只进快照：没有任何 persist（四张表的 item_id 一个都没写）
    expect(saved.filter((id) => /individual-rows|reversal-rows|writeoff-rows|top5-rows/.test(id))).toEqual([])
    // 派生行带上了派生列（损失率 / 占比由快照算）
    expect(snap.individualRows[0].lossRate).toBe(0)
    stop()
  })

  it('用户录过行 ⇒ 一律用用户的行（删掉的行不会被派生塞回来）', async () => {
    const { api, stop } = makeNote([
      // 披露 Tab 自己的落库前缀是 `D2-disc-<variant>-`
      { item_id: 'D2-disc-soe-individual-rows', remark: JSON.stringify([{ rowId: 'u1', name: '用户行', endAmount: 1,
        priorAmount: 0, provision: 0, priorProvision: 0, aging: '', basis: '' }]), conclusion: null } as ChecklistResponse,
      { item_id: 'D2-disc-soe-top5-rows', remark: JSON.stringify([{ rowId: 'u2', companyName: '只留这一家', arAmount: 5,
        contractAssetAmount: 0, provision: 0 }]), conclusion: null } as ChecklistResponse,
    ])
    await nextTick()
    const snap = api.buildSnapshot()
    expect(snap.individualRows.map((r) => r.name)).toEqual(['用户行'])
    expect(snap.top5Rows.map((r) => r.companyName)).toEqual(['只留这一家'])
    // 没录入的两张仍按来源派生
    expect(snap.writeOffRows.map((r) => r.companyName)).toEqual(['丙公司'])
    stop()
  })

  it('「带入」按钮与派生同一份映射：带入后快照与派生前逐字节相同', async () => {
    const { api: derived, stop: stopA } = makeNote()
    await nextTick()
    const before = JSON.stringify(derived.buildSnapshot().individualRows)
    stopA()

    const { api, stop } = makeNote()
    await nextTick()
    expect(api.importIndividualFromBadDebt()).toBe(2)
    expect(api.importReversalFromWriteoffCheck()).toBe(1)
    expect(api.importWriteOffFromWriteoffCheck()).toBe(1)
    expect(api.importTop5FromAnalysis()).toBe(5)
    expect(JSON.stringify(api.buildSnapshot().individualRows)).toBe(before)
    // 再点一次不重复加（按名称去重）
    expect(api.importIndividualFromBadDebt()).toBe(0)
    stop()
  })
})
