<template>
  <div class="gt-batch-bar" v-if="selectedCount > 0">
    <span class="gt-batch-bar-count">已选 {{ selectedCount }} 个底稿</span>
    <div class="gt-batch-bar-actions">
      <el-button size="small" type="primary" @click="$emit('batch-action', { action: 'submit_review', ids: selectedIds })">
        📤 批量提交复核
      </el-button>
      <el-button
        v-if="canReturn"
        size="small"
        type="warning"
        @click="$emit('batch-action', { action: 'return_to_draft', ids: selectedIds })"
      >
        ↩️ 批量退回
      </el-button>
      <el-button
        v-if="canComplete"
        size="small"
        type="success"
        @click="$emit('batch-action', { action: 'mark_complete', ids: selectedIds })"
      >
        ✅ 批量标记完成
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { usePermission } from '@/composables/usePermission'

defineProps<{
  selectedCount: number
  selectedIds: string[]
}>()

defineEmits<{
  'batch-action': [payload: { action: string; ids: string[] }]
}>()

const { can } = usePermission()

// 退回和标记完成需要 manager+ 权限
const canReturn = computed(() => can('adjustment:review'))
const canComplete = computed(() => can('adjustment:review'))
</script>

<style scoped>
.gt-batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: #f0edf5;
  border: 1px solid #e8e4f0;
  border-radius: 6px;
  margin-bottom: 8px;
}

.gt-batch-bar-count {
  font-size: 13px;
  font-weight: 600;
  color: #4b2d77;
}

.gt-batch-bar-actions {
  display: flex;
  gap: 8px;
}
</style>
