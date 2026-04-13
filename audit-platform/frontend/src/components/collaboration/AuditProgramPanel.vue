<template>
  <div class="gt-audit-program-panel">
    <div class="panel-header">
      <h3>审计程序</h3>
      <el-button type="primary" size="small" @click="showAddDialog = true">
        <el-icon><Plus /></el-icon> 添加程序
      </el-button>
    </div>

    <!-- Filters -->
    <div class="filters">
      <el-select v-model="filterType" placeholder="程序类型" clearable size="small" style="width: 150px">
        <el-option label="风险评估" value="risk_assessment" />
        <el-option label="控制测试" value="control_test" />
        <el-option label="实质性程序" value="substantive" />
      </el-select>
      <el-select v-model="filterCycle" placeholder="审计循环" clearable size="small" style="width: 150px">
        <el-option label="销售与收款" value="sales" />
        <el-option label="采购与付款" value="purchases" />
        <el-option label="生产与存货" value="inventory" />
        <el-option label="人力资源" value="hr" />
        <el-option label="财务" value="finance" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="执行状态" clearable size="small" style="width: 150px">
        <el-option label="未开始" value="not_started" />
        <el-option label="进行中" value="in_progress" />
        <el-option label="已完成" value="completed" />
        <el-option label="不适用" value="not_applicable" />
      </el-select>
    </div>

    <!-- Audit Procedures Table -->
    <el-table :data="filteredProcedures" stripe class="procedure-table" max-height="400">
      <el-table-column prop="procedure_code" label="程序编号" width="120" />
      <el-table-column prop="procedure_name" label="程序名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="procedure_type" label="类型" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="procedureTypeTag(row.procedure_type)">
            {{ formatProcedureType(row.procedure_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="audit_cycle" label="审计循环" width="120">
        <template #default="{ row }">
          {{ formatCycle(row.audit_cycle) }}
        </template>
      </el-table-column>
      <el-table-column prop="related_risk_id" label="关联风险" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.related_risk_id" size="small" type="info">已关联</el-tag>
          <span v-else class="text-muted">未关联</span>
        </template>
      </el-table-column>
      <el-table-column prop="workpaper_link" label="关联底稿" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.related_wp_code" size="small">{{ row.related_wp_code }}</el-tag>
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="execution_status" label="状态" width="100">
        <template #default="{ row }">
          <el-select
            :model-value="row.execution_status"
            size="small"
            @change="updateStatus(row, $event)"
          >
            <el-option label="未开始" value="not_started" />
            <el-option label="进行中" value="in_progress" />
            <el-option label="已完成" value="completed" />
            <el-option label="不适用" value="not_applicable" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="completed_date" label="完成日期" width="120">
        <template #default="{ row }">
          {{ row.executed_at ? formatDate(row.executed_at) : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="linkWorkpaper(row)">关联底稿</el-button>
          <el-button type="danger" link size="small" @click="deleteProcedure(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Coverage Summary -->
    <div class="coverage-summary">
      <el-row :gutter="20">
        <el-col :span="6">
          <div class="stat-card">
            <div class="stat-value">{{ procedures.length }}</div>
            <div class="stat-label">总程序数</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card">
            <div class="stat-value">{{ completedCount }}</div>
            <div class="stat-label">已完成</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card">
            <div class="stat-value">{{ inProgressCount }}</div>
            <div class="stat-label">进行中</div>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="stat-card">
            <div class="stat-value">{{ completionRate }}%</div>
            <div class="stat-label">完成率</div>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- Add Procedure Dialog -->
    <el-dialog v-model="showAddDialog" title="添加审计程序" width="600px">
      <el-form :model="newProcedure" label-width="120px">
        <el-form-item label="程序编号">
          <el-input v-model="newProcedure.procedure_code" placeholder="如: AP-SALES-001" />
        </el-form-item>
        <el-form-item label="程序名称">
          <el-input v-model="newProcedure.procedure_name" placeholder="如: 销售收入的截止测试" />
        </el-form-item>
        <el-form-item label="程序类型">
          <el-select v-model="newProcedure.procedure_type">
            <el-option label="风险评估程序" value="risk_assessment" />
            <el-option label="控制测试" value="control_test" />
            <el-option label="实质性程序" value="substantive" />
          </el-select>
        </el-form-item>
        <el-form-item label="审计循环">
          <el-select v-model="newProcedure.audit_cycle">
            <el-option label="销售与收款" value="sales" />
            <el-option label="采购与付款" value="purchases" />
            <el-option label="生产与存货" value="inventory" />
            <el-option label="人力资源" value="hr" />
            <el-option label="财务" value="finance" />
          </el-select>
        </el-form-item>
        <el-form-item label="科目代码">
          <el-input v-model="newProcedure.account_code" placeholder="如: 6001" />
        </el-form-item>
        <el-form-item label="程序描述">
          <el-input v-model="newProcedure.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="关联风险">
          <el-select v-model="newProcedure.related_risk_id" clearable>
            <el-option
              v-for="risk in risks"
              :key="risk.id"
              :label="`${risk.account_or_cycle} - ${risk.combined_risk}`"
              :value="risk.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="addProcedure">确定</el-button>
      </template>
    </el-dialog>

    <!-- Link Workpaper Dialog -->
    <el-dialog v-model="showLinkDialog" title="关联底稿" width="400px">
      <el-form label-width="100px">
        <el-form-item label="底稿代码">
          <el-input v-model="linkWorkpaperCode" placeholder="如: WP-SALES-001" />
        </el-form-item>
        <el-form-item label="底稿ID">
          <el-input v-model="linkWorkpaperId" placeholder="底稿UUID" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showLinkDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmLinkWorkpaper">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { auditProgramApi } from '@/services/collaborationApi'

interface Procedure {
  id: string
  program_id: string
  procedure_code: string
  procedure_name: string
  procedure_type: string
  audit_cycle: string
  account_code: string
  description: string
  execution_status: string
  executed_at: string | null
  related_risk_id: string | null
  related_wp_code: string | null
}

interface Risk {
  id: string
  account_or_cycle: string
  combined_risk: string
}

const props = defineProps<{
  projectId: string
}>()

const procedures = ref<Procedure[]>([])
const risks = ref<Risk[]>([])
const showAddDialog = ref(false)
const showLinkDialog = ref(false)
const selectedProcedure = ref<Procedure | null>(null)
const linkWorkpaperCode = ref('')
const linkWorkpaperId = ref('')

const filterType = ref('')
const filterCycle = ref('')
const filterStatus = ref('')

const newProcedure = ref({
  procedure_code: '',
  procedure_name: '',
  procedure_type: 'substantive',
  audit_cycle: 'sales',
  account_code: '',
  description: '',
  related_risk_id: '',
})

const filteredProcedures = computed(() => {
  return procedures.value.filter(p => {
    if (filterType.value && p.procedure_type !== filterType.value) return false
    if (filterCycle.value && p.audit_cycle !== filterCycle.value) return false
    if (filterStatus.value && p.execution_status !== filterStatus.value) return false
    return true
  })
})

const completedCount = computed(() => procedures.value.filter(p => p.execution_status === 'completed').length)
const inProgressCount = computed(() => procedures.value.filter(p => p.execution_status === 'in_progress').length)
const completionRate = computed(() => {
  if (procedures.value.length === 0) return 0
  return Math.round((completedCount.value / procedures.value.length) * 100)
})

function procedureTypeTag(type: string): string {
  const map: Record<string, string> = {
    risk_assessment: 'info',
    control_test: 'warning',
    substantive: 'success',
  }
  return map[type] || 'info'
}

function formatProcedureType(type: string): string {
  const map: Record<string, string> = {
    risk_assessment: '风险评估',
    control_test: '控制测试',
    substantive: '实质性',
  }
  return map[type] || type
}

function formatCycle(cycle: string): string {
  const map: Record<string, string> = {
    sales: '销售与收款',
    purchases: '采购与付款',
    inventory: '生产与存货',
    hr: '人力资源',
    finance: '财务',
  }
  return map[cycle] || cycle
}

function formatDate(iso: string): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('zh-CN')
}

async function loadProcedures() {
  try {
    const { data } = await auditProgramApi.listProcedures(props.projectId)
    procedures.value = data || []
  } catch {
    procedures.value = []
  }
}

async function addProcedure() {
  if (!newProcedure.value.procedure_code || !newProcedure.value.procedure_name) {
    ElMessage.warning('请填写程序编号和名称')
    return
  }
  try {
    const { data } = await auditProgramApi.createProcedure(props.projectId, props.projectId, newProcedure.value)
    procedures.value.push(data)
    showAddDialog.value = false
    newProcedure.value = {
      procedure_code: '',
      procedure_name: '',
      procedure_type: 'substantive',
      audit_cycle: 'sales',
      account_code: '',
      description: '',
      related_risk_id: '',
    }
    ElMessage.success('程序已添加')
  } catch {
    ElMessage.error('添加失败')
  }
}

async function updateStatus(proc: Procedure, status: string) {
  proc.execution_status = status
  if (status === 'completed') {
    proc.executed_at = new Date().toISOString()
  }
  try {
    await auditProgramApi.updateProcedureStatus(props.projectId, proc.id, { status, conclusion: '' })
    ElMessage.success('状态已更新')
  } catch {
    ElMessage.error('更新失败')
  }
}

function linkWorkpaper(proc: Procedure) {
  selectedProcedure.value = proc
  linkWorkpaperCode.value = proc.related_wp_code || ''
  linkWorkpaperId.value = ''
  showLinkDialog.value = true
}

async function confirmLinkWorkpaper() {
  if (!selectedProcedure.value) return
  try {
    await auditProgramApi.linkWorkpaper(props.projectId, selectedProcedure.value.id, {
      workpaper_id: linkWorkpaperId.value,
      workpaper_code: linkWorkpaperCode.value,
    })
    selectedProcedure.value.related_wp_code = linkWorkpaperCode.value
    showLinkDialog.value = false
    ElMessage.success('底稿已关联')
  } catch {
    ElMessage.error('关联失败')
  }
}

async function deleteProcedure(proc: Procedure) {
  procedures.value = procedures.value.filter(p => p.id !== proc.id)
  ElMessage.success('程序已删除')
}

loadProcedures()
</script>

<style scoped>
.gt-audit-program-panel {
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
.filters {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
.procedure-table {
  font-size: 13px;
}
.text-muted {
  color: #909399;
}
.coverage-summary {
  margin-top: 16px;
}
.stat-card {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #409EFF;
}
.stat-label {
  font-size: 12px;
  color: #606266;
  margin-top: 4px;
}
</style>
