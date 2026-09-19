<template>
  <el-card shadow="never" class="amort-card">
    <template #header>
      <div class="section-title">
        <span>{{ title }}</span>
        <div class="title-actions">
          <el-tag v-if="schedule.rows.length" size="small" type="info">
            共 {{ schedule.rows.length }} 期
          </el-tag>
          <el-tag
            v-if="schedule.rows.length && schedule.validation.isValid"
            size="small"
            type="success"
          >
            末期归零 ✓
          </el-tag>
          <el-tag
            v-else-if="schedule.rows.length"
            size="small"
            type="danger"
          >
            尾差 {{ fmtAmt(schedule.validation.tailDiff) }}
          </el-tag>
        </div>
      </div>
    </template>

    <el-alert
      v-if="!schedule.rows.length"
      type="info"
      :closable="false"
      show-icon
      title="请填写租赁负债初始确认、折现率、租赁期与每期租金后自动生成摊销表（实际利率法，与 H9-4 同源引擎）。"
    />

    <el-table
      v-else
      :data="schedule.rows"
      border
      stripe
      size="small"
      class="amort-table"
      max-height="420"
      show-summary
      :summary-method="getSummary"
      :row-class-name="rowClassName"
    >
      <el-table-column prop="period" :label="periodLabel" width="70" align="center" />
      <el-table-column prop="beginBalance" label="期初余额" min-width="120" align="right">
        <template #default="{ row }">{{ fmtAmt(row.beginBalance) }}</template>
      </el-table-column>
      <el-table-column prop="payment" label="本期付款" min-width="120" align="right">
        <template #default="{ row }">{{ fmtAmt(row.payment) }}</template>
      </el-table-column>
      <el-table-column prop="interest" label="利息费用" min-width="120" align="right">
        <template #default="{ row }">{{ fmtAmt(row.interest) }}</template>
      </el-table-column>
      <el-table-column prop="principal" label="本金偿还" min-width="120" align="right">
        <template #default="{ row }">{{ fmtAmt(row.principal) }}</template>
      </el-table-column>
      <el-table-column prop="endBalance" label="期末余额" min-width="120" align="right">
        <template #default="{ row }">{{ fmtAmt(row.endBalance) }}</template>
      </el-table-column>
    </el-table>

    <p class="amort-hint">
      公式：利息=期初×{{ rateHint }}；本金=付款−利息；期末=期初−本金；末年/月调整付款使期末归零（±1 元容差）。
      OnlyOffice 源表仍可作精编兜底。
    </p>
  </el-card>
</template>

<script setup lang="ts">
/**
 * H8-6 HTML 摊销表面板（按年/按月共用）
 */
import type { buildH86AmortSchedule } from '../../composables/useH8Measurement'

type Schedule = ReturnType<typeof buildH86AmortSchedule>

const props = defineProps<{
  schedule: Schedule
  mode: 'annual' | 'monthly'
}>()

const title = props.mode === 'annual'
  ? '租赁负债摊销表（按年 · HTML）'
  : '租赁负债摊销表（按月 · HTML）'
const periodLabel = props.mode === 'annual' ? '年次' : '期数'
const rateHint = props.mode === 'annual' ? '年利率' : '月利率(=年利率/12)'

function fmtAmt(v: number): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClassName({ rowIndex }: { rowIndex: number }) {
  const last = props.schedule.rows.length - 1
  return rowIndex === last ? 'last-period-row' : ''
}

function getSummary({ columns, data }: { columns: any[]; data: any[] }) {
  const sums: string[] = []
  columns.forEach((col, i) => {
    if (i === 0) {
      sums[i] = '合计'
      return
    }
    const prop = col.property
    if (prop === 'payment' || prop === 'interest' || prop === 'principal') {
      const t = data.reduce((s, r) => s + (Number(r[prop]) || 0), 0)
      sums[i] = fmtAmt(t)
    } else {
      sums[i] = ''
    }
  })
  return sums
}
</script>

<style scoped>
.amort-card { margin-bottom: 12px; }
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-weight: 600;
}
.title-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.amort-table { width: 100%; }
.amort-table :deep(.last-period-row) { background: var(--el-color-success-light-9); }
.amort-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
</style>
