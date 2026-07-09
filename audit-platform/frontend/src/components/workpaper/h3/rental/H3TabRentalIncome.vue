<template>
  <div class="h3-tab-rental-income">
    <!-- 区域1：租赁合同汇总 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(1) 租赁合同汇总</span>
          <span class="action-btns">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="addContractRow">+ 新增</el-button>
            <el-button size="small" @click="generateAI('H3-14-contract')">AI</el-button>
          </span>
        </div>
      </template>
      <el-table :data="contractRows" border size="small" class="audit-table">
        <el-table-column prop="assetName" label="资产" min-width="120">
          <template #default="{ row, $index }">
            <el-input v-model="row.assetName" size="small" :disabled="isReadonly" @change="onContractChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="tenant" label="租户" min-width="100">
          <template #default="{ row, $index }">
            <el-input v-model="row.tenant" size="small" :disabled="isReadonly" @change="onContractChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="leaseStart" label="合同起始" width="100">
          <template #default="{ row, $index }">
            <el-input v-model="row.leaseStart" size="small" :disabled="isReadonly" @change="onContractChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="leaseEnd" label="合同终止" width="100">
          <template #default="{ row, $index }">
            <el-input v-model="row.leaseEnd" size="small" :disabled="isReadonly" @change="onContractChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column prop="monthlyRent" label="月租" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.monthlyRent" size="small" :disabled="isReadonly" @change="onContractChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column label="年租金" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="月租×12">{{ fmtNum(row.monthlyRent * 12) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="area" label="面积(㎡)" width="80" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.area" size="small" :disabled="isReadonly" @change="onContractChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column label="每㎡月租" width="80" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="月租/面积">{{ row.area ? (row.monthlyRent / row.area).toFixed(1) : '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 区域2：月度租金收入明细 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(2) 月度租金收入明细（12个月逐月）</span>
          <el-button size="small" @click="generateAI('H3-14-monthly')">AI</el-button>
        </div>
      </template>
      <el-table :data="contractRows" border size="small" class="audit-table" :row-class-name="getMonthlyRowClass">
        <el-table-column prop="assetName" label="资产" min-width="100" fixed />
        <el-table-column v-for="m in 12" :key="m" :label="`${m}月`" width="75" align="right">
          <template #default="{ row, $index }">
            <el-input v-model.number="row.monthlyActual[m-1]" size="small" :disabled="isReadonly" @change="onMonthlyChange($index, row)" />
          </template>
        </el-table-column>
        <el-table-column label="累计" min-width="90" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtNum(sumMonthly(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异率" width="80" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'text-warn': Math.abs(calcMonthlyDiffRate(row)) > 5 }">
              {{ calcMonthlyDiffRate(row).toFixed(1) }}%
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 区域3：到期管理 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>(3) 到期管理</span>
          <el-button size="small" @click="generateAI('H3-14-expiry')">AI</el-button>
        </div>
      </template>
      <el-table :data="contractRows" border size="small" class="audit-table" :row-class-name="getExpiryRowClass">
        <el-table-column prop="assetName" label="资产" min-width="120" />
        <el-table-column prop="tenant" label="租户" min-width="100" />
        <el-table-column prop="leaseEnd" label="合同到期日" width="100" />
        <el-table-column label="到期月数" width="80" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" :class="{ 'text-expiry': row.monthsToExpiry <= 3 }">
              {{ row.monthsToExpiry ?? '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="renewalStatus" label="续租状态" width="100">
          <template #default="{ row, $index }">
            <el-select v-model="row.renewalStatus" size="small" :disabled="isReadonly" @change="onContractChange($index, row)">
              <el-option label="已续租" value="已续租" />
              <el-option label="洽谈中" value="洽谈中" />
              <el-option label="未续租" value="未续租" />
              <el-option label="空置" value="空置" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="vacancyForecast" label="空置预测" min-width="100">
          <template #default="{ row, $index }">
            <el-input v-model="row.vacancyForecast" size="small" :disabled="isReadonly" @change="onContractChange($index, row)" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 导入导出 -->
    <div class="toolbar">
      <el-dropdown size="small">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item>导出模板</el-dropdown-item>
            <el-dropdown-item>导出数据</el-dropdown-item>
            <el-dropdown-item>导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-title">
          <span>审计说明 / 结论</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-14')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-14')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请输入审计说明..." :disabled="isReadonly" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabRentalIncome.vue — H3-14 租金收入测算
 * 三区域(合同/月度12列/到期)+空置高亮+到期预警+AI+💬复核
 */
import { ref, computed, inject, toRef } from 'vue'
import { useH3RentalIncome } from '../../composables/useH3RentalIncome'
import { useH3FormData } from '../../composables/useH3FormData'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  measurementModel?: 'cost' | 'fair_value'
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('cost') as any,
})

const {
  contractRows, addContractRow, updateContractRow, updateMonthlyData,
} = useH3RentalIncome({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

const auditConclusion = ref(getValue('H3-14-conclusion') ?? '')

function onContractChange(index: number, row: any) {
  updateContractRow(index, row)
  publishRentalIncomeCalculated()
}
function onMonthlyChange(index: number, row: any) {
  updateMonthlyData(index, row)
  publishRentalIncomeCalculated()
}

/** EventBus: publish 'h3:rental-income-calculated' */
function publishRentalIncomeCalculated() {
  const totalAnnualRent = contractRows.value.reduce((sum: number, r: any) => {
    const monthlyRent = r.monthlyRent || 0
    const months = r.rentMonths || 12
    const vacancyRate = r.vacancyRate || 0
    return sum + monthlyRent * months * (1 - vacancyRate)
  }, 0)
  http.post(`/api/projects/${props.projectId}/events/publish`, {
    event_type: 'h3:rental-income-calculated',
    payload: { wp_id: props.wpId, totalAnnualRent },
  }).catch(() => { /* best effort */ })
}

function sumMonthly(row: any): number {
  return (row.monthlyActual || []).reduce((s: number, v: number) => s + (v || 0), 0)
}

function calcMonthlyDiffRate(row: any): number {
  const expected = row.monthlyRent * 12
  const actual = sumMonthly(row)
  if (!expected) return 0
  return ((actual - expected) / expected) * 100
}

function getMonthlyRowClass({ row }: { row: any }): string {
  if (Math.abs(calcMonthlyDiffRate(row)) > 5) return 'row-warn'
  return ''
}

function getExpiryRowClass({ row }: { row: any }): string {
  if (row.monthsToExpiry != null && row.monthsToExpiry <= 3) return 'row-expiry'
  if (row.renewalStatus === '空置') return 'row-vacant'
  return ''
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function generateAI(section: string) {
  window.dispatchEvent(new CustomEvent('ai:generate', { detail: { section, wpId: props.wpId } }))
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-rental-income { padding: 16px; font-size: 13px; }
.section-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.action-btns { display: flex; gap: 4px; }
.audit-table { font-size: 13px; }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.audit-table :deep(.row-warn) { background-color: #fef9e7 !important; }
.audit-table :deep(.row-expiry) { background-color: #fff3e0 !important; }
.audit-table :deep(.row-vacant) { background-color: #fef9e7 !important; }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.text-warn { color: var(--el-color-warning); }
.text-expiry { color: #e65100; font-weight: 600; }
.toolbar { margin-bottom: 12px; }
.conclusion-card { margin-top: 16px; }
</style>
