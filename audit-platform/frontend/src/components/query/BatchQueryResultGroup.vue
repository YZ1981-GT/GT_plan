<template>
  <div class="batch-result-group">
    <div class="batch-result-header">
      <span class="batch-result-summary">
        成功 {{ totalSuccess }} / 失败 {{ totalFailed }} / 共 {{ Object.keys(results).length }}
      </span>
      <el-button
        v-if="totalSuccess > 0"
        type="primary"
        size="small"
        @click="handleMergedExport"
        :loading="exporting"
      >
        合并导出
      </el-button>
    </div>

    <el-collapse v-model="activeNames">
      <el-collapse-item
        v-for="(result, wpCode) in results"
        :key="wpCode"
        :name="wpCode"
      >
        <template #title>
          <div class="collapse-title">
            <el-tag
              :type="result.error ? 'danger' : 'success'"
              size="small"
              class="status-tag"
            >
              {{ result.error ? '失败' : '成功' }}
            </el-tag>
            <span class="wp-code-label">{{ wpCode }}</span>
            <span v-if="!result.error" class="row-count">
              {{ result.rows?.length ?? 0 }} 行
            </span>
          </div>
        </template>

        <div v-if="result.error" class="error-message">
          <el-alert :title="result.error" type="error" :closable="false" show-icon />
        </div>

        <div v-else class="result-table-wrapper">
          <el-table
            :data="result.rows || []"
            border
            size="small"
            max-height="300"
            stripe
          >
            <el-table-column
              v-for="col in (result.columns || [])"
              :key="col"
              :prop="col"
              :label="col"
              min-width="120"
              show-overflow-tooltip
            />
          </el-table>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineProps, defineEmits } from 'vue'

export interface BatchResult {
  rows?: Record<string, any>[]
  columns?: string[]
  total?: number
  source?: string
  error?: string
}

export interface BatchQueryResultGroupProps {
  results: Record<string, BatchResult>
  totalSuccess: number
  totalFailed: number
}

const props = defineProps<BatchQueryResultGroupProps>()

const emit = defineEmits<{
  (e: 'merged-export'): void
}>()

const activeNames = ref<string[]>(Object.keys(props.results))
const exporting = ref(false)

function handleMergedExport() {
  emit('merged-export')
}

defineExpose({ exporting })
</script>

<style scoped>
.batch-result-group {
  margin-top: 12px;
}

.batch-result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.batch-result-summary {
  font-size: 13px;
  color: #606266;
}

.collapse-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-tag {
  flex-shrink: 0;
}

.wp-code-label {
  font-weight: 600;
  font-size: 13px;
}

.row-count {
  font-size: 12px;
  color: #909399;
}

.error-message {
  padding: 8px;
}

.result-table-wrapper {
  padding: 4px;
}
</style>
