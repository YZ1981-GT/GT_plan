<template>
  <div class="k13-tab-disclosure-soe">
    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>按去向披露本期确认的营业外支出金额（国有企业版）。数据来源K13-1审定表，subscribe 'substantive:adjudicated' + 'adjustment:created' 事件自动刷新。国企版18行×5列，简化格式侧重分类汇总。</p>
    </div>

    <!-- ═══ 跨底稿引用（GtIndexChip） ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="K13-1" :context-project-id="props.projectId" />
      <GtIndexChip value="K13-2" :context-project-id="props.projectId" />
      <GtIndexChip value="A13" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ 主表：营业外支出按去向分类披露（国企） ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">营业外支出披露明细（国有企业）</span>
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
        <el-table-column prop="category" label="项目（去向分类）" min-width="180" />
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
        <el-table-column prop="nonRecurring" label="计入当期非经常性损益的金额" min-width="180" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.nonRecurring"
              :controls="false"
              :precision="2"
              size="small"
              placeholder="0.00"
              @change="handleRowChange(row)"
            />
            <span v-else>{{ fmtAmt(row.nonRecurring) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="说明" min-width="160">
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
        placeholder="输入营业外支出附注披露说明（国企格式）..."
        @change="handleNarrativeSave"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-tips">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从K13-1审定表自动拉取（按去向分类行）</li>
        <li>订阅 'substantive:adjudicated' + 'adjustment:created' 事件自动刷新</li>
        <li>国企需额外关注国有资产处置损失等特有项目</li>
        <li>营业外支出中罚款/捐赠为典型非经常性损益项目</li>
        <li>与日常活动无关的损失才纳入营业外支出</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K13TabDisclosureSoe.vue — K13 附注披露信息（国有企业）
 *
 * 18行×5列，按去向披露+自动取数+AI辅助
 * Spec: .kiro/specs/k13-non-operating-expense/ Task 4.6
 * Requirements: 6.1
 *
 * 功能：
 * - 按去向分类披露营业外支出信息（国有企业版）
 * - 自动从K13-1审定表取数（subscribe EventBus 'substantive:adjudicated'）
 * - AI辅助文本生成按钮（每个section标题行右侧放AI按钮）
 * - GtIndexChip跨底稿引用：K13-1 / K13-2 / A13
 * - el-card包裹
 * - 编制提示details折叠底部
 *
 * EventBus:
 * - subscribe: 'substantive:adjudicated' (filter accountCode=6711 or wpCode='K13')
 * - subscribe: 'adjustment:created' (filter wpCode='K13') — 调整分录变化时刷新
 * - publish: 'disclosure:note-text-updated' (noteId='non_operating_expense')
 */
import { ref, computed, onMounted, onUnmounted, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

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

const ACCOUNT_CODE = '6711'
const ABNORMAL_THRESHOLD = 0.5

/** 营业外支出标准去向分类（国企版，精简分类） */
const CATEGORIES = [
  '非流动资产处置损失',
  '捐赠支出',
  '债务重组损失',
  '罚款滞纳金支出',
  '资产盘亏损失',
  '国有资产处置损失',
  '非常损失',
  '其他',
]

// ─── Types ───────────────────────────────────────────────────────────────────

interface DisclosureRow {
  category: string
  currentAmount: number
  priorAmount: number
  nonRecurring: number
  remark: string
}

// ─── State ───────────────────────────────────────────────────────────────────

const disclosureRows = ref<DisclosureRow[]>(
  CATEGORIES.map(c => ({ category: c, currentAmount: 0, priorAmount: 0, nonRecurring: 0, remark: '' }))
)
const narrativeText = ref('')
const totalAdjudicated = ref(0)

// ─── Load saved data from allResponses ───────────────────────────────────────

function loadSavedData(): void {
  for (let i = 0; i < CATEGORIES.length; i++) {
    const key = `K13-disc-soe-row-${i}`
    const saved = props.allResponses.get(key)
    if (saved) {
      try {
        const parsed = typeof saved.remark === 'string' ? JSON.parse(saved.remark) : saved.remark
        if (parsed) {
          disclosureRows.value[i] = {
            category: CATEGORIES[i],
            currentAmount: Number(parsed.currentAmount || 0),
            priorAmount: Number(parsed.priorAmount || 0),
            nonRecurring: Number(parsed.nonRecurring || 0),
            remark: parsed.remark || '',
          }
        }
      } catch { /* ignore parse errors */ }
    }
  }

  const narrativeSaved = props.allResponses.get('K13-disclosure-soe-narrative')
  if (narrativeSaved) {
    narrativeText.value = narrativeSaved.remark || narrativeSaved.conclusion || ''
  }
}

// ─── Auto-fill from K13-1 adjudicated data ───────────────────────────────────

function applyAutoFill(): void {
  for (let i = 0; i < CATEGORIES.length; i++) {
    const adjKey = `K13-1-row-${i}-audited`
    const adjSaved = props.allResponses.get(adjKey)
    if (adjSaved) {
      const val = Number(adjSaved.remark ?? adjSaved.conclusion ?? 0)
      if (val !== 0) {
        disclosureRows.value[i].currentAmount = val
      }
    }
  }

  const totalKey = 'K13-1-adjudicated-amount'
  const totalSaved = props.allResponses.get(totalKey)
  if (totalSaved) {
    totalAdjudicated.value = Number(totalSaved.remark ?? totalSaved.conclusion ?? 0)
  }
}

// ─── EventBus: subscribe 'substantive:adjudicated' + 'adjustment:created' ────

function handleAdjudicated(payload: any): void {
  if (!payload) return
  if (payload.accountCode === ACCOUNT_CODE || payload.wpCode === 'K13') {
    if (payload.auditedAmount != null) {
      totalAdjudicated.value = Number(payload.auditedAmount)
    }
    applyAutoFill()
  }
}

function handleAdjustmentCreated(payload: any): void {
  if (!payload) return
  // 调整分录变化时刷新附注数据（K13-3 → A13 + 附注刷新）
  if (payload.wpCode === 'K13') {
    applyAutoFill()
  }
}

// ─── Save handlers ───────────────────────────────────────────────────────────

function handleRowChange(row: DisclosureRow): void {
  const idx = disclosureRows.value.indexOf(row)
  if (idx >= 0) {
    emit('save', `K13-disc-soe-row-${idx}`, JSON.stringify({
      currentAmount: row.currentAmount,
      priorAmount: row.priorAmount,
      nonRecurring: row.nonRecurring,
      remark: row.remark,
    }))
  }
}

function handleNarrativeSave(): void {
  emit('save', 'K13-disclosure-soe-narrative', { remark: narrativeText.value })
  eventBus.emit('disclosure:note-text-updated' as any, {
    noteId: 'non_operating_expense',
    wpCode: 'K13',
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
      prompt: `为K13营业外支出底稿生成国有企业附注披露文本。去向分类：${CATEGORIES.join('/')}。审定发生额合计：${totalAdjudicated.value}。`,
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
    if (col.property === 'nonRecurring') {
      return fmtAmt(disclosureRows.value.reduce((s, r) => s + (r.nonRecurring || 0), 0))
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
  eventBus.on('adjustment:created' as any, handleAdjustmentCreated)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, handleAdjudicated)
  eventBus.off('adjustment:created' as any, handleAdjustmentCreated)
})
</script>

<style scoped>
.k13-tab-disclosure-soe {
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

.cross-ref-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
}

.cross-refs-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
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
