/**
 * useB19RelatedParty — B19 识别关联方 数据层
 *
 * 三块数据：
 * 1. 管理层关联方清单  → related_party_registry（eqcr CRUD，全平台各循环关联方核对的唯一真源）
 * 2. 关联方交易台账    → related_party_transactions（eqcr CRUD）
 * 3. 未披露关联方扫描  → checklist_responses（item_id 前缀 b19u-），异常项推送 B50 风险因素
 *
 * 后端 API（已存在，列名 name/relation_type/is_controlled_by_same_party 正确）：
 *   GET/POST  /api/eqcr/projects/{pid}/related-parties
 *   PATCH/DEL /api/eqcr/projects/{pid}/related-parties/{id}
 *   POST      /api/eqcr/projects/{pid}/related-party-transactions
 *   PATCH/DEL /api/eqcr/projects/{pid}/related-party-transactions/{id}
 *   GET/PUT   /api/workpapers/{wpId}/checklist-responses
 */
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { UNDISCLOSED_SECTIONS } from './b19Presets'

export interface RelatedPartyDetail {
  enterprise_type?: string
  registered_place?: string
  legal_rep?: string
  business_nature?: string
  registered_capital?: string
  shareholding_ratio?: string
}

export interface RelatedParty {
  id: string
  name: string
  relation_type: string
  is_controlled_by_same_party: boolean
  detail: RelatedPartyDetail
}

export interface RelatedPartyTxn {
  id: string
  related_party_id: string
  amount: string | null
  transaction_type: string
  is_arms_length: boolean | null
}

export interface UndisclosedCell {
  exist: string // 是 / 否 / 不适用 / ''
  source: string
  program: string
}

export function useB19RelatedParty(projectId: string, wpId: string) {
  const parties = ref<RelatedParty[]>([])
  const transactions = ref<RelatedPartyTxn[]>([])
  const loadingParties = ref(false)
  const loadingTxns = ref(false)

  // 未披露扫描：cells[`${si}-${ii}`] = {exist, source, program}
  const _initScan = (): Record<string, UndisclosedCell> => {
    const m: Record<string, UndisclosedCell> = {}
    UNDISCLOSED_SECTIONS.forEach((sec, si) => {
      sec.items.forEach((_it, ii) => {
        m[`${si}-${ii}`] = { exist: '', source: '', program: '' }
      })
    })
    return m
  }
  const undisclosed = ref<Record<string, UndisclosedCell>>(_initScan())
  const overallSummary = ref('')
  const loadingScan = ref(false)

  const rpBase = `/api/eqcr/projects/${projectId}/related-parties`
  const txnBase = `/api/eqcr/projects/${projectId}/related-party-transactions`
  const clUrl = `/api/workpapers/${wpId}/checklist-responses`

  // ─── 管理层关联方清单 ──────────────────────────────────────────────
  async function loadParties() {
    loadingParties.value = true
    try {
      const resp = await api.get(rpBase)
      const data = resp?.data ?? resp
      parties.value = (data?.registries ?? []).map((r: any) => ({
        id: r.id,
        name: r.name,
        relation_type: r.relation_type,
        is_controlled_by_same_party: !!r.is_controlled_by_same_party,
        detail: (r.detail && typeof r.detail === 'object') ? r.detail : {},
      }))
      transactions.value = (data?.transactions ?? []).map((t: any) => ({
        id: t.id,
        related_party_id: t.related_party_id,
        amount: t.amount ?? null,
        transaction_type: t.transaction_type,
        is_arms_length: t.is_arms_length ?? null,
      }))
    } catch (e) {
      console.warn('B19 加载关联方清单失败', e)
    } finally {
      loadingParties.value = false
    }
  }

  async function createParty(payload: {
    name: string
    relation_type: string
    is_controlled_by_same_party: boolean
    detail?: RelatedPartyDetail
  }) {
    await api.post(rpBase, payload)
    await loadParties()
    ElMessage.success('已新增关联方')
  }

  async function updateParty(id: string, patch: Partial<RelatedParty>) {
    await api.patch(`${rpBase}/${id}`, patch)
    await loadParties()
  }

  async function deleteParty(id: string) {
    await api.delete(`${rpBase}/${id}`)
    await loadParties()
    ElMessage.success('已删除关联方')
  }

  // ─── 关联方交易台账 ────────────────────────────────────────────────
  async function createTxn(payload: {
    related_party_id: string
    amount: number | null
    transaction_type: string
    is_arms_length: boolean | null
  }) {
    loadingTxns.value = true
    try {
      await api.post(txnBase, payload)
      await loadParties()
      ElMessage.success('已新增关联交易')
    } finally {
      loadingTxns.value = false
    }
  }

  async function updateTxn(id: string, patch: Partial<RelatedPartyTxn> & { amount?: number | null }) {
    await api.patch(`${txnBase}/${id}`, patch)
    await loadParties()
  }

  async function deleteTxn(id: string) {
    await api.delete(`${txnBase}/${id}`)
    await loadParties()
    ElMessage.success('已删除关联交易')
  }

  // ─── 未披露关联方扫描 ──────────────────────────────────────────────
  function _emptyCell(): UndisclosedCell {
    return { exist: '', source: '', program: '' }
  }

  function ensureCell(si: number, ii: number): UndisclosedCell {
    const k = `${si}-${ii}`
    if (!undisclosed.value[k]) undisclosed.value[k] = _emptyCell()
    return undisclosed.value[k]
  }

  async function loadScan() {
    loadingScan.value = true
    try {
      const items = (await api.get(clUrl)) as any[]
      const map: Record<string, UndisclosedCell> = {}
      // 预填所有预置项的空 cell，避免模板渲染期创建 cell（Vue 反模式）
      UNDISCLOSED_SECTIONS.forEach((sec, si) => {
        sec.items.forEach((_it, ii) => {
          map[`${si}-${ii}`] = _emptyCell()
        })
      })
      for (const it of items || []) {
        const id: string = it.item_id || ''
        if (!id.startsWith('b19u-')) continue
        if (id === 'b19u-overall') {
          overallSummary.value = it.remark || ''
          continue
        }
        // b19u-{si}-{ii} | b19u-{si}-{ii}-src | b19u-{si}-{ii}-prog
        const m = id.match(/^b19u-(\d+)-(\d+)(?:-(src|prog))?$/)
        if (!m) continue
        const key = `${m[1]}-${m[2]}`
        if (!map[key]) map[key] = _emptyCell()
        if (m[3] === 'src') map[key].source = it.remark || ''
        else if (m[3] === 'prog') map[key].program = it.remark || ''
        else map[key].exist = it.conclusion || ''
      }
      undisclosed.value = map
    } catch (e) {
      console.warn('B19 加载未披露扫描失败', e)
    } finally {
      loadingScan.value = false
    }
  }

  async function saveScan() {
    const items: any[] = []
    for (const [key, cell] of Object.entries(undisclosed.value)) {
      if (!cell.exist && !cell.source && !cell.program) continue
      items.push({ item_id: `b19u-${key}`, conclusion: cell.exist || null, remark: null })
      if (cell.source) items.push({ item_id: `b19u-${key}-src`, conclusion: null, remark: cell.source })
      if (cell.program) items.push({ item_id: `b19u-${key}-prog`, conclusion: null, remark: cell.program })
    }
    items.push({ item_id: 'b19u-overall', conclusion: null, remark: overallSummary.value || '' })
    await api.put(clUrl, { project_id: projectId, items })
    ElMessage.success('未披露扫描已保存')
  }

  /** 汇总所有"存在"迹象为风险因素文本，推送 B50 */
  function collectExistFactors(): string[] {
    const factors: string[] = []
    UNDISCLOSED_SECTIONS.forEach((sec, si) => {
      sec.items.forEach((it, ii) => {
        const cell = undisclosed.value[`${si}-${ii}`]
        if (cell?.exist === '是') {
          const src = cell.source ? `（来源：${cell.source}）` : ''
          factors.push(`未披露关联方迹象：${it.text}${src}（来自 B19-1）`)
        }
      })
    })
    return factors
  }

  function pushToB50() {
    const factors = collectExistFactors()
    if (!factors.length) {
      ElMessage.info('暂无标记为「存在」的迹象，无需推送')
      return
    }
    eventBus.emit('b50:push-risk-factor' as any, { factors, source: 'B19-1' })
    ElMessage.success(`已推送 ${factors.length} 项未披露关联方迹象至 B50 风险因素识别`)
  }

  return {
    parties,
    transactions,
    loadingParties,
    loadingTxns,
    undisclosed,
    overallSummary,
    loadingScan,
    loadParties,
    createParty,
    updateParty,
    deleteParty,
    createTxn,
    updateTxn,
    deleteTxn,
    loadScan,
    saveScan,
    ensureCell,
    collectExistFactors,
    pushToB50,
  }
}
