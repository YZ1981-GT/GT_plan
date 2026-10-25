<template>
  <div class="n2-tab-other-tax-calc">
    <!-- ═══ 审计目标 ═══ -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title>审计目标</template>
      <ol class="ao-list">
        <li><strong>完整性</strong>：应交城建税及附加是否已全额计提(计税依据完整)</li>
        <li><strong>准确性</strong>：税率适用是否正确、计算是否准确(逐月测算验证)</li>
      </ol>
    </el-alert>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>应交其他税费测算表 N2-8</span>
        <el-tag type="info" size="small">26×9 · 11公式</el-tag>
        <GtIndexChip value="wp:N2-6" />
        <GtIndexChip value="wp:N2-1" />
      </div>
      <div class="section-actions">
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 当前权威模型：自动附加税 + 手工税种 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>测算口径：</strong>城建税、教育费附加、地方教育附加按
        “增值税应交额 + 消费税”乘适用税率自动计算；其他税种按计税依据、税率或直接录入金额测算。
        测算额与账面计提数的差异用于审计核对。
      </div>
    </div>

    <div class="calc-toolbar">
      <div class="toolbar-section">
        <span class="toolbar-label">城建税地区：</span>
        <el-segmented
          :model-value="otherTaxCalc.urbanAreaType.value"
          :options="urbanAreaOptions"
          @change="handleUrbanAreaChange"
        />
      </div>
      <div class="toolbar-section">
        <el-button size="small" type="warning" plain @click="handleImportFromN26">从N2-6带入</el-button>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleAddManualRow">新增税种</el-button>
        <span class="toolbar-hint">计税依据：增值税 {{ fmtAmount(otherTaxCalc.vatPayable.value) }} + 消费税 {{ fmtAmount(otherTaxCalc.consumptionTaxAmount.value) }}</span>
      </div>
    </div>

    <el-table :data="otherTaxCalc.allCalcRows.value" row-key="key" border size="small" style="width: 100%" max-height="560">
      <el-table-column prop="taxType" label="税种" min-width="140" fixed>
        <template #default="{ row }">
          <el-tag v-if="row.kind === 'auto'" size="small" type="success">自动</el-tag>
          <span style="margin-left:6px">{{ row.taxType }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="taxItem" label="应税项目" min-width="180">
        <template #default="{ row }">
          <el-input v-if="!isReadonly && row.kind === 'manual'" :model-value="row.taxItem" size="small"
            @change="(v: string) => handleManualUpdate(row, 'taxItem', v)" />
          <span v-else>{{ row.taxItem || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="taxBase" label="计税依据" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && row.kind === 'manual'" :model-value="row.taxBase" :controls="false" :precision="2" size="small"
            @change="(v: number) => handleManualUpdate(row, 'taxBase', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.taxBase) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="rate" label="税率" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && row.kind === 'manual'" :model-value="row.rate * 100" :controls="false" :precision="2" size="small"
            @change="(v: number) => handleManualUpdate(row, 'rate', (v ?? 0) / 100)" />
          <span v-else>{{ fmtPercent(row.rate) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="computed" label="测算额" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && row.kind === 'manual'" :model-value="row.computed" :controls="false" :precision="2" size="small"
            @change="(v: number) => handleManualUpdate(row, 'amountManual', v ?? 0)" />
          <span v-else class="auto-calc-cell">{{ fmtAmount(row.computed) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="bookAccrued" label="账面计提数" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.bookAccrued" :controls="false" :precision="2" size="small"
            @change="(v: number) => handleBookAccrual(row, v ?? 0)" />
          <span v-else>{{ fmtAmount(row.bookAccrued) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="diff" label="差异" min-width="120" align="right">
        <template #default="{ row }">
          <span :class="row.diff !== 0 ? 'diff-nonzero' : ''">{{ fmtAmount(row.diff) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="160">
        <template #default="{ row }">
          <el-input v-if="!isReadonly && row.kind === 'manual'" :model-value="row.remark" size="small"
            @change="(v: string) => handleManualUpdate(row, 'remark', v)" />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button v-if="canRemoveManualRow(row)" type="danger" link size="small" @click="handleRemoveManualRow(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="result-card">
      <template #header>
        <div class="card-header">
          <span>测算结果汇总</span>
          <el-button type="primary" size="small" :disabled="isReadonly" @click="handleSyncToN21">同步至N2-1</el-button>
        </div>
      </template>
      <div class="result-grid">
        <div class="result-item"><span class="result-label">城建税</span><span class="result-value">{{ fmtAmount(otherTaxCalc.annualSummary.value.urbanTax) }}</span></div>
        <div class="result-item"><span class="result-label">教育费附加</span><span class="result-value">{{ fmtAmount(otherTaxCalc.annualSummary.value.educationTax) }}</span></div>
        <div class="result-item"><span class="result-label">地方教育附加</span><span class="result-value">{{ fmtAmount(otherTaxCalc.annualSummary.value.localEducationTax) }}</span></div>
        <div class="result-item result-item--total"><span class="result-label">全部税种测算合计</span><span class="result-value">{{ fmtAmount(otherTaxCalc.annualSummary.value.total) }}</span></div>
      </div>
    </el-card>

    <!-- ═══ 审计说明+结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <el-button size="small" @click="handleAiNote">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :readonly="isReadonly"
        placeholder="请输入其他税费测算审计说明..."
        @change="handleNoteChange"
      />
    </el-card>

    <el-card shadow="never" class="conclusion-card" style="margin-top: 12px">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <el-button size="small" @click="handleAiConclusion">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :readonly="isReadonly"
        placeholder="请输入审计结论..."
        @change="handleConclusionChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>城建税税率根据企业注册地选择：市区7% / 县城5% / 其他1%（《城市维护建设税法》）</li>
        <li>教育费附加固定3%，地方教育附加固定2%</li>
        <li>计税依据 = 实际缴纳的增值税(N2-6逐月带入) + 消费税(手工录入)</li>
        <li>免征政策：月销售额≤10万免征教育费附加和地方教育附加(城建税不免)</li>
        <li>同比变动率超过30%需关注并说明原因</li>
        <li>测算结果通过"同步至N2-1"按钮回填审定表对应税种行，同时联动N4税金及附加</li>
        <li>消费税：多数企业为0，酒类/烟草/奢侈品企业需逐月录入</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabOtherTaxCalc — N2-8 应交其他税费测算表 (完全重写)
 *
 * 对照源xlsx模板 26行×9列, 11公式
 * 当前权威模型：3 个自动附加税行 + 稳定身份手工税种行
 * 旧月度/季度 API 已移除，页面按 useN2OtherTaxCalc.allCalcRows 渲染
 */
import { ref, computed, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useN2FormData } from '../../composables/useN2FormData'
import { useN2OtherTaxCalc, type UrbanAreaType, type CalcRow } from '../../composables/useN2OtherTaxCalc'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
  year?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)
const scheduleAutoSnapshot = inject<(() => void) | undefined>('scheduleAutoSnapshot', undefined)

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
const auditConclusion = ref('')

// ─── Constants ───────────────────────────────────────────────────────────────

const urbanAreaOptions = [
  { label: '市区 7%', value: '市区' },
  { label: '县城 5%', value: '县城' },
  { label: '其他 1%', value: '其他' },
]

// 当前权威行模型由 useN2OtherTaxCalc.allCalcRows 提供（3 自动行 + 稳定身份手工行）

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number): string {
  if (val === 0) return '—'
  return (val * 100).toFixed(1) + '%'
}

// ─── Handlers（当前权威行模型） ─────────────────────────────────────────────
function handleUrbanAreaChange(val: string | number) {
  otherTaxCalc.setUrbanAreaType(val as UrbanAreaType)
}

async function handleManualUpdate(row: CalcRow, field: string, value: any) {
  if (row.kind !== 'manual') return
  await otherTaxCalc.updateManualRow(row.key, field as any, value)
}

async function handleBookAccrual(row: CalcRow, value: number) {
  await otherTaxCalc.setBookAccrual(row.taxType, value)
}

async function handleAddManualRow() {
  await otherTaxCalc.addManualRow()
  ElMessage.success('已新增税种行')
}

const DEFAULT_MANUAL_KEYS = new Set([
  'row-消费税', 'row-资源税', 'row-城镇土地使用税', 'row-车船税',
])
function canRemoveManualRow(row: CalcRow): boolean {
  return row.kind === 'manual' && !DEFAULT_MANUAL_KEYS.has(row.key)
}

async function handleRemoveManualRow(row: CalcRow) {
  await otherTaxCalc.removeManualRow(row.key)
  ElMessage.success('已删除税种行')
}

function handleImportFromN26() {
  otherTaxCalc.importFromN26()
  ElMessage.success('已从N2-6更新计税依据')
}

async function handleSyncToN21() {
  await otherTaxCalc.syncToAdjudication()
  // syncToAdjudication 已按 EventBus 契约发布 tax-accrual:updated；页面不重复投递第二种载荷。
  scheduleAutoSnapshot?.()
  ElMessage.success('已同步至N2-1审定表')
}

function handleNoteChange() {
  formData.debouncedSave('N2-8-note', { remark: auditNote.value || null })
}

function handleConclusionChange() {
  formData.debouncedSave('N2-8-conclusion', { remark: auditConclusion.value || null })
}

function handleAiAssist() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n2-other-tax-calc',
      prompt: '请基于应交税费底稿逐月测算数据，对城建税及附加的完整性和准确性进行分析',
      context: {
        urbanTax: String(otherTaxCalc.annualSummary.value.urbanTax),
        educationTax: String(otherTaxCalc.annualSummary.value.educationTax),
        localEducationTax: String(otherTaxCalc.annualSummary.value.localEducationTax),
        total: String(otherTaxCalc.annualSummary.value.totalSurtax),
        urbanAreaType: otherTaxCalc.urbanAreaType.value,
      },
    }).catch(() => {})
  })
}

function handleAiNote() {
  handleAiAssist()
}

function handleAiConclusion() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n2-other-tax-conclusion',
      prompt: '请生成城建税及附加测算审计结论',
      context: {
        total: String(otherTaxCalc.annualSummary.value.totalSurtax),
        differenceRows: String(otherTaxCalc.diffRows.value.length),
      },
    }).catch(() => {})
  })
}

function handleReview() {
  openReviewDialog?.('N2-8-其他税费测算')
}

function handleExportTemplate() { /* TODO: useN2ImportExport */ }
function handleExportData() { /* TODO: useN2ImportExport */ }
function handleImportData() { /* TODO: useN2ImportExport */ }

// ─── 数据恢复 ────────────────────────────────────────────────────────────────

function restoreData(): void {
  const noteResp = formData.allResponses.value.get('N2-8-note')
  if (noteResp?.remark) auditNote.value = noteResp.remark
  const concResp = formData.allResponses.value.get('N2-8-conclusion')
  if (concResp?.remark) auditConclusion.value = concResp.remark
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

/* ─── 审计目标 ─── */
.audit-objective {
  margin-bottom: 14px;
}
.audit-objective :deep(.el-alert__content) {
  padding: 2px 0;
}
.ao-list {
  padding-left: 18px;
  line-height: 1.55;
  font-size: 12px;
  margin: 0;
}

/* ─── Section Header ─── */
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
.toolbar-hint {
  font-size: 12px;
  color: #909399;
  cursor: help;
  border-bottom: 1px dashed #c0c4cc;
}

/* ─── 表格公式列样式 ─── */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}
.auto-calc-cell {
  color: #606266;
  background: transparent;
}
.total-cell {
  font-weight: 600;
  color: #303133;
}
.diff-nonzero {
  color: #e6a23c;
  font-weight: 500;
}
.variance-high {
  color: #e6a23c;
  font-weight: 600;
  background: #fdf6ec;
  padding: 2px 4px;
  border-radius: 2px;
}
.variance-icon {
  color: #e6a23c;
  margin-left: 4px;
  font-size: 14px;
  vertical-align: middle;
}

/* ─── 行样式 ─── */
:deep(.quarter-subtotal-row) {
  background-color: #ecf5ff !important;
  font-weight: 500;
}
:deep(.quarter-subtotal-row) td {
  background-color: #ecf5ff !important;
}
:deep(.annual-total-row) {
  background-color: #f0f9eb !important;
  font-weight: 700;
  border-top: 2px solid #67c23a;
}
:deep(.annual-total-row) td {
  background-color: #f0f9eb !important;
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
  background: #f0f9eb;
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
  color: #67c23a;
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
