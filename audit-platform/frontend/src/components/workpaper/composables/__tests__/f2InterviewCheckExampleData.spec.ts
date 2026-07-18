import { describe, expect, it } from 'vitest'
import {
  INTERVIEW_EXAMPLE_CONTRACT_ROWS,
  INTERVIEW_EXAMPLE_SECTIONS,
  isInterviewCheckExampleSheet,
} from '../../f2-special/ipo/f2InterviewCheckExampleData'

describe('f2InterviewCheckExampleData', () => {
  it('识别示例 sheet 名称', () => {
    expect(isInterviewCheckExampleSheet('访谈记录与核对示例')).toBe(true)
    expect(isInterviewCheckExampleSheet('（示例）访谈记录与核对')).toBe(true)
    expect(isInterviewCheckExampleSheet('供应商访谈记录F2-72')).toBe(false)
    expect(isInterviewCheckExampleSheet()).toBe(false)
  })

  it('七个编制分区完整且均有编制指引', () => {
    expect(INTERVIEW_EXAMPLE_SECTIONS).toHaveLength(7)
    expect(INTERVIEW_EXAMPLE_SECTIONS.map((s) => s.title)).toEqual([
      '一、走访的公司基本信息',
      '二、交易基本情况',
      '三、与发行人的主要合同条款核对',
      '四、走访经营场所',
      '五、现场函证',
      '六、关联方关系',
      '七、其他',
    ])
    for (const section of INTERVIEW_EXAMPLE_SECTIONS) {
      expect(section.guide.length).toBeGreaterThan(10)
    }
  })

  it('合同条款核对表覆盖源表关键项目', () => {
    const items = INTERVIEW_EXAMPLE_CONTRACT_ROWS.map((row) => row.item)
    for (const key of [
      '交易模式', '交易规模', '付款方式', '付款期限', '佣金返利',
      '运输方式及费用承担', '质量保证', '退货、换货情况',
      '第三方收款/付款', '其他资金往来', '是否涉诉',
    ]) {
      expect(items).toContain(key)
    }
    const filled = INTERVIEW_EXAMPLE_CONTRACT_ROWS.filter((row) => row.inquiry)
    expect(filled.length).toBeGreaterThanOrEqual(10)
    for (const row of filled) {
      expect(row.crossCheck.length).toBeGreaterThan(0)
    }
  })
})
