<template>
  <div class="g7-long-term-equity-method">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="6" animated /></div>
    <template v-else>
      <div class="g7-long-term-equity-method-toolbar">
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
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
      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted, defineAsyncComponent } from 'vue'
import { useG7EquMetFormData } from './composables/useG7EquMetFormData'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
const GtGridSheet = defineAsyncComponent(() => import('./GtGridSheet.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const props = defineProps<{ wpId: string; projectId: string; wpCode?: string; sheetName?: string; htmlData?: any; readonly?: boolean }>()
const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const formData = useG7EquMetFormData({ wpId: wpIdRef, projectId: computed(() => props.projectId) })
const isReadonly = computed(() => !!props.readonly)
const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: computed(() => props.projectId) })
const { versionTrailRef } = versionToolbar
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  const m = name.match(/(G7A|G7-\d+)/)
  return m ? m[1] : ''
})
onMounted(async () => { await formData.loadAll(); isLoading.value = false })
</script>
<style scoped>.g7-long-term-equity-method { padding: 12px; } .loading-container { padding: 24px; } .g7-long-term-equity-method-toolbar { margin-bottom: 8px; }</style>
