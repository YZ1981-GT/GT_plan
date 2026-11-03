/**
 * H4 工程物资披露表的状态 / 读回 / 取数 / 快照（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1）。
 *
 * 两个 Tab（`H4TabDisclosureListed` / `H4TabDisclosureSoe`）原在组件内联持有表单状态、挂载时 `load`（无数据则从来源取数、
 * 国企另回放 H2 在建工程审定缓存）与「同步到附注」的快照，原样抽到这里。`onChange` = Tab 的防抖保存（离屏传空函数，
 * 不写底稿）；界面提示留在 Tab。
 */
import { reactive, ref } from 'vue'
import {
  H4_LISTED_ITEM,
  createDefaultH4ListedMaterials,
  num,
  type H4ListedMaterialRow,
} from './h4ListedDisclosureModel'
import {
  H4_SOE_ITEM,
  createDefaultH4SoeSummary,
  type H4SoeSummaryRow,
} from './h4SoeDisclosureModel'
import { readH2CipSnapshot, type H2CipAdjudicatedSnapshot } from './h2CipBridge'
import type { H4ListedSyncSnapshot } from './h4DisclosureSyncPayload'
import type { H4SoeSyncSnapshot } from './h4SoeDisclosureSyncPayload'
import type { useH4Disclosure } from './useH4Disclosure'

type ResponseMap = ReadonlyMap<string, { remark?: string | null } | undefined>
type H4DisclosureApi = ReturnType<typeof useH4Disclosure>

function parseJson(responses: ResponseMap, itemId: string): any {
  const raw = responses.get(itemId)?.remark
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

/** 上市：（2）工程物资分类表 */
export function useH4ListedDisclosureForm(opts: {
  disclosure: Pick<H4DisclosureApi, 'pullListedMaterials' | 'significantNoteDraft'>
  onChange: () => void
}) {
  const materials = reactive<H4ListedMaterialRow[]>(createDefaultH4ListedMaterials())
  const noteText = ref('')

  function applyMaterials(src: H4ListedMaterialRow[]) {
    const byKey = new Map(src.map((r) => [r.key, r]))
    for (const row of materials) {
      const s = byKey.get(row.key)
      if (!s) continue
      row.endBalance = num(s.endBalance)
      row.priorBalance = num(s.priorBalance)
    }
  }

  /** 从 H4-2 分类明细及 H4-7 减值取数（附注说明为空时带入重大变动摘要） */
  function pullFromSources(): void {
    applyMaterials(opts.disclosure.pullListedMaterials())
    if (!noteText.value.trim() && opts.disclosure.significantNoteDraft.value) {
      noteText.value = opts.disclosure.significantNoteDraft.value
    }
    opts.onChange()
  }

  /** 读回已存的分类表与说明；返回分类表是否有数（没有 ⇒ 挂载要从来源取数） */
  function readBack(responses: ResponseMap): boolean {
    const saved = parseJson(responses, H4_LISTED_ITEM.materials)
    if (Array.isArray(saved) && saved.length) {
      applyMaterials(saved.map((r: any) => ({
        key: r.key,
        label: r.label,
        endBalance: num(r.endBalance),
        priorBalance: num(r.priorBalance),
        isDeduction: !!r.isDeduction,
      })))
    }
    noteText.value = String(responses.get(H4_LISTED_ITEM.noteText)?.remark ?? '')
    return materials.some((r) => r.endBalance || r.priorBalance)
  }

  /** Tab 挂载时读回；分类表全空则从来源取数 */
  function load(responses: ResponseMap): void {
    if (!readBack(responses)) pullFromSources()
  }

  function snapshot(): H4ListedSyncSnapshot {
    return { materials: [...materials], noteText: noteText.value }
  }

  return { materials, noteText, pullFromSources, readBack, load, snapshot }
}

/** 国企：23、在建工程汇总（工程物资行取自 H4-1；在建工程行可回放 H2 审定缓存） */
export function useH4SoeDisclosureForm(opts: {
  disclosure: Pick<H4DisclosureApi, 'pullSoeSummary' | 'significantNoteDraft'>
  onChange: () => void
}) {
  const summary = reactive<H4SoeSummaryRow[]>(createDefaultH4SoeSummary())
  const noteText = ref('')

  function cipRowEmpty(): boolean {
    const cip = summary.find((r) => r.key === 'cip')
    if (!cip) return true
    return !num(cip.endBook) && !num(cip.beginBook) && !num(cip.endImpairment) && !num(cip.beginImpairment)
  }

  /** 写入 H2 在建工程审定快照（`force=false` 时不覆盖已有数据）；返回是否写入 */
  function applyCipSnapshot(snap: H2CipAdjudicatedSnapshot, force: boolean): boolean {
    const cip = summary.find((r) => r.key === 'cip')
    if (!cip) return false
    if (!force && !cipRowEmpty()) return false
    cip.endBook = snap.endBook
    cip.endImpairment = snap.endImpairment
    cip.beginBook = snap.beginBook
    cip.beginImpairment = snap.beginImpairment
    opts.onChange()
    return true
  }

  /** 从 H4-1 审定同步工程物资行（附注说明为空时带入重大变动摘要） */
  function pullFromSources(): void {
    const next = opts.disclosure.pullSoeSummary(summary.map((r) => ({ ...r })))
    for (const row of next) {
      const t = summary.find((x) => x.key === row.key)
      if (!t) continue
      t.endBook = row.endBook
      t.endImpairment = row.endImpairment
      t.beginBook = row.beginBook
      t.beginImpairment = row.beginImpairment
    }
    if (!noteText.value.trim() && opts.disclosure.significantNoteDraft.value) {
      noteText.value = opts.disclosure.significantNoteDraft.value
    }
    opts.onChange()
  }

  /** Tab 挂载时读回；工程物资行全空则从 H4-1 取数；在建工程行为空时回放本会话的 H2 审定缓存 */
  function load(responses: ResponseMap, projectId: string): void {
    const saved = parseJson(responses, H4_SOE_ITEM.summary)
    if (Array.isArray(saved) && saved.length) {
      for (const row of saved) {
        const t = summary.find((x) => x.key === row.key)
        if (!t) continue
        t.endBook = num(row.endBook)
        t.endImpairment = num(row.endImpairment)
        t.beginBook = num(row.beginBook)
        t.beginImpairment = num(row.beginImpairment)
      }
    }
    noteText.value = String(responses.get(H4_SOE_ITEM.noteText)?.remark ?? '')
    const hasMat = summary.some((r) => r.key === 'materials' && (r.endBook || r.beginBook || r.endImpairment))
    if (!hasMat) pullFromSources()
    if (cipRowEmpty() && projectId) {
      const cached = readH2CipSnapshot(projectId)
      if (cached) applyCipSnapshot(cached, false)
    }
  }

  function snapshot(): H4SoeSyncSnapshot {
    return { summary: summary.map((r) => ({ ...r })), noteText: noteText.value }
  }

  return { summary, noteText, applyCipSnapshot, pullFromSources, load, snapshot }
}
