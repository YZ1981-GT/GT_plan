<template>
  <div class="j3-share-based-payment">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- 双模式切换工具栏 -->
      <div v-if="showModeToolbar" class="j3-mode-toolbar">
        <el-segmented v-model="renderMode" :options="renderModeOptions" size="small" />
        <el-tag v-if="!dualMode.ooAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <!-- OnlyOffice 模式 -->
      <GtOnlyOfficeSheet
        v-if="renderMode === 'onlyoffice'"
        :key="ooSheetName"
        :wp-id="props.wpId"
        :sheet-name="ooSheetName"
        :project-id="props.projectId"
        :readonly="isReadonly"
        @fallback="onOoFallback"
      />

      <template v-else>
      <!-- 底稿目录（默认页） -->
      <J3TabIndex
        v-if="!currentSheet || currentSheet === 'J3'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="props.isReadonly"
        @navigate-sheet="handleNavigateSheet"
      />

      <!-- J3A 程序表（整册专属组件内分发，对齐 H1A/L1A） -->
      <CycleTabProcedure
        v-else-if="currentSheet === 'J3A'"
        sheet-code="J3A"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="props.isReadonly"
      />

      <!-- J3-1 股份支付情况表 -->
      <J3TabDetail
        v-else-if="currentSheet === 'J3-1'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :year="props.year"
        :html-data="props.htmlData"
        :all-responses="allResponses"
        :is-readonly="props.isReadonly"
        :save-immediate="handleChildSave"
      />

      <!-- J3-2 股份支付检查表 -->
      <J3TabCheck
        v-else-if="currentSheet === 'J3-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :year="props.year"
        :html-data="props.htmlData"
        :all-responses="allResponses"
        :is-readonly="props.isReadonly"
        :save-immediate="handleChildSave"
      />

      <!-- 兜底 OnlyOffice -->
      <div v-else class="j3-sheet-placeholder">
        <el-empty :description="`J3 未识别的 sheet: ${currentSheet}（将使用 OnlyOffice）`" />
      </div>

      </template><!-- end HTML mode -->

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtJ3ShareBasedPayment — J3 股份支付主入口组件
 *
 * J3 无独立科目（费用端走 K8/K9，权益端走 M4，现金端走 J1）。
 * persistence三连环：selfLoad + allResponses Map + handleChildSave
 *
 * Spec: .kiro/specs/j3-share-based-payment/
 */
import { computed, ref, onMounted, defineAsyncComponent, provide, toRef } from 'vue'
import { useWorkpaperVersionToolbar } from '../composables/useWorkpaperVersionToolbar'
import { useJ3EntryDualMode, type J3RenderMode } from '../composables/useJ3EntryDualMode'
import CycleTabProcedure from '../shared/CycleTabProcedure.vue'
import GtOnlyOfficeSheet from '../GtOnlyOfficeSheet.vue'
import http from '@/utils/http'

// defineAsyncComponent 懒加载
const GtWpVersionTrail = defineAsyncComponent(() => import('../version-trail/GtWpVersionTrail.vue'))
const J3TabIndex = defineAsyncComponent(() => import('./core/J3TabIndex.vue'))
const J3TabDetail = defineAsyncComponent(() => import('./core/J3TabDetail.vue'))
const J3TabCheck = defineAsyncComponent(() => import('./core/J3TabCheck.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  year?: string | number
  sheetName?: string
  htmlData?: Record<string, unknown> | null
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  save: []
  completed: []
  'navigate-sheet': [sheetName: string]
}>()

const isLoading = ref(true)

/** 当前 sheet 名（从 props.sheetName 提取编码） */
const currentSheet = computed(() => {
  const sn = props.sheetName || ''
  if (/\bJ3A\b/.test(sn) || sn.includes('实质性程序表')) return 'J3A'
  const m = sn.match(/(J3-\d+)/)
  if (m) return m[1]
  if (sn.includes('目录') || sn === 'J3') return 'J3'
  return sn
})

// ─── Persistence: allResponses Map ──────────────────────────────────────────
const allResponses = ref<Map<string, { item_id: string; conclusion: string | null; remark: string | null }>>(new Map())

async function selfLoad() {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const items = res.data?.data || res.data || []
    if (Array.isArray(items)) {
      const map = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
      for (const it of items) {
        if (it.item_id) map.set(it.item_id, { item_id: it.item_id, conclusion: it.conclusion ?? null, remark: it.remark ?? null })
      }
      allResponses.value = map
    }
  } catch { /* silent */ }
  if (props.htmlData) {
    const snapshot = ((props.htmlData as any).responses_snapshot || (props.htmlData as any).checklist_responses) as any
    if (Array.isArray(snapshot)) {
      for (const it of snapshot) {
        if (it.item_id && !allResponses.value.has(String(it.item_id))) {
          allResponses.value.set(String(it.item_id), { item_id: String(it.item_id), conclusion: it.conclusion ?? null, remark: it.remark ?? null })
        }
      }
    }
  }
}

let saveTimer: ReturnType<typeof setTimeout> | null = null
async function handleChildSave(items: Array<{ item_id: string; conclusion: string | null; remark: string | null }>): Promise<void> {
  for (const it of items) allResponses.value.set(it.item_id, it)
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    try {
      await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
      scheduleAutoSnapshot()
    } catch { /* silent */ }
  }, 800)
}

// ─── 版本追踪 ────────────────────────────────────────────────────────────────
const versionToolbar = useWorkpaperVersionToolbar({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const { versionTrailRef, openVersionHistory, scheduleAutoSnapshot } = versionToolbar
provide('j3VersionTrailRef', versionTrailRef)
provide('j3OpenVersionHistory', openVersionHistory)

// ─── 双模式切换（HTML ↔ OnlyOffice） ─────────────────────────────────────────
const KNOWN_HTML_SHEETS = new Set(['J3', 'J3A', 'J3-1', 'J3-2'])

const showModeToolbar = computed(() =>
  KNOWN_HTML_SHEETS.has(currentSheet.value) || !currentSheet.value,
)

const dualMode = useJ3EntryDualMode({
  wpId: toRef(props, 'wpId'),
  currentSheet,
  reloadAllResponses: selfLoad,
})

const ooSheetName = computed(() =>
  dualMode.resolveOoSheetName() || props.sheetName || 'J3-1',
)

const renderMode = computed({
  get: () => dualMode.mode.value,
  set: (v: J3RenderMode) => { void dualMode.switchMode(v) },
})

const renderModeOptions = computed(() => [
  { label: '结构化视图', value: 'html' as const },
  {
    label: '在线编辑',
    value: 'onlyoffice' as const,
    disabled: !dualMode.ooAvailable.value,
  },
])

function onOoFallback(): void {
  void dualMode.switchMode('html')
}

function handleNavigateSheet(sheetName: string) {
  emit('navigate-sheet', sheetName)
}

onMounted(async () => {
  await selfLoad()
  isLoading.value = false
})
</script>

<style scoped>
.j3-share-based-payment {
  padding: 16px;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.j3-mode-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.j3-sheet-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}
</style>
