<template>
  <el-dialog v-model="visible" title="完成核对表（签发前置关卡）" width="600px" :close-on-click-modal="false">
    <p class="checklist-subtitle">{{ data?.title }}</p>
    <el-table v-if="data?.items" :data="data.items" class="gt-compact-table">
      <el-table-column type="index" label="序号" width="60" />
      <el-table-column prop="content" label="检查项" min-width="250" />
      <el-table-column label="自动校验" width="120" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.auto_pass === true" type="success" size="small">通过</el-tag>
          <el-tag v-else-if="row.auto_pass === false" type="danger" size="small">未通过</el-tag>
          <span v-else class="manual-check">人工确认</span>
        </template>
      </el-table-column>
      <el-table-column label="确认" width="70" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row._confirmed" />
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="!allConfirmed" @click="proceed">
        确认签发
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { apiProxy } from '@/utils/apiProxy'

const props = defineProps<{
  projectId: string
  year: number
  projectType?: string
}>()

const emit = defineEmits<{
  (e: 'proceed'): void
}>()

const visible = ref(false)
const data = ref<any>(null)

const allConfirmed = computed(() => {
  if (!data.value?.items) return false
  return data.value.items.every((i: any) => i._confirmed)
})

async function open() {
  visible.value = true
  const params = new URLSearchParams({ project_type: props.projectType || 'general' })
  data.value = await apiProxy.get(
    `/api/projects/${props.projectId}/review-workflow/${props.year}/completion-checklist?${params}`
  )
  // Initialize confirmation state
  data.value?.items?.forEach((item: any) => {
    item._confirmed = item.auto_pass === true
  })
}

function proceed() {
  visible.value = false
  emit('proceed')
}

defineExpose({ open })
</script>

<style scoped>
.checklist-subtitle { color: var(--el-text-color-secondary); margin-bottom: 12px; }
.manual-check { color: var(--el-text-color-placeholder); font-size: 12px; }
</style>
