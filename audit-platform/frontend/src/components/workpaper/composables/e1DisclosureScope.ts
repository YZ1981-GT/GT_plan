/**
 * e1DisclosureScope — E1 货币资金披露**主表行**单一真源（两变体）
 *
 * 行标签逐字取自源 xlsx（openpyxl 实证），每行带 `sourceRef` 指向源单元格，
 * 供后端守卫 `test_note_e1_structure.py` 做「源 xlsx ↔ 附注模板 ↔ 同步载荷」三向比对。
 *
 * **两变体差异（源模板实证，不是笔误）**
 *
 * |            | 上市（R7~R15）                    | 国企（R7~R12）           |
 * |------------|-----------------------------------|--------------------------|
 * | 列头       | `项  目` / `期末数` / `期初数`     | `项 目` / `期末余额` / `年初余额` |
 * | 首行       | `库存现金`                        | **`现金`**               |
 * | 财务公司   | 有 `存放财务公司款项`             | 无                       |
 * | 应计利息   | 有 `存款应计利息`                 | 无                       |
 * | 境外款项   | 有 `其中：存放在境外的款项总额` 行 | **无**（R13 是括注文字） |
 *
 * 🔴 国企版**没有**「其中：存放在境外的款项总额」数据行 —— 源 xlsx R13 是括注
 * 「（如有因抵押、质押或冻结等对使用有限制、存放在境外、有潜在回收风险的款项应单独说明。）」，
 * 被 md 重建当成数据行落进了附注模板（假行），由 `fix_note_e1_monetary_fund_structure.py` 删除。
 *
 * spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/
 *       Requirements 4.1, 4.2, 4.3, 4.4 / Property 5
 */

export type E1DisclosureVariantKey = 'listed' | 'soe'

export interface E1MainRowDef {
  /** 稳定标识（持久化与行匹配用，**不可改**） */
  key: string
  /** 展示名 —— 逐字取自源 xlsx */
  label: string
  /**
   * 审定表跨 sheet 取数键。
   *
   * 🔴 **必须是 `E1-adj-total-{科目码}` 形态，不可改成语义槽名** —— 这是
   * **跨 spec 数据契约**（归档 spec `e1-monetary-fund-refactor` 明确「写出
   * `E1-adj-total-1001/1002/1012` = 三科目审定合计，供报表/附注引用」，
   * `backend/app/routers/wp_formula.py` 亦在引用），且既有项目已按此键持久化，
   * 改键会断链并丢数据。
   *
   * 空串 = 该行无对应键（合计行、境外款项行、以及「存放财务公司款项」/「数字货币」
   * 这两个按准则解释 15 号增设、无一级标准科目的行 → 由审计师手工填或
   * 由 render 的语义槽预填）。
   */
  crossKey: string
  /** 源 xlsx 单元格引用（供守卫反查） */
  sourceRef: string
  /** 合计行（`is_total`，投影器据此加粗） */
  isTotal?: boolean
  /** 「其中：」性质的补充说明行（不参与合计） */
  isMemo?: boolean
}

/** 上市披露主表行 —— 源 xlsx「附注披露信息(上市公司)」R8~R15。 */
export const E1_MAIN_ROWS_LISTED: readonly E1MainRowDef[] = Object.freeze([
  { key: 'cash', label: '库存现金', crossKey: 'E1-adj-total-1001', sourceRef: 'A8' },
  { key: 'bank', label: '银行存款', crossKey: 'E1-adj-total-1002', sourceRef: 'A9' },
  // 准则解释 15 号「可在货币资金项目之下增设」→ 无一级标准科目，无跨 sheet 键
  { key: 'finance_co', label: '存放财务公司款项', crossKey: '', sourceRef: 'A10' },
  {
    key: 'other_mf',
    label: '其他货币资金',
    crossKey: 'E1-adj-total-1012',
    sourceRef: 'A11',
  },
  { key: 'accrued', label: '存款应计利息', crossKey: '', sourceRef: 'A12' },
  // 同上：准则解释 15 号「可增设二级科目」→ 无一级标准科目
  { key: 'digital', label: '数字货币', crossKey: '', sourceRef: 'A13' },
  { key: 'total', label: '合计', crossKey: '', sourceRef: 'A14', isTotal: true },
  {
    key: 'overseas',
    // 🔴 逐字取自源 xlsx R15（改造前底稿写的是缩写「其中：存放境外」，与附注/源模板不一致）
    label: '其中：存放在境外的款项总额',
    crossKey: '',
    sourceRef: 'A15',
    isMemo: true,
  },
])

/** 国企披露主表行 —— 源 xlsx「附注披露信息(国企)」R8~R12。 */
export const E1_MAIN_ROWS_SOE: readonly E1MainRowDef[] = Object.freeze([
  // 🔴 国企版首行字面是「现金」不是「库存现金」（源 xlsx R8）
  { key: 'cash', label: '现金', crossKey: 'E1-adj-total-1001', sourceRef: 'A8' },
  { key: 'bank', label: '银行存款', crossKey: 'E1-adj-total-1002', sourceRef: 'A9' },
  {
    key: 'other_mf',
    label: '其他货币资金',
    crossKey: 'E1-adj-total-1012',
    sourceRef: 'A10',
  },
  { key: 'digital', label: '数字货币', crossKey: '', sourceRef: 'A11' },
  { key: 'total', label: '合计', crossKey: '', sourceRef: 'A12', isTotal: true },
])

export function e1MainRows(variant: E1DisclosureVariantKey): readonly E1MainRowDef[] {
  return variant === 'soe' ? E1_MAIN_ROWS_SOE : E1_MAIN_ROWS_LISTED
}

// ─── 列头（底稿侧按源 xlsx；附注侧的投影列头见 e1NoteSectionMap）──────────────

export interface E1MainColumnLabels {
  label: string
  ending: string
  opening: string
}

/** 底稿披露主表列头 —— 逐字取自源 xlsx R7（上市 `项  目` 两空格 / 国企 `项 目` 一空格）。 */
export const E1_MAIN_COLUMNS: Readonly<Record<E1DisclosureVariantKey, E1MainColumnLabels>> =
  Object.freeze({
    listed: { label: '项  目', ending: '期末数', opening: '期初数' },
    soe: { label: '项 目', ending: '期末余额', opening: '年初余额' },
  })

export function e1MainColumns(variant: E1DisclosureVariantKey): E1MainColumnLabels {
  return E1_MAIN_COLUMNS[variant]
}

/** 参与合计的行（排除合计行与「其中：」备注行）。 */
export function e1SummableRows(variant: E1DisclosureVariantKey): readonly E1MainRowDef[] {
  return e1MainRows(variant).filter((r) => !r.isTotal && !r.isMemo)
}

// ─── 披露说明文本段（源 xlsx 逐段）──────────────────────────────────────────

/**
 * 一段可录入的披露说明。
 *
 * **区分「披露正文」与「编制提示」**：源 xlsx 里 R17/R19/R23（上市）与
 * R13/R14（国企）是括注/提示，属**编制指引**，进折叠提示区与附注模板 `guidance`；
 * 而审计师实际要写进附注 `text_content` 的是对应的**披露正文**。故这里只声明
 * 真正需要录入的段，`guidance` 字段承载源模板的指引原文供 UI 就地展示。
 */
export interface E1NoteTextDef {
  /** 稳定 key（持久化 `E1-disclosure-{variant}-note-{key}`，**不可改**） */
  key: string
  /** 中文标题 —— 会写进 `_note_texts[].title`（附注正文若缺 title 会渲染成英文键） */
  title: string
  /** 源 xlsx 单元格引用 */
  sourceRef: string
  /** 源模板指引原文（编制提示，就地展示，不进附注正文） */
  guidance: string
  /** 该段的 AI prompt（≥20 字 + 写明口径 + 「不得虚构」） */
  aiPrompt: string
  /** 输入框占位提示 */
  placeholder: string
}

const RESTRICTED_AI_PROMPT =
  '根据已提供的货币资金披露主表、②受限制的货币资金明细表与待归类科目数据，' +
  '撰写「受限及境外款项」披露说明。须覆盖：因抵押/质押/冻结等对使用有限制的款项及其原因、' +
  '存放在境外的款项总额、以及其中资金汇回受到限制的部分。' +
  '若数据显示不存在受限或境外款项，则如实表述「不存在」。' +
  '只使用已提供的事实与金额；缺少证据的事项明确标注「待核实」，不得虚构受限事由、担保安排或金额。'

/** 上市披露说明段 —— 源 xlsx「附注披露信息(上市公司)」R18 / R23。 */
export const E1_NOTE_TEXTS_LISTED: readonly E1NoteTextDef[] = Object.freeze([
  {
    key: 'restricted',
    title: '受限及境外款项说明',
    sourceRef: 'A18',
    guidance:
      '（披露因抵押、质押或冻结等对使用有限制的款项，以及存放在境外的款项总额。'
      + '公司应单独披露存放在境外且资金汇回受到限制的款项。）——源模板 A19',
    aiPrompt: RESTRICTED_AI_PROMPT,
    placeholder:
      '例：期末，本公司不存在抵押、质押或冻结、或存放在境外且资金汇回受到限制的款项。',
  },
  {
    key: 'interest',
    title: '存款利息说明',
    sourceRef: 'A23',
    guidance:
      '【提示-关于存款利息的披露：（1）银行存款包括应计利息，指基于实际利率法计提的应计但未到付息期的'
      + '银行存款利息，不包括已到期可收取但于资产负债表日尚未收到的利息（即逾期未收利息，列示于'
      + '报表项目「应收利息」）；（2）可以在表格下方增加说明「银行存款中含应计利息XXX元」，'
      + '也可以增加二级明细「存款应计利息」；（3）这部分利息不属于「现金及现金等价物」。】——源模板 A23',
    aiPrompt:
      '根据已提供的货币资金披露主表「存款应计利息」金额，撰写存款利息披露说明。'
      + '须说明：银行存款中所含应计利息金额（按实际利率法计提、尚未到付息期）、'
      + '该部分不属于现金及现金等价物、且不含逾期未收利息（列示于「应收利息」）。'
      + '金额一律取自已提供数据，不得虚构利率、计提期间或金额。',
    placeholder: '例：上述银行存款中含应计利息 XXX 元，该部分不属于现金及现金等价物。',
  },
])

/** 国企披露说明段 —— 源 xlsx「附注披露信息(国企)」R13 / R14。 */
export const E1_NOTE_TEXTS_SOE: readonly E1NoteTextDef[] = Object.freeze([
  {
    key: 'restricted',
    title: '受限及境外款项说明',
    sourceRef: 'A13',
    guidance:
      '（如有因抵押、质押或冻结等对使用有限制、存放在境外、有潜在回收风险的款项应单独说明。）'
      + '——源模板 A13',
    aiPrompt: RESTRICTED_AI_PROMPT
      + '国企口径还需说明是否存在「有潜在回收风险」的款项及其依据。',
    placeholder:
      '例：期末，本公司不存在因抵押、质押或冻结等对使用有限制、存放在境外或有潜在回收风险的款项。',
  },
  {
    key: 'digital',
    title: '数字货币说明',
    sourceRef: 'A14',
    guidance:
      '（提示：企业持有由中国人民银行发行的数字人民币，可单独增加「数字货币」二级明细项目）'
      + '——源模板 A14',
    aiPrompt:
      '根据已提供的货币资金披露主表「数字货币」金额，撰写数字货币披露说明。'
      + '依据《企业会计准则解释第15号》（财会〔2021〕35号）：企业持有中国人民银行发行的数字人民币，'
      + '可增设「数字货币」二级科目核算，并在资产负债表「货币资金」项目中列报。'
      + '若本项目无数字货币余额则如实表述「不涉及」。不得虚构持有规模、钱包数量或用途。',
    placeholder: '例：期末本公司持有数字人民币 XXX 元，已在「货币资金」项目中列报。',
  },
])

export function e1NoteTexts(variant: E1DisclosureVariantKey): readonly E1NoteTextDef[] {
  return variant === 'soe' ? E1_NOTE_TEXTS_SOE : E1_NOTE_TEXTS_LISTED
}

/** 某段的持久化键。 */
export function e1NoteTextKey(variant: E1DisclosureVariantKey, sectionKey: string): string {
  return `E1-disclosure-${variant}-note-${sectionKey}`
}

/** 旧版单一说明框的持久化键（迁移用：首段为空时承接旧内容，不丢审计师已写的字）。 */
export function e1LegacyNoteKey(variant: E1DisclosureVariantKey): string {
  return `E1-disclosure-${variant}-note`
}
