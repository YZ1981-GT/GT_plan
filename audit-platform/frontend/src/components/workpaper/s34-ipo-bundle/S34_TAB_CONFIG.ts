/**
 * S34 首发审核（IPO）特项底稿 Bundle — TabDef 分组配置
 *
 * 来源：Phase0 双源核对（s34_structure_reference.md 第二节分组表 + design.md Req 4.3）
 * 产出日期：2026-07（Task 5.1 of s34-ipo-review-bundle spec）
 *
 * 结构：8 业务主题分组 + 1 overview（核查清单总览面板）
 *   - overview: 固定首位，渲染 S34-0 核查事项清单
 *   - 各专项底稿 Tab: 按 S34-0 清单序号排列，分入 8 个业务主题分组
 *
 * 🔴 分组顺序以 S34-0 序号为基准（Req 4.6）
 * 🔴 只有 wpIdMap 中有值的底稿才显示 Tab（Req 8.3, 9.1）
 * 🔴 overview Tab 恒可见（Property 3）
 *
 * Requirements: 4.1, 4.2, 4.3, 4.6
 */

export interface TabDef {
  /** Tab 标识 = sheetName 路由值（'overview' | 'S34-1'...） */
  id: string
  /** Tab 显示名（专项简称） */
  label: string
  /** 业务主题分组 */
  group: string
  /** 子底稿编码（wp_index 查 wp_id）；overview 无此字段 */
  wpCode?: string
  /** 是否含公式子检查表 */
  hasSubTable?: boolean
  /** 子 sheet 名列表（如 ['S34-16-1','S34-16-2']） */
  subSheets?: string[]
}

/** 分组名称常量 */
export const S34_GROUPS = {
  OVERVIEW: '总览',
  EQUITY_INCENTIVE: '股权与激励',
  RELATED_PARTY: '关联与共同投资',
  REVENUE_DISTRIBUTION: '收入与经销',
  COST_RND: '成本费用与研发',
  ASSET_IMPAIRMENT: '资产与减值',
  FINANCE_CONTROL: '财务规范与内控',
  CAPITAL_INVESTMENT: '资金与投资',
  SPECIAL_MATTERS: '特殊事项',
} as const

/**
 * S34 Bundle 完整 Tab 配置（8 分组 + overview = 42 条）
 *
 * 数据来源：s34_structure_reference.md 第一/二/三节交叉验证
 * 分组顺序：S34-0 核查清单序号基准
 *
 * hasSubTable 底稿：S34-2, S34-3, S34-4, S34-8, S34-9, S34-11,
 *   S34-16, S34-18, S34-20, S34-25, S34-30, S34-34
 */
export const S34_TAB_DEFS: TabDef[] = [
  // ─── Overview（固定首位，恒可见）───
  {
    id: 'overview',
    label: '核查清单',
    group: S34_GROUPS.OVERVIEW,
  },

  // ─── 分组1: 股权与激励 ───
  {
    id: 'S34-2',
    label: '期权激励',
    group: S34_GROUPS.EQUITY_INCENTIVE,
    wpCode: 'S34-2',
    hasSubTable: true,
    subSheets: ['S34-2-1', 'S34-2-2'],
  },
  {
    id: 'S34-3',
    label: '股份支付',
    group: S34_GROUPS.EQUITY_INCENTIVE,
    wpCode: 'S34-3',
    hasSubTable: true,
    subSheets: ['S34-3-1'],
  },

  // ─── 分组2: 关联与共同投资 ───
  {
    id: 'S34-4',
    label: '关联交易',
    group: S34_GROUPS.RELATED_PARTY,
    wpCode: 'S34-4',
    hasSubTable: true,
    subSheets: ['S34-4-1'],
  },
  {
    id: 'S34-9',
    label: '共同投资',
    group: S34_GROUPS.RELATED_PARTY,
    wpCode: 'S34-9',
    hasSubTable: true,
    subSheets: ['S34-9-1'],
  },

  // ─── 分组3: 收入与经销 ───
  {
    id: 'S34-16',
    label: '第三方回款',
    group: S34_GROUPS.REVENUE_DISTRIBUTION,
    wpCode: 'S34-16',
    hasSubTable: true,
    subSheets: ['S34-16-1', 'S34-16-2'],
  },
  {
    id: 'S34-18',
    label: '引用第三方数据',
    group: S34_GROUPS.REVENUE_DISTRIBUTION,
    wpCode: 'S34-18',
    hasSubTable: true,
    subSheets: ['S34-18-1'],
  },
  {
    id: 'S34-19',
    label: '经销商模式',
    group: S34_GROUPS.REVENUE_DISTRIBUTION,
    wpCode: 'S34-19',
  },
  {
    id: 'S34-20',
    label: '劳务外包',
    group: S34_GROUPS.REVENUE_DISTRIBUTION,
    wpCode: 'S34-20',
    hasSubTable: true,
    subSheets: ['S34-20-1'],
  },
  {
    id: 'S34-21',
    label: '委外加工',
    group: S34_GROUPS.REVENUE_DISTRIBUTION,
    wpCode: 'S34-21',
  },
  {
    id: 'S34-35',
    label: '收入核查',
    group: S34_GROUPS.REVENUE_DISTRIBUTION,
    wpCode: 'S34-35',
  },

  // ─── 分组4: 成本费用与研发 ───
  {
    id: 'S34-27',
    label: '研发投入认定',
    group: S34_GROUPS.COST_RND,
    wpCode: 'S34-27',
  },
  {
    id: 'S34-28',
    label: '研发资本化',
    group: S34_GROUPS.COST_RND,
    wpCode: 'S34-28',
  },
  {
    id: 'S34-29',
    label: '科研政府补助',
    group: S34_GROUPS.COST_RND,
    wpCode: 'S34-29',
  },
  {
    id: 'S34-32',
    label: '期间费用',
    group: S34_GROUPS.COST_RND,
    wpCode: 'S34-32',
  },

  // ─── 分组5: 资产与减值 ───
  {
    id: 'S34-5',
    label: '应收减值',
    group: S34_GROUPS.ASSET_IMPAIRMENT,
    wpCode: 'S34-5',
  },
  {
    id: 'S34-6',
    label: '固定资产减值',
    group: S34_GROUPS.ASSET_IMPAIRMENT,
    wpCode: 'S34-6',
  },
  {
    id: 'S34-8',
    label: '合并无形资产',
    group: S34_GROUPS.ASSET_IMPAIRMENT,
    wpCode: 'S34-8',
    hasSubTable: true,
    subSheets: ['S34-8-1', 'S34-8-2'],
  },
  {
    id: 'S34-31',
    label: '存货',
    group: S34_GROUPS.ASSET_IMPAIRMENT,
    wpCode: 'S34-31',
  },
  {
    id: 'S34-33',
    label: '商誉减值',
    group: S34_GROUPS.ASSET_IMPAIRMENT,
    wpCode: 'S34-33',
  },
  {
    id: 'S34-40',
    label: '在建工程',
    group: S34_GROUPS.ASSET_IMPAIRMENT,
    wpCode: 'S34-40',
  },

  // ─── 分组6: 财务规范与内控 ───
  {
    id: 'S34-14',
    label: '财务内控',
    group: S34_GROUPS.FINANCE_CONTROL,
    wpCode: 'S34-14',
  },
  {
    id: 'S34-15',
    label: '现金交易',
    group: S34_GROUPS.FINANCE_CONTROL,
    wpCode: 'S34-15',
  },
  {
    id: 'S34-17',
    label: '会计政策变更',
    group: S34_GROUPS.FINANCE_CONTROL,
    wpCode: 'S34-17',
  },
  {
    id: 'S34-22',
    label: '股权集中治理',
    group: S34_GROUPS.FINANCE_CONTROL,
    wpCode: 'S34-22',
  },
  {
    id: 'S34-23',
    label: '互联网信息系统',
    group: S34_GROUPS.FINANCE_CONTROL,
    wpCode: 'S34-23',
  },
  {
    id: 'S34-24',
    label: '信息系统专项',
    group: S34_GROUPS.FINANCE_CONTROL,
    wpCode: 'S34-24',
  },

  // ─── 分组7: 资金与投资 ───
  {
    id: 'S34-10',
    label: '财务性投资',
    group: S34_GROUPS.CAPITAL_INVESTMENT,
    wpCode: 'S34-10',
  },
  {
    id: 'S34-25',
    label: '资金流水',
    group: S34_GROUPS.CAPITAL_INVESTMENT,
    wpCode: 'S34-25',
    hasSubTable: true,
    subSheets: ['S34-25-1', 'S34-25-2', 'S34-25-3'],
  },
  {
    id: 'S34-36',
    label: '投资收益占比',
    group: S34_GROUPS.CAPITAL_INVESTMENT,
    wpCode: 'S34-36',
  },
  {
    id: 'S34-37',
    label: '现金流异常',
    group: S34_GROUPS.CAPITAL_INVESTMENT,
    wpCode: 'S34-37',
  },
  {
    id: 'S34-39',
    label: '应收票据融资',
    group: S34_GROUPS.CAPITAL_INVESTMENT,
    wpCode: 'S34-39',
  },

  // ─── 分组8: 特殊事项 ───
  {
    id: 'S34-1',
    label: '军工涉秘豁免',
    group: S34_GROUPS.SPECIAL_MATTERS,
    wpCode: 'S34-1',
  },
  {
    id: 'S34-7',
    label: '税收优惠',
    group: S34_GROUPS.SPECIAL_MATTERS,
    wpCode: 'S34-7',
  },
  {
    id: 'S34-11',
    label: '业务重组',
    group: S34_GROUPS.SPECIAL_MATTERS,
    wpCode: 'S34-11',
    hasSubTable: true,
    subSheets: ['S34-11-1'],
  },
  {
    id: 'S34-12',
    label: '经营业绩下滑',
    group: S34_GROUPS.SPECIAL_MATTERS,
    wpCode: 'S34-12',
  },
  {
    id: 'S34-13',
    label: '持续经营',
    group: S34_GROUPS.SPECIAL_MATTERS,
    wpCode: 'S34-13',
  },
  {
    id: 'S34-26',
    label: '未盈利/未弥补亏损',
    group: S34_GROUPS.SPECIAL_MATTERS,
    wpCode: 'S34-26',
  },
  {
    id: 'S34-30',
    label: '对赌协议',
    group: S34_GROUPS.SPECIAL_MATTERS,
    wpCode: 'S34-30',
    hasSubTable: true,
    subSheets: ['S34-30-1'],
  },
  {
    id: 'S34-34',
    label: '涉农企业',
    group: S34_GROUPS.SPECIAL_MATTERS,
    wpCode: 'S34-34',
    hasSubTable: true,
    subSheets: ['S34-34-1', 'S34-34-2'],
  },
  {
    id: 'S34-38',
    label: '估值调整协议',
    group: S34_GROUPS.SPECIAL_MATTERS,
    wpCode: 'S34-38',
  },
  {
    id: 'S34-41',
    label: '客户供应商核查',
    group: S34_GROUPS.SPECIAL_MATTERS,
    wpCode: 'S34-41',
  },
]

/** 所有 S34 专项底稿 wp_code 集合（排除 overview） */
export const S34_WP_CODES = S34_TAB_DEFS
  .filter((t) => t.wpCode)
  .map((t) => t.wpCode!) as readonly string[]

/** 含子检查表的底稿编码集合 */
export const S34_WITH_SUB_TABLE = S34_TAB_DEFS
  .filter((t) => t.hasSubTable)
  .map((t) => t.wpCode!) as readonly string[]

/** 分组名称列表（按顺序，不含 overview） */
export const S34_GROUP_NAMES = [
  S34_GROUPS.EQUITY_INCENTIVE,
  S34_GROUPS.RELATED_PARTY,
  S34_GROUPS.REVENUE_DISTRIBUTION,
  S34_GROUPS.COST_RND,
  S34_GROUPS.ASSET_IMPAIRMENT,
  S34_GROUPS.FINANCE_CONTROL,
  S34_GROUPS.CAPITAL_INVESTMENT,
  S34_GROUPS.SPECIAL_MATTERS,
] as const

/**
 * 按分组聚合 TabDef（不含 overview）
 * 用于模板中渲染分组头
 */
export function getTabsByGroup(): Array<{ group: string; tabs: TabDef[] }> {
  const grouped: Array<{ group: string; tabs: TabDef[] }> = []
  for (const groupName of S34_GROUP_NAMES) {
    const tabs = S34_TAB_DEFS.filter(
      (t) => t.group === groupName && t.wpCode,
    )
    if (tabs.length > 0) {
      grouped.push({ group: groupName, tabs })
    }
  }
  return grouped
}
