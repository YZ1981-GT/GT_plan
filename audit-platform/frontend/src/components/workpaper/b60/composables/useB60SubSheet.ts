/**
 * useB60SubSheet — B60 结构化子底稿数据持久化
 *
 * 每个 section 打包成一条 checklist_responses：
 *   item_id = {code}-{sectionId}, conclusion=null, remark=JSON
 *
 * 直接读写子底稿自身 wp_id 的 /checklist-responses 端点（子底稿有独立 wp_id）。
 *
 * Spec: b60-strategy-rework（直接修复）
 */
import { ref, reactive, onMounted, onScopeDispose, type Ref } from 'vue'
import http from '@/utils/http'
import { ElMessage } from 'element-plus'
import type { B60SubSheetSchema, B60Section } from '../constants/subSheetSchemas'

export interface UseB60SubSheetOptions {
  wpId: Ref<string>
  schema: B60SubSheetSchema
}

type SectionData = Record<string, any>

export function useB60SubSheet(options: UseB60SubSheetOptions) {
  const { wpId, schema } = options

  const store = reactive<Record<string, SectionData>>({})
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const loading = ref(false)

  let _timer: ReturnType<typeof setTimeout> | null = null
  const _dirty = new Set<string>()
  let _failures = 0
  const MAX_FAILURES = 3

  function _itemId(sectionId: string): string {
    return `${schema.code}-${sectionId}`
  }

  function _emptyData(section: B60Section): SectionData {
    if (section.kind === 'fields') return {}
    if (section.kind === 'questionnaire') return {}
    // table
    if (section.fixedRows && section.fixedRows.length > 0) {
      return { rows: section.fixedRows.map((r) => ({ ...r })) }
    }
    return { rows: [] }
  }

  function _initStore(): void {
    for (const section of schema.sections) {
      if (!(section.id in store)) {
        store[section.id] = _emptyData(section)
      }
    }
  }

  async function load(): Promise<void> {
    if (!wpId.value) return
    loading.value = true
    try {
      const { data } = await http.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const items: any[] = Array.isArray(data) ? data : (data?.data || data?.items || [])
      const byId: Record<string, any> = {}
      for (const it of items) {
        if (it?.item_id) byId[it.item_id] = it
      }
      for (const section of schema.sections) {
        const rec = byId[_itemId(section.id)]
        if (rec?.remark) {
          try {
            const parsed = JSON.parse(rec.remark)
            if (parsed && typeof parsed === 'object') {
              store[section.id] = parsed
              continue
            }
          } catch { /* fall through to empty */ }
        }
        store[section.id] = _emptyData(section)
      }
    } catch {
      _initStore()
    } finally {
      loading.value = false
    }
  }

  async function _doSave(): Promise<void> {
    if (!wpId.value || _dirty.size === 0) return
    if (_failures >= MAX_FAILURES) return
    const ids = [..._dirty]
    _dirty.clear()
    saveStatus.value = 'saving'
    const items = ids.map((sectionId) => ({
      item_id: _itemId(sectionId),
      conclusion: null,
      remark: JSON.stringify(store[sectionId] ?? {}),
    }))
    try {
      await http.put(`/api/workpapers/${wpId.value}/checklist-responses`, { items })
      _failures = 0
      saveStatus.value = 'saved'
    } catch {
      _failures++
      saveStatus.value = 'unsaved'
      if (_failures >= MAX_FAILURES) {
        ElMessage.warning('保存失败，请检查网络后重试')
      } else {
        ids.forEach((id) => _dirty.add(id))
      }
    }
  }

  function _schedule(): void {
    if (_timer) clearTimeout(_timer)
    _timer = setTimeout(() => {
      _timer = null
      void _doSave()
    }, 800)
  }

  /** 标记某 section 为脏并触发防抖保存 */
  function markDirty(sectionId: string): void {
    _dirty.add(sectionId)
    saveStatus.value = 'unsaved'
    _schedule()
  }

  async function flush(): Promise<void> {
    if (_timer) { clearTimeout(_timer); _timer = null }
    if (_dirty.size > 0) await _doSave()
  }

  onMounted(() => {
    _initStore()
    void load()
  })

  onScopeDispose(() => {
    if (_timer) { clearTimeout(_timer); _timer = null }
    if (_dirty.size > 0) void _doSave()
  })

  return { store, saveStatus, loading, markDirty, flush, load }
}
