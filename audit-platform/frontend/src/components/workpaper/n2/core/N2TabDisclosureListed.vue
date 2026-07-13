<template>
  <div class="n2-tab-disclosure-listed">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3 class="section-title">附注披露信息（上市公司）</h3>
        <el-tag type="primary" size="small">上市 27×11</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('disclosure-listed')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>上市公司应交税费附注披露（27×11）：</strong>
        按各税种分行列示期初余额、本期计提（贷方增加）、本期缴纳（借方减少）、期末余额。
        数据自动从N2-1审定表/N2-2明细表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
        负债类贷方科目：期末 = 期初 + 计提 − 缴纳。
      </div>
    </div>

    <!-- ═══ Section 1: 各税种期初期末明细 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>应交税费明细</span>
          <el-button size="small" @click="handleAI('section-tax-detail')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="disclosureRows" border size="small" style="width: 100%" :row-class-name="getRowClassName">
        <el-table-column prop="item" label="项目" min-width="180" fixed>
          <template #default="{ row }">
            <span :class="{ 'total-row-label': row._isTotal, 'subtotal-row-label': row._isSubtotal }">
              {{ row.item }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="期初余额" width="130" align="right">
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !row._isSubtotal && !isReadonly">
              <el-input-number
                :model-value="row.beginBalance"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'beginBalance', val ?? 0)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._isTotal || row._isSubtotal }">
              {{ fmtAmount(row.beginBalance) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="本期计提" width="130" align="right">
          <template #header>
            <el-tooltip content="贷方增加（计提）" placement="top">
              <span class="formula-col-header">本期计提</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !row._isSubtotal && !isReadonly">
              <el-input-number
                :model-value="row.accrual"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'accrual', val ?? 0)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._isTotal || row._isSubtotal }">
              {{ fmtAmount(row.accrual) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="本期缴纳" width="130" align="right">
          <template #header>
            <el-tooltip content="借方减少（缴纳）" placement="top">
              <span class="formula-col-header">本期缴纳</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !row._isSubtotal && !isReadonly">
              <el-input-number
                :model-value="row.payment"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(val: number | undefined) => updateRow($index, 'payment', val ?? 0)"
              />
            </template>
            <span v-else :class="{ 'formula-value': row._isTotal || row._isSubtotal }">
              {{ fmtAmount(row.payment) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="期末余额" width="130" align="right">
          <template #header>
            <el-tooltip content="期末 = 期初 + 计提 − 缴纳（负债类贷方）" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 税种变动说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>税种变动说明</span>
          <el-button size="small" @click="handleAI('section-change-note')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="changeNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明主要税种变动原因（如增值税增减、城建税变动、房产税从价/从租、土地增值税项目结算等）..."
        @change="handleChangeNoteChange"
      />
    </el-card>

    <!-- ═══ Section 3: 欠缴税款说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>欠缴税款说明</span>
          <el-button size="small" @click="handleAI('section-overdue-note')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="overdueNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :readonly="isReadonly"
        placeholder="如有欠缴税款，说明税种、金额、欠缴原因及预期解决方案..."
        @change="handleOverdueNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从N2-1审定表和N2-2明细表自动拉取</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>上市公司按各税种分行列示：增值税/城建税/教育费附加/房产税/土地增值税/所得税等</li>
        <li>期末 = 期初 + 计提 − 缴纳（负债类贷方科目）</li>
        <li>格式：27行×11列</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabDisclosureListed — 附注披露信息（上市公司）27×11
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 4.5
 * Requirements: 13.1-13.3
 *
 * 功能：
 * - 表格：项目 | 期初 | 本期计提 | 本期缴纳 | 期末
 * - 行：增值税/城建税/教育费附加/地方教育附加/房产税/土地增值税/所得税/印花税/车船税/其他 + 合计
 * - Auto-refresh from N2-1 (subscribe 'substantive:adjudicated')
 * - textarea sections for change note / overdue note
 * - AI辅助 per section
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useN2FormData } from '../../composables/useN2FormData'
import { calcLiabilityEndBalance } from '../../composables/useN2FormulaEngine'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useN2FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── State ───────────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly ?? false)

/** 固定的税种行（上市公司 27 行，这里列示主要税种） */
const TAX_ITEMS = [
  '增值税',
  '城市维护建设税',
  '教育费附加',
  '地方教育附加',
  '企业所得税',
  '房产税',
  '土地使用税',
  '土地增值税',
  '印花税',
  '车船税',
  '个人所得税（代扣代缴）',
  '其他',
]

interface DisclosureDataRow {
  item: string
  beginBalance: number
  accrual: number
  payment: number
}

const dataRows = ref<DisclosureDataRow[]>(
  TAX_ITEMS.map(item => ({ item, beginBalance: 0, accrual: 0, payment: 0 })),
)

const changeNote = ref('')
const overdueNote = ref('')

// ─── 合计 + 小计 + 公式计算 ──────────────────────────────────────────────────

interface DisplayRow extends DisclosureDataRow {
  endBalance: number
  _isTotal?: boolean
  _isSubtotal?: boolean
}

const disclosureRows = computed<DisplayRow[]>(() => {
  const rows: DisplayRow[] = dataRows.value.map(r => ({
    ...r,
    endBalance: calcLiabilityEndBalance(r.beginBalance, r.accrual, r.payment),
  }))
  // 合计行
  const totalBegin = rows.reduce((s, r) => s + r.beginBalance, 0)
  const totalAccrual = rows.reduce((s, r) => s + r.accrual, 0)
  const totalPayment = rows.reduce((s, r) => s + r.payment, 0)
  rows.push({
    item: '合计',
    beginBalance: totalBegin,
    accrual: totalAccrual,
    payment: totalPayment,
    endBalance: calcLiabilityEndBalance(totalBegin, totalAccrual, totalPayment),
    _isTotal: true,
  })
  return rows
})

// ─── 更新行 ──────────────────────────────────────────────────────────────────

function updateRow(index: number, field: 'beginBalance' | 'accrual' | 'payment', val: number) {
  if (index >= 0 && index < dataRows.value.length) {
    dataRows.value[index][field] = val
    formData.debouncedSave(`N2-disclosure-listed-${index}-${field}`, { remark: String(val) })
  }
}

function getRowClassName({ row }: { row: DisplayRow }): string {
  if (row._isTotal) return 'total-row'
  if (row._isSubtotal) return 'subtotal-row'
  return ''
}

// ─── 文本区保存 ──────────────────────────────────────────────────────────────

function handleChangeNoteChange() {
  formData.debouncedSave('N2-disclosure-listed-change-note', { remark: changeNote.value || null })
}

function handleOverdueNoteChange() {
  formData.debouncedSave('N2-disclosure-listed-overdue-note', { remark: overdueNote.value || null })
}

// ─── AI / 复核 ──────────────────────────────────────────────────────────────

function handleAI(section: string) {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `n2-disclosure-listed-${section}`,
      prompt: `请基于应交税费底稿"${section}"区段数据，给出审计分析建议`,
      context: { section, wpId: props.wpId },
    }).catch(() => {})
  })
}

function handleReview() {
  openReviewDialog?.('N2-disclosure-listed')
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val == null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  for (let i = 0; i < dataRows.value.length; i++) {
    for (const field of ['beginBalance', 'accrual', 'payment'] as const) {
      const resp = formData.allResponses.value.get(`N2-disclosure-listed-${i}-${field}`)
      if (resp?.remark) {
        dataRows.value[i][field] = Number(resp.remark) || 0
      }
    }
  }
  const changeResp = formData.allResponses.value.get('N2-disclosure-listed-change-note')
  if (changeResp?.remark) changeNote.value = changeResp.remark
  const overdueResp = formData.allResponses.value.get('N2-disclosure-listed-overdue-note')
  if (overdueResp?.remark) overdueNote.value = overdueResp.remark
}

// ─── EventBus: 审定变化刷新 ─────────────────────────────────────────────────

function onAdjudicatedRefresh() {
  formData.loadData().then(() => restoreData())
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreData()
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})
</script>

<style scoped>
.n2-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.methodology-text strong { color: #b88230; }

.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }

.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.total-row-label { font-weight: 700; color: #303133; }
.subtotal-row-label { font-weight: 600; color: #606266; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.total-row) { background: #f0f9eb !important; font-weight: 600; }
:deep(.total-row td) { border-top: 2px solid #67c23a; }
:deep(.subtotal-row) { background: #f5f7fa !important; }

.n2-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n2-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.n2-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
