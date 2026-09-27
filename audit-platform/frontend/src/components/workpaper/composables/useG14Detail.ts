/**
/**
 * useG14Detail — G14-2「信用减值损失明细表」权威模板列模型（13 列 A..M，固定 9 行 + 合计）
 *
 * spec `g-cycle-single-region-detail-lanes` Task 10 / C-9（选项 A：前端行集对齐模板 9 行）
 *
 * ═══ 模板几何（openpyxl 逐格实测）═══
 *
 * 两级表头 R9/R10；R9 横向分组两个：`B9:D9` 本期数 · `F9:K9` 对应科目-减值准备。
 * 数据区 **R11-R19 固定 9 行**（行集由 `G14_LINE_ITEMS` 固定，`rowKey` 不生成也不派生自
 * 位置）；footer R20 合计（逐列 `=SUM(x11:x19)`，`L20` 例外是布尔 `=D20=K20`）。
 * 有效列 13 = A..M（全满，`max_column` 就是 13）。
 *
 * 四个公式列，每行都有：
 * | 列 | 模板公式 | 口径 |
 * |---|---|---|
 * | D | `=B+C` | 审定数 = 未审 + 调整 |
 * | J | `=F+G-H-I` | 期末余额 = 期初 + 计提 − 转回 − 转销 |
 * | K | `=G+H` | 🔴 见下 |
 * | L | `=D=K` | 布尔核对：审定数 == 计入损益 |
 *
 * ═══ 🔴 模板 `K=G+H` 是缺陷，本模块按 `G−H` 算 ═══
 *
 * `J=F+G-H-I` 要求 `H`「本期转回」填**正数**（转回减少准备）。同一张表里 `K=G+H` 却把
 * 转回当成**增加**损益 —— 两式对 `H` 的符号约定互相矛盾，必有一错。
 *
 * 判定「`K` 错」的三条依据：
 * 1. 会计口径：信用减值损失（损益）= 本期计提 − 本期转回，转回冲减损益；
 * 2. `J` 的形式与准则口径「期初 + 计提 − 转回 − 转销 = 期末」逐字一致，它是对的；
 * 3. 平台早已裁定「转回填正数」—— `useG14FormulaEngine.migrateReversalToPositive`
 *    专门把历史负数统一成正数。
 *
 * ⇒ 本模块 `profitLoss = calcNetImpairmentLoss(计提, 转回) = 计提 − 转回`。
 * 与 G8 的模板缺陷同族处置：`K` 在模板每行都有公式 ⇒ 后端仍判 `mode=formula`
 * （OO 侧改不了），但 Excel 侧显示模板算的值、平台侧显示本模块算的值，**有转回时两者
 * 相差 2×转回**。这个差异是如实登记的欠账（见 spec evidence `task10-c9-g14-rootfix.md`
 * §2.2），不是本模块的 bug：修模板要么改字节（禁止）、要么走覆盖层（框架层尚无该机制）。
 * 模板自己的 `L=D=K` 核对列会在有转回时显示不平 —— 用户看得见，不是静默错。
 *
 * ═══ 🔴 行集必须逐项等于模板 9 行 ═══
 *
 * 行表引擎按**数组顺序**把 store 行映射到 R11-R19。改造前前端自研了第 10 行
 * `rowKey: 'ca'`（合同资产减值损失）⇒ 10 行数据落进 9 行区会扩行、把 footer R20 挤下去。
 * 已按选项 A 并入模板 R19「其他」行（见 `DROPPED_LEGACY_G14_ROWS`）。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { G14_LINE_ITEMS } from './g14Constants'
import {
  parseNum,
  calcAdjustedAmount,
  calcProvisionRollForward,
  calcNetImpairmentLoss,
  calcSubtotal,
  isRollForwardBalanced,
  isReconciled,
  migrateReversalToPositive,
  calcVariance,
} from './useG14FormulaEngine'
import {
  fetchG14ProvisionClosingsFromTb,
  isClosingReconciledWithTb,
  type G14ProvisionTbResult,
} from './g14ProvisionTb'
import { useWorkpaperAuditYear } from './workpaperAuditYear'
import type { ChecklistResponse } from './useF1FormData'

/**
 * G14-2 受管行（13 字段与模板列序 A..M **逐列对应**）+ 3 个不受管的试算对账派生字段。
 *
 * `【公式】` 标记的字段由 `enrichRow` 重算，UI 只读。
 * `rowKey` 是行身份（`stable_template_row_key`，行集由 `G14_LINE_ITEMS` 固定、不生成）。
 */
export interface G14DetailRow {
  /** 行身份（受管 `row_identity_key`）。**不生成、不派生自位置**；合计行用 'total'。 */
  rowKey: string

  /** A 项目 */
  label: string
  /** B 本期数 / 未审数 */
  currentUnadjusted: number
  /** C 本期数 / 调整数 */
  currentAdjustment: number
  /** D 本期数 / 审定数　**【公式】** `=B+C` */
  currentAudited: number
  /** E 对应科目 */
  provisionAccount: string
  /** F 对应科目-减值准备 / 期初余额 */
  openingProvision: number
  /** G 对应科目-减值准备 / 本期计提 */
  currentProvision: number
  /** H 对应科目-减值准备 / 本期转回 —— **填正数**（`J` 与 `K` 都按正数口径） */
  currentReversal: number
  /** I 对应科目-减值准备 / 本期转销 */
  currentWriteoff: number
  /** J 对应科目-减值准备 / 期末余额　**【公式】** `=F+G-H-I` */
  closingProvision: number
  /** K 对应科目-减值准备 / 计入损益　**【公式】** `=G-H`（🔴 模板写的是 `=G+H`，见模块头） */
  profitLoss: number
  /** L 核对　**【公式·布尔】** `=D=K` */
  reconciled: boolean
  /** M 索引号 */
  indexRef: string

  // ── 以下三个**不是模板列**：试算余额对账的派生值，不受管、不进 store ──────
  /** 试算准备期末（取数结果；null=未取到） */
  tbClosing: number | null
  /** 期末余额（J）与试算期末是否一致（无试算数时视为通过） */
  tbClosingMatched: boolean
  /** 期末余额（J） − 试算期末 */
  tbClosingVariance: number | null
}

/**
 * 改造前存在、**已从受管行模型移除**的字段（C-9）。
 *
 * 逐条给出归属而不是笼统「模板没有」—— 指不出归属的才是真冗余。
 */
export const DROPPED_LEGACY_G14_FIELDS: readonly { field: string; reason: string }[] = [
  {
    field: 'otherMovement',
    reason: '模板 J 是 `=F+G-H-I`，**不含**「其他变动」项 —— 自研列会让录入的其他变动在 Excel 侧凭空消失',
  },
  {
    field: 'closingComputed',
    reason: '与模板 J 双源：模板 J 本身就是推算式公式，不存在「录入期末 vs 推算期末」两个值',
  },
  {
    field: 'rollForwardVariance',
    reason: '上一条的差额列，随之失去意义（期末余额的对账对象是**试算余额** tbClosing）',
  },
  {
    field: 'rollForwardBalanced',
    reason: '同上；滚动自洽由模板公式 J 保证，不需要再校验一遍',
  },
] as const

/** 模板固定行集之外、已从行集移除的行（C-9）。 */
export const DROPPED_LEGACY_G14_ROWS: readonly { rowKey: string; reason: string }[] = [
  {
    rowKey: 'ca',
    reason: '权威模板 `明细表G14-2` 固定行集只有 9 行、无「合同资产减值损失」专行；'
      + '合同资产 ECL 按 CAS22 仍计入 6702 ⇒ 并入模板 R19「其他」行（1142 取数、'
      + 'D6 的 ECL 事件、调整分录 rowKey 推断三处落点同步改指 other）',
  },
] as const

const ITEM_ID_ROWS = 'G14-detail-rows'
const ITEM_ID_TB = 'G14-detail-provision-tb'

function createDefaultRows(tb: G14ProvisionTbResult = {}): G14DetailRow[] {
  return G14_LINE_ITEMS.map((def) => enrichRow({ ...def }, tb[def.rowKey] ?? null))
}

/**
 * 按模板四条公式重算派生列。
 *
 * 🔴 `closingProvision`（J）改为**公式**（`=F+G-H-I`）：模板 J 本身就是推算式，没有
 * 「录入期末」的空间。改造前前端把它当录入列、另设 `closingComputed` 推算列并校验两者
 * 一致 —— 那是双源。期末余额的对账对象是**试算余额**（`tbClosing`），不是自己的推算值。
 */
function enrichRow(
  raw: Partial<G14DetailRow> & { rowKey: string },
  tbClosing: number | null = null,
): G14DetailRow {
  const def = G14_LINE_ITEMS.find((d) => d.rowKey === raw.rowKey)
  const currentUnadjusted = parseNum(raw.currentUnadjusted)
  const currentAdjustment = parseNum(raw.currentAdjustment)
  const openingProvision = parseNum(raw.openingProvision)
  const currentProvision = parseNum(raw.currentProvision)
  // 🔴 先 parseNum 再迁移：`migrateReversalToPositive(reversal: number)` 收窄类型，
  //    而 `raw` 是 Partial ⇒ 直接传会是 `number | undefined`（既存类型错，本轮新建的
  //    窄配置 tsconfig._g14.json 首次把它暴露出来）。
  const currentReversal = migrateReversalToPositive(parseNum(raw.currentReversal))
  const currentWriteoff = parseNum(raw.currentWriteoff)
  // D = B+C
  const currentAudited = calcAdjustedAmount(currentUnadjusted, currentAdjustment)
  // 🔴 K = G−H（模板写的是 =G+H，是缺陷，见模块头三条依据）
  const profitLoss = calcNetImpairmentLoss(currentProvision, currentReversal)
  // J = F+G−H−I（模板**不含**「其他变动」项 ⇒ 第五参传 0）
  const closingProvision = calcProvisionRollForward(
    openingProvision,
    currentProvision,
    currentReversal,
    currentWriteoff,
    0,
  )
  const tb = tbClosing != null && !Number.isNaN(tbClosing) ? tbClosing : null
  return {
    rowKey: raw.rowKey,
    label: def?.label ?? raw.label ?? raw.rowKey,
    currentUnadjusted,
    currentAdjustment,
    currentAudited,
    provisionAccount: def?.provisionAccount ?? raw.provisionAccount ?? '',
    openingProvision,
    currentProvision,
    currentReversal,
    currentWriteoff,
    closingProvision,
    profitLoss,
    // L = D=K
    reconciled: isReconciled(currentAudited, profitLoss),
    indexRef: raw.indexRef ?? '',
    tbClosing: tb,
    tbClosingMatched: isClosingReconciledWithTb(closingProvision, tb),
    tbClosingVariance: tb == null ? null : calcVariance(closingProvision, tb),
  }
}

function parseStoredRows(json: string | null | undefined, tb: G14ProvisionTbResult): G14DetailRow[] {
  if (!json) return createDefaultRows(tb)
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return createDefaultRows(tb)
    const byKey = new Map(parsed.map((r: any) => [r.rowKey, r]))
    return G14_LINE_ITEMS.map((def) =>
      enrichRow({ ...def, ...(byKey.get(def.rowKey) ?? {}) }, tb[def.rowKey] ?? null),
    )
  } catch {
    return createDefaultRows(tb)
  }
}

function parseTbCache(json: string | null | undefined): G14ProvisionTbResult {
  if (!json) return {}
  try {
    const parsed = JSON.parse(json)
    if (!parsed || typeof parsed !== 'object') return {}
    const out: G14ProvisionTbResult = {}
    for (const [k, v] of Object.entries(parsed)) {
      if (v == null) out[k] = null
      else out[k] = parseNum(v)
    }
    return out
  } catch {
    return {}
  }
}

export interface UseG14DetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  projectId?: Ref<string> | ComputedRef<string>
}

export function useG14Detail(options: UseG14DetailOptions) {
  const auditYear = useWorkpaperAuditYear()
  const tbClosingByKey = ref<G14ProvisionTbResult>({})
  const tbLoading = ref(false)
  const rows = ref<G14DetailRow[]>(createDefaultRows())

  function reenrichAll(): void {
    rows.value = rows.value.map((r) =>
      enrichRow(r, tbClosingByKey.value[r.rowKey] ?? null),
    )
  }

  watch(
    () => options.allResponses.value.get(ITEM_ID_TB)?.remark,
    (json) => {
      tbClosingByKey.value = parseTbCache(json)
      reenrichAll()
    },
    { immediate: true },
  )

  watch(
    () => options.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => {
      rows.value = parseStoredRows(json, tbClosingByKey.value)
    },
    { immediate: true },
  )

  /**
   * 落库只存**可编辑列**（B/C/F/G/H/I/M）+ 行身份。
   *
   * 🔴 公式列（D/J/K/L）不入 store：它们由 `enrichRow` 按模板公式重算，写进去就是双源。
   * `label`/`provisionAccount`（A/E）也不存 —— 由 `G14_LINE_ITEMS` 按 `rowKey` 派生，
   * 存进去会在模板改名时产生第二真源。
   */
  function persist(): void {
    const payload = rows.value.map((r) => ({
      rowKey: r.rowKey,
      currentUnadjusted: r.currentUnadjusted,
      currentAdjustment: r.currentAdjustment,
      openingProvision: r.openingProvision,
      currentProvision: r.currentProvision,
      currentReversal: r.currentReversal,
      currentWriteoff: r.currentWriteoff,
      indexRef: r.indexRef,
    }))
    options.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(payload) })
    window.dispatchEvent(new CustomEvent('g14:detail-updated'))
  }

  function persistTbCache(): void {
    options.debouncedSave(ITEM_ID_TB, { remark: JSON.stringify(tbClosingByKey.value) })
  }

  function updateCell(rowKey: string, field: keyof G14DetailRow, value: unknown): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowKey === rowKey)
    if (idx === -1) return
    const raw = { ...rows.value[idx], [field]: value }
    const next = [...rows.value]
    next[idx] = enrichRow(raw, tbClosingByKey.value[rowKey] ?? null)
    rows.value = next
    persist()
  }

  function fillUnauditedFromProfitLoss(): void {
    if (options.isReadonly.value) return
    rows.value = rows.value.map((r) =>
      enrichRow({ ...r, currentUnadjusted: r.profitLoss }, tbClosingByKey.value[r.rowKey] ?? null),
    )
    persist()
  }

  /** 从试算表取各行对应准备/OCI/预计负债期末，写入对账列 */
  async function fetchProvisionClosingFromTb(manual = false): Promise<boolean> {
    const projectId = options.projectId?.value
    const year = auditYear.value
    if (!projectId || year == null) {
      if (manual) ElMessage.warning('无法取数：缺少项目或审计年度')
      return false
    }
    tbLoading.value = true
    try {
      const result = await fetchG14ProvisionClosingsFromTb(projectId, year)
      tbClosingByKey.value = result
      reenrichAll()
      persistTbCache()
      const hitCount = Object.values(result).filter((v) => v != null).length
      if (manual) {
        if (hitCount === 0) ElMessage.info('试算表未匹配到减值准备相关科目，请检查科目映射或手工录入期末')
        else ElMessage.success(`已取数对账 ${hitCount} 行准备/OCI/预计负债期末`)
      }
      return hitCount > 0
    } catch {
      if (manual) ElMessage.error('试算取数失败，请稍后重试')
      return false
    } finally {
      tbLoading.value = false
    }
  }

  /**
   * 🔴 C-9 改为「把试算期末倒推进**期初余额**」。
   *
   * 改造前是「把试算期末写入期末余额」—— 但模板 J 是公式 `=F+G-H-I`，期末余额没有录入
   * 空间，写进去会被 `enrichRow` 立刻重算覆盖（等于按钮无效）。
   * 试算期末与推算期末不符时，真正该查的是**期初/计提/转回/转销四个录入项**；
   * 本函数只做一件确定正确的事：在四项变动已录的前提下，令期末等于试算期末所需的期初
   * （`期初 = 试算期末 − 计提 + 转回 + 转销`），供审计人员核对期初是否录错。
   */
  function applyTbClosingToOpening(): void {
    if (options.isReadonly.value) return
    let n = 0
    rows.value = rows.value.map((r) => {
      const tb = tbClosingByKey.value[r.rowKey]
      if (tb == null) return enrichRow(r, null)
      n += 1
      const opening = tb - r.currentProvision + r.currentReversal + r.currentWriteoff
      return enrichRow({ ...r, openingProvision: opening }, tb)
    })
    if (n === 0) {
      ElMessage.info('尚无试算期末数据，请先「取数对账」')
      return
    }
    persist()
    ElMessage.success(`已按试算期末倒推 ${n} 行期初余额（期末=期初+计提−转回−转销）`)
  }

  const dataRows = computed(() => rows.value)
  const totalRow = computed(() => {
    const r = rows.value
    return enrichRow({
      rowKey: 'total',
      label: '合计',
      provisionAccount: '',
      currentUnadjusted: calcSubtotal(r.map((x) => x.currentUnadjusted)),
      currentAdjustment: calcSubtotal(r.map((x) => x.currentAdjustment)),
      openingProvision: calcSubtotal(r.map((x) => x.openingProvision)),
      currentProvision: calcSubtotal(r.map((x) => x.currentProvision)),
      currentReversal: calcSubtotal(r.map((x) => x.currentReversal)),
      currentWriteoff: calcSubtotal(r.map((x) => x.currentWriteoff)),
      indexRef: '',
    }, null)
  })

  const grandTotalAudited = computed(() => totalRow.value.currentAudited)
  const detailTotalMismatch = computed(() =>
    !isReconciled(totalRow.value.currentAudited, totalRow.value.profitLoss),
  )
  const anyTbClosingMismatch = computed(() =>
    rows.value.some((r) => r.tbClosing != null && !r.tbClosingMatched),
  )

  return {
    rows: dataRows,
    totalRow,
    grandTotalAudited,
    detailTotalMismatch,
    anyTbClosingMismatch,
    tbLoading,
    updateCell,
    fillUnauditedFromProfitLoss,
    fetchProvisionClosingFromTb,
    applyTbClosingToOpening,
    persist,
    ITEM_ID_ROWS,
  }
}
