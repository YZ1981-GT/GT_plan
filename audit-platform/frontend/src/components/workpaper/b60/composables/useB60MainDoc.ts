/**
 * useB60MainDoc — B60 主底稿（总体审计策略）结构化数据管理
 *
 * - 普通 section：checklist_responses（主 B60 wp_id，item_id = B60-M-{sectionId}，remark=JSON）
 * - SCOT+ section（T26/T27）：复用 /api/projects/{pid}/b60/scot-rows（wizard_state.b60_scot_rows）
 * - B50 一键带入：GET /api/b60/b50-risk-rows
 *
 * Spec: b60-strategy-rework（直接修复）
 */
import { ref, reactive, onMounted, onScopeDispose, type Ref } from 'vue'
import http from '@/utils/http'
import { ElMessage } from 'element-plus'
import { B60_MAIN_SECTIONS, type MainDocSection } from '../constants/mainDocSchema'

const MAIN_CODE = 'B60-M'

export interface ScotRow {
  scot_id: string
  name: string
  detail: string
  approach: string
  cycle_code: string
  risk_id: string
  procedure_wp_index: string
  rely_on_controls: string
  control_test: string
  row_type: 'scot' | 'amount'
}

function emptyScotRow(rowType: 'scot' | 'amount'): ScotRow {
  return {
    scot_id: '', name: '', detail: '', approach: '', cycle_code: '',
    risk_id: '', procedure_wp_index: '', rely_on_controls: '', control_test: '',
    row_type: rowType,
  }
}

export interface UseB60MainDocOptions {
  wpId: Ref<string>
  projectId: Ref<string>
}

export function useB60MainDoc(options: UseB60MainDocOptions) {
  const { wpId, projectId } = options

  // ── 普通 section 数据（checklist）──
  const store = reactive<Record<string, any>>({})
  // ── SCOT+ 行（scot-rows 后端）──
  const scotRows = ref<ScotRow[]>([])
  const amountRows = ref<ScotRow[]>([])

  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const loading = ref(false)

  const genericSections = B60_MAIN_SECTIONS.filter((s) => !s.scot)

  // ── checklist 防抖保存 ──
  let _timer: ReturnType<typeof setTimeout> | null = null
  const _dirty = new Set<string>()
  let _failures = 0

  function _emptyData(section: MainDocSection): any {
    if (section.kind === 'table') {
      if (section.fixedRows && section.fixedRows.length > 0) {
        return { rows: section.fixedRows.map((r) => ({ ...r })) }
      }
      return { rows: [] }
    }
    return {}
  }

  function _initStore(): void {
    for (const s of genericSections) {
      if (!(s.id in store)) store[s.id] = _emptyData(s)
    }
  }

  async function loadChecklist(): Promise<void> {
    if (!wpId.value) return
    try {
      const { data } = await http.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const items: any[] = Array.isArray(data) ? data : (data?.data || data?.items || [])
      const byId: Record<string, any> = {}
      for (const it of items) if (it?.item_id) byId[it.item_id] = it
      for (const s of genericSections) {
        const rec = byId[`${MAIN_CODE}-${s.id}`]
        if (rec?.remark) {
          try {
            const parsed = JSON.parse(rec.remark)
            if (parsed && typeof parsed === 'object') { store[s.id] = parsed; continue }
          } catch { /* fall through */ }
        }
        store[s.id] = _emptyData(s)
      }
    } catch {
      _initStore()
    }
  }

  async function _doSave(): Promise<void> {
    if (!wpId.value || _dirty.size === 0 || _failures >= 3) return
    const ids = [..._dirty]; _dirty.clear()
    saveStatus.value = 'saving'
    const items = ids.map((id) => ({
      item_id: `${MAIN_CODE}-${id}`,
      conclusion: null,
      remark: JSON.stringify(store[id] ?? {}),
    }))
    try {
      await http.put(`/api/workpapers/${wpId.value}/checklist-responses`, { items })
      _failures = 0; saveStatus.value = 'saved'
    } catch {
      _failures++; saveStatus.value = 'unsaved'
      if (_failures >= 3) ElMessage.warning('保存失败，请检查网络后重试')
      else ids.forEach((id) => _dirty.add(id))
    }
  }

  function _schedule(): void {
    if (_timer) clearTimeout(_timer)
    _timer = setTimeout(() => { _timer = null; void _doSave() }, 800)
  }

  function markDirty(sectionId: string): void {
    _dirty.add(sectionId); saveStatus.value = 'unsaved'; _schedule()
  }

  // ── SCOT+ 行加载/保存 ──
  async function loadScot(): Promise<void> {
    if (!projectId.value) return
    try {
      const { data } = await http.get(`/api/projects/${projectId.value}/b60/scot-rows`)
      const payload = data?.data ?? data ?? {}
      const rows: ScotRow[] = Array.isArray(payload.rows) ? payload.rows : []
      scotRows.value = rows.filter((r) => (r.row_type || 'scot') === 'scot')
      amountRows.value = rows.filter((r) => r.row_type === 'amount')
    } catch {
      scotRows.value = []; amountRows.value = []
    }
  }

  let _scotTimer: ReturnType<typeof setTimeout> | null = null
  async function _doSaveScot(): Promise<void> {
    if (!projectId.value) return
    saveStatus.value = 'saving'
    const rows = [...scotRows.value, ...amountRows.value]
    try {
      await http.put(`/api/projects/${projectId.value}/b60/scot-rows`, { rows })
      saveStatus.value = 'saved'
    } catch {
      saveStatus.value = 'unsaved'
      ElMessage.warning('SCOT+ 保存失败，请稍后重试')
    }
  }

  function scheduleScotSave(): void {
    saveStatus.value = 'unsaved'
    if (_scotTimer) clearTimeout(_scotTimer)
    _scotTimer = setTimeout(() => { _scotTimer = null; void _doSaveScot() }, 800)
  }

  function addScotRow(rowType: 'scot' | 'amount'): void {
    const target = rowType === 'scot' ? scotRows : amountRows
    target.value.push(emptyScotRow(rowType))
    scheduleScotSave()
  }
  function removeScotRow(rowType: 'scot' | 'amount', idx: number): void {
    const target = rowType === 'scot' ? scotRows : amountRows
    target.value.splice(idx, 1)
    scheduleScotSave()
  }

  // ── B50 一键带入 ──
  async function fetchB50Rows(): Promise<{ fs_risks: any[]; assertion_risks: any[]; accounts: any[] }> {
    try {
      const { data } = await http.get(`/api/b60/b50-risk-rows`, { params: { project_id: projectId.value } })
      const payload = data?.data ?? data ?? {}
      return {
        fs_risks: payload.fs_risks || [],
        assertion_risks: payload.assertion_risks || [],
        accounts: payload.accounts || [],
      }
    } catch {
      return { fs_risks: [], assertion_risks: [], accounts: [] }
    }
  }

  /** 从 B50 带入财报层次风险 → Table 24 */
  function importFsRisks(fsRisks: any[]): number {
    const s = store['s6-fs-risk']
    if (!s || !Array.isArray(s.rows)) return 0
    const existing = new Set(s.rows.map((r: any) => (r.desc || '').trim()))
    let n = 0
    for (const r of fsRisks) {
      const desc = (r.description || '').trim()
      if (!desc || existing.has(desc)) continue
      s.rows.push({
        factor: r.is_special ? '特别风险' : '财报层次风险',
        desc,
        special: r.is_special ? '是' : '否',
        fraud: '',
      })
      existing.add(desc); n++
    }
    if (n > 0) markDirty('s6-fs-risk')
    return n
  }

  /** 从 B50 带入认定层次风险 → Table 25 */
  function importAssertionRisks(rows: any[]): number {
    const s = store['s6-assertion-risk']
    if (!s || !Array.isArray(s.rows)) return 0
    const existing = new Set(s.rows.map((r: any) => (r.desc || '').trim()))
    let n = 0
    for (const r of rows) {
      const desc = (r.description || '').trim()
      if (!desc || existing.has(desc)) continue
      s.rows.push({
        factor: r.account || '',
        desc,
        fsItem: r.account || '',
        assertion: r.assertion_cn || '',
        special: r.is_special_risk ? '是' : '否',
        fraud: '',
      })
      existing.add(desc); n++
    }
    if (n > 0) markDirty('s6-assertion-risk')
    return n
  }

  /** 从 B50 带入科目 → SCOT+ Table 26（approach: combined→综合性 / substantive→实质性） */
  function importScotFromAccounts(accounts: any[]): number {
    const existing = new Set(scotRows.value.map((r) => (r.name || '').trim()))
    let n = 0
    for (const a of accounts) {
      const name = (a.account || '').trim()
      if (!name || existing.has(name)) continue
      const approach = a.approach === 'combined' ? '综合性' : a.approach === 'substantive' ? '实质性' : ''
      scotRows.value.push({
        scot_id: 'B50',
        name,
        detail: '',
        approach,
        cycle_code: a.cycle || '',
        risk_id: name,
        procedure_wp_index: '',
        rely_on_controls: a.reliance || (a.substantive_only === 'Y' ? '否' : ''),
        control_test: '',
        row_type: 'scot',
      })
      existing.add(name); n++
    }
    if (n > 0) scheduleScotSave()
    return n
  }

  onMounted(() => {
    _initStore()
    loading.value = true
    Promise.all([loadChecklist(), loadScot()]).finally(() => { loading.value = false })
  })

  onScopeDispose(() => {
    if (_timer) { clearTimeout(_timer); void _doSave() }
    if (_scotTimer) { clearTimeout(_scotTimer); void _doSaveScot() }
  })

  async function flush(): Promise<void> {
    if (_timer) { clearTimeout(_timer); _timer = null }
    if (_scotTimer) { clearTimeout(_scotTimer); _scotTimer = null }
    await _doSave()
    await _doSaveScot()
  }

  return {
    store, scotRows, amountRows, saveStatus, loading, genericSections,
    markDirty, addScotRow, removeScotRow, scheduleScotSave,
    fetchB50Rows, importFsRisks, importAssertionRisks, importScotFromAccounts,
    flush,
    reload: async () => { await Promise.all([loadChecklist(), loadScot()]) },
  }
}
