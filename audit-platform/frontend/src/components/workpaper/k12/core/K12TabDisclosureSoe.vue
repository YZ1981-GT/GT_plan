<template>
  <div class="k12-tab-disclosure-soe">
    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>按来源披露本期确认的营业外收入金额（国有企业版）。数据来源K12-1审定表，subscribe 'substantive:adjudicated' 事件自动刷新。国企版29行×5列，分类及格式与上市版略有差异，增加"国有资产处置收益"等国企特有项目。</p>
    </div>

    <!-- ═══ 主表：营业外收入按来源分类披露（国企） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">营业外收入披露明细（国有企业）</span>
          <div class="section-actions">
            <el-button size="small" type="primary" link @click="applyAutoFill">
              <el-icon><Refresh /></el-icon>从审定表取数
            </el-button>
            <el-button size="small" type="primary" link @click="generateAI('disclosure-soe')">
              <el-icon><MagicStick /></el-icon>AI辅助
            </el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="disclosureRows"
        border
        size="small"
        show-summary
        :summary-method="summaryMethod"
        class="disclosure-table"
      >
        <el-table-column prop="category" label="项目（来源分类）" min-width="160" />
        <el-table-column prop="currentAmount" label="本期发生额" min-width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'amount-zero': !row.currentAmount }">{{ fmtAmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priorAmount" label="上期发生额" min-width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="同比变动" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'abnormal-rate': isAbnormal(row) }">{{ formatRate(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="说明" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="披露说明"
              @change="handleRowChange(row)"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 审计说明（AI辅助文本区域） ═══ -->
    <el-card shadow="never" class="narrative-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">附注披露说明</span>
          <el-button size="small" type="primary" link @click="generateAI('narrative')">
            <el-icon><MagicStick /></el-icon>AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="narrativeText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="输入营业外收入附注披露说明（国企格式）..."
        @change="handleNarrativeSave"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-tips">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从K12-1审定表自动拉取（按来源分类行）</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>国企需额外关注国有资产处置收益等特有项目</li>
        <li>营业外收入各来源占比超过50%时标注重大项目</li>
        <li>与日常活动无关的利得才纳入营业外收入（非其他收益6117）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K12TabDisclosureSoe.vue — K12 附注披露信息（国有企业）
 *
 * 29行5列，按来源披露+自动取数+AI辅助
 * Spec: .kiro/specs/k12-non-operating-income/ Task 6.1
 * Requirements: 6.1
 *
 * 功能：
 * - 按来源分类披露营业外收入信息（国有企业版）
 * - 自动从K12-1审定表取数（subscribe EventBus 'substantive:adjudicated'）
 * - AI辅助文本生成按钮（每个section标题行右侧放AI按钮）
 * - el-card包裹
 * - 编制提示details折叠底部
 *
 * EventBus:
 * - subscribe: 'substantive:adjudicated' (filter accountCode=6301)
 * - publish: 'disclosure:note-text-updated' (noteId='non_operating_income')
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'

// ─── Props & Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

// ─── Constants ───────────────────────────────────────────────────────────────

const ACCOUNT_CODE = '6301'
const ABNORMAL_THRESHOLD = 0.5

/** 营业外收入标准来源分类（国企版，含国企特有项目） */
const CATEGORIES = [
  '政府补助',
  '债务重组利得',
  '资产盘盈利得',
  '罚款收入',
  '捐赠利得',
  '无法支付款项转入',
  '国有资产处置收益',
  '其他',
]

// ─── Types ───────────────────────────────────────────────────────────────────

interface DisclosureRow {
  category: string
  currentAmount: number
  priorAmount: number
  remark: string
}

// ─── State ───────────────────────────────────────────────────────────────────

const disclosureRows = ref<DisclosureRow[]>(
  CATEGORIES.map(c => ({ category: c, currentAmount: 0, priorAmount: 0, remark: '' }))
)
const narrativeText = ref('')
const totalAdjudicated = ref(0)

// ─── Load saved data from allResponses ───────────────────────────────────────

function loadSavedData(): void {
  for (let i = 0; i < CATEGORIES.length; i++) {
    const key = `K12-disc-soe-row-${i}`
    const saved = props.allResponses.get(key)
    if (saved) {
      try {
        const parsed = typeof saved.remark === 'string' ? JSON.parse(saved.remark) : saved.remark
        if (parsed) {
          disclosureRows.value[i] = {
            category: CATEGORIES[i],
            currentAmount: Number(parsed.currentAmount || 0),
            priorAmount: Number(parsed.priorAmount || 0),
            remark: parsed.remark || '',
          }
        }
      } catch { /* ignore parse errors */ }
    }
  }

  const narrativeSaved = props.allResponses.get('K12-disclosure-soe-narrative')
  if (narrativeSaved) {
    narrativeText.value = narrativeSaved.remark || narrativeSaved.conclusion || ''
  }
}

// ─── Auto-fill from K12-1 adjudicated data ───────────────────────────────────

function applyAutoFill(): void {
  for (let i = 0; i < CATEGORIES.length; i++) {
    const adjKey = `K12-1-row-${i}-audited`
    const adjSaved = props.allResponses.get(adjKey)
    if (adjSaved) {
      const val = Number(adjSaved.remark ?? adjSaved.conclusion ?? 0)
      if (val !== 0) {
        disclosureRows.value[i].currentAmount = val
      }
    }
  }

  const totalKey = 'K12-1-adjudicated-amount'
  const totalSaved = props.allResponses.get(totalKey)
  if (totalSaved) {
    totalAdjudicated.value = Number(totalSaved.remark ?? totalSaved.conclusion ?? 0)
  }
}

// ─── EventBus: subscribe 'substantive:adjudicated' ───────────────────────────

function handleAdjudicated(payload: any): void {
  if (!payload) return
  if (payload.accountCode === ACCOUNT_CODE || payload.wpCode === 'K12') {
    if (payload.auditedAmount != null) {
      totalAdjudicated.value = Number(payload.auditedAmount)
    }
    applyAutoFill()
  }
}

// ─── Save handlers ───────────────────────────────────────────────────────────

function handleRowChange(row: DisclosureRow): void {
  const idx = disclosureRows.value.indexOf(row)
  if (idx >= 0) {
    emit('save', `K12-disc-soe-row-${idx}`, {
      currentAmount: row.currentAmount,
      priorAmount: row.priorAmount,
      remark: row.remark,
    })
  }
}

function handleNarrativeSave(): void {
  emit('save', 'K12-disclosure-soe-narrative', { remark: narrativeText.value })
  eventBus.emit('disclosure:note-text-updated' as any, {
    noteId: 'non_operating_income',
    wpCode: 'K12',
    variant: 'soe',
    text: narrativeText.value,
  })
}

// ─── AI generation ───────────────────────────────────────────────────────────

async function generateAI(section: string): Promise<void> {
  if (!props.wpId) return
  try {
    const res = await api.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section,
      prompt: `为K12营业外收入底稿生成国有企业附注披露文本。来源分类：${CATEGORIES.join('/')}。审定发生额：${totalAdjudicated.value}。`,
      context: JSON.stringify(disclosureRows.value),
    })
    const content = res?.data?.content || res?.content || ''
    if (content && section === 'narrative') {
      narrativeText.value = content
      handleNarrativeSave()
    }
    ElMessage.success('AI生成完成')
  } catch {
    ElMessage.warning('AI生成失败，请手动填写')
  }
}

// ─── Table helpers ───────────────────────────────────────────────────────────

const totalCurrentAmount = computed(() =>
  disclosureRows.value.reduce((s, r) => s + (r.currentAmount || 0), 0)
)

function summaryMethod({ columns }: { columns: any[]; data: DisclosureRow[] }): string[] {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    if (col.property === 'currentAmount') return fmtAmt(totalCurrentAmount.value)
    if (col.property === 'priorAmount') {
      return fmtAmt(disclosureRows.value.reduce((s, r) => s + (r.priorAmount || 0), 0))
    }
    return ''
  })
}

function isAbnormal(row: DisclosureRow): boolean {
  if (!row.priorAmount || row.priorAmount === 0) return false
  const rate = Math.abs((row.currentAmount - row.priorAmount) / row.priorAmount)
  return rate > ABNORMAL_THRESHOLD
}

function formatRate(row: DisclosureRow): string {
  if (!row.priorAmount || row.priorAmount === 0) return '—'
  const rate = (row.currentAmount - row.priorAmount) / row.priorAmount
  return (rate * 100).toFixed(1) + '%'
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadSavedData()
  applyAutoFill()
  eventBus.on('substantive:adjudicated' as any, handleAdjudicated)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, handleAdjudicated)
})
</script>

<style scoped>
.k12-tab-disclosure-soe {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  color: #6b5900;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title {
  font-weight: 600;
  font-size: 14px;
}

.section-actions {
  display: flex;
  gap: 8px;
}

.disclosure-card,
.narrative-card {
  margin: 0;
}

.disclosure-table {
  font-size: var(--wp-font-size, 13px);
}

.amount-zero {
  color: var(--el-text-color-placeholder);
}

.abnormal-rate {
  color: var(--el-color-danger);
  font-weight: 600;
}

.compile-tips {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.compile-tips summary {
  cursor: pointer;
  font-weight: 500;
}

.compile-tips ul {
  margin: 8px 0 0;
  padding-left: 20px;
}
</style>
