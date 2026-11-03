/**
 * 质控分类组别的前端读法（spec trim-followup-residual-findings-closure R3）。
 *
 * 原状（可打红）：A1-11 / A1-12 / A17 / A17-1 / 复核清单各自按 `business_category === 'A'`、首字母或下标判组别
 * ⇒ A1~A8 项目在 A1-11 被当成非 A 类、漏掉质控复核 / EQCR 必签；旧场景值 IPO 被显示成「I类」。
 * 现：项目分类读后端下发的 project_classification（classificationOf），表里存的码按后端同口径归组（categoryGroupOfCode）。
 * CATEGORY_CODES 与后端登记码逐值对拍见 backend tests/test_project_classification.py。
 */
import { describe, expect, it } from 'vitest'
import {
  CATEGORY_CODES, categoryGroupOfCode, classificationOf, describeCategoryGroup, type ProjectClassification,
} from '@/types/projectClassification'

function pc(code: string | null, group: 'A' | 'B' | 'C', defaulted = false): ProjectClassification {
  return {
    category_code: code, category_group: group, defaulted, scenario: 'normal', scenario_label: '常规年审',
    is_ipo: false, is_refinancing: false, is_capital_market: false, tags: [],
  }
}

describe('categoryGroupOfCode', () => {
  it.each([
    ['A', 'A'], ['A1', 'A'], ['a8', 'A'], [' B3 ', 'B'], ['B6', 'B'], ['C', 'C'],
    ['', 'C'], [null, 'C'], ['IPO', 'C'], ['A9', 'C'], ['ABC', 'C'], ['B7', 'C'],
  ] as const)('%s → %s（登记码归组；空 / 未登记 / 旧场景值按 C）', (code, group) => {
    expect(categoryGroupOfCode(code)).toBe(group)
  })

  it('登记码 = 组别 + 细分类，且首字母就是组别', () => {
    expect(CATEGORY_CODES.filter((c) => c.length === 1)).toEqual(['A', 'B', 'C'])
    for (const code of CATEGORY_CODES) expect(categoryGroupOfCode(code)).toBe(code.charAt(0))
  })
})

describe('classificationOf', () => {
  it('从项目详情 / project_context / 复核上下文取 project_classification，或认它本身', () => {
    const classification = pc('A1', 'A')
    expect(classificationOf({ client_name: '客户', project_classification: classification })).toBe(classification)
    expect(classificationOf(classification)).toBe(classification)
  })

  it.each([
    [null], [undefined], ['A1'], [{}], [{ business_category: 'A1' }], [{ project_classification: { category_group: 'D' } }],
  ])('拿不到合法分类解释 ⇒ null（不回退读分类原值）：%j', (source) => {
    expect(classificationOf(source)).toBeNull()
  })
})

describe('describeCategoryGroup', () => {
  it.each([
    [pc('A', 'A'), 'A 类'],
    [pc('A1', 'A'), 'A 类（A1）'],
    [pc('B2', 'B'), 'B 类（B2）'],
    [pc(null, 'C', true), 'C 类（分类未填写）'],
    [null, ''],
  ] as const)('%j → %s', (classification, text) => {
    expect(describeCategoryGroup(classification)).toBe(text)
  })
})
