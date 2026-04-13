<template>
  <div class="gt-evidence-chain-view">
    <div class="panel-header">
      <h3>🔗 证据链分析</h3>
      <div class="header-actions">
        <select v-model="chainType" class="type-select">
          <option value="all">全部类型</option>
          <option value="revenue">收入</option>
          <option value="purchase">采购</option>
          <option value="expense">费用</option>
        </select>
        <button class="btn-primary" @click="loadChains">🔍 查询</button>
        <button class="btn-primary" @click="generateChain">🤖 AI生成</button>
      </div>
    </div>

    <!-- 风险汇总 -->
    <div class="risk-summary">
      <div class="risk-item high">
        <span class="risk-count">{{ riskStats.high }}</span>
        <span class="risk-label">高风险</span>
      </div>
      <div class="risk-item medium">
        <span class="risk-count">{{ riskStats.medium }}</span>
        <span class="risk-label">中风险</span>
      </div>
      <div class="risk-item low">
        <span class="risk-count">{{ riskStats.low }}</span>
        <span class="risk-label">低风险</span>
      </div>
    </div>

    <!-- 证据链列表 -->
    <div class="chain-list">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="chains.length === 0" class="empty-state">
        暂无证据链数据，点击「AI生成」开始分析
      </div>
      <div
        v-for="chain in chains"
        :key="chain.id"
        class="chain-card"
        :class="`risk-${chain.risk_level}`"
      >
        <div class="chain-header">
          <span class="chain-type-badge">{{ chainTypeLabel(chain.chain_type) }}</span>
          <span class="chain-step">步骤 {{ chain.chain_step }}</span>
          <span :class="['risk-badge', chain.risk_level]">
            {{ riskLabel(chain.risk_level) }}
          </span>
        </div>
        <div class="chain-doc-ids">
          <span class="doc-label">单据ID：</span>
          <code class="doc-id">{{ chain.source_document_id?.slice(0, 8) }}...</code>
          <span v-if="chain.target_document_id" class="arrow">→</span>
          <code v-if="chain.target_document_id" class="doc-id">
            {{ chain.target_document_id?.slice(0, 8) }}...
          </code>
        </div>
        <div class="chain-match">
          <span :class="['match-status', chain.match_status]">
            {{ matchStatusLabel(chain.match_status) }}
          </span>
          <span v-if="chain.mismatch_description" class="mismatch-desc">
            {{ chain.mismatch_description }}
          </span>
        </div>
      </div>
    </div>

    <!-- 生成进度 -->
    <div v-if="generating" class="generate-progress">
      <div class="progress-bar-wrap">
        <div class="progress-bar" :style="{ width: generateProgress + '%' }"></div>
      </div>
      <span>{{ generateProgress }}% — {{ generateStatus }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { evidenceChainApi } from '@/api'

const props = defineProps({ projectId: { type: String, required: true } })

const chainType = ref('all')
const loading = ref(false)
const generating = ref(false)
const generateProgress = ref(0)
const generateStatus = ref('')
const chains = ref([])

const riskStats = computed(() => {
  return {
    high: chains.value.filter(c => c.risk_level === 'high').length,
    medium: chains.value.filter(c => c.risk_level === 'medium').length,
    low: chains.value.filter(c => c.risk_level === 'low').length,
  }
})

async function loadChains() {
  loading.value = true
  try {
    const typeFilter = chainType.value !== 'all' ? `&chain_type=${chainType.value}` : ''
    const res = await evidenceChainApi.list(props.projectId, typeFilter)
    chains.value = res.data || []
  } finally {
    loading.value = false
  }
}

async function generateChain() {
  generating.value = true
  generateProgress.value = 0
  generateStatus.value = '分析财务数据...'
  try {
    await evidenceChainApi.generate(props.projectId, chainType.value === 'all' ? '' : chainType.value, (p, s) => {
      generateProgress.value = p
      generateStatus.value = s
    })
    await loadChains()
  } finally {
    generating.value = false
  }
}

function chainTypeLabel(t) {
  return { revenue: '收入', purchase: '采购', expense: '费用' }[t] || t
}
function riskLabel(r) {
  return { high: '🔴 高风险', medium: '🟡 中风险', low: '🟢 低风险' }[r] || r
}
function matchStatusLabel(m) {
  return { matched: '✅ 匹配', mismatched: '⚠️ 不匹配', missing: '❌ 缺失' }[m] || m
}

loadChains()
</script>

<style scoped>
.gt-evidence-chain-view { padding: 16px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.panel-header h3 { margin: 0; font-size: 16px; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.type-select { padding: 5px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 12px; }
.btn-primary { padding: 6px 14px; background: #4b2d77; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 12px; }

.risk-summary { display: flex; gap: 12px; margin-bottom: 16px; }
.risk-item { flex: 1; text-align: center; padding: 12px; border-radius: 8px; }
.risk-item.high { background: rgba(255,77,79,0.1); }
.risk-item.medium { background: rgba(255,173,0,0.1); }
.risk-item.low { background: rgba(82,196,26,0.1); }
.risk-count { display: block; font-size: 24px; font-weight: 700; }
.risk-item.high .risk-count { color: #ff4d4f; }
.risk-item.medium .risk-count { color: #faad14; }
.risk-item.low .risk-count { color: #52c41a; }
.risk-label { font-size: 12px; color: #666; }

.chain-list { display: flex; flex-direction: column; gap: 8px; max-height: 400px; overflow-y: auto; }
.chain-card { border: 1px solid #eee; border-radius: 8px; padding: 10px 12px; }
.chain-card.risk-high { border-color: rgba(255,77,79,0.3); background: rgba(255,77,79,0.03); }
.chain-card.risk-medium { border-color: rgba(255,173,0,0.3); background: rgba(255,173,0,0.03); }
.chain-card.risk-low { border-color: rgba(82,196,26,0.3); background: rgba(82,196,26,0.03); }

.chain-header { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.chain-type-badge { background: rgba(75,45,119,0.1); color: #4b2d77; padding: 2px 6px; border-radius: 4px; font-size: 11px; }
.chain-step { font-size: 12px; color: #666; }
.risk-badge { font-size: 11px; padding: 2px 6px; border-radius: 4px; }
.risk-badge.high { background: #fff2f0; color: #ff4d4f; }
.risk-badge.medium { background: #fff7e6; color: #fa8c16; }
.risk-badge.low { background: #f6ffed; color: #52c41a; }

.chain-doc-ids { font-size: 12px; color: #666; margin-bottom: 4px; }
.doc-label { color: #999; }
.doc-id { background: #f5f5f5; padding: 1px 4px; border-radius: 3px; font-size: 11px; }
.arrow { margin: 0 4px; color: #999; }

.chain-match { display: flex; align-items: center; gap: 8px; }
.match-status { font-size: 12px; padding: 2px 6px; border-radius: 4px; }
.match-status.matched { background: #f6ffed; color: #52c41a; }
.match-status.mismatched { background: #fff7e6; color: #fa8c16; }
.match-status.missing { background: #fff2f0; color: #ff4d4f; }
.mismatch-desc { font-size: 11px; color: #999; }

.generate-progress { margin-top: 12px; }
.progress-bar-wrap { height: 6px; background: #f0f0f0; border-radius: 3px; overflow: hidden; margin-bottom: 4px; }
.progress-bar { height: 100%; background: #4b2d77; transition: width 0.3s; }
.generate-progress span { font-size: 12px; color: #666; }
.loading, .empty-state { text-align: center; padding: 20px; color: #999; font-size: 13px; }
</style>
