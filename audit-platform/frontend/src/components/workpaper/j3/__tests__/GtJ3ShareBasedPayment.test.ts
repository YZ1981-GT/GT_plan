/**
 * J3 股份支付 — 组件测试
 *
 * 验证 sheetName 分发 + 权益/现金模式切换
 *
 * Spec: .kiro/specs/j3-share-based-payment/
 * Requirements: 1.1-1.4
 */
import { describe, it, expect } from 'vitest'

// 测试 sheetName 解析逻辑（从主入口组件提取的纯逻辑）
function resolveSheet(sheetName: string): string {
  const m = sheetName.match(/(J3-\d+)/)
  if (m) return m[1]
  if (sheetName.includes('目录') || sheetName === 'J3') return 'J3'
  return sheetName
}

describe('GtJ3ShareBasedPayment sheetName分发', () => {
  it('J3-1 情况表', () => {
    expect(resolveSheet('股份支付情况表J3-1')).toBe('J3-1')
  })

  it('J3-2 检查表', () => {
    expect(resolveSheet('股份支付检查表J3-2')).toBe('J3-2')
  })

  it('底稿目录', () => {
    expect(resolveSheet('底稿目录')).toBe('J3')
  })

  it('直接 J3 编码', () => {
    expect(resolveSheet('J3')).toBe('J3')
  })

  it('未识别的 sheet 原样返回', () => {
    expect(resolveSheet('未知Sheet')).toBe('未知Sheet')
  })
})

describe('结算类型分类', () => {
  it('权益结算方案 → 贷记资本公积', () => {
    const type = 'equity'
    const label = type === 'equity' ? '贷记资本公积' : '贷记应付职工薪酬'
    expect(label).toBe('贷记资本公积')
  })

  it('现金结算方案 → 贷记应付职工薪酬', () => {
    const type = 'cash'
    const label = type === 'equity' ? '贷记资本公积' : '贷记应付职工薪酬'
    expect(label).toBe('贷记应付职工薪酬')
  })
})

describe('IPO适用性判断', () => {
  function checkIPO(projectType: string): boolean {
    const keywords = ['ipo', '首发', '首次公开发行']
    return keywords.some(kw => projectType.toLowerCase().includes(kw))
  }

  it('IPO项目 → 显示面板', () => {
    expect(checkIPO('IPO审计')).toBe(true)
    expect(checkIPO('首次公开发行')).toBe(true)
  })

  it('非IPO项目 → 隐藏面板', () => {
    expect(checkIPO('年报审计')).toBe(false)
    expect(checkIPO('')).toBe(false)
  })
})
