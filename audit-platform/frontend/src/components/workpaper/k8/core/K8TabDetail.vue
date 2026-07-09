<template>
  <div class="k8-tab-detail">
    <div class="section-header">
      <h3>K8-2 销售费用明细表</h3>
      <div class="header-actions">
        <GtIndexChip value="K8-1" :context-project-id="props.projectId" />
      </div>
    </div>
    <el-empty description="K8-2 明细表（27列3区段，48行，待实现）" />
  </div>
</template>

<script setup lang="ts">
/**
 * K8TabDetail.vue — K8-2 明细表（27列3区段，48行）
 * Stub: 将在 Phase 4 (task 4.3) 实现
 * GtIndexChip: links back to K8-1 审定表
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
.k8-tab-detail { padding: 12px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; }
.header-actions { display: flex; gap: 8px; align-items: center; }
</style>
