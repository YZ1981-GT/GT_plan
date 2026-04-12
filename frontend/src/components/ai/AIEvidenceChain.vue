<template>
  <div class="ai-evidence-chain">
    <!-- 左侧：证据链列表 -->
    <aside class="chain-list">
      <div class="list-header">
        <h3>证据链</h3>
        <button class="btn-primary" @click="showCreateModal = true">+ 新建</button>
      </div>

      <div class="chain-items">
        <div
          v-for="chain in chains"
          :key="chain.chain_id"
          class="chain-item"
          :class="{ active: selectedChain?.chain_id === chain.chain_id }"
          @click="selectChain(chain)"
        >
          <div class="chain-name">{{ chain.chain_name }}</div>
          <div class="chain-meta">
            <span>{{ chain.business_cycle }}</span>
            <span class="score" :class="getScoreClass(chain.completeness_score)">
              {{ chain.completeness_score?.toFixed(0) || 0 }}%
            </span>
          </div>
        </div>
        <div v-if="chains.length === 0" class="empty">暂无证据链</div>
      </div>
    </aside>

    <!-- 右侧：证据链详情 -->
    <main class="chain-detail">
      <div v-if="!selectedChain" class="no-selection">
        <div class="icon">🔗</div>
        <p>选择或创建一个证据链</p>
      </div>

      <template v-else>
        <div class="detail-header">
          <div>
            <h2>{{ selectedChain.chain_name }}</h2>
            <p class="subtitle">{{ selectedChain.business_cycle }} · 完整性 {{ selectedChain.completeness_score?.toFixed(1) || 0 }}%</p>
          </div>
          <div class="header-actions">
            <button class="btn-sm" @click="analyzeChain" :disabled="analyzing">
              {{ analyzing ? '分析中...' : '🔍 AI分析' }}
            </button>
            <button class="btn-sm btn-primary" @click="showAddItemModal = true">+ 添加证据</button>
          </div>
        </div>

        <!-- 证据项时间线 -->
        <div class="evidence-timeline" v-if="selectedChain.items?.length">
          <div
            v-for="(item, idx) in selectedChain.items"
            :key="item.item_id"
            class="timeline-item"
          >
            <div class="timeline-marker">
              <div class="marker-dot" :class="{ key: item.is_key_evidence }"></div>
              <div class="marker-line" v-if="idx < selectedChain.items.length - 1"></div>
            </div>
            <div class="timeline-content">
              <div class="evidence-card">
                <div class="evidence-header">
                  <div class="evidence-title">
                    <span v-if="item.is_key_evidence" class="key-badge">关键</span>
                    {{ item.evidence_name }}
                  </div>
                  <div class="evidence-type badge">{{ item.evidence_type }}</div>
                </div>
                <div class="evidence-meta">
                  <span>来源: {{ item.source_module }}</span>
                  <span>序号: {{ item.item_order }}</span>
                  <span class="completeness" :class="getScoreClass(item.completeness)">
                    {{ item.completeness?.toFixed(0) || 0 }}%
                  </span>
                </div>
                <div class="evidence-desc" v-if="item.description">
                  {{ item.description }}
                </div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="no-items">
          <p>暂无证据项，请添加</p>
        </div>

        <!-- AI 分析结果 -->
        <div class="analysis-result" v-if="analysisResult">
          <h4>AI 分析结果</h4>
          <div class="result-content" v-html="renderAnalysis(analysisResult)"></div>
        </div>
      </template>
    </main>

    <!-- 创建证据链弹窗 -->
    <div class="modal-overlay" v-if="showCreateModal" @click.self="showCreateModal = false">
      <div class="modal">
        <h3>新建证据链</h3>
        <form @submit.prevent="createChain">
          <div class="form-group">
            <label>证据链名称</label>
            <input v-model="newChain.chain_name" required />
          </div>
          <div class="form-group">
            <label>业务循环</label>
            <select v-model="newChain.business_cycle">
              <option value="采购与付款">采购与付款</option>
              <option value="销售与收款">销售与收款</option>
              <option value="生产与存货">生产与存货</option>
              <option value="人力资源">人力资源</option>
              <option value="筹资与投资">筹资与投资</option>
              <option value="财务报告">财务报告</option>
            </select>
          </div>
          <div class="form-group">
            <label>描述（可选）</label>
            <textarea v-model="newChain.description" rows="2"></textarea>
          </div>
          <div class="form-actions">
            <button type="button" class="btn-sm" @click="showCreateModal = false">取消</button>
            <button type="submit" class="btn-primary">创建</button>
          </div>
        </form>
      </div>
    </div>

    <!-- 添加证据项弹窗 -->
    <div class="modal-overlay" v-if="showAddItemModal" @click.self="showAddItemModal = false">
      <div class="modal">
        <h3>添加证据项</h3>
        <form @submit.prevent="addItem">
          <div class="form-group">
            <label>证据名称</label>
            <input v-model="newItem.evidence_name" required />
          </div>
          <div class="form-group">
            <label>证据类型</label>
            <select v-model="newItem.evidence_type">
              <option value="external">外部证据</option>
              <option value="internal">内部证据</option>
              <option value="documentary">文档证据</option>
              <option value="electronic">电子证据</option>
            </select>
          </div>
          <div class="form-group">
            <label>来源模块</label>
            <input v-model="newItem.source_module" placeholder="如: 总账、发票系统" />
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea v-model="newItem.description" rows="2"></textarea>
          </div>
          <div class="form-group">
            <label>
              <input type="checkbox" v-model="newItem.is_key_evidence" />
              标记为关键证据
            </label>
          </div>
          <div class="form-actions">
            <button type="button" class="btn-sm" @click="showAddItemModal = false">取消</button>
            <button type="submit" class="btn-primary">添加</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAIEvidenceChain } from '@/composables/useAI'
import { aiEvidenceChain } from '@/api'

const props = defineProps({
  projectId: { type: String, required: true },
})

const {
  chains,
  currentChain,
  loading,
  analysisResult,
  createChain: createChainApi,
  addEvidenceItem: addItemApi,
  analyzeChain: analyzeChainApi,
  fetchChains,
  getChainDetails,
} = useAIEvidenceChain()

const selectedChain = ref(null)
const showCreateModal = ref(false)
const showAddItemModal = ref(false)
const analyzing = ref(false)

const newChain = ref({
  chain_name: '',
  business_cycle: '采购与付款',
  description: '',
})

const newItem = ref({
  evidence_name: '',
  evidence_type: 'documentary',
  source_module: '',
  description: '',
  is_key_evidence: false,
})

onMounted(async () => {
  await fetchChains(props.projectId)
})

async function selectChain(chain) {
  selectedChain.value = chain
  const details = await getChainDetails(chain.chain_id)
  selectedChain.value = details
  analysisResult.value = null
}

async function createChain() {
  const chain = await createChainApi({
    project_id: props.projectId,
    ...newChain.value,
  })
  chains.value.unshift(chain)
  showCreateModal.value = false
  newChain.value = { chain_name: '', business_cycle: '采购与付款', description: '' }
  await selectChain(chain)
}

async function addItem() {
  if (!selectedChain.value) return
  const item = await addItemApi({
    chain_id: selectedChain.value.chain_id,
    ...newItem.value,
  })
  selectedChain.value.items = selectedChain.value.items || []
  selectedChain.value.items.push(item)
  showAddItemModal.value = false
  newItem.value = { evidence_name: '', evidence_type: 'documentary', source_module: '', description: '', is_key_evidence: false }
  // 刷新链详情
  await selectChain(selectedChain.value)
}

async function analyzeChain() {
  if (!selectedChain.value) return
  analyzing.value = true
  try {
    const result = await analyzeChainApi(selectedChain.value.chain_id)
    analysisResult.value = result
  } catch (e) {
    console.error('Analysis failed:', e)
  } finally {
    analyzing.value = false
  }
}

function getScoreClass(score) {
  if (score >= 80) return 'high'
  if (score >= 50) return 'medium'
  return 'low'
}

function renderAnalysis(result) {
  if (!result) return ''
  if (typeof result === 'string') return result.replace(/\n/g, '<br>')
  return JSON.stringify(result, null, 2).replace(/\n/g, '<br>')
}
</script>

<style scoped>
.ai-evidence-chain {
  display: flex;
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, sans-serif;
}

.chain-list {
  width: 280px;
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
}

.list-header {
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #e4e7ed;
}

.list-header h3 { margin: 0; font-size: 16px; }

.chain-items {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.chain-item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.2s;
}

.chain-item:hover { background: #f5f7fa; }
.chain-item.active { background: #ecf5ff; border-left: 3px solid #409eff; }

.chain-name { font-size: 14px; color: #303133; margin-bottom: 4px; }

.chain-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #909399;
}

.score { font-weight: 600; }
.score.high { color: #67c23a; }
.score.medium { color: #e6a23c; }
.score.low { color: #f56c6c; }

.chain-detail {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
}

.no-selection {
  text-align: center;
  padding: 60px;
  color: #909399;
}

.icon { font-size: 48px; margin-bottom: 12px; }

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.detail-header h2 { margin: 0 0 4px; font-size: 20px; }
.subtitle { margin: 0; font-size: 14px; color: #909399; }

.header-actions { display: flex; gap: 8px; }

.evidence-timeline {
  position: relative;
  padding-left: 24px;
}

.timeline-marker {
  position: absolute;
  left: 7px;
}

.marker-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #409eff;
  border: 2px solid #fff;
  box-shadow: 0 0 0 2px #409eff;
}

.marker-dot.key {
  background: #e6a23c;
  box-shadow: 0 0 0 2px #e6a23c;
}

.marker-line {
  width: 2px;
  height: 100%;
  background: #e4e7ed;
  margin-left: 5px;
  margin-top: 4px;
}

.timeline-content {
  margin-left: 20px;
  margin-bottom: 16px;
}

.evidence-card {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 14px;
}

.evidence-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.evidence-title { font-size: 14px; font-weight: 500; display: flex; align-items: center; gap: 6px; }

.evidence-type { font-size: 12px; padding: 2px 8px; background: #ecf5ff; color: #409eff; border-radius: 10px; }

.evidence-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.evidence-desc {
  font-size: 13px;
  color: #606266;
  line-height: 1.5;
}

.key-badge {
  padding: 1px 6px;
  background: #fdf6ec;
  color: #e6a23c;
  border-radius: 8px;
  font-size: 11px;
}

.no-items {
  text-align: center;
  padding: 40px;
  color: #909399;
}

.analysis-result {
  margin-top: 24px;
  background: #fffbeb;
  border: 1px solid #fcd34d;
  border-radius: 8px;
  padding: 16px;
}

.analysis-result h4 { margin: 0 0 12px; font-size: 14px; color: #92400e; }

.result-content {
  font-size: 13px;
  line-height: 1.6;
  color: #78350f;
  white-space: pre-wrap;
}

.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  width: 440px;
  max-width: 90vw;
}

.modal h3 { margin: 0 0 16px; }

.form-group { margin-bottom: 14px; }
.form-group label { display: block; margin-bottom: 4px; font-size: 13px; color: #606266; }
.form-group input[type="text"],
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

.btn-primary {
  background: #409eff;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 8px 16px;
  cursor: pointer;
  font-size: 14px;
}

.btn-sm {
  padding: 6px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
}

.empty { text-align: center; padding: 40px 16px; color: #909399; font-size: 14px; }
</style>
