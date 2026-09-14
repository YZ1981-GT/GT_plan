/**
 * useH3Adjustment — H3-3 调整分录 composable
 *
 * 按资产类别分摊 AJE/RJE 到 H3-1：原值/公允、累计折旧摊销、减值准备三个区块。
 *
 * 🔴 **2026-08-06 修**：桶键与判定函数原名 `aje1503`/`isH31503`，且判定按
 * `code.startsWith('1503'|'1504'|'1505')` —— 那三个码分别是
 * **可供出售金融资产（G6 域）/ 债权投资（G4 域）/ 债权投资减值准备**，
 * 投资性房地产真实科目族是 `1521`/`1525`/`1526`/`1527`（后端
 * `four_table/h3_account_scope.py` 已于 2026-08-01 纠正）。
 * 旧判定靠**名称正则**碰巧还能分对大部分行，但：
 *   - G6 的「可供出售金融资产」调整分录会被 `startsWith('1503')` 误判进 H3 原值桶；
 *   - 真正的 `1525 投资性房地产累计折旧` 只能靠名称命中，改名即失配。
 * 现改为「本循环正确科目族前缀 ∪ 名称关键字」，并把误伤前缀移除。
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistItem } from './useH3FormData'
import { calcAuditedAmount, calcSubtotal } from './useH3FormulaEngine'
import {
  H3_ASSET_CATEGORIES,
  emptyCategoryAmountMap,
  inferH3CategoryFromAdjustment,
  normalizeH3Category,
  type H3AssetCategory,
} from './h3CategoryMap'
import { H3_FALLBACK_CODES } from './h3AccountScope'

export interface H3AdjustmentRow {
  rowId: string
  seq: number
  description: string
  entryType: 'AJE' | 'RJE' | ''
  category: string
  accountCode: string
  accountName: string
  summary: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
}

export interface H3CategoryAdjBucket {
  ajeGross: Record<H3AssetCategory, number>
  rjeGross: Record<H3AssetCategory, number>
  ajeAccumDep: Record<H3AssetCategory, number>
  rjeAccumDep: Record<H3AssetCategory, number>
  ajeImpairment: Record<H3AssetCategory, number>
  rjeImpairment: Record<H3AssetCategory, number>
}

export interface H3SyncWriteTarget {
  key: string
  label: string
  itemId: string
  exists: boolean
  aje: number
  rje: number
}

const ITEM_ID = 'H3-3-adj-rows'

/**
 * 科目码前缀边界匹配 —— `1521` 不得误命中 `15210`（不同科目）。
 * 只认「逐字相等」或「后跟点号/横杠的子科目」。
 */
function _codeInFamily(code: string, prefixes: readonly string[]): boolean {
  const c = String(code || '').trim()
  if (!c) return false
  return prefixes.some((p) => c === p || c.startsWith(`${p}.`) || c.startsWith(`${p}-`))
}

/** 累计折旧（1525）与累计摊销（1526，土地使用权走摊销） */
export function isH3AccumDepSubject(code: string, name: string): boolean {
  return (
    _codeInFamily(code, [H3_FALLBACK_CODES.accumDep, H3_FALLBACK_CODES.accumAmort])
    || /累计折旧|累计摊销/.test(name)
  )
}

/** 减值准备（1527） */
export function isH3ImpairmentSubject(code: string, name: string): boolean {
  return _codeInFamily(code, [H3_FALLBACK_CODES.impairment]) || /减值准备/.test(name)
}

/**
 * 原值 / 公允价值（1521）。
 *
 * 名称侧必须叠否决词 —— `投资性房地产累计折旧` **包含** `投资性房地产`，
 * 无否决词时原值桶会把三个备抵桶一并吃掉（与后端 `_GROSS_EXCLUDES` 同款理由）。
 * 调用顺序上备抵判定在前，此处否决词是双保险。
 */
export function isH3GrossSubject(code: string, name: string): boolean {
  if (/累计折旧|累计摊销|减值准备/.test(name)) return false
  return _codeInFamily(code, [H3_FALLBACK_CODES.gross]) || /投资性房地产/.test(name)
}

function _sumMap(m: Record<H3AssetCategory, number>): number {
  return H3_ASSET_CATEGORIES.reduce((s, c) => s + (m[c] || 0), 0)
}

/** 按分类写入 AJE/RJE；缺行金额并入「其他」 */
export function applyAdjToRows(
  rows: any[],
  ajeMap: Record<H3AssetCategory, number>,
  rjeMap: Record<H3AssetCategory, number>,
): any[] {
  const used = new Set<H3AssetCategory>()
  const next = rows.map((r) => {
    const cat = normalizeH3Category(r.category)
    used.add(cat)
    const aje = ajeMap[cat] || 0
    const rje = rjeMap[cat] || 0
    const unadj = Number(r.unadjusted) || 0
    return {
      ...r,
      category: r.category || cat,
      aje,
      rje,
      audited: calcAuditedAmount(unadj, aje, rje),
    }
  })

  let orphanAje = 0
  let orphanRje = 0
  for (const cat of H3_ASSET_CATEGORIES) {
    if (!used.has(cat)) {
      orphanAje += ajeMap[cat] || 0
      orphanRje += rjeMap[cat] || 0
    }
  }
  if ((orphanAje || orphanRje) && next.length) {
    const otherIdx = next.findIndex((r) => normalizeH3Category(r.category) === '其他')
    const idx = otherIdx >= 0 ? otherIdx : 0
    next[idx].aje = (Number(next[idx].aje) || 0) + orphanAje
    next[idx].rje = (Number(next[idx].rje) || 0) + orphanRje
    next[idx].audited = calcAuditedAmount(
      Number(next[idx].unadjusted) || 0,
      Number(next[idx].aje) || 0,
      Number(next[idx].rje) || 0,
    )
  }
  return next
}

export function buildCategoryBuckets(rows: H3AdjustmentRow[]): H3CategoryAdjBucket {
  const bucket: H3CategoryAdjBucket = {
    ajeGross: emptyCategoryAmountMap(),
    rjeGross: emptyCategoryAmountMap(),
    ajeAccumDep: emptyCategoryAmountMap(),
    rjeAccumDep: emptyCategoryAmountMap(),
    ajeImpairment: emptyCategoryAmountMap(),
    rjeImpairment: emptyCategoryAmountMap(),
  }
  for (const row of rows) {
    const net = (Number(row.debitAmount) || 0) - (Number(row.creditAmount) || 0)
    const cat = inferH3CategoryFromAdjustment(row)
    const isRje = row.entryType === 'RJE'
    const code = row.accountCode
    const name = row.accountName
    if (isH3ImpairmentSubject(code, name)) {
      if (isRje) bucket.rjeImpairment[cat] += net
      else bucket.ajeImpairment[cat] += net
    } else if (isH3AccumDepSubject(code, name)) {
      if (isRje) bucket.rjeAccumDep[cat] += net
      else bucket.ajeAccumDep[cat] += net
    } else if (isH3GrossSubject(code, name) || !!code) {
      if (isRje) bucket.rjeGross[cat] += net
      else bucket.ajeGross[cat] += net
    }
  }
  return bucket
}

export function useH3Adjustment(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params
  const rows = ref<H3AdjustmentRow[]>([])

  function loadRows(): void {
    const raw = getValue(ITEM_ID)
    rows.value = Array.isArray(raw) ? raw.map(_normalize) : []
  }

  function _normalize(raw: any, idx?: number): H3AdjustmentRow {
    const category = raw.category
      ? normalizeH3Category(raw.category)
      : inferH3CategoryFromAdjustment(raw)
    return {
      rowId: raw.rowId ?? `adj-${Math.random().toString(36).slice(2, 8)}`,
      seq: raw.seq ?? (idx != null ? idx + 1 : 1),
      description: raw.description ?? '',
      entryType: raw.entryType ?? '',
      category,
      accountCode: raw.accountCode ?? '',
      accountName: raw.accountName ?? '',
      summary: raw.summary ?? '',
      debitAmount: Number(raw.debitAmount) || 0,
      creditAmount: Number(raw.creditAmount) || 0,
      indexRef: raw.indexRef ?? '',
      remark: raw.remark ?? '',
    }
  }

  const debitTotal = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
  const creditTotal = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
  const balanced = computed(() => Math.abs(debitTotal.value - creditTotal.value) < 0.01)

  const categoryBuckets = computed(() => buildCategoryBuckets(rows.value))

  const syncSummary = computed(() => {
    const b = categoryBuckets.value
    return {
      ajeGross: _sumMap(b.ajeGross),
      rjeGross: _sumMap(b.rjeGross),
      ajeAccumDep: _sumMap(b.ajeAccumDep),
      rjeAccumDep: _sumMap(b.rjeAccumDep),
      ajeImpairment: _sumMap(b.ajeImpairment),
      rjeImpairment: _sumMap(b.rjeImpairment),
      totalAje: _sumMap(b.ajeGross) + _sumMap(b.ajeAccumDep) + _sumMap(b.ajeImpairment),
      totalRje: _sumMap(b.rjeGross) + _sumMap(b.rjeAccumDep) + _sumMap(b.rjeImpairment),
      byCategory: b,
    }
  })

  /** 发布目标：各 H3-1 区块是否存在及将写入金额 */
  const writeTargets = computed<H3SyncWriteTarget[]>(() => {
    const b = categoryBuckets.value
    const has = (id: string) => {
      const v = getValue(id)
      return Array.isArray(v) && v.length > 0
    }
    return [
      {
        key: 'cost-original',
        label: 'H3-1 成本·原值（1521）',
        itemId: 'H3-1-cost-original-rows',
        exists: has('H3-1-cost-original-rows'),
        aje: _sumMap(b.ajeGross),
        rje: _sumMap(b.rjeGross),
      },
      {
        key: 'cost-dep',
        label: 'H3-1 成本·累计折旧摊销（1525/1526）',
        itemId: 'H3-1-cost-dep-rows',
        exists: has('H3-1-cost-dep-rows'),
        aje: _sumMap(b.ajeAccumDep),
        rje: _sumMap(b.rjeAccumDep),
      },
      {
        key: 'cost-impair',
        label: 'H3-1 成本·减值准备（1527）',
        itemId: 'H3-1-cost-impair-rows',
        exists: has('H3-1-cost-impair-rows'),
        aje: _sumMap(b.ajeImpairment),
        rje: _sumMap(b.rjeImpairment),
      },
      {
        key: 'fair',
        label: 'H3-1 公允·资产（1521）',
        itemId: 'H3-1-fair-rows',
        exists: has('H3-1-fair-rows'),
        aje: _sumMap(b.ajeGross),
        rje: _sumMap(b.rjeGross),
      },
    ]
  })

  function addRow(): void {
    rows.value.push(_normalize({ seq: rows.value.length + 1, entryType: 'AJE', category: '其他' }))
    _persist()
  }

  function removeRow(index: number): void {
    rows.value.splice(index, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
  }

  function updateCell(index: number, field: keyof H3AdjustmentRow, value: any): void {
    const row = rows.value[index]
    if (!row) return
    if (field === 'category') {
      row.category = normalizeH3Category(String(value))
    } else {
      ;(row as any)[field] = value
    }
    _persist()
  }

  function syncToH31(): { cost: boolean; fair: boolean; impair: boolean } {
    const b = categoryBuckets.value
    let cost = false
    let fair = false
    let impair = false

    const ensureThreeCats = (raw: any[] | undefined, kind: 'orig' | 'dep' | 'imp') => {
      const base = Array.isArray(raw) && raw.length ? [...raw] : []
      const have = new Set(base.map((r) => normalizeH3Category(r.category)))
      for (const cat of H3_ASSET_CATEGORIES) {
        if (!have.has(cat)) {
          base.push({
            rowId: `${kind}-${cat}`,
            category: cat,
            beginBalance: 0,
            increase: 0,
            decrease: 0,
            provision: 0,
            reversal: 0,
            transfer: 0,
            transferDep: 0,
            transferImp: 0,
            endBalance: 0,
            unadjusted: 0,
            aje: 0,
            rje: 0,
            audited: 0,
          })
        }
      }
      return base
    }

    const needGross = _sumMap(b.ajeGross) || _sumMap(b.rjeGross)
    const needAccumDep = _sumMap(b.ajeAccumDep) || _sumMap(b.rjeAccumDep)
    const needImpairment = _sumMap(b.ajeImpairment) || _sumMap(b.rjeImpairment)

    const orig = getValue('H3-1-cost-original-rows')
    if ((Array.isArray(orig) && orig.length > 0) || needGross) {
      setValue('H3-1-cost-original-rows', applyAdjToRows(ensureThreeCats(orig, 'orig'), b.ajeGross, b.rjeGross))
      cost = true
    }

    const dep = getValue('H3-1-cost-dep-rows')
    if ((Array.isArray(dep) && dep.length > 0) || needAccumDep) {
      setValue('H3-1-cost-dep-rows', applyAdjToRows(ensureThreeCats(dep, 'dep'), b.ajeAccumDep, b.rjeAccumDep))
      cost = true
    }

    const imp = getValue('H3-1-cost-impair-rows')
    if ((Array.isArray(imp) && imp.length > 0) || needImpairment) {
      setValue('H3-1-cost-impair-rows', applyAdjToRows(ensureThreeCats(imp, 'imp'), b.ajeImpairment, b.rjeImpairment))
      impair = true
      cost = true
    }

    const fairRows = getValue('H3-1-fair-rows')
    if ((Array.isArray(fairRows) && fairRows.length > 0) || needGross) {
      // 公允模式仅在已有公允行或仅有公允底稿时写入；若同时有成本行，成本优先已写原值桶
      if (Array.isArray(fairRows) && fairRows.length > 0) {
        setValue('H3-1-fair-rows', applyAdjToRows(ensureThreeCats(fairRows, 'orig'), b.ajeGross, b.rjeGross))
        fair = true
      }
    }

    setValue('H3-3-sync-summary', syncSummary.value)
    return { cost, fair, impair }
  }

  function publishAdjustment(): boolean {
    if (!balanced.value) {
      ElMessage.warning('借贷不平衡，无法发布至 H3-1')
      return false
    }
    const result = syncToH31()
    const payload = {
      wpCode: 'H3',
      wp_code: 'H3',
      rows: rows.value,
      debitTotal: debitTotal.value,
      creditTotal: creditTotal.value,
      sync: syncSummary.value,
      writeTargets: writeTargets.value,
      timestamp: Date.now(),
    }
    try {
      eventBus.emit('adjustment:created', payload as any)
    } catch { /* best effort */ }
    window.dispatchEvent(new CustomEvent('adjustment:created', { detail: payload }))

    if (result.cost || result.fair) {
      const parts = writeTargets.value
        .filter((t) => t.exists && (Math.abs(t.aje) >= 0.01 || Math.abs(t.rje) >= 0.01))
        .map((t) => t.label)
      ElMessage.success(
        `已按分类分摊发布至 H3-1${parts.length ? `：${parts.join('、')}` : ''}（AJE ${syncSummary.value.totalAje.toLocaleString('zh-CN')} / RJE ${syncSummary.value.totalRje.toLocaleString('zh-CN')}）`,
      )
      return true
    }
    ElMessage.warning('已发布事件，但 H3-1 尚无审定行可写入，请先编制 H3-1')
    return false
  }

  function pushToA13(rowIds?: string[]): void {
    const targets = rowIds
      ? rows.value.filter((r) => rowIds.includes(r.rowId))
      : rows.value
    const payload = { wpCode: 'H3', wp_code: 'H3', entries: targets, items: targets, timestamp: Date.now() }
    try {
      eventBus.emit('a13:push-misstatement', payload as any)
    } catch { /* best effort */ }
    window.dispatchEvent(new CustomEvent('a13:push-misstatement', { detail: payload }))
    window.dispatchEvent(new CustomEvent('adjustment:push-to-a13', { detail: payload }))
    ElMessage.success(`已推送 ${targets.length} 笔至 A13`)
  }

  function _persist(): void { setValue(ITEM_ID, rows.value) }
  watch(allResponses, () => loadRows(), { immediate: true })

  return {
    rows,
    debitTotal,
    creditTotal,
    isBalanced: balanced,
    syncSummary,
    categoryBuckets,
    writeTargets,
    addRow,
    removeRow,
    updateCell,
    publishAdjustment,
    pushToA13,
    syncToH31,
  }
}

export default useH3Adjustment
