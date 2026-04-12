<template>
  <div class="archive-modification-form">
    <div class="form-header">
      <h3>归档后修改申请</h3>
    </div>

    <el-form :model="form" label-width="130px">
      <el-form-item label="修改原因" required>
        <el-input
          v-model="form.modification_reason"
          type="textarea"
          :rows="4"
          placeholder="请详细描述需要修改的原因"
        />
      </el-form-item>

      <el-form-item label="受影响项目" required>
        <el-checkbox-group v-model="form.affected_items">
          <el-checkbox
            v-for="item in availableItems"
            :key="item"
            :label="item"
            style="display: block; margin-bottom: 8px"
          >
            {{ item }}
          </el-checkbox>
        </el-checkbox-group>
      </el-form-item>

      <el-form-item label="申请状态">
        <el-input :model-value="approvalStatusLabel" readonly />
      </el-form-item>

      <el-form-item>
        <el-button type="primary" @click="submitRequest">提交申请</el-button>
      </el-form-item>
    </el-form>

    <!-- 审批流程展示 -->
    <el-divider content-position="left">审批流程</el-divider>
    <el-steps :active="approvalStep" align-center finish-status="success">
      <el-step title="提交申请" :description="form.submitted_at || ''" />
      <el-step title="审核中" />
      <el-step :title="approvalResultLabel" />
    </el-steps>

    <!-- 历史申请记录 -->
    <div v-if="historyRecords.length > 0" class="history-section">
      <h4>历史申请</h4>
      <el-table :data="historyRecords" stripe>
        <el-table-column prop="submitted_at" label="提交时间" width="160" />
        <el-table-column prop="modification_reason" label="修改原因" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="approvalTagType(row.approval_status)">
              {{ approvalStatusText(row.approval_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="approver_comments" label="审批意见" min-width="160" show-overflow-tooltip />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { archiveApi } from '@/services/collaborationApi'

const projectId = 'current-project-id'

const availableItems = ref([
  '审计报告',
  '财务报表',
  '工作底稿',
  '函证材料',
  '附件资料',
  '其他',
])

const form = ref({
  modification_reason: '',
  affected_items: [] as string[],
  approval_status: 'PENDING',
  submitted_at: '',
})

const historyRecords = ref<any[]>([])

const approvalStep = computed(() => {
  const s = form.value.approval_status
  if (s === 'PENDING') return 0
  if (s === 'UNDER_REVIEW') return 1
  return 2
})

const approvalStatusLabel = computed(() => {
  const map: Record<string, string> = {
    PENDING: '待提交',
    UNDER_REVIEW: '审核中',
    APPROVED: '已批准',
    REJECTED: '已拒绝',
  }
  return map[form.value.approval_status] || form.value.approval_status
})

const approvalResultLabel = computed(() => {
  return form.value.approval_status === 'APPROVED' ? '已批准' :
    form.value.approval_status === 'REJECTED' ? '已拒绝' : ''
})

function approvalTagType(s: string) {
  const map: Record<string, string> = {
    PENDING: 'info',
    UNDER_REVIEW: 'warning',
    APPROVED: 'success',
    REJECTED: 'danger',
  }
  return map[s] || 'info'
}

function approvalStatusText(s: string) {
  const map: Record<string, string> = {
    PENDING: '待审核',
    UNDER_REVIEW: '审核中',
    APPROVED: '已批准',
    REJECTED: '已拒绝',
  }
  return map[s] || s
}

onMounted(() => {
  // load history if available
})

async function submitRequest() {
  if (!form.value.modification_reason) {
    ElMessage.warning('请填写修改原因')
    return
  }
  if (form.value.affected_items.length === 0) {
    ElMessage.warning('请选择受影响的项目')
    return
  }
  try {
    await archiveApi.requestModification(projectId, {
      modification_reason: form.value.modification_reason,
      affected_items: form.value.affected_items,
    })
    form.value.approval_status = 'UNDER_REVIEW'
    form.value.submitted_at = new Date().toLocaleString('zh-CN')
    ElMessage.success('修改申请已提交')
  } catch {
    ElMessage.error('提交失败')
  }
}
</script>

<style scoped>
.archive-modification-form {}
.form-header { margin-bottom: 16px; }
.history-section { margin-top: 24px; }
.history-section h4 { margin-bottom: 12px; }
</style>
