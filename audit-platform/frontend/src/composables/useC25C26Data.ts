/**
 * useC25C26Data — C25/C26 数据持久化 composable
 *
 * 职责：
 * - selfLoad(): GET /api/workpapers/:wpId/checklist-responses，按前缀 C25-/C26- 解析到结构化 state
 * - C25 state: 10 步评估 [{applicable, executor, result, indexRef}] + conclusion + remark
 * - C26 state: 动态行 [{category, indexNo, purpose, plannedTest, walkthrough, controlTest, testResult, clientFeedback, conclusion, evidence, elements}]
 * - debounceSave(): 2s debounce 文本字段
 * - saveImmediate(): 枚举/tag 变更即时保存
 * - persistAll(): 序列化 state → items → PUT
 * - C26 addRow(name) / removeRow(index)
 * - flushPendingSaves(): unmount 时确保无数据丢失
 * - readonly guard: isReadonly 时跳过所有保存
 *
 * Spec: .kiro/specs/c25-c26-internal-audit-info-control/
 * Task: 3.1
 * Requirements: 6.1, 6.2, 6.3, 6.4, 3.3
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

/** C25 单步评估数据 */
export interface C25Step {
  applicable: '是' | '否' | null
  executor: string
  result: string
  indexRef: string
}

/** C25 完整状态 */
export interface C25State {
  steps: C25Step[]
  conclusion: string  // 可以利用/不能利用/可以部分利用
  remark: string
}

/** C26 控制矩阵行 */
export interface C26ControlRow {
  category: string
  indexNo: string
  purpose: string
  plannedTest: string
  walkthrough: string
  controlTest: string
  testResult: string   // 未发现例外/发现例外/不适用
  clientFeedback: string
  conclusion: string   // 有效/无效/部分有效/不适用
  evidence: string
  elements: string[]   // 完整性/准确性/授权/访问限制 的子集
}

/** C26 完整状态 */
export interface C26State {
  rows: C26ControlRow[]
}

/** checklist-responses 单条 item */
export interface ChecklistResponseItem {
  item_id: string
  conclusion: string | null
  remark: string | null
  wp_ref?: string | null
}

// ─── Constants ───────────────────────────────────────────────────────────────

const C25_STEP_COUNT = 10
const DEBOUNCE_MS = 2000

const C26_FIELDS = [
  'category', 'indexNo', 'purpose', 'plannedTest', 'walkthrough',
  'controlTest', 'testResult', 'clientFeedback', 'conclusion', 'evidence', 'elements',
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function createEmptyC25Step(): C25Step {
  return { applicable: null, executor: '', result: '', indexRef: '' }
}

function createEmptyC26Row(): C26ControlRow {
  return {
    category: '', indexNo: '', purpose: '', plannedTest: '',
    walkthrough: '', controlTest: '', testResult: '', clientFeedback: '',
    conclusion: '', evidence: '', elements: [],
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useC25C26Data(
  wpId: Ref<string>,
  projectId: Ref<string>,
  isReadonly: Ref<boolean>,
) {
  // ─── Reactive state ────────────────────────────────────────────────────────
  const c25 = ref<C25State>({
    steps: Array.from({ length: C25_STEP_COUNT }, () => createEmptyC25Step()),
    conclusion: '',
    remark: '',
  })

  const c26 = ref<C26State>({ rows: [] })

  const loading = ref(false)
  const saving = ref(false)

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  let pendingSave = false

  // ─── selfLoad ──────────────────────────────────────────────────────────────

  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    loading.value = true
    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: ChecklistResponseItem[] = Array.isArray(res) ? res : (res?.data ?? [])
      parseResponses(responses)
    } catch {
      ElMessage.warning('数据加载失败，可手动填写')
    } finally {
      loading.value = false
    }
  }

  function parseResponses(responses: ChecklistResponseItem[]): void {
    // ─── Parse C25 ───
    const stepPattern = /^C25-step-(\d+)-(\w+)$/
    for (const r of responses) {
      if (!r.item_id) continue

      const stepMatch = r.item_id.match(stepPattern)
      if (stepMatch) {
        const idx = parseInt(stepMatch[1], 10) - 1 // 1-based → 0-based
        const field = stepMatch[2] as 'applicable' | 'executor' | 'result' | 'indexRef'
        if (idx >= 0 && idx < C25_STEP_COUNT && c25.value.steps[idx]) {
          if (field === 'applicable') {
            c25.value.steps[idx].applicable = (r.conclusion as C25Step['applicable']) || null
          } else if (field === 'executor') {
            c25.value.steps[idx].executor = r.remark || ''
          } else if (field === 'result') {
            c25.value.steps[idx].result = r.remark || ''
          } else if (field === 'indexRef') {
            c25.value.steps[idx].indexRef = r.remark || r.wp_ref || ''
          }
        }
        continue
      }

      if (r.item_id === 'C25-reliance-conclusion') {
        c25.value.conclusion = r.conclusion || ''
        continue
      }
      if (r.item_id === 'C25-reliance-remark') {
        c25.value.remark = r.remark || ''
        continue
      }
    }

    // ─── Parse C26 ───
    // Collect max row index from C26-ctrl-{m}-* patterns
    const ctrlPattern = /^C26-ctrl-(\d+)-(\w+)$/
    let maxRow = 0
    const c26Map = new Map<number, Partial<C26ControlRow>>()

    for (const r of responses) {
      if (!r.item_id) continue
      const match = r.item_id.match(ctrlPattern)
      if (!match) continue

      const rowIdx = parseInt(match[1], 10) // 1-based
      const field = match[2]
      if (rowIdx > maxRow) maxRow = rowIdx

      if (!c26Map.has(rowIdx)) c26Map.set(rowIdx, {})
      const row = c26Map.get(rowIdx)!

      if (field === 'elements') {
        // elements stored as comma-separated in conclusion or remark
        const raw = r.conclusion || r.remark || ''
        row.elements = raw ? raw.split(',').map(s => s.trim()).filter(Boolean) : []
      } else if (field === 'testResult' || field === 'conclusion' || field === 'category') {
        // enum fields stored in conclusion slot
        ;(row as any)[field] = r.conclusion || ''
      } else {
        // text fields stored in remark slot
        ;(row as any)[field] = r.remark || ''
      }
    }

    // Build C26 rows array in order
    const rows: C26ControlRow[] = []
    for (let i = 1; i <= maxRow; i++) {
      const partial = c26Map.get(i)
      if (partial) {
        rows.push({ ...createEmptyC26Row(), ...partial })
      } else {
        rows.push(createEmptyC26Row())
      }
    }
    c26.value.rows = rows
  }

  // ─── Serialize → items ─────────────────────────────────────────────────────

  function serializeAll(): ChecklistResponseItem[] {
    const items: ChecklistResponseItem[] = []

    // ─── C25 steps ───
    for (let i = 0; i < C25_STEP_COUNT; i++) {
      const step = c25.value.steps[i]
      const n = i + 1
      items.push({
        item_id: `C25-step-${n}-applicable`,
        conclusion: step.applicable || null,
        remark: null,
      })
      items.push({
        item_id: `C25-step-${n}-executor`,
        conclusion: null,
        remark: step.executor || null,
      })
      items.push({
        item_id: `C25-step-${n}-result`,
        conclusion: null,
        remark: step.result || null,
      })
      items.push({
        item_id: `C25-step-${n}-indexRef`,
        conclusion: null,
        remark: step.indexRef || null,
        wp_ref: step.indexRef || null,
      })
    }

    // ─── C25 conclusion ───
    items.push({
      item_id: 'C25-reliance-conclusion',
      conclusion: c25.value.conclusion || null,
      remark: null,
    })
    items.push({
      item_id: 'C25-reliance-remark',
      conclusion: null,
      remark: c25.value.remark || null,
    })

    // ─── C26 rows ───
    for (let i = 0; i < c26.value.rows.length; i++) {
      const row = c26.value.rows[i]
      const m = i + 1
      items.push({
        item_id: `C26-ctrl-${m}-category`,
        conclusion: row.category || null,
        remark: null,
      })
      items.push({
        item_id: `C26-ctrl-${m}-indexNo`,
        conclusion: null,
        remark: row.indexNo || null,
      })
      items.push({
        item_id: `C26-ctrl-${m}-purpose`,
        conclusion: null,
        remark: row.purpose || null,
      })
      items.push({
        item_id: `C26-ctrl-${m}-plannedTest`,
        conclusion: null,
        remark: row.plannedTest || null,
      })
      items.push({
        item_id: `C26-ctrl-${m}-walkthrough`,
        conclusion: null,
        remark: row.walkthrough || null,
      })
      items.push({
        item_id: `C26-ctrl-${m}-controlTest`,
        conclusion: null,
        remark: row.controlTest || null,
      })
      items.push({
        item_id: `C26-ctrl-${m}-testResult`,
        conclusion: row.testResult || null,
        remark: null,
      })
      items.push({
        item_id: `C26-ctrl-${m}-clientFeedback`,
        conclusion: null,
        remark: row.clientFeedback || null,
      })
      items.push({
        item_id: `C26-ctrl-${m}-conclusion`,
        conclusion: row.conclusion || null,
        remark: null,
      })
      items.push({
        item_id: `C26-ctrl-${m}-evidence`,
        conclusion: null,
        remark: row.evidence || null,
        wp_ref: row.evidence || null,
      })
      items.push({
        item_id: `C26-ctrl-${m}-elements`,
        conclusion: row.elements.length > 0 ? row.elements.join(',') : null,
        remark: null,
      })
    }

    return items
  }

  // ─── persistAll (PUT) ──────────────────────────────────────────────────────

  async function persistAll(): Promise<void> {
    if (isReadonly.value) return
    if (!wpId.value) return

    const items = serializeAll()
    if (items.length === 0) return

    saving.value = true
    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        project_id: projectId.value,
        items,
      })
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，数据已保留在本地')
      }
    } finally {
      saving.value = false
    }
  }

  // ─── debounceSave (2s for text fields) ─────────────────────────────────────

  function debounceSave(): void {
    if (isReadonly.value) return
    pendingSave = true
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      pendingSave = false
      persistAll()
    }, DEBOUNCE_MS)
  }

  // ─── saveImmediate (enum/tag changes) ──────────────────────────────────────

  function saveImmediate(): void {
    if (isReadonly.value) return
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    pendingSave = false
    persistAll()
  }

  // ─── flushPendingSaves (onBeforeUnmount) ───────────────────────────────────

  function flushPendingSaves(): void {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    if (pendingSave) {
      pendingSave = false
      persistAll()
    }
  }

  // ─── C26 addRow / removeRow ────────────────────────────────────────────────

  /**
   * 添加新 C26 控制行。name 为 ElMessageBox.prompt 确认后传入的控制名称。
   * 调用者负责弹出确认对话框，此处仅处理数据层。
   */
  function addRow(name: string): void {
    if (isReadonly.value) return
    const newRow = createEmptyC26Row()
    newRow.indexNo = name
    c26.value.rows.push(newRow)
    saveImmediate()
  }

  /**
   * 删除 C26 控制行。
   */
  function removeRow(index: number): void {
    if (isReadonly.value) return
    if (index < 0 || index >= c26.value.rows.length) return
    c26.value.rows.splice(index, 1)
    saveImmediate()
  }

  // ─── C25 field update helpers ──────────────────────────────────────────────

  /** 更新 C25 步骤文本字段（debounce 保存） */
  function updateC25StepText(stepIndex: number, field: 'executor' | 'result' | 'indexRef', value: string): void {
    if (isReadonly.value) return
    if (stepIndex < 0 || stepIndex >= C25_STEP_COUNT) return
    c25.value.steps[stepIndex][field] = value
    debounceSave()
  }

  /** 更新 C25 步骤适用性（即时保存） */
  function updateC25StepApplicable(stepIndex: number, value: '是' | '否' | null): void {
    if (isReadonly.value) return
    if (stepIndex < 0 || stepIndex >= C25_STEP_COUNT) return
    c25.value.steps[stepIndex].applicable = value
    saveImmediate()
  }

  /** 更新 C25 利用结论（即时保存） */
  function updateC25Conclusion(value: string): void {
    if (isReadonly.value) return
    c25.value.conclusion = value
    saveImmediate()
  }

  /** 更新 C25 结论说明（debounce 保存） */
  function updateC25Remark(value: string): void {
    if (isReadonly.value) return
    c25.value.remark = value
    debounceSave()
  }

  // ─── C26 field update helpers ──────────────────────────────────────────────

  /** 更新 C26 行文本字段（debounce 保存） */
  function updateC26RowText(
    rowIndex: number,
    field: 'purpose' | 'plannedTest' | 'walkthrough' | 'controlTest' | 'clientFeedback' | 'evidence' | 'indexNo',
    value: string,
  ): void {
    if (isReadonly.value) return
    if (rowIndex < 0 || rowIndex >= c26.value.rows.length) return
    c26.value.rows[rowIndex][field] = value
    debounceSave()
  }

  /** 更新 C26 行枚举字段（即时保存） */
  function updateC26RowEnum(
    rowIndex: number,
    field: 'category' | 'testResult' | 'conclusion',
    value: string,
  ): void {
    if (isReadonly.value) return
    if (rowIndex < 0 || rowIndex >= c26.value.rows.length) return
    c26.value.rows[rowIndex][field] = value
    saveImmediate()
  }

  /** 更新 C26 行四要素标记（即时保存） */
  function updateC26RowElements(rowIndex: number, value: string[]): void {
    if (isReadonly.value) return
    if (rowIndex < 0 || rowIndex >= c26.value.rows.length) return
    c26.value.rows[rowIndex].elements = value
    saveImmediate()
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    c25,
    c26,
    loading,
    saving,
    // Load
    selfLoad,
    // Save
    debounceSave,
    saveImmediate,
    persistAll,
    flushPendingSaves,
    // C26 dynamic rows
    addRow,
    removeRow,
    // C25 helpers
    updateC25StepText,
    updateC25StepApplicable,
    updateC25Conclusion,
    updateC25Remark,
    // C26 helpers
    updateC26RowText,
    updateC26RowEnum,
    updateC26RowElements,
    // Internals (for testing)
    serializeAll,
    parseResponses,
  }
}

export default useC25C26Data
