/**
 * useParagraphVariables — 段落型政策检查 composable
 *
 * 职责：
 * - 变量插值 / 上下文注入（entityName / periodEnd / indexNo / hasHeaderInfo）
 * - 模板解析（renderedContent / renderedSegmentValue）
 * - 段落数据管理（segmentValues / conclusionValue / initData）
 * - debounce save / field-change emit
 * - formatSeq 中文序号顿号
 *
 * Validates: Requirements 6.2
 */
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { DFormData, FieldChangePayload } from '../GtDForm.vue'

// ─── Types ───────────────────────────────────────────────────────────────────

interface ReferenceDoc {
  enabled?: boolean
  label?: string
  source?: string
  target_section?: string
  render?: 'index_chip' | string
}

export interface SegmentDef {
  id: string
  seq?: string
  title: string
  start_row?: number
  end_row?: number
  editable?: boolean
  content?: string
  type?: 'textarea' | string
  cell?: string
  max_length?: number
  placeholder?: string
  hint?: string
  formatting?: 'markdown' | string
  reference_doc?: ReferenceDoc
}

export interface ConclusionOption {
  value: string
  label: string
  description?: string
  class?: 'success' | 'warning' | 'danger' | 'info'
  icon?: string
}

export interface ConclusionBlock {
  mode?: 'single' | string
  cell?: string
  options?: ConclusionOption[]
  mutual_exclusive?: boolean
  required?: boolean
}

interface ParagraphData extends DFormData {
  segments?: Record<string, string>
  conclusion?: string
}

// ─── Params ──────────────────────────────────────────────────────────────────

export interface UseParagraphVariablesParams {
  schema: () => any
  htmlData: () => DFormData
  emit: {
    (e: 'field-change', payload: FieldChangePayload): void
    (e: 'save', data: DFormData): void
  }
  readonly: () => boolean
  assistedFieldsList: () => string[]
}

// ─── Return type inferred from function ──────────────────────────────────────

// ─── Composable ──────────────────────────────────────────────────────────────

export function useParagraphVariables(params: UseParagraphVariablesParams) {
  const {
    schema,
    htmlData,
    emit,
    readonly: isReadonly,
    assistedFieldsList,
  } = params

  // ─── Refs ────────────────────────────────────────────────────────────────

  const _segmentValues = ref<Record<string, string>>({})
  const _conclusionValue = ref<string>('')

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Computed: context injection ─────────────────────────────────────────

  const fixedCells = computed(() => (schema() as any)?.fixed_cells ?? {})

  const _entityName = computed(() => fixedCells.value?.A3 || '')
  const _periodEnd = computed(() => fixedCells.value?.A4 || '')
  const _indexNo = computed(
    () => fixedCells.value?.I3 || fixedCells.value?.J3 || fixedCells.value?.O3 || fixedCells.value?.P3 || ''
  )
  const _hasHeaderInfo = computed(
    () => !!(_entityName.value || _periodEnd.value || _indexNo.value)
  )

  // ─── Computed: schema parsing ────────────────────────────────────────────

  const _segments = computed<SegmentDef[]>(() => {
    const arr = (schema() as any)?.segments
    return Array.isArray(arr) ? arr as SegmentDef[] : []
  })

  const _conclusionBlock = computed<ConclusionBlock | null>(() => {
    const c = (schema() as any)?.conclusion
    return c && typeof c === 'object' ? c : null
  })

  const _conclusionOptions = computed<ConclusionOption[]>(
    () => _conclusionBlock.value?.options ?? []
  )

  const _hasConclusion = computed(
    () => _conclusionBlock.value?.mode === 'single' && _conclusionOptions.value.length > 0
  )

  // ─── Computed: markdown rendering ────────────────────────────────────────

  /** 只读段落预渲染 markdown → 安全 HTML（按 segment.id 缓存） */
  const _renderedContent = computed<Record<string, string>>(() => {
    const out: Record<string, string> = {}
    for (const seg of _segments.value) {
      if (!seg.editable && seg.formatting === 'markdown' && seg.content) {
        try {
          const html = marked(seg.content, { async: false }) as string
          out[seg.id] = DOMPurify.sanitize(html)
        } catch {
          out[seg.id] = ''
        }
      }
    }
    return out
  })

  /** 可编辑段落用户输入实时渲染 markdown 预览 */
  const _renderedSegmentValue = computed<Record<string, string>>(() => {
    const out: Record<string, string> = {}
    for (const seg of _segments.value) {
      if (seg.editable && seg.formatting === 'markdown') {
        const text = _segmentValues.value[seg.id]
        if (text) {
          try {
            const html = marked(text, { async: false }) as string
            out[seg.id] = DOMPurify.sanitize(html)
          } catch {
            out[seg.id] = ''
          }
        }
      }
    }
    return out
  })

  // ─── Helpers ─────────────────────────────────────────────────────────────

  /** 中文/阿拉伯数字 seq 统一加顿号：「一」→「一、」 */
  function _formatSeq(seq: string | undefined): string {
    if (!seq) return ''
    const trimmed = String(seq).trim()
    if (!trimmed) return ''
    if (/[、.．]$/.test(trimmed)) return trimmed
    return trimmed + '、'
  }

  /** 段落 textarea 默认行数：按 max_length 推导 */
  function _segmentRows(seg: SegmentDef): number {
    const max = seg.max_length || 0
    if (max <= 600) return 6
    if (max <= 2000) return 8
    if (max <= 4000) return 10
    return 12
  }

  /** 引用文档解析为 GtIndexChip 可识别的 ref */
  function _referenceChipValue(seg: SegmentDef): string {
    const refDoc = seg.reference_doc
    if (!refDoc?.enabled || !refDoc.target_section) return ''
    const section = refDoc.target_section.split(/\s+/)[0] || refDoc.target_section
    return 'Note:' + section
  }

  // ─── Field change emitters ───────────────────────────────────────────────

  function emitFieldChange(field_name: string, oldValue: any, newValue: any, cell?: string) {
    emit('field-change', {
      field_name,
      old_value: oldValue,
      new_value: newValue,
      cell,
    })
  }

  // ─── Segment handlers ──────────────────────────────────────────────────

  function _onSegmentChange(_segId: string) {
    _debounceSave()
  }

  function _onSegmentBlur(segId: string) {
    const seg = _segments.value.find(s => s.id === segId)
    emitFieldChange(
      'segments.' + segId,
      undefined,
      _segmentValues.value[segId],
      seg?.cell,
    )
    if (isReadonly()) return
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    emit('save', buildSavePayload())
  }

  // ─── Conclusion handlers ─────────────────────────────────────────────────

  function _onConclusionChange(value: string | number | boolean | undefined) {
    const newVal = String(value ?? '')
    emitFieldChange(
      'conclusion',
      undefined,
      newVal,
      _conclusionBlock.value?.cell,
    )
    _debounceSave()
  }

  // ─── Save payload + debounce ─────────────────────────────────────────────

  function buildSavePayload(): ParagraphData {
    return {
      ...(htmlData() || {}),
      segments: { ..._segmentValues.value },
      conclusion: _conclusionValue.value,
      ai_assisted_fields: assistedFieldsList().length > 0 ? assistedFieldsList() : undefined,
    } as ParagraphData
  }

  function _debounceSave() {
    if (isReadonly()) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      emit('save', buildSavePayload())
    }, 1500)
  }

  // ─── Init / Sync ─────────────────────────────────────────────────────────

  function _initData() {
    const data = (htmlData() ?? {}) as ParagraphData

    // 段落值
    const segIn = data.segments && typeof data.segments === 'object' ? data.segments : {}
    const segOut: Record<string, string> = {}
    for (const seg of _segments.value) {
      if (!seg.editable) continue
      const v = (segIn as Record<string, any>)[seg.id]
      segOut[seg.id] = typeof v === 'string' ? v : ''
    }
    _segmentValues.value = segOut

    // 结论
    _conclusionValue.value = typeof data.conclusion === 'string' ? data.conclusion : ''
  }

  _initData()

  watch(
    () => htmlData(),
    () => { _initData() },
    { deep: true }
  )

  watch(
    () => schema(),
    () => { _initData() },
    { deep: true }
  )

  // ─── Cleanup ─────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────────

  return {
    segmentValues: _segmentValues,
    conclusionValue: _conclusionValue,
    renderedContent: _renderedContent,
    renderedSegmentValue: _renderedSegmentValue,
    entityName: _entityName,
    periodEnd: _periodEnd,
    indexNo: _indexNo,
    hasHeaderInfo: _hasHeaderInfo,
    segments: _segments,
    conclusionBlock: _conclusionBlock,
    conclusionOptions: _conclusionOptions,
    hasConclusion: _hasConclusion,
    formatSeq: _formatSeq,
    segmentRows: _segmentRows,
    referenceChipValue: _referenceChipValue,
    onSegmentChange: _onSegmentChange,
    onSegmentBlur: _onSegmentBlur,
    onConclusionChange: _onConclusionChange,
    debounceSave: _debounceSave,
    initData: _initData,
  }
}
