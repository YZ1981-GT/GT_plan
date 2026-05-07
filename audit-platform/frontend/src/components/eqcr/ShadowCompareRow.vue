<!--
  ShadowCompareRow — EQCR 影子计算对比组件 [R7-S3-04 Task 19]
  显示"项目组值 vs 影子值 vs 差异"的三列对比表格。

  用法：
    <ShadowCompareRow :rows="compareData" @verdict="onVerdict" />
-->
<template>
  <div class="gt-shadow-compare">
    <el-table :data="rows" border size="small" style="width: 100%">
      <el-table-column label="维度" prop="dimension" width="160" />
      <el-table-column label="项目组值" width="140" align="right">
        <template #default="{ row }">
          <span class="gt-shadow-team">{{ fmtValue(row.teamValue) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="影子值" width="140" align="right">
        <template #default="{ row }">
          <span class="gt-shadow-mine">{{ fmtValue(row.shadowValue) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="差异" width="120" align="right">
        <template #default="{ row }">
          <span :class="{ 'gt-shadow-diff--nonzero': row.diff !== 0 }">
            {{ fmtValue(row.diff) }}
            <small v-if="row.diffPct != null">({{ row.diffPct }}%)</small>
          </span>
        </template>
      </el-table-column>
      <el-table-column label="判断" width="160" align="center">
        <template #default="{ row }">
          <el-button size="small" type="success" @click="$emit('verdict', row, 'pass')" :disabled="row.verdict === 'pass'">通过</el-button>
          <el-button size="small" type="danger" @click="$emit('verdict', row, 'flag')" :disabled="row.verdict === 'flag'">标记</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

export interface ShadowCompareItem {
  dimension: string
  teamValue: number | null
  shadowValue: number | null
  diff: number
  diffPct: number | null
  verdict?: 'pass' | 'flag' | null
}

defineProps<{
  rows: ShadowCompareItem[]
}>()

defineEmits<{
  (e: 'verdict', row: ShadowCompareItem, action: 'pass' | 'flag'): void
}>()

const displayPrefs = useDisplayPrefsStore()

function fmtValue(v: number | null | undefined): string {
  if (v == null) return '—'
  return displayPrefs.fmt(v)
}
</script>

<style scoped>
.gt-shadow-compare { margin: var(--gt-space-3) 0; }
.gt-shadow-team { color: var(--gt-color-text); font-weight: 500; }
.gt-shadow-mine { color: var(--gt-color-primary); font-weight: 600; }
.gt-shadow-diff--nonzero { color: var(--gt-color-coral); font-weight: 600; }
</style>
