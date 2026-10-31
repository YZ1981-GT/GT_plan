/**
 * 附注目录的章标题（编辑器左侧树 useNoteTree、四栏目录 FourColumnCatalog 共用）。
 *
 * 优先取库内章行（note_section 恰为章号，如「八」）的 section_title：生成链按项目口径写章名，存量项目经
 * backend/scripts/fix/realign_project_notes.py 按四版 Word 对齐（上市「五」单体 / 合并章名不同也由此得到）。
 * 没有章行（早期数据）才退回下面的内置名称，内置名称与种子 note_template_{soe,listed}.json 的章名一致。
 * spec: disclosure-note-template-word-realignment Phase 3
 */

export const SOE_CHAPTER_LABELS: Record<string, string> = {
  '一': '公司（企业）基本情况', '二': '财务报表编制基础', '三': '遵循企业会计准则的声明',
  '四': '重要会计政策、会计估计', '五': '会计政策、会计估计变更及差错更正', '六': '税项',
  '七': '企业合并及合并财务报表', '八': '财务报表主要项目注释',
  '九': '或有事项', '十': '资产负债表日后事项', '十一': '关联方关系及其交易',
  '十二': '母公司财务报表的主要项目附注', '十三': '按照有关财务会计制度应披露的其他内容', '十四': '财务报表之批准',
}

export const LISTED_CHAPTER_LABELS: Record<string, string> = {
  '一': '公司基本情况', '二': '财务报表的编制基础', '三': '重要会计政策及会计估计',
  '四': '税项', '五': '合并财务报表项目附注', '六': '研发支出',
  '七': '在其他主体中的权益', '八': '政府补助', '九': '金融工具风险管理',
  '十': '公允价值', '十一': '关联方及关联交易', '十二': '股份支付',
  '十三': '承诺及或有事项', '十四': '资产负债表日后事项', '十五': '其他重要事项',
  '十六': '公司财务报表主要项目注释', '十七': '补充资料',
}

export interface ChapterRowLike {
  note_section: string
  section_title?: string | null
}

/** 章号（如「八」）在该项目里的标题：章行标题 → 内置名称 → 空串（调用方再兜底）。 */
export function chapterLabel(rows: readonly ChapterRowLike[], prefix: string, templateType?: string | null): string {
  const own = rows.find(r => r.note_section === prefix)?.section_title?.trim()
  if (own) return own
  const labels = templateType === 'listed' ? LISTED_CHAPTER_LABELS : SOE_CHAPTER_LABELS
  return labels[prefix] || ''
}
