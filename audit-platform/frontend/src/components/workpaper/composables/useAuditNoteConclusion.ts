/**
 * useAuditNoteConclusion — 通用审计说明 + 审计结论 persistence composable
 *
 * 收敛 F/G/H/I 全循环 sheet 中重复的 auditNote/auditConclusion 模式：
 * - onMounted 从 allResponses 恢复
 * - 编辑时 saveImmediate 持久化到 checklist_responses
 * - item_id 命名: `{prefix}-audit-note` / `{prefix}-audit-conclusion`
 *
 * 用法:
 * ```ts
 * const { auditNote, auditConclusion, saveAuditNote, saveAuditConclusion } =
 *   useAuditNoteConclusion('I4-detail', toRef(props, 'allResponses'), {
 *     saveImmediate: props.saveImmediate,
 *     isReadonly: toRef(props, 'isReadonly'),
 *   })
 * ```
 *
 * 或使用 emit 模式:
 * ```ts
 * const { auditNote, auditConclusion, saveAuditNote, saveAuditConclusion } =
 *   useAuditNoteConclusion('I4-detail', toRef(props, 'allResponses'), {
 *     onSave: (itemId, value) => emit('save', itemId, value),
 *     isReadonly: toRef(props, 'isReadonly'),
 *   })
 * ```
 */
import { ref, onMounted, type Ref } from 'vue'

export interface AuditNoteConclusionOptions {
  /** props.saveImmediate 回调（优先使用） */
  saveImmediate?: (items: Array<{ item_id: string; conclusion: null; remark: string }>) => void
  /** emit('save', itemId, value) 模式 */
  onSave?: (itemId: string, value: string) => void
  /** 只读标志 */
  isReadonly?: Ref<boolean> | boolean
}

export interface AuditNoteConclusionReturn {
  auditNote: Ref<string>
  auditConclusion: Ref<string>
  saveAuditNote: (val: string) => void
  saveAuditConclusion: (val: string) => void
  noteKey: string
  conclusionKey: string
}

/**
 * @param prefix  item_id 前缀，如 'I4-detail' → 生成 'I4-detail-audit-note'
 * @param allResponses  props.allResponses (Map)
 * @param options  persistence 配置
 */
export function useAuditNoteConclusion(
  prefix: string,
  allResponses: Ref<Map<string, any>> | Map<string, any>,
  options: AuditNoteConclusionOptions = {},
): AuditNoteConclusionReturn {
  const noteKey = `${prefix}-audit-note`
  const conclusionKey = `${prefix}-audit-conclusion`
  const auditNote = ref('')
  const auditConclusion = ref('')

  function _getMap(): Map<string, any> {
    const raw = allResponses
    if (raw instanceof Map) return raw
    // Ref<Map> case
    return (raw as Ref<Map<string, any>>).value
  }

  function _isReadonly(): boolean {
    const r = options.isReadonly
    if (r == null) return false
    if (typeof r === 'boolean') return r
    return r.value
  }

  function _persist(itemId: string, val: string): void {
    const map = _getMap()
    const item = { item_id: itemId, conclusion: null, remark: val }
    map.set(itemId, item)
    if (options.saveImmediate) {
      options.saveImmediate([item])
    } else if (options.onSave) {
      options.onSave(itemId, val)
    }
  }

  function saveAuditNote(val: string): void {
    if (_isReadonly()) return
    auditNote.value = val
    _persist(noteKey, val)
  }

  function saveAuditConclusion(val: string): void {
    if (_isReadonly()) return
    auditConclusion.value = val
    _persist(conclusionKey, val)
  }

  onMounted(() => {
    const map = _getMap()
    const n = map.get(noteKey)
    if (n?.remark) auditNote.value = n.remark
    const c = map.get(conclusionKey)
    if (c?.remark) auditConclusion.value = c.remark
  })

  return {
    auditNote,
    auditConclusion,
    saveAuditNote,
    saveAuditConclusion,
    noteKey,
    conclusionKey,
  }
}

export default useAuditNoteConclusion
