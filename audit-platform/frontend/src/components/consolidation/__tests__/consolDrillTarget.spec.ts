import { describe, expect, it } from 'vitest'

import {
  consolDrillNumber,
  consolDrillTargetKey,
  createReportConsolDrillTarget,
  createTbConsolDrillTarget,
  isConsolDrillTargetCurrent,
} from '../composables/consolDrillTarget'

const CONTEXT = { reportType: 'balance_sheet', nodeKey: 'node:parent' }

describe('ConsolDrillTarget', () => {
  it('TB 目标冻结本次行、报表类型、节点、科目和真实零值', () => {
    const row = {
      row_code: 'BS-001',
      row_name: '货币资金',
      consolidated: 0,
      standard_account_code: '1001',
    }
    const target = createTbConsolDrillTarget(row, CONTEXT)

    expect(target).toEqual({
      source: 'tb',
      rowCode: 'BS-001',
      reportType: 'balance_sheet',
      nodeKey: 'node:parent',
      period: 'current',
      itemName: '货币资金',
      colName: '合并审定数',
      totalValue: 0,
      accountCode: '1001',
    })
    expect(Object.isFrozen(target)).toBe(true)
    row.row_code = 'BS-999'
    expect(target?.rowCode).toBe('BS-001')
  })

  it('报表本期与上期按动态列名构造，不把 0 或 null 混淆', () => {
    const row = {
      row_code: 'IS-010',
      row_name: '营业收入',
      current_period_amount: 0,
      prior_period_amount: null,
    }
    const labels = { currentLabel: '调整抵销本期', priorLabel: '调整抵销上期' }
    const current = createReportConsolDrillTarget(
      row,
      { label: labels.currentLabel, ...labels },
      { ...CONTEXT, reportType: 'income_statement', accountCode: '6001' },
    )
    const prior = createReportConsolDrillTarget(
      row,
      { label: labels.priorLabel, ...labels },
      { ...CONTEXT, reportType: 'income_statement' },
    )

    expect(current).toMatchObject({
      source: 'report',
      rowCode: 'IS-010',
      reportType: 'income_statement',
      nodeKey: 'node:parent',
      period: 'current',
      totalValue: 0,
      colName: '调整抵销本期',
      accountCode: '6001',
    })
    expect(prior).toMatchObject({
      source: 'report',
      rowCode: 'IS-010',
      reportType: 'income_statement',
      nodeKey: 'node:parent',
      period: 'prior',
      totalValue: null,
      colName: '调整抵销上期',
    })
  })

  it('非金额列或缺少行次、报表类型、节点时不制造可请求目标', () => {
    const row = { row_code: '1', row_name: '项目', current_period_amount: 1 }
    expect(createReportConsolDrillTarget(
      row,
      { label: '项目', currentLabel: '合并本期', priorLabel: '合并上期' },
      CONTEXT,
    )).toBeNull()
    expect(createTbConsolDrillTarget({ ...row, row_code: '' }, CONTEXT)).toBeNull()
    expect(createTbConsolDrillTarget(row, { reportType: '', nodeKey: 'node' })).toBeNull()
    expect(createTbConsolDrillTarget(row, { reportType: 'balance_sheet', nodeKey: '' })).toBeNull()
  })

  it('数字归一明确区分零、空值和非法值', () => {
    expect(consolDrillNumber(0)).toBe(0)
    expect(consolDrillNumber('0')).toBe(0)
    expect(consolDrillNumber(null)).toBeNull()
    expect(consolDrillNumber('')).toBeNull()
    expect(consolDrillNumber('not-a-number')).toBeNull()
  })

  it('上下文匹配会拒绝切来源、报表类型或节点后的陈旧目标', () => {
    const target = createTbConsolDrillTarget(
      { row_code: '1', row_name: '资产', consolidated: 10 },
      CONTEXT,
    )
    expect(isConsolDrillTargetCurrent(target, {
      source: 'tb', reportType: 'balance_sheet', nodeKey: 'node:parent',
    })).toBe(true)
    expect(isConsolDrillTargetCurrent(target, {
      source: 'report', reportType: 'balance_sheet', nodeKey: 'node:parent',
    })).toBe(false)
    expect(isConsolDrillTargetCurrent(target, {
      source: 'tb', reportType: 'income_statement', nodeKey: 'node:parent',
    })).toBe(false)
    expect(isConsolDrillTargetCurrent(target, {
      source: 'tb', reportType: 'balance_sheet', nodeKey: 'node:other',
    })).toBe(false)
  })

  it('目标 key 包含请求身份字段，但不受标题和值变化影响', () => {
    const first = createTbConsolDrillTarget({ row_code: '1', row_name: '甲', consolidated: 1 }, CONTEXT)!
    const sameIdentity = { ...first, itemName: '乙', totalValue: 2 }
    const anotherRow = createTbConsolDrillTarget({ row_code: '2', row_name: '甲', consolidated: 1 }, CONTEXT)!
    expect(consolDrillTargetKey(first)).toBe(consolDrillTargetKey(sameIdentity))
    expect(consolDrillTargetKey(first)).not.toBe(consolDrillTargetKey(anotherRow))
    expect(consolDrillTargetKey(null)).toBe('')
  })
})
