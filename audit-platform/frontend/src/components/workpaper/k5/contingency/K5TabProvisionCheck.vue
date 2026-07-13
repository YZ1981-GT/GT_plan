<template>
  <div class="k5-tab-provision-check">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性（负债重点）：</b>所有符合 CAS13 三条件（现时义务/很可能流出/金额可靠计量）的事项均已确认预计负债；</li>
        <li><b>存在与计价：</b>已确认预计负债真实存在且以最佳估计数计量，未确认的或有负债判断恰当；</li>
        <li><b>列报与披露：</b>预计负债及或有事项已按准则恰当列报披露。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 ═══ -->
    <div class="section-header">
      <h3>K5-7 预计负债综合检查表</h3>
      <div class="header-actions">
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="$emit('navigate-sheet', '审定表K5-1')">复核</el-button>
      </div>
    </div>

    <!-- ═══ 不合规红色摘要 Banner ═══ -->
    <el-alert
      v-if="nonComplianceSummary.hasNonCompliant"
      type="error"
      :closable="false"
      show-icon
      class="non-compliance-banner"
    >
      <template #title>
        存在 {{ nonComplianceSummary.count }} 项不合规：
        <span v-for="(item, idx) in nonComplianceSummary.items" :key="item.id">
          {{ item.label }}{{ idx < nonComplianceSummary.items.length - 1 ? '、' : '' }}
        </span>
      </template>
    </el-alert>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <p>逐项检查或有事项识别完整性、可能性评估合理性、最佳估计数计量、折现处理、跨期确认、分类正确性、律师函一致性、期后事项、关联方等10项。判断"合规/不合规/不适用"。</p>
    </div>

    <!-- ═══ 检查表主体 ═══ -->
    <el-table :data="checkItems" border size="small" style="width: 100%" max-height="560">
      <el-table-column prop="seq" label="序" width="48" align="center" />
      <el-table-column prop="label" label="检查项" width="160" />
      <el-table-column prop="description" label="检查内容/标准" min-width="260">
        <template #default="{ row }">
          <span class="check-desc">{{ row.description }}</span>
        </template>
      </el-table-column>
      <el-table-column label="结论" width="200" align="center">
        <template #default="{ row }">
          <el-radio-group
            :model-value="row.compliance"
            :disabled="isReadonly"
            size="small"
            @change="(v: any) => handleComplianceChange(row.id, v)"
          >
            <el-radio-button value="合规">合规</el-radio-button>
            <el-radio-button value="不合规">不合规</el-radio-button>
            <el-radio-button value="不适用">不适用</el-radio-button>
          </el-radio-group>
        </template>
      </el-table-column>
      <el-table-column label="审计证据" min-width="180">
        <template #default="{ row }">
          <el-input
            :model-value="row.evidence"
            :disabled="isReadonly"
            size="small"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            placeholder="审计证据/说明"
            @blur="(e: FocusEvent) => handleEvidenceChange(row.id, (e.target as HTMLTextAreaElement)?.value ?? '')"
          />
        </template>
      </el-table-column>
      <el-table-column label="📎" width="56" align="center">
        <template #default="{ row }">
          <el-tooltip content="抽凭+OCR" placement="top">
            <el-button link size="small" :disabled="isReadonly" @click="handleOcr(row.id)">
              📎
            </el-button>
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 完成度统计 ═══ -->
    <div class="summary-bar">
      <span>检查进度: {{ checkedCount }} / {{ checkItems.length }}</span>
      <el-tag v-if="isAllChecked()" type="success" size="small">全部完成</el-tag>
      <el-tag v-else type="info" size="small">进行中</el-tag>
      <span v-if="nonComplianceSummary.hasNonCompliant" class="text-danger">
        ⚠ {{ nonComplianceSummary.count }} 项不合规
      </span>
      <el-button size="small" style="margin-left: auto" @click="openVoucherSampling">⚡ 抽凭</el-button>
    </div>

    <!-- 抽凭引擎 Dialog -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 2701 预计负债-综合检查）" width="720px" :close-on-click-modal="false" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :account-codes="['2701']"
        dialog-mode
        @filled="onSampleFilled"
      />
    </el-dialog>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>逐项判断：合规（检查通过）/ 不合规（存在问题需跟进）/ 不适用（该项不涉及）</li>
        <li>存在"不合规"项时顶部红色摘要提示，需在审计说明中说明影响</li>
        <li>📎列可上传评估报告等附件 → OCR识别辅助填充证据</li>
        <li>全部检查完成后综合形成K5底稿结论</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabProvisionCheck.vue — K5-7 预计负债综合检查表
 * 10项逐项合规判断+红色摘要+抽凭+OCR
 * 抽凭引擎 GtVoucherSamplingEngine dialog + 行级OCR(📎评估报告)
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 4.5, 6.3
 * Requirements: 8.3-8.5
 */
import { ref, computed, toRef, defineAsyncComponent } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useK5ProvisionCheck, type K5ComplianceState } from '../../composables/useK5ProvisionCheck'
import http from '@/utils/http'
import type { Ref } from 'vue'

const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'),
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

// 父组件模板绑定会自动解包 ref → 子组件收到纯 Map；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const {
  checkItems,
  nonComplianceSummary,
  updateCompliance,
  updateEvidence,
  setOcrAttachment,
  isAllChecked,
} = useK5ProvisionCheck({
  allResponses: allResponsesRef,
  saveResponse: async (field: string, value: any) => {
    emit('save', `K5-${field}`, value)
  },
})

// ─── Derived ─────────────────────────────────────────────────────────────────

const checkedCount = computed(() => checkItems.value.filter(i => i.compliance !== null).length)

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleComplianceChange(id: string, value: K5ComplianceState) {
  updateCompliance(id, value)
}

function handleEvidenceChange(id: string, value: string) {
  updateEvidence(id, value)
}

function handleOcr(itemId: string) {
  // 行级OCR: 上传评估报告 → POST contract-ocr → 确认弹窗 → 填入审计证据
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pdf,.png,.jpg,.jpeg'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    formData.append('doc_type', 'evaluation_report')
    try {
      const res = await http.post('/d4/contract-ocr', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const ocrResult = res?.data?.data ?? res?.data ?? {}
      const ocrText = ocrResult.text || ocrResult.content || JSON.stringify(ocrResult)
      // 确认弹窗
      await ElMessageBox.confirm(
        `OCR识别结果：\n${ocrText.substring(0, 300)}${ocrText.length > 300 ? '...' : ''}\n\n是否填入该检查项的审计证据字段？`,
        '评估报告OCR识别',
        { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }
      )
      // 填入审计证据
      setOcrAttachment(itemId, ocrText)
      ElMessage.success('已将OCR识别结果填入审计证据')
    } catch (err: any) {
      if (err !== 'cancel' && err?.toString() !== 'cancel') {
        ElMessage.warning('OCR识别失败或已取消')
      }
    }
  }
  input.click()
}

// ─── 抽凭引擎 ────────────────────────────────────────────────────────────────

const showSamplingDialog = ref(false)

function openVoucherSampling() {
  showSamplingDialog.value = true
}

function onSampleFilled(sample: any) {
  showSamplingDialog.value = false
  ElMessage.success('抽凭样本已填入')
}

function handleAiGenerate() { emit('save', 'K5-7-ai-trigger', { remark: 'provision-check' }) }
</script>

<style scoped>
.k5-tab-provision-check { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }
.non-compliance-banner { margin-bottom: 12px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.check-desc { font-size: 12px; color: #606266; line-height: 1.5; }
.text-danger { color: #f56c6c; font-weight: 500; }
.summary-bar { display: flex; align-items: center; gap: 16px; margin-top: 10px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-radio-button__inner) { padding: 5px 10px; font-size: 12px; }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
