/**
 * K3-5 长期挂账 / K3-6 关联方往来的行级抽凭（spec voucher-identity-writeback-and-audit-phase 任务 13）
 *
 * 原实现读引擎载荷的 `payload.voucherNo`（载荷是 `{ samples, … }`）⇒ 抽凭与挂凭导入都是空操作。现在抽到的凭证记进
 * 「抽凭明细」：一个对方科目一行，挂到发起抽凭的往来对象行；挂凭导入按往来单位对上同名往来对象（唯一命中才挂）。
 * 通用五条用例里的「旧行」不适用（明细是新存储，没有旧行），只验其余四条的同一套行为。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn(), prompt: vi.fn() },
}))

import { useK3RowVoucherFill } from '../k3RowVoucherFill'
import { metaOf } from '../shared/voucherCheckFill'
import { MULTI, paired, resetVoucherFillMocks, sample, VK } from './voucherFillHostHarness'

const ITEM = 'K3-5-row-vouchers'
const targets = [{ rowId: 'lo-1', counterparty: '甲公司' }, { rowId: 'lo-2', counterparty: '乙公司' }]

function make(seed?: unknown[]) {
  const map = new Map<string, any>()
  if (seed) map.set(ITEM, { item_id: ITEM, remark: JSON.stringify(seed) })
  const saves: string[] = []
  const api = useK3RowVoucherFill({
    sheet: 'K3-5',
    allResponses: () => map,
    save: (itemId, payload) => {
      saves.push(itemId)
      map.set(itemId, { item_id: itemId, ...payload })
    },
    projectId: 'proj-1',
    readonly: false,
    targets: () => targets,
  })
  const stored = () => JSON.parse(String(map.get(ITEM)?.remark ?? '[]'))
  return { api, saves, stored }
}

/** 辅助核算往来单位（后端 enrich_items_with_aux_party 写在样本上的两个字段） */
const aux = (name: string) => ({ partyName: name, partyAuxType: '客户' })

beforeEach(resetVoucherFillMocks)

describe('K3-5 / K3-6 行级抽凭明细', () => {
  it('行上抽凭：样本挂到发起行，一个对方科目一行；再抽一次不重复；`_gt` 随明细落库、读回还在', async () => {
    const { api, stored } = make()
    const batch = [
      sample('fp-1', { debitAmount: null, creditAmount: '300.00', pairing: paired(['1002', '银行存款', '200.00'], ['6111', '投资收益', '100.00']) }),
      sample('fp-2', { voucherNo: '0014', pairing: MULTI }),
    ]
    await api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-1' }, targets[0])
    await api.onEngineFilled({ samples: batch, phase: 'final', batchId: 'b-2' }, targets[0])
    expect(api.rows.value.map(r => [r.targetRowId, r.counterparty, r.voucherNo, r.counterpartAccount, r.debitAmount, r.creditAmount])).toEqual([
      ['lo-1', '甲公司', '0012', '1002', 0, 200],
      ['lo-1', '甲公司', '0012', '6111', 0, 100],
      ['lo-1', '甲公司', '0014', '多科目', 1000, 0],
    ])
    expect(api.vouchersOf('lo-1')).toHaveLength(3)
    expect(stored()[0]._gt).toMatchObject({ vk: VK, ph: 'final', b: 'b-1', src: ['engine'] })
    const again = make(stored())
    expect(metaOf(again.api.rows.value[0])).toMatchObject({ b: 'b-1' })
  })

  it('挂凭导入：按往来单位对上同名往来对象，对不上的留在明细里（未对应）；导入两次不重复', async () => {
    const { api } = make()
    await api.onAttachImported([sample('fp-1', aux('乙公司')), sample('fp-2', { voucherNo: '0020', ...aux('丙公司') })])
    await api.onAttachImported([sample('fp-1', aux('乙公司'))])
    expect(api.rows.value.map(r => [r.voucherNo, r.targetRowId, r.counterparty])).toEqual([
      ['0012', 'lo-2', '乙公司'],
      ['0020', '', '丙公司'],
    ])
  })

  it('撤销按批次删明细行，同时来自挂凭的保留；替换只删本阶段抽凭行', async () => {
    const { api } = make([{ rowId: 'm1', targetRowId: 'lo-1', voucherNo: '手-1', checkResult: '' }])
    await api.onEngineFilled({ samples: [sample('fp-1'), sample('fp-2', { voucherNo: '0013' })], phase: 'final', batchId: 'b-1' }, targets[0])
    await api.onAttachImported([sample('fp-2', { voucherNo: '0013' })])
    await api.onEngineFilled({ samples: [sample('fp-3', { voucherNo: '0015' })], phase: 'final', fillMode: 'replace', batchId: 'b-2' }, targets[1])
    await nextTick()
    expect(api.rows.value.map(r => r.voucherNo)).toEqual(['手-1', '0013', '0015'])
    expect(await api.onUndoRequest({ logId: 'l-2', batchId: 'b-2', performUndo: async () => true })).toBe(true)
    expect(api.rows.value.map(r => r.voucherNo)).toEqual(['手-1', '0013'])
  })

  it('年审阶段预审行只读：删不掉，绕过界面改了，保存时按读入版本写回', async () => {
    const prelim = { rowId: 'p1', targetRowId: 'lo-1', voucherNo: '0012', checkResult: '已核对', _gt: { vk: VK, lfp: 'fp-1', ph: 'preliminary', b: 'b-0', src: ['engine'], pr: 'paired' } }
    const { api, stored } = make([prelim])
    await api.ready()
    expect(api.rowClass({ row: api.rows.value[0] })).toContain('gt-row-locked')
    api.removeVoucher('p1')
    expect(api.rows.value.map(r => r.rowId)).toEqual(['p1'])
    api.rows.value[0].checkResult = '被改了'
    api.persist()
    expect(stored()[0]).toMatchObject({ rowId: 'p1', checkResult: '已核对' })
  })
})
