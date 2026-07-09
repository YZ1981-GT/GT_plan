<template>
  <div class="k4-tab-check">
    <!-- Section标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">K4-4 其他流动负债检查表</h3>
      <div class="head-actions">
        <el-button size="small" @click="openReview('K4-4-check')">💬复核</el-button>
      </div>
    </div>

    <!-- 不合规红色警告 -->
    <el-alert
      v-if="nonComplianceSummary.hasNonCompliant"
      type="error"
      :closable="false"
      style="margin-bottom:10px"
    >
      ⚠️ 存在 {{ nonComplianceSummary.count }} 项"不合规"：
      <span v-for="(nc, idx) in nonComplianceSummary.items" :key="nc.id">
        {{ nc.label }}<span v-if="idx < nonComplianceSummary.items.length - 1">、</span>
      </span>
    </el-alert>

    <!-- 琥珀色方法论块 -->
    <div class="methodology-block">
      <div class="methodology-title">K4-4 检查要求（完整性认定为主）</div>
      <div class="methodology-content">
        其他流动负债（2245）负债类科目，完整性认定为关注重点。检查内容涵盖：
        ①分类正确性（是否混入合同负债/其他应付等）②流动性判断（是否应重分类至非流动）
        ③完整性反向截止（期后偿付/到期倒查确认不存在少计）④合规性（预提依据/代扣代缴）。
      </div>
    </div>

    <!-- 检查项卡片列表 -->
    <div v-for="item in checkItems" :key="item.id" class="check-item-card">
      <el-card shadow="never">
        <template #header>
          <div class="check-item-header">
            <span class="check-seq">{{ item.seq }}.</span>
            <span class="check-label">{{ item.label }}</span>
            <el-tag v-if="item.compliance === '合规'" type="success" size="small">合规</el-tag>
            <el-tag v-else-if="item.compliance === '不合规'" type="danger" size="small">不合规</el-tag>
            <el-tag v-else-if="item.compliance === '不适用'" type="info" size="small">不适用</el-tag>
            <el-tag v-else type="warning" size="small">未判定</el-tag>
          </div>
        </template>

        <!-- 检查描述 -->
        <p class="check-description">{{ item.description }}</p>

        <!-- 合规判定radio -->
        <div class="check-field-row">
          <span class="field-label">合规判定：</span>
          <el-radio-group
            :model-value="item.compliance"
            :disabled="isReadonly"
            @change="(v: string) => handleComplianceChange(item.id, v as any)"
          >
            <el-radio value="合规">合规</el-radio>
            <el-radio value="不合规">不合规</el-radio>
            <el-radio value="不适用">不适用</el-radio>
          </el-radio-group>
        </div>

        <!-- 审计证据 -->
        <div class="check-field-row">
          <span class="field-label">审计证据：</span>
          <el-input
            :model-value="item.evidence"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            :disabled="isReadonly"
            placeholder="记录检查过程、审计证据及发现..."
            @change="(v: string) => handleEvidenceChange(item.id, v)"
          />
        </div>

        <!-- 凭证号 + 抽凭 + OCR -->
        <div class="check-action-row">
          <div class="voucher-field">
            <span class="field-label">凭证号：</span>
            <el-input
              :model-value="item.voucherRef"
              size="small"
              :disabled="isReadonly"
              placeholder="如：记-001"
              style="width:140px"
              @change="(v: string) => handleVoucherRefChange(item.id, v)"
            />
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleVoucherSampling(item.id)">
              🎲 抽凭
            </el-button>
          </div>
          <div class="ocr-field">
            <el-button size="small" type="default" link :disabled="isReadonly" @click="handleOcrUpload(item.id)">
              📎 OCR识别
            </el-button>
            <span v-if="item.ocrAttachment" class="ocr-indicator">✓ 已附</span>
          </div>
        </div>

        <!-- 备注 -->
        <div class="check-field-row">
          <span class="field-label">备注：</span>
          <el-input
            :model-value="item.remark"
            size="small"
            :disabled="isReadonly"
            placeholder="补充说明..."
            @change="(v: string) => handleRemarkChange(item.id, v)"
          />
        </div>
      </el-card>
    </div>

    <!-- 抽凭引擎 Dialog -->
    <GtVoucherSamplingEngine
      v-if="voucherDialogVisible"
      v-model:visible="voucherDialogVisible"
      :wp-id="wpId"
      :project-id="projectId"
      @sample-selected="handleSampleSelected"
    />

    <!-- OCR file input -->
    <input ref="ocrFileInput" type="file" accept="image/*,.pdf" style="display:none" @change="handleOcrFileSelected" />

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <div class="compile-content">
        <p>1. 其他流动负债（2245）为负债类科目，完整性认定为主（负债易少计）。</p>
        <p>2. 四项检查：分类正确性→确认科目归属；流动性→非流动应重分类；完整性→反向截止测试；合规性→预提/代扣合法合规。</p>
        <p>3. 行级抽凭：点击"🎲抽凭"打开抽凭引擎Dialog，选择样本后自动填入凭证号。</p>
        <p>4. 行级OCR：点击"📎OCR识别"上传凭证影像，调用OCR识别后确认填入证据字段。</p>
        <p>5. 存在任何"不合规"项时，顶部红色警告提示，需在审计说明中解释并建议调整。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K4TabCheck.vue — K4-4 其他流动负债检查表
 *
 * Spec: k4-other-current-liabilities Task 4.4
 * Requirements: 4.1-4.3
 *
 * 功能：
 * - 逐项检查：分类正确性/流动性判断/完整性(反向截止)/合规性
 * - Per-item: compliance radio (合规/不合规/不适用) + evidence + 凭证号 + 📎OCR + 备注
 * - Red banner when any "不合规" exists
 * - 行级抽凭: GtVoucherSamplingEngine dialog
 * - 行级OCR: 📎 upload → POST contract-ocr → ElMessageBox confirm → merge
 *
 * 科目：2245 其他流动负债（负债类，完整性认定为主）
 */
import { ref, inject, onMounted, defineAsyncComponent, toRef } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useK4Check, type K4ComplianceState } from '@/components/workpaper/composables/useK4Check'
import http from '@/utils/http'

// Lazy import voucher sampling engine
const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('@/components/workpaper/shared/GtVoucherSamplingEngine.vue'),
)

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ═══ useK4Check composable ═══
function saveResponse(itemId: string, value: any): void {
  emit('save', itemId, value)
}

const {
  checkItems,
  nonComplianceSummary,
  updateCompliance,
  updateEvidence,
  updateRemark,
  setVoucherRef,
  setOcrAttachment,
} = useK4Check({
  allResponses: toRef(props, 'allResponses'),
  saveResponse,
})

// ═══ 抽凭引擎 ═══
const voucherDialogVisible = ref(false)
let currentVoucherItemId = ''

function handleVoucherSampling(itemId: string): void {
  currentVoucherItemId = itemId
  voucherDialogVisible.value = true
}

function handleSampleSelected(sample: any): void {
  if (currentVoucherItemId && sample) {
    const ref = sample.voucherNo || sample.voucher_no || sample.ref || ''
    setVoucherRef(currentVoucherItemId, ref)
    ElMessage.success(`已选取凭证：${ref}`)
  }
  voucherDialogVisible.value = false
}

// ═══ 行级OCR ═══
const ocrFileInput = ref<HTMLInputElement | null>(null)
let currentOcrItemId = ''

function handleOcrUpload(itemId: string): void {
  currentOcrItemId = itemId
  ocrFileInput.value?.click()
}

async function handleOcrFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = '' // reset

  try {
    const formData = new FormData()
    formData.append('file', file)

    ElMessage.info('正在OCR识别...')
    const res = await http.post('/api/d4/contract-ocr', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const ocrText = res.data?.data?.text || res.data?.text || ''

    if (!ocrText) {
      ElMessage.warning('OCR未识别到文字内容')
      return
    }

    // 确认弹窗
    await ElMessageBox.confirm(
      `OCR识别结果：\n\n${ocrText.slice(0, 500)}${ocrText.length > 500 ? '...' : ''}`,
      'OCR识别确认',
      { confirmButtonText: '填入证据', cancelButtonText: '取消', type: 'info' },
    )

    // merge到evidence
    const item = checkItems.value.find(i => i.id === currentOcrItemId)
    if (item) {
      const merged = item.evidence ? `${item.evidence}\n[OCR] ${ocrText}` : `[OCR] ${ocrText}`
      updateEvidence(currentOcrItemId, merged)
      setOcrAttachment(currentOcrItemId, file.name)
      ElMessage.success('OCR内容已填入审计证据')
    }
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.error('OCR识别失败：' + (err?.response?.data?.detail || err.message || '未知错误'))
    }
  }
}

// ═══ 字段更新 ═══
function handleComplianceChange(itemId: string, value: K4ComplianceState): void {
  updateCompliance(itemId, value)
}

function handleEvidenceChange(itemId: string, value: string): void {
  updateEvidence(itemId, value)
}

function handleRemarkChange(itemId: string, value: string): void {
  updateRemark(itemId, value)
}

function handleVoucherRefChange(itemId: string, value: string): void {
  setVoucherRef(itemId, value)
}

// ═══ 复核 ═══
function openReview(id: string): void {
  openReviewDialog(id)
}
</script>

<style scoped>
.k4-tab-check { padding: 16px; font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }

/* 琥珀色方法论 */
.methodology-block { border-left: 4px solid #f59e0b; background: #fffbeb; border-radius: 4px; padding: 12px 16px; margin-bottom: 14px; }
.methodology-title { font-weight: 600; color: #92400e; margin-bottom: 4px; font-size: 12px; }
.methodology-content { font-size: 12px; color: #78350f; line-height: 1.6; }

/* 检查项卡片 */
.check-item-card { margin-bottom: 10px; }
.check-item-header { display: flex; align-items: center; gap: 8px; }
.check-seq { font-weight: 700; color: var(--el-color-primary); }
.check-label { font-weight: 600; font-size: 14px; flex: 1; }
.check-description { font-size: 12px; color: var(--el-text-color-secondary); margin: 0 0 12px 0; line-height: 1.6; }

/* 字段行 */
.check-field-row { margin-bottom: 10px; }
.field-label { display: inline-block; width: 72px; font-size: 12px; color: #606266; font-weight: 500; vertical-align: top; }

/* 操作行（凭证+OCR） */
.check-action-row { display: flex; align-items: center; gap: 24px; margin-bottom: 10px; flex-wrap: wrap; }
.voucher-field { display: flex; align-items: center; gap: 6px; }
.ocr-field { display: flex; align-items: center; gap: 6px; }
.ocr-indicator { font-size: 11px; color: #67c23a; }

/* 编制提示 */
.compile-hint { margin-top: 16px; }
.compile-hint summary { cursor: pointer; font-weight: 500; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-content { padding: 8px 12px; background: #fffbeb; border-left: 3px solid #f59e0b; margin-top: 6px; font-size: 12px; line-height: 1.8; }
.compile-content p { margin: 0; }
</style>
