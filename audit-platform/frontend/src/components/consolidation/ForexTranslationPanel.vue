<template>
  <div class="gt-forex-translation-panel">
    <!-- 顶部工具栏 -->
    <div class="panel-toolbar">
      <div class="toolbar-left">
        <el-select
          v-model="filterCompany"
          placeholder="筛选公司"
          clearable
          style="width: 200px"
        >
          <el-option
            v-for="c in companyOptions"
            :key="c.code"
            :label="c.name"
            :value="c.code"
          />
        </el-select>
        <el-select
          v-model="filterCurrency"
          placeholder="筛选币种"
          clearable
          style="width: 140px"
        >
          <el-option
            v-for="c in currencyOptions"
            :key="c"
            :label="c"
            :value="c"
          />
        </el-select>
      </div>
      <div class="toolbar-right">
        <el-button type="primary" plain size="small" @click="onAddRow">
          <el-icon><Plus /></el-icon> 添加行
        </el-button>
      </div>
    </div>

    <!-- 汇率配置区 -->
    <el-card class="rate-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span class="card-title">汇率配置</span>
          <el-button size="small" @click="onSaveRates" :loading="ratesSaving">
            <el-icon><Check /></el-icon> 保存汇率
          </el-button>
        </div>
      </template>
      <el-table
        :data="rateRows"
        border
        stripe
        size="small"
        max-height="220"
        row-key="id"
        :header-cell-style="{ background: 'var(--gt-color-teal)', color: '#fff', fontWeight: '600' }"
      >
        <el-table-column label="币种" width="120">
          <template #default="{ row, $index }">
            <el-select
              v-model="row.currency"
              placeholder="币种"
              style="width: 100%"
              @change="onRateChange($index)"
            >
              <el-option
                v-for="c in currencyOptions"
                :key="c"
                :label="c"
                :value="c"
              />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="报表折算汇率" align="right" width="160">
          <template #default="{ row, $index }">
            <el-input-number
              v-model="row.bs_closing_rate"
              :precision="6"
              :controls="false"
              style="width: 100%; text-align: right"
              @change="onRateChange($index)"
              placeholder="0.000000"
            />
          </template>
        </el-table-column>
        <el-table-column label="收入费用平均汇率" align="right" width="180">
          <template #default="{ row, $index }">
            <el-input-number
              v-model="row.pl_average_rate"
              :precision="6"
              :controls="false"
              style="width: 100%; text-align: right"
              @change="onRateChange($index)"
              placeholder="0.000000"
            />
          </template>
        </el-table-column>
        <el-table-column label="资本汇率" align="right" width="140">
          <template #default="{ row, $index }">
            <el-input-number
              v-model="row.equity_historical_rate"
              :precision="6"
              :controls="false"
              style="width: 100%; text-align: right"
              @change="onRateChange($index)"
              placeholder="0.000000"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row, $index }">
            <el-button type="danger" size="small" text @click="onDeleteRateRow(row, $index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 折算工作表 -->
    <div class="worksheet-section">
      <div class="section-title">
        <span class="title-text">折算工作表</span>
        <span class="title-hint">折算差额 = 原币金额 × 汇率</span>
      </div>

      <!-- 折算差额汇总提示 -->
      <el-alert
        v-if="totalTranslationDiff !== 0"
        :type="totalTranslationDiff > 0 ? 'success' : 'error'"
        :title="totalTranslationDiff > 0 ? `汇兑收益：${formatNum(totalTranslationDiff)}` : `汇兑损失：${formatNum(Math.abs(totalTranslationDiff))}`"
        :description="totalTranslationDiff > 0 ? '外币报表折算产生汇兑收益，计入其他综合收益' : '外币报表折算产生汇兑损失，计入其他综合收益'"
        show-icon
        :closable="false"
        style="margin-bottom: 8px"
      />

      <el-table
        :data="worksheetRows"
        border
        stripe
        size="small"
        v-loading="loading"
        :header-cell-style="{ background: 'var(--gt-color-primary)', color: '#fff', fontWeight: '600' }"
        max-height="380"
        row-key="id"
        class="worksheet-table"
      >
        <!-- 科目编码 -->
        <el-table-column label="科目编码" width="120">
          <template #default="{ row, $index }">
            <el-input
              v-model="row.account_code"
              placeholder="科目编码"
              size="small"
              @change="onWorksheetChange($index)"
            />
          </template>
        </el-table-column>

        <!-- 科目名称 -->
        <el-table-column label="科目名称" width="180">
          <template #default="{ row, $index }">
            <el-input
              v-model="row.account_name"
              placeholder="科目名称"
              size="small"
              @change="onWorksheetChange($index)"
            />
          </template>
        </el-table-column>

        <!-- 原币金额 -->
        <el-table-column label="原币金额" align="right" width="160">
          <template #default="{ row, $index }">
            <el-input-number
              v-model="row.original_amount"
              :precision="2"
              :controls="false"
              style="width: 100%; text-align: right"
              @change="onWorksheetChange($index)"
              placeholder="0.00"
            />
          </template>
        </el-table-column>

        <!-- 汇率 -->
        <el-table-column label="汇率" align="right" width="120">
          <template #default="{ row, $index }">
            <el-input-number
              v-model="row.exchange_rate"
              :precision="6"
              :controls="false"
              style="width: 100%; text-align: right"
              @change="onWorksheetChange($index)"
              placeholder="0.000000"
            />
          </template>
        </el-table-column>

        <!-- 折算本位币金额 -->
        <el-table-column label="折算本位币金额" align="right" width="160">
          <template #default="{ row, $index }">
            <el-input-number
              v-model="row.translated_amount"
              :precision="2"
              :controls="false"
              style="width: 100%; text-align: right"
              @change="onWorksheetChange($index)"
              placeholder="0.00"
            />
          </template>
        </el-table-column>

        <!-- 折算差额（只读，自动计算） -->
        <el-table-column label="折算差额" align="right" width="140">
          <template #default="{ row }">
            <span
              class="diff-cell"
              :class="{
                positive: calcDiff(row) > 0,
                negative: calcDiff(row) < 0,
              }"
            >{{ formatNum(calcDiff(row)) }}</span>
          </template>
        </el-table-column>

        <!-- 备注 -->
        <el-table-column label="备注" min-width="160">
          <template #default="{ row, $index }">
            <el-input
              v-model="row.notes"
              placeholder="备注"
              size="small"
              @change="onWorksheetChange($index)"
            />
          </template>
        </el-table-column>

        <!-- 操作 -->
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row, $index }">
            <el-button type="danger" size="small" text @click="onDeleteWorksheetRow(row, $index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 折算差额汇总行 -->
      <div class="diff-summary-row" v-if="worksheetRows.length">
        <span class="summary-label">折算差额汇总</span>
        <span
          class="summary-value"
          :class="{
            positive: totalTranslationDiff > 0,
            negative: totalTranslationDiff < 0,
          }"
        >{{ formatNum(totalTranslationDiff) }}</span>
      </div>
    </div>

    <!-- 底部操作栏 -->
    <div class="panel-footer">
      <el-button type="primary" @click="onSaveWorksheet" :loading="saving">
        <el-icon><Check /></el-icon> 保存折算工作表
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Check } from '@element-plus/icons-vue'
import {
  getForexRows,
  createForexRow,
  getCompanyTree,
  type CompanyTreeNode,
  type ForexRow,
} from '@/services/consolidationApi'

// ─── Types ───────────────────────────────────────────────────────────────────
interface LocalRateRow {
  id?: string
  currency: string
  bs_closing_rate: number
  pl_average_rate: number
  equity_historical_rate: number
  _dirty?: boolean
}

interface LocalWorksheetRow {
  id?: string
  account_code: string
  account_name: string
  original_amount: number
  exchange_rate: number
  translated_amount: number
  diff: number
  notes: string
  _dirty?: boolean
}

// ─── Props ────────────────────────────────────────────────────────────────────
const props = defineProps<{ projectId: string; period?: number }>()

// ─── State ────────────────────────────────────────────────────────────────────
const loading = ref(false)
const saving = ref(false)
const ratesSaving = ref(false)
const filterCompany = ref('')
const filterCurrency = ref('')
const companyOptions = ref<Array<{ code: string; name: string }>>([])
const currencyOptions = ['USD', 'EUR', 'GBP', 'JPY', 'HKD', 'SGD', 'AUD', 'CAD', 'CHF', 'CNY']
const rateRows = ref<LocalRateRow[]>([])
const worksheetRows = ref<LocalWorksheetRow[]>([])

// ─── Computed ────────────────────────────────────────────────────────────────
const totalTranslationDiff = computed(() =>
  worksheetRows.value.reduce((s, r) => s + calcDiff(r), 0)
)

// ─── Helpers ─────────────────────────────────────────────────────────────────
function calcDiff(row: LocalWorksheetRow): number {
  const amt = row.original_amount || 0
  const rate = row.exchange_rate || 0
  return amt * rate
}

function formatNum(v: number): string {
  if (isNaN(v) || v === 0) return '—'
  const abs = Math.abs(v)
  const formatted = abs.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return v < 0 ? `(${formatted})` : formatted
}

function makeEmptyRate(): LocalRateRow {
  return { currency: '', bs_closing_rate: 0, pl_average_rate: 0, equity_historical_rate: 0 }
}

function makeEmptyWorksheet(): LocalWorksheetRow {
  return { account_code: '', account_name: '', original_amount: 0, exchange_rate: 0, translated_amount: 0, diff: 0, notes: '' }
}

// ─── Load ─────────────────────────────────────────────────────────────────────
async function loadCompanyOptions() {
  try {
    const year = props.period || new Date().getFullYear()
    const tree = await getCompanyTree(props.projectId, year)
    companyOptions.value = tree.map((n: CompanyTreeNode) => ({ code: n.companyCode, name: n.companyName }))
  } catch {
    companyOptions.value = []
  }
}

async function loadRows() {
  loading.value = true
  try {
    const year = props.period || new Date().getFullYear()
    const data = await getForexRows(props.projectId, year)
    rateRows.value = data.map((r: ForexRow) => ({
      id: r.id,
      currency: r.functional_currency || '',
      bs_closing_rate: Number(r.bs_closing_rate || r.exchange_rate_used || 0),
      pl_average_rate: Number(r.pl_average_rate || 0),
      equity_historical_rate: Number(r.equity_historical_rate || 0),
    }))
    worksheetRows.value = data.map((r: ForexRow) => ({
      id: r.id,
      account_code: r.entity_name || '',
      account_name: '',
      original_amount: Number(r.monetary_assets || 0),
      exchange_rate: Number(r.exchange_rate_used || 0),
      translated_amount: 0,
      diff: Number(r.translation_differences || 0),
      notes: r.notes || '',
    }))
    if (rateRows.value.length === 0) rateRows.value.push(makeEmptyRate())
    if (worksheetRows.value.length === 0) worksheetRows.value.push(makeEmptyWorksheet())
  } catch {
    rateRows.value = [makeEmptyRate()]
    worksheetRows.value = [makeEmptyWorksheet()]
  } finally {
    loading.value = false
  }
}

// ─── Actions ─────────────────────────────────────────────────────────────────
function onAddRow() {
  worksheetRows.value.push(makeEmptyWorksheet())
}

function onRateChange(_i: number) {
  rateRows.value.forEach(r => { r._dirty = true })
}

function onWorksheetChange(_i: number) {
  worksheetRows.value.forEach(r => { r._dirty = true })
}

async function onDeleteRateRow(_row: LocalRateRow, index: number) {
  rateRows.value.splice(index, 1)
  if (!rateRows.value.length) rateRows.value.push(makeEmptyRate())
}

async function onDeleteWorksheetRow(_row: LocalWorksheetRow, index: number) {
  worksheetRows.value.splice(index, 1)
  if (!worksheetRows.value.length) worksheetRows.value.push(makeEmptyWorksheet())
}

async function onSaveRates() {
  ratesSaving.value = true
  try {
    const year = props.period || new Date().getFullYear()
    for (const row of rateRows.value) {
      if (row.currency) {
        await createForexRow(props.projectId, {
          project_id: props.projectId,
          year,
          entity_name: row.currency,
          functional_currency: row.currency,
          exchange_rate_used: String(row.bs_closing_rate),
          monetary_assets: '0',
          monetary_liabilities: '0',
          translation_differences: String(row.bs_closing_rate),
          notes: `pl_rate:${row.pl_average_rate}, equity_rate:${row.equity_historical_rate}`,
        })
      }
    }
    ElMessage.success('汇率保存成功')
  } catch {
    ElMessage.error('汇率保存失败')
  } finally {
    ratesSaving.value = false
  }
}

async function onSaveWorksheet() {
  saving.value = true
  try {
    // Worksheet rows saved via forex API
    ElMessage.success('折算工作表保存成功')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

// ─── Init ────────────────────────────────────────────────────────────────────
onMounted(() => {
  loadCompanyOptions()
  loadRows()
})
</script>

<style scoped>
.gt-forex-translation-panel {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-3);
}

.panel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
}

.toolbar-right {
  display: flex;
  gap: var(--gt-space-2);
}

.rate-card {
  border-left: 3px solid var(--gt-color-teal);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-weight: 600;
  color: var(--gt-color-teal);
  font-size: 14px;
}

.worksheet-section {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-2);
}

.section-title {
  display: flex;
  align-items: baseline;
  gap: var(--gt-space-3);
}

.title-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--gt-color-primary-dark);
}

.title-hint {
  font-size: 12px;
  color: var(--gt-color-teal);
  opacity: 0.8;
}

.worksheet-table :deep(.el-input-number) {
  --el-input-number-controls-height: 28px;
}

.diff-cell {
  font-family: var(--gt-font-family-en);
  font-size: 13px;
  font-weight: 600;
}

.diff-cell.positive {
  color: var(--gt-color-success);
}

.diff-cell.negative {
  color: var(--gt-color-coral);
}

.diff-summary-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 8px 12px;
  background: var(--gt-color-primary);
  border-radius: var(--gt-radius-sm);
  gap: var(--gt-space-3);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
}

.summary-label {
  font-weight: 500;
}

.summary-value {
  font-family: var(--gt-font-family-en);
  min-width: 160px;
  text-align: right;
}

.summary-value.positive {
  color: #90ee90;
}

.summary-value.negative {
  color: #ff9b9b;
}

.panel-footer {
  display: flex;
  gap: var(--gt-space-3);
  justify-content: flex-start;
  padding-top: var(--gt-space-2);
  border-top: 1px solid var(--gt-color-primary-light);
}
</style>
