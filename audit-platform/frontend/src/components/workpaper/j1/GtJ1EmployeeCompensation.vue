<template>
  <div class="j1-employee-compensation">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- 底稿目录 -->
      <J1TabIndex v-if="currentSheet === 'J1-index'" />
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
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" />
      <!-- J1-2 明细表 -->
      <J1TabDetail v-else-if="currentSheet === 'J1-2'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" />
      <!-- J1-3 调整分录 -->
      <J1TabAdjustment v-else-if="currentSheet === 'J1-3'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" />
      <!-- J1-4 月度分析表 -->
      <J1TabMonthlyAnalysis v-else-if="currentSheet === 'J1-4'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" />
      <!-- J1-5 同行业对比 -->
      <J1TabIndustryCompare v-else-if="currentSheet === 'J1-5'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" />
      <!-- J1-6 计提检查 -->
      <J1TabAccrualCheck v-else-if="currentSheet === 'J1-6'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" />
      <!-- J1-7 分配检查 -->
      <J1TabAllocationCheck v-else-if="currentSheet === 'J1-7'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" />
      <!-- J1-8 一般检查 -->
      <J1TabGeneralCheck v-else-if="currentSheet === 'J1-8'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" />
      <!-- J1-9 非货币性福利 -->
      <J1TabNonMonetaryCheck v-else-if="currentSheet === 'J1-9'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" />
      <!-- J1-10 辞退福利 -->
      <J1TabSeveranceCheck v-else-if="currentSheet === 'J1-10'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" />
      <!-- 附注（上市公司） -->
      <J1TabDisclosureListed v-else-if="currentSheet === 'J1附注(上市)'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" />
      <!-- 附注（国有企业） -->
      <J1TabDisclosureSoe v-else-if="currentSheet === 'J1附注(国企)'"
        :wp-id="wpId" :project-id="projectId" :html-data="htmlData" />
      <!-- 兜底 OnlyOffice -->
      <div v-else class="j1-sheet-placeholder">
        <el-empty :description="`J1 未识别的 sheet: ${currentSheet}（将使用 OnlyOffice）`" />
      </div>

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
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
 * 12个子组件全部采用 defineAsyncComponent 实现按需加载。
 */
import { computed, ref, onMounted, defineAsyncComponent, provide, toRef } from 'vue'
import { useWorkpaperVersionToolbar } from '../composables/useWorkpaperVersionToolbar'
import CycleTabProcedure from '../shared/CycleTabProcedure.vue'

// ── defineAsyncComponent lazy 加载 ──────────────────────────────────────────
const GtWpVersionTrail = defineAsyncComponent(() => import('../version-trail/GtWpVersionTrail.vue'))
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

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  year?: string | number
  sheetName?: string
  htmlData?: Record<string, unknown> | null
  isReadonly?: boolean
}>()

defineEmits<{
  save: []
  completed: []
  'navigate-sheet': [sheetName: string]
}>()

const isLoading = ref(true)

/** 当前 sheet 名（从 props.sheetName 提取） */
const currentSheet = computed(() => {
  const sn = props.sheetName || ''
  // 程序表 J1A（须先于 J1-\d+，避免误匹配）
  if (/\bJ1A\b/.test(sn) || sn.includes('实质性程序表')) return 'J1A'
  // 匹配 J1-X 格式
  const mCode = sn.match(/(J1-\d+)/)
  if (mCode) return mCode[1]
  // 匹配附注特殊名称
  if (sn.includes('上市')) return 'J1附注(上市)'
  if (sn.includes('国有') || sn.includes('国企')) return 'J1附注(国企)'
  // 底稿目录
  if (sn.includes('目录')) return 'J1-index'
  return sn
})

// ─── 版本追踪 useWorkpaperVersionToolbar ─────────────────────────────────────
const versionToolbar = useWorkpaperVersionToolbar({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const { versionTrailRef, openVersionHistory, scheduleAutoSnapshot } = versionToolbar
provide('j1VersionTrailRef', versionTrailRef)
provide('j1OpenVersionHistory', openVersionHistory)

onMounted(async () => {
  // 轻量初始化 — selfLoad 由各子组件自行管理
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
