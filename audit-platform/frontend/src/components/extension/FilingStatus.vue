<template>
  <div class="gt-filing-status">
    <el-tag :type="(tagType) || undefined" size="small">{{ label }}</el-tag>
    <div class="gt-filing-times" v-if="submittedAt || respondedAt">
      <span v-if="submittedAt" class="gt-time">提交: {{ fmtTime(submittedAt) }}</span>
      <span v-if="respondedAt" class="gt-time">响应: {{ fmtTime(respondedAt) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status: string
  submittedAt?: string
  respondedAt?: string
}>()

const tagType = computed((): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' => {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    submitted: '',
    pending: 'warning',
    approved: 'success',
    rejected: 'danger',
  }
  return m[props.status] || 'info'
})

const label = computed(() => {
  const m: Record<string, string> = {
    submitted: '已提交',
    pending: '待审核',
    approved: '已通过',
    rejected: '已驳回',
  }
  return m[props.status] || props.status
})

function fmtTime(d: string) {
  return d ? new Date(d).toLocaleString('zh-CN') : ''
}
</script>

<style scoped>
.gt-filing-status { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.gt-filing-times { display: flex; flex-direction: column; gap: 1px; }
.gt-time { font-size: 11px; color: var(--gt-color-text-tertiary); }
</style>
