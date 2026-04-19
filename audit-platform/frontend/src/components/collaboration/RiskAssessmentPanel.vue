<template>
  <div class="gt-risk-assessment-panel">
    <div class="panel-header">
      <h3>风险评估</h3>
      <el-button type="primary" size="small" @click="showAddDialog = true">
        <el-icon><Plus /></el-icon> 添加风险
      </el-button>
    </div>

    <!-- Risk Matrix Heatmap -->
    <div class="risk-heatmap">
      <h4>风险矩阵热力图</h4>
      <div class="heatmap-container">
        <table class="heatmap-table">
          <thead>
            <tr>
              <th></th>
              <th>控制风险-高</th>
              <th>控制风险-中</th>
              <th>控制风险-低</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="ir in ['high', 'medium', 'low']" :key="ir">
              <td class="row-label">固有风险-{{ ir === 'high' ? '高' : ir === 'medium' ? '中' : '低' }}</td>
              <td
                v-for="cr in ['high', 'medium', 'low']"
                :key="cr"
                class="heatmap-cell"
                :style="{ backgroundColor: getHeatmapColor(ir, cr) }"
              >
                <span class="cell-count">{{ getCellCount(ir, cr) }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="heatmap-legend">
          <span class="legend-item"><span class="color-box" style="background:#F56C6C"></span> 高风险</span>
          <span class="legend-item"><span class="color-box" style="background:#E6A23C"></span> 中风险</span>
          <span class="legend-item"><span class="color-box" style="background:#67C23A"></span> 低风险</span>
        </div>
      </div>
    </div>

    <!-- Risk Assessment Table -->
    <el-table :data="risks" stripe class="risk-table" max-height="400">
      <el-table-column prop="account_or_cycle" label="科目/循环" width="140" />
      <el-table-column prop="assertion_level" label="认定层次" width="120">
        <template #default="{ row }">
          <el-tag size="small">{{ formatAssertion(row.assertion_level) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="inherent_risk" label="固有风险" width="100">
        <template #default="{ row }">
          <el-tag :type="riskType(row.inherent_risk)" size="small">
            {{ row.inherent_risk === 'high' ? '高' : row.inherent_risk === 'medium' ? '中' : '低' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="control_risk" label="控制风险" width="100">
        <template #default="{ row }">
          <el-tag :type="riskType(row.control_risk)" size="small">
            {{ row.control_risk === 'high' ? '高' : row.control_risk === 'medium' ? '中' : '低' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="combined_risk" label="组合风险" width="100">
        <template #default="{ row }">
          <el-tag :type="riskType(row.combined_risk)" size="small" class="combined-risk">
            {{ row.combined_risk === 'high' ? '高' : row.combined_risk === 'medium' ? '中' : '低' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="is_significant_risk" label="特别风险" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.is_significant_risk" type="danger" size="small">是</el-tag>
          <span v-else class="text-muted">否</span>
        </template>
      </el-table-column>
      <el-table-column prop="response_strategy" label="应对策略" min-width="200">
        <template #default="{ row }">
          <el-input
            v-if="row.is_significant_risk"
            v-model="row.response_strategy"
            type="textarea"
            :rows="2"
            placeholder="请输入应对策略"
            @blur="saveResponse(row)"
          />
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="deleteRisk(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Add Risk Dialog -->
    <el-dialog append-to-body v-model="showAddDialog" title="添加风险评估" width="600px">
      <el-form :model="newRisk" label-width="120px">
        <el-form-item label="科目/循环">
          <el-input v-model="newRisk.account_or_cycle" placeholder="如: 销售收入" />
        </el-form-item>
        <el-form-item label="认定层次">
          <el-select v-model="newRisk.assertion_level" placeholder="选择认定">
            <el-option label="存在" value="existence" />
            <el-option label="完整性" value="completeness" />
            <el-option label="权利和义务" value="rights_obligations" />
            <el-option label="计价" value="valuation" />
            <el-option label="准确性" value="accuracy" />
            <el-option label="截止" value="cutoff" />
            <el-option label="分类" value="classification" />
          </el-select>
        </el-form-item>
        <el-form-item label="固有风险">
          <el-radio-group v-model="newRisk.inherent_risk">
            <el-radio label="high">高</el-radio>
            <el-radio label="medium">中</el-radio>
            <el-radio label="low">低</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="控制风险">
          <el-radio-group v-model="newRisk.control_risk">
            <el-radio label="high">高</el-radio>
            <el-radio label="medium">中</el-radio>
            <el-radio label="low">低</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="风险描述">
          <el-input v-model="newRisk.risk_description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="特别风险">
          <el-switch v-model="newRisk.is_significant_risk" />
        </el-form-item>
        <el-form-item v-if="newRisk.is_significant_risk" label="应对策略">
          <el-input v-model="newRisk.response_strategy" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="addRisk">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { riskApi } from '@/services/collaborationApi'

interface Risk {
  id: string
  project_id: string
  account_or_cycle: string
  assertion_level: string
  inherent_risk: string
  control_risk: string
  combined_risk: string
  is_significant_risk: boolean
  risk_description: string
  response_strategy: string
}

const props = defineProps<{
  projectId: string
}>()

const risks = ref<Risk[]>([])
const showAddDialog = ref(false)
const newRisk = ref({
  account_or_cycle: '',
  assertion_level: 'existence',
  inherent_risk: 'medium',
  control_risk: 'medium',
  risk_description: '',
  is_significant_risk: false,
  response_strategy: '',
})

// Heatmap color mapping
const riskColors: Record<string, string> = {
  high: '#F56C6C',
  medium: '#E6A23C',
  low: '#67C23A',
}

function getHeatmapColor(ir: string, cr: string): string {
  const matrix: Record<string, Record<string, string>> = {
    high: { high: '#F56C6C', medium: '#E6A23C', low: '#E6A23C' },
    medium: { high: '#E6A23C', medium: '#E6A23C', low: '#67C23A' },
    low: { high: '#67C23A', medium: '#67C23A', low: '#67C23A' },
  }
  return matrix[ir]?.[cr] || '#f0f0f0'
}

function getCellCount(ir: string, cr: string): number {
  return risks.value.filter(
    r => r.inherent_risk === ir && r.control_risk === cr
  ).length
}

function riskType(level: string): string {
  const map: Record<string, string> = {
    high: 'danger',
    medium: 'warning',
    low: 'success',
  }
  return map[level] || 'info'
}

function formatAssertion(level: string): string {
  const map: Record<string, string> = {
    existence: '存在',
    completeness: '完整性',
    rights_obligations: '权利和义务',
    valuation: '计价',
    accuracy: '准确性',
    cutoff: '截止',
    classification: '分类',
  }
  return map[level] || level
}

async function loadRisks() {
  try {
    const { data } = await riskApi.list(props.projectId)
    risks.value = data || []
  } catch {
    risks.value = []
  }
}

async function addRisk() {
  if (!newRisk.value.account_or_cycle) {
    ElMessage.warning('请输入科目/循环')
    return
  }
  try {
    const { data } = await riskApi.create(props.projectId, newRisk.value)
    risks.value.push(data)
    showAddDialog.value = false
    newRisk.value = {
      account_or_cycle: '',
      assertion_level: 'existence',
      inherent_risk: 'medium',
      control_risk: 'medium',
      risk_description: '',
      is_significant_risk: false,
      response_strategy: '',
    }
    ElMessage.success('风险已添加')
  } catch {
    ElMessage.error('添加失败')
  }
}

async function saveResponse(risk: Risk) {
  try {
    await riskApi.updateResponse(props.projectId, risk.id, { response_strategy: risk.response_strategy })
    ElMessage.success('应对策略已保存')
  } catch {
    ElMessage.error('保存失败')
  }
}

async function deleteRisk(risk: Risk) {
  risks.value = risks.value.filter(r => r.id !== risk.id)
  ElMessage.success('风险已删除')
}

loadRisks()
</script>

<style scoped>
.gt-risk-assessment-panel {
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
.risk-heatmap {
  margin-bottom: 20px;
  background: #f9f9f9;
  border-radius: 8px;
  padding: 16px;
}
.risk-heatmap h4 {
  margin: 0 0 12px;
  font-size: 14px;
  color: #606266;
}
.heatmap-container {
  display: flex;
  align-items: flex-start;
  gap: 24px;
}
.heatmap-table {
  border-collapse: collapse;
}
.heatmap-table th,
.heatmap-table td {
  border: 1px solid #dcdfe6;
  padding: 8px 16px;
  text-align: center;
}
.heatmap-table th {
  background: #f5f7fa;
  font-weight: 600;
  font-size: 13px;
}
.row-label {
  background: #f5f7fa;
  font-weight: 600;
  font-size: 13px;
}
.heatmap-cell {
  min-width: 80px;
  min-height: 50px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.cell-count {
  font-weight: 700;
  font-size: 18px;
  color: #fff;
}
.heatmap-legend {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.color-box {
  display: inline-block;
  width: 16px;
  height: 16px;
  border-radius: 3px;
}
.risk-table {
  font-size: 13px;
}
.combined-risk {
  font-weight: 700;
}
.text-muted {
  color: #909399;
}
</style>
