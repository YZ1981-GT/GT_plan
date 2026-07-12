<template>
  <div class="k8-disclosure-soe">
    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>附注披露信息（国企）</h3>
      <div class="header-actions">
        <el-button size="small" type="primary" plain @click="handleAiGenerate"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        <el-button size="small" @click="openReviewDialog?.('K8-disclosure-soe')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>国企附注按费用性质简化披露（30行×5列）：项目/本期发生额/上期发生额/变动额/变动率。数据来自K8-1审定表，subscribe 'substantive:adjudicated' 事件自动刷新。</p>
    </div>

    <!-- ═══ 自动取数提示 ═══ -->
    <el-alert v-if="hasAutoData" type="success" :closable="true" style="margin-bottom:10px" show-icon>
      <template #title>已从K8-1审定表自动取数填充附注数据</template>
    </el-alert>

    <!-- ═══ 费用披露表格 ═══ -->
    <el-table :data="disclosureRows" border size="small" style="width:100%" max-height="460" show-summary :summary-method="summaryMethod">
      <el-table-column prop="project" label="项目" min-width="140" />
      <el-table-column prop="currentAmount" label="本期发生额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.currentAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateField(row.id, 'currentAmount', v ?? 0)" />
          <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.currentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="priorAmount" label="上期发生额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.priorAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateField(row.id, 'priorAmount', v ?? 0)" />
          <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.priorAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动额" width="130" align="right">
        <template #default="{ row }">
          <span class="formula-cell" :title="`变动 = 本期 - 上期`">{{ fmtAmt(row.currentAmount - row.priorAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动率" width="100" align="right">
        <template #default="{ row }">
          <span :class="{ 'abnormal-cell': isAbnormal(row) }">{{ formatRate(row) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 附注说明文本 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-head">
          <span class="card-title">附注说明</span>
          <el-button size="small" type="primary" plain @click="handleAiNarrative"><el-icon><MagicStick /></el-icon> AI生成</el-button>
        </div>
      </template>
      <el-input v-model="narrativeText" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" :disabled="isReadonly" placeholder="附注说明文本（可AI辅助生成）" @blur="handleNarrativeSave" />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>国企附注按费用性质简化披露</li>
        <li>表格规格：30行×5列（项目/本期/上期/变动额/变动率）</li>
        <li>变动额/变动率为公式列</li>
        <li>数据来源：K8-1审定表，subscribe EventBus自动刷新</li>
        <li>异常波动（|变动率|>30%）红色标记</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K8TabDisclosureSoe.vue — 附注披露信息（国企）30行×5列
 *
 * Spec: .kiro/specs/k8-selling-expenses/ | Task: 4.6, 6.2
 * Requirements: 8.1, 8.2
 *
 * 功能：
 * - 国企按费用性质简化披露
 * - 本期/上期/变动额/变动率（公式列）
 * - 自动从K8-1取数 + subscribe EventBus刷新
 * - subscribe EventBus 'adjustment:created' (accountCode=6601) 刷新
 * - AI辅助
 */
import { ref, onMounted, onUnmounted, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import type { Ref } from 'vue'

const K8_ACCOUNT_CODE = '6601'
const ABNORMAL_THRESHOLD = 0.3

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ (e: 'save', itemId: string, value: any): void }>()
const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

// ─── 数据模型 ────────────────────────────────────────────────────────────────

interface DisclosureRow {
  id: string
  project: string
  currentAmount: number
  priorAmount: number
  isTotal?: boolean
}

const disclosureRows = ref<DisclosureRow[]>([])
const narrativeText = ref('')
const hasAutoData = ref(false)

// ─── 默认行（国企简化版） ────────────────────────────────────────────────────

const DEFAULT_SOE_PROJECTS = [
  '职工薪酬', '差旅费', '业务招待费', '广告宣传费', '运输费',
  '折旧费', '摊销费', '办公费', '通讯费', '物料消耗',
  '租赁费', '保险费', '修理费', '包装费', '佣金及手续费',
  '售后服务费', '水电费', '仓储费', '其他',
]

function initDefaultRows(): void {
  disclosureRows.value = DEFAULT_SOE_PROJECTS.map((name, idx) => ({
    id: `soe-${idx}`,
    project: name,
    currentAmount: 0,
    priorAmount: 0,
  }))
}

// ─── 加载已保存数据 ──────────────────────────────────────────────────────────

function loadSavedData(): void {
  const saved = props.allResponses.get('K8-disclosure-soe-rows')
  if (saved?.remark) {
    try { disclosureRows.value = JSON.parse(saved.remark) } catch { initDefaultRows() }
  } else {
    initDefaultRows()
  }
  const savedNarrative = props.allResponses.get('K8-disclosure-soe-narrative')
  if (savedNarrative?.remark) { narrativeText.value = savedNarrative.remark }
}

// ─── 自动取数 ────────────────────────────────────────────────────────────────

function applyAutoFill(): void {
  const adjData = props.allResponses.get('K8-1-audited-by-item')
  if (adjData?.remark) {
    hasAutoData.value = true
    try {
      const data = JSON.parse(adjData.remark)
      if (data && typeof data === 'object') {
        for (const row of disclosureRows.value) {
          const src = data[row.project]
          if (src) {
            row.currentAmount = Number(src.currentAmount ?? src.audited ?? 0)
            row.priorAmount = Number(src.priorAmount ?? src.prior ?? 0)
          }
        }
      }
    } catch { /* silent */ }
  }
}

// ─── 字段更新 + 持久化 ──────────────────────────────────────────────────────

function updateField(id: string, field: string, value: any): void {
  const row = disclosureRows.value.find(r => r.id === id)
  if (row) { ;(row as any)[field] = value; persistRows() }
}

function persistRows(): void {
  emit('save', 'K8-disclosure-soe-rows', { remark: JSON.stringify(disclosureRows.value) })
}

function handleNarrativeSave(): void {
  emit('save', 'K8-disclosure-soe-narrative', { remark: narrativeText.value })
  eventBus.emit('disclosure:note-text-updated' as any, { wpCode: 'K8', variant: 'soe', text: narrativeText.value })
}

// ─── 合计汇总 ────────────────────────────────────────────────────────────────

function summaryMethod({ columns, data }: { columns: any[]; data: DisclosureRow[] }): string[] {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (prop === 'currentAmount') return fmtAmt(data.reduce((s, r) => s + (r.currentAmount || 0), 0))
    if (prop === 'priorAmount') return fmtAmt(data.reduce((s, r) => s + (r.priorAmount || 0), 0))
    if (idx === 3) {
      const totalCur = data.reduce((s, r) => s + (r.currentAmount || 0), 0)
      const totalPri = data.reduce((s, r) => s + (r.priorAmount || 0), 0)
      return fmtAmt(totalCur - totalPri)
    }
    return ''
  })
}

// ─── EventBus ────────────────────────────────────────────────────────────────

function handleAdjudicated(payload: any): void {
  if (!payload || payload.accountCode === K8_ACCOUNT_CODE || payload.wpCode === 'K8') {
    applyAutoFill()
  }
}

function handleAdjustmentCreated(payload: any): void {
  // 过滤 accountCode=6601 的调整分录事件，触发数据刷新
  if (payload && payload.accountCode === K8_ACCOUNT_CODE) {
    applyAutoFill()
  }
}

onMounted(() => {
  loadSavedData()
  applyAutoFill()
  eventBus.on('substantive:adjudicated', handleAdjudicated)
  eventBus.on('adjustment:created', handleAdjustmentCreated)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', handleAdjudicated)
  eventBus.off('adjustment:created', handleAdjustmentCreated)
})

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function isAbnormal(row: DisclosureRow): boolean {
  if (!row.priorAmount || row.priorAmount === 0) return false
  return Math.abs((row.currentAmount - row.priorAmount) / row.priorAmount) > ABNORMAL_THRESHOLD
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

function handleAiGenerate(): void { ElMessage.info('AI辅助生成附注披露...') }
function handleAiNarrative(): void { ElMessage.info('AI生成附注说明文本...') }
</script>

<style scoped>
.k8-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.disclosure-card { margin-top: 14px; }
.disclosure-card :deep(.el-card__header) { padding: 10px 16px; }
.card-head { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.formula-cell { text-decoration: underline dashed; cursor: help; color: #409eff; }
.abnormal-cell { color: #f56c6c; font-weight: 600; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table__footer-wrapper td) { font-weight: 600; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; }
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
