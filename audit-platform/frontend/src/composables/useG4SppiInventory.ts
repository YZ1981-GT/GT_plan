/**
 * useG4SppiInventory — G4-7 有价证券盘点表
 *
 * Spec: .kiro/specs/g4-bond-investment-sppi/ Task 7.1
 * Requirements: 4.1~4.8, 6.3, 6.8
 *
 * 职责：
 * - 管理 InventoryHeader（盘点单位/日期/地点/人员/监盘叙述）
 * - 管理 InventoryItem[]（seq/securitiesName/faceValue/quantity/total/couponRate/maturityDate）
 * - computed: 每行 total = calcInventoryTotal(faceValue, quantity)
 * - computed: 合计行 + headerStatus（关键字段完备性）
 * - 动态行增删；监盘叙述可由头信息自动生成
 * - 持久化到 checklist_responses via debouncedSave
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { calcInventoryTotal, calcSumColumn, parseNum } from '@/composables/useG4SppiFormulaEngine'
import type { ChecklistResponse } from '@/composables/useG4SppiFormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface InventoryHeader {
  company: string
  countDate: string
  /** 资产负债表日 / 截止日（用于判断是否需要倒轧） */
  balanceSheetDate: string
  /** 盘点地点（纸质底稿叙述与多地点监盘控制所必需） */
  location: string
  accountingSupervisor: string
  cashier: string
  observer: string
  counter: string
  /** 复核人（纸质表头字段） */
  reviewer: string
  /** 参加人数（叙述「XX人于…」） */
  participantCount: string
  /** 监盘叙述（可由头信息生成，可手改） */
  narrative: string
}

export interface InventoryItem {
  id: string
  seq: number
  securitiesName: string
  faceValue: number
  quantity: number
  total: number              // 公式: 面值 × 数量 (2dp)
  couponRate: number
  maturityDate: string
}

export interface InventorySummary {
  faceValueTotal: number
  quantityTotal: number
  totalTotal: number
}

export interface HeaderCompleteness {
  filled: number
  total: number
  missing: string[]
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY_HEADER = 'G4-7-header'
const STORAGE_KEY_ITEMS = 'G4-7-items'
const STORAGE_KEY_AUDIT_DESC = 'G4-7-audit-description'
const STORAGE_KEY_AUDIT_CONCLUSION = 'G4-7-audit-conclusion'

/** G4-8 倒轧表持久化键（推送目标） */
const RECON_KEY_ITEMS = 'G4-8-items'
const RECON_KEY_HEADER = 'G4-8-header'

const MAX_ROWS = 200

const REQUIRED_HEADER_FIELDS: { key: keyof InventoryHeader; label: string }[] = [
  { key: 'company', label: '盘点单位' },
  { key: 'countDate', label: '盘点日期' },
  { key: 'location', label: '盘点地点' },
  { key: 'observer', label: '监盘人' },
  { key: 'counter', label: '盘点人' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateId(): string {
  return `g4inv-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function createDefaultHeader(): InventoryHeader {
  return {
    company: '',
    countDate: '',
    balanceSheetDate: '',
    location: '',
    accountingSupervisor: '',
    cashier: '',
    observer: '',
    counter: '',
    reviewer: '',
    participantCount: '',
    narrative: '',
  }
}

/** 盘点日与资产负债表日均已填写且不相等 → 需要 G4-8 倒轧 */
export function isRollForwardNeeded(countDate: string, balanceSheetDate: string): boolean {
  const a = (countDate || '').trim().slice(0, 10)
  const b = (balanceSheetDate || '').trim().slice(0, 10)
  if (!a || !b) return false
  return a !== b
}

function normalizeDate(v: unknown): string {
  return String(v ?? '').trim().slice(0, 10)
}

/** 由盘点头生成监盘叙述（对齐纸质底稿红字占位句式） */
export function buildInventoryNarrative(h: InventoryHeader): string {
  const people = h.participantCount?.trim() || '—'
  const date = h.countDate?.trim() || '—年—月—日'
  const loc = h.location?.trim() || '—'
  const parts = [
    `${people}人于${date}，在${loc}对有价证券进行盘点，现将现场盘点出的有价证券列示如下：`,
  ]
  const roles: string[] = []
  if (h.observer?.trim()) roles.push(`监盘人：${h.observer.trim()}`)
  if (h.counter?.trim()) roles.push(`盘点人：${h.counter.trim()}`)
  if (h.accountingSupervisor?.trim()) roles.push(`会计主管：${h.accountingSupervisor.trim()}`)
  if (h.cashier?.trim()) roles.push(`出纳：${h.cashier.trim()}`)
  if (h.reviewer?.trim()) roles.push(`复核人：${h.reviewer.trim()}`)
  if (roles.length) parts.push(roles.join('；') + '。')
  if (h.company?.trim()) parts.push(`盘点单位：${h.company.trim()}。`)
  return parts.join('')
}

export function headerCompleteness(h: InventoryHeader): HeaderCompleteness {
  const missing = REQUIRED_HEADER_FIELDS
    .filter((f) => !String(h[f.key] ?? '').trim())
    .map((f) => f.label)
  return {
    filled: REQUIRED_HEADER_FIELDS.length - missing.length,
    total: REQUIRED_HEADER_FIELDS.length,
    missing,
  }
}

function createEmptyItem(name: string, seq: number): InventoryItem {
  return {
    id: generateId(),
    seq,
    securitiesName: name,
    faceValue: 0,
    quantity: 0,
    total: 0,
    couponRate: 0,
    maturityDate: '',
  }
}

/** 公式链求解：每行 total = 面值 × 数量 */
function enrichItem(item: InventoryItem): InventoryItem {
  return {
    ...item,
    total: calcInventoryTotal(item.faceValue, item.quantity),
  }
}

function safeParseJson<T>(jsonStr: string | null | undefined): T | null {
  if (!jsonStr) return null
  try {
    return JSON.parse(jsonStr) as T
  } catch {
    return null
  }
}

function normalizeHeader(raw: Partial<InventoryHeader> | null): InventoryHeader {
  return { ...createDefaultHeader(), ...(raw || {}) }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseG4SppiInventoryOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  /** 推送至 G4-8 时优先立即落库，避免切换 Tab 时 debounce 未刷出 */
  saveImmediate?: (itemId: string, data: Partial<ChecklistResponse>) => void | Promise<void>
  isReadonly: Ref<boolean>
  /** 项目级资产负债表日（htmlData），可覆盖空的头信息字段 */
  projectBalanceSheetDate?: Ref<string>
}

export function useG4SppiInventory(opts: UseG4SppiInventoryOptions) {
  const { allResponses, debouncedSave, isReadonly } = opts

  function persistOut(itemId: string, data: Partial<ChecklistResponse>): void {
    if (opts.saveImmediate) {
      void opts.saveImmediate(itemId, data)
    } else {
      debouncedSave(itemId, data)
    }
  }

  // ─── 盘点信息头 ──────────────────────────────────────────────────────────
  const header = ref<InventoryHeader>(createDefaultHeader())

  // ─── 盘点明细 ────────────────────────────────────────────────────────────
  const items = ref<InventoryItem[]>([enrichItem(createEmptyItem('', 1))])

  // ─── 审计说明/结论 ───────────────────────────────────────────────────────
  const auditDescription = ref('')
  const auditConclusion = ref('')

  // ─── 合计行（computed） ──────────────────────────────────────────────────
  const summary = computed<InventorySummary>(() => ({
    faceValueTotal: calcSumColumn(items.value.map((i) => parseNum(i.faceValue))),
    quantityTotal: calcSumColumn(items.value.map((i) => parseNum(i.quantity))),
    totalTotal: calcSumColumn(items.value.map((i) => i.total)),
  }))

  const headerStatus = computed(() => headerCompleteness(header.value))

  /** 有效报表日：本表头优先，其次项目截止日，再次 G4-8 头 */
  const effectiveBalanceSheetDate = computed(() => {
    const fromHeader = normalizeDate(header.value.balanceSheetDate)
    if (fromHeader) return fromHeader
    const fromProject = normalizeDate(opts.projectBalanceSheetDate?.value)
    if (fromProject) return fromProject
    const g48 = safeParseJson<{ balanceSheetDate?: string }>(
      allResponses.value.get(RECON_KEY_HEADER)?.remark,
    )
    return normalizeDate(g48?.balanceSheetDate)
  })

  const needsRollForward = computed(() =>
    isRollForwardNeeded(header.value.countDate, effectiveBalanceSheetDate.value),
  )

  const validItemCount = computed(
    () => items.value.filter((i) => (i.securitiesName || '').trim()).length,
  )

  // ─── 从 allResponses 加载 ────────────────────────────────────────────────

  function readStoredRaw(itemId: string): string | null {
    const item = allResponses.value.get(itemId)
    const c = item?.conclusion
    if (c != null && String(c).trim() !== '') return String(c)
    const r = item?.remark
    if (r != null && String(r).trim() !== '') return String(r)
    return null
  }

  function loadFromResponses(): void {
    const headerParsed = safeParseJson<Partial<InventoryHeader>>(readStoredRaw(STORAGE_KEY_HEADER))
    if (headerParsed) {
      header.value = normalizeHeader(headerParsed)
    }
    // 项目截止日回填空字段
    if (!header.value.balanceSheetDate && opts.projectBalanceSheetDate?.value) {
      header.value = {
        ...header.value,
        balanceSheetDate: normalizeDate(opts.projectBalanceSheetDate.value),
      }
    }

    const itemsParsed = safeParseJson<InventoryItem[]>(readStoredRaw(STORAGE_KEY_ITEMS))
    if (itemsParsed && Array.isArray(itemsParsed) && itemsParsed.length > 0) {
      items.value = itemsParsed.map(enrichItem)
    }

    auditDescription.value = readStoredRaw(STORAGE_KEY_AUDIT_DESC) || ''
    auditConclusion.value = readStoredRaw(STORAGE_KEY_AUDIT_CONCLUSION) || ''
  }

  // allResponses 异步加载完成后回填
  watch(
    () => readStoredRaw(STORAGE_KEY_ITEMS),
    () => loadFromResponses(),
    { immediate: true },
  )

  watch(
    () => opts.projectBalanceSheetDate?.value,
    (v) => {
      if (!header.value.balanceSheetDate && v) {
        header.value = { ...header.value, balanceSheetDate: normalizeDate(v) }
      }
    },
  )

  // ─── 持久化 ──────────────────────────────────────────────────────────────

  function persistHeader(): void {
    if (isReadonly.value) return
    const json = JSON.stringify(header.value)
    debouncedSave(STORAGE_KEY_HEADER, { conclusion: json, remark: json })
  }

  function persistItems(): void {
    if (isReadonly.value) return
    const json = JSON.stringify(items.value)
    debouncedSave(STORAGE_KEY_ITEMS, { conclusion: json, remark: json })
  }

  function persistAuditDescription(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_AUDIT_DESC, { conclusion: null, remark: auditDescription.value })
  }

  function persistAuditConclusion(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_AUDIT_CONCLUSION, { conclusion: null, remark: auditConclusion.value })
  }

  // ─── 操作 ────────────────────────────────────────────────────────────────

  function updateHeader(patch: Partial<InventoryHeader>, regenNarrative = false): void {
    if (isReadonly.value) return
    const next = { ...header.value, ...patch }
    if (regenNarrative || !next.narrative?.trim()) {
      next.narrative = buildInventoryNarrative(next)
    }
    header.value = next
    persistHeader()
  }

  function regenerateNarrative(): void {
    if (isReadonly.value) return
    header.value = { ...header.value, narrative: buildInventoryNarrative(header.value) }
    persistHeader()
  }

  function updateItem(id: string, patch: Partial<InventoryItem>): void {
    if (isReadonly.value) return
    items.value = items.value.map((item) => {
      if (item.id !== id) return item
      const updated = { ...item, ...patch }
      return enrichItem(updated)
    })
    persistItems()
  }

  async function addItem(): Promise<void> {
    if (isReadonly.value) return
    if (items.value.length >= MAX_ROWS) {
      ElMessageBox.alert(`行数已达上限（${MAX_ROWS}行），无法继续新增。`, '提示')
      return
    }
    try {
      const { value: name } = await ElMessageBox.prompt(
        '请输入证券名称',
        '新增盘点明细',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '证券名称不能为空',
        },
      )
      const seq = items.value.length + 1
      items.value = [...items.value, enrichItem(createEmptyItem(name, seq))]
      persistItems()
    } catch {
      /* cancelled */
    }
  }

  function removeItem(id: string): void {
    if (isReadonly.value || items.value.length <= 1) return
    items.value = items.value
      .filter((item) => item.id !== id)
      .map((item, idx) => ({ ...item, seq: idx + 1 }))
    persistItems()
  }

  function setAuditDescription(value: string): void {
    if (isReadonly.value) return
    auditDescription.value = value
    persistAuditDescription()
  }

  function setAuditConclusion(value: string): void {
    if (isReadonly.value) return
    auditConclusion.value = value
    persistAuditConclusion()
  }

  /**
   * 将本表盘点明细推送到 G4-8 倒轧表（盘点日实存区段）。
   * 按 inventoryRowId / 证券名称匹配，保留已有增减与账面/备注。
   */
  function pushToReconciliation(): number {
    if (isReadonly.value) return 0
    const sources = items.value.filter((r) => (r.securitiesName || '').trim())
    if (!sources.length) {
      ElMessage.warning('本表无有效盘点行可推送（请先填写证券名称）')
      return 0
    }

    let existing: Array<Record<string, unknown>> = []
    const raw = allResponses.value.get(RECON_KEY_ITEMS)?.remark
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed)) existing = parsed
      } catch {
        /* ignore */
      }
    }

    const byInvId = new Map(
      existing
        .filter((r) => r.inventoryRowId)
        .map((r) => [String(r.inventoryRowId), r]),
    )
    const byName = new Map(
      existing
        .filter((r) => String(r.securitiesName ?? '').trim())
        .map((r) => [String(r.securitiesName).trim(), r]),
    )

    const next: Record<string, unknown>[] = []
    let added = 0
    let updated = 0

    for (const src of sources) {
      const name = src.securitiesName.trim()
      const matched = byInvId.get(src.id) || byName.get(name)
      const countFaceValue = parseNum(src.faceValue)
      const countQuantity = parseNum(src.quantity)
      const countCouponRate = parseNum(src.couponRate)
      const countMaturityDate = String(src.maturityDate || '')
      const countTotal = calcInventoryTotal(countFaceValue, countQuantity)

      const countPatch = {
        securitiesName: name,
        countFaceValue,
        countQuantity,
        countTotal,
        countCouponRate,
        countMaturityDate,
        inventoryRowId: src.id,
        // 报表日条款默认继承盘点日（增减为 0 时报告日=盘点日）
        reportFaceValue: countFaceValue,
        reportCouponRate: countCouponRate,
        reportMaturityDate: countMaturityDate,
      }

      if (matched) {
        next.push({
          ...matched,
          ...countPatch,
          id: matched.id || `from-g47-${src.id}`,
          // 保留增减、账面、差异备注、证据索引
          increaseQuantity: matched.increaseQuantity ?? 0,
          increaseFaceTotal: matched.increaseFaceTotal ?? 0,
          decreaseQuantity: matched.decreaseQuantity ?? 0,
          decreaseFaceTotal: matched.decreaseFaceTotal ?? 0,
          changeEvidenceRef: matched.changeEvidenceRef ?? '',
          bookQuantity: matched.bookQuantity ?? 0,
          bookFaceValue: matched.bookFaceValue ?? countFaceValue,
          bookTotal: matched.bookTotal ?? 0,
          bookCarryingAmount: matched.bookCarryingAmount ?? 0,
          remark: matched.remark ?? '',
          // 兼容旧净增字段
          changeQuantity: matched.changeQuantity,
          changeFaceValueTotal: matched.changeFaceValueTotal,
        })
        updated += 1
      } else {
        next.push({
          id: `from-g47-${src.id}`,
          seq: next.length + 1,
          ...countPatch,
          increaseQuantity: 0,
          increaseFaceTotal: 0,
          decreaseQuantity: 0,
          decreaseFaceTotal: 0,
          changeEvidenceRef: '',
          reportQuantity: countQuantity,
          reportTotal: countTotal,
          bookQuantity: 0,
          bookFaceValue: countFaceValue,
          bookTotal: 0,
          bookCarryingAmount: 0,
          varianceQuantity: 0,
          variance: 0,
          remark: '',
          changeQuantity: 0,
          changeFaceValueTotal: 0,
        })
        added += 1
      }
    }

    // 保留倒轧表中本盘点未覆盖的行
    const syncedIds = new Set(next.map((r) => String(r.id)))
    const syncedNames = new Set(next.map((r) => String(r.securitiesName ?? '').trim()))
    const syncedInvIds = new Set(
      next.map((r) => String(r.inventoryRowId ?? '')).filter(Boolean),
    )
    for (const r of existing) {
      const id = String(r.id ?? '')
      const name = String(r.securitiesName ?? '').trim()
      const iid = String(r.inventoryRowId ?? '')
      if (syncedIds.has(id)) continue
      if (iid && syncedInvIds.has(iid)) continue
      if (name && syncedNames.has(name)) continue
      if (name || parseNum(r.countQuantity) || parseNum(r.bookQuantity)) next.push(r)
    }

    const payload = next.map((r, i) => ({ ...r, seq: i + 1 }))
    persistOut(RECON_KEY_ITEMS, { remark: JSON.stringify(payload) })

    // 同步日期头信息到 G4-8
    const existingHeader = safeParseJson<Record<string, string>>(
      allResponses.value.get(RECON_KEY_HEADER)?.remark,
    ) || {}
    const countDate = normalizeDate(header.value.countDate)
    const balanceSheetDate = effectiveBalanceSheetDate.value
    persistOut(RECON_KEY_HEADER, {
      remark: JSON.stringify({
        ...existingHeader,
        countDate: countDate || existingHeader.countDate || '',
        balanceSheetDate: balanceSheetDate || existingHeader.balanceSheetDate || '',
      }),
    })

    const rollHint = needsRollForward.value
      ? '；盘点日≠报表日，请打开 G4-8 登记增减并完成倒轧'
      : '；请打开 G4-8 核对账面结存'
    ElMessage.success(`已推送至 G4-8：新增 ${added}、更新 ${updated}${rollHint}`)
    return added + updated
  }

  return {
    // 数据
    header,
    items,
    summary,
    headerStatus,
    effectiveBalanceSheetDate,
    needsRollForward,
    validItemCount,
    auditDescription,
    auditConclusion,
    // 操作
    updateHeader,
    regenerateNarrative,
    updateItem,
    addItem,
    removeItem,
    setAuditDescription,
    setAuditConclusion,
    pushToReconciliation,
    // 加载
    loadFromResponses,
    // 持久化
    persistHeader,
    persistItems,
  }
}

export default useG4SppiInventory
