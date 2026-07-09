<template>
  <div class="k8-tab-substantive-analysis">
    <div class="section-header">
      <h3>K8-4 实质性分析程序</h3>
      <div class="header-actions">
        <GtIndexChip value="K8-2" :context-project-id="props.projectId" />
      </div>
    </div>
    <el-empty description="K8-4 实质性分析（25公式，39行，待实现）" />
  </div>
</template>

<script setup lang="ts">
/**
 * K8TabSubstantiveAnalysis.vue — K8-4 实质性分析程序（25公式，39行）
 * Stub: 将在 Phase 4 (task 4.4) 实现
 * GtIndexChip: links to K8-2 明细表
 */
import { defineAsyncComponent } from 'vue'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

defineEmits<{ (e: 'save', itemId: string, value: any): void }>()
</script>

<style scoped>
.k8-tab-substantive-analysis { padding: 12px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; }
.header-actions { display: flex; gap: 8px; align-items: center; }
</style>
