<script setup lang="ts">
/**
 * D2TabAdjudication — 审定表D2-1
 * 固定行el-table：单项计提|账龄组合|客户类型组合|合计
 * SUMIF自动取数蓝色背景, 变动率>30%红色高亮, 试算平衡表差异
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { useD2Adjudication, type AdjudicationRow } from '../composables/useD2Adjudication'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'export-template'): void
  (e: 'export-data'): void
  (e: 'import-data'): void
}>()

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话集成 (Task 47.1)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function handleCellContextMenu(row: any, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.property || 'unknown'
  const rowKey = row?.rowKey || 'unknown'
  openReviewDialog(`D2-adjudication-${rowKey}-${field}`)
}

const viewMode = defineModel<'structured' | 'online'>('viewMode', { default: 'structured' })

const {
  adjudicationRows,
  totalRow,
  trialBalanceDiff,
  updateCell,
  isChangeRateWarning,
  sumifStatus,
} = useD2Adjudication({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const loading = computed(() => sumifStatus.value === 'computing')

function fmtRate(rate: number | ''): string {
  if (rate === '') return '-'
  return (rate * 100).toFixed(1) + '%'
}

function getCellClass(row: AdjudicationRow, field: string): string {
  const classes: string[] = []
  if (row.isFromSumif && ['currentUnadjusted', 'currentAje', 'currentRje'].includes(field)) {
    classes.push('sumif-cell')
  }
  if (field === 'changeRate' && isChangeRateWarning(row.changeRate)) {
    classes.push('rate-warning')
  }
  if (row.rowKey === 'total') {
    classes.push('total-row')
  }
  return classes.join(' ')
}

function getRowClassName({ row }: { row: AdjudicationRow }): string {
  return row.rowKey === 'total' ? 'total-row-bg' : ''
}

function handleCellEdit(row: AdjudicationRow, field: string, value: number | string) {
  if (!row.isEditable || props.isReadonly) return
  updateCell(row.rowKey, field, value)
}
</script>

<template>
  <div class="d2-tab-adjudication">
    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="emit('export-template')">导出模板</el-button>
        <el-button size="small" @click="emit('export-data')">导出数据</el-button>
        <el-button size="small" @click="emit('import-data')">导入数据</el-button>
      </div>
      <div class="toolbar-right">
        <el-segmented v-model="viewMode" :options="[
          { label: '结构化视图', value: 'structured' },
          { label: '在线编辑', value: 'online' },
        ]" size="small" />
      </div>
    </div>

    <!-- 试算平衡表差异警告 -->
    <el-alert
      v-if="!trialBalanceDiff.isZero"
      type="error"
      :closable="false"
      class="tb-diff-alert"
    >
      试算平衡表差异：{{ displayPrefs.fmtAmount(trialBalanceDiff.amount) }}元（审定数与试算表不一致）
    </el-alert>

    <!-- 主表 -->
    <el-skeleton :loading="loading" :rows="6" animated>
      <template #default>
        <el-table
          :data="adjudicationRows"
          border
          stripe
          size="small"
          :row-class-name="getRowClassName"
          style="width: 100%"
        >
          <el-table-column prop="label" label="项目" width="180" fixed />

          <!-- 期初 -->
          <el-table-column label="期初" align="center">
            <el-table-column label="未审数" width="120" align="right">
              <template #default="{ row }">
                <span :class="getCellClass(row, 'priorUnadjusted')">
                  {{ displayPrefs.fmtAmount(row.priorUnadjusted) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="AJE" width="100" align="right">
              <template #default="{ row }">
                <span>{{ displayPrefs.fmtAmount(row.priorAje) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="RJE" width="100" align="right">
              <template #default="{ row }">
                <span>{{ displayPrefs.fmtAmount(row.priorRje) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="审定数" width="120" align="right">
              <template #default="{ row }">
                <span class="audited-cell">{{ displayPrefs.fmtAmount(row.priorAudited) }}</span>
              </template>
            </el-table-column>
          </el-table-column>

          <!-- 期末 -->
          <el-table-column label="期末" align="center">
            <el-table-column label="未审数" width="120" align="right">
              <template #default="{ row }">
                <el-tooltip v-if="row.isFromSumif" content="取自D2-2按信用风险组合方式聚合" placement="top">
                  <span :class="getCellClass(row, 'currentUnadjusted')">
                    {{ displayPrefs.fmtAmount(row.currentUnadjusted) }}
                  </span>
                </el-tooltip>
                <span v-else>{{ displayPrefs.fmtAmount(row.currentUnadjusted) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="AJE" width="100" align="right">
              <template #default="{ row }">
                <el-tooltip v-if="row.isFromSumif" content="取自D2-2按信用风险组合方式聚合" placement="top">
                  <span :class="getCellClass(row, 'currentAje')">
                    {{ displayPrefs.fmtAmount(row.currentAje) }}
                  </span>
                </el-tooltip>
                <span v-else>{{ displayPrefs.fmtAmount(row.currentAje) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="RJE" width="100" align="right">
              <template #default="{ row }">
                <el-tooltip v-if="row.isFromSumif" content="取自D2-2按信用风险组合方式聚合" placement="top">
                  <span :class="getCellClass(row, 'currentRje')">
                    {{ displayPrefs.fmtAmount(row.currentRje) }}
                  </span>
                </el-tooltip>
                <span v-else>{{ displayPrefs.fmtAmount(row.currentRje) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="审定数" width="120" align="right">
              <template #default="{ row }">
                <span class="audited-cell">{{ displayPrefs.fmtAmount(row.currentAudited) }}</span>
              </template>
            </el-table-column>
          </el-table-column>

          <!-- 变动 -->
          <el-table-column label="变动额" width="120" align="right">
            <template #default="{ row }">
              <span>{{ displayPrefs.fmtAmount(row.change) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动率" width="100" align="right">
            <template #default="{ row }">
              <span :class="getCellClass(row, 'changeRate')">{{ fmtRate(row.changeRate) }}</span>
            </template>
          </el-table-column>

          <!-- 原因分析 -->
          <el-table-column label="原因分析" min-width="200">
            <template #default="{ row }">
              <el-input
                v-if="row.isEditable && !isReadonly"
                :model-value="row.reasonAnalysis"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 3 }"
                size="small"
                @change="(v: string) => handleCellEdit(row, 'reason', v)"
              />
              <span v-else>{{ row.reasonAnalysis || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.d2-tab-adjudication {
  padding: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
}
.tb-diff-alert {
  margin-bottom: 12px;
}
.sumif-cell {
  background-color: #e6f7ff;
  padding: 2px 4px;
  border-radius: 2px;
}
.rate-warning {
  color: #f56c6c;
  font-weight: 600;
}
.audited-cell {
  font-weight: 600;
}
:deep(.total-row-bg) {
  background-color: #fafafa !important;
  font-weight: 600;
}
.total-row {
  font-weight: 600;
}
</style>
