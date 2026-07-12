<template>
  <div class="n2-tab-other-tax-calc">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>其他税费测算表 N2-8</span>
        <el-tag type="info" size="small">26×9 · 11公式</el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" @click="handleAiAssist">
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
        <strong>城建税及附加测算：</strong>
        城建税 = (增值税 + 消费税) × 税率(市区7%/县城5%/其他1%)；
        教育费附加 = (增值税 + 消费税) × 3%；
        地方教育附加 = (增值税 + 消费税) × 2%。
        计税依据取自N2-6增值税测算结果，自动联动。
      </div>
    </div>

    <!-- ═══ 计税依据来源 + 地区选择 ═══ -->
    <div class="calc-toolbar">
      <div class="toolbar-section">
        <span class="toolbar-label">计税依据来源：</span>
        <el-tag type="primary" effect="plain">
          N2-6 应交增值税 = {{ fmtAmount(otherTaxCalc.taxBase.value) }}
        </el-tag>
        <el-tooltip content="计税依据 = 应交增值税(N2-6) + 消费税" placement="top">
          <el-icon class="info-icon"><InfoFilled /></el-icon>
        </el-tooltip>
      </div>
      <div class="toolbar-section">
        <span class="toolbar-label">城建税地区：</span>
        <el-segmented
          :model-value="otherTaxCalc.urbanAreaType.value"
          :options="urbanAreaOptions"
          @change="handleUrbanAreaChange"
        />
      </div>
    </div>

    <!-- ═══ 消费税录入（如有） ═══ -->
    <div class="consumption-tax-row">
      <span class="row-label">消费税金额（如有）：</span>
      <el-input-number
        :model-value="consumptionTaxAmount"
        :disabled="isReadonly"
        :controls="false"
        :precision="2"
        size="small"
        placeholder="0"
        style="width: 140px"
        @change="handleConsumptionTaxChange"
      />
      <span class="row-hint">无消费税则填0</span>
    </div>

    <!-- ═══ 三行附加税测算表 ═══ -->
    <el-table
      :data="otherTaxCalc.rows.value"
      border
      size="small"
      style="width: 100%"
      show-summary
      :summary-method="getSummaryRow"
    >
      <el-table-column prop="taxType" label="税种" width="140" />
      <el-table-column label="计税依据" width="160" align="right">
        <template #header>
          <el-tooltip content="增值税 + 消费税（取自N2-6联动）" placement="top">
            <span class="formula-col-header">计税依据</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-cell">{{ fmtAmount(row.taxBase) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="适用税率" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="row.taxType === '城建税' ? 'warning' : 'info'" effect="plain">
            {{ fmtPercent(row.rate) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="应交税额" width="160" align="right">
        <template #header>
          <el-tooltip content="公式：计税依据 × 适用税率" placement="top">
            <span class="formula-col-header">应交税额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-cell">{{ fmtAmount(row.amount) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 测算结果汇总卡片 ═══ -->
    <el-card shadow="never" class="result-card">
      <template #header>
        <div class="card-header">
          <span>测算结果汇总</span>
          <el-tag type="success" size="small" effect="dark">
            回填N2-1 + 联动N4
          </el-tag>
        </div>
      </template>
      <div class="result-grid">
        <div class="result-item">
          <span class="result-label">城建税</span>
          <span class="result-value">{{ fmtAmount(otherTaxCalc.summary.value.urbanMaintenance) }}</span>
        </div>
        <div class="result-item">
          <span class="result-label">教育费附加</span>
          <span class="result-value">{{ fmtAmount(otherTaxCalc.summary.value.educationSurcharge) }}</span>
        </div>
        <div class="result-item">
          <span class="result-label">地方教育附加</span>
          <span class="result-value">{{ fmtAmount(otherTaxCalc.summary.value.localEducation) }}</span>
        </div>
        <div class="result-item result-item--total">
          <span class="result-label">合计应交</span>
          <span class="result-value">{{ fmtAmount(otherTaxCalc.summary.value.total) }}</span>
        </div>
      </div>
    </el-card>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header">
          <span>审计说明与结论</span>
          <el-button size="small" @click="handleAiAssist">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="请输入其他税费测算审计说明..."
        @change="handleNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>城建税税率根据企业注册地选择：市区7% / 县城5% / 其他1%</li>
        <li>教育费附加固定3%，地方教育附加固定2%</li>
        <li>计税依据 = 实际缴纳的增值税(N2-6) + 消费税</li>
        <li>注意优惠政策：月销售额≤10万免征教育费附加/地方教育附加</li>
        <li>测算结果自动回填N2-1对应税种行，联动N4税金及附加</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabOtherTaxCalc — N2-8 其他税费测算表
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 4.11
 * Requirements: 5.1-5.5
 *
 * 核心职责：
 * - 26×9+11公式，城建税/教育费附加/地方教育附加
 * - 计税依据取自N2-6（联动）
 * - 城建税税率地区选择（市区7%/县城5%/其他1%）
 * - 回填N2-1及联动N4
 * - Uses useN2OtherTaxCalc composable
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ChatDotSquare, InfoFilled } from '@element-plus/icons-vue'
import { useN2FormData } from '../../composables/useN2FormData'
import { useN2OtherTaxCalc, type UrbanAreaType } from '../../composables/useN2OtherTaxCalc'

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

// ─── Composable ──────────────────────────────────────────────────────────────

const otherTaxCalc = useN2OtherTaxCalc({
  allResponses: formData.allResponses,
  saveField: formData.saveField,
  getField: formData.getField,
})

// ─── State ───────────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly ?? false)
const auditNote = ref('')
const consumptionTaxAmount = ref(0)

// ─── Constants ───────────────────────────────────────────────────────────────

const urbanAreaOptions = [
  { label: '市区 7%', value: '市区' },
  { label: '县城 5%', value: '县城' },
  { label: '其他 1%', value: '其他' },
]

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number): string {
  return (val * 100).toFixed(1) + '%'
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleUrbanAreaChange(val: string | number) {
  otherTaxCalc.setUrbanAreaType(val as UrbanAreaType)
}

function handleConsumptionTaxChange(val: number) {
  consumptionTaxAmount.value = val ?? 0
  otherTaxCalc.setConsumptionTax(val ?? 0)
}

function handleNoteChange() {
  formData.debouncedSave('N2-8-note', { remark: auditNote.value || null })
}

function handleAiAssist() {
  ElMessage.info('AI辅助其他税费分析...')
}

function handleReview() {
  openReviewDialog?.('N2-8-其他税费测算')
}

/** 合计行 */
function getSummaryRow({ columns }: { columns: any[] }) {
  const sums: string[] = []
  columns.forEach((_col: any, index: number) => {
    if (index === 0) { sums[index] = '合计'; return }
    if (index === 3) { sums[index] = fmtAmount(otherTaxCalc.summary.value.total); return }
    sums[index] = ''
  })
  return sums
}

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  const noteResp = formData.allResponses.value.get('N2-8-note')
  if (noteResp?.remark) auditNote.value = noteResp.remark
  // 恢复消费税
  const ct = formData.getField('8', 'consumption-tax')
  if (ct != null) consumptionTaxAmount.value = Number(ct) || 0
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreData()
})
</script>

<style scoped>
.n2-tab-other-tax-calc {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 方法论上下文 ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 工具栏 ─── */
.calc-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
  padding: 10px 14px;
  background: #f5f7fa;
  border-radius: 6px;
}

.toolbar-section {
  display: flex;
  align-items: center;
  gap: 8px;
}

.toolbar-label {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  white-space: nowrap;
}

.info-icon {
  color: #909399;
  cursor: help;
}

/* ─── 消费税行 ─── */
.consumption-tax-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding: 8px 14px;
  background: #fafafa;
  border-radius: 4px;
}

.row-label {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.row-hint {
  font-size: 12px;
  color: #c0c4cc;
}

/* ─── 表格 ─── */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.formula-cell {
  color: #409eff;
  font-weight: 500;
}

/* ─── 结果卡片 ─── */
.result-card {
  margin-top: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.result-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px;
  background: #f5f7fa;
  border-radius: 6px;
}

.result-item--total {
  background: #ecf5ff;
}

.result-label {
  font-size: 12px;
  color: #909399;
}

.result-value {
  font-size: 16px;
  font-weight: 700;
  color: #303133;
}

.result-item--total .result-value {
  color: #409eff;
}

/* ─── 结论卡片 ─── */
.conclusion-card {
  margin-top: 16px;
}

/* ─── 编制提示 ─── */
.n2-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.n2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
