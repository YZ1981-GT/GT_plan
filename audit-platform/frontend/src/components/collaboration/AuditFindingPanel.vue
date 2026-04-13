<template>
  <div class="gt-audit-finding-panel">
    <div class="panel-header">
      <h3>审计发现</h3>
      <el-button type="primary" size="small" @click="showAddDialog = true">
        <el-icon><Plus /></el-icon> 添加发现
      </el-button>
    </div>

    <!-- Findings Table -->
    <el-table :data="findings" stripe class="finding-table" max-height="400">
      <el-table-column prop="finding_code" label="发现编号" width="150" />
      <el-table-column prop="finding_description" label="描述" min-width="200" show-overflow-tooltip />
      <el-table-column prop="severity" label="严重程度" width="100">
        <template #default="{ row }">
          <el-tag :type="severityTag(row.severity)" size="small">
            {{ severityLabel(row.severity) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="affected_account" label="受影响科目" width="120" />
      <el-table-column prop="finding_amount" label="财务影响" width="120">
        <template #default="{ row }">
          {{ row.finding_amount ? formatCurrency(row.finding_amount) : '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="management_response" label="管理层回复" min-width="150" show-overflow-tooltip />
      <el-table-column prop="final_disposition" label="最终处理" width="110">
        <template #default="{ row }">
          <el-tag :type="dispositionTag(row.final_treatment)" size="small">
            {{ dispositionLabel(row.final_treatment) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="linked_adjustment" label="关联调整" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.related_adjustment_id" type="success" size="small">已关联</el-tag>
          <span v-else class="text-muted">未关联</span>
        </template>
      </el-table-column>
      <el-table-column prop="linked_workpaper" label="关联底稿" width="100">
        <template #default="{ row }">
          <span v-if="row.related_wp_code">{{ row.related_wp_code }}</span>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="editFinding(row)">编辑</el-button>
          <el-button type="danger" link size="small" @click="deleteFinding(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Financial Impact Summary -->
    <div class="impact-summary">
      <el-row :gutter="20">
        <el-col :span="6">
          <div class="stat-card">
            <div class="stat-value">{{ findings.length }}</div>
            <div class="stat-label">总发现数</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card">
            <div class="stat-value">{{ highSeverityCount }}</div>
            <div class="stat-label">高严重程度</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card">
            <div class="stat-value">{{ formatCurrency(totalImpact) }}</div>
            <div class="stat-label">财务影响总额</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card">
            <div class="stat-value">{{ adjustedCount }}</div>
            <div class="stat-label">已调整</div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- Add Finding Dialog -->
    <el-dialog v-model="showAddDialog" title="添加审计发现" width="650px">
      <el-form :model="newFinding" label-width="130px">
        <el-form-item label="发现描述">
          <el-input v-model="newFinding.finding_description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="严重程度">
          <el-radio-group v-model="newFinding.severity">
            <el-radio label="high">高</el-radio>
            <el-radio label="medium">中</el-radio>
            <el-radio label="low">低</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="受影响科目">
          <el-input v-model="newFinding.affected_account" placeholder="如: 应收账款" />
        </el-form-item>
        <el-form-item label="财务影响金额">
          <el-input-number v-model="newFinding.finding_amount" :precision="2" :step="1000" />
        </el-form-item>
        <el-form-item label="管理层回复">
          <el-input v-model="newFinding.management_response" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="最终处理">
          <el-select v-model="newFinding.final_treatment">
            <el-option label="调整" value="adjusted" />
            <el-option label="未调整" value="unadjusted" />
            <el-option label="披露" value="disclosed" />
            <el-option label="无需处理" value="no_action" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联调整分录">
          <el-select v-model="newFinding.related_adjustment_id" clearable>
            <el-option label="请选择" value="" />
            <!-- Would populate with adjustment entries -->
          </el-select>
        </el-form-item>
        <el-form-item label="关联底稿">
          <el-input v-model="newFinding.related_wp_code" placeholder="底稿代码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="addFinding">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { findingApi } from '@/services/collaborationApi'

interface Finding {
  id: string
  project_id: string
  finding_code: string
  finding_description: string
  severity: string
  affected_account: string | null
  finding_amount: number | null
  management_response: string | null
  final_treatment: string | null
  related_adjustment_id: string | null
  related_wp_code: string | null
}

const props = defineProps<{
  projectId: string
}>()

const findings = ref<Finding[]>([])
const showAddDialog = ref(false)

const newFinding = ref({
  finding_description: '',
  severity: 'medium',
  affected_account: '',
  finding_amount: null as number | null,
  management_response: '',
  final_treatment: '',
  related_adjustment_id: '',
  related_wp_code: '',
})

const highSeverityCount = computed(() => findings.value.filter(f => f.severity === 'high').length)
const totalImpact = computed(() => findings.value.reduce((sum, f) => sum + (f.finding_amount || 0), 0))
const adjustedCount = computed(() => findings.value.filter(f => f.final_treatment === 'adjusted').length)

function severityTag(severity: string): string {
  const map: Record<string, string> = {
    high: 'danger',
    medium: 'warning',
    low: 'success',
  }
  return map[severity] || 'info'
}

function severityLabel(severity: string): string {
  const map: Record<string, string> = {
    high: '高',
    medium: '中',
    low: '低',
  }
  return map[severity] || severity
}

function dispositionTag(treatment: string | null): string {
  const map: Record<string, string> = {
    adjusted: 'success',
    unadjusted: 'danger',
    disclosed: 'warning',
    no_action: 'info',
  }
  return map[treatment || ''] || 'info'
}

function dispositionLabel(treatment: string | null): string {
  const map: Record<string, string> = {
    adjusted: '已调整',
    unadjusted: '未调整',
    disclosed: '披露',
    no_action: '无需处理',
  }
  return map[treatment || ''] || '-'
}

function formatCurrency(amount: number): string {
  if (!amount) return '-'
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
  }).format(amount)
}

async function loadFindings() {
  try {
    const { data } = await findingApi.list(props.projectId)
    findings.value = data || []
  } catch {
    findings.value = []
  }
}

async function addFinding() {
  if (!newFinding.value.finding_description) {
    ElMessage.warning('请填写发现描述')
    return
  }
  try {
    const { data } = await findingApi.create(props.projectId, newFinding.value)
    findings.value.push(data)
    showAddDialog.value = false
    resetNewFinding()
    ElMessage.success('审计发现已添加')
  } catch {
    ElMessage.error('添加失败')
  }
}

function editFinding(finding: Finding) {
  newFinding.value = {
    finding_description: finding.finding_description,
    severity: finding.severity,
    affected_account: finding.affected_account || '',
    finding_amount: finding.finding_amount,
    management_response: finding.management_response || '',
    final_treatment: finding.final_treatment || '',
    related_adjustment_id: finding.related_adjustment_id || '',
    related_wp_code: finding.related_wp_code || '',
  }
  showAddDialog.value = true
}

async function deleteFinding(finding: Finding) {
  findings.value = findings.value.filter(f => f.id !== finding.id)
  ElMessage.success('审计发现已删除')
}

function resetNewFinding() {
  newFinding.value = {
    finding_description: '',
    severity: 'medium',
    affected_account: '',
    finding_amount: null,
    management_response: '',
    final_treatment: '',
    related_adjustment_id: '',
    related_wp_code: '',
  }
}

loadFindings()
</script>

<style scoped>
.gt-audit-finding-panel {
  padding: 16px;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.panel-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.finding-table {
  font-size: 13px;
}
.text-muted {
  color: #909399;
}
.impact-summary {
  margin-top: 16px;
}
.stat-card {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}
.stat-value {
  font-size: 20px;
  font-weight: 700;
  color: #F56C6C;
}
.stat-label {
  font-size: 12px;
  color: #606266;
  margin-top: 4px;
}
</style>
