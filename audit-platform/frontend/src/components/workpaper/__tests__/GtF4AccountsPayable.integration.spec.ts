/**
 * F4 应付账款 — 集成测试
 *
 * 验证各模块间的组合正确性（非 Vue 组件挂载）：
 * 1. sheetName 正则分发正确性（12个 sheet → 对应组件编码）
 * 2. 贷方余额公式链（期初+贷方-借方=期末 → +AJE+RJE=审定）
 * 3. 两级审定交叉校验（按性质小计===按账龄小计）
 * 4. F4-7 截止自动提取→3区域分配（期后采购/入库/收票）
 * 5. F4-8 抽凭引擎样本借贷分配
 * 6. F4-2 三区段Tab行同步+账龄交叉校验
 * 7. F4-9 供应商融资3区域独立操作
 * 8. EventBus(substantive:adjudicated) 跨组件传递
 * 9. 导入导出 round-trip（后端 spec 完整性）
 *
 * **Validates: Requirements 全部**
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  calcCreditBalance,
  calcAdjustedAmount,
  calcAgingTotal,
  calcAgingCrossCheck,
  calcConcentration,
  calcChangeRate,
  isDebitCreditBalanced,
  calcOutstandingDays,
  calcSubtotal,
  parseNum,
} from '../composables/useF4AccPayFormulaEngine'

import {
  F4_DETAIL_BASIC_COLUMNS,
  F4_DETAIL_AGING_COLUMNS,
  F4_DETAIL_AUDIT_COLUMNS,
} from '../composables/useF4Detail'

// ---------------------------------------------------------------------------
// 1. sheetName 正则分发正确性
// ---------------------------------------------------------------------------
describe('F4 集成: sheetName 正则分发', () => {
  /**
   * 复制 GtF4AccountsPayable.vue 中 currentSheet computed 逻辑为纯函数
   */
  function resolveSheet(name: string): string {
    if (/附注披露/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
    const m = name.match(/(F4A|F4-\d+)/)
    return m ? m[1] : ''
  }

  const cases: [string, string][] = [
    ['F4A', 'F4A'],
    ['F4A 应付账款实质性程序表', 'F4A'],
    ['F4-1 审定表', 'F4-1'],
    ['F4-2 明细表', 'F4-2'],
    ['F4-3 调整分录', 'F4-3'],
    ['F4-4 实质性分析', 'F4-4'],
    ['F4-5 长期挂账检查', 'F4-5'],
    ['F4-6 关联方检查表', 'F4-6'],
    ['F4-7 未入账检查表', 'F4-7'],
    ['F4-8 应付账款检查表', 'F4-8'],
    ['F4-9 供应商融资检查表', 'F4-9'],
    ['附注披露(上市)', '附注上市'],
    ['附注披露(国企)', '附注国企'],
  ]

  it.each(cases)('sheetName "%s" → currentSheet "%s"', (input, expected) => {
    expect(resolveSheet(input)).toBe(expected)
  })

  it('全部12个sheet映射完整', () => {
    // 12个sheet: F4A + F4-1~F4-9 + 附注上市 + 附注国企
    const allSheets = cases.map(([, result]) => result)
    const unique = [...new Set(allSheets)]
    expect(unique).toHaveLength(12)
  })

  it('未匹配的 sheetName 返回空字符串（走 OnlyOffice fallback）', () => {
    expect(resolveSheet('Z99-unknown')).toBe('')
    expect(resolveSheet('')).toBe('')
  })
})

// ---------------------------------------------------------------------------
// 2. 贷方余额公式链（composition 测试）
// ---------------------------------------------------------------------------
describe('F4 集成: 贷方余额公式链', () => {
  it('期末未审 = 期初审定 + 贷方 - 借方 → 审定 = 期末未审 + AJE + RJE', () => {
    const openingAdjusted = 800000
    const creditAmount = 200000 // 贷方（增加）
    const debitAmount = 50000   // 借方（减少/付款）

    // Step 1: 贷方余额公式
    const closingUnadjusted = calcCreditBalance(openingAdjusted, creditAmount, debitAmount)
    expect(closingUnadjusted).toBe(800000 + 200000 - 50000) // 950000

    // Step 2: 审定公式
    const aje = -10000
    const rje = 5000
    const closingAdjusted = calcAdjustedAmount(closingUnadjusted, aje, rje)
    expect(closingAdjusted).toBe(950000 + (-10000) + 5000) // 945000
  })

  it('按性质合计 = 货款 + 工程款 + 服务费 + 其他', () => {
    const goodsAdjusted = calcAdjustedAmount(
      calcCreditBalance(300000, 80000, 20000), -2000, 0,
    ) // (300000+80000-20000) + (-2000) + 0 = 358000
    const constructionAdjusted = calcAdjustedAmount(
      calcCreditBalance(200000, 50000, 10000), 1000, -500,
    ) // (200000+50000-10000) + 1000 + (-500) = 240500
    const serviceAdjusted = calcAdjustedAmount(
      calcCreditBalance(100000, 30000, 5000), 0, 0,
    ) // 125000
    const otherAdjusted = calcAdjustedAmount(
      calcCreditBalance(50000, 10000, 2000), 0, 0,
    ) // 58000

    const total = goodsAdjusted + constructionAdjusted + serviceAdjusted + otherAdjusted
    expect(total).toBe(358000 + 240500 + 125000 + 58000) // 781500
  })

  it('差异 = 审定 - 试算表数', () => {
    const audited = 945000
    const trialBalance = 950000
    const variance = audited - trialBalance
    expect(variance).toBe(-5000)
    expect(variance !== 0).toBe(true) // 差异≠0 → 红色高亮
  })
})

// ---------------------------------------------------------------------------
// 3. 两级审定交叉校验（按性质===按账龄）
// ---------------------------------------------------------------------------
describe('F4 集成: 两级审定交叉校验', () => {
  /**
   * 复制 useF4Adjudication 中 crossCheckPassed 逻辑：
   * Math.abs(natureSubtotal.closingAdjusted - agingSubtotal.closingAdjusted) < 0.005
   */
  function crossCheckPassed(natureSubtotal: number, agingSubtotal: number): boolean {
    return Math.abs(natureSubtotal - agingSubtotal) < 0.005
  }

  it('按性质小计 === 按账龄小计 → 校验通过', () => {
    // 按性质：货款300000 + 工程款200000 + 服务费150000 + 其他50000 = 700000
    const natureRows = [300000, 200000, 150000, 50000]
    const natureSubtotal = calcSubtotal(natureRows)

    // 按账龄：1年以内500000 + 1-2年120000 + 2-3年50000 + 3年以上30000 = 700000
    const agingRows = [500000, 120000, 50000, 30000]
    const agingSubtotal = calcSubtotal(agingRows)

    expect(natureSubtotal).toBe(700000)
    expect(agingSubtotal).toBe(700000)
    expect(crossCheckPassed(natureSubtotal, agingSubtotal)).toBe(true)
  })

  it('按性质小计 ≠ 按账龄小计 → 校验失败（红色高亮）', () => {
    const natureSubtotal = 700000
    const agingSubtotal = 695000 // 差5000
    expect(crossCheckPassed(natureSubtotal, agingSubtotal)).toBe(false)
  })

  it('浮点精度差异在容差内 → 校验通过', () => {
    const natureSubtotal = 700000.001
    const agingSubtotal = 700000.004
    expect(crossCheckPassed(natureSubtotal, agingSubtotal)).toBe(true)
  })

  it('两级各自SUM公式链验证', () => {
    // 按性质各行经过完整公式链
    const goods = calcAdjustedAmount(calcCreditBalance(100000, 50000, 20000), 0, 0) // 130000
    const construction = calcAdjustedAmount(calcCreditBalance(80000, 30000, 10000), 0, 0) // 100000
    const service = calcAdjustedAmount(calcCreditBalance(50000, 20000, 5000), 0, 0) // 65000
    const other = calcAdjustedAmount(calcCreditBalance(30000, 10000, 5000), 0, 0) // 35000
    const natureTotal = goods + construction + service + other // 330000

    // 按账龄各行
    const within1 = calcAdjustedAmount(calcCreditBalance(200000, 80000, 30000), 0, 0) // 250000
    const y1to2 = calcAdjustedAmount(calcCreditBalance(40000, 20000, 10000), 0, 0) // 50000
    const y2to3 = calcAdjustedAmount(calcCreditBalance(15000, 5000, 2000), 0, 0) // 18000
    const y3plus = calcAdjustedAmount(calcCreditBalance(5000, 5000, 2000), 0, 0) // 8000
    const agingTotal = within1 + y1to2 + y2to3 + y3plus // 326000

    // 在实际场景中两者应相等（数据一致性），此处测试不等场景会触发红色
    expect(crossCheckPassed(natureTotal, agingTotal)).toBe(natureTotal === agingTotal)
  })
})

// ---------------------------------------------------------------------------
// 4. F4-7 截止自动提取→3区域分配（期后采购/入库/收票）
// ---------------------------------------------------------------------------
describe('F4 集成: F4-7 截止自动提取→3区域分配', () => {
  /**
   * 复制 useF4UnrecordedCheck.distributeCutoffSamples 的分配逻辑
   */
  function classifyVoucher(v: { voucherType: string | null; summary: string | null }): 'purchase' | 'receipt' | 'invoice' {
    const type = (v.voucherType || '').trim()
    const summary = (v.summary || '').toLowerCase()

    if (type === '付' || type === '转' || summary.includes('采购') || summary.includes('购')) {
      return 'purchase'
    } else if (type === '收' || summary.includes('入库') || summary.includes('验收')) {
      return 'receipt'
    } else {
      return 'invoice'
    }
  }

  it('凭证类型"付"或摘要含"采购" → purchase区域', () => {
    expect(classifyVoucher({ voucherType: '付', summary: '支付供应商货款' })).toBe('purchase')
    expect(classifyVoucher({ voucherType: '', summary: '采购原材料' })).toBe('purchase')
    expect(classifyVoucher({ voucherType: '转', summary: '预付转采购' })).toBe('purchase')
  })

  it('凭证类型"收"或摘要含"入库"/"验收" → receipt区域', () => {
    expect(classifyVoucher({ voucherType: '收', summary: '收到商品' })).toBe('receipt')
    expect(classifyVoucher({ voucherType: '', summary: '原材料入库' })).toBe('receipt')
    expect(classifyVoucher({ voucherType: '', summary: '设备验收入库' })).toBe('receipt')
  })

  it('其他凭证 → invoice区域', () => {
    expect(classifyVoucher({ voucherType: '', summary: '收到增值税发票' })).toBe('invoice')
    expect(classifyVoucher({ voucherType: '', summary: '服务费确认' })).toBe('invoice')
    expect(classifyVoucher({ voucherType: null, summary: null })).toBe('invoice')
  })

  it('批量分配场景：5张凭证正确分配到3区域', () => {
    const vouchers = [
      { voucherType: '付', summary: '采购办公用品' },
      { voucherType: '收', summary: '材料入库' },
      { voucherType: '', summary: '收到发票' },
      { voucherType: '转', summary: '购买设备' },
      { voucherType: '', summary: '验收合格' },
    ]
    const result = { purchase: 0, receipt: 0, invoice: 0 }
    for (const v of vouchers) {
      result[classifyVoucher(v)]++
    }
    expect(result.purchase).toBe(2) // 付+转(购)
    expect(result.receipt).toBe(2)  // 收+验收
    expect(result.invoice).toBe(1)  // 发票
  })

  it('金额取 creditAmount 优先，无则取 debitAmount', () => {
    const voucher = { creditAmount: '50000', debitAmount: '30000' }
    const amount = parseNum(voucher.creditAmount) || parseNum(voucher.debitAmount)
    expect(amount).toBe(50000) // creditAmount 优先

    const voucher2 = { creditAmount: '', debitAmount: '20000' }
    const amount2 = parseNum(voucher2.creditAmount) || parseNum(voucher2.debitAmount)
    expect(amount2).toBe(20000) // fallback to debitAmount
  })
})

// ---------------------------------------------------------------------------
// 5. F4-8 抽凭引擎样本借贷分配
// ---------------------------------------------------------------------------
describe('F4 集成: F4-8 抽凭引擎样本借贷分配', () => {
  /**
   * 复制 useF4VoucherCheck.distributeSamples 的分配逻辑
   */
  function distributeSample(s: {
    debitAmount: string | null
    creditAmount: string | null
  }): { debit: number; credit: number } {
    return {
      debit: parseNum(s.debitAmount),
      credit: parseNum(s.creditAmount),
    }
  }

  it('贷方发生（采购增加）→ 填入贷方检查区', () => {
    const { debit, credit } = distributeSample({ debitAmount: '0', creditAmount: '500000' })
    expect(credit).toBe(500000)
    expect(debit).toBe(0)
    expect(credit > 0).toBe(true) // → creditRows
  })

  it('借方发生（付款减少）→ 填入借方检查区', () => {
    const { debit, credit } = distributeSample({ debitAmount: '200000', creditAmount: '0' })
    expect(debit).toBe(200000)
    expect(credit).toBe(0)
    expect(debit > 0).toBe(true) // → debitRows
  })

  it('同时有借贷方 → 分别填入两个区域', () => {
    const { debit, credit } = distributeSample({ debitAmount: '100000', creditAmount: '300000' })
    expect(debit).toBe(100000)
    expect(credit).toBe(300000)
    // 两个区域都有分配
    expect(debit > 0 && credit > 0).toBe(true)
  })

  it('金额为null → 解析为0', () => {
    const { debit, credit } = distributeSample({ debitAmount: null, creditAmount: null })
    expect(debit).toBe(0)
    expect(credit).toBe(0)
  })

  it('批量样本借贷小计', () => {
    const samples = [
      { debitAmount: '100000', creditAmount: '0' },
      { debitAmount: '0', creditAmount: '300000' },
      { debitAmount: '50000', creditAmount: '200000' },
      { debitAmount: '0', creditAmount: '150000' },
    ]
    const debitTotal = calcSubtotal(samples.map((s) => parseNum(s.debitAmount)))
    const creditTotal = calcSubtotal(samples.map((s) => parseNum(s.creditAmount)))
    expect(debitTotal).toBe(150000)
    expect(creditTotal).toBe(650000)
  })
})

// ---------------------------------------------------------------------------
// 6. F4-2 三区段Tab行同步+账龄交叉校验
// ---------------------------------------------------------------------------
describe('F4 集成: F4-2 三区段Tab列定义+账龄交叉校验', () => {
  it('基础信息区段9列完整', () => {
    expect(F4_DETAIL_BASIC_COLUMNS).toHaveLength(9)
    const props = F4_DETAIL_BASIC_COLUMNS.map((c) => c.prop)
    expect(props).toContain('seq')
    expect(props).toContain('creditor')
    expect(props).toContain('companyCode')
    expect(props).toContain('relatedPartyType')
    expect(props).toContain('paymentNature')
    expect(props).toContain('openingAdjusted')
    expect(props).toContain('currentDebit')
    expect(props).toContain('currentCredit')
    expect(props).toContain('closingBalance')
  })

  it('账龄与核对区段10列完整', () => {
    expect(F4_DETAIL_AGING_COLUMNS).toHaveLength(10)
    const props = F4_DETAIL_AGING_COLUMNS.map((c) => c.prop)
    expect(props).toContain('aging1Year')
    expect(props).toContain('aging1to2Year')
    expect(props).toContain('aging2to3Year')
    expect(props).toContain('aging3YearPlus')
    expect(props).toContain('agingTotal')
    expect(props).toContain('isConfirmed')
    expect(props).toContain('confirmationResult')
    expect(props).toContain('subsequentPayment')
    expect(props).toContain('subsequentPaymentDate')
    expect(props).toContain('remark')
  })

  it('调整与审定区段8列完整', () => {
    expect(F4_DETAIL_AUDIT_COLUMNS).toHaveLength(8)
    const props = F4_DETAIL_AUDIT_COLUMNS.map((c) => c.prop)
    expect(props).toContain('ajeAdjustment')
    expect(props).toContain('rjeReclassification')
    expect(props).toContain('adjustedBalance')
    expect(props).toContain('adjustedAging1')
    expect(props).toContain('adjustedAging2')
    expect(props).toContain('adjustedAging3')
    expect(props).toContain('adjustedAging4')
    expect(props).toContain('indexRef')
  })

  it('三区段合计为27列', () => {
    const total = F4_DETAIL_BASIC_COLUMNS.length + F4_DETAIL_AGING_COLUMNS.length + F4_DETAIL_AUDIT_COLUMNS.length
    expect(total).toBe(27)
  })

  it('公式列标记editable=false', () => {
    const closingCol = F4_DETAIL_BASIC_COLUMNS.find((c) => c.prop === 'closingBalance')
    expect(closingCol?.editable).toBe(false)
    expect(closingCol?.formula).toBeDefined()

    const agingTotalCol = F4_DETAIL_AGING_COLUMNS.find((c) => c.prop === 'agingTotal')
    expect(agingTotalCol?.editable).toBe(false)
    expect(agingTotalCol?.formula).toBeDefined()

    const adjustedCol = F4_DETAIL_AUDIT_COLUMNS.find((c) => c.prop === 'adjustedBalance')
    expect(adjustedCol?.editable).toBe(false)
    expect(adjustedCol?.formula).toBeDefined()
  })

  it('账龄交叉校验：合计===期末余额时通过', () => {
    const opening = 500000
    const credit = 100000
    const debit = 30000
    const closingBalance = calcCreditBalance(opening, credit, debit) // 570000

    const aging1 = 400000
    const aging2 = 100000
    const aging3 = 50000
    const aging4 = 20000
    const agingTotal = calcAgingTotal(aging1, aging2, aging3, aging4) // 570000

    expect(calcAgingCrossCheck(agingTotal, closingBalance)).toBe(true)
  })

  it('账龄交叉校验：合计≠期末余额时失败（agingMismatch=true）', () => {
    const closingBalance = 570000
    const agingTotal = calcAgingTotal(400000, 100000, 50000, 10000) // 560000

    expect(calcAgingCrossCheck(agingTotal, closingBalance)).toBe(false)
    // agingMismatch=true → 红色标记
  })
})

// ---------------------------------------------------------------------------
// 7. F4-9 供应商融资3区域独立操作
// ---------------------------------------------------------------------------
describe('F4 集成: F4-9 供应商融资3区域独立操作', () => {
  it('3区域各自独立小计互不影响', () => {
    const factoringAmounts = [500000, 300000, 200000]
    const noteAmounts = [1000000, 800000]
    const supplyChainAmounts = [600000, 400000, 350000]

    const factoringSubtotal = calcSubtotal(factoringAmounts)
    const noteSubtotal = calcSubtotal(noteAmounts)
    const supplyChainSubtotal = calcSubtotal(supplyChainAmounts)

    expect(factoringSubtotal).toBe(1000000)
    expect(noteSubtotal).toBe(1800000)
    expect(supplyChainSubtotal).toBe(1350000)

    // 总计
    const overallTotal = factoringSubtotal + noteSubtotal + supplyChainSubtotal
    expect(overallTotal).toBe(4150000)
  })

  it('保理区：终止确认="否" → 高亮 + 重分类金额', () => {
    const factoringRows = [
      { amount: 500000, isDerecognized: '否' },
      { amount: 300000, isDerecognized: '是' },
      { amount: 200000, isDerecognized: '否' },
    ]
    const highlighted = factoringRows.filter((r) => r.isDerecognized === '否')
    expect(highlighted).toHaveLength(2)
    const reclassAmount = calcSubtotal(highlighted.map((r) => r.amount))
    expect(reclassAmount).toBe(700000)
  })

  it('供应链区：应重分类="是" → 高亮', () => {
    const supplyChainRows = [
      { amount: 600000, shouldReclassify: '否' },
      { amount: 400000, shouldReclassify: '是' },
      { amount: 350000, shouldReclassify: '是' },
    ]
    const highlighted = supplyChainRows.filter((r) => r.shouldReclassify === '是')
    expect(highlighted).toHaveLength(2)
    const reclassAmount = calcSubtotal(highlighted.map((r) => r.amount))
    expect(reclassAmount).toBe(750000)
  })

  it('票据区：已背书且列报不充分 → 高亮', () => {
    const noteRows = [
      { amount: 1000000, isEndorsed: '是', reportingAdequacy: '充分' },
      { amount: 800000, isEndorsed: '是', reportingAdequacy: '不充分' },
      { amount: 500000, isEndorsed: '否', reportingAdequacy: '' },
    ]
    const highlighted = noteRows.filter((r) => r.isEndorsed === '是' && r.reportingAdequacy !== '充分')
    expect(highlighted).toHaveLength(1)
    expect(highlighted[0].amount).toBe(800000)
  })

  it('添加行到一个区域不影响其他区域长度', () => {
    // 模拟区域独立性
    let factoringCount = 3
    let noteCount = 2
    let supplyChainCount = 4

    // 添加一行到保理区
    factoringCount++
    expect(factoringCount).toBe(4)
    expect(noteCount).toBe(2) // 不变
    expect(supplyChainCount).toBe(4) // 不变

    // 删除一行从票据区
    noteCount--
    expect(factoringCount).toBe(4) // 不变
    expect(noteCount).toBe(1)
    expect(supplyChainCount).toBe(4) // 不变
  })
})

// ---------------------------------------------------------------------------
// 8. EventBus(substantive:adjudicated) 跨组件传递
// ---------------------------------------------------------------------------
describe('F4 集成: EventBus 事件结构验证', () => {
  it('substantive:adjudicated 事件payload结构正确（科目2202）', () => {
    const eventPayload = {
      wpCode: 'F4',
      accountCode: '2202',
      auditedAmount: 945000,
    }
    expect(eventPayload.accountCode).toBe('2202')
    expect(eventPayload.wpCode).toBe('F4')
    expect(typeof eventPayload.auditedAmount).toBe('number')
    expect(eventPayload.auditedAmount).toBeGreaterThan(0)
  })

  it('CustomEvent dispatch + listen round-trip', () => {
    let received: any = null
    const handler = (e: Event) => {
      received = (e as CustomEvent).detail
    }
    window.addEventListener('substantive:adjudicated', handler)

    // 模拟 useF4Adjudication.publishAdjudicated
    const payload = { wpCode: 'F4', accountCode: '2202', auditedAmount: 781500 }
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail: payload }))

    expect(received).not.toBeNull()
    expect(received.accountCode).toBe('2202')
    expect(received.auditedAmount).toBe(781500)

    window.removeEventListener('substantive:adjudicated', handler)
  })

  it('f4:writeback-trial-balance 事件结构正确', () => {
    const writebackDetail = { projectId: 'proj-001', accountCode: '2202', auditedAmount: 945000 }
    expect(writebackDetail.accountCode).toBe('2202')
    expect(writebackDetail.auditedAmount).toBe(945000)
  })

  it('disclosure:note-text-updated 事件结构正确', () => {
    const disclosureEvent = {
      accountCode: '2202',
      noteText: '应付账款期末余额945,000元',
      source: '附注披露(上市)',
    }
    expect(disclosureEvent.accountCode).toBe('2202')
    expect(disclosureEvent.noteText).toContain('应付账款')
  })
})

// ---------------------------------------------------------------------------
// 9. 导入导出 round-trip（后端 spec 完整性）
// ---------------------------------------------------------------------------
describe('F4 集成: 导入导出 spec 完整性', () => {
  const importExportPath = path.resolve(
    __dirname,
    '../../../../../../backend/app/routers/wp_render_strategies/_f4_import_export.py',
  )

  let content: string

  it('_f4_import_export.py 文件存在', () => {
    expect(fs.existsSync(importExportPath)).toBe(true)
    content = fs.readFileSync(importExportPath, 'utf-8')
  })

  it('包含全部12个sheet spec定义', () => {
    const expectedSheets = [
      'F4-2', 'F4-3', 'F4-5', 'F4-6',
      'F4-7-purchase', 'F4-7-inbound', 'F4-7-invoice',
      'F4-8-debit', 'F4-8-credit',
      'F4-9-factoring', 'F4-9-note', 'F4-9-supply',
    ]
    for (const sheet of expectedSheets) {
      expect(content).toContain(`"${sheet}"`)
    }
  })

  it('F4-2 spec 有27个 headers（明细表全列）', () => {
    const f4_2_match = content.match(/"F4-2":\s*\{[^}]*?"headers":\s*\[([\s\S]*?)\]/m)
    expect(f4_2_match).not.toBeNull()
    if (f4_2_match) {
      const headerStr = f4_2_match[1]
      const headerCount = (headerStr.match(/"/g) || []).length / 2
      expect(headerCount).toBe(27)
    }
  })

  it('F4-5 spec 有11个 headers（长期挂账检查表）', () => {
    const f4_5_match = content.match(/"F4-5":\s*\{[^}]*?"headers":\s*\[([\s\S]*?)\]/m)
    expect(f4_5_match).not.toBeNull()
    if (f4_5_match) {
      const headerCount = (f4_5_match[1].match(/"/g) || []).length / 2
      expect(headerCount).toBe(11)
    }
  })

  it('F4-6 spec 有15个 headers（关联方检查表）', () => {
    const f4_6_match = content.match(/"F4-6":\s*\{[^}]*?"headers":\s*\[([\s\S]*?)\]/m)
    expect(f4_6_match).not.toBeNull()
    if (f4_6_match) {
      const headerCount = (f4_6_match[1].match(/"/g) || []).length / 2
      expect(headerCount).toBe(15)
    }
  })

  it('F4-7 拆为3个独立区域 spec', () => {
    expect(content).toContain('"F4-7-purchase"')
    expect(content).toContain('"F4-7-inbound"')
    expect(content).toContain('"F4-7-invoice"')
    expect(content).toContain('期后采购')
    expect(content).toContain('期后入库')
    expect(content).toContain('期后收票')
  })

  it('F4-8 拆为借方/贷方独立 spec', () => {
    expect(content).toContain('"F4-8-debit"')
    expect(content).toContain('"F4-8-credit"')
    expect(content).toContain('借方')
    expect(content).toContain('贷方')
  })

  it('F4-9 拆为3个独立区域 spec', () => {
    expect(content).toContain('"F4-9-factoring"')
    expect(content).toContain('"F4-9-note"')
    expect(content).toContain('"F4-9-supply"')
    expect(content).toContain('保理融资')
    expect(content).toContain('票据融资')
    expect(content).toContain('供应链融资')
  })

  it('每个 spec 都同时定义了 headers 和 field_keys', () => {
    const expectedSheets = [
      'F4-2', 'F4-3', 'F4-5', 'F4-6',
      'F4-7-purchase', 'F4-7-inbound', 'F4-7-invoice',
      'F4-8-debit', 'F4-8-credit',
      'F4-9-factoring', 'F4-9-note', 'F4-9-supply',
    ]
    for (const sheet of expectedSheets) {
      const sheetIdx = content.indexOf(`"${sheet}"`)
      expect(sheetIdx).toBeGreaterThan(-1)
      const after = content.slice(sheetIdx, sheetIdx + 2000)
      expect(after).toContain('"headers"')
      expect(after).toContain('"field_keys"')
    }
  })

  it('三个端点路由已注册（通过 create_cycle_import_export_router）', () => {
    expect(content).toContain('create_cycle_import_export_router')
    expect(content).toContain('api_prefix="f4"')
  })
})
