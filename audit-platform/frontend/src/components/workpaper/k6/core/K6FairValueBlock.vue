<template>
  <el-card shadow="never" class="k6-block">
    <template #header>
      <div class="block-head">
        <span class="block-title">{{ title }}</span>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="emit('add')">
          + 项目
        </el-button>
      </div>
    </template>
    <div class="block-hint">{{ hint }}</div>
    <el-table :data="rows" border size="small" style="width:100%" show-summary :summary-method="summary">
      <el-table-column prop="project" label="项目" min-width="180" fixed>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.project"
            size="small"
            placeholder="项目名称"
            @input="(v: string) => emit('update', row.id, 'project', v)"
          />
          <span v-else>{{ row.project || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="endBook" label="期末账面价值" width="140" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!isReadonly" :model-value="row.endBook" @change="(v?: number) => emit('update', row.id, 'endBook', v ?? 0)" />
          <span v-else>{{ fmt(row.endBook) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="endFairValue" label="期末公允价值" width="140" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!isReadonly" :model-value="row.endFairValue" @change="(v?: number) => emit('update', row.id, 'endFairValue', v ?? 0)" />
          <span v-else>{{ fmt(row.endFairValue) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="disposalFee" :label="feeLabel" width="140" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!isReadonly" :model-value="row.disposalFee" @change="(v?: number) => emit('update', row.id, 'disposalFee', v ?? 0)" />
          <span v-else>{{ fmt(row.disposalFee) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="计量校验" width="110" align="center">
        <template #default="{ row }">
          <el-tag v-if="hasData(row)" :type="measureOk(row) ? 'success' : 'danger'" size="small" effect="light">
            {{ measureOk(row) ? '合规' : '超上限' }}
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="timetable" label="时间安排" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.timetable"
            size="small"
            placeholder="预计处置时间安排"
            @input="(v: string) => emit('update', row.id, 'timetable', v)"
          />
          <span v-else>{{ row.timetable || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link :disabled="isReadonly" @click="emit('remove', row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
/**
 * K6FairValueBlock.vue —— 持有待售「公允价值 5 列」表的通用录入区块
 *
 * 三处复用：持有待售非流动资产 / 持有待售处置组 / 持有待售负债（国企 §八、43）。
 * 列头逐字取自源 xlsx（`项目 / 期末账面价值 / 期末公允价值 / 预计{出售|处置}费用 / 时间安排`），
 * 「计量校验」是底稿侧的勾稽提示列（源模板红字「期末账面价值 ≤ 期末公允价值 − 预计处置费用」），
 * **不进附注**（附注只有 5 列）。
 *
 * spec: .kiro/specs/k-cycle-disclosure-alignment/ 批 3 Task 13
 */
import { fmtAmount } from '@/utils/formatters'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import type { K6FairValueUiRow } from '../../composables/useK6NoteBlocks'

const props = defineProps<{
  title: string
  hint: string
  rows: K6FairValueUiRow[]
  feeLabel: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'add'): void
  (e: 'remove', id: string): void
  (e: 'update', id: string, field: string, value: unknown): void
}>()

function fmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return fmtAmount(v)
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function hasData(row: K6FairValueUiRow): boolean {
  return Boolean(num(row.endBook) || num(row.endFairValue) || num(row.disposalFee))
}

/** 源模板红字：期末账面价值 ≤ 期末公允价值 − 预计处置费用（容差 0.01 元） */
function measureOk(row: K6FairValueUiRow): boolean {
  return num(row.endBook) <= num(row.endFairValue) - num(row.disposalFee) + 0.01
}

function summary({ columns }: { columns: any[] }): string[] {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (prop && ['endBook', 'endFairValue', 'disposalFee'].includes(prop)) {
      return fmt(props.rows.reduce((s, r) => s + num((r as any)[prop]), 0))
    }
    return ''
  })
}
</script>

<style scoped>
.k6-block { margin-bottom: 14px; }
.k6-block :deep(.el-card__header) { padding: 10px 16px; }
.k6-block :deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.block-head { display: flex; align-items: center; justify-content: space-between; }
.block-title { font-size: 14px; font-weight: 600; color: #303133; }
.block-hint {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 8px 12px;
  margin-bottom: 10px; border-radius: 4px; color: #78350f; line-height: 1.6;
}
:deep(.el-table__footer-wrapper td) { font-weight: 600; }
</style>
