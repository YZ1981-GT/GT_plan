/**
 * 税审单表编辑状态（税务底稿、汇算申报表共用）：取值、草稿、带版本号保存。
 * 可填写格点击即改，修改先记草稿，「保存」一次提交本表全部手工值；版本冲突提示刷新，不静默覆盖。
 */
import { computed, ref, shallowRef } from 'vue'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import type { TaxInputs, TaxSheetPartValues, TaxSheetResult } from './taxWorkpaperApi'

export interface TaxSheetEditorOptions {
  projectId: () => string
  year: () => number | null
  code: () => string
  fetch: (projectId: string, year: number, code: string) => Promise<TaxSheetResult>
  save: (projectId: string, year: number, code: string, version: number, inputs: TaxInputs) => Promise<TaxSheetResult>
  /** 保存失败提示里的对象名（底稿 / 申报表） */
  label: string
}

const EMPTY_PART: TaxSheetPartValues = { source: '', values: {}, cells: {} }

export function useTaxSheetEditor(opts: TaxSheetEditorOptions) {
  const result = shallowRef<TaxSheetResult | null>(null)
  const loadingValues = ref(false)
  const valuesError = ref('')
  /** 未保存的修改：{sheet: {ref: 值}} */
  const drafts = ref<TaxInputs>({})
  const saving = ref(false)

  const draftCount = computed(() => Object.values(drafts.value).reduce((n, cells) => n + Object.keys(cells).length, 0))
  const dirty = computed(() => draftCount.value > 0)

  function partValues(source: string): TaxSheetPartValues {
    return result.value?.parts.find(p => p.source === source) ?? EMPTY_PART
  }

  let loadSeq = 0
  async function loadValues() {
    const projectId = opts.projectId()
    const year = opts.year()
    if (!year || !projectId) {
      result.value = null
      valuesError.value = year ? '' : '项目未设置审核年度，无法取数'
      return
    }
    const seq = ++loadSeq
    const code = opts.code()
    loadingValues.value = true
    valuesError.value = ''
    try {
      const data = await opts.fetch(projectId, year, code)
      if (seq === loadSeq) result.value = data
    } catch (e: any) {
      if (seq === loadSeq) {
        result.value = null
        valuesError.value = e?.response?.data?.detail || e?.message || '取数失败'
      }
    } finally {
      if (seq === loadSeq) loadingValues.value = false
    }
  }

  function reset() {
    loadSeq++
    result.value = null
    drafts.value = {}
    loadingValues.value = false
  }

  function setDraft(source: string, refName: string, value: number | string | null) {
    drafts.value = { ...drafts.value, [source]: { ...(drafts.value[source] ?? {}), [refName]: value } }
  }

  /** 已保存的手工值 + 草稿 = 本次要提交的全部手工值 */
  function mergedInputs(): TaxInputs {
    const out: TaxInputs = {}
    for (const part of result.value?.parts ?? []) {
      for (const [refName, meta] of Object.entries(part.cells)) {
        if (meta.origin !== 'input') continue
        const v = part.values[refName]
        out[part.source] ??= {}
        out[part.source][refName] = !v ? null : 'n' in v ? Number(v.n) : 's' in v ? v.s : null
      }
    }
    for (const [source, cells] of Object.entries(drafts.value)) {
      out[source] = { ...(out[source] ?? {}), ...cells }
    }
    return out
  }

  async function save(): Promise<boolean> {
    const year = opts.year()
    if (!year || !result.value) return false
    saving.value = true
    try {
      result.value = await opts.save(opts.projectId(), year, opts.code(), result.value.version, mergedInputs())
      drafts.value = {}
      ElMessage.success('已保存')
      return true
    } catch (e: any) {
      if (e?.response?.status === 409) {
        ElMessage.warning(`${opts.label}已被他人修改，请重新取数后再改`)
      } else {
        handleApiError(e, `保存${opts.label}`)
      }
      return false
    } finally {
      saving.value = false
    }
  }

  function discard() {
    drafts.value = {}
  }

  return {
    result, loadingValues, valuesError, drafts, saving, draftCount, dirty,
    partValues, loadValues, reset, setDraft, mergedInputs, save, discard,
  }
}
