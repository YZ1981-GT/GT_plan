/**
 * useG9Detail — G9-2「其他非流动金融资产明细表」行模型。
 *
 * spec `g-cycle-single-region-detail-lanes` · C-1（选项 C 根治）
 * 列模型依据：`evidence/task8-template-design-logic.md`（模板编制思路，逐格实测）
 *
 * ═══ 模板编制思路：「三分量 × 四阶段」═══
 *
 * **公允价值 = 成本 + 累计公允价值变动**（CAS 22 公允价值计量模型）。这个三分量恒等式
 * 在模板里重复出现四次（期初余额 / 期初审定数 / 期末余额 / 期末审定数），构成 28 列的骨架：
 *
 * | 阶段 | 成本 | 累计公允价值变动 | 公允价值 |
 * |---|---|---|---|
 * | 期初余额（未审） | C | D | E【=C+D】 |
 * | 期初账项调整 | F | G | —（调整不单列公允价值） |
 * | 期初审定数 | H【=C+F】 | I【=D+G】 | J【=H+I】 |
 * | 期末余额（未审） | P【=C+M】 | Q【=D+N】 | R【=P+Q】 |
 * | 账项调整 | S | T | — |
 * | 期末审定数 | U【=P+S】 | V【=Q+T】 | W【=U+V】 |
 *
 * 🔴 **`P = C+M` / `Q = D+N` 走未审线**（期初未审 + 本期变动），**不是**从审定数推。
 * 审定数含账项调整，若期末从审定推，本期调整会被重复计入。
 *
 * 🔴 **`O`（计入投资收益的股息）是损益项**，不参与任何余额公式 —— 它挂在
 * `M9:O9`「本期变动」分组下，极易被误当成第三个变动分量。
 *
 * ═══ 会计口径：全 FVTPL，因此**没有** OCI、**没有**减值 ═══
 *
 * 编制说明 A38-A43 列出应列入 G9 的五类资产，全部是 FVTPL。CAS 22 下：
 * * FVTPL 的公允价值变动计入**当期损益**，不走其他综合收益 ⇒ 无 OCI 列；
 * * 减值模型只适用于摊余成本与 FVOCI ⇒ 无减值列。
 *
 * ⇒ 改造前前端的 `ociChange` / `ociCumulative` / `impairmentLoss` /
 * `impairmentProvision` 四列**不是缺映射，是会计错误**（见 `DROPPED_LEGACY_FIELDS`）。
 * 🔴 G8 / G6 是 FVOCI 口径，**有** OCI 与减值列，不得照抄本文件的移除清单。
 *
 * ═══ 三个受管区共用一个 store 键 ═══
 *
 * 模板有三个受管数据区（R12-16 / R19-23 / R26-28），区标题行 R11/R18/R25 与小计行
 * R17/R24/R29 不受管。三区的行存在**同一个** `G9-detail-rows` 数组里，区归属由
 * `section` 字段表达（后端引擎 `row_section_field` 按它过滤）。
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { G9_CLASSIFICATION_OPTIONS } from './g9Constants'
import { parseNum, calcSubtotal } from './useG9FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import {
  fetchG9AuxAssetSeeds,
  pushG9DetailGroupTotalsToAdjudication,
  type G9AuxAssetSeed,
} from './g9CrossHelpers'
import { matchG9AssetKey } from './g9VoucherCross'

// ─── 区（模板三个受管区）─────────────────────────────────────────────────────

/** 行的区归属。值与后端 `phase5_g9_02_detail` 的 `row_section_value` 逐字一致。 */
export type G9Section = 'main' | 'mandatory_fvtpl' | 'designated_fvtpl'

export interface G9SectionMeta {
  key: G9Section
  /** 模板区标题行（不受管，整行只有 A 列有分类文本） */
  titleRow: number
  /** 模板区标题文本（逐字） */
  title: string
}

export const G9_SECTIONS: readonly G9SectionMeta[] = [
  { key: 'main', titleRow: 11, title: '其他非流动金融资产' },
  {
    key: 'mandatory_fvtpl',
    titleRow: 18,
    title: '划分为以公允价值计量且其变动计入当期损益的金融资产',
  },
  {
    key: 'designated_fvtpl',
    titleRow: 25,
    title: '指定为以公允价值计量且其变动计入当期损益的金融资产',
  },
] as const

// ─── 行模型 ─────────────────────────────────────────────────────────────────

/**
 * G9-2 明细行 —— 字段顺序与模板列序 A..AB **逐列对应**。
 *
 * 🔴 顺序与命名由后端判据 `test_g9_column_isomorphism.py` 双向锁住
 * （`FIELD_SPECS_G902` 的 json_key 集合与顺序必须与本接口逐字相等）。
 *
 * `【公式】` 标记的字段由 `enrichG9DetailRow` 按模板公式重算，UI 只读。
 */
export interface G9DetailRow {
  /** 行身份（受管 `row_identity_key`）。生成器带随机后缀，见 `genId`。 */
  rowId: string
  /** 显示序号（不受管、不是身份） */
  seq: number
  /** 行的区归属（模板三个区标题行；不是模板的某一列） */
  section: G9Section

  /** A 类别（工具种类：债务工具投资 / 权益工具投资 / 衍生金融资产 / 其他） */
  category: string
  /** B 投资项目【按明细项目列示，如证券名称或被投资单位名称】 */
  investTarget: string

  /** C 期初余额 / 成本 */
  openingCost: number
  /** D 期初余额 / 累计公允价值变动 */
  openingCumulativeFv: number
  /** E 期初余额 / 公允价值　**【公式】** `=C+D` */
  openingFairValue: number

  /** F 期初账项调整 / 成本 */
  openingAdjCost: number
  /** G 期初账项调整 / 公允价值变动 */
  openingAdjFvChange: number

  /** H 期初审定数 / 成本　**【公式】** `=C+F` */
  openingAuditedCost: number
  /** I 期初审定数 / 累计公允价值变动　**【公式】** `=D+G` */
  openingAuditedCumulativeFv: number
  /** J 期初审定数 / 公允价值　**【公式】** `=H+I`（三分量恒等式） */
  openingAuditedFairValue: number

  /** K 期初重分类数 */
  openingReclass: number
  /** L 期初报表数　**【公式】** `=E+K` */
  openingReported: number

  /** M 本期变动 / 成本（借方发生填正数） */
  periodCost: number
  /** N 本期变动 / 本期公允价值变动 */
  periodFvChange: number
  /** O 本期变动 / 计入投资收益的股息 —— 🔴 损益项，**不参与任何余额公式** */
  periodDividendIncome: number

  /** P 期末余额 / 成本　**【公式】** `=C+M`（🔴 未审线） */
  closingCost: number
  /** Q 期末余额 / 累计公允价值变动　**【公式】** `=D+N`（🔴 未审线） */
  closingCumulativeFv: number
  /** R 期末余额 / 公允价值　**【公式】** `=P+Q`（三分量恒等式） */
  closingFairValue: number

  /** S 账项调整 / 成本 */
  closingAdjCost: number
  /** T 账项调整 / 公允价值变动 */
  closingAdjFvChange: number

  /** U 期末审定数 / 成本　**【公式】** `=P+S` */
  closingAuditedCost: number
  /** V 期末审定数 / 累计公允价值变动　**【公式】** `=Q+T` */
  closingAuditedCumulativeFv: number
  /** W 期末审定数 / 公允价值　**【公式】** `=U+V`（三分量恒等式） */
  closingAuditedFairValue: number

  /** X 期末重分类数 */
  closingReclass: number
  /** Y 期末报表数　**【公式】** `=R+X` */
  closingReported: number

  /** Z 期末应收利息 */
  closingInterestReceivable: number
  /** AA 变现是否存在限制 */
  realizationRestricted: string
  /** AB 发函情况 */
  confirmationStatus: string
}

export interface G9DetailRowIssue {
  rowId: string
  investTarget: string
  field: string
  message: string
  variance?: number
}

export const G9_CONFIRMATION_OPTIONS = [
  '已函证已回函',
  '已函证未回函',
  '未函证（替代测试）',
  '不适用',
] as const

/** AA 列「变现是否存在限制」的可选值（模板为自由文本，这里给常用项便于录入） */
export const G9_REALIZATION_RESTRICTED_OPTIONS = ['否', '是（质押）', '是（冻结）', '是（其他）'] as const

// ─── 迁移（真库有 605 B 存量载荷，必须能读进来）───────────────────────────────

/**
 * 改造前存在、**已从受管行模型移除**的字段，逐条给出理由。
 *
 * 🔴 移除是破坏性变更：真库 G9-detail-rows 有 **605 B / 1 wp** 真实载荷。
 * `migrateLegacyG9Row` 对这些字段**显式登记丢弃计数**，不静默吞。
 */
export const DROPPED_LEGACY_FIELDS: readonly { field: string; reason: string }[] = [
  { field: 'impairmentLoss', reason: '🔴 会计错误：FVTPL 不适用减值模型（减值属摊余成本与 FVOCI）' },
  { field: 'impairmentProvision', reason: '🔴 会计错误：同上' },
  { field: 'ociChange', reason: '🔴 会计错误：FVTPL 的公允价值变动计入当期损益，不走 OCI' },
  { field: 'ociCumulative', reason: '🔴 会计错误：同上' },
  { field: 'fairValueLevel', reason: '属 公允价值测试表G9-4' },
  { field: 'valuationMethod', reason: '属 公允价值测试表G9-4' },
  { field: 'instrumentType', reason: '模板用区标题 + A 列「类别」表达' },
  { field: 'isDesignated', reason: '模板用区标题（R25 指定 FVTPL）表达' },
  { field: 'initialInvestDate', reason: '模板 G9-2 无此列（属程序表 G9A / 凭证检查表 G9-6）' },
  { field: 'maturityDate', reason: '模板 G9-2 无此列' },
  { field: 'holdingQuantity', reason: '模板 G9-2 无此列（属 G9-4 公允价值测试）' },
  { field: 'measurementAttribute', reason: '模板 G9-2 无此列' },
  { field: 'isRelatedParty', reason: '模板 G9-2 无此列（属附注披露）' },
] as const

export interface G9MigrationStats {
  /** 识别为旧形态并完成迁移的行数 */
  migratedRows: number
  /** 逐字段丢弃计数（只记真的出现过值的） */
  droppedByField: Record<string, number>
}

export function createG9MigrationStats(): G9MigrationStats {
  return { migratedRows: 0, droppedByField: {} }
}

/** 旧形态判据：出现任一旧独有字段即视为旧行。 */
export function isLegacyG9Row(raw: Record<string, unknown>): boolean {
  if ('assetName' in raw || 'classification' in raw) return true
  return DROPPED_LEGACY_FIELDS.some((d) => d.field in raw)
}

/**
 * 旧行 → 新列模型（映射依据 `evidence/task8-template-design-logic.md` §3.2）。
 *
 * | 旧字段 | 落位 | 依据 |
 * |---|---|---|
 * | `assetName` | B `investTarget` | 同义 |
 * | `classification` | A `category` | 同义 |
 * | `openingBalance` | C `openingCost` | 🔴 旧单值列无三分量拆分信息，落**成本**是唯一不造假的选择 |
 * | `openingAdjustment` | F `openingAdjCost` | 同上 |
 * | `increaseAmount` − `decreaseAmount` | M `periodCost` | 模板 M 列「借方发生填正数」⇒ 净额 |
 * | `fvChangeAmount` | N `periodFvChange` | 语义对应 |
 * | `closingAdjustment` | S `closingAdjCost` | 同 F |
 * | `interestIncome` | Z `closingInterestReceivable` | 字段名是「利息」⇒ 落 Z 更贴近原义；O 列留空由用户补 |
 * | `openingAdjusted` / `closingBalance` / `closingAdjusted` | **丢弃** | 新模型里是公式列（J/R/W），由 C..T 重算 |
 */
export function migrateLegacyG9Row(
  raw: Record<string, unknown>,
  stats?: G9MigrationStats,
): Partial<G9DetailRow> {
  if (stats) {
    stats.migratedRows += 1
    for (const { field } of DROPPED_LEGACY_FIELDS) {
      const v = raw[field]
      if (v === undefined || v === null || v === '' || v === 0 || v === false) continue
      stats.droppedByField[field] = (stats.droppedByField[field] ?? 0) + 1
    }
  }
  const increase = parseNum(raw.increaseAmount)
  const decrease = parseNum(raw.decreaseAmount)
  return {
    category: String(raw.classification ?? raw.category ?? ''),
    investTarget: String(raw.assetName ?? raw.investTarget ?? ''),
    openingCost: parseNum(raw.openingBalance ?? raw.openingCost),
    openingAdjCost: parseNum(raw.openingAdjustment ?? raw.openingAdjCost),
    periodCost: increase || decrease ? increase - decrease : parseNum(raw.periodCost),
    periodFvChange: parseNum(raw.fvChangeAmount ?? raw.periodFvChange),
    closingAdjCost: parseNum(raw.closingAdjustment ?? raw.closingAdjCost),
    closingInterestReceivable: parseNum(
      raw.interestIncome ?? raw.closingInterestReceivable,
    ),
    confirmationStatus: String(raw.confirmationStatus ?? ''),
  }
}

// ─── 公式引擎（12 条模板公式）─────────────────────────────────────────────────

const ITEM_ID_ROWS = 'G9-detail-rows'
const ITEM_ID_ADJ_ROWS = 'G9-adj-rows'
const DIFF_TOLERANCE = 0.01

function genId(): string {
  return `g9d-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

/**
 * 按模板 **12 条公式**重算派生列。
 *
 * `E=C+D` `H=C+F` `I=D+G` `J=H+I` `L=E+K` `P=C+M` `Q=D+N` `R=P+Q`
 * `U=P+S` `V=Q+T` `W=U+V` `Y=R+X`
 *
 * 🔴 `P`/`Q` 走**未审线**；`O` 股息不进任何余额公式。
 */
export function enrichG9DetailRow(
  raw: Partial<G9DetailRow> & { rowId: string },
  seq: number,
): G9DetailRow {
  const openingCost = parseNum(raw.openingCost)
  const openingCumulativeFv = parseNum(raw.openingCumulativeFv)
  const openingFairValue = openingCost + openingCumulativeFv                       // E=C+D

  const openingAdjCost = parseNum(raw.openingAdjCost)
  const openingAdjFvChange = parseNum(raw.openingAdjFvChange)

  const openingAuditedCost = openingCost + openingAdjCost                          // H=C+F
  const openingAuditedCumulativeFv = openingCumulativeFv + openingAdjFvChange      // I=D+G
  const openingAuditedFairValue = openingAuditedCost + openingAuditedCumulativeFv  // J=H+I

  const openingReclass = parseNum(raw.openingReclass)
  const openingReported = openingFairValue + openingReclass                        // L=E+K

  const periodCost = parseNum(raw.periodCost)
  const periodFvChange = parseNum(raw.periodFvChange)
  const periodDividendIncome = parseNum(raw.periodDividendIncome)

  const closingCost = openingCost + periodCost                                     // P=C+M
  const closingCumulativeFv = openingCumulativeFv + periodFvChange                 // Q=D+N
  const closingFairValue = closingCost + closingCumulativeFv                       // R=P+Q

  const closingAdjCost = parseNum(raw.closingAdjCost)
  const closingAdjFvChange = parseNum(raw.closingAdjFvChange)

  const closingAuditedCost = closingCost + closingAdjCost                          // U=P+S
  const closingAuditedCumulativeFv = closingCumulativeFv + closingAdjFvChange      // V=Q+T
  const closingAuditedFairValue = closingAuditedCost + closingAuditedCumulativeFv  // W=U+V

  const closingReclass = parseNum(raw.closingReclass)
  const closingReported = closingFairValue + closingReclass                        // Y=R+X

  return {
    rowId: raw.rowId,
    seq,
    section: raw.section ?? 'main',
    category: raw.category ?? G9_CLASSIFICATION_OPTIONS[0],
    investTarget: raw.investTarget ?? '',
    openingCost,
    openingCumulativeFv,
    openingFairValue,
    openingAdjCost,
    openingAdjFvChange,
    openingAuditedCost,
    openingAuditedCumulativeFv,
    openingAuditedFairValue,
    openingReclass,
    openingReported,
    periodCost,
    periodFvChange,
    periodDividendIncome,
    closingCost,
    closingCumulativeFv,
    closingFairValue,
    closingAdjCost,
    closingAdjFvChange,
    closingAuditedCost,
    closingAuditedCumulativeFv,
    closingAuditedFairValue,
    closingReclass,
    closingReported,
    closingInterestReceivable: parseNum(raw.closingInterestReceivable),
    realizationRestricted: raw.realizationRestricted ?? '否',
    confirmationStatus: raw.confirmationStatus ?? '',
  }
}

/**
 * 解析 store 载荷为行数组，顺带做旧形态迁移。
 *
 * 🔴 返回 `{ list, stats }` 而不是在 computed 里写 ref：后者产生求值顺序依赖
 * （迁移计数时而为 0），本轮判据实测踩到过。
 */
export function parseG9DetailRows(
  json: string | null | undefined,
): { list: G9DetailRow[]; stats: G9MigrationStats } {
  const stats = createG9MigrationStats()
  if (!json) return { list: [], stats }
  let arr: unknown
  try {
    arr = JSON.parse(json)
  } catch {
    return { list: [], stats }
  }
  if (!Array.isArray(arr)) return { list: [], stats }
  const list = arr.map((r, i) => {
    const raw = (r ?? {}) as Record<string, unknown>
    const rowId = String(raw.rowId ?? raw.id ?? '') || `g9d-legacy-${i}`
    const base = isLegacyG9Row(raw) ? migrateLegacyG9Row(raw, stats) : {}
    return enrichG9DetailRow({ ...raw, ...base, rowId } as Partial<G9DetailRow> & { rowId: string }, i + 1)
  })
  return { list, stats }
}

// ─── 完整性校验（四类，全部围绕模板口径）─────────────────────────────────────

/**
 * 四类校验：
 * ① 有审定余额但投资项目为空（B 列）
 * ② 三分量恒等式不成立（E/J/R/W 四处）
 * ③ 未审线不成立（P=C+M / Q=D+N）
 * ④ 有余额但未留函证痕迹（AB 列）
 *
 * 🔴 改造前还有「FVOCI 的 OCI 一致性」「Level3 须填估值方法」「减值不得为负」三类，
 * 已随对应列移除（前两类是会计错误、第三类属 G9-4）。
 */
export function scanG9DetailIntegrity(rows: G9DetailRow[]): G9DetailRowIssue[] {
  const issues: G9DetailRowIssue[] = []
  for (const r of rows) {
    const name = r.investTarget?.trim() || `第${r.seq}行`
    const base = { rowId: r.rowId, investTarget: name }

    if (!r.investTarget?.trim() && Math.abs(r.closingAuditedFairValue) > DIFF_TOLERANCE) {
      issues.push({ ...base, field: 'investTarget', message: '有审定余额但投资项目为空' })
    }

    const identities: Array<[string, number, string]> = [
      ['openingFairValue', r.openingFairValue - (r.openingCost + r.openingCumulativeFv), '期初：成本 + 累计公允价值变动 ≠ 公允价值（E=C+D）'],
      ['openingAuditedFairValue', r.openingAuditedFairValue - (r.openingAuditedCost + r.openingAuditedCumulativeFv), '期初审定：三分量恒等式不成立（J=H+I）'],
      ['closingFairValue', r.closingFairValue - (r.closingCost + r.closingCumulativeFv), '期末：成本 + 累计公允价值变动 ≠ 公允价值（R=P+Q）'],
      ['closingAuditedFairValue', r.closingAuditedFairValue - (r.closingAuditedCost + r.closingAuditedCumulativeFv), '期末审定：三分量恒等式不成立（W=U+V）'],
    ]
    for (const [field, variance, message] of identities) {
      if (Math.abs(variance) > DIFF_TOLERANCE) issues.push({ ...base, field, message, variance })
    }

    const costLine = r.closingCost - (r.openingCost + r.periodCost)
    if (Math.abs(costLine) > DIFF_TOLERANCE) {
      issues.push({ ...base, field: 'closingCost', message: '期末成本应等于「期初未审成本 + 本期成本变动」（P=C+M，未审线）', variance: costLine })
    }
    const fvLine = r.closingCumulativeFv - (r.openingCumulativeFv + r.periodFvChange)
    if (Math.abs(fvLine) > DIFF_TOLERANCE) {
      issues.push({ ...base, field: 'closingCumulativeFv', message: '期末累计公允价值变动应等于「期初未审 + 本期变动」（Q=D+N，未审线）', variance: fvLine })
    }

    if (Math.abs(r.closingAuditedFairValue) > DIFF_TOLERANCE && !r.confirmationStatus?.trim()) {
      issues.push({ ...base, field: 'confirmationStatus', message: '有期末审定余额但未填发函情况' })
    }
  }
  return issues
}

function parseAdjudicationClosingTotal(json: string | null | undefined): number | null {
  if (!json) return null
  try {
    const store = JSON.parse(json)
    if (!store || typeof store !== 'object') return null
    let total = 0
    let seen = false
    for (const v of Object.values(store as Record<string, unknown>)) {
      const row = (v ?? {}) as Record<string, unknown>
      if ('closingAdjusted' in row || 'closingUnadjusted' in row) {
        seen = true
        total += parseNum(row.closingAdjusted ?? row.closingUnadjusted)
      }
    }
    return seen ? total : null
  } catch {
    return null
  }
}

// ─── 辅助核算取数 ───────────────────────────────────────────────────────────

/** 辅助核算种子 → 新列模型的行（期末−期初轧差暂入本期成本变动 M）。 */
export function seedRowFromAux(
  seed: G9AuxAssetSeed,
  seq: number,
  existing?: G9DetailRow,
): G9DetailRow {
  const plug = Math.round((seed.closingBalance - seed.openingBalance) * 100) / 100
  const hasMovement = existing && (existing.periodCost || existing.periodFvChange)
  return enrichG9DetailRow(
    {
      rowId: existing?.rowId ?? genId(),
      section: existing?.section ?? 'main',
      investTarget: seed.assetName,
      category: existing?.category ?? G9_CLASSIFICATION_OPTIONS[0],
      // 🔴 辅助核算只给余额，无三分量拆分信息 ⇒ 落「成本」（同迁移的口径）
      openingCost: seed.openingBalance,
      openingCumulativeFv: existing?.openingCumulativeFv ?? 0,
      periodCost: hasMovement ? existing!.periodCost : plug,
      periodFvChange: existing?.periodFvChange ?? 0,
      closingAdjCost: existing?.closingAdjCost ?? 0,
      confirmationStatus: existing?.confirmationStatus ?? '',
    },
    seq,
  )
}

// ─── Composable ─────────────────────────────────────────────────────────────

export function useG9Detail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  projectId?: Ref<string> | ComputedRef<string>
}) {
  /** 四段视图对应模板两级表头的四个一级分组 + 单列补充区 */
  const activeTab = ref<'opening' | 'movement' | 'closing' | 'supplement'>('opening')
  const activeRowIndex = ref(0)
  const auxLoading = ref(false)

  // 🔴 一个 computed 同时产出 list 与迁移统计（不在 computed 里写 ref —— 那会产生
  //    求值顺序依赖，迁移计数时而为 0，本轮判据实测踩到过）。
  const parsed = computed(() =>
    parseG9DetailRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark),
  )
  const rows = computed(() => parsed.value.list)
  const migrationStats = computed(() => parsed.value.stats)
  const hasLegacyPayload = computed(() => parsed.value.stats.migratedRows > 0)

  const currentRowKey = computed(() => rows.value[activeRowIndex.value]?.rowId ?? '')

  /** 按**区**分组（取代改造前按 `classification` 分组 —— 模板的分区是区标题行） */
  const rowsBySection = computed(() => {
    const map = {} as Record<G9Section, G9DetailRow[]>
    for (const s of G9_SECTIONS) map[s.key] = []
    for (const r of rows.value) (map[r.section] ??= []).push(r)
    return map
  })

  /** 区小计（对应模板小计行 R17/R24/R29）+ 合计（R30 = 三区小计枚举相加） */
  const sectionSubtotals = computed(() => {
    const result: Record<string, number> = {}
    for (const s of G9_SECTIONS) {
      result[s.title] = calcSubtotal(
        rowsBySection.value[s.key].map((r) => r.closingAuditedFairValue),
      )
    }
    result['合计'] = calcSubtotal(rows.value.map((r) => r.closingAuditedFairValue))
    return result
  })

  const totals = computed(() => ({
    openingFairValue: calcSubtotal(rows.value.map((r) => r.openingFairValue)),
    openingAuditedFairValue: calcSubtotal(rows.value.map((r) => r.openingAuditedFairValue)),
    openingReported: calcSubtotal(rows.value.map((r) => r.openingReported)),
    periodCost: calcSubtotal(rows.value.map((r) => r.periodCost)),
    periodFvChange: calcSubtotal(rows.value.map((r) => r.periodFvChange)),
    periodDividendIncome: calcSubtotal(rows.value.map((r) => r.periodDividendIncome)),
    closingFairValue: calcSubtotal(rows.value.map((r) => r.closingFairValue)),
    closingAuditedFairValue: calcSubtotal(rows.value.map((r) => r.closingAuditedFairValue)),
    closingReported: calcSubtotal(rows.value.map((r) => r.closingReported)),
    closingInterestReceivable: calcSubtotal(rows.value.map((r) => r.closingInterestReceivable)),
  }))

  const adjudicationClosingTotal = computed(() =>
    parseAdjudicationClosingTotal(opts.allResponses.value.get(ITEM_ID_ADJ_ROWS)?.remark),
  )
  const adjCrossVariance = computed(() => {
    if (adjudicationClosingTotal.value == null || !rows.value.length) return null
    return totals.value.closingAuditedFairValue - adjudicationClosingTotal.value
  })
  const hasAdjCrossMismatch = computed(() =>
    adjCrossVariance.value != null && Math.abs(adjCrossVariance.value) > DIFF_TOLERANCE,
  )
  const integrityIssues = computed(() => scanG9DetailIntegrity(rows.value))

  function persist(list: G9DetailRow[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
  }

  /**
   * 载入时若发现旧形态载荷，**立即按新模型回写一次**。
   *
   * 不回写则每次载入都要重跑迁移，且跨表消费方读到的仍是旧键。
   */
  function persistMigrationIfNeeded(): number {
    if (opts.isReadonly.value) return 0
    const n = migrationStats.value.migratedRows
    if (n > 0) persist(rows.value)
    return n
  }

  function updateRow(rowId: string, patch: Partial<G9DetailRow>): void {
    if (opts.isReadonly.value) return
    persist(
      rows.value.map((r) =>
        r.rowId === rowId ? enrichG9DetailRow({ ...r, ...patch, rowId }, r.seq) : r,
      ),
    )
  }

  async function addRow(section: G9Section = 'main'): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增明细行', {
        inputPlaceholder: '如：某证券 / 某被投资单位',
      })
      const name = (value ?? '').trim()
      if (!name) return
      persist([
        ...rows.value,
        enrichG9DetailRow(
          { rowId: genId(), section, investTarget: name },
          rows.value.length + 1,
        ),
      ])
    } catch { /* cancelled */ }
  }

  async function removeRow(rowId: string): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      await ElMessageBox.confirm('确认删除该明细行？', '删除确认', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      })
      const list = rows.value
        .filter((r) => r.rowId !== rowId)
        .map((r, i) => enrichG9DetailRow(r, i + 1))
      persist(list)
      if (activeRowIndex.value >= list.length) {
        activeRowIndex.value = Math.max(0, list.length - 1)
      }
    } catch { /* cancelled */ }
  }

  async function seedFromAuxBalance(): Promise<{
    added: number; updated: number; dimType: string; error?: string
  }> {
    if (opts.isReadonly.value) return { added: 0, updated: 0, dimType: '', error: '只读' }
    const projectId = opts.projectId?.value ?? ''
    if (!projectId) return { added: 0, updated: 0, dimType: '', error: '缺少项目 ID' }
    auxLoading.value = true
    try {
      const { seeds, dimType, error } = await fetchG9AuxAssetSeeds(projectId)
      if (error || !seeds.length) {
        return { added: 0, updated: 0, dimType, error: error || '无数据' }
      }
      const byName = new Map(
        rows.value
          .filter((r) => r.investTarget.trim())
          .map((r) => [matchG9AssetKey(r.investTarget), r]),
      )
      let added = 0
      let updated = 0
      const next: G9DetailRow[] = []
      let seq = 1
      for (const seed of seeds) {
        const key = matchG9AssetKey(seed.assetName)
        const prev = byName.get(key)
        if (prev) {
          updated += 1
          next.push(seedRowFromAux(seed, seq++, prev))
          byName.delete(key)
        } else {
          added += 1
          next.push(seedRowFromAux(seed, seq++))
        }
      }
      for (const r of rows.value) {
        if (!byName.has(matchG9AssetKey(r.investTarget))) continue
        next.push(enrichG9DetailRow(r, seq++))
      }
      persist(next)
      return { added, updated, dimType }
    } finally {
      auxLoading.value = false
    }
  }

  /** 按**区**回写 G9-1 未审数（改造前按 `classification` 分组）。 */
  function pushTotalsToAdjudication(): number {
    if (opts.isReadonly.value || !rows.value.length) return 0
    const groups = G9_SECTIONS.map((s) => {
      const filtered = rowsBySection.value[s.key]
      return {
        classification: s.title,
        openingAdjusted: calcSubtotal(filtered.map((r) => r.openingAuditedFairValue)),
        closingBalance: calcSubtotal(filtered.map((r) => r.closingFairValue)),
        closingAdjusted: calcSubtotal(filtered.map((r) => r.closingAuditedFairValue)),
      }
    })
    const n = pushG9DetailGroupTotalsToAdjudication(
      opts.allResponses.value,
      opts.debouncedSave,
      groups,
    )
    if (n > 0) {
      ElMessage.success(`已按区回写 G9-1 ${n} 组未审数`)
    } else {
      ElMessage.warning('无可回写的区合计')
    }
    return n
  }

  return {
    rows,
    activeTab,
    activeRowIndex,
    currentRowKey,
    rowsBySection,
    sectionSubtotals,
    totals,
    migrationStats,
    hasLegacyPayload,
    adjudicationClosingTotal,
    adjCrossVariance,
    hasAdjCrossMismatch,
    integrityIssues,
    auxLoading,
    persistMigrationIfNeeded,
    updateRow,
    addRow,
    removeRow,
    seedFromAuxBalance,
    pushTotalsToAdjudication,
    sections: G9_SECTIONS,
    categoryOptions: G9_CLASSIFICATION_OPTIONS,
    confirmationOptions: G9_CONFIRMATION_OPTIONS,
    realizationRestrictedOptions: G9_REALIZATION_RESTRICTED_OPTIONS,
  }
}
