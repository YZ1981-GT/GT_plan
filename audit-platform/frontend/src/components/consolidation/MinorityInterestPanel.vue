<template>
  <div class="minority-interest-panel">
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
      </div>
    </div>

    <!-- Tab页切换：权益 | 损益 | 变动表 -->
    <el-tabs v-model="activeTab" class="mi-tabs">
      <!-- 权益Tab -->
      <el-tab-pane label="权益" name="equity">
        <div class="tab-toolbar">
          <el-button type="primary" plain size="small" @click="onAddEquity">
            <el-icon><Plus /></el-icon> 添加行
          </el-button>
          <el-button size="small" @click="onBatchRecalcEquity">
            <el-icon><Refresh /></el-icon> 重新计算少数股东权益
          </el-button>
        </div>
        <el-table
          :data="filteredEquityRows"
          border
          stripe
          size="small"
          v-loading="loading"
          :header-cell-style="{ background: 'var(--gt-color-primary)', color: '#fff', fontWeight: '600' }"
          max-height="340"
          row-key="id"
          class="mi-table"
        >
          <el-table-column label="子公司" width="180">
            <template #default="{ row, $index }">
              <el-select
                v-model="row.subsidiary_code"
                placeholder="选择子公司"
                style="width: 100%"
                :disabled="!!row.id"
                @change="onEquityChange($index)"
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
          <el-table-column label="净资产" align="right" width="160">
            <template #default="{ row, $index }">
              <el-input-number
                v-model="row.subsidiary_net_assets"
                :precision="2"
                :controls="false"
                style="width: 100%; text-align: right"
                @change="onEquityChange($index)"
              />
            </template>
          </el-table-column>
          <el-table-column label="持股比例(%)" align="right" width="130">
            <template #default="{ row, $index }">
              <el-input-number
                v-model="row.minority_share_ratio"
                :min="0"
                :max="100"
                :precision="2"
                :controls="false"
                style="width: 100%; text-align: right"
                @change="onEquityChange($index)"
              />
            </template>
          </el-table-column>
          <el-table-column label="母公司享权益" align="right" width="160">
            <template #default="{ row }">
              <span class="computed-cell">{{ formatNum(calcParentEquity(row)) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="少数股东权益" align="right" width="160">
            <template #default="{ row }">
              <span class="computed-cell primary">{{ formatNum(calcMinorityEquity(row)) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row, $index }">
              <el-button type="danger" size="small" text @click="onDeleteEquity(row, $index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 合计行 -->
        <div class="total-row" v-if="filteredEquityRows.length">
          <span class="total-label">合计</span>
          <span class="total-cell">{{ formatNum(totalEquityNetAssets) }}</span>
          <span class="total-cell">—</span>
          <span class="total-cell">{{ formatNum(totalParentEquity) }}</span>
          <span class="total-cell primary">{{ formatNum(totalMinorityEquity) }}</span>
          <span class="total-cell"></span>
        </div>
      </el-tab-pane>

      <!-- 损益Tab -->
      <el-tab-pane label="损益" name="profit">
        <div class="tab-toolbar">
          <el-button type="primary" plain size="small" @click="onAddProfit">
            <el-icon><Plus /></el-icon> 添加行
          </el-button>
          <el-button size="small" @click="onBatchRecalcProfit">
            <el-icon><Refresh /></el-icon> 重新计算少数股东损益
          </el-button>
        </div>
        <el-table
          :data="filteredProfitRows"
          border
          stripe
          size="small"
          v-loading="loading"
          :header-cell-style="{ background: 'var(--gt-color-primary)', color: '#fff', fontWeight: '600' }"
          max-height="340"
          row-key="id"
          class="mi-table"
        >
          <el-table-column label="子公司" width="180">
            <template #default="{ row, $index }">
              <el-select
                v-model="row.subsidiary_code"
                placeholder="选择子公司"
                style="width: 100%"
                :disabled="!!row.id"
                @change="onProfitChange($index)"
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
          <el-table-column label="净利润" align="right" width="160">
            <template #default="{ row, $index }">
              <el-input-number
                v-model="row.subsidiary_net_profit"
                :precision="2"
                :controls="false"
                style="width: 100%; text-align: right"
                @change="onProfitChange($index)"
              />
            </template>
          </el-table-column>
          <el-table-column label="持股比例(%)" align="right" width="130">
            <template #default="{ row, $index }">
              <el-input-number
                v-model="row.minority_share_ratio"
                :min="0"
                :max="100"
                :precision="2"
                :controls="false"
                style="width: 100%; text-align: right"
                @change="onProfitChange($index)"
              />
            </template>
          </el-table-column>
          <el-table-column label="母公司享损益" align="right" width="160">
            <template #default="{ row }">
              <span class="computed-cell">{{ formatNum(calcParentProfit(row)) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="少数股东损益" align="right" width="160">
            <template #default="{ row }">
              <span class="computed-cell primary">{{ formatNum(calcMinorityProfit(row)) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row, $index }">
              <el-button type="danger" size="small" text @click="onDeleteProfit(row, $index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="total-row" v-if="filteredProfitRows.length">
          <span class="total-label">合计</span>
          <span class="total-cell">{{ formatNum(totalProfit) }}</span>
          <span class="total-cell">—</span>
          <span class="total-cell">{{ formatNum(totalParentProfit) }}</span>
          <span class="total-cell primary">{{ formatNum(totalMinorityProfit) }}</span>
          <span class="total-cell"></span>
        </div>
      </el-tab-pane>

      <!-- 变动表Tab -->
      <el-tab-pane label="变动表" name="change">
        <div class="tab-toolbar">
          <el-button type="primary" plain size="small" @click="onAddChange">
            <el-icon><Plus /></el-icon> 添加行
          </el-button>
        </div>
        <el-table
          :data="filteredChangeRows"
          border
          stripe
          size="small"
          v-loading="loading"
          :header-cell-style="{ background: 'var(--gt-color-primary)', color: '#fff', fontWeight: '600' }"
          max-height="340"
          row-key="id"
          class="mi-table"
        >
          <el-table-column label="子公司" width="180">
            <template #default="{ row, $index }">
              <el-select
                v-model="row.subsidiary_code"
                placeholder="选择子公司"
                style="width: 100%"
                :disabled="!!row.id"
                @change="onChangeRow($index)"
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
          <el-table-column label="期初余额" align="right" width="160">
            <template #default="{ row, $index }">
              <el-input-number
                v-model="row.beginning_balance"
                :precision="2"
                :controls="false"
                style="width: 100%; text-align: right"
                @change="onChangeRow($index)"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期增加" align="right" width="160">
            <template #default="{ row, $index }">
              <el-input-number
                v-model="row.increase"
                :precision="2"
                :controls="false"
                style="width: 100%; text-align: right"
                @change="onChangeRow($index)"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" align="right" width="160">
            <template #default="{ row, $index }">
              <el-input-number
                v-model="row.decrease"
                :precision="2"
                :controls="false"
                style="width: 100%; text-align: right"
                @change="onChangeRow($index)"
              />
            </template>
          </el-table-column>
          <el-table-column label="期末余额" align="right" width="160">
            <template #default="{ row }">
              <span class="computed-cell primary bold">{{ formatNum(calcEndingBalance(row)) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row, $index }">
              <el-button type="danger" size="small" text @click="onDeleteChange(row, $index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="total-row" v-if="filteredChangeRows.length">
          <span class="total-label">合计</span>
          <span class="total-cell">{{ formatNum(totalBeginning) }}</span>
          <span class="total-cell">{{ formatNum(totalIncrease) }}</span>
          <span class="total-cell">{{ formatNum(totalDecrease) }}</span>
          <span class="total-cell primary bold">{{ formatNum(totalEnding) }}</span>
          <span class="total-cell"></span>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 底部操作栏 -->
    <div class="panel-footer">
      <el-button type="primary" @click="onSaveAll" :loading="saving">
        <el-icon><Check /></el-icon> 保存全部
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Check, Refresh } from '@element-plus/icons-vue'
import {
  getMinorityInterestRows,
  createMinorityInterestRow,
  updateMinorityInterestRow,
  getCompanyTree,
  type CompanyTreeNode,
} from '@/services/consolidationApi'

// ─── Types ───────────────────────────────────────────────────────────────────
interface LocalEquityRow {
  id?: string
  project_id: string
  year: number
  subsidiary_code: string
  subsidiary_net_assets: number
  minority_share_ratio: number
  is_excess_loss: boolean
}

interface LocalProfitRow {
  id?: string
  project_id: string
  year: number
  subsidiary_code: string
  subsidiary_net_profit: number
  minority_share_ratio: number
}

interface LocalChangeRow {
  id?: string
  project_id: string
  year: number
  subsidiary_code: string
  beginning_balance: number
  increase: number
  decrease: number
}

// ─── Props ────────────────────────────────────────────────────────────────────
const props = defineProps<{ projectId: string; period?: number }>()

// ─── State ────────────────────────────────────────────────────────────────────
const loading = ref(false)
const saving = ref(false)
const activeTab = ref('equity')
const filterCompany = ref('')
const companyOptions = ref<Array<{ code: string; name: string }>>([])

// Three tab data arrays
const equityRows = ref<LocalEquityRow[]>([])
const profitRows = ref<LocalProfitRow[]>([])
const changeRows = ref<LocalChangeRow[]>([])

// ─── Computed ────────────────────────────────────────────────────────────────
const filteredEquityRows = computed(() =>
  filterCompany.value ? equityRows.value.filter(r => r.subsidiary_code === filterCompany.value) : equityRows.value
)
const filteredProfitRows = computed(() =>
  filterCompany.value ? profitRows.value.filter(r => r.subsidiary_code === filterCompany.value) : profitRows.value
)
const filteredChangeRows = computed(() =>
  filterCompany.value ? changeRows.value.filter(r => r.subsidiary_code === filterCompany.value) : changeRows.value
)

// Equity totals
const totalEquityNetAssets = computed(() => filteredEquityRows.value.reduce((s, r) => s + (r.subsidiary_net_assets || 0), 0))
const totalParentEquity = computed(() => filteredEquityRows.value.reduce((s, r) => s + calcParentEquity(r), 0))
const totalMinorityEquity = computed(() => filteredEquityRows.value.reduce((s, r) => s + calcMinorityEquity(r), 0))

// Profit totals
const totalProfit = computed(() => filteredProfitRows.value.reduce((s, r) => s + (r.subsidiary_net_profit || 0), 0))
const totalParentProfit = computed(() => filteredProfitRows.value.reduce((s, r) => s + calcParentProfit(r), 0))
const totalMinorityProfit = computed(() => filteredProfitRows.value.reduce((s, r) => s + calcMinorityProfit(r), 0))

// Change totals
const totalBeginning = computed(() => filteredChangeRows.value.reduce((s, r) => s + (r.beginning_balance || 0), 0))
const totalIncrease = computed(() => filteredChangeRows.value.reduce((s, r) => s + (r.increase || 0), 0))
const totalDecrease = computed(() => filteredChangeRows.value.reduce((s, r) => s + (r.decrease || 0), 0))
const totalEnding = computed(() => filteredChangeRows.value.reduce((s, r) => s + calcEndingBalance(r), 0))

// ─── Helpers ─────────────────────────────────────────────────────────────────
function calcParentEquity(row: LocalEquityRow): number {
  return (row.subsidiary_net_assets || 0) * (1 - (row.minority_share_ratio || 0) / 100)
}
function calcMinorityEquity(row: LocalEquityRow): number {
  return (row.subsidiary_net_assets || 0) * ((row.minority_share_ratio || 0) / 100)
}
function calcParentProfit(row: LocalProfitRow): number {
  return (row.subsidiary_net_profit || 0) * (1 - (row.minority_share_ratio || 0) / 100)
}
function calcMinorityProfit(row: LocalProfitRow): number {
  return (row.subsidiary_net_profit || 0) * ((row.minority_share_ratio || 0) / 100)
}
function calcEndingBalance(row: LocalChangeRow): number {
  return (row.beginning_balance || 0) + (row.increase || 0) - (row.decrease || 0)
}

function formatNum(v: number): string {
  if (isNaN(v) || v === 0) return '—'
  const abs = Math.abs(v)
  const formatted = abs.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return v < 0 ? `(${formatted})` : formatted
}

function makeEmptyEquity(): LocalEquityRow {
  return { project_id: props.projectId, year: props.period || new Date().getFullYear(), subsidiary_code: '', subsidiary_net_assets: 0, minority_share_ratio: 0, is_excess_loss: false }
}
function makeEmptyProfit(): LocalProfitRow {
  return { project_id: props.projectId, year: props.period || new Date().getFullYear(), subsidiary_code: '', subsidiary_net_profit: 0, minority_share_ratio: 0 }
}
function makeEmptyChange(): LocalChangeRow {
  return { project_id: props.projectId, year: props.period || new Date().getFullYear(), subsidiary_code: '', beginning_balance: 0, increase: 0, decrease: 0 }
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
    const data = await getMinorityInterestRows(props.projectId, year)
    // Map API rows to local
    equityRows.value = data.map(r => ({
      id: r.id,
      project_id: r.project_id,
      year: r.year,
      subsidiary_code: r.subsidiary_name || '',
      subsidiary_net_assets: Number(r.total_equity) || 0,
      minority_share_ratio: Number(r.minority_percentage) || 0,
      is_excess_loss: false,
    }))
    profitRows.value = data.map(r => ({
      id: r.id,
      project_id: r.project_id,
      year: r.year,
      subsidiary_code: r.subsidiary_name || '',
      subsidiary_net_profit: 0,
      minority_share_ratio: Number(r.minority_percentage) || 0,
    }))
    changeRows.value = data.map(r => ({
      id: r.id,
      project_id: r.project_id,
      year: r.year,
      subsidiary_code: r.subsidiary_name || '',
      beginning_balance: 0,
      increase: 0,
      decrease: 0,
    }))
    if (equityRows.value.length === 0) equityRows.value.push(makeEmptyEquity())
    if (profitRows.value.length === 0) profitRows.value.push(makeEmptyProfit())
    if (changeRows.value.length === 0) changeRows.value.push(makeEmptyChange())
  } catch {
    equityRows.value = [makeEmptyEquity()]
    profitRows.value = [makeEmptyProfit()]
    changeRows.value = [makeEmptyChange()]
  } finally {
    loading.value = false
  }
}

// ─── Actions ─────────────────────────────────────────────────────────────────
function onAddEquity() { equityRows.value.push(makeEmptyEquity()) }
function onAddProfit() { profitRows.value.push(makeEmptyProfit()) }
function onAddChange() { changeRows.value.push(makeEmptyChange()) }

function onEquityChange(_i: number) {}
function onProfitChange(_i: number) {}
function onChangeRow(_i: number) {}

async function onDeleteEquity(row: LocalEquityRow, index: number) {
  if (row.id) {
    try {
      await (window as any).$http.delete(`/api/consolidation/minority-interest/${row.id}`, { params: { project_id: props.projectId } })
    } catch { /* ignore */ }
  }
  equityRows.value.splice(index, 1)
  if (!equityRows.value.length) equityRows.value.push(makeEmptyEquity())
}
async function onDeleteProfit(row: LocalProfitRow, index: number) {
  profitRows.value.splice(index, 1)
  if (!profitRows.value.length) profitRows.value.push(makeEmptyProfit())
}
async function onDeleteChange(row: LocalChangeRow, index: number) {
  changeRows.value.splice(index, 1)
  if (!changeRows.value.length) changeRows.value.push(makeEmptyChange())
}

function onBatchRecalcEquity() {
  equityRows.value = equityRows.value.map(r => ({ ...r }))
  ElMessage.success('少数股东权益已重新计算')
}
function onBatchRecalcProfit() {
  profitRows.value = profitRows.value.map(r => ({ ...r }))
  ElMessage.success('少数股东损益已重新计算')
}

async function onSaveAll() {
  saving.value = true
  try {
    const year = props.period || new Date().getFullYear()
    for (const row of equityRows.value) {
      if (row.id) {
        await updateMinorityInterestRow(row.id, props.projectId, {
          project_id: props.projectId,
          year: row.year,
          subsidiary_name: row.subsidiary_code,
          ownership_percentage: String(100 - row.minority_share_ratio),
          minority_percentage: String(row.minority_share_ratio),
          total_equity: String(row.subsidiary_net_assets),
          minority_interest_amount: String(calcMinorityEquity(row)),
          changes: '',
          notes: '',
        })
      } else if (row.subsidiary_code || row.subsidiary_net_assets > 0) {
        await createMinorityInterestRow(props.projectId, {
          project_id: props.projectId,
          year,
          subsidiary_name: row.subsidiary_code,
          ownership_percentage: String(100 - row.minority_share_ratio),
          minority_percentage: String(row.minority_share_ratio),
          total_equity: String(row.subsidiary_net_assets),
          minority_interest_amount: String(calcMinorityEquity(row)),
          changes: '',
          notes: '',
        })
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

// ─── Init ────────────────────────────────────────────────────────────────────
onMounted(() => {
  loadCompanyOptions()
  loadRows()
})
</script>

<style scoped>
.minority-interest-panel {
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

.tab-toolbar {
  display: flex;
  gap: var(--gt-space-2);
  margin-bottom: var(--gt-space-2);
}

.mi-table :deep(.el-input-number) {
  --el-input-number-controls-height: 28px;
}

.computed-cell {
  font-family: var(--gt-font-family-en);
  font-size: 13px;
  color: var(--gt-color-primary);
}

.computed-cell.primary {
  color: var(--gt-color-teal);
  font-weight: 600;
}

.computed-cell.bold {
  font-weight: 700;
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
  margin-top: var(--gt-space-2);
}

.total-label {
  width: 180px;
  flex-shrink: 0;
}

.total-cell {
  width: 160px;
  text-align: right;
  font-family: var(--gt-font-family-en);
}

.total-cell:nth-child(3) { width: 130px; }
.total-cell:last-child { width: 100px; text-align: center; }

.total-cell.primary {
  color: #7ddfff;
  font-weight: 700;
}

.panel-footer {
  display: flex;
  gap: var(--gt-space-3);
  justify-content: flex-start;
  padding-top: var(--gt-space-2);
  border-top: 1px solid var(--gt-color-primary-light);
}
</style>
