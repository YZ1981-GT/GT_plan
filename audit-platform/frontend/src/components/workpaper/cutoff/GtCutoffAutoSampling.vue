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
import { computed, onMounted, ref, toRef } from 'vue'
import { useCutoffAutoSampling, type CutoffConfig, type ExtractedVoucher, type FillMode } from '../composables/useCutoffAutoSampling'
import type { CutoffDirection } from '../composables/cutoffJudgment'
import http from '@/utils/http'
import CutoffPreviewDialog from './CutoffPreviewDialog.vue'
import CutoffHistoryDrawer from './CutoffHistoryDrawer.vue'
import PostFillAiReviewDialog, { type PostFillReviewRow } from '../voucher-sampling/PostFillAiReviewDialog.vue'

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  accountCode: string
  cutoffDirection: 'post_cutoff' | 'pre_cutoff' | 'window'
  defaultConditions?: Partial<CutoffConfig>
  workpaperId: string
  projectId: string
  year: number
  /** 只读态：为真时禁用一键取数与回写（R25.6） */
  readonly?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  readonly: false,
})

// 只读态（R25.6）：以 computed 传入 composable，供一键取数/回写守卫使用
const readonlyRef = computed(() => props.readonly)

// ─── Emits ────────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  (e: 'filled', payload: { samples: ExtractedVoucher[]; fillMode: FillMode }): void
  /** AI 复核意见经用户确认后回传，供父级写入截止底稿审计说明（Req 26.5） */
  (e: 'applied', text: string): void
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
  triggerCutoffFetch,
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
  readonly: readonlyRef,
  onFilled: (payload) => {
    emit('filled', payload)
    // 截止凭证回写完成 → 触发回写后 AI 复核弹窗（Req 26.2）
    triggerPostFillReview(payload.samples)
  },
})

// ─── 回写后 AI 复核（Req 26：截止一键取数回写后触发，section=cutoff-review） ───

const aiAvailable = ref(false)
const showReview = ref(false)
const reviewRows = ref<PostFillReviewRow[]>([])

async function checkAiHealth() {
  try {
    const r = await http.get('/api/ai/health', { _silent: true } as any)
    const status = r.data?.data?.status ?? r.data?.status
    aiAvailable.value = status === 'healthy' || status === 'degraded'
  } catch {
    aiAvailable.value = false
  }
}

/** 截止凭证回写完成后弹出 AI 复核（R26.2） */
function triggerPostFillReview(samples: ExtractedVoucher[]) {
  reviewRows.value = samples.map((s) => ({
    voucherNo: s.voucherNo,
    voucherDate: s.voucherDate,
    summary: s.summary,
    debitAmount: s.debitAmount,
    creditAmount: s.creditAmount,
    counterpartAccount: s.counterpartAccount,
    cutoffStatus: s.cutoffStatus,
  }))
  showReview.value = true
}

/** 确认采用 AI 复核意见 → 上抛父级写入截止底稿审计说明（R26.5/26.8） */
function onReviewApplied(text: string) {
  emit('applied', text)
}

onMounted(() => { void checkAiHealth() })

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

// 一键取数（R25）：从四表库凭证库按基准日 ±N 天窗口检索并回写，跨期行标注跨期疑点
async function handleCutoffFetch() {
  if (props.readonly) return
  if (!validateConfig()) return
  await triggerCutoffFetch()
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
      <el-button type="primary" :loading="loading" :disabled="readonly" @click="handleExtract">
        开始提取
      </el-button>
      <!-- 一键取数：四表库凭证库联动（R25），只读禁用 -->
      <el-button type="success" plain :loading="loading" :disabled="readonly" @click="handleCutoffFetch">
        一键取数
      </el-button>
      <el-button text @click="handleShowHistory">
        提取历史
      </el-button>
      <span v-if="readonly" class="readonly-hint">只读状态下已禁用取数与回写</span>
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

    <!-- 回写后 AI 复核弹窗（Req 26，section=cutoff-review） -->
    <PostFillAiReviewDialog
      v-model="showReview"
      :wp-id="workpaperId"
      :rows="reviewRows"
      section="cutoff-review"
      :ai-available="aiAvailable"
      @applied="onReviewApplied"
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
  font-size: var(--wp-font-size, 13px);
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
  align-items: center;
  gap: 12px;
  padding: 8px 0 0 100px;
}

.readonly-hint {
  font-size: 12px;
  color: #909399;
}
</style>
