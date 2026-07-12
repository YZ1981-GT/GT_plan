<template>
  <div class="k2-tab-check">
    <!-- Section标题栏 + AI + 复核 右对齐 -->
    <div class="section-head">
      <h3 class="sheet-title">K2-6 其他流动资产检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" type="default" link @click="openReview">💬复核</el-button>
      </div>
    </div>

    <!-- 红色摘要 banner（存在不合规项） -->
    <el-alert v-if="checkState.summary.value.hasNonCompliant" type="error" :closable="false" class="nc-banner">
      ⚠️ 存在不合规项 {{ checkState.summary.value.nonCompliant }} 个，请关注：
      {{ nonCompliantLabels }}
    </el-alert>

    <!-- 琥珀色方法论上下文 -->
    <div class="methodology-block">
      <div class="methodology-title">检查要求（CAS14/CAS22）</div>
      <div class="methodology-content">
        检查其他流动资产分类正确性（是否应归入其他科目）、流动性（12个月内是否变现/使用）、
        可回收性（减值迹象评估）、资本化合理性（合同取得成本CAS14三条件）。逐项判断合规/不合规/不适用。
      </div>
    </div>

    <!-- 4个检查项卡片 -->
    <div class="check-cards">
      <el-card
        v-for="item in checkState.checkItems.value"
        :key="item.key"
        shadow="hover"
        class="check-card"
        :class="{ 'card-fail': item.result === '不合规', 'card-pass': item.result === '合规', 'card-na': item.result === '不适用' }"
      >
        <template #header>
          <div class="card-header">
            <span class="card-label">{{ item.label }}</span>
            <el-tag v-if="item.result" :type="resultTagType(item.result)" size="small">{{ item.result }}</el-tag>
          </div>
        </template>

        <!-- 描述 -->
        <p class="card-desc">{{ item.description }}</p>

        <!-- 结果选择 -->
        <div class="result-row">
          <span class="result-label">检查结果：</span>
          <el-radio-group
            :model-value="item.result"
            :disabled="isReadonly"
            size="small"
            @change="(v: string) => checkState.updateCheckResult(item.key, v as any)"
          >
            <el-radio-button v-for="opt in checkState.RESULT_OPTIONS" :key="opt" :value="opt">{{ opt }}</el-radio-button>
          </el-radio-group>
        </div>

        <!-- 审计证据 -->
        <el-input
          :model-value="item.evidence"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          :disabled="isReadonly"
          placeholder="填写审计证据/检查过程..."
          class="evidence-input"
          @blur="(e: FocusEvent) => checkState.updateCheckField(item.key, 'evidence', (e.target as HTMLTextAreaElement).value)"
        />

        <!-- 行级操作：抽凭 + OCR + 备注 -->
        <div class="row-actions">
          <el-button size="small" :disabled="isReadonly" @click="handleVoucherSampling(item.key)">
            📎 抽凭
          </el-button>
          <el-upload
            :show-file-list="false"
            :disabled="isReadonly"
            :before-upload="(file: File) => handleOcrUpload(item.key, file)"
            accept="image/*,.pdf"
          >
            <el-button size="small" :disabled="isReadonly">📎 OCR</el-button>
          </el-upload>
          <span v-if="item.voucherRef" class="voucher-ref">凭证: {{ item.voucherRef }}</span>
          <span v-if="item.ocrAttachment" class="ocr-badge">✓ 已识别</span>
        </div>

        <!-- 备注 -->
        <el-input
          :model-value="item.remark"
          size="small"
          :disabled="isReadonly"
          placeholder="备注"
          class="remark-input"
          @change="(v: string) => checkState.updateCheckField(item.key, 'remark', v)"
        />
      </el-card>
    </div>

    <!-- 汇总统计 -->
    <div class="check-summary">
      <span>共 {{ checkState.summary.value.total }} 项</span>
      <el-tag type="success" size="small">合规 {{ checkState.summary.value.compliant }}</el-tag>
      <el-tag type="danger" size="small">不合规 {{ checkState.summary.value.nonCompliant }}</el-tag>
      <el-tag type="info" size="small">不适用 {{ checkState.summary.value.notApplicable }}</el-tag>
      <el-tag v-if="checkState.summary.value.pending > 0" type="warning" size="small">待判定 {{ checkState.summary.value.pending }}</el-tag>
    </div>

    <!-- 抽凭引擎 dialog -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 1231 其他流动资产）" width="720px" :close-on-click-modal="false" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :wp-id="props.wpId"
        account-code="1231"
        @filled="onSampleFilled"
      />
    </el-dialog>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>4个检查维度：分类正确性/流动性/可回收性/资本化合理性</li>
        <li>每项支持行级抽凭(GtVoucherSamplingEngine dialog) + OCR附件识别</li>
        <li>存在"不合规"时顶部红色banner提示</li>
        <li>OCR上传后调用 /d4/contract-ocr 识别→确认弹窗→填入证据</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K2TabCheck.vue — K2-6 其他流动资产检查表
 *
 * Spec: .kiro/specs/k2-other-current-assets/
 * Task: 4.6
 * Requirements: 6.1-6.3
 *
 * 功能：
 * - 4检查项卡片：分类正确性/流动性/可回收性/资本化合理性
 * - 每项：描述 + 合规/不合规/不适用 radio + 审计证据textarea + 备注
 * - 行级抽凭（GtVoucherSamplingEngine dialog）
 * - 行级OCR（📎上传→POST /d4/contract-ocr→ElMessageBox确认→merge）
 * - 红色摘要banner（存在任何"不合规"项时）
 * - Uses useK2Check composable
 */
import { ref, computed, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK2Check, type K2CheckResult } from '../../composables/useK2Check'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import http from '@/utils/http'

// ─── Props / Emits ───────────────────────────────────────────────────────────

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

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const checkState = useK2Check(
  computed(() => props.allResponses),
  {
    onSave: (itemId: string, value: any) => {
      emit('save', itemId, value)
    },
  },
)

// ─── Sampling ────────────────────────────────────────────────────────────────

const showSamplingDialog = ref(false)
const currentSamplingKey = ref('')

function handleVoucherSampling(key: string): void {
  currentSamplingKey.value = key
  showSamplingDialog.value = true
}

function onSampleFilled(payload: any): void {
  if (currentSamplingKey.value && payload?.voucherNo) {
    checkState.updateCheckField(currentSamplingKey.value, 'voucherRef', payload.voucherNo)
  }
  showSamplingDialog.value = false
}

// ─── OCR ─────────────────────────────────────────────────────────────────────

async function handleOcrUpload(key: string, file: File): Promise<boolean> {
  try {
    const formData = new FormData()
    formData.append('file', file)

    const res = await http.post('/api/d4/contract-ocr', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const ocrResult = res.data?.data?.text || res.data?.text || ''

    if (!ocrResult) {
      ElMessage.warning('OCR未识别出内容')
      return false
    }

    await ElMessageBox.confirm(
      `OCR识别结果：\n\n${ocrResult.slice(0, 500)}${ocrResult.length > 500 ? '...' : ''}`,
      'OCR结果确认',
      { confirmButtonText: '填入证据', cancelButtonText: '取消', type: 'info' },
    )

    // 合并到证据
    const existing = checkState.checkItems.value.find(i => i.key === key)?.evidence || ''
    const merged = existing ? `${existing}\n[OCR] ${ocrResult}` : `[OCR] ${ocrResult}`
    checkState.updateCheckField(key, 'evidence', merged)
    checkState.updateCheckField(key, 'ocrAttachment', file.name)
    ElMessage.success('OCR内容已填入')
  } catch {
    /* cancelled or error */
  }
  return false // prevent default upload
}

// ─── AI Assist ───────────────────────────────────────────────────────────────

async function handleAiAssist(): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: '请根据其他流动资产(1231)的检查要求，生成检查表各项的建议性证据描述',
      context: '科目:其他流动资产(1231)，检查项：分类正确性/流动性/可回收性/资本化合理性',
      section: 'K2-6-check',
    })
    const generated = res.data?.data?.content || res.data?.content || ''
    if (generated) {
      await ElMessageBox.confirm(`AI建议：\n\n${generated.slice(0, 400)}`, 'AI辅助', {
        confirmButtonText: '参考', cancelButtonText: '关闭',
      })
    }
  } catch { /* silent */ }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const nonCompliantLabels = computed(() =>
  checkState.checkItems.value
    .filter(i => i.result === '不合规')
    .map(i => i.label)
    .join('、'),
)

function resultTagType(result: K2CheckResult): '' | 'success' | 'danger' | 'info' {
  if (result === '合规') return 'success'
  if (result === '不合规') return 'danger'
  if (result === '不适用') return 'info'
  return ''
}

function openReview(): void {
  openReviewDialog('K2-6-check')
}
</script>

<style scoped>
.k2-tab-check { padding: 16px; font-size: var(--wp-font-size, 13px); }

.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }

/* 红色摘要 banner */
.nc-banner { margin-bottom: 12px; }

/* 琥珀色方法论 */
.methodology-block {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.7;
}
.methodology-title { font-weight: 600; color: #78350f; margin-bottom: 4px; }

/* 检查卡片 */
.check-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }
.check-card { transition: border-color 0.2s; }
.check-card.card-fail { border-color: #f56c6c; }
.check-card.card-pass { border-color: #67c23a; }
.check-card.card-na { border-color: #909399; }

.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-label { font-weight: 600; font-size: 14px; }
.card-desc { font-size: 12px; color: var(--el-text-color-secondary); margin: 0 0 12px; line-height: 1.6; }

.result-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.result-label { font-size: 12px; color: var(--el-text-color-regular); white-space: nowrap; }

.evidence-input { margin-bottom: 8px; }

.row-actions { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.voucher-ref { font-size: 11px; color: var(--el-color-primary); }
.ocr-badge { font-size: 11px; color: #67c23a; }

.remark-input { margin-top: 4px; }

/* 汇总 */
.check-summary { display: flex; align-items: center; gap: 10px; padding: 10px 0; font-size: var(--wp-font-size, 13px); }

/* 编制提示 */
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
