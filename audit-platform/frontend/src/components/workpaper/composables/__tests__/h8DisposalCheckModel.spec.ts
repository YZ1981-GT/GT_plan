/**
 * H8-12 减少检查表 — 纯函数模型单测
 */
import { describe, it, expect } from 'vitest'
import {
  calcRouNetValue,
  calcCoverageRate,
  normalizeDisposalRow,
  normalizeReductionMethod,
  calcDisposalSummary,
  sumLinkedRouDecrease,
  buildNoteDraft,
  buildConclusionDraft,
  getEvidenceHint,
  isEarlyTermWithoutPenaltyNote,
  isMaturityNearZeroAnomaly,
  recalcDisposalRow,
  seedDisposalRowsFromH82,
  mapLiabilityFromH9,
  mergeSeededDisposalRows,
} from '../h8DisposalCheckModel'
import { calcTerminationGainLoss } from '../useH8CAS21Engine'

describe('h8DisposalCheckModel', () => {
  describe('calcRouNetValue / calcTerminationGainLoss', () => {
    it('净值 = 原值 − 累计折旧 − 减值准备（对齐致同 M=J-K-L）', () => {
      expect(calcRouNetValue({
        rouCost: 1000,
        accDepreciation: 300,
        impairmentProvision: 50,
      })).toBe(650)
    })

    it('终止损益 = 负债余额 − 净值', () => {
      expect(calcTerminationGainLoss(700, 650)).toBe(50)
      expect(calcTerminationGainLoss(500, 650)).toBe(-150)
    })
  })

  describe('calcCoverageRate', () => {
    it('总体为 0 时返回 0，避免 #DIV/0!', () => {
      expect(calcCoverageRate(1000, 0)).toBe(0)
      expect(calcCoverageRate(1000, -1)).toBe(0)
    })

    it('正常计算检查比例并封顶 100%', () => {
      expect(calcCoverageRate(200, 1000)).toBe(20)
      expect(calcCoverageRate(1500, 1000)).toBe(100)
    })
  })

  describe('normalizeReductionMethod', () => {
    it('兼容旧终止原因别名', () => {
      expect(normalizeReductionMethod('到期')).toBe('到期终止')
      expect(normalizeReductionMethod('双方协商')).toBe('提前退租')
      expect(normalizeReductionMethod('违约终止')).toBe('提前退租')
      expect(normalizeReductionMethod('提前退租')).toBe('提前退租')
    })
  })

  describe('normalizeDisposalRow / recalcDisposalRow', () => {
    it('旧数据仅有净值时回填原值并重算损益', () => {
      const row = normalizeDisposalRow({
        contractNo: 'L-1',
        terminationReason: '提前退租',
        rouNetValue: 800,
        liabilityBalance: 900,
      })
      expect(row.reductionMethod).toBe('提前退租')
      expect(row.rouCost).toBe(800)
      expect(row.rouNetValue).toBe(800)
      expect(row.gainLoss).toBe(100)
    })

    it('原值/折旧/减值变更后重算净值与终止损益', () => {
      const row = normalizeDisposalRow({
        rouCost: 1000,
        accDepreciation: 200,
        impairmentProvision: 0,
        liabilityBalance: 700,
      })
      expect(row.rouNetValue).toBe(800)
      expect(row.gainLoss).toBe(-100)
      row.accDepreciation = 400
      recalcDisposalRow(row)
      expect(row.rouNetValue).toBe(600)
      expect(row.gainLoss).toBe(100)
    })
  })

  describe('sumLinkedRouDecrease', () => {
    it('优先取 H8-1 原值贷方', () => {
      const linked = sumLinkedRouDecrease(5000, [
        { terminationDate: '2024-06-01', initialAmount: 1000 },
      ])
      expect(linked.source).toBe('H8-1')
      expect(linked.amount).toBe(5000)
    })

    it('无贷方时汇总 H8-2 已终止合同入账值', () => {
      const linked = sumLinkedRouDecrease(0, [
        { terminationDate: '2024-06-01', initialAmount: 1000 },
        { terminationDate: '', initialAmount: 2000 },
        { terminationDate: '2024-12-01', initialAmount: 300 },
      ])
      expect(linked.source).toBe('H8-2')
      expect(linked.amount).toBe(1300)
      expect(linked.terminatedCount).toBe(2)
    })
  })

  describe('flags / drafts', () => {
    it('提前退租无违约金且备注未说明时提示', () => {
      expect(isEarlyTermWithoutPenaltyNote({
        reductionMethod: '提前退租',
        terminationReason: '提前退租',
        earlyTermPenalty: 0,
        remark: '',
      })).toBe(true)
      expect(isEarlyTermWithoutPenaltyNote({
        reductionMethod: '提前退租',
        terminationReason: '提前退租',
        earlyTermPenalty: 0,
        remark: '合同约定无违约金',
      })).toBe(false)
    })

    it('到期终止仍有较大净值/负债时视为异常', () => {
      expect(isMaturityNearZeroAnomaly({
        reductionMethod: '到期终止',
        terminationReason: '到期终止',
        rouNetValue: 500,
        liabilityBalance: 0,
      }, 0)).toBe(true)
      expect(isMaturityNearZeroAnomaly({
        reductionMethod: '到期终止',
        terminationReason: '到期终止',
        rouNetValue: 0.5,
        liabilityBalance: 0,
      }, 0)).toBe(false)
    })

    it('getEvidenceHint 按减少方式提示证据', () => {
      expect(getEvidenceHint('提前退租')).toContain('违约金')
      expect(getEvidenceHint('到期终止')).toContain('交还')
    })

    it('calcDisposalSummary / 起草文案覆盖检查比例与 H9 缺口', () => {
      const rows = [
        normalizeDisposalRow({
          rouCost: 200,
          liabilityBalance: 180,
          h9Synced: false,
          checks: { check1: true, check2: true, check3: true, check4: false, check5: false },
        }),
      ]
      const summary = calcDisposalSummary(rows, 1000)
      expect(summary.coverageRate).toBe(20)
      expect(summary.unsyncedH9Count).toBe(1)
      expect(summary.incompleteCheckCount).toBe(1)
      const note = buildNoteDraft(summary, 1000)
      expect(note).toContain('检查比例')
      expect(note).toContain('H9')
      expect(buildConclusionDraft(summary)).toContain('需关注')
      expect(buildConclusionDraft(calcDisposalSummary([], 0))).toContain('尚未抽取')
    })
  })

  describe('seed / H9 liability / merge', () => {
    it('seedDisposalRowsFromH82 仅带入已填终止日的行并计算净值', () => {
      const seeded = seedDisposalRowsFromH82([
        {
          rowId: 'd1',
          contractNo: 'L-1',
          assetName: '办公室',
          terminationDate: '2024-06-30',
          initialAmount: 1000,
          accDepEnd: 400,
        },
        {
          contractNo: 'L-2',
          assetName: '在租',
          terminationDate: '',
          initialAmount: 2000,
        },
      ])
      expect(seeded).toHaveLength(1)
      expect(seeded[0].contractNo).toBe('L-1')
      expect(seeded[0].rouCost).toBe(1000)
      expect(seeded[0].accDepreciation).toBe(400)
      expect(seeded[0].rouNetValue).toBe(600)
      expect(seeded[0].reductionDate).toBe('2024-06-30')
    })

    it('mapLiabilityFromH9 按合同号优先取审定/期末余额并重算损益', () => {
      const rows = [
        normalizeDisposalRow({
          contractNo: 'L-1',
          rouCost: 1000,
          accDepreciation: 400,
          liabilityBalance: 0,
        }),
        normalizeDisposalRow({
          contractNo: 'L-X',
          rouCost: 100,
          liabilityBalance: 10,
        }),
      ]
      const { rows: next, matched } = mapLiabilityFromH9(rows, [
        { contractNo: 'L-1', auditedEnd: 550, endBalance: 500 },
      ])
      expect(matched).toBe(1)
      expect(next[0].liabilityBalance).toBe(550)
      expect(next[0].rouNetValue).toBe(600)
      expect(next[0].gainLoss).toBe(-50)
      expect(next[1].liabilityBalance).toBe(10)
    })

    it('mapLiabilityFromH9 允许负债余额为 0（已摊完）', () => {
      const rows = [normalizeDisposalRow({ contractNo: 'L-0', rouCost: 100, accDepreciation: 100 })]
      const { rows: next, matched } = mapLiabilityFromH9(rows, [
        { contractNo: 'L-0', finalAudited: 0, endBalance: 999 },
      ])
      expect(matched).toBe(1)
      expect(next[0].liabilityBalance).toBe(0)
    })

    it('mergeSeededDisposalRows 保留已有核对勾选与手工字段', () => {
      const existing = [
        normalizeDisposalRow({
          rowId: 'keep-1',
          contractNo: 'L-1',
          rouCost: 1,
          liabilityBalance: 99,
          checks: { check1: true, check2: true, check3: true, check4: true, check5: false },
          remark: '手工备注',
          h9Synced: true,
        }),
      ]
      const seeded = seedDisposalRowsFromH82([
        {
          contractNo: 'L-1',
          assetName: '办公室',
          terminationDate: '2024-06-30',
          initialAmount: 1000,
          accDepEnd: 400,
        },
        {
          contractNo: 'L-2',
          assetName: '新终止',
          terminationDate: '2024-07-01',
          initialAmount: 200,
          accDepEnd: 50,
        },
      ])
      const merged = mergeSeededDisposalRows(existing, seeded)
      expect(merged).toHaveLength(2)
      const l1 = merged.find(r => r.contractNo === 'L-1')!
      expect(l1.rowId).toBe('keep-1')
      expect(l1.checks.check1).toBe(true)
      expect(l1.checks.check4).toBe(true)
      expect(l1.h9Synced).toBe(true)
      expect(l1.liabilityBalance).toBe(99)
      expect(l1.remark).toBe('手工备注')
      expect(l1.rouCost).toBe(1000)
      expect(merged.find(r => r.contractNo === 'L-2')!.rouNetValue).toBe(150)
    })
  })
})
