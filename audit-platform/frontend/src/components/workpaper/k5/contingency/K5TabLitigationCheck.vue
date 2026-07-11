<template>
  <div class="k5-tab-litigation">
    <!-- ═══ Section标题 ═══ -->
    <div class="section-header">
      <h3>K5-6 未决诉讼检查表</h3>
      <div class="header-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增行
        </el-button>
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI评估
        </el-button>
        <el-button size="small" @click="$emit('navigate-sheet', '审定表K5-1')">复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <p>未决诉讼按CAS13三级可能性判断：<strong>很可能(>50%)→确认预计负债</strong>；可能(≤50%)→附注披露或有负债；极小可能→不处理。律师函/回函是判断败诉可能性的关键审计证据。</p>
    </div>

    <!-- ═══ 交叉验证指示器 ═══ -->
    <div class="cross-check-bar">
      <span>K5-6 已确认预计损失: <strong>{{ fmtNum(crossCheck.litigationTotal) }}</strong></span>
      <span>K5-1 未决诉讼审定: <strong>{{ fmtNum(crossCheck.adjudicationLitigation) }}</strong></span>
      <el-tag v-if="crossCheck.isMatch" type="success" size="small">✓ 一致</el-tag>
      <el-tag v-else type="danger" size="small">差异 {{ fmtNum(crossCheck.diff) }}</el-tag>
    </div>

    <!-- ═══ 主表 ═══ -->
    <el-table :data="litigationRows" border size="small" style="width: 100%" max-height="520">
      <el-table-column type="index" label="序" width="48" align="center" />
      <el-table-column label="案件名称" min-width="150">
        <template #default="{ row }">
          <el-input v-model="row.caseName" :disabled="isReadonly" size="small" @blur="save(row.rowId, 'caseName', row.caseName)" />
        </template>
      </el-table-column>
      <el-table-column label="涉案金额" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.amount" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:95px" @change="(v:number) => save(row.rowId, 'amount', v)" />
        </template>
      </el-table-column>
      <el-table-column label="诉讼阶段" width="100">
        <template #default="{ row }">
          <el-select v-model="row.stage" :disabled="isReadonly" size="small" placeholder="阶段" @change="(v:string) => save(row.rowId, 'stage', v)">
            <el-option v-for="s in stageOptions" :key="s" :label="s" :value="s" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="律师意见" min-width="140">
        <template #default="{ row }">
          <el-input v-model="row.lawyerOpinion" :disabled="isReadonly" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" @blur="save(row.rowId, 'lawyerOpinion', row.lawyerOpinion)" />
        </template>
      </el-table-column>
      <el-table-column label="败诉可能性" width="130">
        <template #default="{ row }">
          <el-select v-model="row.lossLikelihood" :disabled="isReadonly" size="small" placeholder="级别" @change="(v:string) => save(row.rowId, 'lossLikelihood', v)">
            <el-option label="很可能(>50%)" value="very_likely" />
            <el-option label="可能(≤50%)" value="possible" />
            <el-option label="极小可能" value="remote" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="预计损失" width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.estimatedLoss" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:95px" @change="(v:number) => save(row.rowId, 'estimatedLoss', v)" />
        </template>
      </el-table-column>
      <el-table-column label="确认" width="72" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.recognition === 'recognize'" type="danger" size="small">确认</el-tag>
          <el-tag v-else-if="row.recognition === 'disclose'" type="warning" size="small">披露</el-tag>
          <el-tag v-else-if="row.recognition === 'ignore'" type="info" size="small">不处理</el-tag>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="📎" width="56" align="center">
        <template #default="{ row }">
          <el-tooltip content="律师函联动（上传+OCR）" placement="top">
            <el-button link size="small" :disabled="isReadonly" @click="handleLawyerLetter(row.rowId)">
              📎
            </el-button>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="" width="48" align="center">
        <template #default="{ $index }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow($index)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 统计摘要 ═══ -->
    <div class="summary-bar">
      <span>合计案件: {{ subtotals.count }}</span>
      <span>涉案金额: {{ fmtNum(subtotals.totalAmount) }}</span>
      <span>已确认损失: <strong class="text-danger">{{ fmtNum(subtotals.recognizedLoss) }}</strong></span>
      <span>需披露损失: <strong class="text-warning">{{ fmtNum(subtotals.disclosedLoss) }}</strong></span>
      <el-button size="small" style="margin-left: auto" @click="openVoucherSampling">⚡ 抽凭</el-button>
    </div>

    <!-- 抽凭引擎 Dialog -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 2701 预计负债-诉讼）" width="720px" :close-on-click-modal="false" destroy-on-close>
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
        <li>败诉可能性 > 50% → 确认预计负债，金额为预计损失</li>
        <li>败诉可能性 ≤ 50% 但非极小 → 附注披露或有负债</li>
        <li>律师函/回函应作为判断败诉可能性的核心证据</li>
        <li>已确认预计损失合计应与 K5-1 未决诉讼行审定数一致</li>
        <li>📎列可上传律师函附件 → OCR识别自动填充律师意见</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabLitigationCheck.vue — K5-6 未决诉讼检查表
 * 律师函联动+可能性判断+预计损失+交叉验证+OCR
 * 抽凭引擎 GtVoucherSamplingEngine dialog + 行级OCR(📎律师函)
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 4.5, 6.3
 * Requirements: 8.1-8.4
 */
import { ref, toRef, defineAsyncComponent } from 'vue'
import { Plus, Delete, MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useK5Litigation } from '../../composables/useK5Litigation'
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
  litigationRows,
  subtotals,
  crossCheck,
  stageOptions,
  updateCell,
  addRow,
  removeRow,
  setLawyerLetterRef,
} = useK5Litigation({
  allResponses: allResponsesRef,
  saveResponse: async (field: string, value: any) => {
    emit('save', `K5-${field}`, value)
  },
})

function save(rowId: string, field: string, value: any) { updateCell(rowId, field, value) }
function handleAddRow() { addRow() }
function handleAiGenerate() { emit('save', 'K5-6-ai-trigger', { remark: 'litigation-eval' }) }

function handleLawyerLetter(rowId: string) {
  // 触发律师函上传+OCR流程（行级OCR: POST contract-ocr → 确认弹窗 → 填入律师意见）
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pdf,.png,.jpg,.jpeg'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    formData.append('doc_type', 'lawyer_letter')
    try {
      const res = await http.post('/d4/contract-ocr', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const ocrResult = res?.data?.data ?? res?.data ?? {}
      const ocrText = ocrResult.text || ocrResult.content || JSON.stringify(ocrResult)
      // 确认弹窗
      await ElMessageBox.confirm(
        `OCR识别结果：\n${ocrText.substring(0, 300)}${ocrText.length > 300 ? '...' : ''}\n\n是否填入律师意见字段？`,
        '律师函OCR识别',
        { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }
      )
      // 填入律师意见
      setLawyerLetterRef(rowId, ocrText)
      ElMessage.success('已将OCR识别结果填入律师意见')
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

function fmtNum(v: number): string {
  if (!v && v !== 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k5-tab-litigation { padding: 12px; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 13px; color: #78350f; line-height: 1.6; }
.cross-check-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: 13px; }
.text-muted { color: #c0c4cc; font-size: 12px; }
.text-danger { color: #f56c6c; }
.text-warning { color: #e6a23c; }
.summary-bar { display: flex; gap: 24px; margin-top: 10px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: 13px; color: #606266; }
:deep(.el-table) { font-size: 13px; }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
