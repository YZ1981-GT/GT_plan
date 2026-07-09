<script setup lang="ts">
/**
 * D1BusinessModeMatrix — D1-6 矩阵汇总视图
 *
 * 横向 3 组合 × 纵向依据行 + QA 矩阵，对齐 Excel 模板布局
 */
import type { BusinessModeRow, QAMatrix } from '../composables/useD1BusinessMode'
import GtReviewDot from '../GtReviewDot.vue'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  basisRows: BusinessModeRow[]
  qaMatrix: QAMatrix
  businessModeResults: string[]
  reportItemResults: string[]
  businessModeOptions: string[]
  isReadonly: boolean
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'update-basis', rowId: string, field: string, value: string): void
  (e: 'update-qa', questionIdx: number, columnIdx: number, answer: 'Y' | 'N' | ''): void
  (e: 'cell-contextmenu', row: BusinessModeRow, event: MouseEvent): void
}>()

const YN_OPTIONS = [
  { label: '是', value: 'Y' as const },
  { label: '否', value: 'N' as const },
]

function formatReportItem(item: string): string {
  if (!item) return ''
  return `应列报为${item}`
}

function isEmptyResults(results: string[]): boolean {
  return results.every((r) => !r)
}
</script>

<template>
  <div class="bm-matrix">
    <!-- (一) 业务模式及依据 -->
    <div class="section-title">（一）应收票据业务模式及依据</div>
    <div class="table-scroll">
      <el-table
        :data="basisRows"
        border
        size="small"
        class="basis-table"
        @cell-contextmenu="(row: BusinessModeRow, _col: unknown, _cell: unknown, event: MouseEvent) => emit('cell-contextmenu', row, event)"
      >
        <el-table-column label="组合名称" min-width="180" fixed>
          <template #default="{ row }: { row: BusinessModeRow }">
            <div class="combo-name-cell">
              <span class="combo-name-text">{{ row.combinationName }}</span>
              <GtReviewDot row-prefix="D1-business-mode" :row-key="row.rowId" />
            </div>
          </template>
        </el-table-column>

        <el-table-column label="被审计单位管理应收票据业务模式" min-width="260">
          <template #default="{ row }: { row: BusinessModeRow }">
            <el-select
              :model-value="row.businessMode"
              placeholder="请选择业务模式"
              clearable
              size="small"
              :disabled="isReadonly"
              style="width: 100%"
              @change="(v: string) => emit('update-basis', row.rowId, 'businessMode', v || '')"
            >
              <el-option
                v-for="opt in businessModeOptions"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </template>
        </el-table-column>

        <el-table-column label="具体依据" min-width="200">
          <template #default="{ row }: { row: BusinessModeRow }">
            <el-input
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
              :model-value="row.basis"
              placeholder="如：频繁贴现、背书……"
              :disabled="isReadonly"
              @input="(v: string) => emit('update-basis', row.rowId, 'basis', v || '')"
            />
          </template>
        </el-table-column>

        <el-table-column label="索引号" width="140">
          <template #default="{ row }: { row: BusinessModeRow }">
            <div class="index-cell">
              <el-input
                :model-value="row.indexRef"
                placeholder="如 D1-8"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => emit('update-basis', row.rowId, 'indexRef', v || '')"
              />
              <GtIndexChip
                v-if="row.indexRef"
                :value="row.indexRef"
                :context-project-id="projectId"
              />
            </div>
          </template>
        </el-table-column>

        <el-table-column label="备注" min-width="140">
          <template #default="{ row }: { row: BusinessModeRow }">
            <el-input
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
              :model-value="row.remark"
              placeholder="备注..."
              :disabled="isReadonly"
              @input="(v: string) => emit('update-basis', row.rowId, 'remark', v || '')"
            />
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- (二) 分类判断 QA 矩阵 -->
    <div class="section-title">（二）应收票据分类判断</div>
    <p class="qa-intro">了解并观察被审计单位贴现或背书的实际情况及未来预期</p>
    <div class="table-scroll">
      <table class="qa-matrix">
        <thead>
          <tr>
            <th class="qa-question-col">问题</th>
            <th v-for="col in qaMatrix.columns" :key="col">{{ col }}</th>
            <th class="qa-remark-col">备注</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(q, qIdx) in qaMatrix.questions" :key="qIdx">
            <td class="qa-question-col">{{ q }}</td>
            <td v-for="(_col, cIdx) in qaMatrix.columns" :key="cIdx" class="qa-cell">
              <el-select
                :model-value="qaMatrix.cells[qIdx][cIdx].answer"
                placeholder="—"
                clearable
                size="small"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: 'Y' | 'N' | '') => emit('update-qa', qIdx, cIdx, v || '')"
              >
                <el-option
                  v-for="opt in YN_OPTIONS"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </td>
            <td class="qa-remark-col" />
          </tr>

          <tr class="result-row">
            <td class="qa-question-col result-label">确定业务模式</td>
            <td
              v-for="(res, i) in businessModeResults"
              :key="'bm-' + i"
              class="result-cell"
            >
              <span v-if="res">{{ res }}</span>
              <span v-else class="result-hint">请完成上方问答</span>
            </td>
            <td class="qa-remark-col" />
          </tr>

          <tr class="result-row">
            <td class="qa-question-col result-label">确定报表项目</td>
            <td
              v-for="(res, i) in reportItemResults"
              :key="'ri-' + i"
              class="result-cell"
            >
              <span v-if="res">{{ formatReportItem(res) }}</span>
              <span v-else class="result-hint">请完成上方问答</span>
            </td>
            <td class="qa-remark-col" />
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="isEmptyResults(businessModeResults)" class="matrix-empty-hint">
      请完成分类判断矩阵全部问答后，系统将自动判定业务模式与列报项目。
    </div>
  </div>
</template>

<style scoped>
.bm-matrix {
  width: 100%;
}

.table-scroll {
  width: 100%;
  overflow-x: auto;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 16px 0 10px;
}

.basis-table :deep(.el-table th),
.basis-table :deep(.el-table td),
.basis-table :deep(.el-input__inner),
.basis-table :deep(.el-textarea__inner) {
  font-size: 13px;
}

.combo-name-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.combo-name-text {
  font-weight: 600;
}

.index-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.index-cell .el-input {
  flex: 1;
}

.qa-intro {
  margin: 0 0 8px;
  font-size: 13px;
  color: #606266;
}

.qa-matrix {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.qa-matrix th,
.qa-matrix td {
  border: 1px solid #ebeef5;
  padding: 8px 10px;
  vertical-align: middle;
}

.qa-matrix th {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
  text-align: center;
}

.qa-question-col {
  text-align: left !important;
  min-width: 280px;
}

.qa-cell {
  min-width: 140px;
  text-align: center;
}

.qa-remark-col {
  width: 72px;
}

.result-row .result-cell {
  background: #ecf5ff;
  font-weight: 600;
  color: #303133;
  text-align: left;
}

.result-row .result-label {
  background: #ecf5ff;
  font-weight: 600;
}

.result-hint {
  color: #909399;
  font-weight: 400;
  font-size: 12px;
}

.matrix-empty-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}
</style>
