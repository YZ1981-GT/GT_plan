<!--
  历史简版桩（GtGridSheet + OO 兜底）。
  htmlRendererRegistry 已改为加载 GtG6OtherBondInvestmentEcl.vue（完整 ECL 调度器）。
  本文件保留以免旧路径/类型声明断裂，请勿再注册为 g6-other-bond-investment-ecl。
-->
<template>
  <div class="g6-other-bond-investment-ecl">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="6" animated /></div>
    <template v-else>
      <div class="g6-other-bond-investment-ecl-toolbar">
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
      </div>
      <GtGridSheet
        v-if="currentSheet || props.htmlData"
        :html-data="props.htmlData || formData.getSheet(currentSheet)"
        :readonly="isReadonly"
      />
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />
      <!-- 版本链/复核 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted, inject, defineAsyncComponent } from 'vue'
import { useG6BonEclFormData } from './composables/useG6BonEclFormData'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
const GtGridSheet = defineAsyncComponent(() => import('./GtGridSheet.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const props = defineProps<{ wpId: string; projectId: string; wpCode?: string; sheetName?: string; htmlData?: any; readonly?: boolean }>()
const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const formData = useG6BonEclFormData({ wpId: wpIdRef, projectId: computed(() => props.projectId) })
const isReadonly = computed(() => !!props.readonly)
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  const m = name.match(/(G6A|G6-\d+)/)
  return m ? m[1] : ''
})
onMounted(async () => { await formData.loadAll(); isLoading.value = false })
</script>
<style scoped>.g6-other-bond-investment-ecl { padding: 12px; } .loading-container { padding: 24px; } .g6-other-bond-investment-ecl-toolbar { margin-bottom: 8px; }</style>
