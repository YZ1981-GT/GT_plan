<template>
  <div class="j2-defined-benefit-plan">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- 底稿目录 -->
      <J2TabIndex
        v-if="currentSheet === '底稿目录'"
        :wp-id="wpId"
        :project-id="projectId"
      />
      <!-- J2A 程序表（整册专属组件内分发，对齐 H1A/L1A） -->
      <CycleTabProcedure
        v-else-if="currentSheet === 'J2A'"
        sheet-code="J2A"
        :html-data="htmlData"
        :wp-id="wpId"
        :project-id="projectId"
        :is-readonly="isReadonly"
      />
      <!-- J2-1 审定表 -->
      <J2TabAdjudication
        v-else-if="currentSheet === 'J2-1'"
        :wp-id="wpId"
        :project-id="projectId"
        :html-data="htmlData"
        :is-readonly="isReadonly"
        @save="onSave"
      />
      <!-- J2-2 明细表 -->
      <J2TabDetail
        v-else-if="currentSheet === 'J2-2'"
        :wp-id="wpId"
        :project-id="projectId"
        :html-data="htmlData"
        :is-readonly="isReadonly"
      />
      <!-- J2-3 调整分录 -->
      <J2TabAdjustment
        v-else-if="currentSheet === 'J2-3'"
        :wp-id="wpId"
        :project-id="projectId"
        :html-data="htmlData"
        :is-readonly="isReadonly"
      />
      <!-- J2-4 计提情况检查表 -->
      <J2TabAccrualCheck
        v-else-if="currentSheet === 'J2-4'"
        :wp-id="wpId"
        :project-id="projectId"
        :html-data="htmlData"
        :is-readonly="isReadonly"
      />
      <!-- 附注（上市公司） -->
      <J2TabDisclosureListed
        v-else-if="currentSheet === 'J2附注(上市)'"
        :wp-id="wpId"
        :project-id="projectId"
        :html-data="htmlData"
        :is-readonly="isReadonly"
      />
      <!-- 附注（国有企业） -->
      <J2TabDisclosureSoe
        v-else-if="currentSheet === 'J2附注(国企)'"
        :wp-id="wpId"
        :project-id="projectId"
        :html-data="htmlData"
        :is-readonly="isReadonly"
      />
      <!-- 兜底 -->
      <div v-else class="j2-sheet-placeholder">
        <el-empty :description="`J2 未识别的 sheet: ${currentSheet}`" />
      </div>

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtJ2DefinedBenefitPlan — J2 设定受益计划主入口组件
 *
 * 按 sheetName v-if 分发到各子组件（defineAsyncComponent lazy 加载）。
 * 科目2221长期应付职工薪酬-设定受益计划（贷方/负债类）：期末=期初+贷方-借方
 *
 * J2 包含：底稿目录 + 审定表(设定受益/其他长期/辞退) + 明细表 + 调整分录 +
 *          计提检查(精算假设+ISA620) + 附注(双版本)
 */
import { computed, ref, onMounted, defineAsyncComponent, provide, toRef } from 'vue'
import { useJ2FormData } from '@/composables/workpaper/j2/useJ2FormData'
import { useWorkpaperVersionToolbar } from '../composables/useWorkpaperVersionToolbar'
import CycleTabProcedure from '../shared/CycleTabProcedure.vue'

// ── defineAsyncComponent lazy loading ───────────────────────────────────────
const GtWpVersionTrail = defineAsyncComponent(() => import('../version-trail/GtWpVersionTrail.vue'))
const J2TabIndex = defineAsyncComponent(() => import('./J2TabIndex.vue'))
const J2TabAdjudication = defineAsyncComponent(() => import('./J2TabAdjudication.vue'))
const J2TabDetail = defineAsyncComponent(() => import('./J2TabDetail.vue'))
const J2TabAdjustment = defineAsyncComponent(() => import('./J2TabAdjustment.vue'))
const J2TabAccrualCheck = defineAsyncComponent(() => import('./J2TabAccrualCheck.vue'))
const J2TabDisclosureListed = defineAsyncComponent(() => import('./J2TabDisclosureListed.vue'))
const J2TabDisclosureSoe = defineAsyncComponent(() => import('./J2TabDisclosureSoe.vue'))

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

// ── selfLoad ────────────────────────────────────────────────────────────────
const formData = useJ2FormData({
  wpId: props.wpId,
  projectId: props.projectId,
  year: props.year,
  sheetName: props.sheetName,
  htmlData: props.htmlData,
})

/** 当前 sheet 名（从 props.sheetName 提取） */
const currentSheet = computed(() => {
  const sn = props.sheetName || ''
  // 程序表 J2A（须先于其他匹配）
  if (/\bJ2A\b/.test(sn) || sn.includes('实质性程序表')) return 'J2A'
  // 匹配 J2-1, J2-2, J2-3, J2-4, J2附注(上市), J2附注(国企), 底稿目录
  if (sn.includes('底稿目录')) return '底稿目录'
  if (sn.includes('J2-1') || sn.includes('审定表')) return 'J2-1'
  if (sn.includes('J2-2') || sn.includes('明细表')) return 'J2-2'
  if (sn.includes('J2-3') || sn.includes('调整分录')) return 'J2-3'
  if (sn.includes('J2-4') || sn.includes('计提') || sn.includes('检查表')) return 'J2-4'
  if (sn.includes('上市')) return 'J2附注(上市)'
  if (sn.includes('国有') || sn.includes('国企')) return 'J2附注(国企)'
  // 尝试正则
  const m = sn.match(/^(J2-\d+)/)
  return m ? m[1] : sn
})

// ─── 版本追踪 useWorkpaperVersionToolbar ─────────────────────────────────────
const versionToolbar = useWorkpaperVersionToolbar({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const { versionTrailRef, openVersionHistory, scheduleAutoSnapshot } = versionToolbar
provide('j2VersionTrailRef', versionTrailRef)
provide('j2OpenVersionHistory', openVersionHistory)

function onSave() {
  scheduleAutoSnapshot()
  emit('save')
}

onMounted(async () => {
  await formData.loadData()
  isLoading.value = false
})
</script>

<style scoped>
.j2-defined-benefit-plan {
  padding: 16px;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.j2-sheet-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}
</style>
