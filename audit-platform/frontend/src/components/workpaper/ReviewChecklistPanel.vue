<script setup lang="ts">
/**
 * 复核检查清单面板 — 检查项列表+进度条+通过/退回按钮
 * Sprint 10 Task 10.6
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'

interface CheckItem {
  id: string
  label: string
  checked: boolean
}

const props = defineProps<{ wpId: string; projectId: string }>()
const emit = defineEmits<{ (e: 'pass'): void; (e: 'reject'): void }>()

const items = ref<CheckItem[]>([])
const loading = ref(false)

const progress = computed(() => {
  const total = items.value.length
  const checked = items.value.filter(i => i.checked).length
  return total > 0 ? Math.round((checked / total) * 100) : 0
})

const allPassed = computed(() => items.value.length > 0 && items.value.every(i => i.checked))

async function loadChecklist() {
  loading.value = true
  try {
    const data = await api.get(`/api/workpapers/${props.wpId}/review-checklist`)
    items.value = (data as any).items || []
  } catch {
    // Use default items on error
    items.value = [
      { id: 'chk-01', label: '底稿编制完整性', checked: false },
      { id: 'chk-02', label: '数据来源可追溯', checked: false },
      { id: 'chk-03', label: '公式计算正确', checked: false },
      { id: 'chk-04', label: '交叉索引完整', checked: false },
      { id: 'chk-05', label: '审计结论合理', checked: false },
    ]
  } finally {
    loading.value = false
  }
}

async function toggleItem(item: CheckItem) {
  item.checked = !item.checked
}

async function handlePass() {
  if (!allPassed.value) {
    ElMessage.warning('请先完成所有检查项')
    return
  }
  emit('pass')
  ElMessage.success('复核通过')
}

async function handleReject() {
  try {
    await ElMessageBox.prompt('请输入退回原因', '退回底稿', { type: 'warning' })
    emit('reject')
    ElMessage.info('已退回')
  } catch { /* cancelled */ }
}

onMounted(loadChecklist)
</script>

<template>
  <div class="review-checklist-panel">
    <div class="panel-header">
      <span class="title">复核检查清单</span>
      <el-progress :percentage="progress" :stroke-width="6" style="width: 120px;" />
    </div>
    <el-scrollbar max-height="300px">
      <div v-for="item in items" :key="item.id" class="check-item">
        <el-checkbox v-model="item.checked" @change="toggleItem(item)">
          {{ item.label }}
        </el-checkbox>
      </div>
    </el-scrollbar>
    <div class="panel-actions">
      <el-button type="success" :disabled="!allPassed" @click="handlePass">通过</el-button>
      <el-button type="warning" @click="handleReject">退回</el-button>
    </div>
  </div>
</template>

<style scoped>
.review-checklist-panel { padding: 12px; }
.panel-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.title { font-weight: 600; font-size: 14px; }
.check-item { padding: 6px 0; }
.panel-actions { display: flex; gap: 8px; margin-top: 12px; justify-content: flex-end; }
</style>
