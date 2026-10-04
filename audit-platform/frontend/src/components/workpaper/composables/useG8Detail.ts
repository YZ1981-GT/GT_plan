/**
 * useG8Detail — G8-2「其他权益工具投资明细表」权威模板列模型（23 列 A..W）
 *
 * spec `g-cycle-single-region-detail-lanes` Task 9b / C-8（选项 C 根治：改前端对齐模板）
 * 列模型依据 `evidence/task8-c6-remaining-eight-template-logic.md` §3 + 本轮 openpyxl 逐格实测
 *
 * ═══ 🔴 G8 是 FVOCI —— OCI 列是准则要求，**绝不可照抄 G9/G10 的「删 OCI」** ═══
 *
 * 受管表内注释逐字：「在初始确认时，企业可以将非交易性权益工具投资**指定为以公允价值计量
 * 且其变动计入其他综合收益**的金融资产。该指定一经作出，**不得撤销**。」
 * ⇒ 模板的三个 OCI 列（F 期初累计 / L 本期转留存 / R 期末累计）是 CAS22 要求的。
 * G9/G10 删 OCI 的依据是「那两张表全 FVTPL」，对 G8 **反向**成立。同理 G6（其他债权投资）
 * 也是 FVOCI 口径。
 *
 * ═══ 列模型：三分量 + OCI 旁列 × 四阶段 ═══
 *
 * ```
 * A 被投资单位名称   B 投资比例
 * C9:F9  期初余额 : C 成本 · D 累计公允价值变动 · E 合计【=SUM(C:D)】
 *                   F 计入其他综合收益的累计利得或损失
 *        G 期初调整数 · H 期初审定数【=E+G】
 * I9:N9  本期变动 : I 成本 · J 本期公允价值变动 · K 处置时公允价值变动结转
 *                   L 其他综合收益转入留存收益 · M 合计【=I+J+K+L】
 *                   N 本期确认的股利收入
 * O9:R9  期末余额 : O 成本【=C+I】 · P 累计公允价值变动【=D+J+K】 · Q 合计【=O+P】
 *                   R 计入其他综合收益的累计利得或损失【=F+J+L】
 *        S 调整数 · T 审定数【=Q+S】
 * U 指定为FVOCI的原因   V 其他综合收益转入留存收益的原因   W 发函情况
 * ```
 *
 * `N 本期确认的股利收入`是**损益项**（与 G9 的 O 列股息同理）：不进任何余额公式。
 *
 * ═══ 🔴 模板自身有四处行级缺陷 —— 本模块按**会计正确**口径算，不模仿模板的不一致 ═══
 *
 * 逐行实测（`明细表G8-2` R11-R20）：
 *
 * | 行 | M 本期变动合计 | P 期末累计FV变动 | R 期末OCI累计 | T 审定数 |
 * |---|---|---|---|---|
 * | R11 | `=SUM(I:L)` ✅含 L | `=D+J` ❌漏 K | ✅ `=F+J+L` | ✅ `=Q+S` |
 * | R12 | `=SUM(I:K)` ❌漏 L | `=D+J+K` ✅含 K | ✅ `=F+J+L` | ❌**无公式** |
 * | R13..R20 | `=SUM(I:K)` ❌漏 L | `=D+J` ❌漏 K | ❌**无公式** | ✅ `=Q+S` |
 *
 * 即 R11 与 R12 各对一半、R13-R20 两处都漏，且 R12 缺 T、R13-R20 缺 R。
 * 会计判读（C-6 §3.3）：M 应含 L · P 应含 K · R 与 T 每行都该有。
 *
 * ⇒ **本模块按会计正确口径算全部四列**（`M=I+J+K+L` / `P=D+J+K` / `R=F+J+L` / `T=Q+S`）。
 * 后端三段 sheet spec 则按**模板实测**声明 `mode`（`g802-r11` / `g802-r12` / `g802-r13plus`），
 * 因此在缺陷行上前端算得出值、模板格却是空的或口径不同 —— 这个差异是**如实登记的欠账**
 * （见 spec evidence `task9b-c8-g8-rootfix.md` §2.3），不是本模块的 bug：
 * 修模板要么改字节（`backend/wp_templates/` 运行时只读 + sha 冻结，禁止）、
 * 要么走覆盖层（框架层尚无该机制）+ 会计专业复核，两者都不在本 lane 范围。
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcAdjustedAmount,
  calcSubtotal,
} from './useG8FormulaEngine'
import {
  fetchG8AuxInvesteeSeeds,
  matchG8InvesteeKey,
  pushG8DetailTotalsToAdjudication,
  type G8AuxInvesteeSeed,
} from './g8CrossHelpers'
import type { ChecklistResponse } from './useF1FormData'

/**
 * G8-2 受管行（23 字段，与模板列序 A..W **逐列对应**）。
 *
 * `【公式】` 标记的字段由 `enrichG8DetailRow` 重算，UI 只读。
 * `rowId`/`seq` 不受管（身份 / 显示序号，不占模板任何一列）。
 */
export interface G8DetailRow {
  /** 行身份（受管 `row_identity_key`）。生成器带随机后缀，见 `genId`。 */
  rowId: string
  /** 显示序号（不受管、不是身份） */
  seq: number

  /** A 被投资单位名称 */
  investeeName: string
  /** B 投资比例（小数，如 0.15 = 15%） */
  investmentRatio: number

  /** C 期初余额 / 成本 */
  openingCost: number
  /** D 期初余额 / 累计公允价值变动 */
  openingFvAccum: number
  /** E 期初余额 / 合计　**【公式】** `=SUM(C:D)` */
  openingTotal: number
  /** F 期初余额 / 计入其他综合收益的累计利得或损失 */
  openingOciCumulative: number
  /** G 期初调整数 */
  openingAdjustment: number
  /** H 期初审定数　**【公式】** `=E+G` */
  openingAdjusted: number

  /** I 本期变动 / 成本 —— **净额列**（模板无「本期减少」） */
  movementCost: number
  /** J 本期变动 / 本期公允价值变动 —— FVOCI 下**这一列就是本期 OCI** */
  movementFvChange: number
  /** K 本期变动 / 处置时公允价值变动结转 */
  disposalFvTransfer: number
  /** L 本期变动 / 其他综合收益转入留存收益 */
  ociToRetainedEarnings: number
  /** M 本期变动 / 合计　**【公式】** `=I+J+K+L`（🔴 模板仅 R11 含 L，其余漏） */
  movementTotal: number
  /** N 本期确认的股利收入 —— **损益项**，不进任何余额公式 */
  dividendIncome: number

  /** O 期末余额 / 成本　**【公式】** `=C+I` */
  closingCost: number
  /** P 期末余额 / 累计公允价值变动　**【公式】** `=D+J+K`（🔴 模板仅 R12 含 K） */
  closingFvAccum: number
  /** Q 期末余额 / 合计　**【公式】** `=O+P` */
  closingTotal: number
  /** R 期末余额 / 计入其他综合收益的累计利得或损失　**【公式】** `=F+J+L`（🔴 模板 R13-20 无） */
  closingOciCumulative: number
  /** S 调整数 */
  closingAdjustment: number
  /** T 审定数　**【公式】** `=Q+S`（🔴 模板 R12 无） */
  closingAdjusted: number

  /** U 指定为以公允价值计量且其变动计入其他综合收益的原因 */
  designationReason: string
  /** V 其他综合收益转入留存收益的原因 */
  transferReason: string
  /** W 发函情况 */
  confirmationStatus: string
}

/**
 * 改造前存在、**已从受管行模型移除**的字段（C-8）。
 *
 * 逐条给出归属而不是笼统「模板没有」—— 指不出归属的才是真冗余。
 */
export const DROPPED_LEGACY_G8_FIELDS: readonly { field: string; reason: string }[] = [
  { field: 'fairValueLevel', reason: '权威源是 公允价值测试表G8-4' },
  { field: 'valuationMethod', reason: '权威源同上（G8-4）' },
  { field: 'shareCount', reason: '权威源同上（G8-4 的持股数×单价明细）' },
  { field: 'pricePerShare', reason: '权威源同上（G8-4）' },
  { field: 'fairValueTotal', reason: '权威源同上（G8-4）；期末公允价值在本表是 Q 列（=O+P）' },
  { field: 'decreaseAmount', reason: '模板 I 是**净额**单列，拆增减会与 I 双源' },
  {
    field: 'ociCurrentChange',
    reason: 'FVOCI 下「本期 OCI」就是模板 J 列「本期公允价值变动」—— 两字段双源，'
      + '改造前还专门写了一条校验提醒它们应相等，那正是双源的证据',
  },
  { field: 'remark', reason: '模板无此列' },
] as const

/**
 * `enrichG8DetailRow` 的入参：受管列的 `Partial` + **显式列出**的 legacy 键。
 *
 * 只放真实存在过的 legacy 键，读完即弃、不回写（不用 `Record<string, unknown>` 兜底 ——
 * 那会让拼错的字段名也能通过编译，G10 那一轮实测过）。
 */
export type G8DetailRowInput = Partial<G8DetailRow> & {
  rowId: string
  /** legacy：单值期初，拆成 C/D/E 三分量 */
  openingBalance?: number | string | null
  /** legacy：单值期末，拆成 O/P/Q 三分量 */
  closingBalance?: number | string | null
  /** legacy：与模板 I（净额）合并 */
  increaseAmount?: number | string | null
  /** legacy：与模板 I（净额）合并，取负 */
  decreaseAmount?: number | string | null
  /** legacy：改名为 movementFvChange（模板 J） */
  fvChangeAmount?: number | string | null
  /** legacy：改名为 openingOciCumulative（模板 F） */
  ociOpeningCumulative?: number | string | null
  /** legacy：改名为 closingOciCumulative（模板 R） */
  ociCumulativeChange?: number | string | null
  /** legacy：与模板 J 双源，读取时不采用 */
  ociCurrentChange?: number | string | null
}

/** 行级完整性/勾稽提示 */
export interface G8DetailRowIssue {
  rowId: string
  investeeName: string
  field: string
  message: string
  variance?: number
}

export const G8_CONFIRMATION_STATUS_OPTIONS = [
  '已发函已回函',
  '已发函未回函',
  '未发函',
  '不适用',
] as const

const ITEM_ID_ROWS = 'G8-detail-rows'
const DIFF_TOLERANCE = 0.01

function genId(): string {
  return `g8d-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

/** 有值判定：`null`/`undefined`/空串都算「没填」（0 是有值）。 */
function hasValue(v: unknown): boolean {
  return v != null && String(v).trim() !== ''
}

/**
 * 按模板 8 条公式重算派生列。
 *
 * | 列 | 公式 | 说明 |
 * |---|---|---|
 * | E | `=SUM(C:D)` | 期初合计 |
 * | H | `=E+G` | 期初审定数 |
 * | M | `=I+J+K+L` | 本期变动合计（🔴 含 L，模板仅 R11 如此） |
 * | O | `=C+I` | 期末成本 |
 * | P | `=D+J+K` | 期末累计公允价值变动（🔴 含 K，模板仅 R12 如此） |
 * | Q | `=O+P` | 期末合计 |
 * | R | `=F+J+L` | 期末 OCI 累计（🔴 模板 R13-20 无该公式） |
 * | T | `=Q+S` | 期末审定数（🔴 模板 R12 无该公式） |
 *
 * 🔴 **兼容读**（旧载荷 → 模板列）：
 * * `openingBalance` 单值 → 落 E；若未单独给 D，则 `D = openingBalance − C`（反推分量）
 * * `closingBalance` 单值 → 仅用于反推 P（`P = closingBalance − O`），**不**直接落 Q ——
 *   Q 由 `=O+P` 重算，因为 O 是 `=C+I` 的硬公式，直接落 Q 会与它双源
 * * `increaseAmount − decreaseAmount` → 落 I（模板 I 是净额）
 * * `fvChangeAmount` → 落 J；`ociCurrentChange` **不采用**（与 J 双源）
 * * `ociOpeningCumulative` → 落 F；`ociCumulativeChange` 仅在 F/J/L 全空时用于反推 F
 */
export function enrichG8DetailRow(raw: G8DetailRowInput, seq: number): G8DetailRow {
  // ── 期初三分量（C / D / E）────────────────────────────────────────────
  const openingCost = parseNum(raw.openingCost)
  const legacyOpeningTotal = parseNum(raw.openingBalance)
  let openingFvAccum: number
  if (hasValue(raw.openingFvAccum)) {
    openingFvAccum = parseNum(raw.openingFvAccum)
  } else if (hasValue(raw.openingBalance)) {
    openingFvAccum = legacyOpeningTotal - openingCost
  } else {
    openingFvAccum = 0
  }
  const openingTotal = openingCost + openingFvAccum

  // ── 期初 OCI（F）与调整/审定（G / H）──────────────────────────────────
  let openingOciCumulative = parseNum(raw.openingOciCumulative ?? raw.ociOpeningCumulative)
  const openingAdjustment = parseNum(raw.openingAdjustment)
  const openingAdjusted = calcAdjustedAmount(openingTotal, openingAdjustment)

  // ── 本期变动（I / J / K / L / M）+ 股利（N）──────────────────────────
  let movementCost: number
  if (hasValue(raw.movementCost)) {
    movementCost = parseNum(raw.movementCost)
  } else {
    // legacy：模板 I 是净额 ⇒ 增减合并
    movementCost = parseNum(raw.increaseAmount) - parseNum(raw.decreaseAmount)
  }
  const movementFvChange = parseNum(raw.movementFvChange ?? raw.fvChangeAmount)
  const disposalFvTransfer = parseNum(raw.disposalFvTransfer)
  const ociToRetainedEarnings = parseNum(raw.ociToRetainedEarnings)
  // M = I+J+K+L（🔴 含 L）
  const movementTotal = movementCost + movementFvChange + disposalFvTransfer + ociToRetainedEarnings
  const dividendIncome = parseNum(raw.dividendIncome)

  // ── 期末三分量（O / P / Q）────────────────────────────────────────────
  // O = C+I
  const closingCost = openingCost + movementCost
  // P = D+J+K（🔴 含 K）
  let closingFvAccum = openingFvAccum + movementFvChange + disposalFvTransfer
  if (!hasValue(raw.openingFvAccum) && !hasValue(raw.openingBalance) && hasValue(raw.closingBalance)) {
    // 只有 legacy 期末单值可依据时，反推分量（期初侧无任何依据的情形）
    closingFvAccum = parseNum(raw.closingBalance) - closingCost
  }
  // Q = O+P
  const closingTotal = closingCost + closingFvAccum

  // ── 期末 OCI（R）：=F+J+L ────────────────────────────────────────────
  if (
    !hasValue(raw.openingOciCumulative)
    && !hasValue(raw.ociOpeningCumulative)
    && hasValue(raw.ociCumulativeChange)
    && !hasValue(raw.movementFvChange)
    && !hasValue(raw.fvChangeAmount)
    && !hasValue(raw.ociToRetainedEarnings)
  ) {
    // 旧载荷只有「期末累计」而无任何分量 ⇒ 反推期初累计，保住 R 的值
    openingOciCumulative = parseNum(raw.ociCumulativeChange)
  }
  const closingOciCumulative = openingOciCumulative + movementFvChange + ociToRetainedEarnings

  // ── 期末调整/审定（S / T）────────────────────────────────────────────
  const closingAdjustment = parseNum(raw.closingAdjustment)
  const closingAdjusted = calcAdjustedAmount(closingTotal, closingAdjustment)

  return {
    rowId: raw.rowId,
    seq,
    investeeName: String(raw.investeeName ?? ''),
    investmentRatio: parseNum(raw.investmentRatio),
    openingCost,
    openingFvAccum,
    openingTotal,
    openingOciCumulative,
    openingAdjustment,
    openingAdjusted,
    movementCost,
    movementFvChange,
    disposalFvTransfer,
    ociToRetainedEarnings,
    movementTotal,
    dividendIncome,
    closingCost,
    closingFvAccum,
    closingTotal,
    closingOciCumulative,
    closingAdjustment,
    closingAdjusted,
    designationReason: String(raw.designationReason ?? ''),
    transferReason: String(raw.transferReason ?? ''),
    confirmationStatus: String(raw.confirmationStatus ?? ''),
  }
}

/**
 * 辅助核算种子 → 明细行。
 *
 * 🔴 期末−期初的轧差落 **J 本期公允价值变动**（不是 I 成本）：辅助核算只给余额，
 * 无法区分「新增投资」与「公允价值变动」。落 J 的理由是 FVOCI 下余额变动**多数**来自
 * 公允价值重估；备注栏模板没有 ⇒ 提示改由 `scanG8DetailIntegrity` 的「轧差待拆分」
 * 校验承担（原实现把提示写进已删除的 `remark` 列）。
 */
export function seedRowFromAux(
  seed: G8AuxInvesteeSeed,
  seq: number,
  existing?: G8DetailRow,
): G8DetailRow {
  const plug = Math.round((seed.closingBalance - seed.openingBalance) * 100) / 100
  const touched = existing
    && (existing.movementCost || existing.movementFvChange || existing.disposalFvTransfer)
  return enrichG8DetailRow(
    {
      rowId: existing?.rowId ?? genId(),
      investeeName: seed.investeeName,
      // 辅助核算只给余额 ⇒ 期初全额落成本分量，公允价值变动分量置 0
      openingCost: seed.openingBalance,
      openingFvAccum: 0,
      openingOciCumulative: existing?.openingOciCumulative ?? 0,
      openingAdjustment: existing?.openingAdjustment ?? 0,
      movementCost: existing?.movementCost ?? 0,
      movementFvChange: touched ? existing!.movementFvChange : plug,
      disposalFvTransfer: existing?.disposalFvTransfer ?? 0,
      ociToRetainedEarnings: existing?.ociToRetainedEarnings ?? 0,
      dividendIncome: existing?.dividendIncome ?? 0,
      closingAdjustment: existing?.closingAdjustment ?? 0,
      investmentRatio: existing?.investmentRatio ?? 0,
      designationReason: existing?.designationReason ?? '',
      transferReason: existing?.transferReason ?? '',
      confirmationStatus: existing?.confirmationStatus ?? '',
    },
    seq,
  )
}

/**
 * 扫描明细行完整性。
 *
 * 🔴 C-8 变更：删掉三类「靠已移除列」的校验（Level3 须填估值方法 / 公允价值合计 ≠
 * 数量×单价 / 公允价值合计与期末审定数不一致）—— 那三列的权威源是 `公允价值测试表G8-4`，
 * 校验也随之归 `useG8FairValueTest`。删掉一类「双源提醒」（本期 OCI 变动与 FV 变动不一致）
 * —— 两者已合并成模板 J 一列，不可能不一致。
 *
 * 新增两类按模板口径的分量校验（与 G9/G10 同族）。
 */
export function scanG8DetailIntegrity(rows: G8DetailRow[]): G8DetailRowIssue[] {
  const issues: G8DetailRowIssue[] = []
  for (const r of rows) {
    const name = r.investeeName?.trim() || `第${r.seq}行`
    const push = (field: string, message: string, variance?: number): void => {
      issues.push({ rowId: r.rowId, investeeName: name, field, message, variance })
    }

    if (Math.abs(r.closingAdjusted) > DIFF_TOLERANCE && !r.designationReason?.trim()) {
      push('designationReason', '有期末审定余额但未填指定 OCI 原因')
    }
    if (Math.abs(r.ociToRetainedEarnings) > DIFF_TOLERANCE && !r.transferReason?.trim()) {
      push('transferReason', 'OCI 转入留存收益已填金额但未说明转入原因')
    }
    if (!r.investeeName?.trim() && Math.abs(r.closingAdjusted) > DIFF_TOLERANCE) {
      push('investeeName', '有审定余额但被投资单位名称为空')
    }

    // 期初分量恒等式 E = C+D
    const openDiff = r.openingTotal - (r.openingCost + r.openingFvAccum)
    if (Math.abs(openDiff) > DIFF_TOLERANCE) {
      push('openingTotal', '期初 成本+累计公允价值变动 ≠ 合计（E=SUM(C:D)）', openDiff)
    }
    // 期末成本走未审线 O = C+I
    const costDiff = r.closingCost - (r.openingCost + r.movementCost)
    if (Math.abs(costDiff) > DIFF_TOLERANCE) {
      push('closingCost', '期末成本应等于「期初成本 + 本期成本变动」（O=C+I）', costDiff)
    }
    // 期末累计公允价值变动 P = D+J+K（🔴 含处置结转 K）
    const fvDiff = r.closingFvAccum
      - (r.openingFvAccum + r.movementFvChange + r.disposalFvTransfer)
    if (Math.abs(fvDiff) > DIFF_TOLERANCE) {
      push(
        'closingFvAccum',
        '期末累计公允价值变动应等于「期初累计 + 本期变动 + 处置时结转」（P=D+J+K）',
        fvDiff,
      )
    }
    // 期末分量恒等式 Q = O+P
    const closeDiff = r.closingTotal - (r.closingCost + r.closingFvAccum)
    if (Math.abs(closeDiff) > DIFF_TOLERANCE) {
      push('closingTotal', '期末 成本+累计公允价值变动 ≠ 合计（Q=O+P）', closeDiff)
    }
    // OCI 滚动 R = F+J+L
    const ociExpected = r.openingOciCumulative + r.movementFvChange + r.ociToRetainedEarnings
    const hasOci = (
      Math.abs(r.openingOciCumulative) > DIFF_TOLERANCE
      || Math.abs(r.movementFvChange) > DIFF_TOLERANCE
      || Math.abs(r.ociToRetainedEarnings) > DIFF_TOLERANCE
      || Math.abs(r.closingOciCumulative) > DIFF_TOLERANCE
    )
    if (hasOci && Math.abs(r.closingOciCumulative - ociExpected) > DIFF_TOLERANCE) {
      push(
        'closingOciCumulative',
        '期末 OCI 累计应等于「期初累计 + 本期公允价值变动 + 转入留存收益」（R=F+J+L）',
        r.closingOciCumulative - ociExpected,
      )
    }
    // 本期变动合计 M = I+J+K+L（🔴 含 L）
    const mvDiff = r.movementTotal
      - (r.movementCost + r.movementFvChange + r.disposalFvTransfer + r.ociToRetainedEarnings)
    if (Math.abs(mvDiff) > DIFF_TOLERANCE) {
      push('movementTotal', '本期变动合计应含「OCI 转入留存收益」（M=I+J+K+L）', mvDiff)
    }
  }
  return issues
}

function parseRows(json: string | null | undefined): G8DetailRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) =>
      enrichG8DetailRow({ ...r, rowId: r.rowId || r.id || genId() }, i + 1),
    )
  } catch {
    return []
  }
}

function parseAdjudicationClosingTotal(json: string | null | undefined): number | null {
  if (!json) return null
  try {
    const store = JSON.parse(json)
    if (!store || typeof store !== 'object' || Array.isArray(store)) return null
    let sum = 0
    let any = false
    for (const v of Object.values(store as Record<string, any>)) {
      if (!v || typeof v !== 'object') continue
      any = true
      sum += calcAdjustedAmount(parseNum(v.closingUnadjusted), parseNum(v.closingAdjustment))
    }
    return any ? sum : null
  } catch {
    return null
  }
}

export function useG8Detail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  projectId?: Ref<string> | ComputedRef<string>
}) {
  /**
   * 表格分组视图。
   *
   * 🔴 C-8 从两段改**四段**：模板两级表头是四个一级分组（期初余额 C-F+G/H ·
   * 本期变动 I-N · 期末余额 O-R+S/T · 单列说明 A/B/U-W）。原先 `basic`/`fv_oci`
   * 两段是按「自研列 vs OCI 列」切的，与模板分组不对应。
   */
  const activeTab = ref<'basic' | 'opening' | 'movement' | 'closing'>('basic')
  const activeRowIndex = ref(0)
  const auxLoading = ref(false)

  const rows = computed(() => parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark))

  /** 合计行（模板 R21，逐列 `=SUM(x11:x20)`）—— 按模板列聚合。 */
  const totals = computed(() => ({
    openingCost: calcSubtotal(rows.value.map((r) => r.openingCost)),
    openingFvAccum: calcSubtotal(rows.value.map((r) => r.openingFvAccum)),
    openingTotal: calcSubtotal(rows.value.map((r) => r.openingTotal)),
    openingOciCumulative: calcSubtotal(rows.value.map((r) => r.openingOciCumulative)),
    openingAdjusted: calcSubtotal(rows.value.map((r) => r.openingAdjusted)),
    movementCost: calcSubtotal(rows.value.map((r) => r.movementCost)),
    movementFvChange: calcSubtotal(rows.value.map((r) => r.movementFvChange)),
    disposalFvTransfer: calcSubtotal(rows.value.map((r) => r.disposalFvTransfer)),
    ociToRetainedEarnings: calcSubtotal(rows.value.map((r) => r.ociToRetainedEarnings)),
    movementTotal: calcSubtotal(rows.value.map((r) => r.movementTotal)),
    dividendIncome: calcSubtotal(rows.value.map((r) => r.dividendIncome)),
    closingCost: calcSubtotal(rows.value.map((r) => r.closingCost)),
    closingFvAccum: calcSubtotal(rows.value.map((r) => r.closingFvAccum)),
    closingTotal: calcSubtotal(rows.value.map((r) => r.closingTotal)),
    closingOciCumulative: calcSubtotal(rows.value.map((r) => r.closingOciCumulative)),
    closingAdjusted: calcSubtotal(rows.value.map((r) => r.closingAdjusted)),
  }))

  const adjudicationClosingTotal = computed(() =>
    parseAdjudicationClosingTotal(opts.allResponses.value.get('G8-adj-rows')?.remark),
  )

  const adjCrossVariance = computed(() => {
    if (adjudicationClosingTotal.value == null || !rows.value.length) return null
    return totals.value.closingAdjusted - adjudicationClosingTotal.value
  })

  const hasAdjCrossMismatch = computed(() =>
    adjCrossVariance.value != null && Math.abs(adjCrossVariance.value) > DIFF_TOLERANCE,
  )

  const integrityIssues = computed(() => scanG8DetailIntegrity(rows.value))

  const missingDesignationCount = computed(() =>
    integrityIssues.value.filter((i) => i.field === 'designationReason').length,
  )

  const ociRollIssueCount = computed(() =>
    integrityIssues.value.filter((i) => i.field === 'closingOciCumulative').length,
  )

  function persist(list: G8DetailRow[]): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(list) })
  }

  function updateRow(rowId: string, patch: Partial<G8DetailRow>): void {
    if (opts.isReadonly.value) return
    persist(
      rows.value.map((r) =>
        r.rowId === rowId ? enrichG8DetailRow({ ...r, ...patch, rowId }, r.seq) : r,
      ),
    )
  }

  /** 从科目 1503 辅助核算生成/合并明细行 */
  async function seedFromAuxBalance(): Promise<{
    added: number
    updated: number
    dimType: string
    error?: string
  }> {
    if (opts.isReadonly.value) return { added: 0, updated: 0, dimType: '', error: '只读' }
    const projectId = opts.projectId?.value ?? ''
    if (!projectId) return { added: 0, updated: 0, dimType: '', error: '缺少项目 ID' }
    auxLoading.value = true
    try {
      const { seeds, dimType, error } = await fetchG8AuxInvesteeSeeds(projectId)
      if (error || !seeds.length) {
        return { added: 0, updated: 0, dimType, error: error || '无数据' }
      }
      const byName = new Map(
        rows.value
          .filter((r) => r.investeeName.trim())
          .map((r) => [matchG8InvesteeKey(r.investeeName), r]),
      )
      let added = 0
      let updated = 0
      const next: G8DetailRow[] = []
      let seq = 1
      for (const seed of seeds) {
        const key = matchG8InvesteeKey(seed.investeeName)
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
      // 保留辅助核算未覆盖的已有行
      for (const r of rows.value) {
        if (!byName.has(matchG8InvesteeKey(r.investeeName))) continue
        next.push(enrichG8DetailRow(r, seq++))
      }
      persist(next)
      return { added, updated, dimType }
    } finally {
      auxLoading.value = false
    }
  }

  /** 明细合计回写 G8-1 首行未审数 */
  function pushTotalsToAdjudication(): boolean {
    if (opts.isReadonly.value || !rows.value.length) return false
    return pushG8DetailTotalsToAdjudication(
      opts.allResponses.value,
      opts.debouncedSave,
      {
        openingAdjusted: totals.value.openingAdjusted,
        // 🔴 期末未审数取模板 Q 列合计（=O+P），不是已删除的 closingBalance
        closingBalance: totals.value.closingTotal,
        closingAdjusted: totals.value.closingAdjusted,
      },
    )
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入被投资单位名称', '新增明细行', {
        inputPlaceholder: '被投资单位名称',
      })
      const name = (value ?? '').trim()
      if (!name) return
      persist([
        ...rows.value,
        enrichG8DetailRow({ rowId: genId(), investeeName: name }, rows.value.length + 1),
      ])
    } catch { /* cancelled */ }
  }

  function removeRow(rowId: string): void {
    if (opts.isReadonly.value) return
    persist(
      rows.value.filter((r) => r.rowId !== rowId).map((r, i) => enrichG8DetailRow(r, i + 1)),
    )
  }

  return {
    rows,
    activeTab,
    activeRowIndex,
    totals,
    adjudicationClosingTotal,
    adjCrossVariance,
    hasAdjCrossMismatch,
    integrityIssues,
    missingDesignationCount,
    ociRollIssueCount,
    auxLoading,
    updateRow,
    addRow,
    removeRow,
    seedFromAuxBalance,
    pushTotalsToAdjudication,
    confirmationStatusOptions: G8_CONFIRMATION_STATUS_OPTIONS,
  }
}
