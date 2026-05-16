<template>
  <div class="confirmation-ai">
    <div class="panel-header">
      <h3>📮 函证AI审核</h3>
      <div class="header-actions">
        <select v-model="checkType" class="check-select">
          <option value="">全部检查</option>
          <option value="address_verify">地址验证</option>
          <option value="reply_ocr">回函OCR识别</option>
          <option value="amount_compare">金额比对</option>
          <option value="seal_check">印章检查</option>
        </select>
        <button class="btn-primary" @click="runChecks" :disabled="running">
          {{ running ? '检查中...' : '🔍 AI检查' }}
        </button>
      </div>
    </div>

    <!-- 检查结果 -->
    <div class="check-results">
      <div v-if="results.length === 0 && !running" class="empty-state">
        选择函证记录，点击「AI检查」进行智能审核
      </div>
      <div
        v-for="r in results"
        :key="r.id"
        class="check-card"
        :class="`risk-${r.risk_level}`"
      >
        <div class="check-header">
          <span class="check-type-badge">{{ checkTypeLabel(r.check_type) }}</span>
          <span :class="['risk-badge', r.risk_level]">{{ riskLabel(r.risk_level) }}</span>
        </div>
        <div class="check-details">
          <div v-for="(val, key) in r.check_result" :key="key" class="detail-item">
            <span class="detail-key">{{ key }}：</span>
            <span class="detail-val">{{ val }}</span>
          </div>
        </div>
        <div class="check-footer">
          <span :class="['confirm-badge', r.human_confirmed ? 'confirmed' : 'pending']">
            {{ r.human_confirmed ? `✅ 已确认（${r.confirmed_by}）` : '⏳ 待人工确认' }}
          </span>
          <div class="footer-actions">
            <button v-if="!r.human_confirmed" class="btn-sm" @click="confirmCheck(r)">确认</button>
            <button v-if="!r.human_confirmed" class="btn-sm btn-reject" @click="rejectCheck(r)">质疑</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { confirmationAIApi } from '@/api'

const props = defineProps({
  projectId: { type: String, required: true },
  confirmationListId: { type: String, default: null }
})

const checkType = ref('')
const running = ref(false)
const results = ref([])

async function runChecks() {
  running.value = true
  try {
    const res = await confirmationAIApi.runChecks(
      props.confirmationListId,
      checkType.value ? [checkType.value] : ['address_verify', 'reply_ocr', 'amount_compare', 'seal_check']
    )
    results.value = res.data || []
  } finally {
    running.value = false
  }
}

async function confirmCheck(r) {
  await confirmationAIApi.confirm(r.id, { confirmed: true })
  r.human_confirmed = true
  r.confirmed_by = 'current_user'
}

async function rejectCheck(r) {
  await confirmationAIApi.confirm(r.id, { confirmed: false })
  r.human_confirmed = true
  r.confirmed_by = 'current_user'
  r.risk_level = 'high'
}

function checkTypeLabel(t) {
  return { address_verify: '地址验证', reply_ocr: '回函OCR', amount_compare: '金额比对', seal_check: '印章检查' }[t] || t
}
function riskLabel(r) {
  return { high: '🔴 高风险', medium: '🟡 中风险', low: '🟢 低风险', pass: '✅ 通过' }[r] || r
}
</script>

<style scoped>
.confirmation-ai { padding: 16px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.panel-header h3 { margin: 0; font-size: var(--gt-font-size-md); }
.header-actions { display: flex; gap: 8px; }
.check-select { padding: 5px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: var(--gt-font-size-xs); }
.btn-primary { padding: 6px 14px; background: var(--gt-color-primary); color: var(--gt-color-text-inverse); border: none; border-radius: 6px; cursor: pointer; font-size: var(--gt-font-size-xs); }
.btn-primary:disabled { background: var(--gt-color-border); cursor: not-allowed; }

.check-results { display: flex; flex-direction: column; gap: 8px; max-height: 500px; overflow-y: auto; }
.check-card { border: 1px solid #eee; border-radius: 8px; padding: 10px 12px; }
.check-card.risk-high { border-color: rgba(255,77,79,0.3); }
.check-card.risk-medium { border-color: rgba(255,173,0,0.3); }
.check-card.risk-low { border-color: rgba(82,196,26,0.3); }
.check-card.risk-pass { border-color: rgba(82,196,26,0.3); }

.check-header { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.check-type-badge { background: rgba(75,45,119,0.1); color: #4b2d77; padding: 2px 6px; border-radius: 4px; font-size: var(--gt-font-size-xs); }
.risk-badge { font-size: var(--gt-font-size-xs); padding: 2px 6px; border-radius: 4px; }
.risk-badge.high { background: var(--gt-bg-danger); color: var(--gt-color-coral); }
.risk-badge.medium { background: var(--gt-color-wheat-light); color: var(--gt-color-wheat); }
.risk-badge.low { background: var(--gt-bg-success); color: var(--gt-color-success); }
.risk-badge.pass { background: var(--gt-bg-success); color: var(--gt-color-success); }

.check-details { margin-bottom: 6px; }
.detail-item { display: flex; gap: 6px; font-size: var(--gt-font-size-xs); padding: 2px 0; }
.detail-key { color: var(--gt-color-text-secondary); min-width: 80px; }
.detail-val { color: var(--gt-color-text-primary); font-weight: 500; }

.check-footer { display: flex; justify-content: space-between; align-items: center; }
.confirm-badge { font-size: var(--gt-font-size-xs); padding: 2px 6px; border-radius: 4px; }
.confirm-badge.pending { background: var(--gt-color-wheat-light); color: var(--gt-color-wheat); }
.confirm-badge.confirmed { background: var(--gt-bg-success); color: var(--gt-color-success); }
.footer-actions { display: flex; gap: 4px; }
.btn-sm { padding: 2px 8px; border: 1px solid #ddd; background: var(--gt-color-bg-white); border-radius: 4px; cursor: pointer; font-size: var(--gt-font-size-xs); }
.btn-reject { border-color: #ff4d4f; color: var(--gt-color-coral); }
.empty-state { text-align: center; padding: 20px; color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-sm); }
</style>
