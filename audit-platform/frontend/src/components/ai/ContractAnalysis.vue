<template>
  <div class="contract-analysis">
    <div class="panel-header">
      <h3>📑 合同智能分析</h3>
      <div class="header-actions">
        <button class="btn-primary" @click="showUpload = true">📤 上传合同</button>
      </div>
    </div>

    <!-- 上传弹窗 -->
    <div v-if="showUpload" class="modal-overlay" @click.self="showUpload = false">
      <div class="modal">
        <h4>上传合同</h4>
        <div class="form-group">
          <label>合同编号</label>
          <input v-model="uploadForm.contract_no" placeholder="请输入合同编号" />
        </div>
        <div class="form-group">
          <label>合同类型</label>
          <select v-model="uploadForm.contract_type">
            <option value="">请选择</option>
            <option value="sales">销售合同</option>
            <option value="purchase">采购合同</option>
            <option value="service">服务合同</option>
            <option value="lease">租赁合同</option>
            <option value="loan">借款合同</option>
            <option value="guarantee">担保合同</option>
            <option value="other">其他</option>
          </select>
        </div>
        <div class="form-group">
          <label>合同文件</label>
          <input type="file" @change="handleFileSelect" accept=".pdf,.doc,.docx,.jpg,.png" />
        </div>
        <div class="modal-actions">
          <button @click="showUpload = false">取消</button>
          <button class="btn-primary" @click="uploadContract">上传并分析</button>
        </div>
      </div>
    </div>

    <!-- 合同列表 -->
    <div v-if="!showUpload" class="contract-list">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="contracts.length === 0" class="empty-state">
        暂无合同，请上传合同文件
      </div>
      <div
        v-for="contract in contracts"
        :key="contract.id"
        class="contract-card"
        :class="{ selected: selectedId === contract.id }"
        @click="selectContract(contract)"
      >
        <div class="contract-info">
          <span class="contract-no">{{ contract.contract_no || '未编号' }}</span>
          <span :class="['status-badge', contract.analysis_status]">
            {{ statusLabel(contract.analysis_status) }}
          </span>
        </div>
        <div class="contract-meta">
          <span>{{ contractTypeLabel(contract.contract_type) }}</span>
          <span v-if="contract.contract_amount">金额：{{ formatCurrency(contract.contract_amount) }}</span>
          <span v-if="contract.party_b">对手方：{{ contract.party_b }}</span>
        </div>
      </div>
    </div>

    <!-- 合同详情/分析结果 -->
    <div v-if="selectedContract" class="contract-detail">
      <div class="detail-tabs">
        <button
          v-for="tab in ['clause', 'cross', 'link']"
          :key="tab"
          :class="['tab-btn', { active: activeTab === tab }]"
          @click="activeTab = tab"
        >
          {{ tabLabel(tab) }}
        </button>
      </div>

      <!-- 关键条款 -->
      <div v-if="activeTab === 'clause'" class="clause-section">
        <div v-if="clausesLoading" class="loading">分析中...</div>
        <div v-else>
          <div
            v-for="clause in clauses"
            :key="clause.id"
            class="clause-item"
            :class="{ unconfirmed: !clause.human_confirmed }"
          >
            <div class="clause-header">
              <span class="clause-type">{{ clauseTypeLabel(clause.clause_type) }}</span>
              <span :class="['confidence', confidenceClass(clause.confidence_score)]">
                {{ clause.confidence_score ? (clause.confidence_score * 100).toFixed(0) + '%' : '' }}
              </span>
            </div>
            <div class="clause-content">{{ clause.clause_content }}</div>
            <div class="clause-actions">
              <button
                v-if="!clause.human_confirmed"
                class="btn-sm"
                @click="confirmClause(clause)"
              >✅ 确认</button>
              <span v-else class="confirmed-label">已确认</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 交叉引用 -->
      <div v-if="activeTab === 'cross'" class="cross-section">
        <div v-if="crossLoading" class="loading">分析中...</div>
        <div v-else>
          <div
            v-for="ref in crossRefs"
            :key="ref.id"
            class="cross-ref-item"
          >
            <span class="ref-type">{{ ref.reference_type }}</span>
            <span class="ref-target">{{ ref.reference_value }}</span>
            <span :class="['risk-badge', ref.risk_level]">{{ ref.risk_level }}</span>
          </div>
        </div>
      </div>

      <!-- 工作底稿关联 -->
      <div v-if="activeTab === 'link'" class="link-section">
        <div class="link-list">
          <div
            v-for="link in wpLinks"
            :key="link.id"
            class="wp-link-item"
          >
            <span class="link-type">{{ linkTypeLabel(link.link_type) }}</span>
            <span class="link-desc">{{ link.link_description }}</span>
            <span class="wp-id">底稿ID: {{ link.workpaper_id?.slice(0, 8) }}</span>
          </div>
        </div>
        <button class="btn-link-wp" @click="showAddLink = true">🔗 关联工作底稿</button>
      </div>
    </div>

    <!-- 添加关联弹窗 -->
    <div v-if="showAddLink" class="modal-overlay" @click.self="showAddLink = false">
      <div class="modal">
        <h4>关联工作底稿</h4>
        <div class="form-group">
          <label>关联类型</label>
          <select v-model="newLink.link_type">
            <option value="revenue_recognition">收入确认</option>
            <option value="cutoff_test">截止测试</option>
            <option value="contingent_liability">或有负债</option>
            <option value="related_party">关联方</option>
            <option value="guarantee">担保</option>
          </select>
        </div>
        <div class="form-group">
          <label>工作底稿ID</label>
          <input v-model="newLink.workpaper_id" placeholder="输入底稿ID" />
        </div>
        <div class="form-group">
          <label>关联说明</label>
          <textarea v-model="newLink.link_description" rows="3"></textarea>
        </div>
        <div class="modal-actions">
          <button @click="showAddLink = false">取消</button>
          <button class="btn-primary" @click="addWPLink">确认关联</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { contractApi } from '@/api'

const props = defineProps({ projectId: { type: String, required: true } })

const loading = ref(false)
const contracts = ref([])
const selectedId = ref(null)
const selectedContract = ref(null)
const clauses = ref([])
const crossRefs = ref([])
const wpLinks = ref([])
const clausesLoading = ref(false)
const crossLoading = ref(false)
const activeTab = ref('clause')
const showUpload = ref(false)
const showAddLink = ref(false)
const uploadForm = reactive({ contract_no: '', contract_type: '', file: null })
const newLink = reactive({ link_type: '', workpaper_id: '', link_description: '' })

async function loadContracts() {
  loading.value = true
  try {
    const res = await contractApi.list(props.projectId)
    contracts.value = res.data || []
  } finally {
    loading.value = false
  }
}

async function selectContract(contract) {
  selectedId.value = contract.id
  selectedContract.value = contract
  activeTab.value = 'clause'
  await loadClauses(contract.id)
}

async function loadClauses(contractId) {
  clausesLoading.value = true
  try {
    const res = await contractApi.getClauses(contractId)
    clauses.value = res.data || []
  } finally {
    clausesLoading.value = false
  }
}

async function uploadContract() {
  if (!uploadForm.file) return
  const formData = new FormData()
  formData.append('file', uploadForm.file)
  formData.append('project_id', props.projectId)
  if (uploadForm.contract_no) formData.append('contract_no', uploadForm.contract_no)
  if (uploadForm.contract_type) formData.append('contract_type', uploadForm.contract_type)
  try {
    await contractApi.upload(formData)
    showUpload.value = false
    uploadForm.contract_no = ''
    uploadForm.contract_type = ''
    uploadForm.file = null
    await loadContracts()
  } catch (e) {
    console.error(e)
  }
}

function handleFileSelect(e) {
  uploadForm.file = e.target.files[0]
}

async function confirmClause(clause) {
  await contractApi.confirmClause(clause.id)
  clause.human_confirmed = true
}

async function addWPLink() {
  await contractApi.createWPLink({
    contract_id: selectedContract.value.id,
    workpaper_id: newLink.workpaper_id,
    link_type: newLink.link_type,
    link_description: newLink.link_description
  })
  showAddLink.value = false
  newLink.link_type = ''
  newLink.workpaper_id = ''
  newLink.link_description = ''
}

function statusLabel(s) {
  return { pending: '⏳ 待分析', analyzing: '🔄 分析中', completed: '✅ 已完成', failed: '❌ 失败' }[s] || s
}
function contractTypeLabel(t) {
  return { sales: '销售', purchase: '采购', service: '服务', lease: '租赁', loan: '借款', guarantee: '担保', other: '其他' }[t] || t
}
function tabLabel(t) {
  return { clause: '关键条款', cross: '交叉引用', link: '底稿关联' }[t]
}
function clauseTypeLabel(t) {
  return { amount: '金额条款', payment_terms: '付款条件', delivery_terms: '交付条款', penalty: '违约条款', guarantee: '担保条款', pledge: '质押条款', related_party: '关联交易', special_terms: '特殊条款', pricing: '定价条款', duration: '期限条款' }[t] || t
}
function linkTypeLabel(t) {
  return { revenue_recognition: '收入确认', cutoff_test: '截止测试', contingent_liability: '或有负债', related_party: '关联方', guarantee: '担保' }[t] || t
}
function confidenceClass(score) {
  if (!score) return ''
  if (score < 0.7) return 'low'
  if (score < 0.85) return 'medium'
  return 'high'
}
function formatCurrency(val) {
  if (!val) return '-'
  return Number(val).toLocaleString('zh-CN', { style: 'currency', currency: 'CNY' })
}

// 初始加载
loadContracts()
</script>

<style scoped>
.contract-analysis { padding: 16px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.panel-header h3 { margin: 0; font-size: 16px; }

.contract-list { display: flex; flex-direction: column; gap: 8px; max-height: 400px; overflow-y: auto; }

.contract-card {
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 10px 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.contract-card:hover { border-color: #4b2d77; }
.contract-card.selected { border-color: #4b2d77; background: rgba(75,45,119,0.05); }

.contract-info { display: flex; justify-content: space-between; align-items: center; }
.contract-no { font-weight: 600; font-size: 14px; }
.contract-meta { display: flex; gap: 12px; font-size: 12px; color: #666; margin-top: 4px; }

.status-badge { font-size: 11px; padding: 2px 6px; border-radius: 4px; }
.status-badge.pending { background: #fff7e6; color: #fa8c16; }
.status-badge.completed { background: #f6ffed; color: #52c41a; }
.status-badge.analyzing { background: #e6f7ff; color: #1890ff; }
.status-badge.failed { background: #fff2f0; color: #ff4d4f; }

.detail-tabs { display: flex; gap: 4px; margin-bottom: 12px; }
.tab-btn { padding: 4px 12px; border: 1px solid #ddd; background: #fff; border-radius: 4px; cursor: pointer; font-size: 12px; }
.tab-btn.active { background: #4b2d77; color: #fff; border-color: #4b2d77; }

.clause-section, .cross-section, .link-section { display: flex; flex-direction: column; gap: 8px; max-height: 350px; overflow-y: auto; }

.clause-item { border: 1px solid #eee; border-radius: 8px; padding: 10px; }
.clause-item.unconfirmed { border-color: #faad14; background: #fffbe6; }
.clause-header { display: flex; justify-content: space-between; margin-bottom: 6px; }
.clause-type { font-weight: 600; font-size: 13px; color: #4b2d77; }
.clause-content { font-size: 13px; color: #333; line-height: 1.5; white-space: pre-wrap; }
.clause-actions { margin-top: 6px; text-align: right; }
.confirmed-label { font-size: 11px; color: #52c41a; }

.confidence { font-size: 11px; }
.confidence.low { color: #ff4d4f; }
.confidence.medium { color: #faad14; }
.confidence.high { color: #52c41a; }

.cross-ref-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border: 1px solid #eee;
  border-radius: 6px;
  font-size: 13px;
}
.ref-type { background: rgba(75,45,119,0.1); padding: 2px 6px; border-radius: 4px; font-size: 11px; }
.ref-target { flex: 1; }
.risk-badge { padding: 2px 6px; border-radius: 4px; font-size: 11px; }
.risk-badge.high { background: #fff2f0; color: #ff4d4f; }
.risk-badge.medium { background: #fff7e6; color: #fa8c16; }
.risk-badge.low { background: #f6ffed; color: #52c41a; }

.wp-link-item { display: flex; gap: 8px; padding: 8px; border: 1px solid #eee; border-radius: 6px; font-size: 13px; align-items: center; }
.link-type { background: rgba(75,45,119,0.1); padding: 2px 6px; border-radius: 4px; font-size: 11px; white-space: nowrap; }
.link-desc { flex: 1; color: #666; font-size: 12px; }
.wp-id { font-size: 11px; color: #999; }

.btn-primary { padding: 6px 16px; background: #4b2d77; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-primary:hover { background: #3d2066; }
.btn-link-wp { padding: 6px 12px; background: #fff; border: 1px solid #4b2d77; color: #4b2d77; border-radius: 4px; cursor: pointer; font-size: 12px; margin-top: 8px; }
.btn-sm { padding: 2px 8px; border: 1px solid #ddd; background: #fff; border-radius: 4px; cursor: pointer; font-size: 11px; }
.loading, .empty-state { text-align: center; padding: 20px; color: #999; font-size: 13px; }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 200; }
.modal { background: #fff; border-radius: 12px; padding: 24px; width: 400px; max-width: 90%; }
.modal h4 { margin: 0 0 16px; font-size: 16px; }
.form-group { margin-bottom: 12px; }
.form-group label { display: block; font-size: 13px; color: #666; margin-bottom: 4px; }
.form-group input, .form-group select, .form-group textarea { width: 100%; padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; box-sizing: border-box; }
.form-group textarea { resize: vertical; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.modal-actions button { padding: 6px 16px; border-radius: 6px; border: 1px solid #ddd; background: #fff; cursor: pointer; font-size: 13px; }
</style>
