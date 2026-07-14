<template>
  <div class="g2-interest-receivable">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div class="g2-interest-receivable-toolbar">
        <el-segmented
          v-if="isHtmlSheet"
          v-model="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
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

      <!-- G2A 程序表（对齐 D4A） -->
      <CycleTabProcedure
        v-else-if="currentSheet === 'G2A'"
        sheet-code="G2A"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G2-1 审定表 -->
      <G2TabAdjudication
        v-else-if="currentSheet === 'G2-1'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <!-- G2-2 明细表 -->
      <G2TabDetail
        v-else-if="currentSheet === 'G2-2'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <!-- G2-3 坏账准备明细 -->
      <G2TabBadDebtDetail
        v-else-if="currentSheet === 'G2-3'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <!-- G2-4 调整分录 → OnlyOffice（简单表格） -->
      <GtOnlyOfficeSheet
        v-else-if="currentSheet === 'G2-4'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- G2-5 利息测算表 -->
      <G2TabInterestCalc
        v-else-if="currentSheet === 'G2-5'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <!-- G2-6 长期未收回检查 -->
      <G2TabOverdueCheck
        v-else-if="currentSheet === 'G2-6'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <!-- G2-7 坏账准备测算（2区段Tab） -->
      <G2TabECLCalc
        v-else-if="currentSheet === 'G2-7'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <!-- G2-8 凭证检查表（借方/贷方区块） -->
      <G2TabVoucherCheck
        v-else-if="currentSheet === 'G2-8'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <!-- 附注披露(上市) -->
      <G2TabDisclosureListed
        v-else-if="currentSheet === '附注上市'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <!-- 附注披露(国企) -->
      <G2TabDisclosureSOE
        v-else-if="currentSheet === '附注国企'"
        :all-responses="allResponsesRef"
        :is-readonly="isReadonly"
        :debounced-save="formData.debouncedSave"
      />

      <!-- 兜底：未迁移 sheet → OnlyOffice -->
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG2InterestReceivable.vue — G2 应收利息底稿主入口
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Task 1.1, 9.1~9.3
 * sheetName 分发到 G2 专属子组件（G2-1~G2-8 + 附注），G2A/G2-4/未迁移走 OnlyOffice
 * 集成：useWorkpaperVersionToolbar(autoSnapshot) + provide('openReviewDialog')
 * EventBus：监听 g2:save-items 持久化 + substantive:adjudicated(1132)
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
import { useG2IntRecFormData } from './composables/useG2IntRecFormData'
import { useG2DualMode } from './composables/useG2DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import type { ChecklistResponse } from './composables/useF1FormData'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const G2TabAdjudication = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabAdjudication.vue'))
const G2TabDetail = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabDetail.vue'))
const G2TabBadDebtDetail = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabBadDebtDetail.vue'))
const G2TabInterestCalc = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabInterestCalc.vue'))
const G2TabOverdueCheck = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabOverdueCheck.vue'))
const G2TabECLCalc = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabECLCalc.vue'))
const G2TabVoucherCheck = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabVoucherCheck.vue'))
const G2TabDisclosureListed = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabDisclosureListed.vue'))
const G2TabDisclosureSOE = defineAsyncComponent(() => import('./g2-interest-receivable/G2TabDisclosureSOE.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
}>()

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const formData = useG2IntRecFormData({ wpId: wpIdRef, projectId: projectIdRef })
const allResponsesRef = computed(() => formData.allResponses.value)
const isReadonly = computed(() => !!props.readonly)
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

provide('g2VersionTrailRef', versionTrailRef)
provide('g2OpenVersionHistory', openVersionHistory)

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  if (/附注披露/.test(name)) return name.includes('国企') ? '附注国企' : '附注上市'
  const m = name.match(/(G2A|G2-\d+)/)
  return m ? m[1] : ''
})

/** G2A + G2-1~G2-8 + 附注 为 HTML 专属组件（支持双模式） */
const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  return s === 'G2A' || /^G2-[1-8]$/.test(s) || s.startsWith('附注')
})

const dualMode = useG2DualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

// 复核对话 openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide，子组件 inject 命中祖先
provide('reloadWorkpaperData', () => formData.loadAll())

// ─── 监听 g2:save-items → 保存 + autoSnapshot ───────────────────────────────
async function handleG2SaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    for (const it of items) {
      if (it?.item_id) await formData.saveImmediate(it.item_id, it)
    }
    scheduleAutoSnapshot()
  }
}

// ─── 监听 substantive:adjudicated(1132) → 附注刷新 ──────────────────────────
function handleAdjudicated(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
  if (d?.accountCode === '1132') {
    void formData.saveImmediate('G2-1-adjudicated-amount', {
      item_id: 'G2-1-adjudicated-amount',
      conclusion: String(d.adjudicatedAmount),
      remark: null,
    })
  }
}

onMounted(async () => {
  window.addEventListener('g2:save-items', handleG2SaveItems)
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
  await formData.loadAll()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('g2:save-items', handleG2SaveItems)
  window.removeEventListener('substantive:adjudicated', handleAdjudicated)
})
</script>

<style scoped>
.g2-interest-receivable { padding: 12px; }
.loading-container { padding: 24px; }
.g2-interest-receivable-toolbar { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; }
</style>
