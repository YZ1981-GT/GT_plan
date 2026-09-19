/**
 * useF1Detail — F1-2 明细表核心逻辑 composable
 *
 * Spec: .kiro/specs/f1-prepayment/
 * Excel: F1-2 预付账款明细表（借方科目，3 期账龄）
 *
 * 职责：
 * - DetailRow（3-period: agingPrior / agingCurrent / agingAudited）
 * - 行内公式：H=E+F+G, O=H+M-N, Q=O+P, X=Q+V+W
 * - 合计 / 核对 / 账龄占比 / 账龄逻辑校验
 * - 动态账龄配置（useAgingConfig + migrateD3F1Keys）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  parseNum,
  calcPriorAudited,
  calcEndBalance,
  calcEndUnadjusted,
  calcEndAudited,
  calcSubtotal,
  calcPercentage,
  sumAgingValues,
  checkAgingBalance,
} from './useF1FormulaEngine'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from './useF1FormData'
import { type AgingSegment, type AgingPreset } from '@/composables/useAgingConfig'
import { migrateD3F1Keys, remapRowAgingData, type AgingData } from '@/composables/useAgingMigration'
import { ADJUDICATION_LABEL_BY_SEGMENT_KEY } from './agingPresets'
import { useF1AgingScope, type F1AgingScope } from './useF1AgingScope'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DetailRow {
  rowId: string
  customerName: string       // A: 债权人名称
  companyCode: string        // B: 公司代码
  relationType: string       // C: 关联方类型
  nature: string             // D: 款项性质
  priorUnadjusted: number    // E: 期初未审数
  priorAdjustment: number    // F: 期初账项调整
  priorReclass: number       // G: 期初重分类调整
  priorAudited: number       // H: =E+F+G
  agingPrior: AgingData      // I~L: 期初审定账龄
  debit: number              // M: 借方发生
  credit: number             // N: 贷方发生
  endBalance: number         // O: =H+M-N
  entityReclass: number      // P: 被审计单位重分类调整
  endUnadjusted: number      // Q: =O+P
  agingCurrent: AgingData    // R~U: 期末未审账龄
  endAje: number             // V: 账项调整
  endRje: number             // W: 重分类调整
  endAudited: number         // X: =Q+V+W
  agingAudited: AgingData    // Y~AB: 期末审定账龄
  isConfirmed: string        // AC: 是否函证
  postPeriodSettlement: number // AD: 期后回款
  remark: string             // AE: 备注
}

export interface UseF1DetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
  relatedParties: Ref<string[]>
  /**
   * F1 账龄口径单一真源（由主入口装配后注入，与审定表/附注/长期/关联方共享）。
   * 未注入时内部自建（向后兼容单独挂载明细表的场景）。
   */
  agingScope?: F1AgingScope
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'F1-det-rows'
const ITEM_ID_TB_AMOUNT = 'F1-adj-trial-balance-amount'
const AGING_TOLERANCE = 0.01

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

function emptyAging(segments: AgingSegment[]): AgingData {
  const aging: AgingData = {}
  for (const seg of segments) aging[seg.key] = 0
  return aging
}

/** 安全解析 JSON 数组（使用动态 segments 进行迁移） */
function safeParseRows(jsonStr: string | null | undefined, segments: AgingSegment[]): DetailRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(raw => normalizeRow(raw, segments)) : []
  } catch {
    return []
  }
}

/** 规范化行数据，确保所有字段存在且类型正确（使用动态 segments） */
function normalizeRow(raw: any, segments: AgingSegment[]): DetailRow {
  const migrated = migrateD3F1Keys(raw, segments)

  return {
    rowId: raw.rowId || generateRowId(),
    customerName: raw.customerName || '',
    companyCode: raw.companyCode || '',
    nature: raw.nature || '',
    relationType: raw.relationType || '非关联方',
    priorUnadjusted: parseNum(raw.priorUnadjusted),
    priorAdjustment: parseNum(raw.priorAdjustment),
    priorReclass: parseNum(raw.priorReclass),
    priorAudited: parseNum(raw.priorAudited),
    agingPrior: migrated.agingPrior,
    debit: parseNum(raw.debit),
    credit: parseNum(raw.credit),
    endBalance: parseNum(raw.endBalance),
    entityReclass: parseNum(raw.entityReclass),
    endUnadjusted: parseNum(raw.endUnadjusted),
    agingCurrent: migrated.agingCurrent || emptyAging(segments),
    endAje: parseNum(raw.endAje),
    endRje: parseNum(raw.endRje),
    endAudited: parseNum(raw.endAudited),
    agingAudited: migrated.agingAudited,
    isConfirmed: raw.isConfirmed || '',
    postPeriodSettlement: parseNum(raw.postPeriodSettlement),
    remark: raw.remark || '',
  }
}

/**
 * 对单行重新计算公式链：
 * H = E + F + G
 * O = H + M - N（借方科目）
 * Q = O + P
 * X = Q + V + W
 */
export function recalcRowFormulas(row: DetailRow): DetailRow {
  const H = calcPriorAudited(row.priorUnadjusted, row.priorAdjustment, row.priorReclass)
  const O = calcEndBalance(H, row.debit, row.credit)
  const Q = calcEndUnadjusted(O, row.entityReclass)
  const X = calcEndAudited(Q, row.endAje, row.endRje)

  return {
    ...row,
    priorAudited: H,
    endBalance: O,
    endUnadjusted: Q,
    endAudited: X,
  }
}

/** 创建空行（账龄段基于当前项目配置动态初始化为 0） */
export function createEmptyRow(segments: AgingSegment[] = []): DetailRow {
  const empty = emptyAging(segments)
  return {
    rowId: generateRowId(),
    customerName: '',
    companyCode: '',
    nature: '',
    relationType: '非关联方',
    priorUnadjusted: 0,
    priorAdjustment: 0,
    priorReclass: 0,
    priorAudited: 0,
    agingPrior: { ...empty },
    debit: 0,
    credit: 0,
    endBalance: 0,
    entityReclass: 0,
    endUnadjusted: 0,
    agingCurrent: { ...empty },
    endAje: 0,
    endRje: 0,
    endAudited: 0,
    agingAudited: { ...empty },
    isConfirmed: '',
    postPeriodSettlement: 0,
    remark: '',
  }
}

/**
 * 关联方匹配逻辑（纯函数，方便测试）
 */
export function matchRelatedPartyPure(customerName: string, relatedParties: string[]): string {
  if (!customerName) return '非关联方'
  const nameLower = customerName.toLowerCase()
  for (const party of relatedParties) {
    if (!party) continue
    const partyLower = party.toLowerCase()
    if (nameLower.includes(partyLower) || partyLower.includes(nameLower)) {
      return party
    }
  }
  return '非关联方'
}

/**
 * 搜索过滤逻辑（纯函数，方便测试）
 */
export function filterRowsBySearch(rows: DetailRow[], query: string): DetailRow[] {
  if (!query) return rows
  const q = query.toLowerCase()
  return rows.filter(row => row.customerName.toLowerCase().includes(q))
}

/**
 * 函证完成事件处理逻辑（纯函数，方便测试）
 */
export function applyConfirmationCompleted(rows: DetailRow[], customerName: string): DetailRow[] {
  if (!customerName) return rows
  const nameLower = customerName.toLowerCase()
  return rows.map(row => {
    if (row.customerName.toLowerCase() === nameLower) {
      return { ...row, isConfirmed: 'Y' }
    }
    return row
  })
}

function sumAgingField(allRows: DetailRow[], field: 'agingPrior' | 'agingCurrent' | 'agingAudited', segments: AgingSegment[]): AgingData {
  const result: AgingData = {}
  for (const seg of segments) {
    result[seg.key] = calcSubtotal(allRows.map(r => r[field]?.[seg.key] ?? 0))
  }
  return result
}

function buildMetaRow(
  rowId: string,
  customerName: string,
  segments: AgingSegment[],
  overrides: Partial<DetailRow> = {},
): DetailRow {
  return {
    ...createEmptyRow(segments),
    rowId,
    customerName,
    ...overrides,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF1Detail(options: UseF1DetailOptions) {
  const { allResponses, wpId, projectId, debouncedSave, isReadonly, relatedParties } = options

  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  /**
   * 账龄口径：优先用主入口注入的 F1 单一真源（与审定表/附注/长期/关联方共享），
   * 未注入时内部自建（明细表单独挂载的兼容路径）。
   */
  const agingScope: F1AgingScope = options.agingScope ?? useF1AgingScope({
    allResponses,
    projectId,
    debouncedSave,
    isReadonly,
  })

  const agingPreset: ComputedRef<AgingPreset> = agingScope.preset
  const customSegments = agingScope.customSegments
  const segments: ComputedRef<AgingSegment[]> = agingScope.segments

  /** 列定义：使用审定表同口径枚举标签（含N年） */
  const bands = computed(() =>
    segments.value.map((seg) => ({
      key: seg.key,
      label: ADJUDICATION_LABEL_BY_SEGMENT_KEY[seg.key] || seg.label,
      priorField: `agingPrior.${seg.key}`,
      currentField: `agingCurrent.${seg.key}`,
      auditedField: `agingAudited.${seg.key}`,
    })),
  )

  const rows = ref<DetailRow[]>([])
  const searchQuery = ref<string>('')

  watch(
    [() => allResponses.value.get(ITEM_ID_ROWS)?.remark, segments],
    ([jsonStr]) => {
      const segs = segments.value
      if (!segs.length) return
      const parsed = safeParseRows(jsonStr as string | undefined, segs)
      rows.value = parsed.map(recalcRowFormulas)
    },
    { immediate: true },
  )

  function persistRows(): void {
    const toSave = rows.value.map(row => ({ ...row }))
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(toSave) })
  }

  const filteredRows: ComputedRef<DetailRow[]> = computed(() => {
    return filterRowsBySearch(rows.value, searchQuery.value)
  })

  const subtotalRow: ComputedRef<DetailRow> = computed(() => {
    const allRows = rows.value
    const segs = segments.value
    return buildMetaRow('__subtotal__', '合计', segs, {
      priorUnadjusted: calcSubtotal(allRows.map(r => r.priorUnadjusted)),
      priorAdjustment: calcSubtotal(allRows.map(r => r.priorAdjustment)),
      priorReclass: calcSubtotal(allRows.map(r => r.priorReclass)),
      priorAudited: calcSubtotal(allRows.map(r => r.priorAudited)),
      agingPrior: sumAgingField(allRows, 'agingPrior', segs),
      debit: calcSubtotal(allRows.map(r => r.debit)),
      credit: calcSubtotal(allRows.map(r => r.credit)),
      endBalance: calcSubtotal(allRows.map(r => r.endBalance)),
      entityReclass: calcSubtotal(allRows.map(r => r.entityReclass)),
      endUnadjusted: calcSubtotal(allRows.map(r => r.endUnadjusted)),
      agingCurrent: sumAgingField(allRows, 'agingCurrent', segs),
      endAje: calcSubtotal(allRows.map(r => r.endAje)),
      endRje: calcSubtotal(allRows.map(r => r.endRje)),
      endAudited: calcSubtotal(allRows.map(r => r.endAudited)),
      agingAudited: sumAgingField(allRows, 'agingAudited', segs),
      postPeriodSettlement: calcSubtotal(allRows.map(r => r.postPeriodSettlement)),
    })
  })

  const verificationRow: ComputedRef<DetailRow> = computed(() => {
    const tbAmount = parseNum(allResponses.value.get(ITEM_ID_TB_AMOUNT)?.remark)
    const sub = subtotalRow.value
    const segs = segments.value
    return buildMetaRow('__verification__', '核对行（合计-TB数）', segs, {
      priorUnadjusted: sub.priorUnadjusted,
      priorAdjustment: sub.priorAdjustment,
      priorReclass: sub.priorReclass,
      priorAudited: sub.priorAudited,
      agingPrior: sub.agingPrior,
      debit: sub.debit,
      credit: sub.credit,
      endBalance: sub.endBalance,
      entityReclass: sub.entityReclass,
      endUnadjusted: sub.endUnadjusted,
      agingCurrent: sub.agingCurrent,
      endAje: sub.endAje,
      endRje: sub.endRje,
      endAudited: sub.endAudited - tbAmount,
      agingAudited: sub.agingAudited,
      postPeriodSettlement: sub.postPeriodSettlement,
    })
  })

  /** 账龄占比行：各段金额 / 对应余额合计 */
  const agingPctRow = computed(() => {
    const sub = subtotalRow.value
    const segs = segments.value
    const priorPct: AgingData = {}
    const currentPct: AgingData = {}
    const auditedPct: AgingData = {}
    for (const seg of segs) {
      priorPct[seg.key] = calcPercentage(sub.agingPrior?.[seg.key] ?? 0, sub.priorAudited)
      currentPct[seg.key] = calcPercentage(sub.agingCurrent?.[seg.key] ?? 0, sub.endUnadjusted)
      auditedPct[seg.key] = calcPercentage(sub.agingAudited?.[seg.key] ?? 0, sub.endAudited)
    }
    return buildMetaRow('__aging_pct__', '账龄占比', segs, {
      agingPrior: priorPct,
      agingCurrent: currentPct,
      agingAudited: auditedPct,
    })
  })

  /** 账龄逻辑校验行：各段之和是否等于对应余额 */
  const agingCheckRow = computed(() => {
    const sub = subtotalRow.value
    const segs = segments.value
    const priorOk = checkAgingBalance(sumAgingValues(sub.agingPrior), sub.priorAudited, AGING_TOLERANCE)
    const currentOk = checkAgingBalance(sumAgingValues(sub.agingCurrent), sub.endUnadjusted, AGING_TOLERANCE)
    const auditedOk = checkAgingBalance(sumAgingValues(sub.agingAudited), sub.endAudited, AGING_TOLERANCE)

    // 用 aging 字段存 TRUE/FALSE 标记（UI 按 rowId 特殊渲染）
    const flag = (ok: boolean): AgingData => {
      const d: AgingData = {}
      for (const seg of segs) d[seg.key] = ok ? 1 : 0
      return d
    }

    return buildMetaRow('__aging_check__', '账龄逻辑校验', segs, {
      priorAudited: priorOk ? 1 : 0,
      endUnadjusted: currentOk ? 1 : 0,
      endAudited: auditedOk ? 1 : 0,
      agingPrior: flag(priorOk),
      agingCurrent: flag(currentOk),
      agingAudited: flag(auditedOk),
    })
  })

  function addRow(): void {
    if (isReadonly.value) return
    rows.value = [...rows.value, createEmptyRow(segments.value)]
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return

    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }

    if (field.startsWith('agingPrior.')) {
      const subField = field.replace('agingPrior.', '')
      row.agingPrior = { ...row.agingPrior, [subField]: parseNum(value) }
    } else if (field.startsWith('agingCurrent.')) {
      const subField = field.replace('agingCurrent.', '')
      row.agingCurrent = { ...row.agingCurrent, [subField]: parseNum(value) }
    } else if (field.startsWith('agingAudited.')) {
      const subField = field.replace('agingAudited.', '')
      row.agingAudited = { ...row.agingAudited, [subField]: parseNum(value) }
    } else if (['priorUnadjusted', 'priorAdjustment', 'priorReclass', 'debit', 'credit', 'entityReclass', 'endAje', 'endRje', 'postPeriodSettlement'].includes(field)) {
      ;(row as any)[field] = parseNum(value)
    } else {
      ;(row as any)[field] = value
    }

    if (field === 'customerName' && value) {
      row.relationType = matchRelatedPartyPure(String(value), relatedParties.value)
    }

    const recalculated = recalcRowFormulas(row)
    const newRows = [...rows.value]
    newRows[idx] = recalculated
    rows.value = newRows
    persistRows()
  }

  function matchRelatedParty(name: string): string {
    return matchRelatedPartyPure(name, relatedParties.value)
  }

  /**
   * 从 tb_aux_balance（科目 1123，按往来单位维度）归集导入。
   *
   * 后端按当前账龄口径构建完整行（agingPrior/agingCurrent/agingAudited 落首段）
   * 并已 merge 落库；此处把新增行并入本地 rows 保持界面即时一致。
   */
  async function importFromAuxBalance(): Promise<void> {
    if (!wpId.value) return
    try {
      const res: any = await api.post(
        `/api/workpapers/${wpId.value}/f1/import-aux-balance`,
        { project_id: projectId.value },
      )
      const body = res?.data ?? res
      const importedRows: any[] = Array.isArray(body) ? body : (body?.rows ?? [])
      const serverMessage: string = String(body?.message || '')

      if (importedRows.length === 0) {
        ElMessage.info(serverMessage || '未找到科目1123的辅助余额数据')
        return
      }

      const existingMap = new Map(rows.value.map(r => [r.customerName, r]))
      let newCount = 0

      for (const imported of importedRows) {
        const name = imported.customerName || imported.customer_name || ''
        if (!name) continue

        if (existingMap.has(name)) {
          // 已有单位：只刷新四表库来源列（期初/借/贷），不覆盖审计师录入的账龄与调整
          const existing = existingMap.get(name)!
          existing.priorUnadjusted = parseNum(imported.priorUnadjusted ?? imported.prior_unadjusted)
          existing.credit = parseNum(imported.credit)
          existing.debit = parseNum(imported.debit)
          existingMap.set(name, recalcRowFormulas(existing))
        } else {
          // 新单位：后端已按当前账龄口径构建整行（账龄落首段），整行接入
          const newRow = normalizeRow(
            { ...imported, rowId: imported.rowId || generateRowId() },
            segments.value,
          )
          existingMap.set(name, recalcRowFormulas(newRow))
          newCount++
        }
      }

      rows.value = Array.from(existingMap.values())
      persistRows()
      ElMessage.success(serverMessage || `成功导入${importedRows.length}行数据，${newCount}个新客户`)
    } catch {
      ElMessage.error('从辅助余额表导入失败，请稍后重试')
    }
  }

  function onConfirmationCompleted(payload: { customerName: string }): void {
    if (!payload.customerName) return
    rows.value = applyConfirmationCompleted(rows.value, payload.customerName)
    persistRows()
  }

  /**
   * 切换账龄枚举口径（3年段 / 5年段 / 自定义）。
   * 写入表级覆盖并 remap 已有行的账龄字段。CUSTOM 需传入 ≥2 段标签。
   */
  function setAgingPreset(preset: AgingPreset, customLabels?: string[]): boolean {
    if (isReadonly.value) return false
    if (!agingScope.setPreset(preset, customLabels)) return false
    // scope.segments 为 computed（切换后即时反映），据此 remap 已有行的账龄字段
    const segs = segments.value
    rows.value = rows.value.map(row =>
      recalcRowFormulas(remapRowAgingData(row, segs, true) as DetailRow),
    )
    persistRows()
    return true
  }

  /**
   * 按枚举档位快捷分配：将对应余额整笔填入指定账龄段，其余段清零。
   * stage: prior=期初审定 / current=期末未审 / audited=期末审定
   */
  function allocateAging(
    rowId: string,
    stage: 'prior' | 'current' | 'audited',
    segmentKey: string,
  ): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    const row = recalcRowFormulas({ ...rows.value[idx] })
    const segs = segments.value
    const empty = emptyAging(segs)
    if (stage === 'prior') {
      empty[segmentKey] = row.priorAudited
      row.agingPrior = empty
    } else if (stage === 'current') {
      empty[segmentKey] = row.endUnadjusted
      row.agingCurrent = empty
    } else {
      empty[segmentKey] = row.endAudited
      row.agingAudited = empty
    }
    const newRows = [...rows.value]
    newRows[idx] = row
    rows.value = newRows
    persistRows()
  }

  const confirmationHandler = (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (detail?.customerName) onConfirmationCompleted(detail)
  }
  window.addEventListener('confirmation:completed', confirmationHandler)
  eventListeners.push({ event: 'confirmation:completed', handler: confirmationHandler })

  const agingConfigHandler = () => {
    // 表级覆盖存在时不跟随项目全局变更
    if (agingScope.hasSheetOverride.value) return
    if (!segments.value.length) return
    rows.value = rows.value.map(row =>
      remapRowAgingData(row, segments.value, true) as DetailRow,
    )
    persistRows()
  }
  window.addEventListener('aging-config:changed', agingConfigHandler)
  eventListeners.push({ event: 'aging-config:changed', handler: agingConfigHandler })

  onBeforeUnmount(() => {
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
  })

  return {
    rows,
    filteredRows,
    subtotalRow,
    verificationRow,
    agingPctRow,
    agingCheckRow,
    searchQuery,
    segments,
    bands,
    agingPreset,
    customSegments,
    setAgingPreset,
    allocateAging,
    addRow,
    removeRow,
    updateCell,
    matchRelatedParty,
    importFromAuxBalance,
    onConfirmationCompleted,
  }
}

export default useF1Detail
