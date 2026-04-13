<template>
  <div class="gt-goodwill-panel">
    <!-- 顶部工具栏 -->
    <div class="panel-toolbar">
      <div class="toolbar-left">
        <span class="toolbar-label">所属公司</span>
        <el-select
          v-model="filterCompany"
          placeholder="筛选子公司"
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
      </div>
      <div class="toolbar-right">
        <el-button type="primary" plain size="small" @click="onAddRow">
          <el-icon><Plus /></el-icon> 添加商誉行
        </el-button>
      </div>
    </div>

    <!-- 商誉计算表 -->
    <el-table
      :data="filteredRows"
      border
      stripe
      size="small"
      v-loading="loading"
      :header-cell-style="{ background: 'var(--gt-color-primary)', color: '#fff', fontWeight: '600' }"
      class="goodwill-table"
      max-height="420"
      row-key="id"
    >
      <!-- 被收购方 -->
      <el-table-column label="被收购方" width="180">
        <template #default="{ row, $index }">
          <el-select
            v-model="row.subsidiary_code"
            placeholder="选择子公司"
            style="width: 100%"
            :disabled="row._readonly"
            @change="onCellChange($index)"
          >
            <el-option
              v-for="c in companyOptions"
              :key="c.code"
              :label="c.name"
              :value="c.code"
            />
          </el-select>
        </template>
      </el-table-column>

      <!-- 合并成本 -->
      <el-table-column label="合并成本" align="right" width="160">
        <template #default="{ row, $index }">
          <el-input-number
            v-model="row.acquisition_cost"
            :precision="2"
            :min="0"
            :controls="false"
            style="width: 100%; text-align: right"
            @change="onCellChange($index)"
            placeholder="0.00"
          />
        </template>
      </el-table-column>

      <!-- 减：取得的净资产公允价值 -->
      <el-table-column label="减：取得的净资产公允价值" align="right" width="200">
        <template #default="{ row, $index }">
          <el-input-number
            v-model="row.identifiable_net_assets_fv"
            :precision="2"
            :min="0"
            :controls="false"
            style="width: 100%; text-align: right"
            @change="onCellChange($index)"
            placeholder="0.00"
          />
        </template>
      </el-table-column>

      <!-- 商誉 = 合并成本 - 净资产 -->
      <el-table-column label="商誉" align="right" width="160">
        <template #default="{ row }">
          <span
            class="computed-cell"
            :class="{ negative: calcGoodwill(row) < 0 }"
          >{{ formatNum(calcGoodwill(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 本期减值 -->
      <el-table-column label="本期减值" align="right" width="140">
        <template #default="{ row, $index }">
          <el-input-number
            v-model="row.current_year_impairment"
            :precision="2"
            :min="0"
            :controls="false"
            style="width: 100%; text-align: right"
            @change="onCellChange($index)"
            placeholder="0.00"
          />
        </template>
      </el-table-column>

      <!-- 期末账面价值 -->
      <el-table-column label="期末账面价值" align="right" width="160">
        <template #default="{ row }">
          <span class="computed-cell bold">{{ formatNum(calcCarryingAmount(row)) }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row, $index }">
          <el-button
            type="danger"
            size="small"
            text
            :disabled="!row.id"
            @click="onDeleteRow(row, $index)"
          >删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <div class="total-row" v-if="filteredRows.length">
      <span class="total-label">合计</span>
      <span class="total-cell">{{ formatNum(totalAcquisitionCost) }}</span>
      <span class="total-cell">{{ formatNum(totalNetAssetsFv) }}</span>
      <span class="total-cell" :class="{ negative: totalGoodwill < 0 }">{{ formatNum(totalGoodwill) }}</span>
      <span class="total-cell">{{ formatNum(totalCurrentImpairment) }}</span>
      <span class="total-cell bold">{{ formatNum(totalCarryingAmount) }}</span>
      <span class="total-cell"></span>
    </div>

    <!-- 底部操作栏 -->
    <div class="panel-footer">
      <el-button type="primary" @click="onSaveAll" :loading="saving">
        <el-icon><Check /></el-icon> 保存全部
      </el-button>
      <el-button @click="onRecalc" :loading="recalcLoading">
        <el-icon><Refresh /></el-icon> 重新计算商誉
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Check, Refresh } from '@element-plus/icons-vue'
import {
  getGoodwillRows,
  createGoodwillRow,
  updateGoodwillRow,
  deleteGoodwillRow,
  getCompanyTree,
  type GoodwillRow,
  type CompanyTreeNode,
} from '@/services/consolidationApi'

// ─── Types ───────────────────────────────────────────────────────────────────
interface LocalGoodwillRow {
  id?: string
  project_id: string
  year: number
  subsidiary_code: string
  acquisition_cost: number
  identifiable_net_assets_fv: number
  parent_share_ratio: number
  goodwill_amount: number
  accumulated_impairment: number
  current_year_impairment: number
  carrying_amount: number
  is_negative_goodwill: boolean
  _dirty?: boolean
  _readonly?: boolean
}

// ─── Props ────────────────────────────────────────────────────────────────────
const props = defineProps<{ projectId: string }>()

// ─── State ────────────────────────────────────────────────────────────────────
const loading = ref(false)
const saving = ref(false)
const recalcLoading = ref(false)
const rows = ref<LocalGoodwillRow[]>([])
const filterCompany = ref('')
const companyOptions = ref<Array<{ code: string; name: string }>>([])

// ─── Computed ────────────────────────────────────────────────────────────────
const filteredRows = computed(() => {
  if (!filterCompany.value) return rows.value
  return rows.value.filter(r => r.subsidiary_code === filterCompany.value)
})

const totalAcquisitionCost = computed(() =>
  filteredRows.value.reduce((s, r) => s + (r.acquisition_cost || 0), 0)
)
const totalNetAssetsFv = computed(() =>
  filteredRows.value.reduce((s, r) => s + (r.identifiable_net_assets_fv || 0), 0)
)
const totalGoodwill = computed(() =>
  filteredRows.value.reduce((s, r) => s + calcGoodwill(r), 0)
)
const totalCurrentImpairment = computed(() =>
  filteredRows.value.reduce((s, r) => s + (r.current_year_impairment || 0), 0)
)
const totalCarryingAmount = computed(() =>
  filteredRows.value.reduce((s, r) => s + calcCarryingAmount(r), 0)
)

// ─── Helpers ─────────────────────────────────────────────────────────────────
function calcGoodwill(row: LocalGoodwillRow): number {
  const cost = row.acquisition_cost || 0
  const netAssets = row.identifiable_net_assets_fv || 0
  const ratio = row.parent_share_ratio || 1
  return cost - netAssets * ratio
}

function calcCarryingAmount(row: LocalGoodwillRow): number {
  const goodwill = calcGoodwill(row)
  const accumImpairment = row.accumulated_impairment || 0
  const currentImpairment = row.current_year_impairment || 0
  return Math.max(goodwill - accumImpairment - currentImpairment, 0)
}

function formatNum(v: number): string {
  if (isNaN(v) || v === 0) return '—'
  const abs = Math.abs(v)
  const formatted = abs.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return v < 0 ? `(${formatted})` : formatted
}

// ─── Load Data ───────────────────────────────────────────────────────────────
async function loadCompanyOptions() {
  try {
    const year = new Date().getFullYear()
    const tree = await getCompanyTree(props.projectId, year)
    // Flatten tree into options (non-parent companies)
    const flatten = (nodes: CompanyTreeNode[]): Array<{ code: string; name: string }> => {
      return nodes.map(n => ({ code: n.companyCode, name: n.companyName }))
    }
    companyOptions.value = flatten(tree)
  } catch {
    companyOptions.value = []
  }
}

async function loadRows() {
  loading.value = true
  try {
    const year = new Date().getFullYear()
    const data = await getGoodwillRows(props.projectId, year)
    rows.value = data.map((r: GoodwillRow) => mapToLocal(r))
    if (rows.value.length === 0) {
      // Add one empty row by default
      rows.value.push(makeEmptyRow())
    }
  } catch {
    rows.value = [makeEmptyRow()]
  } finally {
    loading.value = false
  }
}

function makeEmptyRow(): LocalGoodwillRow {
  return {
    project_id: props.projectId,
    year: new Date().getFullYear(),
    subsidiary_code: '',
    acquisition_cost: 0,
    identifiable_net_assets_fv: 0,
    parent_share_ratio: 1,
    goodwill_amount: 0,
    accumulated_impairment: 0,
    current_year_impairment: 0,
    carrying_amount: 0,
    is_negative_goodwill: false,
    _dirty: false,
    _readonly: false,
  }
}

function mapToLocal(r: GoodwillRow): LocalGoodwillRow {
  return {
    id: r.id,
    project_id: r.project_id,
    year: r.year,
    subsidiary_code: r.cash_generating_unit || '', // legacy field mapping
    acquisition_cost: Number(r.initial_amount) || 0,
    identifiable_net_assets_fv: 0,
    parent_share_ratio: 1,
    goodwill_amount: Number(r.net_amount) || 0,
    accumulated_impairment: Number(r.cumulative_impairment) || 0,
    current_year_impairment: 0,
    carrying_amount: Number(r.net_amount) || 0,
    is_negative_goodwill: false,
    _dirty: false,
    _readonly: false,
  }
}

// ─── Actions ─────────────────────────────────────────────────────────────────
function onAddRow() {
  rows.value.push(makeEmptyRow())
}

function onCellChange(_index: number) {
  // Mark row as dirty for save
}

async function onDeleteRow(row: LocalGoodwillRow, index: number) {
  if (row.id) {
    try {
      await deleteGoodwillRow(row.id, props.projectId)
      rows.value.splice(index, 1)
      ElMessage.success('删除成功')
    } catch {
      ElMessage.error('删除失败')
    }
  } else {
    rows.value.splice(index, 1)
    if (rows.value.length === 0) rows.value.push(makeEmptyRow())
  }
}

async function onSaveAll() {
  saving.value = true
  try {
    for (const row of rows.value) {
      const payload = {
        project_id: props.projectId,
        year: row.year,
        cash_generating_unit: row.subsidiary_code,
        initial_amount: String(row.acquisition_cost),
        cumulative_impairment: String(row.accumulated_impairment + row.current_year_impairment),
        net_amount: String(calcCarryingAmount(row)),
        recoverable_amount: '0',
        impairment_test_date: '',
        notes: '',
      }
      if (row.id) {
        await updateGoodwillRow(row.id, props.projectId, payload)
      } else if (row.subsidiary_code || row.acquisition_cost > 0) {
        await createGoodwillRow(props.projectId, payload)
      }
    }
    ElMessage.success('保存成功')
    await loadRows()
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

function onRecalc() {
  recalcLoading.value = true
  setTimeout(() => {
    rows.value = rows.value.map(r => ({ ...r, _dirty: true }))
    recalcLoading.value = false
    ElMessage.success('商誉已重新计算')
  }, 500)
}

// ─── Init ────────────────────────────────────────────────────────────────────
onMounted(() => {
  loadCompanyOptions()
  loadRows()
})
</script>

<style scoped>
.gt-goodwill-panel {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-3);
}

.panel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gt-space-4);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
}

.toolbar-label {
  font-size: 14px;
  color: var(--gt-color-primary-dark);
  font-weight: 500;
}

.goodwill-table :deep(.el-input-number) {
  --el-input-number-controls-height: 28px;
}

.computed-cell {
  font-family: var(--gt-font-family-en);
  font-size: 13px;
  color: var(--gt-color-primary);
}

.computed-cell.bold {
  font-weight: 600;
}

.computed-cell.negative {
  color: var(--gt-color-coral);
}

.total-row {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: var(--gt-color-primary);
  border-radius: var(--gt-radius-sm);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  gap: 4px;
}

.total-label {
  width: 180px;
  flex-shrink: 0;
}

.total-cell {
  width: 160px;
  text-align: right;
  padding-right: 4px;
  font-family: var(--gt-font-family-en);
}

.total-cell:nth-child(3) { width: 200px; }
.total-cell:nth-child(6) { width: 160px; }
.total-cell:last-child { width: 100px; text-align: center; }

.total-cell.negative {
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
