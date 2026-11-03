/**
 * J1 应付职工薪酬披露表（上市 / 国企）默认骨架行 —— 源模板行序逐字（合计行由 `useJ1DisclosureSections` 的 computed 生成）。
 *
 * 原先内联在两个披露 Tab 里；附注页离屏同步（spec note-pull-followup-closure R1）要用同一份骨架实例化
 * `useJ1DisclosureSections`，故原样移到这里由 Tab 与离屏 provider 共用（只复用不复制）。
 * `useJ1DisclosureSections` 会克隆这些行，不改动常量本身。
 */
import type { J1DisclosureRow, J1DisclosureVariant } from './j1DisclosureRowModel'

export interface J1DisclosureDefaults {
  summary: J1DisclosureRow[]
  shortTerm: J1DisclosureRow[]
  postEmployment: J1DisclosureRow[]
}

export const J1_DISCLOSURE_DEFAULTS: Record<J1DisclosureVariant, J1DisclosureDefaults> = {
  listed: {
    // 上市 · 汇总表固定行
    summary: ([
      { id: 's-1', label: '短期薪酬', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 's-2', label: '离职后福利-设定提存计划', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 's-3', label: '辞退福利', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 's-4', label: '一年内到期的其他福利', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
    ]) as J1DisclosureRow[],
    // 上市 ·（1）短期薪酬明细
    shortTerm: ([
      { id: 'st-1', label: '工资、奖金、津贴和补贴', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-2', label: '职工福利费', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-3', label: '社会保险费', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-4', label: '其中：1. 医疗保险费', category: 'short_term', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-5', label: '2. 工伤保险费', category: 'short_term', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-6', label: '3. 生育保险费', category: 'short_term', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-7', label: '住房公积金', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-8', label: '工会经费和职工教育经费', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-9', label: '短期带薪缺勤', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-10', label: '短期利润分享计划', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-11', label: '非货币性福利', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-12', label: '其他短期薪酬', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
    ]) as J1DisclosureRow[],
    // 上市 ·（2）设定提存计划
    postEmployment: ([
      { id: 'pe-1', label: '离职后福利', category: 'post_employment', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'pe-2', label: '其中：1. 基本养老保险费', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'pe-3', label: '2. 失业保险费', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'pe-4', label: '3. 企业年金缴费', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'pe-5', label: '4. 其他', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'pe-6', label: '其他长期职工福利（不适用的删除）', category: 'post_employment', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'pe-7', label: '其中：1. xxx', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'pe-8', label: '2. 其他', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
    ]) as J1DisclosureRow[],
  },
  soe: {
    // 国企 ·（1）应付职工薪酬汇总
    summary: ([
      { id: 's-1', label: '短期薪酬', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 's-2', label: '离职后福利-设定提存计划', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 's-3', label: '辞退福利', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 's-4', label: '一年内到期的其他福利', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 's-5', label: '其他', category: 'summary', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
    ]) as J1DisclosureRow[],
    // 国企 ·（2）短期薪酬
    shortTerm: ([
      { id: 'st-1', label: '工资、奖金、津贴和补贴', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-2', label: '职工福利费', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-3', label: '社会保险费', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-4', label: '其中：医疗保险费', category: 'short_term', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-5', label: '工伤保险费', category: 'short_term', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-6', label: '生育保险费', category: 'short_term', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-7', label: '其他', category: 'short_term', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-8', label: '住房公积金', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-9', label: '工会经费和职工教育经费', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-10', label: '短期带薪缺勤', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-11', label: '短期利润分享计划', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'st-12', label: '其他短期薪酬', category: 'short_term', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
    ]) as J1DisclosureRow[],
    // 国企 ·（3）设定提存计划
    postEmployment: ([
      { id: 'pe-1', label: '离职后福利', category: 'post_employment', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'pe-2', label: '其中：基本养老保险费', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'pe-3', label: '失业保险费', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'pe-4', label: '企业年金缴费', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'pe-5', label: '其他', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'pe-6', label: '其他长期职工福利（不适用的删除）', category: 'post_employment', beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'pe-7', label: '其中：xxx', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
      { id: 'pe-8', label: '其他', category: 'post_employment', indent: 1, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 },
    ]) as J1DisclosureRow[],
  },
}
