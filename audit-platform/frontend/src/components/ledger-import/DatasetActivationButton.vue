<template>
  <el-button
    type="success"
    :loading="activating"
    :disabled="disabled"
    aria-label="激活数据集"
    @click="onActivate"
  >
    <slot>激活数据集</slot>
  </el-button>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { ledger } from '@/services/apiPaths'

const props = defineProps<{
  projectId: string
  datasetId: string
  datasetName?: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  activated: [datasetId: string]
  error: [err: unknown]
}>()

const activating = ref(false)

async function onActivate() {
  // 6.15 + 10.40: ElMessageBox.prompt 二次确认 + reason 字段
  let reason = ''
  try {
    const { value } = await ElMessageBox.prompt(
      `即将激活数据集${props.datasetName ? ` "${props.datasetName}"` : ''}，所有项目组成员将立即看到新数据`,
      '确认激活',
      {
        confirmButtonText: '确认激活',
        cancelButtonText: '取消',
        inputPlaceholder: '激活理由（可选）',
        inputType: 'textarea',
        inputValidator: () => true,  // reason is optional
        type: 'warning',
      },
    )
    reason = value || ''
  } catch {
    // User cancelled
    return
  }

  // 10.41 + 6.16: Pass reason to API
  activating.value = true
  try {
    await api.post(
      `${ledger.import.base(props.projectId)}/datasets/${props.datasetId}/activate`,
      { reason },
    )
    ElMessage.success('数据集已激活')
    emit('activated', props.datasetId)
  } catch (e: any) {
    const msg = e?.detail?.message || e?.message || '激活失败'
    ElMessage.error(msg)
    emit('error', e)
  } finally {
    activating.value = false
  }
}
</script>
