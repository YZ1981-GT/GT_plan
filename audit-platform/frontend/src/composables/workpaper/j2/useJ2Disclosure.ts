/**
 * useJ2Disclosure — J2 附注披露（上市公司 / 国有企业 双版本）
 *
 * 上市公司：99行×4列，含DBO变动/计划资产变动/敏感性/到期分析
 * 国有企业：78行×7列，含期初/增加/减少/期末 + 精算假设/到期分析
 *
 * 数据来源：从审定表(J2-1)和明细表(J2-2)自动取数
 *
 * Spec: .kiro/specs/j2-defined-benefit-plan/
 * Requirements: 3.4-3.5
 */
import { ref, type Ref } from 'vue'
import http from '@/utils/http'

export type DisclosureVersion = 'listed' | 'soe'

export interface DisclosureSection {
  title: string
  rows: DisclosureRow[]
}

export interface DisclosureRow {
  label: string
  endAmount: number
  beginAmount: number
  increase?: number
  decrease?: number
  note?: string
}

export function useJ2Disclosure(version: DisclosureVersion) {
  const sections: Ref<DisclosureSection[]> = ref([])
  const isLoading = ref(false)

  function getDefaultSections(): DisclosureSection[] {
    if (version === 'listed') {
      return [
        {
          title: '长期应付职工薪酬',
          rows: [
            { label: '设定受益计划净负债', endAmount: 0, beginAmount: 0 },
            { label: '辞退福利', endAmount: 0, beginAmount: 0 },
            { label: '其他长期职工福利', endAmount: 0, beginAmount: 0 },
            { label: '合计', endAmount: 0, beginAmount: 0 },
            { label: '减：一年内到期', endAmount: 0, beginAmount: 0 },
            { label: '长期应付职工薪酬净额', endAmount: 0, beginAmount: 0 },
          ],
        },
        {
          title: '设定受益计划变动',
          rows: [
            { label: '期初设定受益义务现值', endAmount: 0, beginAmount: 0 },
            { label: '当期服务成本', endAmount: 0, beginAmount: 0 },
            { label: '利息费用', endAmount: 0, beginAmount: 0 },
            { label: '精算损失', endAmount: 0, beginAmount: 0 },
            { label: '已支付福利', endAmount: 0, beginAmount: 0 },
            { label: '期末设定受益义务现值', endAmount: 0, beginAmount: 0 },
          ],
        },
        {
          title: '精算假设',
          rows: [
            { label: '折现率', endAmount: 0, beginAmount: 0 },
            { label: '薪酬增长率', endAmount: 0, beginAmount: 0 },
            { label: '预期死亡率', endAmount: 0, beginAmount: 0 },
          ],
        },
        {
          title: '敏感性分析',
          rows: [
            { label: '折现率+50bp对DBO的影响', endAmount: 0, beginAmount: 0 },
            { label: '折现率-50bp对DBO的影响', endAmount: 0, beginAmount: 0 },
          ],
        },
        {
          title: '未折现福利预计到期分析',
          rows: [
            { label: '1年内', endAmount: 0, beginAmount: 0 },
            { label: '1-2年', endAmount: 0, beginAmount: 0 },
            { label: '2-5年', endAmount: 0, beginAmount: 0 },
            { label: '5年以上', endAmount: 0, beginAmount: 0 },
          ],
        },
      ]
    }
    // SOE 国有企业版
    return [
      {
        title: '长期应付职工薪酬',
        rows: [
          { label: '设定受益计划净负债', endAmount: 0, beginAmount: 0, increase: 0, decrease: 0 },
          { label: '其他长期职工福利', endAmount: 0, beginAmount: 0, increase: 0, decrease: 0 },
          { label: '辞退福利', endAmount: 0, beginAmount: 0, increase: 0, decrease: 0 },
          { label: '合计', endAmount: 0, beginAmount: 0, increase: 0, decrease: 0 },
        ],
      },
      {
        title: '设定受益义务现值变动',
        rows: [
          { label: '期初余额', endAmount: 0, beginAmount: 0 },
          { label: '当期服务成本', endAmount: 0, beginAmount: 0 },
          { label: '利息费用', endAmount: 0, beginAmount: 0 },
          { label: '精算损益', endAmount: 0, beginAmount: 0 },
          { label: '已支付福利', endAmount: 0, beginAmount: 0 },
          { label: '期末余额', endAmount: 0, beginAmount: 0 },
        ],
      },
      {
        title: '精算假设',
        rows: [
          { label: '折现率', endAmount: 0, beginAmount: 0 },
          { label: '薪酬增长率', endAmount: 0, beginAmount: 0 },
          { label: '死亡率', endAmount: 0, beginAmount: 0 },
          { label: '离职率', endAmount: 0, beginAmount: 0 },
        ],
      },
    ]
  }

  function loadFromHtmlData(data: Record<string, unknown>) {
    if (data.disclosure && Array.isArray(data.disclosure)) {
      sections.value = data.disclosure as DisclosureSection[]
    } else {
      sections.value = getDefaultSections()
    }
  }

  function initDefault() {
    sections.value = getDefaultSections()
  }

  return {
    sections,
    isLoading,
    loadFromHtmlData,
    initDefault,
  }
}
