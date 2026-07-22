/**
 * useH3Adjustment — H3-3 调整分录 composable
 *
 * 按资产类别分摊 AJE/RJE 到 H3-1：1503 原值/公允、1504 折旧、1505 减值
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
  aje1503: Record<H3AssetCategory, number>
  rje1503: Record<H3AssetCategory, number>
  aje1504: Record<H3AssetCategory, number>
  rje1504: Record<H3AssetCategory, number>
  aje1505: Record<H3AssetCategory, number>
  rje1505: Record<H3AssetCategory, number>
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

export function isH31504(code: string, name: string): boolean {
  return code.startsWith('1504') || /累计折旧|累计摊销/.test(name)
}

export function isH31505(code: string, name: string): boolean {
  return code.startsWith('1505') || /减值准备/.test(name)
}

export function isH31503(code: string, name: string): boolean {
  return code.startsWith('1503') || /投资性房地产/.test(name)
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
    aje1503: emptyCategoryAmountMap(),
    rje1503: emptyCategoryAmountMap(),
    aje1504: emptyCategoryAmountMap(),
    rje1504: emptyCategoryAmountMap(),
    aje1505: emptyCategoryAmountMap(),
    rje1505: emptyCategoryAmountMap(),
  }
  for (const row of rows) {
    const net = (Number(row.debitAmount) || 0) - (Number(row.creditAmount) || 0)
    const cat = inferH3CategoryFromAdjustment(row)
    const isRje = row.entryType === 'RJE'
    const code = row.accountCode
    const name = row.accountName
    if (isH31505(code, name)) {
      if (isRje) bucket.rje1505[cat] += net
      else bucket.aje1505[cat] += net
    } else if (isH31504(code, name)) {
      if (isRje) bucket.rje1504[cat] += net
      else bucket.aje1504[cat] += net
    } else if (isH31503(code, name) || !!code) {
      if (isRje) bucket.rje1503[cat] += net
      else bucket.aje1503[cat] += net
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
      aje1503: _sumMap(b.aje1503),
      rje1503: _sumMap(b.rje1503),
      aje1504: _sumMap(b.aje1504),
      rje1504: _sumMap(b.rje1504),
      aje1505: _sumMap(b.aje1505),
      rje1505: _sumMap(b.rje1505),
      totalAje: _sumMap(b.aje1503) + _sumMap(b.aje1504) + _sumMap(b.aje1505),
      totalRje: _sumMap(b.rje1503) + _sumMap(b.rje1504) + _sumMap(b.rje1505),
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
        label: 'H3-1 成本·原值（1503）',
        itemId: 'H3-1-cost-original-rows',
        exists: has('H3-1-cost-original-rows'),
        aje: _sumMap(b.aje1503),
        rje: _sumMap(b.rje1503),
      },
      {
        key: 'cost-dep',
        label: 'H3-1 成本·累计折旧（1504）',
        itemId: 'H3-1-cost-dep-rows',
        exists: has('H3-1-cost-dep-rows'),
        aje: _sumMap(b.aje1504),
        rje: _sumMap(b.rje1504),
      },
      {
        key: 'cost-impair',
        label: 'H3-1 成本·减值准备（1505）',
        itemId: 'H3-1-cost-impair-rows',
        exists: has('H3-1-cost-impair-rows'),
        aje: _sumMap(b.aje1505),
        rje: _sumMap(b.rje1505),
      },
      {
        key: 'fair',
        label: 'H3-1 公允·资产（1503）',
        itemId: 'H3-1-fair-rows',
        exists: has('H3-1-fair-rows'),
        aje: _sumMap(b.aje1503),
        rje: _sumMap(b.rje1503),
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

    const need1503 = _sumMap(b.aje1503) || _sumMap(b.rje1503)
    const need1504 = _sumMap(b.aje1504) || _sumMap(b.rje1504)
    const need1505 = _sumMap(b.aje1505) || _sumMap(b.rje1505)

    const orig = getValue('H3-1-cost-original-rows')
    if ((Array.isArray(orig) && orig.length > 0) || need1503) {
      setValue('H3-1-cost-original-rows', applyAdjToRows(ensureThreeCats(orig, 'orig'), b.aje1503, b.rje1503))
      cost = true
    }

    const dep = getValue('H3-1-cost-dep-rows')
    if ((Array.isArray(dep) && dep.length > 0) || need1504) {
      setValue('H3-1-cost-dep-rows', applyAdjToRows(ensureThreeCats(dep, 'dep'), b.aje1504, b.rje1504))
      cost = true
    }

    const imp = getValue('H3-1-cost-impair-rows')
    if ((Array.isArray(imp) && imp.length > 0) || need1505) {
      setValue('H3-1-cost-impair-rows', applyAdjToRows(ensureThreeCats(imp, 'imp'), b.aje1505, b.rje1505))
      impair = true
      cost = true
    }

    const fairRows = getValue('H3-1-fair-rows')
    if ((Array.isArray(fairRows) && fairRows.length > 0) || need1503) {
      // 公允模式仅在已有公允行或仅有公允底稿时写入；若同时有成本行，成本优先已写 1503
      if (Array.isArray(fairRows) && fairRows.length > 0) {
        setValue('H3-1-fair-rows', applyAdjToRows(ensureThreeCats(fairRows, 'orig'), b.aje1503, b.rje1503))
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
