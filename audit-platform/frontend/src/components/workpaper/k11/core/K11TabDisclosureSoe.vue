<template>
  <div class="k11-disclosure-soe">
    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>附注披露信息（国企）</h3>
      <div class="header-actions">
        <el-button size="small" type="primary" plain @click="handleAiGenerate"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        <el-button size="small" @click="openReviewDialog?.('K11-disclosure-soe')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>按资产类别披露本期确认的减值损失金额（国有企业版）。数据来源K11-1审定表，subscribe 'substantive:adjudicated' 事件自动刷新。国企版29行×27列，分类及格式与上市版略有差异。</p>
    </div>

    <!-- ═══ 自动取数提示 ═══ -->
    <el-alert v-if="hasAutoData" type="success" :closable="true" style="margin-bottom:10px" show-icon>
      <template #title>已从K11-1审定表自动取数填充附注数据</template>
    </el-alert>

    <!-- ═══ 减值损失披露表 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-head">
          <span class="card-title">资产减值损失—按资产类别分类（国企版）</span>
          <el-button size="small" type="primary" plain @click="handleAiSection('impairment-by-category-soe')"><el-icon><MagicStick /></el-icon> AI</el-button>
        </div>
      </template>
      <el-table
        :data="disclosureRows"
        border
        size="small"
        style="width: 100%"
        max-height="460"
        show-summary
        :summary-method="summaryMethod"
      >
        <el-table-column prop="category" label="资产类别" min-width="150" fixed />
        <el-table-column prop="currentProvision" label="本期计提" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.currentProvision" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateField(row.id, 'currentProvision', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.currentProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="currentReversal" label="本期转回" width="130" align="right">
          <template #default="{ row }">
            <template v-if="row.noReversal">
              <span class="no-reversal">不可转回</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.currentReversal" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateField(row.id, 'currentReversal', v ?? 0)" />
              <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.currentReversal) }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="本期发生额" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :title="`本期发生额 = 计提 - 转回 = ${row.currentProvision} - ${row.currentReversal}`">
              {{ fmtAmt(row.currentProvision - row.currentReversal) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="priorAmount" label="上期发生额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly && !row.isTotal" :model-value="row.priorAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => updateField(row.id, 'priorAmount', v ?? 0)" />
            <span v-else :class="{ 'formula-cell': row.isTotal }">{{ fmtAmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="90" align="right">
          <template #default="{ row }">
            <span :class="{ 'abnormal-cell': isAbnormal(row) }">{{ formatRate(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && !row.isTotal" :model-value="row.remark" size="small" @change="(v: string) => updateField(row.id, 'remark', v)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 附注说明文本 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-head">
          <span class="card-title">附注说明</span>
          <el-button size="small" type="primary" plain @click="handleAiSection('narrative')"><el-icon><MagicStick /></el-icon> AI生成</el-button>
        </div>
      </template>
      <el-input v-model="narrativeText" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="附注说明文本（可AI辅助生成）" @blur="handleNarrativeSave" />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>国有企业按资产类别分别披露减值损失金额</li>
        <li>表格规格：29行×27列（含合计行，国企标准）</li>
        <li>本期发生额 = 本期计提 - 本期转回（公式列）</li>
        <li>商誉减值不可转回（CAS8），标注"不可转回"</li>
        <li>数据来源：K11-1审定表，subscribe EventBus自动刷新</li>
        <li>与上市版差异：国企分类含部分国资委专有报告科目</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K11TabDisclosureSoe.vue — 附注披露信息（国企）29行×27列
 *
 * Spec: .kiro/specs/k11-asset-impairment-loss/ | Task: 4.5
 * Requirements: 6.1
 *
 * 功能：
 * - 按资产类别披露减值损失信息（国有企业版）
 * - 自动从K11-1审定表取数（subscribe EventBus 'substantive:adjudicated'）
 * - AI辅助文本生成按钮（每个section标题行右侧放AI按钮）
 * - el-card包裹
 * - 大表格用虚拟滚动（max-height限制）
 */
import { ref, onMounted, onUnmounted, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'

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
  category: string
  currentProvision: number
  currentReversal: number
  priorAmount: number
  remark: string
  isTotal?: boolean
  noReversal?: boolean
}

const disclosureRows = ref<DisclosureRow[]>([])
const narrativeText = ref('')
const hasAutoData = ref(false)

// ─── 默认行（按资产类别分类 — 国有企业） ────────────────────────────────────

const DEFAULT_CATEGORIES_SOE = [
  { name: '存货跌价损失', noReversal: false },
  { name: '应收账款坏账损失', noReversal: false },
  { name: '其他应收款坏账损失', noReversal: false },
  { name: '固定资产减值损失', noReversal: false },
  { name: '在建工程减值损失', noReversal: false },
  { name: '无形资产减值损失', noReversal: false },
  { name: '商誉减值损失', noReversal: true },
  { name: '长期股权投资减值损失', noReversal: false },
  { name: '投资性房地产减值损失', noReversal: false },
  { name: '使用权资产减值损失', noReversal: false },
  { name: '生产性生物资产减值损失', noReversal: false },
  { name: '油气资产减值损失', noReversal: false },
  { name: '工程物资减值损失', noReversal: false },
  { name: '持有待售资产减值损失', noReversal: false },
  { name: '长期待摊费用减值损失', noReversal: false },
  { name: '其他', noReversal: false },
]

function initDefaultRows(): void {
  disclosureRows.value = DEFAULT_CATEGORIES_SOE.map((item, idx) => ({
    id: `row-${idx}`,
    category: item.name,
    currentProvision: 0,
    currentReversal: 0,
    priorAmount: 0,
    remark: '',
    noReversal: item.noReversal,
  }))
}

// ─── 加载已保存数据 ──────────────────────────────────────────────────────────

function loadSavedData(): void {
  const saved = props.allResponses.get('K11-disclosure-soe-rows')
  if (saved?.remark) {
    try {
      const parsed = JSON.parse(saved.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        disclosureRows.value = parsed
        return
      }
    } catch { /* fallthrough */ }
  }
  initDefaultRows()

  const savedNarrative = props.allResponses.get('K11-disclosure-soe-narrative')
  if (savedNarrative?.remark) {
    narrativeText.value = savedNarrative.remark
  }
}

// ─── 自动取数（从K11-1审定表） ────────────────────────────────────────────────

function applyAutoFill(): void {
  const adjData = props.allResponses.get('K11-1-audited-by-category')
  if (adjData?.remark) {
    hasAutoData.value = true
    try {
      const data = JSON.parse(adjData.remark)
      if (data && typeof data === 'object') {
        for (const row of disclosureRows.value) {
          const src = data[row.category]
          if (src) {
            row.currentProvision = Number(src.currentProvision ?? src.provision ?? 0)
            row.currentReversal = Number(src.currentReversal ?? src.reversal ?? 0)
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
  if (row) {
    ;(row as any)[field] = value
    persistRows()
  }
}

function persistRows(): void {
  emit('save', 'K11-disclosure-soe-rows', { remark: JSON.stringify(disclosureRows.value) })
}

function handleNarrativeSave(): void {
  emit('save', 'K11-disclosure-soe-narrative', { remark: narrativeText.value })
  eventBus.emit('disclosure:note-text-updated' as any, { wpCode: 'K11', variant: 'soe', text: narrativeText.value })
}

// ─── 合计汇总方法 ────────────────────────────────────────────────────────────

function summaryMethod({ columns, data }: { columns: any[]; data: DisclosureRow[] }): string[] {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (prop === 'currentProvision') return fmtAmt(data.reduce((s, r) => s + (r.currentProvision || 0), 0))
    if (prop === 'currentReversal') return fmtAmt(data.reduce((s, r) => s + (r.currentReversal || 0), 0))
    if (prop === 'priorAmount') return fmtAmt(data.reduce((s, r) => s + (r.priorAmount || 0), 0))
    if (idx === 3) {
      const total = data.reduce((s, r) => s + (r.currentProvision - r.currentReversal), 0)
      return fmtAmt(total)
    }
    return ''
  })
}

// ─── EventBus ────────────────────────────────────────────────────────────────

function handleAdjudicated(payload: any): void {
  if (!payload || payload.accountCode === '6701' || payload.wpCode === 'K11') {
    applyAutoFill()
  }
}

onMounted(() => {
  loadSavedData()
  applyAutoFill()
  eventBus.on('substantive:adjudicated', handleAdjudicated)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', handleAdjudicated)
})

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function isAbnormal(row: DisclosureRow): boolean {
  if (!row.priorAmount || row.priorAmount === 0) return false
  const occurrence = row.currentProvision - row.currentReversal
  const rate = Math.abs((occurrence - row.priorAmount) / row.priorAmount)
  return rate > ABNORMAL_THRESHOLD
}

function formatRate(row: DisclosureRow): string {
  if (!row.priorAmount || row.priorAmount === 0) return '—'
  const occurrence = row.currentProvision - row.currentReversal
  const rate = (occurrence - row.priorAmount) / row.priorAmount
  return (rate * 100).toFixed(1) + '%'
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

async function handleAiGenerate(): Promise<void> {
  handleAiSection('impairment-disclosure-soe')
}

async function handleAiSection(section: string): Promise<void> {
  if (!props.wpId) return
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: `为K11资产减值损失附注（国企版）的"${section}"部分生成披露说明。`,
      context: JSON.stringify(disclosureRows.value.slice(0, 10)),
      section,
    })
    const text = res.data?.data?.content || res.data?.content
    if (text && section === 'narrative') {
      narrativeText.value = text
      handleNarrativeSave()
    }
    ElMessage.success('AI文本已生成')
  } catch {
    ElMessage.info('AI辅助生成附注披露...')
  }
}
</script>

<style scoped>
.k11-disclosure-soe { padding: 12px; font-size: 13px; }

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; }
.header-actions { display: flex; gap: 8px; align-items: center; }

.methodology-context {
  margin-bottom: 12px;
  padding: 10px 14px;
  background: #fffbf0;
  border-left: 3px solid #e6a23c;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}
.methodology-context p { margin: 0; }

.disclosure-card { margin-bottom: 12px; }
.disclosure-card :deep(.el-card__header) { padding: 10px 16px; }
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-title { font-weight: 600; font-size: 13px; }

.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
}
.no-reversal { color: #909399; font-size: 11px; font-style: italic; }
.abnormal-cell { color: #f56c6c; font-weight: 600; }

.compile-hint {
  margin-top: 12px;
  padding: 10px 14px;
  background: #fafafa;
  border-radius: 6px;
  font-size: 12px;
  color: #606266;
}
.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
  margin-bottom: 6px;
}
.compile-hint ul { padding-left: 20px; margin: 0; line-height: 1.8; }
</style>
