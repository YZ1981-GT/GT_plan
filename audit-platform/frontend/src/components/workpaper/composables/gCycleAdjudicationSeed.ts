/**
 * gCycleAdjudicationSeed — G 循环审定表「从四表库带入未审数」的**落点声明**（单一真源）。
 *
 * 后端 `four_table/g_cycle_adjudication_prefill` 只如实下发**逐叶子明细**
 * （`{code, name, slot, opening, closing, current}`）；「哪个叶子进哪一行」这件带
 * **会计判断**的事全部集中在本文件，一处可审阅。
 *
 * ## 三条设计铁律
 *
 * 1. **按科目名归类，不按编码**。存货 14xx / 6403 税种 / 1123 性质 / G 类投资族都实证过
 *    「同一编码在不同项目语义不同」。归类顺序 = 声明顺序，先声明者优先，
 *    且**必须**给否决词（`不含`）—— 「其他债权投资」包含「债权投资」。
 *
 * 2. **未命中不兜底**。命中不了的叶子进 `unclassified` 由审计师分配，
 *    **绝不**塞进「其他」行 —— 「其他」是一个真实的披露行，把不明金额堆进去就是造假
 *    （K2 实测把三行坏账准备全堆进「其他」）。
 *
 * 3. **无法从四表判断的维度用「默认落点 + 明示」**，不是静默猜。
 *    典型是「单项计提 / 按组合计提」「交易性 / 划分为 / 指定为」—— 这些是会计判断，
 *    四表里没有。落点取平台既有的**调整回写默认行**（如 G2 的 `gross-collective`），
 *    并在确认框里逐字告知「四表无法区分 X，已默认落在 Y，请按实际情况调整」，
 *    同时给该行写一条溯源备注。
 *
 * ## 为什么落点声明放前端
 *
 * 审定表的 rowKey 分类体系（`g2AdjudicationItems` / `g11Constants` …）是前端资产。
 * 在后端再写一份 rowKey 字面量就是跨语言双真源。守卫
 * `gCycleAdjudicationSeed.spec.ts` 会把本文件声明的每个 rowKey 与各循环的
 * `G*_ADJUDICATION_ITEMS` 逐一比对（不存在 / 不可编辑即判红），故声明写错不会静默上线。
 *
 * spec: .kiro/specs/g-cycle-extraction-mapping-and-disclosure-alignment/
 *       Requirements 3.3, 3.4, 3.5 / Task 3.3
 */
import type {
  AdjPrefillCell,
  AdjPrefillUnclassified,
} from './shared/adjudicationPrefillPlan'

/**
 * G11-1 源模板兜底列示行（`审定表G11-1` R24 逐字「其他」）。
 *
 * openpyxl 直读 `backend/wp_templates/G/G11 投资收益.xlsx` 实证 R7:R24 共 18 行，
 * **没有**「成本法核算的长期股权投资收益」行 —— 故成本法下的被投资单位分红
 * 在源模板里的正确落点就是本行。
 */
export const G11_FALLBACK_ROW = Object.freeze({ rowKey: 'other', label: '其他' })

// ─── 后端载荷形态 ────────────────────────────────────────────────────────────

export interface GAdjPrefillLeaf {
  code: string
  name: string
  slot: string
  opening: number
  closing: number
  current: number
}

export interface GAdjPrefillSlot {
  label: string
  found: boolean
  is_provision: boolean
  codes: string[]
  opening: number
  closing: number
  current: number
}

export interface GAdjPrefill {
  /** `balance` = 资产/负债类（期初+期末）；`current` = 损益类（本期发生额） */
  period: 'balance' | 'current'
  positive_side: 'debit' | 'credit' | ''
  slots: Record<string, GAdjPrefillSlot>
  leaves: GAdjPrefillLeaf[]
  total: { opening: number; closing: number; current: number }
  parent_check: { leaf_sum: number; parent: number; diff: number } | null
}

/** 归一 render 下发的 `html_data.adjudication_prefill`（形态不符一律返 null） */
export function normalizeGAdjPrefill(raw: unknown): GAdjPrefill | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const r = raw as Record<string, unknown>
  if (!Array.isArray(r.leaves) || r.leaves.length === 0) return null
  const period = r.period === 'current' ? 'current' : 'balance'
  const slots: Record<string, GAdjPrefillSlot> = {}
  const rawSlots = (r.slots ?? {}) as Record<string, Record<string, unknown>>
  for (const [k, v] of Object.entries(rawSlots)) {
    if (!v || typeof v !== 'object') continue
    slots[k] = {
      label: String(v.label ?? k),
      found: !!v.found,
      is_provision: !!v.is_provision,
      codes: Array.isArray(v.codes) ? v.codes.map(String) : [],
      opening: Number(v.opening) || 0,
      closing: Number(v.closing) || 0,
      current: Number(v.current) || 0,
    }
  }
  const leaves: GAdjPrefillLeaf[] = []
  for (const item of r.leaves as Array<Record<string, unknown>>) {
    if (!item || typeof item !== 'object') continue
    const code = String(item.code ?? '').trim()
    if (!code) continue
    leaves.push({
      code,
      name: String(item.name ?? '').trim(),
      slot: String(item.slot ?? 'gross'),
      opening: Number(item.opening) || 0,
      closing: Number(item.closing) || 0,
      current: Number(item.current) || 0,
    })
  }
  if (!leaves.length) return null
  const total = (r.total ?? {}) as Record<string, unknown>
  const pc = r.parent_check as Record<string, unknown> | null | undefined
  return {
    period,
    positive_side: r.positive_side === 'debit' || r.positive_side === 'credit'
      ? r.positive_side
      : '',
    slots,
    leaves,
    total: {
      opening: Number(total.opening) || 0,
      closing: Number(total.closing) || 0,
      current: Number(total.current) || 0,
    },
    parent_check: pc && typeof pc === 'object'
      ? {
        leaf_sum: Number(pc.leaf_sum) || 0,
        parent: Number(pc.parent) || 0,
        diff: Number(pc.diff) || 0,
      }
      : null,
  }
}

// ─── 名称归类规则 ────────────────────────────────────────────────────────────

/** 一条归类规则：命中 `any` 中任一关键字、且不含 `not` 中任一关键字 → 落 `rowKey` */
export interface GSeedRule {
  /** 目标审定表行键 */
  rowKey: string
  /** 命中关键字（任一） */
  any: readonly string[]
  /** 否决关键字（任一命中则本规则不适用） */
  not?: readonly string[]
  /** 只对该语义槽生效（缺省 = 全部槽） */
  slot?: string
}

/** 某循环的 seed 声明 */
export interface GSeedSpec {
  /** 期初列字段名（损益类留空） */
  openingField?: string
  /** 期末 / 本期未审数列字段名 */
  closingField: string
  /** 期初列中文名（提示用） */
  openingLabel?: string
  /** 期末 / 本期列中文名 */
  closingLabel: string
  /** 名称归类规则（顺序即优先级） */
  rules: readonly GSeedRule[]
  /**
   * 四表无法判断的维度的**默认落点**：`{slot: rowKey}`。
   *
   * 🔴 只在 `rules` 全不命中、且该维度确实属于「会计判断」时启用，
   * 并**必须**同时填 `defaultNote` 告知审计师。留空 = 不设默认，未命中一律待归类。
   */
  defaults?: Readonly<Record<string, string>>
  /** 默认落点的告知文案（确认框逐字展示；有 `defaults` 时必填） */
  defaultNote?: string
  /** 行标签查找（守卫用；由各循环的 ADJUDICATION_ITEMS 提供） */
  labelOf?: (rowKey: string) => string
}

/** 名称归一：去空白 / 下划线 / 括号，转小写（与后端 `normalize_account_name` 同口径） */
export function normalizeSeedName(name: string | null | undefined): string {
  return String(name ?? '')
    .replace(/[\s\u3000_－\-—()（）【】\[\]:：、,，.。/\\]+/g, '')
    .toLowerCase()
}

/** 按规则给单个叶子定落点行；无命中返回 `null` */
export function classifySeedLeaf(
  leaf: GAdjPrefillLeaf,
  spec: GSeedSpec,
): string | null {
  const n = normalizeSeedName(leaf.name)
  if (!n) return null
  for (const rule of spec.rules) {
    if (rule.slot && rule.slot !== leaf.slot) continue
    if (rule.not?.some((kw) => n.includes(normalizeSeedName(kw)))) continue
    if (rule.any.some((kw) => n.includes(normalizeSeedName(kw)))) return rule.rowKey
  }
  return null
}

// ─── 载荷 → 待写入格 ─────────────────────────────────────────────────────────

export interface GSeedResult {
  cells: AdjPrefillCell[]
  unclassified: AdjPrefillUnclassified[]
  absentSlots: Array<{ slotKey: string; label: string }>
  /** 本次用到默认落点的行（提示文案用） */
  usedDefaults: Array<{ rowKey: string; label: string }>
}

/**
 * 把后端载荷按声明摊到审定表格上。
 *
 * 同一行可能收到多个叶子 → **累加**（一个审定行对应多个客户子科目是常态）。
 */
export function buildGSeedCells(
  prefill: GAdjPrefill | null,
  spec: GSeedSpec,
): GSeedResult {
  const out: GSeedResult = { cells: [], unclassified: [], absentSlots: [], usedDefaults: [] }
  if (!prefill) return out

  for (const [slotKey, slot] of Object.entries(prefill.slots)) {
    if (!slot.found) out.absentSlots.push({ slotKey, label: slot.label })
  }

  // rowKey → {opening, closing, codes}
  const agg = new Map<string, { opening: number; closing: number; codes: string[] }>()
  const defaulted = new Set<string>()

  for (const leaf of prefill.leaves) {
    let rowKey = classifySeedLeaf(leaf, spec)
    if (!rowKey) {
      const fallback = spec.defaults?.[leaf.slot]
      if (fallback) {
        rowKey = fallback
        defaulted.add(fallback)
      } else {
        out.unclassified.push({
          code: leaf.code,
          name: leaf.name,
          amount: prefill.period === 'current' ? leaf.current : leaf.closing,
          opening: prefill.period === 'current' ? 0 : leaf.opening,
        })
        continue
      }
    }
    const bucket = agg.get(rowKey) ?? { opening: 0, closing: 0, codes: [] }
    bucket.opening += leaf.opening
    bucket.closing += prefill.period === 'current' ? leaf.current : leaf.closing
    if (!bucket.codes.includes(leaf.code)) bucket.codes.push(leaf.code)
    agg.set(rowKey, bucket)
  }

  const labelOf = spec.labelOf ?? ((k: string) => k)
  for (const [rowKey, v] of agg) {
    const label = labelOf(rowKey)
    if (spec.openingField && prefill.period === 'balance') {
      out.cells.push({
        rowKey,
        field: spec.openingField,
        amount: round2(v.opening),
        label,
        periodLabel: spec.openingLabel ?? '期初未审',
        sourceCodes: [...v.codes],
      })
    }
    out.cells.push({
      rowKey,
      field: spec.closingField,
      amount: round2(v.closing),
      label,
      periodLabel: spec.closingLabel,
      sourceCodes: [...v.codes],
    })
    if (defaulted.has(rowKey)) out.usedDefaults.push({ rowKey, label })
  }
  return out
}

function round2(v: number): number {
  return Math.round((Number(v) || 0) * 100) / 100
}

// ═════════════════════════════════════════════════════════════════════════════
// 各循环声明（会计判断集中在此，逐条写依据）
// ═════════════════════════════════════════════════════════════════════════════

/**
 * G2 应收利息（`1132`）。
 *
 * 审定表结构 = `(一)原值 / (二)坏账准备` × `单项计提 / 按组合计提`。
 *
 * 🔴 **两处只能默认、不能推断**：
 * - 「单项计提 / 按组合计提」是**减值方法的会计判断**，四表里没有 → 默认落
 *   `gross-collective`（= 平台既有的 `G2_ADJ_WRITEBACK_ROW_KEY`，G2-4 调整回写也用它）。
 * - 「坏账准备」段**不由本循环取数**：应收利息的坏账在 `1231` 族（由 D/K 循环管），
 *   `G2_SPEC` 只声明 `gross` 槽 → 备抵段永不 seed，由审计师按 G2-7 坏账测算表填。
 *
 * ⚠️ 后端曾按「利息来源」（债权投资利息 / 定期存款利息 …）预聚合成桶，
 * 而那套 rowKey 早已随 G2-1 重建废弃，`LEGACY_ROW_KEY_MAP` 里
 * `deposit-interest → provision-collective` 是**纯位置迁移、语义不成立** ——
 * 照桶键 seed 会把债券利息填进坏账准备行。故本声明不使用任何来源分类。
 */
export const G2_SEED_SPEC: GSeedSpec = {
  openingField: 'openingUnadjusted',
  closingField: 'closingUnadjusted',
  openingLabel: '期初未审',
  closingLabel: '期末未审',
  rules: [],
  defaults: { gross: 'gross-collective' },
  defaultNote:
    '四表库无法区分「单项计提 / 按组合计提坏账准备」（属减值方法的会计判断），'
    + '已统一落在「按组合计提坏账准备」行，请按实际计提方法调整；'
    + '「二、应收利息坏账准备」段不由本循环取数（坏账在 1231 科目族，由 D/K 循环管），请手工填列。',
}

/**
 * G11 投资收益（`6111`，损益类，口径 = 本期发生额贷方）。
 *
 * 18 行细目**全部**靠客户子科目名归类，未命中一律待归类 —— 「其他」行是源模板
 * 的真实披露行，把不明投资收益堆进去会让附注失真。
 *
 * 归类顺序即优先级，几处必须的否决词：
 * - 「其他债权投资」含「债权投资」→ 其他债权投资的两条必须**先**声明；
 * - 「处置」与「持有期间」要分开，否则「处置交易性金融资产」会被「交易性金融资产」吃掉。
 */
export const G11_SEED_SPEC: GSeedSpec = {
  closingField: 'currentUnadjusted',
  closingLabel: '本期未审',
  rules: [
    // 其他债权投资（必须先于「债权投资」）
    { rowKey: 'oth_debt_dispose', any: ['其他债权投资处置', '处置其他债权投资'] },
    { rowKey: 'oth_debt_hold_interest', any: ['其他债权投资'] },
    // 其他非流动金融资产（必须先于泛化的「金融资产」）
    { rowKey: 'onfa_dispose', any: ['处置其他非流动金融资产', '其他非流动金融资产处置'] },
    { rowKey: 'onfa_hold', any: ['其他非流动金融资产'] },
    // 其他权益工具投资
    { rowKey: 'oei_dividend', any: ['其他权益工具'] },
    // 长期股权投资
    { rowKey: 'equity_method', any: ['权益法'] },
    {
      rowKey: 'dispose_hfs_lt',
      any: ['持有待售'],
    },
    { rowKey: 'dispose_lt_equity', any: ['处置长期股权投资', '长期股权投资处置'] },
    // 债权投资（放在「其他债权投资」之后）
    { rowKey: 'debt_dispose', any: ['债权投资处置', '处置债权投资'] },
    { rowKey: 'debt_hold_interest', any: ['债权投资', '持有至到期'] },
    // 交易性金融资产
    { rowKey: 'trading_dispose', any: ['处置交易性', '交易性金融资产处置'] },
    { rowKey: 'trading_hold', any: ['交易性金融资产'] },
    // 企业合并
    { rowKey: 'control_fv_gain', any: ['取得控制权'] },
    { rowKey: 'loss_control_fv_gain', any: ['丧失控制权'] },
    // 衍生 / 套期 / 债务重组
    { rowKey: 'derivative_dispose', any: ['衍生'] },
    { rowKey: 'hedge_ineffective', any: ['套期'] },
    { rowKey: 'debt_restructuring', any: ['债务重组'] },
  ],
  // 🔴 **不设默认落点**：18 行是具体的投资收益来源，猜错等于把钱记到错误来源上。
}

/**
 * 「待归类叶子 → 指定行」的**显式**归入（审计师主动点按钮才走这条路）。
 *
 * 🔴 与 `GSeedSpec.defaults` 的区别：`defaults` 是自动路径的默认落点（只用于
 * 「单项/组合」这类纯会计判断维度）；本函数是**审计师显式动作** ——
 * 用于源模板确实设了兜底列示行的场景（G11-1 源模板 R24 就叫「其他」，且
 * 源模板**没有**「成本法核算的长期股权投资收益」行，故成本法分红的正确落点就是它）。
 *
 * 自动路径仍然不兜底：`G11_SEED_SPEC.defaults` 为空，未命中一律进「待归类」，
 * 由审计师看到金额与科目名后决定是否一键归入。
 */
export function buildExplicitFallbackCells(
  unclassified: readonly AdjPrefillUnclassified[],
  target: { rowKey: string; label: string },
  spec: Pick<GSeedSpec, 'openingField' | 'closingField' | 'openingLabel' | 'closingLabel'>,
  period: 'balance' | 'current' = 'current',
): AdjPrefillCell[] {
  if (!unclassified.length) return []
  const codes = unclassified.map((u) => u.code)
  const closing = round2(unclassified.reduce((s, u) => s + u.amount, 0))
  const opening = round2(unclassified.reduce((s, u) => s + u.opening, 0))
  const cells: AdjPrefillCell[] = []
  if (spec.openingField && period === 'balance') {
    cells.push({
      rowKey: target.rowKey,
      field: spec.openingField,
      amount: opening,
      label: target.label,
      periodLabel: spec.openingLabel ?? '期初未审',
      sourceCodes: codes,
    })
  }
  cells.push({
    rowKey: target.rowKey,
    field: spec.closingField,
    amount: closing,
    label: target.label,
    periodLabel: spec.closingLabel,
    sourceCodes: codes,
  })
  return cells
}

/**
 * G6 其他债权投资（`1506`）的公允价值段落点 —— 与其它循环不同，**按叶子逐项落占位行**。
 *
 * 源模板「一、公允价值」段是 4 个占位行（`投资项目1..4`），故按叶子顺序逐一落。
 * 超过 4 个叶子时余下的进待归类（固定 4 行、行数是源模板限制，不能动态加行）。
 *
 * ⚠️ `G6_ADJUDICATION_ITEMS` 的行标签是**静态常量**、行 store（`G6AdjStoredCell`）
 * 里没有 label 字段 → **改不了行名**。故不做改名，而是把「占位行 ← 来源子科目」
 * 的对应关系 `mappings` 交调用方在确认框里逐条展示，避免审计师看到
 * 「投资项目1 = 700」却不知道钱从哪个子科目来。
 *
 * 「二、摊余成本」段不 seed：`（一）投资成本 / （二）利息调整` 的拆分是摊余成本法
 * 核算结果，四表只有余额、拆不出来；`（四）减值准备` 在 CAS22 下 FVOCI 债务工具的
 * 减值计入其他综合收益、不冲减账面价值，也不由 `1506` 取数。
 */
export const G6_FV_PLACEHOLDER_ROWS = ['fv-item-1', 'fv-item-2', 'fv-item-3', 'fv-item-4'] as const

export interface G6FvSeedResult extends GSeedResult {
  /** 占位行 ← 来源子科目对应关系（供确认框展示，不写入任何列） */
  mappings: Array<{ rowKey: string; code: string; name: string }>
}

export function buildG6FvSeedCells(
  prefill: GAdjPrefill | null,
  labelOf: (rowKey: string) => string = (k) => k,
): G6FvSeedResult {
  return _buildPlaceholderSeedCells(prefill, [...G6_FV_PLACEHOLDER_ROWS], labelOf)
}

/**
 * G8 其他权益工具投资（`1507`）的公允价值段落点 —— 与 G6 同款占位行范式。
 *
 * G8-1 有 10 个固定行（`fv_1` ~ `fv_10`），标签为 `权益工具投资(FVOCI)/其他/被投资单位1~8`，
 * 按叶子顺序逐一落（同 G6 的 4 行 → G8 是 10 行，容量更大）。
 */
export const G8_FV_PLACEHOLDER_ROWS = Array.from(
  { length: 10 },
  (_, i) => `fv_${i + 1}`,
) as string[]

export function buildG8FvSeedCells(
  prefill: GAdjPrefill | null,
  labelOf: (rowKey: string) => string = (k) => k,
): G6FvSeedResult {
  return _buildPlaceholderSeedCells(prefill, G8_FV_PLACEHOLDER_ROWS, labelOf)
}

/**
 * G9 其他非流动金融资产（`1519`）—— 15 行分三组，跳过 `isGroupTotal` 小计行。
 *
 * 可编辑行 = `fvtpl_2~8` / `fvoci_2~4` / `amort_2~3`（12 行），
 * 小计行 `fvtpl_1`/`fvoci_1`/`amort_1` 不可编辑，不落 seed。
 */
export const G9_EDITABLE_ROWS = [
  'fvtpl_2', 'fvtpl_3', 'fvtpl_4', 'fvtpl_5', 'fvtpl_6', 'fvtpl_7', 'fvtpl_8',
  'fvoci_2', 'fvoci_3', 'fvoci_4',
  'amort_2', 'amort_3',
] as const

export function buildG9SeedCells(
  prefill: GAdjPrefill | null,
  labelOf: (rowKey: string) => string = (k) => k,
): G6FvSeedResult {
  return _buildPlaceholderSeedCells(prefill, [...G9_EDITABLE_ROWS], labelOf)
}

/** 通用占位行 seed 逻辑（G6/G8/G9 共用） */
function _buildPlaceholderSeedCells(
  prefill: GAdjPrefill | null,
  placeholderRows: string[],
  labelOf: (rowKey: string) => string,
): G6FvSeedResult {
  const out: G6FvSeedResult = {
    cells: [], unclassified: [], absentSlots: [], usedDefaults: [], mappings: [],
  }
  if (!prefill) return out
  for (const [slotKey, slot] of Object.entries(prefill.slots)) {
    if (!slot.found) out.absentSlots.push({ slotKey, label: slot.label })
  }
  const leaves = prefill.leaves.filter((l) => l.slot === 'gross')
  leaves.forEach((leaf, i) => {
    const rowKey = placeholderRows[i]
    if (!rowKey) {
      out.unclassified.push({
        code: leaf.code, name: leaf.name, amount: leaf.closing, opening: leaf.opening,
      })
      return
    }
    const label = labelOf(rowKey)
    out.mappings.push({ rowKey, code: leaf.code, name: leaf.name })
    out.cells.push({
      rowKey,
      field: 'openingUnadjusted',
      amount: round2(leaf.opening),
      label,
      periodLabel: '期初未审',
      sourceCodes: [leaf.code],
    })
    out.cells.push({
      rowKey,
      field: 'closingUnadjusted',
      amount: round2(leaf.closing),
      label,
      periodLabel: '期末未审',
      sourceCodes: [leaf.code],
    })
  })
  return out
}

/**
 * G4 债权投资（`1504`，资产负债表，备抵 `1505`）。
 *
 * 审定表结构 = `一、原值` × `(单项计提 / 按组合计提)` + `二、减值准备` × `(单项 / 组合)` + `三、净值`。
 *
 * 🔴 **「单项计提 / 按组合计提」是减值方法的会计判断**，四表里没有：
 * - 原值默认落 `original-collective`（按组合计提坏账准备），与 G2 同款处理。
 * - 减值准备默认落 `impairment-collective`（按组合计提减值准备）。
 * - 备抵科目 `1505` 的叶子通过 `slot='provision'` 标识，按关键字归入减值段行。
 *
 * ⚠️ 四表库只有余额无法区分减值方法 → 默认 + 明示审计师调整。
 */
export const G4_SEED_SPEC: GSeedSpec = {
  openingField: 'openingUnadjusted',
  closingField: 'closingUnadjusted',
  openingLabel: '期初未审',
  closingLabel: '期末未审',
  rules: [
    // provision slot → 减值准备段（备抵科目 1505 的叶子）
    { rowKey: 'impairment-collective', any: ['减值', '坏账', '准备'], slot: 'provision' },
  ],
  defaults: { gross: 'original-collective', provision: 'impairment-collective' },
  defaultNote:
    '四表库无法区分「单项计提 / 按组合计提坏账准备」（属减值方法的会计判断），'
    + '原值已统一落在「按组合计提坏账准备」行，减值准备已统一落在对应减值行；'
    + '请按实际计提方法调整。',
}

/**
 * G10 交易性金融负债（`2101`，负债类，贷方科目）。
 *
 * 审定表结构 = `(一) 初始金额` + `(二) 累计公允价值变动` + `(三) 账面余额(=公允价值)`。
 *
 * 🔴 **三组结构（成本 / FV 变动 / 账面）无法从 TB 余额拆分**：
 * TB 只有每个子科目的总余额，不含「初始金额」与「累计公允价值变动」的拆分信息 ——
 * 两者之和才等于账面余额（= TB 余额）。
 *
 * 设计：默认落 `book-collective`（「（三）账面余额·按组合」行），因为 TB 余额即账面余额。
 * 如需拆分为初始金额 + FV 变动，需审计师从 G10-2 明细/子科目会计核算中手工分摊。
 * 无规则（子科目名无法映射到成本/FV 变动维度）。
 */
export const G10_SEED_SPEC: GSeedSpec = {
  openingField: 'openingUnadjusted',
  closingField: 'closingUnadjusted',
  openingLabel: '期初未审',
  closingLabel: '期末未审',
  rules: [],
  defaults: { gross: 'book-collective' },
  defaultNote:
    '四表库只有科目余额，无法拆分为「初始金额」与「累计公允价值变动」'
    + '（两者之和 = 账面余额 = TB 余额），已统一落在「（三）账面余额·按组合」行；'
    + '如需拆分请手工调整。',
}

/**
 * G1 交易性金融资产（`1101`，资产负债表）。
 *
 * 审定表结构 = `(投资成本 / 累计公允价值变动)` × `(交易性 / 划分为 / 指定为)` × `品种(股票/债券/基金/权证/其他)`。
 * rowKey 格式 = `{section}-{class}-{product}`。
 *
 * 🔴 **三个维度中两个无法从四表推断**：
 * 1. `section`（成本 vs FV 变动）—— 可从子科目名推断：
 *    - `1101.01.01 _成本` → `cost`
 *    - `1101.01.02 _公允价值变动` → `fv`
 *    - 平铺形态 `110101`/`110102` 同理
 * 2. `class`（交易性 / 划分为 / 指定为）—— **会计判断**，四表无信息 → 默认 `trading`
 * 3. `product`（股票/债券/基金/权证/其他）—— 客户子科目名多为银行户名/部门名
 *    （如「招行基本户」），通常无品种关键字 → 默认 `other`
 *
 * 设计：
 * - 规则只做 section 判定（含「公允价值变动」→ fv；含「成本」/「投资」→ cost）
 * - class 和 product 统一默认为 `trading` + `other`
 * - 多分类/多品种时须审计师手工用分摊对话框分配
 */
export const G1_SEED_SPEC: GSeedSpec = {
  openingField: 'openingUnadjusted',
  closingField: 'closingUnadjusted',
  openingLabel: '期初未审',
  closingLabel: '期末未审',
  rules: [
    // section 判定：子科目名含「公允价值变动」→ fv；含「成本」/「投资」→ cost
    { rowKey: 'fv-trading-other', any: ['公允价值变动'] },
    { rowKey: 'cost-trading-other', any: ['成本', '投资'] },
  ],
  defaults: { gross: 'cost-trading-other' },
  defaultNote:
    '四表库无法区分交易性金融资产的分类（交易性 / 划分为 / 指定为）与品种（股票 / 债券 / 基金等），'
    + '已统一落在「投资成本·交易性·其他」行；'
    + '多分类或多品种时请手工分摊到对应行（可用分摊对话框）。',
}

/** wp_code → seed 声明（`buildGSeedCells` 通用路径；G6 走 `buildG6FvSeedCells`；G8 走 `buildG8FvSeedCells`） */
export const G_SEED_SPECS: Readonly<Record<string, GSeedSpec>> = Object.freeze({
  G1: G1_SEED_SPEC,
  G2: G2_SEED_SPEC,
  G4: G4_SEED_SPEC,
  G10: G10_SEED_SPEC,
  G11: G11_SEED_SPEC,
})
