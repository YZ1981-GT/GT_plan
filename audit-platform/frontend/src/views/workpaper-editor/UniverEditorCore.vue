<script setup lang="ts">
/**
 * UniverEditorCore — Univer 编辑器核心子 SFC [workpaper-editor-shrink-phase2 §4.1]
 *
 * 组装：
 * 1. useEditorUniver() — Univer 引擎生命周期
 * 2. useEditorSave() — 保存/导出逻辑
 * 3. useWorkpaperAutoSave() — 自动保存
 * 4. CycleTriggerPanel — 左侧栏 cycle 按钮
 * 5. EditorStatusBar — 底部状态栏
 * 6. Univer 画布容器 + Sheet 导航 + prefill tooltip + cross-ref overlay + formula bar
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8
 */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useEditorUniver } from '@/composables/useEditorUniver'
import { useEditorSave } from '@/composables/useEditorSave'
import { useWorkpaperAutoSave } from '@/composables/useWorkpaperAutoSave'
import { usePrefillMarkers } from '@/composables/usePrefillMarkers'
import { useCrossModuleRefs } from '@/composables/useCrossModuleRefs'
import { useUserOverrides } from '@/composables/useUserOverrides'
import { useStaleImpact } from '@/composables/useStaleImpact'
import { type SheetNavFacadeAPI } from '@/composables/useSheetNavFacade'
import { eventBus } from '@/utils/eventBus'
import type { WorkpaperDetail } from '@/services/workpaperApi'
import type { CycleTypeFlags } from '@/composables/useCycleType'
import type { CycleDialogsAPI } from '@/composables/useCycleDialogs'
import UniverSheetNav from '@/components/workpaper/UniverSheetNav.vue'
import SheetTopTabs from '@/components/workpaper/SheetTopTabs.vue'
import GtLoadingOverlay from '@/components/common/GtLoadingOverlay.vue'
import CycleTriggerPanel from './CycleTriggerPanel.vue'
import EditorStatusBar, { type SmartTipData } from './EditorStatusBar.vue'

// ─── Props & Emits ──────────────────────────────────────────────────────────

const props = defineProps<{
  projectId: string
  wpId: string
  wpDetail: WorkpaperDetail
  canEdit: boolean
  sheetNavFacade: SheetNavFacadeAPI
  cycleType: CycleTypeFlags
  cycleDialogs: CycleDialogsAPI
  iCycle: any
  gCycle: any
  kCycle: any
  lCycle: any
  mCycle: any
  nCycle: any
  fCycle: any
}>()

const emit = defineEmits<{
  'saved': []
  'dirty-change': [dirty: boolean]
  'sheet-switch': [sheetId: string]
  'locate-cell': [payload: { sheetName?: string; cellRef: string }]
}>()

const router = useRouter()

// ─── Univer 引擎生命周期 ────────────────────────────────────────────────────

const univerContainer = ref<HTMLElement | null>(null)
const wpDetailRef = computed(() => props.wpDetail)
const projectIdComputed = computed(() => props.projectId)
const wpIdComputed = computed(() => props.wpId)

const {
  univerAPI,
  loading,
  loadingHint,
  loadErrorState,
  loadErrorMessage,
  dirty,
  loadedFromXlsx,
  fileOpenedAt,
  initUniver,
  dispose,
} = useEditorUniver({
  containerRef: univerContainer,
  projectId: projectIdComputed,
  wpId: wpIdComputed,
  wpDetail: wpDetailRef as any,
  sheetNavFacade: props.sheetNavFacade,
})

// ─── 自动保存（先实例化，供 useEditorSave 引用）────────────────────────────

// autoSave 的 onSave 回调通过闭包引用下方的 editorSave.onSave
// 利用 JS 函数 hoisting 特性：autoSave 触发时 editorSave 已完成实例化
const autoSave = useWorkpaperAutoSave(async () => {
  const ok = await onSave()
  if (!ok) {
    ElMessage.warning({ message: '自动保存失败，请手动保存', duration: 5000 })
  }
}, 60_000)

// ─── 保存/导出逻辑 ──────────────────────────────────────────────────────────

const userOverrides = useUserOverrides()
const staleImpact = useStaleImpact(computed(() => props.wpDetail?.wp_code?.split('-')[0] || ''))
const hasPrefillMapping = ref(true)
const showStaleImpactPanel = ref(false)

const {
  saving,
  submitting,
  syncLoading,
  prefillLoading,
  exportingPdf,
  onSave,
  onSubmitForReview,
  onSyncStructure,
  onRefreshPrefill,
  onDownload,
  onExportPdf,
  onUpload,
} = useEditorSave({
  projectId: projectIdComputed,
  wpId: wpIdComputed,
  wpDetail: wpDetailRef as any,
  univerAPI,
  dirty,
  userOverrides,
  staleImpact,
  hasPrefillMapping,
  autoSave,
  initUniver,
  loadedFromXlsx,
  fileOpenedAt,
  loading,
  showStaleImpactPanel,
})

const autoSaveMsg = computed(() => {
  if (autoSave.saving.value) return '保存中...'
  if (autoSave.lastSavedAt.value) {
    const sec = Math.round((Date.now() - autoSave.lastSavedAt.value.getTime()) / 1000)
    if (sec < 5) return '已自动保存'
  }
  return ''
})

// ─── dirty 同步到 Shell + autoSave ──────────────────────────────────────────

watch(dirty, (val) => {
  emit('dirty-change', val)
  if (val) {
    autoSave.markDirty()
  }
})

// ─── saved 事件 → Shell 刷新 wpDetail ───────────────────────────────────────

// 监听 eventBus 的 workpaper:saved 事件（由 useEditorSave 内部触发）
// 转发为 emit('saved') 通知 Shell
eventBus.on('workpaper:saved', (payload: any) => {
  if (payload?.wpId === props.wpId) {
    emit('saved')
  }
})

// ─── Sheet 导航 ─────────────────────────────────────────────────────────────

const sheetNavCollapsed = ref(false)

function onSwitchSheet(sheetId: string) {
  props.sheetNavFacade.switchTo(sheetId)
  emit('sheet-switch', sheetId)
}

// ─── Prefill tooltip + Cross-ref overlay + Formula bar ──────────────────────

const prefillMarkers = usePrefillMarkers()
const crossModuleRefs = useCrossModuleRefs(
  computed(() => props.wpDetail?.wp_code || ''),
  projectIdComputed,
)
// 保留实例引用（内部 watchers 需要 composable 存活）
void prefillMarkers
void crossModuleRefs

const prefillTooltip = ref<{ visible: boolean; text: string; x: number; y: number }>({
  visible: false, text: '', x: 0, y: 0,
})
const formulaBarText = ref('')
const crossRefTags = ref<Array<{ id: string; label: string; color: string; x: number; y: number; route: string }>>([])

// ─── 智能提示 ───────────────────────────────────────────────────────────────

const smartTip = ref<SmartTipData | null>(null)

// ─── 加载失败操作 ───────────────────────────────────────────────────────────

function goBack() {
  router.push({
    name: 'WorkpaperList',
    params: { projectId: props.projectId },
  })
}

function goToLifecycle() {
  router.push({
    name: 'WorkpaperList',
    params: { projectId: props.projectId },
    query: { tab: 'lifecycle' },
  })
}

function onRetryLoad() {
  loadErrorState.value = null
  loadErrorMessage.value = ''
  loading.value = true
  initUniver()
}

// ─── locate-cell 事件监听 ───────────────────────────────────────────────────

eventBus.on('workpaper:locate-cell', (payload: any) => {
  if (payload?.wpId === props.wpId) {
    emit('locate-cell', { sheetName: payload.sheetName, cellRef: payload.cellRef })
    // 如果有 sheetName，先切换到对应 sheet
    if (payload.sheetName && univerAPI.value) {
      const workbook = univerAPI.value.getActiveWorkbook?.()
      if (workbook) {
        const sheets = workbook.getSheets?.() || []
        const target = sheets.find((s: any) => s.getSheetName?.() === payload.sheetName || s.getName?.() === payload.sheetName)
        if (target) {
          workbook.setActiveSheet?.(target)
        }
      }
    }
  }
})

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  initUniver()
})

onUnmounted(() => {
  dispose()
  eventBus.off('workpaper:saved')
  eventBus.off('workpaper:locate-cell')
})

// ─── Expose for Shell (toolbar actions) ─────────────────────────────────────

defineExpose({
  onSave,
  onSubmitForReview,
  onSyncStructure,
  onRefreshPrefill,
  onDownload,
  onExportPdf,
  onUpload,
  saving,
  submitting,
  syncLoading,
  prefillLoading,
  exportingPdf,
  dirty,
  univerAPI,
})
</script>

<template>
  <div class="gt-wp-editor-main">
    <!-- Loading overlay -->
    <GtLoadingOverlay
      :visible="loading"
      text="正在加载底稿..."
      :hint="loadingHint"
      :size="32"
    />

    <!-- 加载失败友好引导 -->
    <div v-if="!loading && loadErrorState" class="gt-wp-editor-error-overlay">
      <div class="gt-wp-editor-error-card">
        <div class="gt-wp-editor-error-icon">
          <span v-if="loadErrorState === 'no_file'">📄</span>
          <span v-else-if="loadErrorState === 'no_index'">🔍</span>
          <span v-else-if="loadErrorState === 'invalid_id'">⚠️</span>
          <span v-else>❌</span>
        </div>
        <div class="gt-wp-editor-error-title">
          <template v-if="loadErrorState === 'no_file'">底稿文件尚未生成</template>
          <template v-else-if="loadErrorState === 'no_index'">底稿不存在</template>
          <template v-else-if="loadErrorState === 'invalid_id'">底稿 ID 不合法</template>
          <template v-else>加载底稿失败</template>
        </div>
        <div class="gt-wp-editor-error-message">{{ loadErrorMessage }}</div>
        <div class="gt-wp-editor-error-actions">
          <el-button size="small" @click="goBack">返回底稿列表</el-button>
          <el-button
            v-if="loadErrorState === 'no_file'"
            size="small"
            type="primary"
            @click="goToLifecycle"
          >前往生命周期</el-button>
          <el-button
            v-if="loadErrorState === 'error'"
            size="small"
            type="primary"
            @click="onRetryLoad"
          >重试</el-button>
        </div>
      </div>
    </div>

    <!-- 左侧 Sheet 导航 -->
    <div v-show="!loading" class="gt-wp-editor-left-col">
      <UniverSheetNav
        :groups="sheetNavFacade.groups.value"
        :active-sheet-id="sheetNavFacade.activeSheetId.value"
        :total-count="sheetNavFacade.totalCount.value"
        :collapsed="sheetNavCollapsed"
        @switch="onSwitchSheet"
        @toggle-collapsed="sheetNavCollapsed = !sheetNavCollapsed"
      />

      <!-- Cycle trigger 按钮面板 -->
      <CycleTriggerPanel
        :wp-detail="wpDetail"
        :cycle-type="cycleType"
        :cycle-dialogs="cycleDialogs"
        :sheet-nav-active-id="sheetNavFacade.activeSheetId.value"
        :i-cycle="iCycle"
        :g-cycle="gCycle"
        :k-cycle="kCycle"
        :l-cycle="lCycle"
        :m-cycle="mCycle"
        :n-cycle="nCycle"
        :f-cycle="fCycle"
      />
    </div>

    <!-- 中间内容区：顶部 sheet tabs + Univer 画布 -->
    <div class="gt-wp-editor-center-col">
      <!-- 顶部水平 sheet 切换栏 -->
      <SheetTopTabs
        :sheets="sheetNavFacade.flatSheets.value"
        :active-sheet-id="sheetNavFacade.activeSheetId.value"
        @switch="onSwitchSheet"
      />
      <!-- Univer 画布容器 -->
      <div class="gt-wp-editor-univer-wrapper">
        <div ref="univerContainer" class="gt-wp-editor-univer"></div>
      </div>
    </div>

    <!-- Prefill cell hover tooltip -->
    <div
      v-if="prefillTooltip.visible"
      class="gt-wp-prefill-tooltip"
      :style="{ left: prefillTooltip.x + 'px', top: prefillTooltip.y + 'px' }"
    >
      {{ prefillTooltip.text }}
    </div>

    <!-- Cross-module reference overlay -->
    <div class="gt-cross-ref-overlay" v-if="crossRefTags.length > 0">
      <div
        v-for="tag in crossRefTags"
        :key="tag.id"
        class="gt-cross-ref-tag"
        :style="{ left: tag.x + 'px', top: tag.y + 'px', backgroundColor: tag.color }"
        @click="router.push(tag.route)"
        :title="tag.label"
      >
        {{ tag.label }}
      </div>
    </div>
  </div>

  <!-- Formula bar -->
  <div v-if="formulaBarText" class="gt-wp-formula-bar">
    <span class="gt-wp-formula-bar-label">ƒ</span>
    <span class="gt-wp-formula-bar-text">{{ formulaBarText }}</span>
  </div>

  <!-- 底部状态栏 -->
  <EditorStatusBar
    :wp-detail="wpDetail"
    :dirty="dirty"
    :auto-save-msg="autoSaveMsg"
    :smart-tip="smartTip"
  />
</template>
