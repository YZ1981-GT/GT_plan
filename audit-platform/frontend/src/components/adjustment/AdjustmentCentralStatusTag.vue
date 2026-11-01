<template>
  <span v-if="status?.review_status" class="gt-central-status">
    <el-tag :type="reviewTag" size="small" :title="status.rejection_reason || ''">
      集中登记：{{ reviewLabel }}<template v-if="status.adjustment_no"> · {{ status.adjustment_no }}</template>
    </el-tag>
    <el-tag v-if="status.client_booking?.status === 'booked'" :type="status.client_booking.effective ? 'success' : 'warning'" size="small">
      {{ status.client_booking.effective ? '客户已入账' : '已标记·当前账套未生效' }}
    </el-tag>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CENTRAL_STATUS_LABELS, type CentralStatus } from '@/components/workpaper/composables/useAdjustmentCentralSync'

const props = defineProps<{ status: CentralStatus | null }>()
const reviewLabel = computed(() => {
  const value = props.status?.review_status || ''
  return CENTRAL_STATUS_LABELS[value] || value
})
const reviewTag = computed<'success' | 'danger' | 'info'>(() => {
  if (props.status?.review_status === 'approved') return 'success'
  if (props.status?.review_status === 'rejected') return 'danger'
  return 'info'
})
</script>

<style scoped>
.gt-central-status { display: inline-flex; align-items: center; gap: 4px; flex-wrap: wrap; }
</style>
