<template>
  <div class="batch-query-toolbar" v-if="selectedWpCodes.length > 0 || showAlways">
    <div class="batch-chips">
      <el-tag
        v-for="code in selectedWpCodes"
        :key="code"
        closable
        class="batch-chip"
        @close="removeWpCode(code)"
      >
        {{ code }}
      </el-tag>
    </div>
    <el-button
      type="primary"
      :loading="loading"
      :disabled="selectedWpCodes.length === 0"
      @click="handleBatchQuery"
    >
      批量查询 ({{ selectedWpCodes.length }})
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref, defineProps, defineEmits, defineExpose } from 'vue'
import { ElMessage } from 'element-plus'

export interface BatchQueryToolbarProps {
  showAlways?: boolean
}

const props = withDefaults(defineProps<BatchQueryToolbarProps>(), {
  showAlways: false,
})

const emit = defineEmits<{
  (e: 'batch-query', wpCodes: string[]): void
}>()

const selectedWpCodes = ref<string[]>([])
const loading = ref(false)

/**
 * 添加 wp_code 到多选集合（ctrl+click 触发）
 * 如果已存在则移除（toggle 行为）
 */
function toggleWpCode(code: string) {
  const idx = selectedWpCodes.value.indexOf(code)
  if (idx >= 0) {
    selectedWpCodes.value.splice(idx, 1)
  } else {
    selectedWpCodes.value.push(code)
  }
}

function removeWpCode(code: string) {
  const idx = selectedWpCodes.value.indexOf(code)
  if (idx >= 0) {
    selectedWpCodes.value.splice(idx, 1)
  }
}

function clearAll() {
  selectedWpCodes.value = []
}

function handleBatchQuery() {
  if (selectedWpCodes.value.length === 0) {
    ElMessage.warning('请先 ctrl+点击至少一个底稿节点')
    return
  }
  emit('batch-query', [...selectedWpCodes.value])
}

function setLoading(val: boolean) {
  loading.value = val
}

defineExpose({
  toggleWpCode,
  removeWpCode,
  clearAll,
  selectedWpCodes,
  setLoading,
})
</script>

<style scoped>
.batch-query-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  flex-wrap: wrap;
}

.batch-chips {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.batch-chip {
  background-color: #7c3aed;
  color: #fff;
  border: none;
}

.batch-chip :deep(.el-tag__close) {
  color: #fff;
}

.batch-chip :deep(.el-tag__close:hover) {
  background-color: rgba(255, 255, 255, 0.3);
  color: #fff;
}
</style>
