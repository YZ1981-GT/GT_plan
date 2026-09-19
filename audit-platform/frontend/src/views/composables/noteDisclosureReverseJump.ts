/**
 * 披露表（底稿）→ 附注模块「反向跳转」：wpCode + variant → 附注章节号（note_section）。
 *
 * 与 noteDisclosureJump.ts（附注 → 披露表，正向）互为镜像，构成单一真源，
 * 避免两个方向各自硬编码章节号导致漂移。
 *
 * 数据方向：披露表 → 附注为单向推送；反向跳转仅用于导航（方便相互编辑确认），
 * 不改动任何数据。
 *
 * 章节号权威来源 note_template_variant_matrix.json：
 *   E1 货币资金 → 上市「五、1」/ 国企「八、1」
 */
import type { RouteLocationRaw } from 'vue-router'

export type DisclosureVariant = 'listed' | 'soe'

export interface NoteSectionVariants {
  /** 上市版附注章节号 */
  listed: string
  /** 国企版附注章节号 */
  soe: string
}

/**
 * 披露节 key → 上市/国企附注章节号映射。
 * 与 noteDisclosureJump.ts 的 isXxxNoteSection 章节判定保持一致（单一真源，两方向不漂移）。
 *
 * 注意 key 通常是 wpCode，但当一个底稿披露表覆盖多个附注节时（如 G1 交易性金融资产底稿
 * 同时覆盖 五、2 交易性 + 五、3 衍生），须用「节级 key」区分，不能只用 wpCode。
 */
export const DISCLOSURE_NOTE_SECTION_MAP: Record<string, NoteSectionVariants> = {
  E1: { listed: '五、1', soe: '八、1' },
  D1: { listed: '五、4', soe: '八、4' }, // 应收票据
  D2: { listed: '五、5', soe: '八、5' }, // 应收账款
  D3: { listed: '五、38', soe: '八、38' }, // 预收款项
  D5: { listed: '五、6', soe: '八、6' }, // 应收款项融资
  D6: { listed: '五、10', soe: '八、11' }, // 合同资产
  D7: { listed: '五、39', soe: '八、39' }, // 合同负债
  D4: { listed: '五、62', soe: '八、64' }, // 营业收入和营业成本
  // G1 交易性金融资产底稿的两张披露表（正向 noteDisclosureJump 均路由到 G1 披露 sheet）
  G1: { listed: '五、2', soe: '八、2' }, // 交易性金融资产
  G1_DERIVATIVE: { listed: '五、3', soe: '八、3' }, // 衍生金融资产（同 G1 底稿，②衍生工具 / 表2）
  // 以下为「正向跳转 + 底稿→附注 sync 已具备、仅补反向跳转」的科目
  // （章节号权威取自 note_template_variant_matrix.json，两变体均为精确编号章节）
  G10: { listed: '五、34', soe: '八、34' }, // 交易性金融负债
  // G7 长期股权投资：主节 五、18 / 八、18（与正向 isG7EquityNoteSection 一致）。
  // 国企披露表还覆盖「七、合并范围的变化」下 13 个子节，各子节标题旁已有 Note 芯片可单独跳转，
  // 故 map 只登记主节（章节号权威 note_template_variant_matrix.json · chang_qi_gu_quan_tou_zi）。
  G7: { listed: '五、18', soe: '八、18' },
  H1: { listed: '五、22', soe: '八、22' }, // 固定资产
  H3: { listed: '五、21', soe: '八、22' }, // 投资性房地产（注：国企版附注章节与固定资产同号八、22，靠内容区分）
  H8: { listed: '五、25', soe: '八、26' }, // 使用权资产
  H9: { listed: '五、47', soe: '八、52' }, // 租赁负债
  I1: { listed: '五、26', soe: '八、27' }, // 无形资产
  I5: { listed: '五、31', soe: '八、32' }, // 其他非流动资产
  // 损益类：listed 用关键词标题（无 五/八 编号，DB 可能截断如「三、信用减值损失（损」，
  // 由 DisclosureEditor.resolveSectionInList 前缀模糊解析为精确章节）；soe 用清晰编号。
  G13: { listed: '三、公允价值变动收益', soe: '八、72' }, // 公允价值变动收益
  G14: { listed: '三、信用减值损失', soe: '八、73' }, // 信用减值损失
  H10: { listed: '三、资产处置收益（损', soe: '八、75' }, // 资产处置收益（listed 章节号是模板 md 截断值，勿「修正」）
  // 对称补齐：正向跳转已具备、本轮补反向的专有章节科目（章节号权威取自 DB note_section↔section_title）。
  F1: { listed: '五、7', soe: '八、7' },   // 预付款项
  F2: { listed: '五、9', soe: '八、10' },  // 存货
  G11: { listed: '五、69', soe: '八、70' }, // 投资收益
  H2: { listed: '五、23', soe: '八、23' }, // 在建工程
  I2: { listed: '五、27', soe: '八、28' }, // 开发支出
  I3: { listed: '五、28', soe: '八、29' }, // 商誉
  I4: { listed: '五、29', soe: '八、30' }, // 长期待摊费用
  I6: { listed: '五、66', soe: '八、67' }, // 研发费用
  K1: { listed: '五、8', soe: '八、9' },   // 其他应收款
  K2: { listed: '五、13', soe: '八、14' },  // 其他流动资产
  K3: { listed: '五、42', soe: '八、42' },  // 其他应付款
  K4: { listed: '五、44', soe: '八、48' },  // 其他流动负债
  K5: { listed: '五、50', soe: '八、55' },  // 预计负债
  K6: { listed: '持有待售资产', soe: '八、12' }, // 持有待售资产
  K7: { listed: '五、51', soe: '八、56' },  // 递延收益
  K8: { listed: '五、64', soe: '八、65' },  // 销售费用
  K9: { listed: '五、65', soe: '八、66' },  // 管理费用
  K10: { listed: '五、68', soe: '八、69' }, // 其他收益
  K12: { listed: '三、营业外收入（注：', soe: '八、76' }, // 营业外收入（listed 章节号是模板 md 截断值，勿「修正」）
  H5: { soe: '八、25' },                    // 油气资产（国企专属，上市无独立章节）
  // 损益类关键词标题（DB 可能截断，由 resolveSectionInList 模糊解析）
  K11: { listed: '三、资产减值损失（损', soe: '八、74' }, // 资产减值损失（listed 章节号是模板 md 截断值，勿「修正」）
  K13: { listed: '三、营业外支出（注：', soe: '八、77' },   // 营业外支出（listed 章节号是模板 md 截断值，勿「修正」）
  // N1 递延所得税资产（与 N3 递延所得税负债共用同一附注章节；正向跳转默认落 N1）。
  // N3 若将来补披露表，可加 N3 条目指向同一章节号（导航共用，数据所有权见
  // spec n1-disclosure-note-linkage · Decision 1）。
  N1: { listed: '五、30', soe: '八、31' }, // 递延所得税资产（和递延所得税负债）
  N2: { listed: '五、41', soe: '八、41' }, // 应交税费
  N4: { listed: '五、63', soe: null }, // 税金及附加（仅上市有独立章节）
  N5: { listed: null, soe: '八、78' }, // 所得税费用（仅国企有独立章节）
  // L1 短期借款（权威 note_template_variant_matrix.json · duan_qi_jie_kuan）
  L1: { listed: '五、33', soe: '八、33' }, // 短期借款
  // L3 长期借款（权威 note_template_variant_matrix.json · chang_qi_jie_kuan）
  L3: { listed: '五、45', soe: '八、49' }, // 长期借款
  // L5 长期应付款（权威 note_template_variant_matrix.json · chang_qi_ying_fu_kuan）
  L5: { listed: '五、48', soe: '八、53' }, // 长期应付款
  // L7 其他非流动负债（权威 note_template_variant_matrix.json · qi_ta_fei_liu_dong_fu_zhai）
  L7: { listed: '五、52', soe: '八、57' }, // 其他非流动负债
  // M 循环权益类（权威 note_template_variant_matrix.json）
  M2: { soe: '八、58' },                    // 实收资本（仅国企）
  M3: { listed: '五、56' },                  // 库存股（仅上市）
  M4: { listed: '五、55', soe: '八、60' },   // 资本公积
  M5: { listed: '五、59', soe: '八、62' },   // 盈余公积
  M6: { listed: '五、61', soe: '八、63' },   // 未分配利润
  M7: { listed: '五、58', soe: '八、61' },   // 专项储备
  M9: { listed: '五、57' },                  // 其他综合收益（仅上市）
  M10: { listed: '五、54', soe: '八、59' },  // 其他权益工具
  // H4 工程物资推送到 H2 在建工程附注章节（子表），反向跳转同样指向在建工程章节。
  H4: { listed: '五、23', soe: '八、23' }, // 工程物资 → 在建工程章节
  // H6 固定资产清理推送到 H1 固定资产附注章节（子表），反向跳转同样指向固定资产章节。
  H6: { listed: '五、22', soe: '八、22' }, // 固定资产清理 → 固定资产章节
  // J1 应付职工薪酬（五、40 / 八、40，J1 独占，不与 J2 共用；精确===匹配）
  J1: { listed: '五、40', soe: '八、40' },
  // F3 应付票据（五、36 / 八、36）
  F3: { listed: '五、36', soe: '八、36' },
  // G8 其他权益工具投资（五、19 / 八、19）
  G8: { listed: '五、19', soe: '八、19' },
  // G9 其他非流动金融资产（五、20 / 八、20）
  G9: { listed: '五、20', soe: '八、20' },
  // G12 套期净损益（五、70 / 八、71）
  G12: { listed: '五、70', soe: '八、71' },
}

/** 解析某披露底稿 + 版本对应的附注章节号；无映射返回 null。 */
export function resolveNoteSectionForDisclosure(
  wpCode: string,
  variant: DisclosureVariant,
): string | null {
  const entry = DISCLOSURE_NOTE_SECTION_MAP[wpCode]
  if (!entry) return null
  return entry[variant] || null
}

/**
 * 构造「跳转回附注模块」的路由。
 * - section：目标附注章节（供 DisclosureEditor onMounted 自动定位）
 * - noteTemplate：强制上市/国企视图（支持自由切换上市↔国企）
 * @returns 路由对象；projectId 缺失或无章节映射时返回 null。
 */
export function buildNoteJumpRoute(
  projectId: string,
  wpCode: string,
  variant: DisclosureVariant,
  year?: number,
): RouteLocationRaw | null {
  const section = resolveNoteSectionForDisclosure(wpCode, variant)
  if (!projectId || !section) return null
  const query: Record<string, string> = {
    section,
    noteTemplate: variant,
  }
  if (year && Number.isFinite(year)) query.year = String(year)
  return {
    path: `/projects/${projectId}/disclosure-notes`,
    query,
  }
}
