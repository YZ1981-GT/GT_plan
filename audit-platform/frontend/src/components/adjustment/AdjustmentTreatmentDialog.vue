<template>
  <el-dialog v-model="visible" title="最终处理与历史" width="min(680px, 94vw)" append-to-body destroy-on-close>
    <div v-if="row" class="gt-treatment">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="分录">{{ row.adjustment_no || row.entry_group_id }}</el-descriptions-item>
        <el-descriptions-item label="当前处理">
          <el-tag :type="statusType">{{ statusLabel }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <el-alert v-if="row.origin === 'workpaper'" type="info" :closable="false" show-icon
        title="底稿来源调整由来源底稿显式发布，不在这里选择财务处理。" />
      <template v-else-if="row.review_status === 'approved' && currentStatus === 'include_in_working_tb'">
        <el-alert type="info" :closable="false" show-icon
          title="当前已纳入工作试算表。只有管理层明确不予更正时才转为未更正错报。" />
        <el-form label-position="top">
          <el-form-item label="管理层不予更正原因" required>
            <el-input v-model="managementReason" type="textarea" :rows="3" maxlength="4000" show-word-limit />
          </el-form-item>
          <el-form-item label="沟通时间" required>
            <el-date-picker v-model="communicationAt" type="datetime" value-format="YYYY-MM-DDTHH:mm:ssZ"
              placeholder="选择与管理层沟通时间" style="width: 100%" />
          </el-form-item>
          <el-form-item label="审计师评价（可稍后在错报汇总页补充）">
            <el-input v-model="auditorEvaluation" type="textarea" :rows="2" maxlength="4000" />
          </el-form-item>
        </el-form>
        <el-button type="warning" :loading="saving" @click="markUnadjusted">不予更正并转错报</el-button>
      </template>
      <template v-else-if="row.review_status === 'approved' && ['client_booked', 'unadjusted_misstatement'].includes(currentStatus)">
        <el-alert type="warning" :closable="false" show-icon
          title="撤销后，该 AJE 将恢复计入工作试算表；历史记录不会删除。" />
        <el-form label-position="top">
          <el-form-item label="撤销原因" required>
            <el-input v-model="withdrawReason" type="textarea" :rows="2" maxlength="1000" show-word-limit />
          </el-form-item>
        </el-form>
        <el-button type="warning" :loading="saving" @click="withdraw">撤销当前处理</el-button>
      </template>
      <el-alert v-else type="info" :closable="false" show-icon title="完成内部复核后才能选择最终处理。" />

      <h4>处理历史</h4>
      <el-skeleton v-if="historyLoading" :rows="2" animated />
      <el-empty v-else-if="history.length === 0" description="暂无处理历史" :image-size="60" />
      <el-timeline v-else>
        <el-timeline-item v-for="item in history" :key="item.id" :timestamp="fmtDateTime(item.created_at)" placement="top">
          <strong>{{ actionLabels[item.action] || item.action }}</strong>
          <div v-if="item.reason" class="gt-treatment__reason">{{ item.reason }}</div>
        </el-timeline-item>
      </el-timeline>
    </div>
    <template #footer><el-button @click="visible = false">关闭</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getAdjustmentTreatmentHistory,
  markAdjustmentUnadjusted,
  withdrawAdjustmentTreatment,
} from '@/services/auditPlatformApi'
import { fmtDateTime } from '@/utils/formatters'

const props = defineProps<{ projectId: string; year: number | null }>()
const emit = defineEmits<{ updated: [] }>()
const visible = ref(false)
const saving = ref(false)
const historyLoading = ref(false)
const row = ref<any>(null)
const history = ref<any[]>([])
const managementReason = ref('')
const communicationAt = ref('')
const auditorEvaluation = ref('')
const withdrawReason = ref('')

const actionLabels: Record<string, string> = {
  include_in_working_tb: '纳入工作试算表',
  client_booked: '客户已入账',
  unadjusted_misstatement: '不予更正并转错报',
  withdraw: '撤销最终处理',
}
const currentStatus = computed<string>(() => row.value?.treatment?.status || (
  row.value?.client_booking?.status === 'booked' ? 'client_booked' : 'include_in_working_tb'
))
const statusLabels: Record<string, string> = {
  pending_internal_review: '待内部复核',
  awaiting_workpaper_publish: '待来源底稿发布',
  include_in_working_tb: '纳入工作试算表',
  client_booked: '客户已入账',
  unadjusted_misstatement: '不予更正',
}
const statusLabel = computed(() => currentStatus.value === 'client_booked' && row.value?.treatment?.effective === false
  ? '客户已入账·当前未生效'
  : statusLabels[currentStatus.value] || currentStatus.value)
const statusType = computed(() => currentStatus.value === 'include_in_working_tb' ? 'primary'
  : currentStatus.value === 'client_booked' ? 'success'
    : currentStatus.value === 'unadjusted_misstatement' ? 'warning' : 'info')

async function loadHistory(): Promise<void> {
  if (!row.value || props.year == null) return
  historyLoading.value = true
  try {
    history.value = await getAdjustmentTreatmentHistory(props.projectId, row.value.entry_group_id, props.year)
  } catch {
    ElMessage.error('读取处理历史失败')
  } finally {
    historyLoading.value = false
  }
}

async function open(target: any): Promise<void> {
  row.value = target
  managementReason.value = ''
  communicationAt.value = new Date().toISOString()
  auditorEvaluation.value = ''
  withdrawReason.value = ''
  visible.value = true
  await loadHistory()
}

async function markUnadjusted(): Promise<void> {
  if (!row.value || props.year == null) return
  if (!managementReason.value.trim()) { ElMessage.warning('请填写管理层不予更正原因'); return }
  if (!communicationAt.value) { ElMessage.warning('请选择沟通时间'); return }
  saving.value = true
  try {
    await markAdjustmentUnadjusted(props.projectId, row.value.entry_group_id, {
      year: props.year,
      management_reason: managementReason.value.trim(),
      management_communication_at: new Date(communicationAt.value).toISOString(),
      auditor_evaluation: auditorEvaluation.value.trim() || undefined,
    })
    ElMessage.success('已转为未更正错报，工作试算表已同步更新')
    visible.value = false
    emit('updated')
  } catch {
    ElMessage.error('转为未更正错报失败')
  } finally {
    saving.value = false
  }
}

async function withdraw(): Promise<void> {
  if (!row.value || props.year == null) return
  if (!withdrawReason.value.trim()) { ElMessage.warning('请填写撤销原因'); return }
  saving.value = true
  try {
    await withdrawAdjustmentTreatment(props.projectId, row.value.entry_group_id, {
      year: props.year, reason: withdrawReason.value.trim(),
    })
    ElMessage.success('已撤销最终处理，调整恢复计入工作试算表')
    visible.value = false
    emit('updated')
  } catch {
    ElMessage.error('撤销最终处理失败')
  } finally {
    saving.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.gt-treatment { display: flex; flex-direction: column; gap: 14px; }
.gt-treatment h4 { margin: 4px 0 0; }
.gt-treatment__reason { margin-top: 4px; color: var(--gt-color-text-regular); white-space: pre-wrap; }
</style>
