<template>
  <div class="evidence-chain-panel">
    <el-card class="panel-card">
      <template #header>
        <div class="panel-header">
          <span class="panel-title">🔗 证据链验证</span>
          <el-radio-group v-model="currentTab" size="default" @change="handleTabChange">
            <el-radio-button value="revenue">收入循环</el-radio-button>
            <el-radio-button value="purchase">采购循环</el-radio-button>
            <el-radio-button value="expense">费用报销</el-radio-button>
            <el-radio-button value="bank-analysis">银行流水分析</el-radio-button>
          </el-radio-group>
        </div>
      </template>

      <!-- 汇总卡片 -->
      <div class="summary-cards">
        <el-statistic title="总链条" :value="summary.total">
          <template #prefix><el-icon><Document /></el-icon></template>
        </el-statistic>
        <el-statistic title="已匹配" :value="summary.matched">
          <template #prefix><el-icon style="color: #52c41a"><CircleCheck /></el-icon></template>
        </el-statistic>
        <el-statistic title="不匹配" :value="summary.unmatched">
          <template #prefix><el-icon style="color: #fa8c16"><Warning /></el-icon></template>
        </el-statistic>
        <el-statistic title="缺失" :value="summary.missing">
          <template #prefix><el-icon style="color: #ff4d4f"><Close /></el-icon></template>
        </el-statistic>
        <el-statistic title="高风险" :value="summary.highRisk">
          <template #prefix><el-icon style="color: #ff4d4f"><WarnTriangleFilled /></el-icon></template>
        </el-statistic>
      </div>

      <!-- 证据链可视化 -->
      <div class="chain-visualization">
        <h4>证据链流程图</h4>
        <div class="chain-nodes">
          <template v-for="(node, idx) in chainNodes" :key="idx">
            <div
              class="chain-node"
              :class="[node.status, { 'missing': node.missing }]"
            >
              <div class="node-icon">{{ node.icon }}</div>
              <div class="node-label">{{ node.label }}</div>
              <div class="node-status">{{ node.statusText }}</div>
            </div>
            <div
              v-if="idx < chainNodes.length - 1"
              :key="'line-' + idx"
              class="connector-line"
              :class="{ 'line-error': chainNodes[idx + 1]?.missing || chainNodes[idx + 1]?.status === 'mismatched' }"
            >
              <el-icon><Right /></el-icon>
            </div>
          </template>
          <el-empty v-if="chainNodes.length === 0 && !loading" description="暂无数据" :image-size="60" />
        </div>
      </div>

      <!-- 异常清单 -->
      <div class="anomaly-section">
        <h4>⚠️ 异常清单</h4>
        <el-empty v-if="anomalies.length === 0" description="未发现异常，证据链完整" :image-size="60">
          <template #image>
            <el-icon size="48" color="#52c41a"><SuccessFilled /></el-icon>
          </template>
        </el-empty>
        <el-table v-else :data="anomalies" stripe border size="small" max-height="300">
          <el-table-column label="风险等级" width="100">
            <template #default="{ row }">
              <el-tag :type="riskTagType(row.riskLevel)" size="small">
                {{ row.riskLevelText }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="异常描述" min-width="200" show-overflow-tooltip />
          <el-table-column label="涉及单据" min-width="150">
            <template #default="{ row }">
              <el-tag v-for="(doc, i) in row.documents" :key="i" size="small" style="margin: 2px">
                {{ doc }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="suggestedProcedure" label="建议程序" min-width="200" show-overflow-tooltip />
        </el-table>
      </div>

      <!-- 操作按钮 -->
      <div class="action-bar">
        <el-button type="primary" :loading="loading" @click="runVerification" :icon="Refresh">
          {{ loading ? '验证中...' : '运行验证' }}
        </el-button>
        <el-button @click="exportReport" :icon="Download">导出报告</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import {
  Document, CircleCheck, Warning, Close, WarnTriangleFilled, Right, SuccessFilled,
  Refresh, Download
} from '@element-plus/icons-vue'
import type { FormInstance } from 'element-plus'
import { ElMessage } from 'element-plus'
import { evidenceChain } from '@/services/aiApi'
import type {
  EvidenceChainNode,
  EvidenceAnomaly,
  EvidenceChainSummary
} from '@/services/aiApi'

interface ChainTab {
  label: string
  value: string
}

const props = defineProps<{
  projectId: string
}>()

const currentTab = ref<string>('revenue')
const loading = ref(false)

const chainTabs: ChainTab[] = [
  { label: '收入循环', value: 'revenue' },
  { label: '采购循环', value: 'purchase' },
  { label: '费用报销', value: 'expense' },
  { label: '银行流水分析', value: 'bank-analysis' },
]

const summary = reactive<EvidenceChainSummary>({
  total: 0,
  matched: 0,
  unmatched: 0,
  missing: 0,
  highRisk: 0,
})

// 证据链节点
const chainNodes = ref<EvidenceChainNode[]>([])

// 异常清单
const anomalies = ref<EvidenceAnomaly[]>([])

// 节点定义
const nodeDefinitions: Record<string, Array<{ icon: string; label: string; statusKey: string }>> = {
  revenue: [
    { icon: '📄', label: '合同', statusKey: 'contract' },
    { icon: '📋', label: '订单', statusKey: 'order' },
    { icon: '📦', label: '出库单', statusKey: 'outbound' },
    { icon: '🚚', label: '物流单', statusKey: 'logistics' },
    { icon: '💰', label: '发票', statusKey: 'invoice' },
    { icon: '📝', label: '凭证', statusKey: 'voucher' },
    { icon: '🏦', label: '回款', statusKey: 'receipt' },
  ],
  purchase: [
    { icon: '📄', label: '采购合同', statusKey: 'contract' },
    { icon: '📋', label: '采购订单', statusKey: 'order' },
    { icon: '📦', label: '入库单', statusKey: 'inbound' },
    { icon: '💰', label: '发票', statusKey: 'invoice' },
    { icon: '📝', label: '凭证', statusKey: 'voucher' },
    { icon: '🏦', label: '付款', statusKey: 'payment' },
  ],
  expense: [
    { icon: '📝', label: '申请单', statusKey: 'request' },
    { icon: '💰', label: '发票', statusKey: 'invoice' },
    { icon: '📋', label: '报销单', statusKey: 'report' },
    { icon: '✅', label: '审批', statusKey: 'approval' },
    { icon: '📝', label: '凭证', statusKey: 'voucher' },
  ],
  'bank-analysis': [
    { icon: '📊', label: '流水分析', statusKey: 'analysis' },
    { icon: '⚠️', label: '大额异常', statusKey: 'large' },
    { icon: '🔄', label: '循环检测', statusKey: 'circular' },
    { icon: '🏢', label: '关联方', statusKey: 'related' },
    { icon: '📅', label: '期末集中', statusKey: 'periodEnd' },
  ],
}

async function handleTabChange(tab: string) {
  currentTab.value = tab
  await loadData()
}

async function loadData() {
  // 重置数据
  chainNodes.value = []
  anomalies.value = []
  Object.assign(summary, { total: 0, matched: 0, unmatched: 0, missing: 0, highRisk: 0 })

  // 尝试从 API 加载
  try {
    loading.value = true
    const result = await evidenceChain.getChain(props.projectId, currentTab.value)
    if (result && result.data) {
      updateFromResult(result.data)
    }
  } catch (e) {
    console.error('Failed to load evidence chain:', e)
    // API 不可用时使用模拟数据
    useMockData()
  } finally {
    loading.value = false
  }
}

function useMockData() {
  const nodes = nodeDefinitions[currentTab.value] || []
  chainNodes.value = nodes.map((n, idx) => {
    const statuses = ['matched', 'matched', 'mismatched', 'matched', 'missing'] as const
    const status = statuses[idx % statuses.length]
    return {
      icon: n.icon,
      label: n.label,
      status,
      missing: status === 'missing',
      statusText: status === 'matched' ? '已匹配' : status === 'mismatched' ? '不匹配' : '缺失',
    }
  })

  anomalies.value = [
    {
      riskLevel: 'high',
      riskLevelText: '高风险',
      description: '存在付款但无对应入库记录',
      documents: ['付款记录 #2024001', '入库单缺失'],
      suggestedProcedure: '检查供应商收货确认文件，追查付款依据',
    },
    {
      riskLevel: 'medium',
      riskLevelText: '中风险',
      description: '发票金额与合同金额不一致',
      documents: ['发票 #INV-2024005', '合同 #CTR-2024002'],
      suggestedProcedure: '核对合同条款，确认是否存在折扣或变更',
    },
  ]

  summary.total = chainNodes.value.length
  summary.matched = chainNodes.value.filter(n => n.status === 'matched').length
  summary.unmatched = chainNodes.value.filter(n => n.status === 'mismatched').length
  summary.missing = chainNodes.value.filter(n => n.missing).length
  summary.highRisk = anomalies.value.filter(a => a.riskLevel === 'high').length
}

function updateFromResult(data: {
  nodes?: EvidenceChainNode[]
  anomalies?: EvidenceAnomaly[]
  summary?: EvidenceChainSummary
}) {
  if (data.nodes) {
    chainNodes.value = data.nodes
  }
  if (data.anomalies) {
    anomalies.value = data.anomalies
  }
  if (data.summary) {
    Object.assign(summary, data.summary)
  }
}

function riskTagType(level: string): 'danger' | 'warning' | 'success' | 'info' {
  const map: Record<string, 'danger' | 'warning' | 'success' | 'info'> = {
    high: 'danger',
    medium: 'warning',
    low: 'success',
  }
  return map[level] || 'info'
}

async function runVerification() {
  loading.value = true
  try {
    let result
    if (currentTab.value === 'bank-analysis') {
      // 调用银行流水分析 API: POST /api/projects/{id}/evidence-chain/bank-analysis
      result = await evidenceChain.analyzeBankStatements(props.projectId)
    } else {
      // 调用对应循环验证 API: POST /api/projects/{id}/evidence-chain/{type}
      result = await evidenceChain.verifyChain(props.projectId, currentTab.value)
    }
    if (result && result.data) {
      updateFromResult(result.data)
      ElMessage.success('验证完成')
    }
  } catch (e) {
    console.error('Verification error:', e)
    useMockData()
    ElMessage.warning('API 不可用，使用模拟数据')
  } finally {
    loading.value = false
  }
}

function exportReport() {
  const report = {
    projectId: props.projectId,
    chainType: currentTab.value,
    summary,
    anomalies: anomalies.value,
    chainNodes: chainNodes.value,
    generatedAt: new Date().toISOString(),
  }
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `evidence-chain-${currentTab.value}-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success('报告已导出')
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.evidence-chain-panel {
  padding: 16px;
}

.panel-card {
  border-radius: 8px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

@media (max-width: 768px) {
  .summary-cards {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 480px) {
  .summary-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}

.chain-visualization {
  margin-bottom: 24px;
}

.chain-visualization h4 {
  margin-bottom: 12px;
  font-size: 14px;
  color: #606266;
}

.chain-nodes {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow-x: auto;
  padding: 20px;
  background: #f5f7fa;
  border-radius: 8px;
  min-height: 120px;
}

.chain-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 16px;
  background: #fff;
  border: 2px solid #52c41a;
  border-radius: 8px;
  min-width: 80px;
  transition: all 0.3s;
}

.chain-node.mismatched {
  border-color: #fa8c16;
  background: #fffbf0;
}

.chain-node.missing {
  border-color: #ff4d4f;
  background: #fff0f0;
}

.node-icon {
  font-size: 24px;
  margin-bottom: 4px;
}

.node-label {
  font-size: 12px;
  font-weight: 600;
  color: #333;
}

.node-status {
  font-size: 11px;
  color: #666;
  margin-top: 2px;
}

.connector-line {
  display: flex;
  align-items: center;
  color: #52c41a;
  flex-shrink: 0;
}

.connector-line.line-error {
  color: #ff4d4f;
}

.anomaly-section {
  margin-bottom: 24px;
}

.anomaly-section h4 {
  margin-bottom: 12px;
  font-size: 14px;
  color: #606266;
}

.action-bar {
  display: flex;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid #eee;
}
</style>
