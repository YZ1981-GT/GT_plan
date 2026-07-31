<template>
  <el-table :data="rows" border size="small" class="h7-soe-table">
    <el-table-column label="项目" min-width="220">
      <template #default="{ row }">
        <span :class="{ 'is-industry': row.kind === 'industry', 'is-total': row.kind === 'total' }">
          <span v-if="row.kind === 'category'" class="cat-indent">其中：</span>{{ row.label }}
        </span>
        <span v-if="row.kind === 'category' && !isReadonly" class="row-ops">
          <el-button size="small" link :aria-label="`重命名 ${row.label}`" @click="emit('rename', row.industryKey, row.categoryId)">✎</el-button>
          <el-button size="small" link :aria-label="`删除 ${row.label}`" @click="emit('remove', row.industryKey, row.categoryId)">✕</el-button>
        </span>
        <span v-if="row.kind === 'industry' && !isReadonly" class="row-ops">
          <el-button size="small" link :aria-label="`为 ${row.label} 新增类别`" @click="emit('add', row.industryKey)">＋ 类别</el-button>
        </span>
      </template>
    </el-table-column>

    <el-table-column
      v-for="col in EDIT_COLS"
      :key="col.key"
      :label="col.label"
      min-width="150"
      align="right"
    >
      <template #default="{ row }">
        <WpAmountInput
          v-if="row.editable"
          :model-value="row[col.key]"
          :disabled="isReadonly"
          :aria-label="`${row.label} ${col.label}`"
          @change="(v: number) => emit('change', row.industryKey, row.categoryId, col.key, v)"
        />
        <span v-else class="formula-cell" :title="row.kind === 'total' ? '合计 = 4 个产业行之和' : '产业行 = 其下各类别行之和'">
          {{ fmtAmount(row[col.key]) }}
        </span>
      </template>
    </el-table-column>

    <el-table-column label="期末账面价值" min-width="160" align="right" class-name="auto-calc-col">
      <template #default="{ row }">
        <span class="formula-cell" title="期末账面价值 = 期初账面价值 + 本期增加额 − 本期减少额">
          {{ fmtAmount(row.end) }}
        </span>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
/**
 * H7SoeIndustryTable — H7 国企披露的「产业 + 可扩类别行」5 列表（成本 / 公允价值共用）
 *
 * 源模板 `附注披露信息（国有企业）` R8–R21：项目 / 期初账面价值 / 本期增加额 /
 * 本期减少额 / 期末账面价值；行 = 4 产业 + 每产业「其中：N．」类别行 + 合计。
 * 产业行有类别时只读派生、无类别时可直接录入；期末列恒派生。
 *
 * spec: h7-biological-assets-disclosure-rebuild (Task 7)
 */
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { fmtAmount } from '@/stores/displayPrefs'
import type { H7SoeDisplayRow } from '../../composables/h7SoeDisclosureModel'

defineProps<{
  rows: readonly H7SoeDisplayRow[]
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'change', industryKey: string | undefined, categoryId: string | undefined,
    field: 'begin' | 'increase' | 'decrease', value: number): void
  (e: 'add', industryKey: string | undefined): void
  (e: 'rename', industryKey: string | undefined, categoryId: string | undefined): void
  (e: 'remove', industryKey: string | undefined, categoryId: string | undefined): void
}>()

const EDIT_COLS = [
  { key: 'begin' as const, label: '期初账面价值' },
  { key: 'increase' as const, label: '本期增加额' },
  { key: 'decrease' as const, label: '本期减少额' },
]
</script>

<style scoped>
.h7-soe-table { font-size: var(--wp-font-size, 13px); }
.h7-soe-table :deep(.auto-calc-col) { background: var(--el-fill-color-lighter); }
.is-industry { font-weight: 600; }
.is-total { font-weight: 600; }
.cat-indent { padding-left: 14px; color: var(--el-text-color-secondary); }
.row-ops { margin-left: 6px; }
.formula-cell {
  font-variant-numeric: tabular-nums;
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
</style>
