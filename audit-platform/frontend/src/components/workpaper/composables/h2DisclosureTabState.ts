/**
 * H2 在建工程披露 Tab 的表单状态 + 挂载读回 / 自动取数 + 同步载荷（底稿披露 Tab 与附注页离屏同步共用，
 * spec note-pull-followup-closure R1 / ADR-1）。
 *
 * 由 `H2TabDisclosureListed`（上市 五、23）/ `H2TabDisclosureSoe`（国企 八、23）原样抽出：
 * - 表单状态与默认值（汇总 / 明细 / 重要项目 / 减值 / 工程物资 / 抵押 / 附注说明）；
 * - `load`：挂载、回复变化、审定事件时读回已保存的披露表（汇总 / 工程物资按 key 覆盖金额，其余整表替换），返回是否已有数据
 *   （没有 ⇒ Tab 自动「从审定/明细取数」）；
 * - `applySources`：「从审定/明细取数」的计算部分（读 `H2-1-rows` / `H2-2-rows`，只改内存）；
 * - `snapshot` / `syncPayloads`：「同步到附注」的快照与载荷（Tab 不传适用准则 ⇒ 恒适用、单体口径；离屏同参）。
 * Tab 与离屏 provider 调同一份计算 ⇒ 两条路径发出逐字节相同的载荷。保存（防抖 persistAll）、提示、AI、受限资产段
 * （国企 八、93）、事件、路由、「从 H2-2 同步抵押」按钮留在 Tab。
 *
 * 读回时缺行身份的行仍用 `newRowId(前缀)` 补（与原 Tab 同一工厂、同一前缀）；行身份不进载荷。
 */
import { reactive, ref } from 'vue'
import {
  buildH2ListedSyncPayloads,
  buildH2SoeSyncPayloads,
  type H2ListedSyncSnapshot,
  type H2SoeSyncSnapshot,
  type H2SyncFromWorkpaperPayload,
} from './h2DisclosureSyncPayload'
import {
  H2_LISTED_ITEM,
  buildMortgageNoteText,
  createDefaultListedMaterials,
  createDefaultListedSummary,
  createEmptyListedProject,
  listedDetailSubtotal,
  mapDetailToListedDetail,
  mapDetailToListedProjects,
  mapMortgagedDetailToRows,
  newRowId,
  num,
  type ListedDetailRow,
  type ListedImpairmentRow,
  type ListedMaterialRow,
  type ListedMortgageRow,
  type ListedProjectRow,
  type ListedSummaryRow,
} from './h2ListedDisclosureModel'
import {
  H2_SOE_ITEM,
  createDefaultSoeSummary,
  createEmptySoeProject,
  mapDetailToSoeDetail,
  mapDetailToSoeProjects,
  soeDetailSubtotal,
  type SoeDetailRow,
  type SoeImpairmentRow,
  type SoeProjectRow,
  type SoeSummaryRow,
} from './h2SoeDisclosureModel'

/** 宿主下发的 checklist 回复（item_id → { remark, conclusion }） */
export type H2Responses = ReadonlyMap<string, any>

/** 已保存的 JSON 条目（remark 为空 / 解析失败 ⇒ null） */
function parseSaved(responses: H2Responses, itemId: string): any {
  const raw = responses.get(itemId)?.remark
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

function savedText(responses: H2Responses, itemId: string): string {
  return String(responses.get(itemId)?.remark ?? '')
}

/**
 * 「从审定/明细取数」读的两份来源：H2-1 审定表行 `adj` / H2-2 明细表行 `det`（没有或解析失败为 `[]`；解析出非数组时原样返回，
 * 调用方按 `Array.isArray(x) && x.length` 判是否可用）。
 */
export function readH2PullSources(responses: H2Responses): { adj: unknown; det: unknown } {
  const adjRaw = responses.get('H2-1-rows')?.remark
  const detRaw = responses.get('H2-2-rows')?.remark
  let adj: any[] = []
  let det: any[] = []
  try { if (adjRaw) adj = JSON.parse(adjRaw) } catch { /* ignore */ }
  try { if (detRaw) det = JSON.parse(detRaw) } catch { /* ignore */ }
  return { adj, det }
}

/** 上市（五、23）披露 Tab 的状态与计算 */
export function useH2ListedDisclosureState() {
  const summary = reactive<ListedSummaryRow[]>(createDefaultListedSummary())
  const detailRows = ref<ListedDetailRow[]>([])
  const projectRows = ref<ListedProjectRow[]>([])
  const impairmentRows = ref<ListedImpairmentRow[]>([])
  const materials = reactive<ListedMaterialRow[]>(createDefaultListedMaterials())
  const mortgageRows = ref<ListedMortgageRow[]>([])
  const noteImpairment = ref('')
  const noteFundSource = ref('')
  const noteMortgage = ref('')

  /** 读回已保存的披露表；返回是否已有数据（明细 / 重要项目有行，或汇总有金额） */
  function load(responses: H2Responses): boolean {
    const s = parseSaved(responses, H2_LISTED_ITEM.summary)
    if (Array.isArray(s) && s.length) {
      for (const row of s) {
        const t = summary.find((x) => x.key === row.key)
        if (t) {
          t.endBalance = num(row.endBalance)
          t.priorBalance = num(row.priorBalance)
        }
      }
    }
    const d = parseSaved(responses, H2_LISTED_ITEM.detail)
    detailRows.value = Array.isArray(d) ? d.map((r: any) => ({
      rowId: r.rowId || newRowId('det'),
      name: r.name || '',
      endBook: num(r.endBook),
      endImpairment: num(r.endImpairment),
      priorBook: num(r.priorBook),
      priorImpairment: num(r.priorImpairment),
    })) : []
    const p = parseSaved(responses, H2_LISTED_ITEM.projects)
    projectRows.value = Array.isArray(p) ? p.map((r: any) => ({
      ...createEmptyListedProject(),
      ...r,
      rowId: r.rowId || newRowId('proj'),
      beginBalance: num(r.beginBalance),
      increase: num(r.increase),
      transferToFA: num(r.transferToFA),
      otherDecrease: num(r.otherDecrease),
      interestCapAccum: num(r.interestCapAccum),
      interestCapCurrent: num(r.interestCapCurrent),
      interestCapRate: num(r.interestCapRate),
      budget: num(r.budget),
      cumInputPct: num(r.cumInputPct),
      accumulatedInput: num(r.accumulatedInput),
    })) : []
    const i = parseSaved(responses, H2_LISTED_ITEM.impairment)
    impairmentRows.value = Array.isArray(i) ? i.map((r: any) => ({
      rowId: r.rowId || newRowId('imp'),
      name: r.name || '',
      beginBalance: num(r.beginBalance),
      provision: num(r.provision),
      decrease: num(r.decrease),
    })) : []
    const m = parseSaved(responses, H2_LISTED_ITEM.materials)
    if (Array.isArray(m) && m.length) {
      for (const row of m) {
        const t = materials.find((x) => x.key === row.key)
        if (t) {
          t.endBalance = num(row.endBalance)
          t.priorBalance = num(row.priorBalance)
        }
      }
    }
    noteImpairment.value = savedText(responses, H2_LISTED_ITEM.noteImpairment)
    noteFundSource.value = savedText(responses, H2_LISTED_ITEM.noteFundSource)
    noteMortgage.value = savedText(responses, H2_LISTED_ITEM.noteMortgage)
    const mort = parseSaved(responses, H2_LISTED_ITEM.mortgageRows)
    mortgageRows.value = Array.isArray(mort) ? mort.map((r: any, i: number) => ({
      rowId: r.rowId || newRowId(`mort-${i}`),
      name: r.name || '',
      amount: num(r.amount),
      description: r.description || '',
      remark: r.remark || '',
    })) : []

    const hasData = detailRows.value.length || projectRows.value.length
      || summary.some((r) => r.endBalance || r.priorBalance)
    return Boolean(hasData)
  }

  /** 「从审定/明细取数」的计算部分：明细 / 重要项目 / 抵押取 H2-2，汇总在建工程行取 H2-1（没有则取明细合计） */
  function applySources(responses: H2Responses): void {
    const { adj, det } = readH2PullSources(responses)

    if (Array.isArray(det) && det.length) {
      detailRows.value = mapDetailToListedDetail(det)
      projectRows.value = mapDetailToListedProjects(det)
      // 自动带入抵押（不覆盖已有手工编辑行时若为空则填充）
      if (!mortgageRows.value.length) {
        const morts = mapMortgagedDetailToRows(det)
        if (morts.length) {
          mortgageRows.value = morts
          if (!noteMortgage.value.trim()) noteMortgage.value = buildMortgageNoteText(morts)
        }
      }
    }

    if (Array.isArray(adj) && adj.length) {
      const cipBegin = adj.reduce((s, r) => s + num(r.cipBegin), 0)
      const cipEnd = adj.reduce((s, r) => s + num(r.cipEnd ?? r.audited), 0)
      const impair = adj.reduce((s, r) => s + num(r.impairment), 0)
      const cip = summary.find((r) => r.key === 'cip')
      if (cip) {
        cip.endBalance = cipEnd - impair
        cip.priorBalance = cipBegin
      }
    } else if (detailRows.value.length) {
      const tot = listedDetailSubtotal(detailRows.value)
      const cip = summary.find((r) => r.key === 'cip')
      if (cip) {
        cip.endBalance = tot.endNet
        cip.priorBalance = tot.priorNet
      }
    }
  }

  function snapshot(): H2ListedSyncSnapshot {
    return {
      summary: summary.map((r) => ({ ...r })),
      detail: detailRows.value,
      projects: projectRows.value,
      impairment: impairmentRows.value,
      materials: materials.map((r) => ({ ...r })),
      mortgage: mortgageRows.value,
      noteImpairment: noteImpairment.value,
      noteFundSource: noteFundSource.value,
      noteMortgage: noteMortgage.value,
    }
  }

  /** 「同步到附注」的载荷（五、23 一条）：Tab 不传适用准则，离屏同参 */
  function syncPayloads(wpId: string): H2SyncFromWorkpaperPayload[] {
    return buildH2ListedSyncPayloads(wpId, [], snapshot())
  }

  return {
    summary,
    detailRows,
    projectRows,
    impairmentRows,
    materials,
    mortgageRows,
    noteImpairment,
    noteFundSource,
    noteMortgage,
    load,
    applySources,
    snapshot,
    syncPayloads,
  }
}

/** 国企（八、23）披露 Tab 的状态与计算 */
export function useH2SoeDisclosureState() {
  const summary = reactive<SoeSummaryRow[]>(createDefaultSoeSummary())
  const detailRows = ref<SoeDetailRow[]>([])
  const projectRows = ref<SoeProjectRow[]>([])
  const impairmentRows = ref<SoeImpairmentRow[]>([])
  const noteImpairment = ref('')

  /** 读回已保存的披露表；返回是否已有数据（明细 / 重要项目有行，或汇总有账面余额） */
  function load(responses: H2Responses): boolean {
    const s = parseSaved(responses, H2_SOE_ITEM.summary)
    if (Array.isArray(s) && s.length) {
      for (const row of s) {
        const t = summary.find((x) => x.key === row.key)
        if (t) {
          t.endBook = num(row.endBook)
          t.endImpairment = num(row.endImpairment)
          t.beginBook = num(row.beginBook)
          t.beginImpairment = num(row.beginImpairment)
        }
      }
    }
    const d = parseSaved(responses, H2_SOE_ITEM.detail)
    detailRows.value = Array.isArray(d) ? d.map((r: any) => ({
      rowId: r.rowId || newRowId('soe-det'),
      name: r.name || '',
      endBook: num(r.endBook),
      endImpairment: num(r.endImpairment),
      beginBook: num(r.beginBook),
      beginImpairment: num(r.beginImpairment),
    })) : []
    const p = parseSaved(responses, H2_SOE_ITEM.projects)
    projectRows.value = Array.isArray(p) ? p.map((r: any) => ({
      ...createEmptySoeProject(),
      ...r,
      rowId: r.rowId || newRowId('soe-proj'),
      beginBalance: num(r.beginBalance),
      increase: num(r.increase),
      transferToFA: num(r.transferToFA),
      otherDecrease: num(r.otherDecrease),
      interestCapAccum: num(r.interestCapAccum),
      interestCapCurrent: num(r.interestCapCurrent),
      interestCapRate: num(r.interestCapRate),
      budget: num(r.budget),
      cumInputPct: num(r.cumInputPct),
      accumulatedInput: num(r.accumulatedInput),
    })) : []
    const i = parseSaved(responses, H2_SOE_ITEM.impairment)
    impairmentRows.value = Array.isArray(i) ? i.map((r: any) => ({
      rowId: r.rowId || newRowId('soe-imp'),
      name: r.name || '',
      provisionAmount: num(r.provisionAmount),
      reason: r.reason || '',
    })) : []
    noteImpairment.value = savedText(responses, H2_SOE_ITEM.noteImpairment)

    const hasData = detailRows.value.length || projectRows.value.length
      || summary.some((r) => r.endBook || r.beginBook)
    return Boolean(hasData)
  }

  /** 「从审定/明细取数」的计算部分：明细 / 重要项目取 H2-2，汇总在建工程行取 H2-1（没有则取明细合计） */
  function applySources(responses: H2Responses): void {
    const { adj, det } = readH2PullSources(responses)

    if (Array.isArray(det) && det.length) {
      detailRows.value = mapDetailToSoeDetail(det)
      projectRows.value = mapDetailToSoeProjects(det)
    }

    if (Array.isArray(adj) && adj.length) {
      const cipBegin = adj.reduce((s, r) => s + num(r.cipBegin), 0)
      const cipEnd = adj.reduce((s, r) => s + num(r.cipEnd ?? r.audited), 0)
      const impair = adj.reduce((s, r) => s + num(r.impairment), 0)
      const cip = summary.find((r) => r.key === 'cip')
      if (cip) {
        cip.endBook = cipEnd
        cip.endImpairment = impair
        cip.beginBook = cipBegin
        cip.beginImpairment = 0
      }
    } else if (detailRows.value.length) {
      const tot = soeDetailSubtotal(detailRows.value)
      const cip = summary.find((r) => r.key === 'cip')
      if (cip) {
        cip.endBook = tot.endBook
        cip.endImpairment = tot.endImpairment
        cip.beginBook = tot.beginBook
        cip.beginImpairment = tot.beginImpairment
      }
    }
  }

  function snapshot(): H2SoeSyncSnapshot {
    return {
      summary: summary.map((r) => ({ ...r })),
      detail: detailRows.value,
      projects: projectRows.value,
      impairment: impairmentRows.value,
      noteImpairment: noteImpairment.value,
    }
  }

  /** 「同步到附注」的载荷（八、23 一条）：Tab 不传适用准则，离屏同参 */
  function syncPayloads(wpId: string): H2SyncFromWorkpaperPayload[] {
    return buildH2SoeSyncPayloads(wpId, [], snapshot())
  }

  return {
    summary,
    detailRows,
    projectRows,
    impairmentRows,
    noteImpairment,
    load,
    applySources,
    snapshot,
    syncPayloads,
  }
}

export type H2ListedDisclosureState = ReturnType<typeof useH2ListedDisclosureState>
export type H2SoeDisclosureState = ReturnType<typeof useH2SoeDisclosureState>
