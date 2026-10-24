/**
 * accountToWpMapping.ts — 科目编码前缀 → 底稿推荐映射（由 wp_account_mapping.json 生成）
 *
 * 用途：挂凭弹窗根据凭证涉及的科目自动推荐相关底稿。
 * 来源：backend/data/wp_account_mapping.json 中 D~N 循环各底稿主条目的 account_codes（76 张底稿、104 行）；
 *       函证底稿（D0 / E0 …）与没有标准科目的底稿不列。
 * 维护：映射表更新后运行 `python backend/scripts/gen/gen_account_to_wp_ts.py --write` 重新生成，`--check` 校验一致。
 *
 * 🔴 本文件由脚本生成，禁止手工编辑。
 */

export interface AccountWpMapping {
  /** 四位科目编码前缀（如 '1001'、'1601'） */
  prefix: string
  /** 底稿编码（如 'E1'、'H1'） */
  wpCode: string
  /** 底稿名称 */
  wpName: string
  /** 审计循环 */
  cycle: string
}

/**
 * 科目前缀 → 底稿映射表。同一前缀可对应多张底稿（调用方按 startsWith 匹配，见 findWpCodesByAccountCode）。
 */
export const ACCOUNT_WP_MAPPINGS: AccountWpMapping[] = [
  // D 销售循环
  { prefix: '1121', wpCode: 'D1', wpName: '应收票据', cycle: 'D' },
  { prefix: '1122', wpCode: 'D2', wpName: '应收账款', cycle: 'D' },
  { prefix: '2203', wpCode: 'D3', wpName: '预收款项', cycle: 'D' },
  { prefix: '6001', wpCode: 'D4', wpName: '营业收入', cycle: 'D' },
  { prefix: '6051', wpCode: 'D4', wpName: '营业收入', cycle: 'D' },
  { prefix: '1141', wpCode: 'D6', wpName: '合同资产', cycle: 'D' },
  { prefix: '2205', wpCode: 'D7', wpName: '合同负债', cycle: 'D' },
  // E 货币资金
  { prefix: '1001', wpCode: 'E1', wpName: '货币资金', cycle: 'E' },
  { prefix: '1002', wpCode: 'E1', wpName: '货币资金', cycle: 'E' },
  { prefix: '1012', wpCode: 'E1', wpName: '货币资金', cycle: 'E' },
  // F 存货与采购
  { prefix: '1123', wpCode: 'F1', wpName: '预付款项', cycle: 'F' },
  { prefix: '1401', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1402', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1403', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1404', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1405', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1406', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1407', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1408', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1409', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1411', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1416', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1421', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1431', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1441', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1451', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1452', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1461', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1471', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '1472', wpCode: 'F2', wpName: '存货', cycle: 'F' },
  { prefix: '2201', wpCode: 'F3', wpName: '应付票据', cycle: 'F' },
  { prefix: '2202', wpCode: 'F4', wpName: '应付账款', cycle: 'F' },
  { prefix: '6401', wpCode: 'F5', wpName: '营业成本', cycle: 'F' },
  { prefix: '6402', wpCode: 'F5', wpName: '营业成本', cycle: 'F' },
  // G 投资
  { prefix: '1101', wpCode: 'G1', wpName: '交易性金融资产', cycle: 'G' },
  { prefix: '1132', wpCode: 'G2', wpName: '应收利息', cycle: 'G' },
  { prefix: '1131', wpCode: 'G3', wpName: '应收股利', cycle: 'G' },
  { prefix: '1504', wpCode: 'G4', wpName: '债权投资', cycle: 'G' },
  { prefix: '1531', wpCode: 'G5', wpName: '长期应收款', cycle: 'G' },
  { prefix: '1506', wpCode: 'G6', wpName: '其他债权投资', cycle: 'G' },
  { prefix: '1511', wpCode: 'G7', wpName: '长期股权投资', cycle: 'G' },
  { prefix: '1507', wpCode: 'G8', wpName: '其他权益工具投资', cycle: 'G' },
  { prefix: '1519', wpCode: 'G9', wpName: '其他非流动金融资产', cycle: 'G' },
  { prefix: '2101', wpCode: 'G10', wpName: '交易性金融负债', cycle: 'G' },
  { prefix: '6111', wpCode: 'G11', wpName: '投资收益', cycle: 'G' },
  { prefix: '6103', wpCode: 'G12', wpName: '净敞口套期收益', cycle: 'G' },
  { prefix: '6101', wpCode: 'G13', wpName: '公允价值变动收益', cycle: 'G' },
  { prefix: '6702', wpCode: 'G14', wpName: '信用减值损失', cycle: 'G' },
  // H 固定资产
  { prefix: '1601', wpCode: 'H1', wpName: '固定资产', cycle: 'H' },
  { prefix: '1602', wpCode: 'H1', wpName: '固定资产', cycle: 'H' },
  { prefix: '1603', wpCode: 'H1', wpName: '固定资产', cycle: 'H' },
  { prefix: '1604', wpCode: 'H2', wpName: '在建工程', cycle: 'H' },
  { prefix: '1521', wpCode: 'H3', wpName: '投资性房地产', cycle: 'H' },
  { prefix: '1605', wpCode: 'H4', wpName: '工程物资', cycle: 'H' },
  { prefix: '1631', wpCode: 'H5', wpName: '油气资产', cycle: 'H' },
  { prefix: '1606', wpCode: 'H6', wpName: '固定资产清理', cycle: 'H' },
  { prefix: '1621', wpCode: 'H7', wpName: '生产性生物资产', cycle: 'H' },
  { prefix: '1641', wpCode: 'H8', wpName: '使用权资产', cycle: 'H' },
  { prefix: '1651', wpCode: 'H8', wpName: '使用权资产', cycle: 'H' },
  { prefix: '2601', wpCode: 'H9', wpName: '租赁负债', cycle: 'H' },
  { prefix: '2651', wpCode: 'H9', wpName: '租赁负债', cycle: 'H' },
  { prefix: '6115', wpCode: 'H10', wpName: '资产处置损益', cycle: 'H' },
  // I 无形资产
  { prefix: '1701', wpCode: 'I1', wpName: '无形资产', cycle: 'I' },
  { prefix: '1702', wpCode: 'I1', wpName: '无形资产', cycle: 'I' },
  { prefix: '1703', wpCode: 'I1', wpName: '无形资产', cycle: 'I' },
  { prefix: '1704', wpCode: 'I2', wpName: '开发支出', cycle: 'I' },
  { prefix: '1711', wpCode: 'I3', wpName: '商誉', cycle: 'I' },
  { prefix: '1801', wpCode: 'I4', wpName: '长期待摊费用', cycle: 'I' },
  { prefix: '6604', wpCode: 'I6', wpName: '研发费用', cycle: 'I' },
  // J 薪酬
  { prefix: '2211', wpCode: 'J1', wpName: '应付职工薪酬', cycle: 'J' },
  { prefix: '2705', wpCode: 'J2', wpName: '长期应付职工薪酬', cycle: 'J' },
  // K 管理
  { prefix: '1221', wpCode: 'K1', wpName: '其他应收款', cycle: 'K' },
  { prefix: '1901', wpCode: 'K2', wpName: '其他流动资产', cycle: 'K' },
  { prefix: '2241', wpCode: 'K3', wpName: '其他应付款', cycle: 'K' },
  { prefix: '2801', wpCode: 'K5', wpName: '预计负债', cycle: 'K' },
  { prefix: '1481', wpCode: 'K6', wpName: '持有待售资产和负债', cycle: 'K' },
  { prefix: '2401', wpCode: 'K7', wpName: '递延收益', cycle: 'K' },
  { prefix: '6601', wpCode: 'K8', wpName: '销售费用', cycle: 'K' },
  { prefix: '6602', wpCode: 'K9', wpName: '管理费用', cycle: 'K' },
  { prefix: '6117', wpCode: 'K10', wpName: '其他收益', cycle: 'K' },
  { prefix: '6701', wpCode: 'K11', wpName: '资产减值损失', cycle: 'K' },
  { prefix: '6301', wpCode: 'K12', wpName: '营业外收入', cycle: 'K' },
  { prefix: '6711', wpCode: 'K13', wpName: '营业外支出', cycle: 'K' },
  // L 筹资
  { prefix: '2001', wpCode: 'L1', wpName: '短期借款', cycle: 'L' },
  { prefix: '2231', wpCode: 'L2', wpName: '应付利息', cycle: 'L' },
  { prefix: '2501', wpCode: 'L3', wpName: '长期借款', cycle: 'L' },
  { prefix: '2502', wpCode: 'L4', wpName: '应付债券', cycle: 'L' },
  { prefix: '2701', wpCode: 'L5', wpName: '长期应付款', cycle: 'L' },
  { prefix: '2711', wpCode: 'L6', wpName: '专项应付款', cycle: 'L' },
  { prefix: '6603', wpCode: 'L8', wpName: '财务费用', cycle: 'L' },
  // M 权益
  { prefix: '2232', wpCode: 'M1', wpName: '应付股利', cycle: 'M' },
  { prefix: '4001', wpCode: 'M2', wpName: '实收资本', cycle: 'M' },
  { prefix: '4201', wpCode: 'M3', wpName: '库存股', cycle: 'M' },
  { prefix: '4002', wpCode: 'M4', wpName: '资本公积', cycle: 'M' },
  { prefix: '4101', wpCode: 'M5', wpName: '盈余公积', cycle: 'M' },
  { prefix: '4104', wpCode: 'M6', wpName: '未分配利润', cycle: 'M' },
  { prefix: '4301', wpCode: 'M7', wpName: '专项储备', cycle: 'M' },
  { prefix: '4003', wpCode: 'M9', wpName: '其他综合收益', cycle: 'M' },
  { prefix: '4401', wpCode: 'M10', wpName: '其他权益工具', cycle: 'M' },
  // N 税费
  { prefix: '1811', wpCode: 'N1', wpName: '递延所得税资产', cycle: 'N' },
  { prefix: '2221', wpCode: 'N2', wpName: '应交税费', cycle: 'N' },
  { prefix: '2901', wpCode: 'N3', wpName: '递延所得税负债', cycle: 'N' },
  { prefix: '6403', wpCode: 'N4', wpName: '税金及附加', cycle: 'N' },
  { prefix: '6801', wpCode: 'N5', wpName: '所得税费用', cycle: 'N' },
]

// 按前缀长度降序排列，匹配时优先匹配最长前缀
const SORTED_MAPPINGS = [...ACCOUNT_WP_MAPPINGS].sort(
  (a, b) => b.prefix.length - a.prefix.length || a.prefix.localeCompare(b.prefix),
)

/**
 * 根据科目编码查找推荐底稿编码（可能多个）。
 *
 * @param accountCode 四位或更长的科目编码（如 '1002.01'）
 * @returns 匹配到的 wp_code 数组（去重），空数组表示无映射
 */
export function findWpCodesByAccountCode(accountCode: string): string[] {
  const code = accountCode.trim()
  if (!code) return []
  const matched = new Set<string>()
  for (const m of SORTED_MAPPINGS) {
    if (code.startsWith(m.prefix)) {
      matched.add(m.wpCode)
    }
  }
  return [...matched]
}

/**
 * 批量推荐：给定多个科目编码，返回所有推荐底稿编码（去重）。
 *
 * 适用于多对多凭证场景：一张凭证借贷两侧涉及多个科目，
 * 每个科目可能映射到不同的底稿。
 */
export function findAllRecommendedWpCodes(accountCodes: string[]): string[] {
  const result = new Set<string>()
  for (const code of accountCodes) {
    for (const wp of findWpCodesByAccountCode(code)) {
      result.add(wp)
    }
  }
  return [...result]
}
