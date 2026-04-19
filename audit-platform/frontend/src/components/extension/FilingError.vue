<template>
  <el-dialog append-to-body v-model="visible" title="备案错误信息" width="500px" @close="$emit('close')">
    <template v-if="filing">
      <el-alert type="error" :closable="false" show-icon style="margin-bottom: 16px">
        <template #title>备案处理失败</template>
        <p>{{ filing.error_message || '未知错误' }}</p>
      </el-alert>
      <el-descriptions :column="1" size="small" border>
        <el-descriptions-item label="备案ID">{{ filing.id }}</el-descriptions-item>
        <el-descriptions-item label="备案类型">
          {{ filing.filing_type === 'cicpa_report' ? '中注协报告备案' : '电子底稿归档' }}
        </el-descriptions-item>
        <el-descriptions-item label="状态">{{ filing.filing_status }}</el-descriptions-item>
        <el-descriptions-item label="提交时间">{{ fmtTime(filing.submitted_at) }}</el-descriptions-item>
      </el-descriptions>
    </template>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" @click="onRetry" :loading="retrying">重试提交</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

const props = defineProps<{
  modelValue: boolean
  filing: any
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'retried'): void
  (e: 'close'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const retrying = ref(false)

async function onRetry() {
  if (!props.filing?.id) return
  retrying.value = true
  try {
    await http.post(`/api/regulatory/filings/${props.filing.id}/retry`)
    ElMessage.success('重试请求已提交')
    emit('retried')
    visible.value = false
  } catch { ElMessage.error('重试失败') }
  finally { retrying.value = false }
}

function fmtTime(d: string) { return d ? new Date(d).toLocaleString('zh-CN') : '-' }
</script>
