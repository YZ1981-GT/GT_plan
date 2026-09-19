/**
 * importE0ListsToSummary.spec.ts — E0 发函记录表 → E0-1 带入口径守卫
 *
 * 全部 fixture 的列名逐字取自源模板
 * `backend/wp_templates/E/E0 货币资金 - 函证（Leap应对措施-函证）.xlsx`：
 *   E0-3 A5:P5 所属科目/索引号/报表截止日/开户银行/是否函证/账户名称/银行账号/币种/
 *        利率(%)/账户类型/账户余额（原币）/…
 *   E0-4 A5:P5 所属科目/索引号/报表截止日/开户银行/是否函证/借款人名称/借款账号/币种/
 *        余额/借款日期/到期日期/利率(%)/抵(质)押品/担保人/备注/借款类型/期末应付利息
 *   E0-5 A5:J5 索引号/报表截止日/开户银行/银行承兑汇票号码/结算账户账号/币种/票面金额/
 *        出票日/到期日/抵（质）押品   ← **无「是否函证」列**
 *   E0-6 A5:K5 索引号/报表截止日/开户行名称及收件人/产品名称/产品类型/币种/持有份额/
 *        产品净值/购买日/到期日/是否被用于担保或存在其他使用限制  ← **无「是否函证」列**
 *
 * 口径裁决者 = E0-1!F8 的嵌套 SUMIF/SUMIFS（见被测模块头部注释）。
 */
import { describe, it, expect } from 'vitest'
import {
  isConfirmFlagYes,
  resolveE0AccountType,
  buildSummaryRowsFromListRows,
  dedupeSummaryRows,
  E0_LIST_ACCOUNT_TYPE,
  E0_LIST_SPECS,
} from '../importE0ListsToSummary'
import type { ConfirmationRow } from '../../confirmationTypes'

describe('E0_LIST_SPECS 与源模板对齐', () => {
  it('四张发函记录表齐备，sheetName 为源 xlsx tab 名逐字', () => {
    expect(Object.keys(E0_LIST_SPECS).sort()).toEqual(['E0-3', 'E0-4', 'E0-5', 'E0-6'])
    expect(E0_LIST_SPECS['E0-3'].sheetName).toBe('货币资金发函记录表E0-3')
    expect(E0_LIST_SPECS['E0-4'].sheetName).toBe('借款发函记录表E0-4')
    expect(E0_LIST_SPECS['E0-5'].sheetName).toBe('应付银行承兑汇票发函记录表E0-5')
    expect(E0_LIST_SPECS['E0-6'].sheetName).toBe('理财产品发函记录表E0-6')
  })

  it('E0-5 / E0-6 源模板无「是否函证」列 → hasConfirmFlag=false', () => {
    expect(E0_LIST_SPECS['E0-3'].hasConfirmFlag).toBe(true)
    expect(E0_LIST_SPECS['E0-4'].hasConfirmFlag).toBe(true)
    expect(E0_LIST_SPECS['E0-5'].hasConfirmFlag).toBe(false)
    expect(E0_LIST_SPECS['E0-6'].hasConfirmFlag).toBe(false)
  })

  it('金额列首项 = 源模板逐字列名（E0-5 票面金额 / E0-6 产品净值）', () => {
    expect(E0_LIST_SPECS['E0-3'].amountKeys[0]).toBe('账户余额（原币）')
    expect(E0_LIST_SPECS['E0-4'].amountKeys[0]).toBe('余额')
    expect(E0_LIST_SPECS['E0-5'].amountKeys[0]).toBe('票面金额')
    expect(E0_LIST_SPECS['E0-6'].amountKeys[0]).toBe('产品净值')
  })

  it('聚合口径对齐 E0-1!F8：E0-5 单条件按索引号，E0-6 索引号+产品名', () => {
    expect(E0_LIST_SPECS['E0-3'].groupBy).toBe('accountNo')
    expect(E0_LIST_SPECS['E0-4'].groupBy).toBe('accountNo')
    expect(E0_LIST_SPECS['E0-5'].groupBy).toBe('index')
    expect(E0_LIST_SPECS['E0-6'].groupBy).toBe('index+accountNo')
  })

  it('E0-4 品种权威列是「所属科目」（E0-1 SUMIFS 的匹配列），「借款类型」仅兜底', () => {
    expect(E0_LIST_SPECS['E0-4'].subtypeKeys).toEqual(['所属科目', '借款类型'])
  })

  it('E0-6 兼容专属组件格式 wealth-list-v1（英文字段名）与通用 d-form-table', () => {
    expect(E0_LIST_SPECS['E0-6'].formats).toEqual(['wealth-list-v1', 'd-form-table'])
    expect(E0_LIST_SPECS['E0-6'].amountKeys).toContain('net_value')
    expect(E0_LIST_SPECS['E0-6'].accountNoKeys).toContain('product_name')
    expect(E0_LIST_SPECS['E0-6'].entityKeys).toContain('bank_and_recipient')
    // 其余三张目前只有通用格式
    for (const code of ['E0-3', 'E0-4', 'E0-5']) {
      expect(E0_LIST_SPECS[code].formats).toEqual(['d-form-table'])
    }
  })

  it('E0_LIST_ACCOUNT_TYPE 由 specs 派生，无第二份真源', () => {
    expect(E0_LIST_ACCOUNT_TYPE).toEqual({
      'E0-3': '银行存款',
      'E0-4': '短期借款',
      'E0-5': '应付票据',
      'E0-6': '理财产品',
    })
  })
})

describe('isConfirmFlagYes', () => {
  it('识别多种「是」表示', () => {
    expect(isConfirmFlagYes({ 是否函证: '是' })).toBe(true)
    expect(isConfirmFlagYes({ 是否函证: 'Y' })).toBe(true)
    expect(isConfirmFlagYes({ 是否发函: '√' })).toBe(true)
    expect(isConfirmFlagYes({ confirm_flag: 'true' })).toBe(true)
  })
  it('识别「否」/空为 false', () => {
    expect(isConfirmFlagYes({ 是否函证: '否' })).toBe(false)
    expect(isConfirmFlagYes({ 是否函证: '' })).toBe(false)
    expect(isConfirmFlagYes({})).toBe(false)
  })
})

describe('resolveE0AccountType', () => {
  it('E0-4 按「所属科目」分流长期/短期借款', () => {
    const spec = E0_LIST_SPECS['E0-4']
    expect(resolveE0AccountType({ 所属科目: '长期借款' }, spec)).toEqual({
      accountType: '长期借款',
      fallback: false,
    })
    expect(resolveE0AccountType({ 所属科目: '短期借款' }, spec)).toEqual({
      accountType: '短期借款',
      fallback: false,
    })
  })

  it('E0-4「所属科目」缺失时回退「借款类型」列', () => {
    const spec = E0_LIST_SPECS['E0-4']
    expect(resolveE0AccountType({ 借款类型: '长期借款' }, spec).accountType).toBe('长期借款')
  })

  it('E0-4 两列都缺 → 兜底短期借款并标 fallback（不静默归类）', () => {
    const spec = E0_LIST_SPECS['E0-4']
    expect(resolveE0AccountType({}, spec)).toEqual({ accountType: '短期借款', fallback: true })
  })

  it('E0-3 按「所属科目」细分其他货币资金', () => {
    const spec = E0_LIST_SPECS['E0-3']
    expect(resolveE0AccountType({ 所属科目: '其他货币资金' }, spec).accountType).toBe('其他货币资金')
    expect(resolveE0AccountType({ 所属科目: '银行存款' }, spec).accountType).toBe('银行存款')
    // 「账户类型」是兜底列（源模板 J 列），保证金账户按旧启发式归其他货币资金
    expect(resolveE0AccountType({ 账户类型: '保证金账户' }, spec).accountType).toBe('其他货币资金')
  })

  it('品种固定的清单不产生 fallback（E0-5/E0-6 无分流列）', () => {
    expect(resolveE0AccountType({}, E0_LIST_SPECS['E0-5'])).toEqual({
      accountType: '应付票据',
      fallback: false,
    })
    expect(resolveE0AccountType({}, E0_LIST_SPECS['E0-6'])).toEqual({
      accountType: '理财产品',
      fallback: false,
    })
  })
})

describe('buildSummaryRowsFromListRows — E0-3 货币资金', () => {
  it('仅取「是否函证=是」的行，金额取「账户余额（原币）」', () => {
    const rows = [
      { 所属科目: '银行存款', 索引号: 'F-1', 开户银行: '工商银行', 是否函证: '是', 银行账号: '1001', '账户余额（原币）': 1000, 币种: '人民币' },
      { 所属科目: '银行存款', 索引号: 'F-2', 开户银行: '建设银行', 是否函证: '否', 银行账号: '2001', '账户余额（原币）': 2000 },
    ]
    const out = buildSummaryRowsFromListRows(rows, 'E0-3')
    expect(out).toHaveLength(1)
    expect(out[0].entity_name).toBe('工商银行')
    expect(out[0].amount).toBe(1000)
    expect(out[0].account_no).toBe('1001')
    expect(out[0].currency).toBe('人民币')
    expect(out[0].confirm_index).toBe('F-1')
  })

  it('🔴 同一银行的多个账户各自成行（不被「银行+品种」压成一行）', () => {
    const rows = [
      { 所属科目: '银行存款', 索引号: 'F-1', 开户银行: '工商银行', 是否函证: '是', 银行账号: '1001', '账户余额（原币）': 1000 },
      { 所属科目: '银行存款', 索引号: 'F-1', 开户银行: '工商银行', 是否函证: '是', 银行账号: '1002', '账户余额（原币）': 2000 },
      { 所属科目: '银行存款', 索引号: 'F-1', 开户银行: '工商银行', 是否函证: '是', 银行账号: '1003', '账户余额（原币）': 3000 },
    ]
    const out = buildSummaryRowsFromListRows(rows, 'E0-3')
    expect(out).toHaveLength(3)
    expect(out.map(r => r.amount)).toEqual([1000, 2000, 3000])
    expect(dedupeSummaryRows(out, [])).toHaveLength(3)
  })

  it('同账号多行按 SUMIF 求和（源模板 E0-1!F 列语义）', () => {
    const rows = [
      { 所属科目: '银行存款', 开户银行: '工行', 是否函证: '是', 银行账号: '1001', '账户余额（原币）': 600 },
      { 所属科目: '银行存款', 开户银行: '工行', 是否函证: '是', 银行账号: '1001', '账户余额（原币）': 400 },
    ]
    const out = buildSummaryRowsFromListRows(rows, 'E0-3')
    expect(out).toHaveLength(1)
    expect(out[0].amount).toBe(1000)
  })

  it('无单位名称的行跳过', () => {
    const out = buildSummaryRowsFromListRows([{ 是否函证: '是', '账户余额（原币）': 100 }], 'E0-3')
    expect(out).toHaveLength(0)
  })
})

describe('buildSummaryRowsFromListRows — E0-4 借款', () => {
  it('按 (所属科目, 借款账号) 聚合，长期借款不被吞成短期借款', () => {
    const rows = [
      { 所属科目: '短期借款', 索引号: 'F-3', 开户银行: '工行', 是否函证: '是', 借款账号: 'L-1', 余额: 5000 },
      { 所属科目: '长期借款', 索引号: 'F-3', 开户银行: '工行', 是否函证: '是', 借款账号: 'L-2', 余额: 9000 },
    ]
    const out = buildSummaryRowsFromListRows(rows, 'E0-4')
    expect(out).toHaveLength(2)
    expect(out.map(r => r.account_type)).toEqual(['短期借款', '长期借款'])
    expect(out.map(r => r.amount)).toEqual([5000, 9000])
  })

  it('同账号在两个品种下不合并（SUMIFS 双条件语义）', () => {
    const rows = [
      { 所属科目: '短期借款', 开户银行: '工行', 是否函证: '是', 借款账号: 'X', 余额: 100 },
      { 所属科目: '长期借款', 开户银行: '工行', 是否函证: '是', 借款账号: 'X', 余额: 200 },
    ]
    expect(buildSummaryRowsFromListRows(rows, 'E0-4')).toHaveLength(2)
  })

  it('缺「所属科目」「借款类型」时标 _type_fallback', () => {
    const rows = [{ 开户银行: '工行', 是否函证: '是', 借款账号: 'Y', 余额: 1 }]
    expect(buildSummaryRowsFromListRows(rows, 'E0-4')[0]._type_fallback).toBe(true)
  })
})

describe('buildSummaryRowsFromListRows — E0-5 应付银行承兑汇票', () => {
  const rows = [
    { 索引号: 'F-5', 开户银行: '招商银行', 银行承兑汇票号码: 'BA001', 结算账户账号: '8001', 币种: '人民币', 票面金额: 1000000 },
    { 索引号: 'F-5', 开户银行: '招商银行', 银行承兑汇票号码: 'BA002', 结算账户账号: '8001', 币种: '人民币', 票面金额: 500000 },
    { 索引号: 'F-6', 开户银行: '中信银行', 银行承兑汇票号码: 'BA003', 结算账户账号: '9001', 币种: '人民币', 票面金额: 250000 },
  ]

  it('🔴 无「是否函证」列仍产出行（旧门控会让本品种恒 0 行）', () => {
    const out = buildSummaryRowsFromListRows(rows, 'E0-5')
    expect(out.length).toBeGreaterThan(0)
    // 反向自检：这批 fixture 逐行都没有「是否函证」列
    expect(rows.every(r => !isConfirmFlagYes(r))).toBe(true)
  })

  it('🔴 一函多票：同索引号票面金额求和（SUMIF(E0-5!索引号, E0-1!B, 票面金额)）', () => {
    const out = buildSummaryRowsFromListRows(rows, 'E0-5')
    expect(out).toHaveLength(2)
    expect(out[0].confirm_index).toBe('F-5')
    expect(out[0].amount).toBe(1500000)
    expect(out[1].confirm_index).toBe('F-6')
    expect(out[1].amount).toBe(250000)
  })

  it('结算账户账号组内一致才填，不一致宁缺勿造', () => {
    const same = buildSummaryRowsFromListRows(rows, 'E0-5')
    expect(same[0].account_no).toBe('8001')
    const mixed = buildSummaryRowsFromListRows(
      [
        { 索引号: 'F-7', 开户银行: '浦发', 结算账户账号: 'A', 票面金额: 1 },
        { 索引号: 'F-7', 开户银行: '浦发', 结算账户账号: 'B', 票面金额: 2 },
      ],
      'E0-5',
    )
    expect(mixed).toHaveLength(1)
    expect(mixed[0].account_no).toBeUndefined()
    expect(mixed[0].amount).toBe(3)
  })

  it('索引号缺失的行各自成行（不与他行糊在一起）', () => {
    const out = buildSummaryRowsFromListRows(
      [
        { 开户银行: '甲行', 票面金额: 10 },
        { 开户银行: '乙行', 票面金额: 20 },
      ],
      'E0-5',
    )
    expect(out).toHaveLength(2)
    expect(out.map(r => r.amount)).toEqual([10, 20])
  })

  it('品种恒为「应付票据」', () => {
    expect(buildSummaryRowsFromListRows(rows, 'E0-5').every(r => r.account_type === '应付票据')).toBe(true)
  })
})

describe('buildSummaryRowsFromListRows — E0-6 理财产品', () => {
  it('🔴 无「是否函证」列仍产出行，金额取「产品净值」', () => {
    const rows = [
      { 索引号: 'F-8', 开户行名称及收件人: '兴业银行', 产品名称: '稳赢1号', 币种: '人民币', 持有份额: 100, 产品净值: 1030000 },
    ]
    const out = buildSummaryRowsFromListRows(rows, 'E0-6')
    expect(out).toHaveLength(1)
    expect(out[0].entity_name).toBe('兴业银行')
    expect(out[0].amount).toBe(1030000)
    expect(out[0].account_no).toBe('稳赢1号')
    expect(out[0].account_type).toBe('理财产品')
  })

  it('同索引号下不同产品各自成行（SUMIFS 索引号+产品名称）', () => {
    const rows = [
      { 索引号: 'F-8', 开户行名称及收件人: '兴业银行', 产品名称: '稳赢1号', 产品净值: 100 },
      { 索引号: 'F-8', 开户行名称及收件人: '兴业银行', 产品名称: '稳赢2号', 产品净值: 200 },
    ]
    const out = buildSummaryRowsFromListRows(rows, 'E0-6')
    expect(out).toHaveLength(2)
    expect(out.map(r => r.account_no)).toEqual(['稳赢1号', '稳赢2号'])
  })

  it('wealth-list-v1 英文字段名同样取得到（专属组件已上线）', () => {
    const rows = [
      {
        _row_id: 'r1',
        confirm_index: 'F-8',
        bank_and_recipient: '兴业银行',
        product_name: '稳赢1号',
        currency: '人民币',
        units_held: 1000,
        net_value: 1030000,
      },
    ]
    const out = buildSummaryRowsFromListRows(rows, 'E0-6')
    expect(out).toHaveLength(1)
    expect(out[0].entity_name).toBe('兴业银行')
    expect(out[0].account_no).toBe('稳赢1号')
    // 金额是「产品净值」总额口径，不得乘持有份额
    expect(out[0].amount).toBe(1030000)
    expect(out[0].currency).toBe('人民币')
  })
})

describe('dedupeSummaryRows', () => {
  it('已存在的历史 key（无 account_no）仍能拦住重复带入', () => {
    const existing: ConfirmationRow[] = [
      { _row_id: '1', entity_name: '工行', account_type: '银行存款' } as ConfirmationRow,
    ]
    const out = dedupeSummaryRows(
      [
        { entity_name: '工行', account_type: '银行存款', account_no: '1001' },
        { entity_name: '中行', account_type: '银行存款', account_no: '2001' },
      ],
      existing,
    )
    expect(out).toHaveLength(1)
    expect(out[0].entity_name).toBe('中行')
  })

  it('候选内部按完整键去重（同索引号+品种+账号才算同一条）', () => {
    const out = dedupeSummaryRows(
      [
        { confirm_index: 'F-1', entity_name: '工行', account_type: '银行存款', account_no: '1001' },
        { confirm_index: 'F-1', entity_name: '工行', account_type: '银行存款', account_no: '1001' },
        { confirm_index: 'F-1', entity_name: '工行', account_type: '银行存款', account_no: '1002' },
      ],
      [],
    )
    expect(out).toHaveLength(2)
  })
})

describe('未登记清单编码', () => {
  it('未知 listCode 返回空数组（不抛）', () => {
    expect(buildSummaryRowsFromListRows([{ 开户银行: 'X' }], 'E0-9')).toEqual([])
  })
})
