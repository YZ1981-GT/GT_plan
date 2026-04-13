<template>
  <div class="gt-audit-procedure-panel">
    <div class="panel-header">
      <span class="panel-title">审计程序清单</span>
      <div class="header-actions">
        <el-select
          v-model="filterType"
          placeholder="筛选类型"
          clearable
          size="small"
          style="width: 160px"
        >
          <el-option label="全部" value="" />
          <el-option label="风险评估" value="risk_assessment" />
          <el-option label="控制测试" value="control_test" />
          <el-option label="实质性程序" value="substantive" />
        </el-select>
        <el-select
          v-model="filterCycle"
          placeholder="筛选循环"
          clearable
          size="small"
          style="width: 140px"
        >
          <el-option label="全部" value="" />
          <el-option label="销售与收款" value="sales" />
          <el-option label="采购与付款" value="purchasing" />
          <el-option label="生产与存货" value="production" />
          <el-option label="人力资源" value="hr" />
          <el-option label="筹资与投资" value="financing" />
          <el-option label="货币资金" value="cash" />
        </el-select>
        <el-button type="primary" size="small" @click="openCreateDialog">
          新建程序
        </el-button>
      </div>
    </div>

    <el-table
      :data="filteredProcedures"
      stripe
      class="procedure-table"
      empty-text="暂无审计程序"
    >
      <el-table-column prop="procedure_code" label="程序编号" width="120" />
      <el-table-column prop="procedure_name" label="程序名称" min-width="200" />
      <el-table-column label="类型" width="130">
        <template #default="{ row }">
          <el-tag :type="typeTagType(row.procedure_type)" size="small">
            {{ typeLabel(row.procedure_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="audit_cycle" label="循环" width="120">
        <template #default="{ row }">
          {{ cycleLabel(row.audit_cycle) }}
        </template>
      </el-table-column>
      <el-table-column label="执行状态" width="120">
        <template #default="{ row }">
          <el-select
            :model-value="row.execution_status"
            size="small"
            @change="(val: string) => onStatusChange(row, val)"
          >
            <el-option label="未开始" value="not_started" />
            <el-option label="进行中" value="in_progress" />
            <el-option label="已完成" value="completed" />
            <el-option label="不适用" value="not_applicable" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="完成日期" width="120">
        <template #default="{ row }">
          {{ row.executed_at || '-' }}
        </template>
      </el-table-column>
      <el-table-column prop="related_wp_code" label="关联底稿" width="120">
        <template #default="{ row }">
          <el-button
            v-if="row.related_wp_code"
            type="primary"
            link
            size="small"
            @click="linkWorkpaper(row)"
          >
            {{ row.related_wp_code }}
          </el-button>
          <el-button
            v-else
            type="info"
            link
            size="small"
            @click="linkWorkpaper(row)"
          >
            关联
          </el-button>
        </template>
      </el-table-column>
      <el-table-column prop="conclusion" label="结论" min-width="150" show-overflow-tooltip />
    </el-table>

    <!-- 新建程序对话框 -->
    <el-dialog v-model="createDialogVisible" title="新建审计程序" width="600px">
      <el-form :model="procedureForm" label-width="110px">
        <el-form-item label="程序编号" required>
          <el-input v-model="procedureForm.procedure_code" placeholder="如：AP-001" />
        </el-form-item>
        <el-form-item label="程序名称" required>
          <el-input v-model="procedureForm.procedure_name" placeholder="审计程序名称" />
        </el-form-item>
        <el-form-item label="程序类型" required>
          <el-select v-model="procedureForm.procedure_type" style="width: 100%">
            <el-option label="风险评估程序" value="risk_assessment" />
            <el-option label="控制测试" value="control_test" />
            <el-option label="实质性程序" value="substantive" />
          </el-select>
        </el-form-item>
        <el-form-item label="审计循环">
          <el-select v-model="procedureForm.audit_cycle" style="width: 100%">
            <el-option label="销售与收款" value="sales" />
            <el-option label="采购与付款" value="purchasing" />
            <el-option label="生产与存货" value="production" />
            <el-option label="人力资源" value="hr" />
            <el-option label="筹资与投资" value="financing" />
            <el-option label="货币资金" value="cash" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="procedureForm.description"
            type="textarea"
            :rows="3"
            placeholder="程序描述..."
          />
        </el-form-item>
        <el-form-item label="关联底稿">
          <el-input
            v-model="procedureForm.related_wp_code"
            placeholder="底稿编号（可选）"
          />
        </el-form-item>
        <el-form-item label="关联风险">
          <el-select
            v-model="procedureForm.related_risk_id"
            clearable
            placeholder="选择关联风险（可选）"
            style="width: 100%"
          >
            <el-option
              v-for="risk in risks"
              :key="risk.id"
              :label="`${risk.account_or_cycle} - ${risk.assertion_level}`"
              :value="risk.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitProcedure">保存</el-button>
      </template>
    </el-dialog>

    <!-- 关联底稿对话框 -->
    <el-dialog v-model="linkDialogVisible" title="关联底稿" width="400px">
      <el-form label-width="80px">
        <el-form-item label="底稿编号">
          <el-input v-model="linkForm.related_wp_code" placeholder="输入底稿编号" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="linkDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmLink">确认关联</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { auditProgramApi, riskApi } from '@/services/collaborationApi'

interface Procedure {
  id: string
  project_id: string
  procedure_code: string
  procedure_name: string
  procedure_type: string
  audit_cycle?: string
  account_code?: string
  description?: string
  execution_status: string
  executed_by?: string
  executed_at?: string
  conclusion?: string
  related_wp_code?: string
  related_risk_id?: string
}

interface RiskAssessment {
  id: string
  account_or_cycle: string
  assertion_level: string
}

const props = defineProps<{
  projectId: string
}>()

const procedures = ref<Procedure[]>([])
const risks = ref<RiskAssessment[]>([])
const filterType = ref('')
const filterCycle = ref('')
const createDialogVisible = ref(false)
const linkDialogVisible = ref(false)
const selectedProcedure = ref<Procedure | null>(null)

const procedureForm = ref<{
  procedure_code: string
  procedure_name: string
  procedure_type: string
  audit_cycle: string
  description: string
  related_wp_code: string
  related_risk_id: string
}>({
  procedure_code: '',
  procedure_name: '',
  procedure_type: 'substantive',
  audit_cycle: '',
  description: '',
  related_wp_code: '',
  related_risk_id: '',
})

const linkForm = ref({
  related_wp_code: '',
})

const filteredProcedures = computed(() => {
  return procedures.value.filter(p => {
    if (filterType.value && p.procedure_type !== filterType.value) return false
    if (filterCycle.value && p.audit_cycle !== filterCycle.value) return false
    return true
  })
})

function typeLabel(type: string): string {
  const labels: Record<string, string> = {
    risk_assessment: '风险评估',
    control_test: '控制测试',
    substantive: '实质性程序',
  }
  return labels[type] || type
}

function typeTagType(type: string): string {
  const types: Record<string, string> = {
    risk_assessment: 'info',
    control_test: 'warning',
    substantive: '',
  }
  return types[type] || 'info'
}

function cycleLabel(cycle: string): string {
  const labels: Record<string, string> = {
    sales: '销售收款',
    purchasing: '采购付款',
    production: '生产存货',
    hr: '人力资源',
    financing: '筹资投资',
    cash: '货币资金',
    other: '其他',
  }
  return labels[cycle] || cycle || '-'
}

async function loadProcedures() {
  try {
    const { data } = await auditProgramApi.listProcedures(props.projectId)
    procedures.value = data || []
  } catch (e) {
    console.error('加载审计程序失败', e)
  }
}

async function loadRisks() {
  try {
    const { data } = await riskApi.list(props.projectId)
    risks.value = data || []
  } catch (e) {
    console.error('加载风险评估失败', e)
  }
}

function openCreateDialog() {
  procedureForm.value = {
    procedure_code: '',
    procedure_name: '',
    procedure_type: 'substantive',
    audit_cycle: '',
    description: '',
    related_wp_code: '',
    related_risk_id: '',
  }
  createDialogVisible.value = true
}

async function submitProcedure() {
  if (!procedureForm.value.procedure_code || !procedureForm.value.procedure_name) {
    ElMessage.warning('请填写程序编号和名称')
    return
  }
  try {
    await auditProgramApi.createProcedure(props.projectId, '', procedureForm.value)
    ElMessage.success('创建成功')
    createDialogVisible.value = false
    await loadProcedures()
  } catch (e) {
    ElMessage.error('创建失败')
  }
}

async function onStatusChange(row: Procedure, newStatus: string) {
  try {
    await auditProgramApi.updateProcedureStatus(
      props.projectId,
      row.id,
      { execution_status: newStatus }
    )
    row.execution_status = newStatus
    ElMessage.success('状态已更新')
  } catch (e) {
    ElMessage.error('更新状态失败')
  }
}

function linkWorkpaper(row: Procedure) {
  selectedProcedure.value = row
  linkForm.value.related_wp_code = row.related_wp_code || ''
  linkDialogVisible.value = true
}

async function confirmLink() {
  if (!selectedProcedure.value) return
  try {
    await auditProgramApi.linkWorkpaper(
      props.projectId,
      selectedProcedure.value.id,
      { related_wp_code: linkForm.value.related_wp_code }
    )
    selectedProcedure.value.related_wp_code = linkForm.value.related_wp_code
    linkDialogVisible.value = false
    ElMessage.success('关联成功')
  } catch (e) {
    ElMessage.error('关联失败')
  }
}

onMounted(() => {
  loadProcedures()
  loadRisks()
})
</script>

<style scoped>
.gt-audit-procedure-panel {
  padding: 16px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.procedure-table {
  width: 100%;
}
</style>
