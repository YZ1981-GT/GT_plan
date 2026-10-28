<script setup lang="ts">
/**
 * GtGridCell — 自定义显示的单元格（spec excel-style-table-editing ADR-6）
 *
 * 平时渲染 #display 插槽（金额单位、图标、来源标记等页面自己的显示），进入编辑才挂默认插槽里的编辑器：
 *
 * ```vue
 * <GtGridCell :editable="canEdit" :value="row.amount">
 *   <template #display><GtAmountCell :value="row.amount" :unit="unit" /></template>
 *   <el-input-number v-model="row.amount" :controls="false" @change="onChange" />
 * </GtGridCell>
 * ```
 *
 * 粘贴 / 清空 / 撤销时会把编辑器静默挂一下再写入（宿主照常收到 change）。
 * 经典编辑方式或不在表格里时，直接显示编辑器（与改造前的常驻输入框一致）。
 */
import { computed, getCurrentInstance, nextTick, onBeforeUnmount, onMounted, provide, ref, shallowRef } from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { detectCellContext } from './cellDetect'
import { stripDecorations, type CellEditorKind, type ParseResult } from './cellValue'
import {
  nextEditorId, registerEditorHandle, unregisterEditorHandle,
  type CellEditorHandle, type OpenRequest,
} from './editorHost'
import { GRID_CELL_KEY } from './gridCellContext'
import { kernelForContext } from './gridRegistry'

defineOptions({ name: 'GtGridCell' })

const props = withDefaults(defineProps<{
  /** 可编辑（默认 true）；false 时只显示 */
  editable?: boolean
  /** 复制 / 统计用文本（缺省取显示内容的可见文字） */
  text?: string
  /** 统计 / 撤销比较用的原值 */
  value?: unknown
  /** 编辑器类型（下拉 / 日期在显示态时也要按「展开选择」打开） */
  kind?: CellEditorKind
}>(), { editable: true, text: undefined, value: undefined, kind: undefined })

const instance = getCurrentInstance()!
const detected = detectCellContext(instance)
const ctx = detected && detected.kind !== 'grid-cell' ? detected : null
let prefs: ReturnType<typeof useDisplayPrefsStore> | null = null
try { prefs = useDisplayPrefsStore() } catch { prefs = null }

const inGrid = computed(() => !!ctx && prefs?.gridEditMode !== 'classic')
const editing = ref(false)
const silent = ref(false)
const hosted = shallowRef<CellEditorHandle | null>(null)
const displayRef = ref<HTMLElement | null>(null)
const id = nextEditorId()

const kernel = () => kernelForContext(ctx)

provide(GRID_CELL_KEY, {
  register: (h) => { hosted.value = h },
  unregister: (hid) => { if (hosted.value?.id === hid) hosted.value = null },
  finished: (h, value, refocus) => {
    if (h !== hosted.value || silent.value) return
    editing.value = false
    kernel()?.editorFinished(handle, value, { refocus })
  },
})

async function withSilentEditor(fn: (h: CellEditorHandle) => ParseResult | boolean | Promise<ParseResult | boolean>): Promise<ParseResult | boolean> {
  const wasOpen = editing.value
  if (!wasOpen) {
    silent.value = true
    editing.value = true
    await nextTick()
  }
  try {
    const h = hosted.value
    if (!h) return { ok: false, reason: '没有编辑器' }
    return await fn(h)
  } finally {
    if (!wasOpen) {
      editing.value = false
      silent.value = false
    }
  }
}

const handle: CellEditorHandle = {
  id,
  get kind(): CellEditorKind { return props.kind ?? hosted.value?.kind ?? 'text' },
  editable: () => props.editable,
  multiline: () => hosted.value?.multiline() ?? false,
  getText: () => props.text ?? stripDecorations(displayRef.value?.innerText ?? displayRef.value?.textContent ?? ''),
  getValue: () => (props.value !== undefined ? props.value : handle.getText()),
  isOpen: () => editing.value && !silent.value,
  async open(req: OpenRequest): Promise<boolean> {
    if (!props.editable) return false
    silent.value = false
    if (!editing.value) {
      editing.value = true
      await nextTick()
    }
    const h = hosted.value
    const ok = h ? await h.open(req) : false
    if (!ok) editing.value = false
    return ok
  },
  commit(): unknown {
    const v = hosted.value?.commit()
    editing.value = false
    return v ?? props.value
  },
  cancel(): void {
    hosted.value?.cancel()
    editing.value = false
  },
  applyText: (text: string) => withSilentEditor((h) => h.applyText(text)) as Promise<ParseResult>,
  setValue: async (v: unknown) => {
    const r = await withSilentEditor((h) => h.setValue(v))
    return r === true || (typeof r === 'object' && r.ok)
  },
}

onMounted(() => { if (ctx) registerEditorHandle(handle) })

onBeforeUnmount(() => {
  if (editing.value && !silent.value) {
    const v = hosted.value?.commit()
    kernel()?.editorFinished(handle, v, { refocus: false })
  }
  unregisterEditorHandle(id)
})

defineExpose({ handle })
</script>

<template>
  <div v-if="!inGrid && editable" class="gt-grid-cell"><slot /></div>
  <div
    v-else-if="!editing || silent || !inGrid"
    ref="displayRef"
    class="gt-cell-display gt-grid-cell"
    :class="{ 'gt-cell-display--readonly': !editable }"
    :data-gt-cell-editor="inGrid ? id : undefined"
  >
    <slot name="display">{{ text ?? '' }}</slot>
    <div v-if="silent" class="gt-grid-cell__silent"><slot /></div>
  </div>
  <div v-else class="gt-grid-cell gt-grid-cell--editing" :data-gt-cell-editor="id"><slot /></div>
</template>
