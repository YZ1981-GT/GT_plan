<!--
  G3TabCalcCheck.vue — G3-4 测算及检查表（18列 → 2区段Tab）

  2区段Tab切换：股利测算(9列) / 凭证检查(9列)
  区段间行同步：所有区段共享同一行集合，切换Tab只改可见列
  公式列：应收股利(持股×DPS)、测算差异(测算-入账)
  |差异|>100橙色高亮
  GtVoucherSamplingEngine集成（dialog，科目1131，样本填入凭证检查区段）
  已抽凭行来源tooltip

  Spec: .kiro/specs/g3-dividend-receivable/ Task 6.3
  Requirements: 7.1~7.10
-->
<template>
  <div class="g3-calc-check">
    <div class="section-head">
      <h3 class="sheet-title">G3-4 测算及检查表</h3>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="calcCheck.addRow()">＋ 新增</el-button>
        <el-button size="small" type="success" :disabled="isReadonly" @click="openSamplingEngine">使用抽凭引擎</el-button>
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G3-4-calc-check')">💬复核</el-button>
        <GtIndexChip value="wp:G3-4" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ calcCheck.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：独立测算应收股利金额并与企业入账数核对，通过抽凭检查验证入账凭证的真实性与准确性，关注测算差异较大项目。"
    />

    <!-- 2区段Tab -->
    <el-tabs v-model="calcCheck.segment.value" type="border-card" class="segment-tabs">
      <el-tab-pane
        v-for="seg in calcCheck.segments"
        :key="seg.key"
        :label="seg.label"
        :name="seg.key"
      />
    </el-tabs>

    <!-- 动态列表格 -->
    <el-table
      :data="calcCheck.rows.value"
      border
      size="small"
      max-height="520"
      :row-class-name="rowClassName"
      class="calc-check-table"
    >
      <!-- 序号列（始终显示） -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">
          <span>{{ row.seq }}</span>
          <el-tooltip v-if="calcCheck.isSamplingRow(row)" content="来源: 抽凭引擎" placement="top">
            <span class="sample-flag">📌</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 被投资方名称（始终显示作为锚定列） -->
      <el-table-column label="被投资方" width="150" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.investeeName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => calcCheck.updateRow(row.id, { investeeName: v })"
          />
        </template>
      </el-table-column>

      <!-- 动态区段列 -->
      <el-table-column
        v-for="col in currentColumns"
        :key="col.prop"
        :label="col.label"
        :min-width="col.width"
        :align="col.type === 'number' || col.formula ? 'right' : 'left'"
      >
        <template #default="{ row }">
          <!-- 公式列：只读 + 虚线下划线 + tooltip -->
          <template v-if="col.formula">
            <span
              class="formula-cell"
              :title="getFormulaTooltip(col.prop)"
            >
              {{ fmtNum(row[col.prop]) }}
            </span>
          </template>

          <!-- 日期列 -->
          <template v-else-if="col.type === 'date'">
            <el-date-picker
              :model-value="row[col.prop]"
              type="date"
              size="small"
              :disabled="isReadonly"
              value-format="YYYY-MM-DD"
              style="width:100%"
              @update:model-value="(v: string) => calcCheck.updateRow(row.id, { [col.prop]: v ?? '' })"
            />
          </template>

          <!-- 数字列 -->
          <template v-else-if="col.type === 'number'">
            <el-input-number
              :model-value="row[col.prop] as number"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => calcCheck.updateRow(row.id, { [col.prop]: v ?? 0 })"
            />
          </template>

          <!-- 文本列 -->
          <template v-else>
            <el-input
              :model-value="row[col.prop] as string"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => calcCheck.updateRow(row.id, { [col.prop]: v })"
            />
          </template>
        </template>
      </el-table-column>

      <!-- 操作列(删除) -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-icon class="delete-icon" @click="calcCheck.removeRow(row.id)">
            <Delete />
          </el-icon>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部合计 -->
    <div class="totals-bar">
      <span class="totals-label">合计</span>
      <span class="total-item">应收股利(测算)：{{ fmtNum(calcCheck.totals.value.calculatedDividend) }}</span>
      <span class="total-item">企业入账：{{ fmtNum(calcCheck.totals.value.bookedAmount) }}</span>
      <span class="total-item">测算差异：{{ fmtNum(calcCheck.totals.value.calcVariance) }}</span>
      <span class="total-item">凭证金额：{{ fmtNum(calcCheck.totals.value.amount) }}</span>
    </div>

    <!-- 审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计结论</span>
          <el-button size="small" :disabled="isReadonly" @click="fillAiConclusion">🤖AI辅助</el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对股利测算及凭证检查的复核结论..."
        @change="persistConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示（CAS 依据）</summary>
      <div class="guidance-content">
        <p>1. 应收股利(测算) = 持股数量 × 每股股利；测算差异 = 应收股利(测算) - 企业入账金额。</p>
        <p>2. |测算差异| &gt; 100 元的行以橙色高亮，需重点关注。</p>
        <p>3. 抽凭引擎按科目 1131 抽取样本，自动填入凭证检查区段，已填入行显示 📌 标记。</p>
        <p>4. 2 区段共享同一行集合，切换 Tab 可查看同一被投资方的测算和凭证信息。</p>
        <p>5. 灰色底纹列为自动计算列，不可手动编辑。</p>
        <p class="cas-basis">CAS 依据：通过重新计算与检查凭证获取充分适当的审计证据（《中国注册会计师审计准则第 1301 号——审计证据》）。</p>
      </div>
    </details>

    <!-- 抽凭引擎Dialog -->
    <el-dialog
      v-model="showSamplingDialog"
      title="抽凭引擎 - 科目1131应收股利"
      width="860px"
      destroy-on-close
      append-to-body
    >
      <SamplingEngine
        v-if="showSamplingDialog"
        account-code="1131"
        phase="final"
        default-method="random"
        :workpaper-id="wpId"
        :project-id="projectId"
        @filled="handleSamplingFilled"
      />
      <template #footer>
        <el-button @click="showSamplingDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, inject, defineAsyncComponent } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../GtIndexChip.vue'
import {
  useG3CalcCheck,
  G3_CALCCHECK_SEGMENTS,
  isVarianceExceeding,
  isSamplingRow,
} from '../composables/useG3CalcCheck'
import type { CalcCheckRow, CalcCheckColumn } from '../composables/useG3CalcCheck'
import type { ChecklistResponse } from '../composables/useF1FormData'
import type { SampledVoucher } from '../composables/useSamplingAlgorithms'

// Lazy load GtVoucherSamplingEngine
const SamplingEngine = defineAsyncComponent(
  () => import('../voucher-sampling/GtVoucherSamplingEngine.vue'),
)

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const calcCheck = useG3CalcCheck({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

// ─── 审计结论持久化 ───
const CONCLUSION_KEY = 'G3-4-calccheck-conclusion'
const auditConclusion = ref(
  props.allResponses.get(CONCLUSION_KEY)?.conclusion ?? '',
)

function persistConclusion() {
  if (!props.isReadonly) {
    props.debouncedSave(CONCLUSION_KEY, { conclusion: auditConclusion.value })
  }
}

// ─── 当前区段可见列（排除seq和investeeName，已作固定列） ───
const currentColumns = computed<CalcCheckColumn[]>(() => {
  const seg = G3_CALCCHECK_SEGMENTS.find((s) => s.key === calcCheck.segment.value)
  if (!seg) return []
  return seg.columns.filter((c) => c.prop !== 'seq' && c.prop !== 'investeeName')
})

// ─── 行样式：差异>100橙色 ───
function rowClassName({ row }: { row: CalcCheckRow }): string {
  return isVarianceExceeding(row) ? 'row-variance-exceed' : ''
}

// ─── 公式列tooltip ───
function getFormulaTooltip(prop: keyof CalcCheckRow): string {
  const tooltips: Partial<Record<keyof CalcCheckRow, string>> = {
    seq: '序号（自动）',
    calculatedDividend: '应收股利(测算) = 持股数量 × 每股股利',
    calcVariance: '测算差异 = 应收股利(测算) - 企业入账金额',
  }
  return tooltips[prop] ?? '公式计算'
}

// ─── 数字格式化 ───
function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

// ─── 抽凭引擎 ───
const showSamplingDialog = ref(false)

function openSamplingEngine() {
  showSamplingDialog.value = true
}

function handleSamplingFilled(samples: SampledVoucher[]) {
  if (!samples.length) return

  // 将SampledVoucher映射为CalcCheckRow凭证检查区段字段
  const mapped = samples.map((s) => ({
    voucherDate: s.voucherDate ?? '',
    voucherNo: s.voucherNo ?? '',
    summary: s.summary ?? '',
    counterAccount: s.counterpartAccount ?? '',
    amount: parseFloat(s.debitAmount ?? s.creditAmount ?? '0') || 0,
    receivingBank: '',
    receiptDate: '',
    reconciliationResult: '',
    investeeName: s.accountName ?? '',
  }))

  calcCheck.fillFromSamples(mapped)
  showSamplingDialog.value = false
  ElMessage.success(`已填入 ${mapped.length} 条抽凭样本`)
}

// ─── AI辅助结论 ───
function fillAiConclusion() {
  if (props.isReadonly) return
  const t = calcCheck.totals.value
  const rows = calcCheck.rows.value
  const exceedCount = rows.filter((r) => isVarianceExceeding(r)).length
  const sampledCount = rows.filter((r) => isSamplingRow(r)).length

  const draft =
    `经测算检查，共 ${rows.length} 笔应收股利，` +
    `测算合计 ${fmtNum(t.calculatedDividend)} 元，` +
    `企业入账合计 ${fmtNum(t.bookedAmount)} 元，` +
    `差异合计 ${fmtNum(t.calcVariance)} 元。` +
    (exceedCount > 0
      ? `其中 ${exceedCount} 笔差异超过100元，需关注。`
      : '各项差异均在合理范围内。') +
    (sampledCount > 0
      ? ` 已抽凭检查 ${sampledCount} 笔，凭证核对无异常。`
      : '') +
    (exceedCount === 0
      ? ' 股利测算及凭证检查未发现重大异常，应收股利核算恰当。'
      : ' 建议进一步核实差异较大项目的入账依据。')

  auditConclusion.value = auditConclusion.value
    ? `${auditConclusion.value}\n${draft}`
    : draft
  persistConclusion()
}

// ─── 导入导出（占位，useG3ImportExport Task 8.2 实现） ───
function handleExportTemplate() {
  ElMessage.info('导出模板功能将在导入导出模块完成后启用')
}
function handleExportData() {
  ElMessage.info('导出数据功能将在导入导出模块完成后启用')
}
function handleImportData() {
  ElMessage.info('导入数据功能将在导入导出模块完成后启用')
}
</script>

<style scoped>
.g3-calc-check {
  padding: 12px;
  font-size: 13px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 区段Tab */
.segment-tabs {
  margin-bottom: 0;
}

.segment-tabs :deep(.el-tabs__content) {
  display: none; /* 内容区由下方el-table渲染 */
}

/* 表格 */
.calc-check-table {
  border-top: none;
}

/* 公式列：灰底 + 虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 40px;
  padding: 0 4px;
  text-align: right;
  background: #f5f7fa;
  border-radius: 2px;
}

/* 差异>100橙色 */
:deep(.row-variance-exceed) {
  background-color: #fdf6ec !important;
}
:deep(.row-variance-exceed td) {
  background-color: #fdf6ec !important;
}

/* 抽凭来源标记 */
.sample-flag {
  margin-left: 4px;
  font-size: 12px;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

/* 底部合计 */
.totals-bar {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
  flex-wrap: wrap;
}
.totals-label {
  color: #303133;
  min-width: 36px;
}
.total-item {
  color: #606266;
}

/* 审计结论 */
.conclusion-card {
  margin-top: 12px;
}
.conclusion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 审计目标 */
.audit-objective {
  margin-bottom: 12px;
}

/* 编制提示（guidance-details gold 样式） */
.guidance-details {
  margin-top: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.guidance-content .cas-basis {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}
</style>
