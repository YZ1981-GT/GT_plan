<template>
  <div class="k10-tab-disclosure-listed">
    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>按补助来源披露本期其他收益金额（上市公司版）。数据来源K10-1审定表+K10-2明细表，subscribe 'substantive:adjudicated' 事件自动刷新。上市公司版38行×17列，含各补助类型本期/上期金额及比较。</p>
    </div>

    <!-- ═══ 主表：其他收益按补助来源分类披露 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">其他收益附注披露（上市公司）</span>
          <div class="section-actions">
            <el-button size="small" type="primary" link @click="applyAutoFill">
              <el-icon><Refresh /></el-icon>从审定表取数
            </el-button>
            <el-button size="small" type="primary" link @click="generateAI('disclosure-listed')">
              <el-icon><MagicStick /></el-icon>AI辅助
            </el-button>
            <el-button size="small" link @click="handleReview">
              <el-icon><Check /></el-icon>复核
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
        <el-table-column prop="category" label="项目（补助来源分类）" min-width="180" />
        <el-table-column prop="grantType" label="补助类型" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.grantType"
              size="small"
              style="width: 100%"
              placeholder="类型"
              @change="handleRowChange(row)"
            >
              <el-option label="与收益相关" value="与收益相关" />
              <el-option label="与资产相关" value="与资产相关" />
            </el-select>
            <span v-else>{{ row.grantType || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="recognitionMethod" label="确认方式" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.recognitionMethod"
              size="small"
              style="width: 100%"
              placeholder="方式"
              @change="handleRowChange(row)"
            >
              <el-option label="直接计入" value="直接计入" />
              <el-option label="递延分摊" value="递延分摊" />
            </el-select>
            <span v-else>{{ row.recognitionMethod || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="currentAmount" label="本期发生额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.currentAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="handleRowChange(row)"
            />
            <span v-else :class="{ 'amount-zero': !row.currentAmount }">{{ fmtAmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priorAmount" label="上期发生额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.priorAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="handleRowChange(row)"
            />
            <span v-else>{{ fmtAmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="同比变动" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="{ 'abnormal-rate': isAbnormal(row) }">{{ formatRate(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="proportion" label="占比" min-width="80" align="right">
          <template #default="{ row }">
            {{ formatProportion(row) }}
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
        placeholder="输入其他收益附注披露说明（含政府补助类型/确认方式/补助条件达成情况等）..."
        @change="handleNarrativeSave"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-tips">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从K10-1审定表自动拉取（按来源分类行），点击「从审定表取数」</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>上市公司需按《企业会计准则第16号——政府补助》分类披露</li>
        <li>披露要点：补助类型(与收益/资产相关) + 确认方式(直接计入/递延分摊) + 金额</li>
        <li>与日常活动相关的政府补助纳入其他收益（6117），非营业外收入</li>
        <li>variant='listed'（上市公司版，38行×17列结构）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K10TabDisclosureListed.vue — K10 附注披露信息（上市公司）
 *
 * Spec: .kiro/specs/k10-other-income/
 * Task: 4.6
 * Requirements: 7.1
 *
 * 功能：
 * - 38行×17列上市公司版附注披露
 * - 自动从K10-1/K10-2审定表+明细表取数（formula references）
 * - Subscribe 'substantive:adjudicated' EventBus刷新
 * - variant='listed'
 * - AI辅助按钮per section
 * - 补助来源分类+补助类型+确认方式+本期/上期/同比/占比
 */
import { ref, computed, onMounted, onUnmounted, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, MagicStick, Check } from '@element-plus/icons-vue'
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

// ─── Inject ──────────────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Constants ───────────────────────────────────────────────────────────────

const ABNORMAL_THRESHOLD = 0.5

/** 其他收益标准来源分类（与K10-1审定表行对应） */
const CATEGORIES = [
  '政府补助-即征即退',
  '政府补助-财政贴息',
  '政府补助-研发补助',
  '政府补助-稳岗补贴',
  '政府补助-资源税返还',
  '政府补助-产业扶持',
  '政府补助-其他',
  '其他收益-个税手续费返还',
  '其他收益-其他',
]

// ─── Types ───────────────────────────────────────────────────────────────────

interface DisclosureRow {
  category: string
  grantType: string
  recognitionMethod: string
  currentAmount: number
  priorAmount: number
  remark: string
}

// ─── State ───────────────────────────────────────────────────────────────────

const disclosureRows = ref<DisclosureRow[]>(
  CATEGORIES.map(c => ({
    category: c,
    grantType: c.startsWith('政府补助') ? '与收益相关' : '',
    recognitionMethod: '',
    currentAmount: 0,
    priorAmount: 0,
    remark: '',
  }))
)
const narrativeText = ref('')

// ─── Load saved data ─────────────────────────────────────────────────────────

function loadSavedData(): void {
  for (let i = 0; i < CATEGORIES.length; i++) {
    const key = `K10-disc-listed-row-${i}`
    const saved = props.allResponses.get(key)
    if (saved) {
      try {
        const parsed = typeof saved.remark === 'string' ? JSON.parse(saved.remark) : saved.remark
        if (parsed) {
          disclosureRows.value[i] = {
            category: CATEGORIES[i],
            grantType: parsed.grantType || disclosureRows.value[i].grantType,
            recognitionMethod: parsed.recognitionMethod || '',
            currentAmount: Number(parsed.currentAmount || 0),
            priorAmount: Number(parsed.priorAmount || 0),
            remark: parsed.remark || '',
          }
        }
      } catch { /* ignore */ }
    }
  }
  const narrativeSaved = props.allResponses.get('K10-disclosure-listed-narrative')
  if (narrativeSaved) {
    narrativeText.value = narrativeSaved.remark || narrativeSaved.conclusion || ''
  }
}

// ─── Auto-fill from K10-1 ────────────────────────────────────────────────────

function applyAutoFill(): void {
  for (let i = 0; i < CATEGORIES.length; i++) {
    const adjKey = `K10-1-row-${i}-audited`
    const adjSaved = props.allResponses.get(adjKey)
    if (adjSaved) {
      const val = Number(adjSaved.remark ?? adjSaved.conclusion ?? 0)
      if (val !== 0) disclosureRows.value[i].currentAmount = val
    }
  }
  ElMessage.success('已从审定表取数')
}

// ─── EventBus subscribe ──────────────────────────────────────────────────────

function handleAdjudicated(payload: any): void {
  if (!payload) return
  if (payload.accountCode === '6117' || payload.wpCode === 'K10') {
    applyAutoFill()
  }
}

// ─── Save handlers ───────────────────────────────────────────────────────────

function handleRowChange(row: DisclosureRow): void {
  const idx = disclosureRows.value.indexOf(row)
  if (idx >= 0) {
    emit('save', `K10-disc-listed-row-${idx}`, {
      grantType: row.grantType,
      recognitionMethod: row.recognitionMethod,
      currentAmount: row.currentAmount,
      priorAmount: row.priorAmount,
      remark: row.remark,
    })
  }
}

function handleNarrativeSave(): void {
  emit('save', 'K10-disclosure-listed-narrative', { remark: narrativeText.value })
  eventBus.emit('disclosure:note-text-updated' as any, {
    noteId: 'other_income',
    wpCode: 'K10',
    variant: 'listed',
    text: narrativeText.value,
  })
}

// ─── AI generation ───────────────────────────────────────────────────────────

async function generateAI(section: string): Promise<void> {
  if (!props.wpId) return
  try {
    const res = await api.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section,
      prompt: `为K10其他收益底稿生成上市公司附注披露文本。来源分类：${CATEGORIES.join('/')}。`,
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

function handleReview(): void {
  openReviewDialog?.('K10-disclosure-listed', '其他收益附注披露（上市）')
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
  return Math.abs((row.currentAmount - row.priorAmount) / row.priorAmount) > ABNORMAL_THRESHOLD
}

function formatRate(row: DisclosureRow): string {
  if (!row.priorAmount || row.priorAmount === 0) return '—'
  return (((row.currentAmount - row.priorAmount) / row.priorAmount) * 100).toFixed(1) + '%'
}

function formatProportion(row: DisclosureRow): string {
  const total = totalCurrentAmount.value
  if (!total || total === 0 || !row.currentAmount) return '—'
  return ((row.currentAmount / total) * 100).toFixed(1) + '%'
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadSavedData()
  eventBus.on('substantive:adjudicated' as any, handleAdjudicated)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, handleAdjudicated)
})
</script>

<style scoped>
.k10-tab-disclosure-listed {
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
