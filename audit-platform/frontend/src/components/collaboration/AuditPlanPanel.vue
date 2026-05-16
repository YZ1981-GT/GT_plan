<template>
  <div class="gt-audit-plan-panel">
    <div class="panel-header">
      <span class="panel-title">审计计划</span>
      <div class="header-actions">
        <el-tag v-if="plan?.status" :type="(statusTagType(plan.status)) || undefined" size="small">
          {{ statusLabel(plan.status) }}
        </el-tag>
        <el-button
          v-if="editable"
          type="primary"
          size="small"
          @click="openEditDialog"
        >
          {{ plan ? '编辑' : '创建计划' }}
        </el-button>
        <el-button
          v-if="plan && plan.status === 'draft' && editable"
          type="success"
          size="small"
          @click="submitForApproval"
        >
          提交审批
        </el-button>
      </div>
    </div>

    <el-descriptions :column="2" border class="plan-info">
      <el-descriptions-item label="计划版本">
        {{ plan?.plan_version || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="计划开始日期">
        {{ plan?.planned_start_date || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="计划结束日期">
        {{ plan?.planned_end_date || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="审批人">
        {{ plan?.approved_by || '-' }}
      </el-descriptions-item>
    </el-descriptions>

    <div class="section-block">
      <div class="section-title">审计策略</div>
      <p class="strategy-text">{{ plan?.audit_strategy || '暂无审计策略描述' }}</p>
    </div>

    <div class="section-block">
      <div class="section-title">重点领域</div>
      <div class="focus-tags">
        <el-tag
          v-for="(area, index) in plan?.key_focus_areas || []"
          :key="index"
          type="warning"
          size="small"
          class="focus-tag"
        >
          {{ area }}
        </el-tag>
        <span v-if="!plan?.key_focus_areas?.length" class="no-data">暂无</span>
      </div>
    </div>

    <div class="section-block">
      <div class="section-title">团队分工</div>
      <el-table
        v-if="teamAssignment.length > 0"
        :data="teamAssignment"
        stripe
        size="small"
        class="team-table"
      >
        <el-table-column prop="member_name" label="成员" width="150" />
        <el-table-column prop="role" label="角色" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ row.role }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="responsibilities" label="分工说明" />
      </el-table>
      <span v-else class="no-data">暂无团队分工信息</span>
    </div>

    <!-- 编辑对话框 -->
    <el-dialog append-to-body
      v-model="editDialogVisible"
      :title="plan ? '编辑审计计划' : '创建审计计划'"
      width="700px"
    >
      <el-form :model="planForm" label-width="120px">
        <el-form-item label="审计策略">
          <el-input
            v-model="planForm.audit_strategy"
            type="textarea"
            :rows="4"
            placeholder="请描述审计策略..."
          />
        </el-form-item>
        <el-form-item label="计划开始日期">
          <el-date-picker
            v-model="planForm.planned_start_date"
            type="date"
            placeholder="选择日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="计划结束日期">
          <el-date-picker
            v-model="planForm.planned_end_date"
            type="date"
            placeholder="选择日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="重点领域">
          <el-select
            v-model="planForm.key_focus_areas"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入重点领域"
            style="width: 100%"
          >
            <el-option label="收入确认" value="收入确认" />
            <el-option label="资产减值" value="资产减值" />
            <el-option label="关联方交易" value="关联方交易" />
            <el-option label="或有事项" value="或有事项" />
            <el-option label="持续经营" value="持续经营" />
          </el-select>
        </el-form-item>
        <el-form-item label="重要性水平">
          <el-input
            v-model="planForm.materiality_reference"
            placeholder="请输入重要性水平参考值"
          />
        </el-form-item>
        <el-form-item label="团队分工">
          <div class="team-edit-table">
            <div
              v-for="(member, index) in planForm.team_assignment_summary"
              :key="index"
              class="team-member-row"
            >
              <el-input v-model="member.member_name" placeholder="成员姓名" />
              <el-select v-model="member.role" placeholder="角色" style="width: 120px">
                <el-option label="合伙人" value="partner" />
                <el-option label="经理" value="manager" />
                <el-option label="审计员" value="auditor" />
                <el-option label="QC复核" value="qc_reviewer" />
              </el-select>
              <el-input v-model="member.responsibilities" placeholder="分工说明" />
              <el-button type="danger" size="small" text @click="removeTeamMember(index)">
                删除
              </el-button>
            </div>
            <el-button type="primary" size="small" text @click="addTeamMember">
              + 添加成员
            </el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="savePlan">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { auditProgramApi } from '@/services/collaborationApi'

interface AuditPlan {
  id: string
  project_id: string
  plan_version: number
  audit_strategy?: string
  planned_start_date?: string
  planned_end_date?: string
  key_focus_areas?: string[]
  team_assignment_summary?: TeamMember[]
  materiality_reference?: string
  status: string
  approved_by?: string
  approved_at?: string
}

interface TeamMember {
  member_name: string
  role: string
  responsibilities: string
}

const props = defineProps<{
  projectId: string
  editable?: boolean
}>()

const plan = ref<AuditPlan | null>(null)
const editDialogVisible = ref(false)

const planForm = ref<{
  audit_strategy: string
  planned_start_date: string
  planned_end_date: string
  key_focus_areas: string[]
  materiality_reference: string
  team_assignment_summary: TeamMember[]
}>({
  audit_strategy: '',
  planned_start_date: '',
  planned_end_date: '',
  key_focus_areas: [],
  materiality_reference: '',
  team_assignment_summary: [],
})

const teamAssignment = computed<TeamMember[]>(() => {
  return plan.value?.team_assignment_summary || []
})

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    draft: '草稿',
    submitted: '待审批',
    approved: '已审批',
    rejected: '已退回',
    revised: '已修订',
  }
  return labels[status] || status
}

function statusTagType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const types: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    draft: 'info',
    submitted: 'warning',
    approved: 'success',
    rejected: 'danger',
    revised: 'warning',
  }
  return types[status] || 'info'
}

function openEditDialog() {
  planForm.value = {
    audit_strategy: plan.value?.audit_strategy || '',
    planned_start_date: plan.value?.planned_start_date || '',
    planned_end_date: plan.value?.planned_end_date || '',
    key_focus_areas: plan.value?.key_focus_areas || [],
    materiality_reference: plan.value?.materiality_reference || '',
    team_assignment_summary: plan.value?.team_assignment_summary
      ? [...plan.value.team_assignment_summary]
      : [],
  }
  editDialogVisible.value = true
}

function addTeamMember() {
  planForm.value.team_assignment_summary.push({
    member_name: '',
    role: 'auditor',
    responsibilities: '',
  })
}

function removeTeamMember(index: number) {
  planForm.value.team_assignment_summary.splice(index, 1)
}

async function loadPlan() {
  try {
    const { data } = await (auditProgramApi as any).getPlan(props.projectId)
    plan.value = data || null
  } catch (e) {
    console.error('加载审计计划失败', e)
  }
}

async function savePlan() {
  try {
    if (plan.value) {
      await (auditProgramApi as any).updatePlan(props.projectId, plan.value.id, planForm.value)
      ElMessage.success('保存成功')
    } else {
      await (auditProgramApi as any).createPlan(props.projectId, planForm.value)
      ElMessage.success('创建成功')
    }
    editDialogVisible.value = false
    await loadPlan()
  } catch (e) {
    console.error('保存审计计划失败', e)
    ElMessage.error('保存失败')
  }
}

async function submitForApproval() {
  try {
    await (auditProgramApi as any).submitPlan(props.projectId, plan.value?.id)
    ElMessage.success('已提交审批')
    await loadPlan()
  } catch (e) {
    ElMessage.error('提交审批失败')
  }
}

onMounted(() => {
  loadPlan()
})
</script>

<style scoped>
.gt-audit-plan-panel {
  padding: 16px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.panel-title {
  font-size: var(--gt-font-size-md);
  font-weight: 600;
  color: var(--gt-color-text-primary);
}

.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.section-block {
  margin-top: 16px;
}

.section-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text-regular);
  margin-bottom: 8px;
}

.strategy-text {
  color: var(--gt-color-text-primary);
  line-height: 1.6;
  white-space: pre-wrap;
  margin: 0;
}

.focus-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.focus-tag {
  margin: 0;
}

.team-table {
  width: 100%;
}

.no-data {
  color: var(--gt-color-info);
  font-size: var(--gt-font-size-sm);
}

.team-edit-table {
  width: 100%;
}

.team-member-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.team-member-row .el-input,
.team-member-row .el-select {
  flex: 1;
}
</style>
