/**
 * alternativeStructureAlignment.pbt.spec.ts — 借贷拆表 + round-trip 属性测试
 *
 * confirmation-alternative-structure-alignment Task 6.1：
 * - Property 1  借贷方向行不互污染 + 各自合计正确（getBlockTotalByDirection）
 * - Property 11 round-trip：旧 payload 读→保存→读，已录内容（含 direction / 无 direction 行）不丢
 *
 * 直接驱动 Shared_Core 工厂（createAlternativeConfirmationData），不依赖具体套别渲染层。
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import {
  createAlternativeConfirmationData,
  type AltConfig,
} from '../createAlternativeConfirmationData'
import type { AlternativeCompany } from '../../alternativeD05/alternativeD05Types'

// 最小 splitByDirection 配置：block2 承载「本期发生额」借贷拆表，sumField=['amt']
function makeSplitConfig(overrides: Partial<AltConfig> = {}): AltConfig {
  return {
    format: 'alternative-split-test-v1',
    getSumFields: (bt) => (bt === 'block2' ? ['amt'] : []),
    defaultBalance: () => ({}),
    baseAmount: () => 1000,
    ratios: [
      { key: 'r1', block: 'block2', fields: ['amt'], payloadKey: 'r1_ratio' },
      { key: 'r2', block: 'block3', fields: ['amt'], payloadKey: 'r2_ratio' },
    ],
    metricRatioKeys: { receipt: 'r1', shipment: 'r2' },
    ...overrides,
  }
}

const dirArb = fc.constantFrom<'debit' | 'credit' | undefined>('debit', 'credit', undefined)
const amtArb = fc.integer({ min: 0, max: 100000 }) // 整数金额避免浮点小计断言脆弱

// precise(sum) 口径：Math.round(x*100)/100；整数金额下等于普通求和
function sumOf(rows: { direction?: string; amt: number }[], dir?: string): number {
  return rows.filter((r) => (dir === undefined ? true : r.direction === dir)).reduce((s, r) => s + r.amt, 0)
}

describe('Property 1: 借贷拆表行不互污染 + 各自合计正确', () => {
  it('getBlockTotalByDirection 借方仅累加借方行、贷方仅累加贷方行；getBlockTotal = 全部行合计', () => {
    fc.assert(
      fc.property(
        fc.array(fc.record({ direction: dirArb, amt: amtArb }), { minLength: 0, maxLength: 15 }),
        (rows) => {
          const core = createAlternativeConfirmationData(makeSplitConfig())
          const c = core.addCompany()
          const id = c._company_id!
          for (const r of rows) {
            const row = core.addBlockRow(id, 'block2')!
            if (r.direction) core.updateBlockField(id, 'block2', row._row_id!, 'direction', r.direction)
            core.updateBlockField(id, 'block2', row._row_id!, 'amt', r.amt)
          }
          const company = core.companies.value.find((x) => x._company_id === id)!

          const debit = core.getBlockTotalByDirection(company, 'block2', 'debit').amt
          const credit = core.getBlockTotalByDirection(company, 'block2', 'credit').amt
          const all = core.getBlockTotal(company, 'block2').amt

          // 借方合计仅含借方行、贷方合计仅含贷方行（不互污染）
          expect(debit).toBe(sumOf(rows, 'debit'))
          expect(credit).toBe(sumOf(rows, 'credit'))
          // 全 block 合计 = 借 + 贷 + 无方向行（getBlockTotal 遍历全部行）
          expect(all).toBe(sumOf(rows))
          // 加法分解：全合计 = 借 + 贷 + 无方向行小计
          const undirected = sumOf(rows.filter((r) => !r.direction))
          expect(all).toBe(debit + credit + undirected)
        }
      ),
      { numRuns: 30 }
    )
  })

  it('全部行均有 direction 时：getBlockTotal 恰 = 借 + 贷（Property 1 等式）', () => {
    fc.assert(
      fc.property(
        fc.array(fc.record({ direction: fc.constantFrom<'debit' | 'credit'>('debit', 'credit'), amt: amtArb }), {
          minLength: 1,
          maxLength: 15,
        }),
        (rows) => {
          const core = createAlternativeConfirmationData(makeSplitConfig())
          const c = core.addCompany()
          const id = c._company_id!
          for (const r of rows) {
            const row = core.addBlockRow(id, 'block2')!
            core.updateBlockField(id, 'block2', row._row_id!, 'direction', r.direction)
            core.updateBlockField(id, 'block2', row._row_id!, 'amt', r.amt)
          }
          const company = core.companies.value.find((x) => x._company_id === id)!
          const debit = core.getBlockTotalByDirection(company, 'block2', 'debit').amt
          const credit = core.getBlockTotalByDirection(company, 'block2', 'credit').amt
          const all = core.getBlockTotal(company, 'block2').amt
          expect(all).toBe(debit + credit)
        }
      ),
      { numRuns: 30 }
    )
  })
})

describe('Property 11: round-trip 既有数据不丢（含 direction / 无 direction 行）', () => {
  it('buildPayload → 重新 init，区块行数/direction/金额/is_abnormal 完整保留', () => {
    fc.assert(
      fc.property(
        fc.array(fc.record({ direction: dirArb, amt: amtArb, abnormal: fc.boolean() }), {
          minLength: 0,
          maxLength: 12,
        }),
        (rows) => {
          const cfg = makeSplitConfig()
          const core = createAlternativeConfirmationData(cfg)
          const c = core.addCompany({ entity_name: 'RT' })
          const id = c._company_id!
          for (const r of rows) {
            const row = core.addBlockRow(id, 'block2')!
            if (r.direction) core.updateBlockField(id, 'block2', row._row_id!, 'direction', r.direction)
            core.updateBlockField(id, 'block2', row._row_id!, 'amt', r.amt)
            core.updateBlockField(id, 'block2', row._row_id!, 'is_abnormal', r.abnormal ? '是' : '否')
          }

          const payload = core.buildPayload()

          // 用一个新工厂实例通过 htmlData 载入 payload（模拟保存后重开）
          const core2 = createAlternativeConfirmationData({ ...cfg, htmlData: () => payload })
          const comp2 = core2.companies.value.find((x) => x.entity_name === 'RT')
          expect(comp2).toBeTruthy()
          const b2 = comp2!.block2_rows || []
          expect(b2.length).toBe(rows.length)
          // 顺序保留，逐行核对 direction / amt / is_abnormal
          for (let i = 0; i < rows.length; i++) {
            expect(b2[i].direction).toBe(rows[i].direction)
            expect(Number(b2[i].amt)).toBe(rows[i].amt)
            expect(b2[i].is_abnormal).toBe(rows[i].abnormal ? '是' : '否')
          }
        }
      ),
      { numRuns: 30 }
    )
  })
})
