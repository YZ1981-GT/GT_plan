/**
 * G4 债权投资披露 → `disclosure_notes` 同步载荷
 *
 * 列结构逐字对齐 `note_template_listed.json §五、14` / `note_template_soe.json §八、15`
 * （由 `backend/scripts/fix/fix_note_g_cycle_structure.py` 按权威模板
 * `backend/wp_templates/G/G4 债权投资.xlsx` 重建）。
 *
 * 🔴 本轮只推送**底稿字段真实存在**的表（宁缺勿造）：
 * - 主表（7 列两级：期末/上年年末 × 账面余额·减值准备·账面价值）—— 组件列头与源模板一致
 * - 三阶段减值准备表（上市 6 张 / 国企 3 张，6 列单级）—— 组件 `stageBlocks` 列头一致
 *
 * 其余 6 张模板表（减值准备变动 / 期末重要的债权投资 + 续 / 三阶段迁移 / 核销 ×2）
 * 在底稿里复用了主表的 6 列行模型、没有对应字段 → 见
 * `G4_NOT_SYNCED_TABLES`（每条写明原因），补齐需先给组件加列。
 *
 * 🔴 三阶段表名：国企底稿 `G4StageBlock.title` 带尾部「：」，模板无冒号 →
 *    统一经 `normalizeG4StageTableName` 归一，否则孤儿子表。
 *
 * 🔴 阶段表末列名两版不同、且上市侧**只有「期末第一阶段」是「理由」**，其余「划分依据」
 *    → 直接取底稿 `block.reasonHeader`（组件默认值已与权威模板一致），不写死。
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.1
 */
import type { ColumnDef } from './disclosureColumnDefs'
import { defineColumns } from './disclosureColumnDefs'
import {
  G4_DISCLOSURE_SHEET_NAME,
  G4_MAIN_SUBTABLE,
  G4_NOTE_SECTION,
  isG4DisclosureApplicable,
  normalizeG4StageTableName,
  resolveG4CurrentStandard,
  type G4DisclosureVariant,
} from './g4NoteSectionMap'
import { isPlaceholderStageDetail } from './g4ListedStageDisclosure'

const AMOUNT = 'amount' as const
const PERCENT = 'percent' as const

export const G4_TOTAL_LABEL = '合计'
export const G4_SUBTOTAL_LABEL = '小计'
export const G4_INDIVIDUAL_LABEL = '按单项计提减值准备'
export const G4_PORTFOLIO_LABEL = '按组合计提减值准备'

/** 主表列：期末 / 上年年末（国企：期末数 / 期初数）各含账面余额·减值准备·账面价值 */
export function g4MainColumnsFor(variant: G4DisclosureVariant): ColumnDef[] {
  const endGroup = variant === 'listed' ? '期末余额' : '期末数'
  const priorGroup = variant === 'listed' ? '上年年末余额' : '期初数'
  return defineColumns([
    { key: 'label', label: '项目', is_label: true },
    { key: 'end_gross', label: '账面余额', group: endGroup, format: AMOUNT, align: 'right' },
    { key: 'end_provision', label: '减值准备', group: endGroup, format: AMOUNT, align: 'right' },
    { key: 'end_net', label: '账面价值', group: endGroup, format: AMOUNT, align: 'right' },
    { key: 'prior_gross', label: '账面余额', group: priorGroup, format: AMOUNT, align: 'right' },
    { key: 'prior_provision', label: '减值准备', group: priorGroup, format: AMOUNT, align: 'right' },
    { key: 'prior_net', label: '账面价值', group: priorGroup, format: AMOUNT, align: 'right' },
  ])
}

/** 阶段表列（单级表头）：类别 / 账面余额 / 预期信用损失率 / 减值准备 / 账面价值 / 理由或划分依据 */
export function g4StageColumnsFor(rateLabel: string, reasonHeader: string): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '类别', is_label: true, flat: true },
    { key: 'gross', label: '账面余额', format: AMOUNT, align: 'right' },
    { key: 'loss_rate', label: rateLabel, format: PERCENT, align: 'right' },
    { key: 'provision', label: '减值准备', format: AMOUNT, align: 'right' },
    { key: 'net', label: '账面价值', format: AMOUNT, align: 'right' },
    { key: 'reason', label: reasonHeader },
  ])
}

// ─────────────────────────── 输入形状（结构化子集，避免耦合组件内部类型） ───────────────────────────

export interface G4MainRowLike {
  item?: string
  endingBalance?: number
  endingImpairment?: number
  endingBookValue?: number
  priorBalance?: number
  priorImpairment?: number
  priorBookValue?: number
  isFormula?: boolean
}

export interface G4StageDetailLike {
  name?: string
  bookBalance?: number
  impairment?: number
  reason?: string
}

export interface G4StageBlockLike {
  title?: string
  rateLabel?: string
  reasonHeader?: string
  individual?: { details?: readonly G4StageDetailLike[] }
  portfolio?: { details?: readonly G4StageDetailLike[] }
}

export interface G4Snapshot {
  /** 主表行（组件 `sections['bond-overview'].rows`） */
  mainRows: readonly G4MainRowLike[]
  /** 三阶段块（组件 `stageBlocks`） */
  stageBlocks: readonly G4StageBlockLike[]
  /** 三阶段说明（组件 `stageNoteText`） */
  stageNote: string
  /** 各 section 文本域（section.id → textContent） */
  sectionTexts?: Readonly<Record<string, string>>
}

export interface G4SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function txt(v: unknown): string {
  return String(v ?? '').trim()
}

/** 比率：分母 0 → null（不写 0，避免「0% 损失率」误读） */
function ratio(part: number, whole: number): number | null {
  if (!Number.isFinite(whole) || Math.abs(whole) < 1e-9) return null
  return Number(((part / whole) * 100).toFixed(4))
}

/**
 * 小计 / 合计 / 「减：…」行的 row_type 判定（按标签，与源模板行序一致）。
 *
 * 🔴 必须先去掉标签内空白：源模板写的是「小 计」「合 计」（中间有空格），
 * 直接 `startsWith('小计')` 会漏判 → 小计 / 合计行被当普通数据行推给附注，
 * 丢掉加粗与合计语义（附注侧也无法据 `is_total` 做勾稽）。
 */
function mainRowType(label: string): { row_type: string; is_total?: true } {
  const compact = String(label ?? '').replace(/\s+/g, '')
  if (compact.startsWith(G4_SUBTOTAL_LABEL)) return { row_type: 'subtotal', is_total: true }
  if (compact.startsWith(G4_TOTAL_LABEL)) return { row_type: 'total', is_total: true }
  return { row_type: 'data' }
}

export function buildG4MainRows(
  rows: readonly G4MainRowLike[],
): Record<string, unknown>[] {
  return rows.map((r) => {
    const label = txt(r.item)
    const endGross = num(r.endingBalance)
    const endProv = num(r.endingImpairment)
    const priorGross = num(r.priorBalance)
    const priorProv = num(r.priorImpairment)
    return {
      label,
      end_gross: endGross,
      end_provision: endProv,
      // 账面价值优先取底稿派生值（组件已有公式列），缺失时按 余额−减值 兜底
      end_net: r.endingBookValue != null ? num(r.endingBookValue) : Number((endGross - endProv).toFixed(2)),
      prior_gross: priorGross,
      prior_provision: priorProv,
      prior_net: r.priorBookValue != null ? num(r.priorBookValue) : Number((priorGross - priorProv).toFixed(2)),
      ...mainRowType(label),
    }
  })
}

function stageDetailRow(d: G4StageDetailLike): Record<string, unknown> {
  const gross = num(d.bookBalance)
  const provision = num(d.impairment)
  return {
    label: txt(d.name),
    gross,
    loss_rate: ratio(provision, gross),
    provision,
    net: Number((gross - provision).toFixed(2)),
    reason: txt(d.reason),
    row_type: 'data',
  }
}

function sumDetails(details: readonly G4StageDetailLike[]): { gross: number; provision: number } {
  return details.reduce(
    (acc, d) => ({
      gross: acc.gross + num(d.bookBalance),
      provision: acc.provision + num(d.impairment),
    }),
    { gross: 0, provision: 0 },
  )
}

/** 源模板的「其中：」结构标签行（父行与明细之间），空值列用 null 保持列键齐备 */
export const G4_WHICH_LABEL = '其中：'

function whichRow(): Record<string, unknown> {
  return {
    label: G4_WHICH_LABEL,
    gross: null,
    loss_rate: null,
    provision: null,
    net: null,
    reason: '',
    row_type: 'data',
  }
}

function methodGroupRows(
  label: string,
  details: readonly G4StageDetailLike[],
): Record<string, unknown>[] {
  const { gross, provision } = sumDetails(details)
  return [
    {
      label,
      gross,
      loss_rate: ratio(provision, gross),
      provision,
      net: Number((gross - provision).toFixed(2)),
      reason: '',
      row_type: 'data',
    },
    // 🔴 源模板行序是「按单项/按组合 → 其中： → 逐项明细」，这行结构标签不能丢：
    //    附注是交付物，缺了它读者看不出下面的明细是上一行的拆分。
    whichRow(),
    // 空白骨架行不推（否则附注多出一行全零、名字还叫「其中：」的幽灵数据行）
    ...details.filter((d) => !isPlaceholderStageDetail(d)).map(stageDetailRow),
  ]
}

/**
 * 单张阶段表的行：按单项（含其中明细）→ 按组合（含其中明细）→ 合计。
 * 与源模板行序一致；「其中：」下的明细行数随底稿动态扩展。
 */
export function buildG4StageRows(block: G4StageBlockLike): Record<string, unknown>[] {
  const ind = block.individual?.details ?? []
  const pf = block.portfolio?.details ?? []
  const a = sumDetails(ind)
  const b = sumDetails(pf)
  const gross = a.gross + b.gross
  const provision = a.provision + b.provision
  return [
    ...methodGroupRows(G4_INDIVIDUAL_LABEL, ind),
    ...methodGroupRows(G4_PORTFOLIO_LABEL, pf),
    {
      label: G4_TOTAL_LABEL,
      gross,
      loss_rate: ratio(provision, gross),
      provision,
      net: Number((gross - provision).toFixed(2)),
      reason: '',
      is_total: true,
      row_type: 'total',
    },
  ]
}

/** 阶段表名清单（已归一，顺序 = 底稿块顺序；空标题跳过） */
export function g4StageTableNames(blocks: readonly G4StageBlockLike[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const b of blocks) {
    const name = normalizeG4StageTableName(String(b.title ?? ''))
    if (!name || seen.has(name)) continue
    seen.add(name)
    out.push(name)
  }
  return out
}

export function g4ColumnsFor(
  variant: G4DisclosureVariant,
  blocks: readonly G4StageBlockLike[],
): Record<string, ColumnDef[]> {
  const out: Record<string, ColumnDef[]> = {
    [G4_MAIN_SUBTABLE[variant]]: g4MainColumnsFor(variant),
  }
  for (const b of blocks) {
    const name = normalizeG4StageTableName(String(b.title ?? ''))
    if (!name || out[name]) continue
    out[name] = g4StageColumnsFor(txt(b.rateLabel), txt(b.reasonHeader))
  }
  return out
}

export function buildG4SubTableData(
  variant: G4DisclosureVariant,
  snap: G4Snapshot,
): Record<string, unknown> {
  const out: Record<string, unknown> = {
    [G4_MAIN_SUBTABLE[variant]]: buildG4MainRows(snap.mainRows),
  }
  for (const b of snap.stageBlocks) {
    const name = normalizeG4StageTableName(String(b.title ?? ''))
    if (!name || out[name]) continue
    out[name] = buildG4StageRows(b)
  }
  const texts: Array<Record<string, string>> = []
  const note = txt(snap.stageNote)
  if (note) texts.push({ section: `${variant}-stage-note`, text: note })
  for (const [id, content] of Object.entries(snap.sectionTexts ?? {})) {
    const t = txt(content)
    if (t) texts.push({ section: `${variant}-${id}`, text: t })
  }
  if (texts.length) out._note_texts = texts
  return out
}

/** @returns null=该变体不适用 / 缺 wpId */
export function buildG4SyncPayload(
  wpId: string,
  variant: G4DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
  snap: G4Snapshot,
): G4SyncFromWorkpaperPayload | null {
  if (!wpId || !isG4DisclosureApplicable(variant, applicableStandards)) return null
  return {
    wp_id: wpId,
    sheet_name: G4_DISCLOSURE_SHEET_NAME[variant],
    section_id: G4_NOTE_SECTION[variant],
    current_standard: resolveG4CurrentStandard(variant, applicableStandards),
    sub_table_data: buildG4SubTableData(variant, snap),
    columns: g4ColumnsFor(variant, snap.stageBlocks),
  }
}

export const buildG4ListedColumns = (
  blocks: readonly G4StageBlockLike[] = [],
): Record<string, ColumnDef[]> => g4ColumnsFor('listed', blocks)

export const buildG4SoeColumns = (
  blocks: readonly G4StageBlockLike[] = [],
): Record<string, ColumnDef[]> => g4ColumnsFor('soe', blocks)
