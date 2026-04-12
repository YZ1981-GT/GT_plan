<template>
  <div class="contract-analysis-panel">
    <div class="panel-header">
      <h3>📑 合同智能分析</h3>
      <div class="header-actions">
        <button class="btn-primary" @click="triggerUpload">
          📤 上传合同
        </button>
        <input ref="fileInput" type="file" multiple accept=".pdf,.docx,.doc,.jpg,.jpeg,.png" @change="handleUpload" style="display:none" />
      </div>
    </div>

    <!-- 进度条 -->
    <div v-if="batchProgress > 0" class="progress-section">
      <div class="progress-bar-wrap">
        <div class="progress-bar" :style="{ width: batchProgress + '%' }"></div>
      </div>
      <span class="progress-text">{{ batchProgress }}% - {{ batchStatus }}</span>
    </div>

    <!-- 主内容区 -->
    <div class="main-content">
      <!-- 左侧：合同文件预览 -->
      <div class="left-panel">
        <div class="panel-section">
          <h4>📄 合同列表</h4>
          <div v-if="contracts.length === 0" class="empty-state">
            暂无合同，请上传
          </div>
          <div v-else class="contract-list">
            <div
              v-for="contract in contracts"
              :key="contract.id"
              class="contract-item"
              :class="{ active: selectedContract?.id === contract.id }"
              @click="selectContract(contract)"
            >
              <div class="contract-info">
                <span class="contract-no">{{ contract.contract_no }}</span>
                <span class="contract-type">{{ contractTypeLabel(contract.contract_type) }}</span>
              </div>
              <span :class="['status-badge', contract.analysis_status]">
                {{ analysisStatusLabel(contract.analysis_status) }}
              </span>
            </div>
          </div>
        </div>

        <!-- 文件预览 -->
        <div v-if="selectedContract" class="panel-section preview-section">
          <h4>文件预览</h4>
          <div class="file-preview">
            <div v-if="selectedContract.file_path" class="preview-placeholder">
              <span class="preview-icon">📄</span>
              <span>{{ selectedContract.file_name || '合同文件' }}</span>
              <a :href="selectedContract.file_path" target="_blank" class="btn-link">在新窗口打开</a>
            </div>
            <div v-else class="no-preview">
              暂无预览
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：AI提取结果 -->
      <div class="right-panel">
        <div v-if="!selectedContract" class="empty-state large">
          请从左侧选择一个合同查看分析结果
        </div>

        <template v-else>
          <!-- 合同基本信息 -->
          <div class="panel-section">
            <h4>📋 合同信息</h4>
            <div class="info-grid">
              <div class="info-item">
                <span class="info-label">合同编号</span>
                <span class="info-value">{{ selectedContract.contract_no || '-' }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">甲方</span>
                <span class="info-value">{{ selectedContract.party_a || '-' }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">乙方</span>
                <span class="info-value">{{ selectedContract.party_b || '-' }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">合同金额</span>
                <span class="info-value highlight">{{ formatCurrency(selectedContract.contract_amount) }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">合同日期</span>
                <span class="info-value">{{ selectedContract.contract_date || '-' }}</span>
              </div>
              <div class="info-item">
                <span class="info-label">有效期</span>
                <span class="info-value">
                  {{ selectedContract.effective_date || '-' }} 至 {{ selectedContract.expiry_date || '-' }}
                </span>
              </div>
            </div>
          </div>

          <!-- AI提取条款 -->
          <div class="panel-section">
            <div class="section-header">
              <h4>🔍 AI提取条款</h4>
              <button class="btn-sm" @click="analyzeContract" :disabled="analyzing">
                {{ analyzing ? '分析中...' : '🔄 重新分析' }}
              </button>
            </div>
            <div v-if="extractedClauses.length === 0" class="empty-state">
              暂无提取条款
            </div>
            <div v-else class="clause-list">
              <div
                v-for="clause in extractedClauses"
                :key="clause.id"
                class="clause-item"
              >
                <div class="clause-header">
                  <span class="clause-type">{{ clauseTypeLabel(clause.clause_type) }}</span>
                  <span :class="['confidence-badge', confidenceClass(clause.confidence_score)]">
                    {{ (clause.confidence_score * 100).toFixed(0) }}%
                  </span>
                  <span v-if="!clause.human_confirmed" class="ai-tag">AI辅助-待确认</span>
                </div>
                <div class="clause-content">{{ clause.clause_content }}</div>
                <div class="clause-actions">
                  <button
                    v-if="!clause.human_confirmed"
                    class="btn-xs"
                    @click="confirmClause(clause)"
                  >✅ 确认</button>
                </div>
              </div>
            </div>
          </div>

          <!-- 交叉比对结果 -->
          <div class="panel-section">
            <h4>🔗 与账面数据交叉比对</h4>
            <button class="btn-sm" @click="crossReference" :disabled="crossRefLoading">
              {{ crossRefLoading ? '比对中...' : '🔗 执行交叉比对' }}
            </button>
            <div v-if="crossRefResults.length === 0" class="empty-state">
              暂无比对结果
            </div>
            <table v-else class="cross-ref-table">
              <thead>
                <tr>
                  <th>比对项目</th>
                  <th>合同数据</th>
                  <th>账面数据</th>
                  <th>差异</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(r, idx) in crossRefResults" :key="idx">
                  <td>{{ r.item }}</td>
                  <td>{{ r.contractValue }}</td>
                  <td>{{ r.ledgerValue }}</td>
                  <td :class="{ 'diff-negative': r.difference < 0 }">
                    {{ formatCurrency(r.difference) }}
                  </td>
                  <td>
                    <span :class="['status-badge', r.status]">{{ r.statusText }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 关联底稿 -->
          <div class="panel-section">
            <h4>📎 关联底稿</h4>
            <div class="link-actions">
              <select v-model="linkWpId" class="wp-select">
                <option value="">选择关联底稿</option>
                <option v-for="wp in workpapers" :key="wp.id" :value="wp.id">
                  {{ wp.wp_name }} ({{ wp.wp_code }})
                </option>
              </select>
              <select v-model="linkType" class="type-select">
                <option value="revenue_recognition">收入确认</option>
                <option value="cutoff_test">截止测试</option>
                <option value="contingent_liability">或有负债</option>
                <option value="related_party">关联方交易</option>
                <option value="guarantee">担保事项</option>
              </select>
              <button class="btn-sm btn-primary" @click="linkToWorkpaper" :disabled="!linkWpId">
                关联底稿
              </button>
            </div>
            <div v-if="linkedWorkpapers.length > 0" class="linked-list">
              <div v-for="link in linkedWorkpapers" :key="link.id" class="linked-item">
                <span class="linked-wp">{{ link.workpaper_name }}</span>
                <span class="link-type">{{ linkTypeLabel(link.link_type) }}</span>
                <button class="btn-xs btn-danger" @click="unlinkWorkpaper(link)">解除</button>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 批量分析汇总 -->
    <div v-if="batchSummary" class="batch-summary">
      <h4>📊 批量分析汇总</h4>
      <div class="summary-stats">
        <div class="stat-item">
          <span class="stat-value">{{ batchSummary.total }}</span>
          <span class="stat-label">合同总数</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ batchSummary.analyzed }}</span>
          <span class="stat-label">已完成分析</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ batchSummary.withRisk }}</span>
          <span class="stat-label">含风险条款</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ batchSummary.relatedParty }}</span>
          <span class="stat-label">关联方合同</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { contractAI } from '@/services/aiApi'

const props = defineProps({
  projectId: { type: String, required: true },
})

const fileInput = ref(null)
const contracts = ref([])
const selectedContract = ref(null)
const extractedClauses = ref([])
const crossRefResults = ref([])
const linkedWorkpapers = ref([])
const workpapers = ref([])
const analyzing = ref(false)
const crossRefLoading = ref(false)
const batchProgress = ref(0)
const batchStatus = ref('')
const batchSummary = ref(null)

const linkWpId = ref('')
const linkType = ref('revenue_recognition')

function contractTypeLabel(type) {
  const m = {
    sales: '销售合同', purchase: '采购合同', service: '服务合同',
    lease: '租赁合同', loan: '借款合同', guarantee: '担保合同', other: '其他',
  }
  return m[type] || type
}

function analysisStatusLabel(status) {
  const m = { pending: '待分析', analyzing: '分析中', completed: '已完成', failed: '失败' }
  return m[status] || status
}

function clauseTypeLabel(type) {
  const m = {
    amount: '金额条款', payment_terms: '付款条款', delivery_terms: '交货条款',
    penalty: '违约条款', guarantee: '担保条款', pledge: '质押条款',
    related_party: '关联方条款', special_terms: '特殊条款', pricing: '定价条款', duration: '期限条款',
  }
  return m[type] || type
}

function linkTypeLabel(type) {
  const m = {
    revenue_recognition: '收入确认', cutoff_test: '截止测试',
    contingent_liability: '或有负债', related_party: '关联方交易', guarantee: '担保事项',
  }
  return m[type] || type
}

function confidenceClass(score) {
  if (score >= 0.9) return 'high'
  if (score >= 0.7) return 'medium'
  return 'low'
}

function formatCurrency(val) {
  if (val == null) return '-'
  return Number(val).toLocaleString('zh-CN', { style: 'currency', currency: 'CNY' })
}

async function loadContracts() {
  try {
    const result = await contractAI.getContractList(props.projectId)
    contracts.value = result.data || []
  } catch (e) {
    console.error(e)
    // 模拟数据
    contracts.value = [
      {
        id: '1', contract_no: 'CTR-2024-001', contract_type: 'sales',
        party_a: '公司A', party_b: '客户X公司', contract_amount: 5000000,
        effective_date: '2024-01-01', expiry_date: '2024-12-31',
        analysis_status: 'completed',
      },
      {
        id: '2', contract_no: 'CTR-2024-002', contract_type: 'purchase',
        party_a: '供应商Y公司', party_b: '公司A', contract_amount: 2000000,
        effective_date: '2024-03-01', expiry_date: '2025-02-28',
        analysis_status: 'pending',
      },
    ]
  }
}

async function loadWorkpapers() {
  try {
    // 从 workpaper API 加载
    const { workpaperApi } = await import('@/services/workpaperApi')
    const result = await workpaperApi.listWorkpapers(props.projectId)
    workpapers.value = result || []
  } catch (e) {
    console.error(e)
    workpapers.value = []
  }
}

function selectContract(contract) {
  selectedContract.value = contract
  loadClauses(contract.id)
  loadLinkedWorkpapers(contract.id)
}

async function loadClauses(contractId) {
  try {
    const result = await contractAI.getExtractedClauses(contractId)
    extractedClauses.value = result.data || []
  } catch (e) {
    console.error(e)
    // 模拟数据
    extractedClauses.value = [
      { id: '1', clause_type: 'payment_terms', clause_content: '付款方式：验收合格后30日内支付合同金额的95%，剩余5%作为质保金。', confidence_score: 0.95, human_confirmed: false },
      { id: '2', clause_type: 'penalty', clause_content: '违约责任：延迟交货按合同金额的0.1%/日计算违约金。', confidence_score: 0.88, human_confirmed: true },
      { id: '3', clause_type: 'related_party', clause_content: '本合同为关联交易，交易对方为本公司控股股东控制的企业。', confidence_score: 0.92, human_confirmed: false },
    ]
  }
}

async function loadLinkedWorkpapers(contractId) {
  try {
    const result = await contractAI.getLinkedWorkpapers(contractId)
    linkedWorkpapers.value = result.data || []
  } catch (e) {
    console.error(e)
    linkedWorkpapers.value = []
  }
}

function triggerUpload() {
  fileInput.value?.click()
}

async function handleUpload(e) {
  const files = Array.from(e.target.files)
  if (files.length === 0) return

  batchProgress.value = 1
  batchStatus.value = '上传中...'

  try {
    const formData = new FormData()
    files.forEach(f => formData.append('files', f))
    formData.append('project_id', props.projectId)

    const result = await contractAI.batchUpload(formData, (p) => {
      batchProgress.value = p
      batchStatus.value = p < 50 ? '上传中...' : p < 90 ? '分析中...' : '完成...'
    })

    batchProgress.value = 100
    batchStatus.value = '完成'
    await loadContracts()

    if (result.data?.task_id) {
      pollTaskStatus(result.data.task_id)
    }
  } catch (e) {
    console.error(e)
    batchStatus.value = '上传失败'
    batchProgress.value = 0
  }
}

async function pollTaskStatus(taskId) {
  // 轮询任务状态
  const interval = setInterval(async () => {
    try {
      const result = await contractAI.getTaskStatus(taskId)
      if (result.status === 'completed') {
        clearInterval(interval)
        batchSummary.value = result.summary
        await loadContracts()
      }
    } catch (e) {
      clearInterval(interval)
    }
  }, 2000)
}

async function analyzeContract() {
  if (!selectedContract.value) return
  analyzing.value = true
  try {
    const result = await contractAI.analyzeContract(props.projectId, selectedContract.value.id)
    extractedClauses.value = result.data || []
    selectedContract.value.analysis_status = 'completed'
  } catch (e) {
    console.error(e)
  } finally {
    analyzing.value = false
  }
}

async function confirmClause(clause) {
  clause.human_confirmed = true
  try {
    await contractAI.confirmClause(selectedContract.value.id, clause.id)
  } catch (e) {
    console.error(e)
  }
}

async function crossReference() {
  if (!selectedContract.value) return
  crossRefLoading.value = true
  try {
    const result = await contractAI.crossReference(props.projectId, selectedContract.value.id)
    crossRefResults.value = result.data || []
  } catch (e) {
    console.error(e)
    // 模拟数据
    crossRefResults.value = [
      { item: '收入确认金额', contractValue: '500万', ledgerValue: '480万', difference: -200000, status: 'mismatch', statusText: '不匹配' },
      { item: '回款周期', contractValue: '30天', ledgerValue: '45天', difference: 15, status: 'warning', statusText: '超出账期' },
      { item: '关联方识别', contractValue: '是', ledgerValue: '是', difference: 0, status: 'matched', statusText: '一致' },
    ]
  } finally {
    crossRefLoading.value = false
  }
}

async function linkToWorkpaper() {
  if (!selectedContract.value || !linkWpId.value) return
  try {
    const result = await contractAI.linkToWorkpaper(selectedContract.value.id, linkWpId.value, linkType.value)
    linkedWorkpapers.value.push(result.data)
    linkWpId.value = ''
  } catch (e) {
    console.error(e)
  }
}

async function unlinkWorkpaper(link) {
  try {
    await contractAI.unlinkWorkpaper(link.id)
    const idx = linkedWorkpapers.value.indexOf(link)
    if (idx >= 0) linkedWorkpapers.value.splice(idx, 1)
  } catch (e) {
    console.error(e)
  }
}

onMounted(() => {
  loadContracts()
  loadWorkpapers()
})
</script>

<style scoped>
.contract-analysis-panel { padding: 16px; height: 100%; display: flex; flex-direction: column; }

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.panel-header h3 { margin: 0; font-size: 16px; }

.progress-section { margin-bottom: 16px; }
.progress-bar-wrap {
  height: 8px;
  background: #f0f0f0;
  border-radius: 4px;
  overflow: hidden;
}
.progress-bar { height: 100%; background: #4b2d77; transition: width 0.3s; }
.progress-text { font-size: 12px; color: #666; margin-top: 4px; display: block; }

.main-content {
  display: flex;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.left-panel {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow: hidden;
}

.right-panel {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel-section {
  background: #fff;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 16px;
}
.panel-section h4 {
  margin: 0 0 12px;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.section-header h4 { margin: 0; }

.empty-state {
  padding: 16px;
  text-align: center;
  color: #999;
  background: #fafafa;
  border-radius: 4px;
}
.empty-state.large {
  padding: 48px;
  font-size: 14px;
}

.contract-list { display: flex; flex-direction: column; gap: 8px; }
.contract-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}
.contract-item:hover { background: #f0f0f0; }
.contract-item.active { background: rgba(75,45,119,0.1); border: 1px solid #4b2d77; }
.contract-info { display: flex; flex-direction: column; gap: 2px; }
.contract-no { font-weight: 600; font-size: 13px; }
.contract-type { font-size: 11px; color: #666; }

.status-badge {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}
.status-badge.pending { background: #fff7e6; color: #fa8c16; }
.status-badge.analyzing { background: #e6f7ff; color: #1890ff; }
.status-badge.completed { background: #f6ffed; color: #52c41a; }
.status-badge.failed { background: #fff2f0; color: #ff4d4f; }

.preview-section { flex: 1; display: flex; flex-direction: column; }
.preview-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px;
  background: #fafafa;
  border-radius: 8px;
  text-align: center;
}
.preview-icon { font-size: 48px; }
.btn-link { color: #4b2d77; font-size: 12px; }

.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.info-item { display: flex; flex-direction: column; gap: 2px; }
.info-label { font-size: 11px; color: #999; }
.info-value { font-size: 13px; color: #333; }
.info-value.highlight { color: #4b2d77; font-weight: 600; font-size: 15px; }

.clause-list { display: flex; flex-direction: column; gap: 12px; }
.clause-item {
  border: 1px solid #eee;
  border-radius: 6px;
  padding: 12px;
  background: #fafafa;
}
.clause-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.clause-type {
  font-weight: 600;
  font-size: 13px;
  color: #4b2d77;
}
.confidence-badge {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}
.confidence-badge.high { background: #f6ffed; color: #52c41a; }
.confidence-badge.medium { background: #fff7e6; color: #fa8c16; }
.confidence-badge.low { background: #fff2f0; color: #ff4d4f; }
.ai-tag {
  background: rgba(75,45,119,0.1);
  color: #4b2d77;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}
.clause-content { font-size: 13px; line-height: 1.6; color: #333; }
.clause-actions { margin-top: 8px; display: flex; gap: 8px; }

.cross-ref-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 12px;
  font-size: 12px;
}
.cross-ref-table th, .cross-ref-table td {
  border: 1px solid #eee;
  padding: 8px 12px;
  text-align: left;
}
.cross-ref-table th { background: #f9f9f9; font-weight: 600; }
.diff-negative { color: #ff4d4f; }

.link-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.wp-select, .type-select {
  padding: 6px 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 12px;
  min-width: 120px;
}

.linked-list { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }
.linked-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 4px;
}
.linked-wp { font-size: 13px; flex: 1; }
.link-type { font-size: 11px; color: #666; }

.btn-primary, .btn-sm, .btn-xs {
  padding: 6px 12px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.btn-primary { background: #4b2d77; color: #fff; border-color: #4b2d77; }
.btn-primary:disabled { background: #ccc; border-color: #ccc; cursor: not-allowed; }
.btn-xs { padding: 4px 8px; font-size: 11px; }
.btn-danger { background: #fff2f0; color: #ff4d4f; border-color: #ff4d4f; }

.header-actions { display: flex; gap: 8px; }

.batch-summary {
  margin-top: 16px;
  padding: 16px;
  background: #fafafa;
  border-radius: 8px;
}
.batch-summary h4 { margin: 0 0 12px; font-size: 14px; }
.summary-stats {
  display: flex;
  gap: 16px;
}
.stat-item {
  flex: 1;
  text-align: center;
  padding: 12px;
  background: #fff;
  border-radius: 6px;
}
.stat-value {
  display: block;
  font-size: 24px;
  font-weight: 700;
  color: #4b2d77;
}
.stat-label { font-size: 12px; color: #666; }
</style>
