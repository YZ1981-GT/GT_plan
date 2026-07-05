<template>
  <div class="g5-adjudication">
    <!-- TB差异提示 -->
    <div v-if="Math.abs(adjudication.variance.value) > 0.01" class="variance-alert">
      <el-alert type="error" :closable="false">
        试算表差异：{{ fmtAmount(adjudication.variance.value) }}（审定数 - 试算表）
      </el-alert>
    </div>

    <!-- 五层分组表格 -->
    <el-table
      :data="flatRows"
      :height="560"
      border
      stripe
      style="width: 100%; font-size: 13px"
      :row-class-name="rowClassName"
    >
      <el-table-column prop="item" label="项目" min-width="160" fixed />
      <el-table-column label="期初" align="center">
        <el-table-column prop="openingUnadjusted" label="未审" min-width="90" align="right" />
        <el-table-column prop="openingAJE" label="AJE" min-width="80" align="right" />
        <el-table-column prop="openingRJE" label="RJE" min-width="80" align="right" />
        <el-table-column label="审定" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="未审+AJE+RJE">{{ fmtAmount(row.openingAdjusted) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="期末" align="center">
        <el-table-column prop="closingUnadjusted" label="未审" min-width="90" align="right" />
        <el-table-column prop="closingAJE" label="AJE" min-width="80" align="right" />
        <el-table-column prop="closingRJE" label="RJE" min-width="80" align="right" />
        <el-table-column label="审定" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="未审+AJE+RJE">{{ fmtAmount(row.closingAdjusted) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="变动额" min-width="90" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="期末审定-期初审定">{{ fmtAmount(row.changeAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动率" min-width="80" align="right">
        <template #default="{ row }">
          <span
            :class="{ 'rate-warning': adjudication.needsReason(row) }"
            class="formula-cell"
            title="(期末-期初)/期初"
          >
            {{ row.changeRate !== null ? (row.changeRate * 100).toFixed(1) + '%' : '-' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="reasonAnalysis" label="原因分析" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="adjudication.needsReason(row)"
            v-model="row.reasonAnalysis"
            size="small"
            placeholder="必填"
            :disabled="props.readonly"
          />
          <span v-else>{{ row.reasonAnalysis || '-' }}</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useG5Adjudication } from '../../composables/useG5Adjudication'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const adjudication = useG5Adjudication({
  wpId: props.wpId,
  projectId: props.projectId,
  htmlData: props.htmlData,
  isReadonly: props.readonly,
})

const flatRows = computed(() => adjudication.allRows.value)

function fmtAmount(v: number | null): string {
  if (v === null || v === undefined) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClassName({ row }: any) {
  if (adjudication.needsReason(row) && !row.reasonAnalysis) return 'row-warning'
  return ''
}
</script>

<style scoped>
.g5-adjudication { font-size: 13px; }
.variance-alert { margin-bottom: 8px; }
.formula-cell {
  border-bottom: 1px dashed #999;
  cursor: help;
}
.rate-warning {
  color: #e6a23c;
  font-weight: 600;
}
:deep(.row-warning) { background-color: #fdf6ec !important; }
</style>
