<script setup lang="ts">
/**
 * D4WalkthroughCard — 单事项穿行测试卡片
 *
 * 7维度分组展示（el-collapse 多面板同时打开）
 * 每维度: 标题 + 完整性指示(✓/×) + 📎上传按钮 + OCR状态
 * 底部: 一致性校验结果 + 检查结论下拉 + AI穿行分析按钮
 *
 * Spec: .kiro/specs/d4-14-walkthrough-test/ Task 2.1
 */
import { ref, computed } from 'vue'
import {
  DIMENSION_GROUPS,
  isDimensionComplete,
  type TransactionItem,
} from '../../composables/useD4WalkthroughTest'
import GtIndexChip from '../../GtIndexChip.vue'

// ─── Props & Emits ───────────────────────────────────────────────────
const props = defineProps<{
  item: TransactionItem
  isReadonly: boolean
  wpId: string
  projectId: string
  d4Contracts: any[]
}>()

const emit = defineEmits<{
  (e: 'update', dimKey: string, field: string, value: any): void
  (e: 'ocr-upload', payload: { file: File; dimensionKey: string }): void
  (e: 'ref-contract'): void
  (e: 'ai-analyze'): void
  (e: 'update-conclusion', value: string): void
}>()

// ─── 2.1.1 el-collapse multi-open ───────────────────────────────────
const activeName = ref<string[]>(DIMENSION_GROUPS.map(g => g.key))

// ─── 2.1.2 Dimension completeness ───────────────────────────────────
function getDimData(dimKey: string): any {
  return (props.item as any)[dimKey] ?? {}
}

function isComplete(dimKey: string): boolean {
  return isDimensionComplete(getDimData(dimKey), dimKey)
}

function getOcrStatus(dimKey: string): string {
  return getDimData(dimKey).ocrStatus || 'none'
}

// ─── Field update handler ────────────────────────────────────────────
function onFieldChange(dimKey: string, fieldKey: string, value: any) {
  emit('update', dimKey, fieldKey, value)
}

// ─── 2.1.7 OCR upload ───────────────────────────────────────────────
function handleOcrUpload(dimKey: string, uploadFile: any): boolean {
  const file = uploadFile.raw || uploadFile
  emit('ocr-upload', { file, dimensionKey: dimKey })
  return false
}

// ─── 2.1.8 Consistency result helpers ────────────────────────────────
const consistencyColor = computed(() => {
  const score = props.item.consistencyScore
  if (score >= 100) return '#67c23a'
  if (score >= 80) return '#e6a23c'
  return '#f56c6c'
})

const consistencyLabel = computed(() => {
  const score = props.item.consistencyScore
  if (score >= 100) return '完全一致'
  if (score >= 80) return '基本一致'
  return '存在差异'
})

function isFieldMismatch(dimKey: string, fieldKey: string): boolean {
  const details = props.item.consistencyDetails
  if (!details) return false
  const dimLabel = DIMENSION_GROUPS.find(g => g.key === dimKey)?.label || ''
  if (fieldKey === 'amount') return details.amountMatch.mismatchDimensions.includes(dimLabel)
  if (fieldKey === 'productName') return details.productNameMatch.mismatchDimensions.includes(dimLabel)
  if (fieldKey === 'date') return details.dateMatch.mismatchDimensions.includes(dimLabel)
  return false
}

// ─── 2.1.9 Conclusion options ────────────────────────────────────────
const conclusionOptions = [
  { value: '无异常', label: '无异常' },
  { value: '存在差异已解释', label: '存在差异已解释' },
  { value: '存在重大异常', label: '存在重大异常' },
]
</script>

<template>
  <div class="walkthrough-card">
    <!-- 2.1.1 Seven dimension groups collapse -->
    <el-collapse v-model="activeName" class="dim-collapse">
      <el-collapse-item
        v-for="group in DIMENSION_GROUPS"
        :key="group.key"
        :name="group.key"
      >
        <!-- 2.1.2 Dimension header -->
        <template #title>
          <div class="dim-header">
            <div class="dim-header-left">
              <span class="dim-title">{{ group.label }}</span>
              <el-tag
                :type="isComplete(group.key) ? 'success' : 'info'"
                size="small"
                class="dim-indicator"
              >
                {{ isComplete(group.key) ? '✓' : '×' }}
              </el-tag>
              <!-- OCR badge -->
              <el-tag
                v-if="getOcrStatus(group.key) === 'processing'"
                type="warning" size="small"
              >识别中</el-tag>
              <el-tag
                v-else-if="getOcrStatus(group.key) === 'done'"
                type="success" size="small"
              >已识别</el-tag>
              <el-tag
                v-else-if="getOcrStatus(group.key) === 'failed'"
                type="danger" size="small"
              >识别失败</el-tag>
            </div>
            <div class="dim-header-right" @click.stop>
              <el-upload
                :show-file-list="false"
                :auto-upload="false"
                accept=".pdf,.png,.jpg,.jpeg"
                :disabled="isReadonly"
                @change="(f: any) => handleOcrUpload(group.key, f)"
              >
                <el-button
                  size="small"
                  :disabled="isReadonly"
                  text
                  title="上传附件OCR识别"
                >📎</el-button>
              </el-upload>
            </div>
          </div>
        </template>

        <!-- Dimension form fields -->
        <div class="dim-fields-grid" :class="`dim-grid-${group.key}`">
          <div
            v-for="field in group.fields"
            :key="field.key"
            class="dim-field-item"
            :class="[
              { 'mismatch-field': isFieldMismatch(group.key, field.key) },
              field.type === 'textarea' ? 'dim-field-full' : '',
            ]"
          >
            <label class="dim-field-label">{{ field.label }}</label>
            <!-- 2.1.3~2.1.6 Field rendering by type -->
            <el-input-number
              v-if="field.type === 'number'"
              :model-value="getDimData(group.key)[field.key]"
              :disabled="isReadonly"
              :controls="false"
              :precision="2"
              style="width: 100%"
              @update:model-value="(v: number) => onFieldChange(group.key, field.key, v)"
            />
            <el-input
              v-else-if="field.type === 'textarea'"
              type="textarea"
              :rows="2"
              :model-value="getDimData(group.key)[field.key]"
              :disabled="isReadonly"
              :placeholder="`请输入${field.label}`"
              @input="(v: string) => onFieldChange(group.key, field.key, v)"
            />
            <el-input
              v-else
              :model-value="getDimData(group.key)[field.key]"
              :disabled="isReadonly"
              :placeholder="`请输入${field.label}`"
              @input="(v: string) => onFieldChange(group.key, field.key, v)"
            />
          </div>

          <!-- 2.1.4 Sales contract: ref D4-12 button + GtIndexChip -->
          <div v-if="group.key === 'contract'" class="dim-field-item dim-field-full">
            <label class="dim-field-label">&nbsp;</label>
            <div class="contract-actions">
              <el-button
                size="small"
                type="primary"
                plain
                :disabled="isReadonly"
                @click="emit('ref-contract')"
              >引用D4-12合同</el-button>
              <GtIndexChip value="wp:D4-12" :context-project-id="projectId" />
            </div>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- 2.1.8 Consistency result card -->
    <el-card
      v-if="item.consistencyDetails"
      class="consistency-card"
      :body-style="{ padding: '12px 16px' }"
      shadow="never"
    >
      <div class="consistency-header">
        <span class="consistency-title">一致性校验</span>
        <el-tag
          :color="consistencyColor"
          effect="dark"
          size="small"
          class="score-tag"
        >
          {{ item.consistencyScore }}分 · {{ consistencyLabel }}
        </el-tag>
      </div>
      <div class="consistency-fields">
        <div class="match-item">
          <span class="match-label">金额</span>
          <el-tag
            :type="item.consistencyDetails.amountMatch.isConsistent ? 'success' : 'danger'"
            size="small"
          >
            {{ item.consistencyDetails.amountMatch.isConsistent ? '一致' : '不一致' }}
          </el-tag>
          <span
            v-if="!item.consistencyDetails.amountMatch.isConsistent"
            class="mismatch-dims"
          >
            {{ item.consistencyDetails.amountMatch.mismatchDimensions.join('、') }}
          </span>
        </div>
        <div class="match-item">
          <span class="match-label">品名</span>
          <el-tag
            :type="item.consistencyDetails.productNameMatch.isConsistent ? 'success' : 'danger'"
            size="small"
          >
            {{ item.consistencyDetails.productNameMatch.isConsistent ? '一致' : '不一致' }}
          </el-tag>
          <span
            v-if="!item.consistencyDetails.productNameMatch.isConsistent"
            class="mismatch-dims"
          >
            {{ item.consistencyDetails.productNameMatch.mismatchDimensions.join('、') }}
          </span>
        </div>
        <div class="match-item">
          <span class="match-label">日期</span>
          <el-tag
            :type="item.consistencyDetails.dateMatch.isConsistent ? 'success' : 'danger'"
            size="small"
          >
            {{ item.consistencyDetails.dateMatch.isConsistent ? '一致' : '不一致' }}
          </el-tag>
          <span
            v-if="!item.consistencyDetails.dateMatch.isConsistent"
            class="mismatch-dims"
          >
            {{ item.consistencyDetails.dateMatch.mismatchDimensions.join('、') }}
          </span>
        </div>
      </div>
    </el-card>

    <!-- 2.1.9 Conclusion + AI analyze button -->
    <div class="conclusion-section">
      <div class="conclusion-row">
        <span class="conclusion-label">检查结论：</span>
        <el-select
          :model-value="item.conclusion"
          :disabled="isReadonly"
          placeholder="选择结论"
          size="small"
          style="width: 200px"
          @update:model-value="(v: string) => emit('update-conclusion', v)"
        >
          <el-option
            v-for="opt in conclusionOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly"
          @click="emit('ai-analyze')"
        >🤖 AI穿行分析</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.walkthrough-card { padding: 8px 0; font-size: 13px; }
.dim-collapse :deep(.el-collapse-item__header) { height: 40px; line-height: 40px; padding: 0 12px; }
.dim-header { display: flex; justify-content: space-between; align-items: center; width: 100%; padding-right: 8px; }
.dim-header-left { display: flex; align-items: center; gap: 8px; }
.dim-header-right { display: flex; align-items: center; }
.dim-title { font-size: 13px; font-weight: 600; color: #303133; }
.dim-indicator { font-size: 11px; padding: 0 4px; }

/* ─── 多列网格布局 ─── */
.dim-fields-grid {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 10px 16px; padding: 12px 16px;
}
/* 记账凭证7字段: 前6个三列排，金额独占或和数量并排 */
.dim-grid-voucher { grid-template-columns: repeat(3, 1fr); }
/* 销售合同5字段: 三列（编号/品名/金额一行，审批/确认一行） */
.dim-grid-contract { grid-template-columns: repeat(3, 1fr); }
/* 出库单4字段: 两列 */
.dim-grid-delivery { grid-template-columns: repeat(2, 1fr); }
/* 运输单/签收单3字段: 三列一行搞定 */
.dim-grid-shipping { grid-template-columns: repeat(3, 1fr); }
.dim-grid-receipt { grid-template-columns: repeat(3, 1fr); }
/* 发票3字段: 三列 */
.dim-grid-invoice { grid-template-columns: repeat(3, 1fr); }
/* 其他2字段: 两列 */
.dim-grid-other { grid-template-columns: repeat(2, 1fr); }

.dim-field-item { display: flex; flex-direction: column; gap: 4px; }
.dim-field-full { grid-column: 1 / -1; }
.dim-field-label { font-size: 12px; color: #909399; font-weight: 500; }

.mismatch-field :deep(.el-input__wrapper),
.mismatch-field :deep(.el-input-number .el-input__wrapper) { border-color: #f56c6c !important; box-shadow: 0 0 0 1px #f56c6c inset !important; }
.contract-actions { display: flex; align-items: center; gap: 10px; }
.consistency-card { margin-top: 16px; border-left: 3px solid v-bind(consistencyColor); }
.consistency-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.consistency-title { font-size: 14px; font-weight: 600; color: #303133; }
.score-tag { border: none; }
.consistency-fields { display: flex; flex-direction: row; gap: 16px; flex-wrap: wrap; }
.match-item { display: flex; align-items: center; gap: 8px; }
.match-label { font-size: 12px; color: #606266; font-weight: 500; }
.mismatch-dims { font-size: 11px; color: #f56c6c; }
.conclusion-section { margin-top: 16px; padding: 12px; background: #fafbfc; border-radius: 6px; border: 1px solid #ebeef5; }
.conclusion-row { display: flex; align-items: center; gap: 12px; }
.conclusion-label { font-size: 13px; font-weight: 500; color: #303133; }
</style>
