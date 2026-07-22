/**
 * H1 附注子节目录（历史 composable / 单测共用）
 * 上市 UI 真源已迁至 H1TabDisclosureListed + h1ListedDisclosureModel；
 * 国企 UI 真源为 H1TabDisclosureSoe + h1SoeDisclosureModel。
 */
export type DisclosureVariant = 'listed' | 'soe'

export interface DisclosureSection {
  key: string
  title: string
  hasTable: boolean
  hasDynamicRows: boolean
}

/** @deprecated 上市 UI 已重建，勿再作为真源 */
export const LISTED_SECTIONS: DisclosureSection[] = [
  { key: 'overview', title: '①固定资产情况', hasTable: true, hasDynamicRows: false },
  { key: 'idle', title: '②暂时闲置的固定资产情况', hasTable: true, hasDynamicRows: true },
  { key: 'operating_lease_out', title: '③通过经营租赁租出的固定资产', hasTable: true, hasDynamicRows: true },
  { key: 'restricted', title: '④未办妥产权证书 / 抵押担保', hasTable: true, hasDynamicRows: true },
  { key: 'clearing', title: '（2）固定资产清理', hasTable: true, hasDynamicRows: true },
]

/** 国企附注子节（与源模板 / note 八、22 对齐） */
export const SOE_SECTIONS: DisclosureSection[] = [
  { key: 'summary', title: '15、固定资产（汇总）', hasTable: true, hasDynamicRows: false },
  { key: 'overview', title: '(1) 固定资产情况', hasTable: true, hasDynamicRows: false },
  { key: 'idle', title: '② 暂时闲置的固定资产情况', hasTable: true, hasDynamicRows: true },
  { key: 'title', title: '③ 未办妥产权证书的固定资产情况', hasTable: true, hasDynamicRows: true },
  { key: 'clearing', title: '(2) 固定资产清理', hasTable: true, hasDynamicRows: true },
]
