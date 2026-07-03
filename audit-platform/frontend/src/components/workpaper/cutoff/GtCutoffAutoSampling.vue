<script setup lang="ts">
/**
 * GtCutoffAutoSampling — 截止测试自动提取条件配置面板
 *
 * Spec: .kiro/specs/cutoff-test-auto-sampling/
 * Task: 7.1
 *
 * 通用组件：通过 props 配置适配 D2/D4-17/D4-18/F2/E2 等所有截止性测试
 * Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 7.1, 7.3
 */
import { ref, toRef } from 'vue'
import { useCutoffAutoSampling, type CutoffConfig, type ExtractedVoucher, type FillMode } from '../composables/useCutoffAutoSampling'
import type { CutoffDirection } from '../composables/cutoffJudgment'
import CutoffPreviewDialog from './CutoffPreviewDialog.vue'
import CutoffHistoryDrawer from './CutoffHistoryDrawer.vue'

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  accountCode: string
  cutoffDirection: 'post_cutoff' | 'pre_cutoff' | 'window'
  defaultConditions?: Partial<CutoffConfig>
  workpaperId: string
  projectId: string
  year: number
}

const props = defineProps<Props>()

// ─── Emits ────────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  (e: 'filled', payload: { samples: ExtractedVoucher[]; fillMode: FillMode }): void
}>()

// ─── Composable ───────────────────────────────────────────────────────────────

const {
  config,
  loading,
  previewVisible,
  historyVisible,
  extractedVouchers,
  stats,
  historyList,
  fillMode,
  selectedVouchers,
  selectedCount,
  cutoffErrorCount,
  selectedDebitTotal,
  selectedCreditTotal,
  dateRangeText,
  triggerExtraction,
  confirmFill,
  loadHistory,
  undoLastExtraction,
  toggleSelectAll,
  validateConfig,
  configErrors,
} = useCutoffAutoSampling({
  projectId: toRef(props, 'projectId'),
  year: toRef(props, 'year'),
  workpaperId: toRef(props, 'workpaperId'),
  accountCode: props.accountCode,
  cutoffDirection: props.cutoffDirection as CutoffDirection,
  defaultConditions: props.defaultConditions,
  onFilled: (payload) => {
    emit('filled', payload)
  },
})

// ─── 凭证类型选项 ─────────────────────────────────────────────────────────────

const voucherTypeOptions = [
  { label: '记', value: '记' },
  { label: '收', value: '收' },
  { label: '付', value: '付' },
  { label: '转', value: '转' },
]

// ─── 操作 ─────────────────────────────────────────────────────────────────────

async function handleExtract() {
  if (!validateConfig()) return
  await triggerExtraction()
}

function handleShowHistory() {
  loadHistory()
}
</script>

<template>
  <div class="gt-cutoff-auto-sampling">
    <el-form label-width="100px" label-position="right" size="small">
      <!-- Row 1: 截止基准日 + 日期范围提示 -->
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="截止基准日">
            <el-date-picker
              v-model="config.cutoffDate"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="选择截止基准日"
              style="width: 100%"
            />
            <div v-if="configErrors.cutoffDate" class="field-error">{{ configErrors.cutoffDate }}</div>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="科目范围">
            <el-select
              v-model="config.accountCodes"
              multiple
              filterable
              allow-create
              default-first-option
              placeholder="输入科目编码前缀"
              style="width: 100%"
            >
              <el-option
                v-for="code in config.accountCodes"
                :key="code"
                :label="code"
                :value="code"
              />
            </el-select>
            <div v-if="configErrors.accountCodes" class="field-error">{{ configErrors.accountCodes }}</div>
          </el-form-item>
        </el-col>
      </el-row>

      <!-- Row 2: 前窗口 + 后窗口 -->
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="前窗口天数">
            <el-input-number
              v-model="config.daysBefore"
              :min="0"
              :max="60"
              controls-position="right"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="后窗口天数">
            <el-input-number
              v-model="config.daysAfter"
              :min="0"
              :max="60"
              controls-position="right"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <!-- 日期范围提示 -->
      <el-row v-if="dateRangeText">
        <el-col :span="24">
          <div class="date-range-hint">
            <el-icon><InfoFilled /></el-icon>
            查询日期范围：{{ dateRangeText }}
          </div>
        </el-col>
      </el-row>

      <!-- Row 3: 金额阈值 + 方向过滤 -->
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="金额阈值">
            <el-input-number
              v-model="config.amountThreshold"
              :min="0"
              :precision="2"
              :controls="false"
              placeholder="0表示不限"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="方向过滤">
            <el-radio-group v-model="config.directionFilter">
              <el-radio value="all">不限</el-radio>
              <el-radio value="debit">借方</el-radio>
              <el-radio value="credit">贷方</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-col>
      </el-row>

      <!-- Row 4: 凭证类型 + 摘要关键词 -->
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="凭证类型">
            <el-checkbox-group v-model="config.voucherTypeFilter">
              <el-checkbox
                v-for="opt in voucherTypeOptions"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-checkbox-group>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="摘要关键词">
            <el-input
              v-model="config.summaryKeyword"
              placeholder="支持模糊匹配"
              clearable
            />
          </el-form-item>
        </el-col>
      </el-row>

      <!-- Row 5: 排除已提取 -->
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="排除已提取">
            <el-switch v-model="config.excludeExtracted" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <!-- 操作按钮 -->
    <div class="action-bar">
      <el-button type="primary" :loading="loading" @click="handleExtract">
        开始提取
      </el-button>
      <el-button text @click="handleShowHistory">
        提取历史
      </el-button>
    </div>

    <!-- 预览弹窗 -->
    <CutoffPreviewDialog
      v-model:visible="previewVisible"
      :vouchers="extractedVouchers"
      :stats="stats"
      :fill-mode="fillMode"
      :selected-count="selectedCount"
      :cutoff-error-count="cutoffErrorCount"
      :selected-debit-total="selectedDebitTotal"
      :selected-credit-total="selectedCreditTotal"
      @update:fill-mode="(v: FillMode) => fillMode = v"
      @confirm="confirmFill"
      @toggle-select-all="toggleSelectAll"
    />

    <!-- 提取历史侧栏 -->
    <CutoffHistoryDrawer
      v-model:visible="historyVisible"
      :history-list="historyList"
      @undo="undoLastExtraction"
    />
  </div>
</template>

<script lang="ts">
import { InfoFilled } from '@element-plus/icons-vue'
export default { components: { InfoFilled } }
</script>

<style scoped>
.gt-cutoff-auto-sampling {
  padding: 12px 0;
}

.gt-cutoff-auto-sampling :deep(.el-form-item) {
  margin-bottom: 14px;
}

.gt-cutoff-auto-sampling :deep(.el-form-item__label) {
  font-size: 13px;
}

.date-range-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #909399;
  padding: 0 0 12px 100px;
}

.field-error {
  color: #f56c6c;
  font-size: 12px;
  line-height: 1.4;
  margin-top: 2px;
}

.action-bar {
  display: flex;
  gap: 12px;
  padding: 8px 0 0 100px;
}
</style>
