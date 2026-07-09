<template>
  <div class="n2-tab-disclosure-soe">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3 class="section-title">附注披露信息（国有企业）</h3>
        <el-tag type="warning" size="small">国企 24×11</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('disclosure-soe')">
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
        <strong>国有企业应交税费附注披露（24×11）：</strong>
        国企附注格式与上市公司类似，但增加"应缴国有资本收益"、"国资委考核指标"等专项内容。
        各税种期初/计提/缴纳/期末按负债类公式计算。
        数据自动从N2-1审定表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
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
        <el-table-column prop="item" label="项目" min-width="200" fixed>
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

    <!-- ═══ Section 2: 应缴国有资本收益 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>应缴国有资本收益说明</span>
          <el-button size="small" @click="handleAI('section-soe-capital')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="soeCapitalNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明应缴国有资本收益情况（上缴比例、计算基数、本期应缴金额、实际缴纳情况等）..."
        @change="handleSoeCapitalNoteChange"
      />
    </el-card>

    <!-- ═══ Section 3: 税种变动说明 ═══ -->
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
        placeholder="说明主要税种变动原因（增值税增减、附加税变动、所得税年度汇算清缴差异等）..."
        @change="handleChangeNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从N2-1审定表和N2-2明细表自动拉取</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>国企需额外披露应缴国有资本收益（财企[2007]309号）</li>
        <li>期末 = 期初 + 计提 − 缴纳（负债类贷方科目）</li>
        <li>格式：24行×11列</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabDisclosureSoe — 附注披露信息（国有企业）24×11
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 4.5
 * Requirements: 13.1-13.3
 *
 * 功能：
 * - 表格：项目 | 期初 | 本期计提 | 本期缴纳 | 期末
 * - 行：增值税/城建税/教育费附加/房产税/土增税/所得税/应缴国有资本收益/其他 + 合计
 * - Auto-refresh from N2-1 (subscribe 'substantive:adjudicated')
 * - 国企特有：应缴国有资本收益 section
 * - AI辅助 per section
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useN2FormData } from '../../composables/useN2FormData'
import { calcLiabilityEndBalance } from '../../composables/useN2FormulaEngine'

// ─── Props ───────────────────────────────────────────────────────────────────

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

/** 国企税种行（24行，含国有资本收益） */
const TAX_ITEMS_SOE = [
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
  '应缴国有资本收益',
  '其他',
]

interface DisclosureDataRow {
  item: string
  beginBalance: number
  accrual: number
  payment: number
}

const dataRows = ref<DisclosureDataRow[]>(
  TAX_ITEMS_SOE.map(item => ({ item, beginBalance: 0, accrual: 0, payment: 0 })),
)

const soeCapitalNote = ref('')
const changeNote = ref('')

// ─── 合计 + 公式 ─────────────────────────────────────────────────────────────

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
    formData.debouncedSave(`N2-disclosure-soe-${index}-${field}`, { remark: String(val) })
  }
}

function getRowClassName({ row }: { row: DisplayRow }): string {
  if (row._isTotal) return 'total-row'
  if (row._isSubtotal) return 'subtotal-row'
  return ''
}

// ─── 文本区保存 ──────────────────────────────────────────────────────────────

function handleSoeCapitalNoteChange() {
  formData.debouncedSave('N2-disclosure-soe-capital-note', { remark: soeCapitalNote.value || null })
}

function handleChangeNoteChange() {
  formData.debouncedSave('N2-disclosure-soe-change-note', { remark: changeNote.value || null })
}

// ─── AI / 复核 ──────────────────────────────────────────────────────────────

function handleAI(_section: string) {
  // AI辅助placeholder
}

function handleReview() {
  openReviewDialog?.('N2-disclosure-soe')
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
      const resp = formData.allResponses.value.get(`N2-disclosure-soe-${i}-${field}`)
      if (resp?.remark) {
        dataRows.value[i][field] = Number(resp.remark) || 0
      }
    }
  }
  const capitalResp = formData.allResponses.value.get('N2-disclosure-soe-capital-note')
  if (capitalResp?.remark) soeCapitalNote.value = capitalResp.remark
  const changeResp = formData.allResponses.value.get('N2-disclosure-soe-change-note')
  if (changeResp?.remark) changeNote.value = changeResp.remark
}

// ─── EventBus ────────────────────────────────────────────────────────────────

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
.n2-tab-disclosure-soe { padding: 12px; font-size: 13px; }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }
.methodology-text strong { color: #b88230; }

.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }

.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.total-row-label { font-weight: 700; color: #303133; }
.subtotal-row-label { font-weight: 600; color: #606266; }

:deep(.el-table) { font-size: 13px; }
:deep(.total-row) { background: #f0f9eb !important; font-weight: 600; }
:deep(.total-row td) { border-top: 2px solid #67c23a; }
:deep(.subtotal-row) { background: #f5f7fa !important; }

.n2-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.n2-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.n2-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
