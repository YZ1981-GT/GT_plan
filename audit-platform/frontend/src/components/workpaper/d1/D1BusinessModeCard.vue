<script setup lang="ts">
/**
 * D1BusinessModeCard — 单组合业务模式分析卡片
 *
 * 纵向展示：表(一)依据字段 + 表(二)该组合 QA + 自动判定结果
 */
import { computed } from 'vue'
import type { BusinessModeRow, QAMatrix } from '../composables/useD1BusinessMode'
import GtReviewDot from '../GtReviewDot.vue'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  row: BusinessModeRow
  columnIndex: number
  qaMatrix: QAMatrix
  businessModeResult: string
  reportItemResult: string
  businessModeOptions: string[]
  isReadonly: boolean
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'update-basis', field: string, value: string): void
  (e: 'update-qa', questionIdx: number, answer: 'Y' | 'N' | ''): void
}>()

const YN_OPTIONS = [
  { label: '是', value: 'Y' as const },
  { label: '否', value: 'N' as const },
]

function formatReportItem(item: string): string {
  if (!item) return ''
  return `应列报为${item}`
}

const qaAnsweredCount = computed(() =>
  props.qaMatrix.cells.filter((row) => row[props.columnIndex]?.answer).length,
)

const basisFilled = computed(() =>
  !!(props.row.businessMode || props.row.basis),
)
</script>

<template>
  <div class="bm-card">
    <div class="bm-card-header">
      <div class="bm-card-title">
        <span class="combo-name">{{ row.combinationName }}</span>
        <GtReviewDot row-prefix="D1-business-mode" :row-key="row.rowId" />
      </div>
      <div class="bm-card-tags">
        <el-tag v-if="basisFilled" size="small" type="success" effect="plain">依据已填</el-tag>
        <el-tag v-else size="small" type="info" effect="plain">依据待填</el-tag>
        <el-tag
          size="small"
          :type="qaAnsweredCount === qaMatrix.questions.length ? 'success' : 'warning'"
          effect="plain"
        >
          QA {{ qaAnsweredCount }}/{{ qaMatrix.questions.length }}
        </el-tag>
      </div>
    </div>

    <!-- (一) 业务模式及依据 -->
    <div class="card-section">
      <div class="card-section-title">（一）业务模式及依据</div>
      <el-form label-position="top" size="small" class="basis-form">
        <el-form-item label="被审计单位管理应收票据业务模式">
          <el-select
            :model-value="row.businessMode"
            placeholder="请选择业务模式"
            clearable
            :disabled="isReadonly"
            style="width: 100%"
            @change="(v: string) => emit('update-basis', 'businessMode', v || '')"
          >
            <el-option
              v-for="opt in businessModeOptions"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="具体依据">
          <el-input
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 6 }"
            :model-value="row.basis"
            placeholder="如：频繁贴现、背书、持有意图……"
            :disabled="isReadonly"
            @input="(v: string) => emit('update-basis', 'basis', v || '')"
          />
        </el-form-item>

        <el-form-item label="索引号">
          <div class="index-row">
            <el-input
              :model-value="row.indexRef"
              placeholder="如 D1-8"
              :disabled="isReadonly"
              @change="(v: string) => emit('update-basis', 'indexRef', v || '')"
            />
            <GtIndexChip
              v-if="row.indexRef"
              :value="row.indexRef"
              :context-project-id="projectId"
            />
          </div>
        </el-form-item>

        <el-form-item label="备注">
          <el-input
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :model-value="row.remark"
            placeholder="备注..."
            :disabled="isReadonly"
            @input="(v: string) => emit('update-basis', 'remark', v || '')"
          />
        </el-form-item>
      </el-form>
    </div>

    <!-- (二) 分类判断 QA（该组合列） -->
    <div class="card-section">
      <div class="card-section-title">（二）分类判断</div>
      <p class="qa-hint">了解并观察被审计单位贴现或背书的实际情况及未来预期</p>
      <div
        v-for="(q, qIdx) in qaMatrix.questions"
        :key="qIdx"
        class="qa-item"
      >
        <div class="qa-question">{{ q }}</div>
        <el-select
          :model-value="qaMatrix.cells[qIdx][columnIndex].answer"
          placeholder="请选择"
          clearable
          size="small"
          :disabled="isReadonly"
          style="width: 120px"
          @change="(v: 'Y' | 'N' | '') => emit('update-qa', qIdx, v || '')"
        >
          <el-option
            v-for="opt in YN_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>
    </div>

    <!-- 自动判定 -->
    <div class="result-panel">
      <div class="result-item">
        <span class="result-label">确定业务模式</span>
        <span v-if="businessModeResult" class="result-value">{{ businessModeResult }}</span>
        <span v-else class="result-hint">请完成上方问答</span>
      </div>
      <div class="result-item">
        <span class="result-label">确定报表项目</span>
        <span v-if="reportItemResult" class="result-value">{{ formatReportItem(reportItemResult) }}</span>
        <span v-else class="result-hint">请完成上方问答</span>
      </div>
    </div>

    <div class="cross-ref">
      <span class="cross-ref-label">勾稽参考</span>
      <GtIndexChip value="wp:D1-7" :context-project-id="projectId" />
      <GtIndexChip value="wp:D1-8" :context-project-id="projectId" />
      <GtIndexChip value="wp:D1-1" :context-project-id="projectId" />
    </div>
  </div>
</template>

<style scoped>
.bm-card {
  padding: 4px 0 8px;
}

.bm-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.bm-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.combo-name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.bm-card-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.card-section {
  margin-bottom: 20px;
}

.card-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #ebeef5;
}

.basis-form :deep(.el-form-item__label) {
  font-size: 13px;
  color: #606266;
}

.index-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.index-row .el-input {
  flex: 1;
  max-width: 200px;
}

.qa-hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: #909399;
}

.qa-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  margin-bottom: 8px;
  background: #fafafa;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}

.qa-question {
  flex: 1;
  font-size: 13px;
  color: #303133;
  line-height: 1.6;
}

.result-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  background: #ecf5ff;
  border-radius: 8px;
  border: 1px solid #d9ecff;
  margin-bottom: 12px;
}

.result-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.result-label {
  font-size: 12px;
  font-weight: 600;
  color: #409eff;
}

.result-value {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.result-hint {
  font-size: 12px;
  color: #909399;
}

.cross-ref {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.cross-ref-label {
  font-size: 12px;
  color: #909399;
}
</style>
