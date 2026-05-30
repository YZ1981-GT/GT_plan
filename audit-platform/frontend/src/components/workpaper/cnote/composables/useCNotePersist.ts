/**
 * useCNotePersist.ts — C 类附注披露嵌套表「数据装载 / 持久化」composable
 *
 * 从 GtCNoteTable.vue 剪切 `initData` / `buildSavePayload` / `debounceSave`
 * 三个数据生命周期函数（design §1.5，原 1023-1145 行），并把 saveTimer 与
 * onBeforeUnmount 清理封装在 composable 内部（需求 6 AC-3）。逐字搬运，零行为改变。
 *
 * 设计 D1/D3：composable 不持有状态副本——所有响应式状态（subTableData /
 * hiddenSubtables / currentStandardSubClass / contextData / activeCollapse）
 * 与 schema 派生量（allSubTables / contextFields / visibleSubTables /
 * labelColumnField）均由 shell 以引用 / getter 形式传入，保持单一数据源。
 *
 * 注：design 原型签名仅列出 subTableData/hiddenSubtables/currentStandardSubClass/
 * contextData/sectionId，但 `initData` 实际还写入 activeCollapse、并依赖 schema
 * 派生的 allSubTables/contextFields/visibleSubTables/labelColumnField，故补全这些
 * 入参以保持 byte-for-byte 行为一致（与 useCNoteFormula 补全 currentStandardSubClass
 * 依赖同理）。`props` 必须传入响应式 props 对象本身（而非解构副本），以保证
 * `props.htmlData` / `props.readonly` / `props.schema` 读到最新值。
 *
 * spec: gt-c-note-table-shrink Task 4
 */
import { onBeforeUnmount, type ComputedRef, type Ref } from 'vue'
import type {
  CNoteTableHtmlData,
  CNoteTableSchema,
  ContextField,
  RowData,
  SubClass,
  SubTableSchema,
} from '../../GtCNoteTable.types'
import {
  deriveStandardFromSubClass,
  deriveSubClassFromStandard,
  genRowId,
} from '../cnoteHelpers'

export interface UseCNotePersistOptions {
  /** 响应式 props 对象本身（不可解构副本，否则 htmlData/schema 读到旧值） */
  props: {
    wpId: string
    sheetName: string
    schema: CNoteTableSchema
    htmlData: CNoteTableHtmlData
    readonly?: boolean
  }
  subTableData: Ref<Record<string, RowData[]>>
  hiddenSubtables: Ref<string[]>
  currentStandardSubClass: Ref<SubClass>
  contextData: Ref<Record<string, any>>
  activeCollapse: Ref<string[]>
  /** 附注章节号（持久化上下文契约的一部分；同步逻辑在 shell 内消费） */
  sectionId: Ref<string>
  allSubTables: ComputedRef<SubTableSchema[]> | Ref<SubTableSchema[]>
  contextFields: ComputedRef<ContextField[]> | Ref<ContextField[]>
  visibleSubTables: ComputedRef<SubTableSchema[]> | Ref<SubTableSchema[]>
  labelColumnField: (st: SubTableSchema) => string | null
  emit: (e: 'save', data: CNoteTableHtmlData) => void
}

export function useCNotePersist(opts: UseCNotePersistOptions) {
  const {
    props,
    subTableData,
    hiddenSubtables,
    currentStandardSubClass,
    contextData,
    activeCollapse,
    allSubTables,
    contextFields,
    visibleSubTables,
    labelColumnField,
    emit,
  } = opts

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Init / Sync ───────────────────────────────────────────────────────────

  function initData() {
    const data = props.htmlData ?? {}

    // sub_table_data
    const stIn = data.sub_table_data && typeof data.sub_table_data === 'object'
      ? data.sub_table_data
      : {}
    const result: Record<string, RowData[]> = {}
    for (const st of allSubTables.value) {
      const rows = (stIn as Record<string, any>)[st.id]
      if (Array.isArray(rows)) {
        result[st.id] = rows.map(r => {
          const cleaned: RowData = { ...r }
          if (!cleaned._row_id && st.type === 'dynamic_rows') {
            cleaned._row_id = genRowId()
          }
          return cleaned
        })
      } else {
        // 静态行预填充：把 static_rows[] 转成 row（首次加载）
        const initRows: RowData[] = []
        if (st.type === 'static_rows' && Array.isArray(st.static_rows)) {
          const labelField = labelColumnField(st)
          for (const def of st.static_rows) {
            const row: RowData = { id: def.id }
            if (labelField) row[labelField] = def.label
            initRows.push(row)
          }
        }
        result[st.id] = initRows
      }
    }
    subTableData.value = result

    // hidden_subtables（合并 schema 默认值 + 数据持久化值）
    const hidden = Array.isArray(data.hidden_subtables) ? data.hidden_subtables : []
    const defHidden = props.schema?.hidden_subtables?.default ?? []
    hiddenSubtables.value = Array.from(new Set([...defHidden, ...hidden]))

    // current_standard
    const std = (data.current_standard as string) || (props.schema?.applicable_standard as string) || ''
    currentStandardSubClass.value = deriveSubClassFromStandard(std)

    // context（金额单位等）
    const ctxIn = data.context && typeof data.context === 'object' ? data.context : {}
    const ctxOut: Record<string, any> = { _current_standard: std }
    for (const f of contextFields.value) {
      ctxOut[f.name] = (ctxIn as Record<string, any>)[f.name] ?? f.default ?? ''
    }
    contextData.value = ctxOut

    // 默认展开所有可见子表
    activeCollapse.value = visibleSubTables.value.map(st => st.id)
  }

  // ─── Save payload + debounce ─────────────────────────────────────────────

  function buildSavePayload(): CNoteTableHtmlData {
    const ctx: Record<string, any> = {}
    for (const k of Object.keys(contextData.value)) {
      if (k.startsWith('_')) continue
      ctx[k] = contextData.value[k]
    }
    const currentStandard = deriveStandardFromSubClass(
      currentStandardSubClass.value,
      contextData.value._current_standard as string,
    )
    // Strip internal markers from rows before persist
    const cleanedSubTables: Record<string, RowData[]> = {}
    for (const [id, rows] of Object.entries(subTableData.value)) {
      cleanedSubTables[id] = rows.map(r => {
        const out: RowData = {}
        for (const [k, v] of Object.entries(r)) {
          if (k === '_label' || k === '_is_grand_total' || k === '_is_subtotal' || k === '_indent') {
            continue
          }
          out[k] = v
        }
        return out
      })
    }
    return {
      ...(props.htmlData || {}),
      sub_table_data: cleanedSubTables,
      hidden_subtables: [...hiddenSubtables.value],
      current_standard: currentStandard,
      context: ctx,
    }
  }

  function debounceSave() {
    if (props.readonly) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      emit('save', buildSavePayload())
    }, 1500)
  }

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
  })

  return { initData, buildSavePayload, debounceSave }
}
