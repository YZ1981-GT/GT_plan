<template>
  <div class="j3-share-based-payment">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
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
        :is-readonly="props.isReadonly"
      />

      <!-- J3-2 股份支付检查表 -->
      <J3TabCheck
        v-else-if="currentSheet === 'J3-2'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :year="props.year"
        :html-data="props.htmlData"
        :is-readonly="props.isReadonly"
      />

      <!-- 兜底 OnlyOffice -->
      <div v-else class="j3-sheet-placeholder">
        <el-empty :description="`J3 未识别的 sheet: ${currentSheet}（将使用 OnlyOffice）`" />
      </div>

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtJ3ShareBasedPayment — J3 股份支付主入口组件
 *
 * 按 sheetName v-if 分发到各子组件（defineAsyncComponent lazy 加载）。
 * J3 无独立科目（费用端走 K8/K9，权益端走 M4，现金端走 J1）。
 *
 * J3 包含：程序表(J3A) + 情况表(Black-Scholes参数+等待期) + 检查表(公允价值/服务年限/测算)
 * 程序表在专属组件内分发（对齐 H1A/L1A），不再单独走 a-program-console。
 *
 * Spec: .kiro/specs/j3-share-based-payment/
 * Requirements: 1.1-1.10
 */
import { computed, ref, onMounted, defineAsyncComponent, provide, toRef } from 'vue'
import { useWorkpaperVersionToolbar } from '../composables/useWorkpaperVersionToolbar'
import CycleTabProcedure from '../shared/CycleTabProcedure.vue'

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
  // 程序表 J3A（须先于 J3-\d+）
  if (/\bJ3A\b/.test(sn) || sn.includes('实质性程序表')) return 'J3A'
  // 匹配 J3-1, J3-2 等编码
  const m = sn.match(/(J3-\d+)/)
  if (m) return m[1]
  // 匹配底稿目录
  if (sn.includes('目录') || sn === 'J3') return 'J3'
  return sn
})

// ─── 版本追踪 useWorkpaperVersionToolbar ─────────────────────────────────────
const versionToolbar = useWorkpaperVersionToolbar({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const { versionTrailRef, openVersionHistory, scheduleAutoSnapshot } = versionToolbar
provide('j3VersionTrailRef', versionTrailRef)
provide('j3OpenVersionHistory', openVersionHistory)

function handleNavigateSheet(sheetName: string) {
  emit('navigate-sheet', sheetName)
}

onMounted(async () => {
  // selfLoad — 后续 wave 已在子组件内实现
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
.j3-sheet-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}
</style>
