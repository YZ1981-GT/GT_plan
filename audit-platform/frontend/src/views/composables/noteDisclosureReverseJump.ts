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
  // G1 交易性金融资产底稿的两张披露表（正向 noteDisclosureJump 均路由到 G1 披露 sheet）
  G1: { listed: '五、2', soe: '八、2' }, // 交易性金融资产
  G1_DERIVATIVE: { listed: '五、3', soe: '八、3' }, // 衍生金融资产（同 G1 底稿，②衍生工具 / 表2）
  // 以下为「正向跳转 + 底稿→附注 sync 已具备、仅补反向跳转」的科目
  // （章节号权威取自 note_template_variant_matrix.json，两变体均为精确编号章节）
  G10: { listed: '五、34', soe: '八、34' }, // 交易性金融负债
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
  H10: { listed: '三、资产处置收益', soe: '八、75' }, // 资产处置收益
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
  H5: { soe: '八、25' },                    // 油气资产（国企专属，上市无独立章节）
  // 损益类关键词标题（DB 可能截断，由 resolveSectionInList 模糊解析）
  K11: { listed: '三、资产减值损失', soe: '八、74' }, // 资产减值损失
  K13: { listed: '三、营业外支出', soe: '八、77' },   // 营业外支出
  // N1 递延所得税资产（与 N3 递延所得税负债共用同一附注章节；正向跳转默认落 N1）。
  // N3 若将来补披露表，可加 N3 条目指向同一章节号（导航共用，数据所有权见
  // spec n1-disclosure-note-linkage · Decision 1）。
  N1: { listed: '五、30', soe: '八、31' }, // 递延所得税资产（和递延所得税负债）
  // J1 应付职工薪酬（五、40 / 八、40，J1 独占，不与 J2 共用；精确===匹配）
  J1: { listed: '五、40', soe: '八、40' },
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
