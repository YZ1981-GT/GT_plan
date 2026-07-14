<template>
  <div class="j1-employee-compensation">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- 底稿目录 -->
      <J1TabIndex v-if="currentSheet === 'J1-index'"
        :all-responses="allResponses" :is-readonly="isReadonly ?? false" />
      <!-- J1A 程序表（整册专属组件内分发，对齐 H1A/L1A） -->
      <CycleTabProcedure
        v-else-if="currentSheet === 'J1A'"
        sheet-code="J1A"
        :html-data="htmlData"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
      />
      <!-- J1-1 审定表 -->
      <J1TabAdjudication v-else-if="currentSheet === 'J1-1'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" :is-readonly="isReadonly" />
      <!-- J1-2 明细表 -->
      <J1TabDetail v-else-if="currentSheet === 'J1-2'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData"
        :all-responses="allResponses" :is-readonly="isReadonly" :save-immediate="handleChildSave" />
      <!-- J1-3 调整分录 -->
      <J1TabAdjustment v-else-if="currentSheet === 'J1-3'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData"
        :all-responses="allResponses" :is-readonly="isReadonly" />
      <!-- J1-4 月度分析表 -->
      <J1TabMonthlyAnalysis v-else-if="currentSheet === 'J1-4'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData"
        :all-responses="allResponses" :is-readonly="isReadonly" :save-immediate="handleChildSave" />
      <!-- J1-5 同行业对比 -->
      <J1TabIndustryCompare v-else-if="currentSheet === 'J1-5'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData"
        :all-responses="allResponses" :is-readonly="isReadonly" :save-immediate="handleChildSave" />
      <!-- J1-6 计提检查 -->
      <J1TabAccrualCheck v-else-if="currentSheet === 'J1-6'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData"
        :all-responses="allResponses" :is-readonly="isReadonly" :save-immediate="handleChildSave" />
      <!-- J1-7 分配检查 -->
      <J1TabAllocationCheck v-else-if="currentSheet === 'J1-7'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData"
        :all-responses="allResponses" :is-readonly="isReadonly" :save-immediate="handleChildSave" />
      <!-- J1-8 一般检查 -->
      <J1TabGeneralCheck v-else-if="currentSheet === 'J1-8'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" :is-readonly="isReadonly" />
      <!-- J1-9 非货币性福利 -->
      <J1TabNonMonetaryCheck v-else-if="currentSheet === 'J1-9'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" :is-readonly="isReadonly" />
      <!-- J1-10 辞退福利 -->
      <J1TabSeveranceCheck v-else-if="currentSheet === 'J1-10'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" :is-readonly="isReadonly" />
      <!-- 附注（上市公司） -->
      <J1TabDisclosureListed v-else-if="currentSheet === 'J1附注(上市)'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" />
      <!-- 附注（国有企业） -->
      <J1TabDisclosureSoe v-else-if="currentSheet === 'J1附注(国企)'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" />
      <!-- IPO企业薪酬审计提示（只读注意事项） -->
      <J1TabIpoTips v-else-if="currentSheet === 'IPO-tips'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" />
      <!-- 兜底 OnlyOffice -->
      <div v-else class="j1-sheet-placeholder">
        <el-empty :description="`J1 未识别的 sheet: ${currentSheet}（将使用 OnlyOffice）`" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtJ1EmployeeCompensation — J1 应付职工薪酬主入口组件
 *
 * 按 sheetName v-if 分发到各子组件（defineAsyncComponent lazy 加载）。
 * 科目2211应付职工薪酬（贷方/负债类）：期末=期初+贷方-借方
 *
 * persistence三连环：selfLoad(checklist-responses GET) + allResponses Map + handleChildSave(PUT)
 */
import { computed, ref, onMounted, onBeforeUnmount, defineAsyncComponent, provide, toRef, inject, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useChecklistPersistence,
  type ChecklistResponse,
} from '@/composables/workpaper/useChecklistPersistence'
import { collectChecklistResponses } from '@/composables/workpaper/checklistPersistenceHelpers'
import { WorkpaperRuntimeContextKey } from '../composables/useWorkpaperScaffold'
import CycleTabProcedure from '../shared/CycleTabProcedure.vue'

// ── defineAsyncComponent lazy 加载 ──────────────────────────────────────────
const J1TabIndex = defineAsyncComponent(() => import('./core/J1TabIndex.vue'))
const J1TabAdjudication = defineAsyncComponent(() => import('./core/J1TabAdjudication.vue'))
const J1TabDetail = defineAsyncComponent(() => import('./core/J1TabDetail.vue'))
const J1TabAdjustment = defineAsyncComponent(() => import('./core/J1TabAdjustment.vue'))
const J1TabMonthlyAnalysis = defineAsyncComponent(() => import('./analysis/J1TabMonthlyAnalysis.vue'))
const J1TabIndustryCompare = defineAsyncComponent(() => import('./analysis/J1TabIndustryCompare.vue'))
const J1TabAccrualCheck = defineAsyncComponent(() => import('./inspection/J1TabAccrualCheck.vue'))
const J1TabAllocationCheck = defineAsyncComponent(() => import('./inspection/J1TabAllocationCheck.vue'))
const J1TabGeneralCheck = defineAsyncComponent(() => import('./inspection/J1TabGeneralCheck.vue'))
const J1TabNonMonetaryCheck = defineAsyncComponent(() => import('./inspection/J1TabNonMonetaryCheck.vue'))
const J1TabSeveranceCheck = defineAsyncComponent(() => import('./inspection/J1TabSeveranceCheck.vue'))
const J1TabDisclosureListed = defineAsyncComponent(() => import('./core/J1TabDisclosureListed.vue'))
const J1TabDisclosureSoe = defineAsyncComponent(() => import('./core/J1TabDisclosureSoe.vue'))
const J1TabIpoTips = defineAsyncComponent(() => import('./J1TabIpoTips.vue'))

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

/** 目录页跳转（对齐 D4 目录页范式）：J1TabIndex inject 调用 → 切换到目标 sheet */
provide('jumpToSection', (sheetName: string) => emit('navigate-sheet', sheetName))

const isLoading = ref(true)

/** 当前 sheet 名（从 props.sheetName 提取） */
const currentSheet = computed(() => {
  const sn = props.sheetName || ''
  if (/\bJ1A\b/.test(sn) || sn.includes('实质性程序表')) return 'J1A'
  if (sn.includes('IPO')) return 'IPO-tips'
  const mCode = sn.match(/(J1-\d+)/)
  if (mCode) return mCode[1]
  if (sn.includes('上市')) return 'J1附注(上市)'
  if (sn.includes('国有') || sn.includes('国企')) return 'J1附注(国企)'
  if (sn.includes('目录')) return 'J1-index'
  return sn
})

// ─── Runtime Boundary + Persistence Adapter ─────────────────────────────────
const runtime = inject(WorkpaperRuntimeContextKey, null)
const persistence = useChecklistPersistence({
  wpId: toRef(props, 'wpId'),
  projectId: computed(() => props.projectId || undefined),
  debounceMs: 800,
  onSaved: () => runtime?.version.scheduleAutoSnapshot(),
})
const allResponses = persistence.responses

/** selfLoad：render-config 快照兼容基线 + GET 服务端为准，合并快照未返回的 section。 */
async function selfLoad(): Promise<void> {
  const snapshot = collectChecklistResponses(
    (props.htmlData as any)?.responses_snapshot,
    (props.htmlData as any)?.allResponses,
    (props.htmlData as any)?.checklist_responses,
  )
  if (snapshot.length > 0) persistence.hydrate(snapshot)
  const fallback = new Map(allResponses.value)
  try {
    await persistence.load()
  } catch {
    if (fallback.size === 0) ElMessage.warning('J1 保存数据加载失败，请刷新后重试')
  }
  const merged = new Map(allResponses.value)
  for (const [itemId, item] of fallback) {
    if (!merged.has(itemId)) merged.set(itemId, item)
  }
  persistence.hydrate(merged)
}

/**
 * 子 tab 已完成业务序列化；统一交给 Adapter 管理逐 item debounce/flush/error。
 * 返回 Promise 以兼容子 composable 的 `saveImmediate(items).catch(...)` 契约。
 */
async function handleChildSave(items: ChecklistResponse[]): Promise<void> {
  for (const { item_id, ...patch } of items) {
    persistence.saveDebounced(item_id, patch)
  }
}

// 整册专属组件在 sheet 切换时不卸载主入口；主动 flush 待保存 section。
watch(currentSheet, async (nextSheet, prevSheet) => {
  if (nextSheet === prevSheet) return
  try {
    await persistence.flush()
  } catch {
    ElMessage.error('J1 切换底稿时保存失败，数据已保留，可返回后重试')
  }
})

onBeforeUnmount(() => { void persistence.flush().catch(() => undefined) })

onMounted(async () => {
  await selfLoad()
  isLoading.value = false
})
</script>

<style scoped>
.j1-employee-compensation {
  padding: 0;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.j1-sheet-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}
</style>
