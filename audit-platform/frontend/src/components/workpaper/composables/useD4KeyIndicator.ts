/**
 * useD4KeyIndicator — D4-22 主营业务收入重要指标分析表 composable
 *
 * 固定12行KPI指标 × 动态列（本期/上期/N个同行业公司） + 合理性分析
 * 自动计算：人均创收/ROP/运输费用占比
 * 持久化：item_id前缀 D4-22-* + debounce 2s
 *
 * Spec: D4-22 IPO重要指标分析
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'

// ═══════════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════════

/** 单个指标行 */
export interface IndicatorRow {
  key: string
  label: string
  currentPeriod: number | string
  priorPeriod: number | string
  peers: (number | string)[]  // 同行业公司值，与 peerNames 对应
  analysis: string            // 合理性分析（文本）
  isAutoCalc: boolean         // 是否自动计算行
  formula?: string            // 公式描述（tooltip用）
}

/** 同行业公司列 */
export interface PeerCompany {
  id: string
  name: string
}

export interface UseD4KeyIndicatorOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
}

// ═══════════════════════════════════════════════════════════════════════════════
// 固定指标定义
// ═══════════════════════════════════════════════════════════════════════════════

export const INDICATOR_DEFINITIONS: { key: string; label: string; isAutoCalc: boolean; formula?: string }[] = [
  { key: 'budget', label: '年度预算', isAutoCalc: false },
  { key: 'revenue', label: '主营业务收入', isAutoCalc: false },
  { key: 'salesHeadcount', label: '销售人员数量', isAutoCalc: false },
  { key: 'revenuePerCapita', label: '销售人员人均创收', isAutoCalc: true, formula: '主营业务收入 ÷ 销售人员数量' },
  { key: 'regionDistribution', label: '销售区域分布是否变化（占比和区域数量等）', isAutoCalc: false },
  { key: 'performanceTarget', label: '销售人员业绩指标', isAutoCalc: false },
  { key: 'salesCompensation', label: '销售人员薪酬', isAutoCalc: false },
  { key: 'backlog', label: '期末在手订单', isAutoCalc: false },
  { key: 'ebit', label: '息税前利润（利润总额＋财务费用）', isAutoCalc: false },
  { key: 'totalCompensation', label: '薪酬总额（支付给职工以及为职工支付的现金+期末应付职工薪酬-期初应付职工薪酬）', isAutoCalc: false },
  { key: 'rop', label: '人力投入回报率(ROP)', isAutoCalc: true, formula: '息税前利润 ÷ 薪酬总额' },
  { key: 'transportRatio', label: '运输费用/营业收入', isAutoCalc: true, formula: '运输费用 ÷ 营业收入（需手动输入运输费用）' },
]

// ═══════════════════════════════════════════════════════════════════════════════
// 纯函数（可测试）
// ═══════════════════════════════════════════════════════════════════════════════

/** 安全除法 */
export function safeDivide(numerator: number | string, denominator: number | string): number | null {
  const n = typeof numerator === 'string' ? parseFloat(numerator) : numerator
  const d = typeof denominator === 'string' ? parseFloat(denominator) : denominator
  if (!n || !d || isNaN(n) || isNaN(d) || d === 0) return null
  return n / d
}

/** 计算自动指标值 */
export function calcAutoIndicator(
  key: string,
  getVal: (indicatorKey: string) => number | string,
): number | null {
  switch (key) {
    case 'revenuePerCapita': return safeDivide(getVal('revenue'), getVal('salesHeadcount'))
    case 'rop': return safeDivide(getVal('ebit'), getVal('totalCompensation'))
    case 'transportRatio': return safeDivide(getVal('transportRatio_numerator'), getVal('revenue'))
    default: return null
  }
}

/** 格式化自动计算结果 */
export function formatAutoValue(key: string, val: number | null): string {
  if (val === null) return ''
  if (key === 'rop' || key === 'transportRatio') return (val * 100).toFixed(2) + '%'
  return val.toFixed(2)
}

// ═══════════════════════════════════════════════════════════════════════════════
// Composable 主体
// ═══════════════════════════════════════════════════════════════════════════════

export function useD4KeyIndicator(options: UseD4KeyIndicatorOptions) {
  const { wpId, projectId, allResponses, isReadonly } = options

  const rows = ref<IndicatorRow[]>([])
  const peerCompanies = ref<PeerCompany[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  // 运输费用（自动计算运输费用/营业收入的分子，独立存储）
  const transportExpense = ref<number | string>('')

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load ───────────────────────────────────────────────────────────

  function loadData() {
    const resp = allResponses.value.get('D4-22-rows')
    if (resp?.remark) {
      try {
        const parsed = JSON.parse(resp.remark)
        if (parsed && typeof parsed === 'object') {
          // 逆投影：持久化扁平行 → UI 行模型（peer_N → peers 数组，
          // metricName→label，rationality→analysis）。按 metricName 对齐
          // INDICATOR_DEFINITIONS 固定 12 行，缺字段回退空值。
          const peerCount = Array.isArray(parsed.peers) ? parsed.peers.length : 0
          if (Array.isArray(parsed.rows) && parsed.rows.length) {
            const byMetric = new Map(parsed.rows.map((r: any) => [String(r.metricName ?? r.label ?? ''), r]))
            rows.value = INDICATOR_DEFINITIONS.map(def => {
              const src = byMetric.get(def.label) ?? {}
              const peers: (number | string)[] = []
              for (let i = 1; i <= Math.max(peerCount, 0); i++) {
                peers.push(src[`peer_${i}`] ?? '')
              }
              return {
                key: def.key,
                label: def.label,
                currentPeriod: src.currentPeriod ?? '',
                priorPeriod: src.priorPeriod ?? '',
                peers,
                analysis: src.rationality ?? '',
                isAutoCalc: def.isAutoCalc,
              }
            })
          } else {
            initRows()
          }
          if (Array.isArray(parsed.peers)) peerCompanies.value = parsed.peers
          if (parsed.transportExpense != null) transportExpense.value = parsed.transportExpense
          return
        }
      } catch { /* fallback */ }
    }
    initRows()
  }

  function loadNoteConclusion() {
    auditNote.value = allResponses.value.get('D4-22-note')?.remark || ''
    auditConclusion.value = allResponses.value.get('D4-22-conclusion')?.remark || ''
  }

  function initRows() {
    rows.value = INDICATOR_DEFINITIONS.map(def => ({
      key: def.key,
      label: def.label,
      currentPeriod: '',
      priorPeriod: '',
      peers: [],
      analysis: '',
      isAutoCalc: def.isAutoCalc,
      formula: def.formula,
    }))
  }

  watch(() => allResponses.value.get('D4-22-rows')?.remark, () => loadData(), { immediate: true })
  watch(() => allResponses.value.get('D4-22-note')?.remark, () => loadNoteConclusion(), { immediate: true })

  // ─── Peer Companies CRUD ────────────────────────────────────────────

  function addPeer(name: string): PeerCompany {
    const peer: PeerCompany = {
      id: `peer-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name,
    }
    peerCompanies.value.push(peer)
    // 给每行的 peers 数组追加空值
    for (const row of rows.value) {
      row.peers.push('')
    }
    persistAll()
    return peer
  }

  function removePeer(id: string) {
    if (isReadonly.value) return
    const idx = peerCompanies.value.findIndex(p => p.id === id)
    if (idx < 0) return
    peerCompanies.value.splice(idx, 1)
    for (const row of rows.value) {
      row.peers.splice(idx, 1)
    }
    persistAll()
  }

  function renamePeer(id: string, name: string) {
    if (isReadonly.value) return
    const peer = peerCompanies.value.find(p => p.id === id)
    if (peer) peer.name = name
    persistAll()
  }

  // ─── Cell Update ────────────────────────────────────────────────────

  function updateCell(indicatorKey: string, field: 'currentPeriod' | 'priorPeriod' | 'analysis', value: any) {
    if (isReadonly.value) return
    const row = rows.value.find(r => r.key === indicatorKey)
    if (!row) return
    row[field] = value
    recalcAuto()
    persistAll()
  }

  function updatePeerCell(indicatorKey: string, peerIndex: number, value: any) {
    if (isReadonly.value) return
    const row = rows.value.find(r => r.key === indicatorKey)
    if (!row) return
    while (row.peers.length <= peerIndex) row.peers.push('')
    row.peers[peerIndex] = value
    persistAll()
  }

  function updateTransportExpense(val: number | string) {
    if (isReadonly.value) return
    transportExpense.value = val
    recalcAuto()
    persistAll()
  }

  // ─── Auto-calc ──────────────────────────────────────────────────────

  function recalcAuto() {
    const getVal = (key: string): number | string => {
      if (key === 'transportRatio_numerator') return transportExpense.value
      const row = rows.value.find(r => r.key === key)
      return row?.currentPeriod ?? ''
    }

    for (const row of rows.value) {
      if (row.isAutoCalc) {
        const result = calcAutoIndicator(row.key, getVal)
        if (result !== null) {
          row.currentPeriod = formatAutoValue(row.key, result)
        }
      }
    }
  }

  // ─── Stats ──────────────────────────────────────────────────────────

  const filledCount = computed(() =>
    rows.value.filter(r => r.currentPeriod !== '' && r.currentPeriod !== 0).length,
  )
  const totalIndicators = computed(() => rows.value.length)
  const peerCount = computed(() => peerCompanies.value.length)
  const analysisFilledCount = computed(() => rows.value.filter(r => r.analysis.trim() !== '').length)

  // ─── Persistence (debounce 2s) ──────────────────────────────────────
  // 持久化形态与后端 phase5_d4_ipo_related_sheets D4-22 descriptor 对齐：
  //   行身份 metricName（descriptor ROW_IDENTITY_STORE_KEY_D422）
  //   固定列 currentPeriod / priorPeriod / rationality
  //   动态同业列 peer_1 / peer_2 / …（稳定键 {slot}_{seq}，禁 label 作 key）
  // UI 内部态仍是 peers 数组 + label/analysis/isAutoCalc；持久化时展平，
  // 加载时由 loadData 读回原形态（前端行模型不变，仅序列化层对齐）。
  function toPersistedRows(): Record<string, any>[] {
    return rows.value.map(r => {
      const out: Record<string, any> = {
        metricName: r.label,
        currentPeriod: r.currentPeriod,
        priorPeriod: r.priorPeriod,
        rationality: r.analysis,
      }
      r.peers.forEach((v, i) => { out[`peer_${i + 1}`] = v })
      return out
    })
  }

  function persistAll() {
    allResponses.value.set('D4-22-rows', {
      item_id: 'D4-22-rows',
      conclusion: null,
      remark: JSON.stringify({
        rows: toPersistedRows(),
        peers: peerCompanies.value,
        transportExpense: transportExpense.value,
      }),
    })
    allResponses.value.set('D4-22-note', {
      item_id: 'D4-22-note',
      conclusion: null,
      remark: auditNote.value,
    })
    allResponses.value.set('D4-22-conclusion', {
      item_id: 'D4-22-conclusion',
      conclusion: null,
      remark: auditConclusion.value,
    })
    debounceSave()
  }

  function debounceSave() {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave() {
    const keys = ['D4-22-rows', 'D4-22-note', 'D4-22-conclusion']
    const items = keys.map(k => allResponses.value.get(k)).filter(Boolean)
    window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
  }

  // 双向回写 flushHtml 用：清防抖 + 立即派发 d4:save-items（先落库再 readStoreProjection）。
  function flushPendingSave() {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null }
    flushSave()
  }

  // 双向回写 reloadHtml 用：切回 HTML 后从 allResponses 重读。
  function reload() {
    loadData()
    loadNoteConclusion()
  }

  function updateAuditNote(val: string) {
    if (isReadonly.value) return
    auditNote.value = val
    persistAll()
  }

  function updateAuditConclusion(val: string) {
    if (isReadonly.value) return
    auditConclusion.value = val
    persistAll()
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
  })

  // ─── Return ─────────────────────────────────────────────────────────

  return {
    rows,
    peerCompanies,
    auditNote,
    auditConclusion,
    transportExpense,
    filledCount,
    totalIndicators,
    peerCount,
    analysisFilledCount,
    addPeer,
    removePeer,
    renamePeer,
    updateCell,
    updatePeerCell,
    updateTransportExpense,
    updateAuditNote,
    updateAuditConclusion,
    recalcAuto,
    loadData,
    flushPendingSave,
    reload,
  }
}

export default useD4KeyIndicator
