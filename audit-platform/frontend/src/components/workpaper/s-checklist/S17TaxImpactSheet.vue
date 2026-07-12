<template>
  <div class="s17-tax-impact">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实非经常性损益项目所得税影响的计算是否准确，确认税后非经常性损益金额的列报与披露恰当。"
      style="margin-bottom: 16px"
    />

    <!-- ═══ S17-21 非经常性损益项目的所得税影响 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>非经常性损益项目的所得税影响 S17-21</span>
          <div class="header-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              :loading="saving"
              @click="handleSave"
            >保存</el-button>
            <el-button size="small" @click="handleOpenReview('s17-tax-impact', 'S17-21所得税影响')">
              复核
            </el-button>
            <el-button v-if="!isReadonly" size="small" @click="handleAiAssist">
              🤖 AI辅助
            </el-button>
          </div>
        </div>
      </template>

      <!-- 编制提示 -->
      <details class="compile-hint">
        <summary>编制提示</summary>
        <div class="methodology-context">
          <p>本表计算非经常性损益各项目的所得税影响金额。</p>
          <p>所得税影响 = 非经常性损益金额 × 适用税率（一般为 25%，高新技术企业 15%，小微企业另算）。</p>
          <p>部分项目可能存在永久性差异（如罚款支出不可扣除），需单独标注。</p>
          <p>计算结果汇总后回填至 S17-1 审定表"所得税影响"列。</p>
        </div>
      </details>

      <!-- 适用税率设置 -->
      <div class="tax-rate-config">
        <span class="config-label">适用所得税税率：</span>
        <el-input-number
          v-model="taxRate"
          :min="0"
          :max="100"
          :step="5"
          :precision="0"
          :controls="true"
          size="small"
          :disabled="isReadonly"
          @change="recalcAll"
        />
        <span class="config-unit">%</span>
        <el-tag size="small" type="info" style="margin-left: 12px">
          {{ taxRate === 25 ? '一般企业' : taxRate === 15 ? '高新技术企业' : '自定义' }}
        </el-tag>
      </div>

      <!-- 税影响计算表 -->
      <el-table
        :data="taxRows"
        border
        size="small"
        style="width: 100%; font-size: 13px"
        show-summary
        :summary-method="getSummary"
        :cell-class-name="cellClassName"
      >
        <el-table-column type="index" label="序号" width="55" align="center" />

        <el-table-column prop="itemName" label="非经常性损益项目" min-width="250" />

        <el-table-column prop="grossAmount" label="税前金额" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly && row.editable"
              v-model="row.grossAmount"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="() => recalcRow(row)"
            />
            <span v-else>{{ fmt(row.grossAmount) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="deductible" label="可抵扣" width="80" align="center">
          <template #default="{ row }">
            <el-checkbox
              v-model="row.deductible"
              :disabled="isReadonly"
              @change="() => recalcRow(row)"
            />
          </template>
        </el-table-column>

        <el-table-column prop="effectiveRate" label="适用税率" width="100" align="center">
          <template #default="{ row }">
            <span class="formula-cell" :title="row.deductible ? `${row.effectiveRate}% 可税前扣除` : '不可扣除，无所得税影响'">
              {{ row.deductible ? `${row.effectiveRate}%` : '—' }}
            </span>
          </template>
        </el-table-column>

        <el-table-column prop="taxImpact" label="所得税影响" min-width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell audited-amount" title="所得税影响 = 税前金额 × 适用税率（不可扣除项为0）">
              {{ fmt(row.taxImpact) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column prop="netAmount" label="税后净额" min-width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="税后净额 = 税前金额 - 所得税影响">
              {{ fmt(row.netAmount) }}
            </span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 动态行 -->
      <div v-if="!isReadonly" class="row-actions">
        <el-button size="small" type="primary" plain @click="addRow">+ 新增项目</el-button>
      </div>
    </el-card>

    <!-- ═══ 审核说明 ═══ -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>审核说明</span>
          <div class="header-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAiConclusion">🤖 AI辅助</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="对所得税影响计算方法及特殊事项的说明..."
        @change="markDirty"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * S17TaxImpactSheet.vue — S17-21 非经常性损益项目的所得税影响
 *
 * 功能：
 * - 20×7 所得税影响计算表
 * - 公式：所得税影响 = 税前金额 × 适用税率（不可扣除项影响为0）
 * - 税后净额 = 税前金额 - 所得税影响
 * - 适用税率可配置（默认25%，高新15%）
 * - 部分项目不可税前扣除（如罚款），标记后所得税影响为0
 * - 合计行
 * - 动态行新增
 * - readonly 禁止编辑
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 5.3
 * Requirements: 8.2
 */
import { ref, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { fmtAmount } from '@/utils/formatters'

function fmt(val: number | null | undefined): string {
  return fmtAmount(val, 2)
}

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>(
  'openReviewDialog',
  () => {}
)

function handleOpenReview(sectionId: string, sectionLabel: string) {
  openReviewDialog(sectionId, sectionLabel)
}

// ─── 数据模型 ────────────────────────────────────────────────────────────────

interface TaxRow {
  id: string
  itemName: string
  grossAmount: number
  deductible: boolean
  effectiveRate: number
  taxImpact: number
  netAmount: number
  editable: boolean
}

const taxRate = ref(25)
const taxRows = ref<TaxRow[]>([])
const auditNote = ref('')
const saving = ref(false)
const isDirty = ref(false)

// ─── 默认项目 ────────────────────────────────────────────────────────────────

const DEFAULT_ITEMS: Array<{ name: string; deductible: boolean }> = [
  { name: '非流动资产处置损益', deductible: true },
  { name: '债务重组损益', deductible: true },
  { name: '非货币性资产交换损益', deductible: true },
  { name: '政府补助', deductible: true },
  { name: '委托投资/贷款损益', deductible: true },
  { name: '对外捐赠支出', deductible: true },
  { name: '罚款/赔偿支出', deductible: false },
  { name: '税收滞纳金', deductible: false },
  { name: '公允价值变动损益（非套期）', deductible: true },
  { name: '单独测试减值准备转回', deductible: true },
]

// ─── 计算逻辑 ────────────────────────────────────────────────────────────────

function recalcRow(row: TaxRow) {
  row.effectiveRate = taxRate.value
  row.taxImpact = row.deductible
    ? Math.round((row.grossAmount || 0) * taxRate.value) / 100
    : 0
  row.netAmount = (row.grossAmount || 0) - row.taxImpact
  markDirty()
}

function recalcAll() {
  for (const row of taxRows.value) {
    recalcRow(row)
  }
}

function markDirty() { isDirty.value = true }

function addRow() {
  const idx = taxRows.value.length
  taxRows.value.push({
    id: `s17-21-${Date.now()}-${idx}`,
    itemName: '',
    grossAmount: 0,
    deductible: true,
    effectiveRate: taxRate.value,
    taxImpact: 0,
    netAmount: 0,
    editable: true,
  })
  markDirty()
}

// ─── 合计 ────────────────────────────────────────────────────────────────────

function getSummary({ columns, data }: any) {
  const sums: string[] = []
  columns.forEach((col: any, i: number) => {
    if (i === 0) { sums[i] = ''; return }
    if (i === 1) { sums[i] = '合计'; return }
    const prop = col.property
    if (['grossAmount', 'taxImpact', 'netAmount'].includes(prop)) {
      sums[i] = fmt(data.reduce((s: number, r: any) => s + (Number(r[prop]) || 0), 0))
    } else { sums[i] = '' }
  })
  return sums
}

function cellClassName({ column }: any) {
  if (['所得税影响', '税后净额'].includes(column.label)) return 'formula-column'
  return ''
}

// ─── AI ──────────────────────────────────────────────────────────────────────

function handleAiAssist() {
  ElMessage.info('AI辅助功能开发中，将自动从S17-1取数并计算所得税影响')
}

function handleAiConclusion() {
  ElMessage.info('AI将根据税影响计算自动生成审核说明')
}

// ─── 保存 ────────────────────────────────────────────────────────────────────

async function handleSave() {
  if (saving.value) return
  saving.value = true
  try {
    const payload = {
      tax_rate: taxRate.value,
      tax_rows: taxRows.value.map(r => ({
        id: r.id,
        item_name: r.itemName,
        gross_amount: r.grossAmount,
        deductible: r.deductible,
        effective_rate: r.effectiveRate,
        tax_impact: r.taxImpact,
        net_amount: r.netAmount,
      })),
      audit_note: auditNote.value,
    }
    await http.put(
      `/api/workpapers/${props.wpId}/checklist-responses`,
      { sheet_name: '非经常性损益项目的所得税影响S17-21', data: payload }
    )
    isDirty.value = false
    ElMessage.success('所得税影响表已保存')
  } catch (err: any) {
    ElMessage.error(`保存失败：${err?.message || '未知错误'}`)
  } finally {
    saving.value = false
  }
}

// ─── 加载 ────────────────────────────────────────────────────────────────────

async function loadData() {
  try {
    const res = await http.get(
      `/api/workpapers/${props.wpId}/render-config`,
      { _silent: true } as any
    )
    const sheets = res?.data?.sheets || res?.sheets || []
    const sheet = sheets.find((s: any) =>
      s.sheet_name?.includes('S17-21') || s.sheet_name?.includes('所得税影响')
    )
    const htmlData = sheet?.html_data

    if (htmlData?.tax_rows?.length) {
      taxRate.value = htmlData.tax_rate || 25
      taxRows.value = htmlData.tax_rows.map((r: any, idx: number) => ({
        id: r.id || `s17-21-${idx}`,
        itemName: r.item_name || r.itemName || '',
        grossAmount: Number(r.gross_amount ?? r.grossAmount ?? 0),
        deductible: r.deductible !== false,
        effectiveRate: Number(r.effective_rate ?? r.effectiveRate ?? taxRate.value),
        taxImpact: Number(r.tax_impact ?? r.taxImpact ?? 0),
        netAmount: Number(r.net_amount ?? r.netAmount ?? 0),
        editable: true,
      }))
    } else {
      taxRows.value = DEFAULT_ITEMS.map((item, idx) => ({
        id: `s17-21-${idx}`,
        itemName: item.name,
        grossAmount: 0,
        deductible: item.deductible,
        effectiveRate: taxRate.value,
        taxImpact: 0,
        netAmount: 0,
        editable: true,
      }))
    }

    if (htmlData?.audit_note) {
      auditNote.value = htmlData.audit_note
    }
  } catch {
    taxRows.value = DEFAULT_ITEMS.map((item, idx) => ({
      id: `s17-21-${idx}`,
      itemName: item.name,
      grossAmount: 0,
      deductible: item.deductible,
      effectiveRate: taxRate.value,
      taxImpact: 0,
      netAmount: 0,
      editable: true,
    }))
  }
}

onMounted(() => { loadData() })
</script>

<style scoped>
.s17-tax-impact { padding: 12px; }
.audit-section { margin-bottom: 16px; }
.section-header { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 8px; }
.compile-hint { margin-bottom: 12px; font-size: var(--wp-font-size, 13px); }
.compile-hint summary { cursor: pointer; color: #909399; font-size: 12px; margin-bottom: 8px; }
.methodology-context { padding: 10px 14px; border-left: 4px solid #e6a23c; background-color: #fdf6ec; font-size: var(--wp-font-size, 13px); line-height: 1.7; color: #606266; }
.methodology-context p { margin: 4px 0; }
.tax-rate-config { margin-bottom: 12px; display: flex; align-items: center; gap: 8px; font-size: var(--wp-font-size, 13px); }
.config-label { color: #606266; }
.config-unit { color: #909399; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
.audited-amount { font-weight: 600; color: #303133; }
.row-actions { margin-top: 12px; }
:deep(.formula-column) { background-color: #fafafa; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
</style>
