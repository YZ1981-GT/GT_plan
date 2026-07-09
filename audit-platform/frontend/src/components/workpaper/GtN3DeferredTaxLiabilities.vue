<template>
  <div class="n3-deferred-tax-liabilities">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div class="n3-deferred-tax-liabilities-toolbar">
        <el-segmented
          v-if="isHtmlSheet"
          v-model="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <!-- 双模式：HTML sheet 切到 OnlyOffice -->
      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- N3A 程序表 → OnlyOffice fallback（Phase 6 前暂不做HTML组件化） -->
      <GtOnlyOfficeSheet
        v-else-if="currentSheet === 'N3A'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- 底稿目录 -->
      <N3TabIndex
        v-else-if="currentSheet === 'N3' || currentSheet === '底稿目录'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- N3-1 审定表（负债类，78公式，期末余额） -->
      <N3TabAdjudication
        v-else-if="currentSheet === 'N3-1'"
        :all-responses="allResponsesRef"
        :wp-id="wpIdRef"
        :project-id="projectIdRef"
        :is-readonly="isReadonly"
      />

      <!-- N3-2 明细表（14列14公式，应纳税暂时性差异×税率） -->
      <N3TabDetail
        v-else-if="currentSheet === 'N3-2'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- N3-3 调整分录 -->
      <N3TabAdjustment
        v-else-if="currentSheet === 'N3-3'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- 附注披露 -->
      <N3TabDisclosure
        v-else-if="currentSheet === '附注' || currentSheet === 'disclosure'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- 兜底：未迁移 sheet → OnlyOffice fallback -->
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtN3DeferredTaxLiabilities.vue — N3 递延所得税负债底稿主入口
 *
 * Spec: .kiro/specs/n3-deferred-tax-liabilities/ Task 1.1
 * 科目: 2901递延所得税负债（负债类/贷方）
 * sheetName 分发到 N3 专属子组件（N3-1~N3-3），N3A 走 OnlyOffice 兜底
 * 集成：useWorkpaperVersionToolbar(autoSnapshot on save) + provide('openReviewDialog')
 * EventBus：substantive:adjudicated(2901) / deferred-tax:liability-updated → N5
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, defineAsyncComponent } from 'vue'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'

// ─── defineAsyncComponent lazy 加载子组件 ────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const N3TabIndex = defineAsyncComponent(() => import('./n3/core/N3TabIndex.vue'))
const N3TabAdjudication = defineAsyncComponent(() => import('./n3/core/N3TabAdjudication.vue'))
const N3TabDetail = defineAsyncComponent(() => import('./n3/core/N3TabDetail.vue'))
const N3TabAdjustment = defineAsyncComponent(() => import('./n3/core/N3TabAdjustment.vue'))
const N3TabDisclosure = defineAsyncComponent(() => import('./n3/core/N3TabDisclosure.vue'))

// ─── Props ───────────────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
}>()

// ─── 状态 ────────────────────────────────────────────────────────────────────
const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const allResponses = ref<Map<string, any>>(new Map())
const allResponsesRef = computed(() => allResponses.value)
const isReadonly = computed(() => !!props.readonly)
const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
const { versionTrailRef } = versionToolbar

// ─── 双模式 ──────────────────────────────────────────────────────────────────
const dualMode = {
  currentMode: ref<'html' | 'onlyoffice'>('html'),
  modeOptions: [
    { label: 'HTML', value: 'html' },
    { label: 'OnlyOffice', value: 'onlyoffice' },
  ],
  isOoAvailable: ref(true),
  onModeChange: () => {},
}

// ─── sheetName 正则提取编码 ──────────────────────────────────────────────────
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 匹配 N3A, N3-1~N3-3, N3
  const m = name.match(/(N3A|N3-\d+|N3)/)
  if (m) return m[1]
  if (name.includes('底稿目录')) return '底稿目录'
  if (name.includes('附注') || name.includes('披露')) return '附注'
  return name
})

/** N3-1~N3-3 + 附注 为 HTML 专属组件渲染的 sheet（支持双模式切换）；N3A 走 OnlyOffice */
const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return /^N3-\d+$/.test(s) || s === 'N3' || s === '底稿目录' || s === '附注'
})

// ─── selfLoad（bundle内嵌场景 htmlData 为 null 时自加载） ─────────────────────
async function selfLoad(): Promise<void> {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
      params: { project_id: props.projectId },
    })
    const sheets = res.data?.data?.sheets || res.data?.sheets || []
    const targetSheet = sheets.find((s: any) =>
      s.sheet_name === props.sheetName || s.wp_code === props.wpCode,
    )
    if (targetSheet?.html_data) {
      // 解析 checklist_responses 到 allResponses map
      const responses = targetSheet.html_data?.checklist_responses || []
      const map = new Map<string, any>()
      for (const r of responses) {
        if (r?.item_id) map.set(r.item_id, r)
      }
      allResponses.value = map
    }
  } catch (e) {
    console.error('[N3] selfLoad failed:', e)
  }
}

// ─── provide openReviewDialog 供子组件 inject ────────────────────────────────
function openReviewDialog(sectionId: string): void {
  console.log('[N3] openReviewDialog:', sectionId)
}
provide('openReviewDialog', openReviewDialog)
provide('reloadWorkpaperData', selfLoad)

// ─── 生命周期 ────────────────────────────────────────────────────────────────
onMounted(async () => {
  // 如果 htmlData 为 null（selfLoad 场景），自行加载
  if (!props.htmlData) {
    await selfLoad()
  } else {
    // 从 htmlData 解析 checklist_responses
    const responses = props.htmlData?.checklist_responses || []
    const map = new Map<string, any>()
    for (const r of responses) {
      if (r?.item_id) map.set(r.item_id, r)
    }
    allResponses.value = map
  }
  isLoading.value = false

  // ─── EventBus 订阅 'disclosure:refresh' → 刷新数据 ────────────────────
  eventBus.on('disclosure:refresh' as any, onDisclosureRefresh)
})

onBeforeUnmount(() => {
  eventBus.off('disclosure:refresh' as any, onDisclosureRefresh)
})

// ─── EventBus handler: disclosure:refresh → 重新加载数据 ─────────────────────
function onDisclosureRefresh(): void {
  selfLoad()
}

// ─── 版本快照：子组件保存后触发自动快照（六大集成标准） ──────────────────────
provide('scheduleAutoSnapshot', versionToolbar.scheduleAutoSnapshot)
</script>

<style scoped>
.n3-deferred-tax-liabilities { padding: 12px; }
.loading-container { padding: 24px; }
.n3-deferred-tax-liabilities-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
