<template>
  <el-table :data="rows" border size="small" class="accrual-table" :row-class-name="({ row }) => row.indent > 0 ? 'sub-row' : ''">
    <!-- 项目 -->
    <el-table-column label="项目" min-width="180" fixed>
      <template #default="{ row }">
        <span :style="{ paddingLeft: row.indent * 16 + 'px' }">{{ row.label }}</span>
      </template>
    </el-table-column>
    <!-- 计提基数 -->
    <el-table-column label="计提基数" align="center">
      <el-table-column label="名称" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.baseName" size="small" @change="(v: string) => $emit('update', row.id, 'baseName', v)" />
          <span v-else>{{ row.baseName || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.baseAmount" :controls="false" size="small" style="width:98px" @change="(v: number) => $emit('update', row.id, 'baseAmount', v ?? 0)" />
          <span v-else>{{ fmtAmt(row.baseAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="索引" width="70">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.baseIndex" size="small" @change="(v: string) => $emit('update', row.id, 'baseIndex', v)" />
          <span v-else>{{ row.baseIndex || '-' }}</span>
        </template>
      </el-table-column>
    </el-table-column>
    <!-- 计提比例 -->
    <el-table-column label="计提比例" width="90" align="right">
      <template #default="{ row }">
        <el-input-number v-if="!isReadonly" :model-value="row.rate * 100" :controls="false" size="small" style="width:68px" :precision="2" @change="(v: number) => $emit('update', row.id, 'rate', (v ?? 0) / 100)">
          <template #suffix>%</template>
        </el-input-number>
        <span v-else>{{ row.rate > 0 ? (row.rate * 100).toFixed(2) + '%' : '-' }}</span>
      </template>
    </el-table-column>
    <!-- 应提金额（公式） -->
    <el-table-column label="应提金额" width="110" align="right" class-name="calc-col">
      <template #default="{ row }">
        <el-tooltip content="应提金额 = 计提基数金额 × 计提比例" placement="top">
          <span class="formula-cell">{{ fmtAmt(row.estimated) }}</span>
        </el-tooltip>
      </template>
    </el-table-column>
    <!-- 实际计提数 -->
    <el-table-column label="实际计提数" width="110" align="right">
      <template #default="{ row }">
        <el-input-number v-if="!isReadonly" :model-value="row.actual" :controls="false" size="small" style="width:98px" @change="(v: number) => $emit('update', row.id, 'actual', v ?? 0)" />
        <span v-else>{{ fmtAmt(row.actual) }}</span>
      </template>
    </el-table-column>
    <!-- 差异（公式） -->
    <el-table-column label="差异" width="100" align="right" class-name="calc-col">
      <template #default="{ row }">
        <el-tooltip content="差异 = 实际计提 - 应提金额" placement="top">
          <span class="formula-cell" :class="{ 'text-danger': row.diff !== 0 }">{{ fmtAmt(row.diff) }}</span>
        </el-tooltip>
      </template>
    </el-table-column>
    <!-- 差异原因 -->
    <el-table-column label="差异原因" width="120">
      <template #default="{ row }">
        <el-input v-if="!isReadonly" :model-value="row.diffReason" size="small" @change="(v: string) => $emit('update', row.id, 'diffReason', v)" />
        <span v-else>{{ row.diffReason || '-' }}</span>
      </template>
    </el-table-column>
    <!-- 结论 -->
    <el-table-column label="结论" width="100">
      <template #default="{ row }">
        <el-select v-if="!isReadonly" :model-value="row.conclusion" size="small" placeholder="选择" clearable @change="(v: string) => $emit('update', row.id, 'conclusion', v)">
          <el-option label="合理" value="合理" />
          <el-option label="需调整" value="需调整" />
          <el-option label="待定" value="待定" />
        </el-select>
        <span v-else>{{ row.conclusion || '-' }}</span>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
defineProps<{
  rows: Array<any>
  isReadonly: boolean
}>()

defineEmits<{
  update: [rowId: string, field: string, value: any]
}>()

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
</script>

<style scoped>
.accrual-table { font-size: 13px; }
:deep(.calc-col) { background-color: #f5f7fa !important; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; color: #606266; }
.text-danger { color: #f56c6c !important; font-weight: 600; }
:deep(.sub-row) { color: #606266; }
</style>
