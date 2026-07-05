<template>
  <div class="c24-anomaly-entry">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="methodology-bar" />
      <p>C24-5 异常分录测试：基于 13 条规则对所有分录进行筛选，标记疑似异常分录，逐条核查并形成结论。</p>
    </div>

    <!-- 规则配置面板 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">异常规则配置</span>
        <el-button v-if="!isReadonly" size="small" type="primary" @click="$emit('run-screen')">重新筛选</el-button>
      </div>

      <el-card shadow="never" class="rules-card">
        <el-checkbox-group :model-value="enabledRules" :disabled="isReadonly" @change="onRulesChange">
          <div class="rules-grid">
            <!-- 规则1: 假期录入 -->
            <div class="rule-item">
              <el-checkbox label="holidays">1. 假期录入</el-checkbox>
            </div>
            <!-- 规则2: 夜间录入 -->
            <div class="rule-item">
              <el-checkbox label="night">2. 夜间录入</el-checkbox>
              <div v-if="enabledRules.includes('night')" class="rule-params">
                <span>起始</span>
                <el-input-number :model-value="ruleParams.nightStartHour" :disabled="isReadonly" :min="18" :max="23" size="small" @change="onParamChange('nightStartHour', $event)" />
                <span>~结束</span>
                <el-input-number :model-value="ruleParams.nightEndHour" :disabled="isReadonly" :min="1" :max="8" size="small" @change="onParamChange('nightEndHour', $event)" />
              </div>
            </div>
            <!-- 规则3: 频繁调整 -->
            <div class="rule-item">
              <el-checkbox label="frequent">3. 频繁调整</el-checkbox>
            </div>
            <!-- 规则4: 大额分录 -->
            <div class="rule-item">
              <el-checkbox label="large">4. 大额分录</el-checkbox>
              <div v-if="enabledRules.includes('large')" class="rule-params">
                <span>阈值</span>
                <el-input-number :model-value="ruleParams.largeAmountThreshold" :disabled="isReadonly" :min="0" :step="10000" size="small" @change="onParamChange('largeAmountThreshold', $event)" />
              </div>
            </div>
            <!-- 规则5: 刚好低于审批限额 -->
            <div class="rule-item">
              <el-checkbox label="approval">5. 刚好低于审批限额</el-checkbox>
              <div v-if="enabledRules.includes('approval')" class="rule-params">
                <span>审批限额</span>
                <el-input-number :model-value="ruleParams.approvalLimit" :disabled="isReadonly" :min="0" :step="10000" size="small" @change="onParamChange('approvalLimit', $event)" />
              </div>
            </div>
            <!-- 规则6: 约整数 -->
            <div class="rule-item">
              <el-checkbox label="round">6. 约整数</el-checkbox>
              <div v-if="enabledRules.includes('round')" class="rule-params">
                <span>末尾0位数</span>
                <el-input-number :model-value="ruleParams.roundAmountDigits" :disabled="isReadonly" :min="2" :max="6" size="small" @change="onParamChange('roundAmountDigits', $event)" />
              </div>
            </div>
            <!-- 规则7: 尾数一致 -->
            <div class="rule-item">
              <el-checkbox label="tail">7. 尾数一致</el-checkbox>
            </div>
            <!-- 规则8: 同金额/同摘要重复 -->
            <div class="rule-item">
              <el-checkbox label="duplicate">8. 同金额或同摘要重复</el-checkbox>
            </div>
            <!-- 规则9: 借贷方不常见组合 -->
            <div class="rule-item">
              <el-checkbox label="unusual">9. 借贷方不常见组合</el-checkbox>
            </div>
            <!-- 规则10: 大量分录异常账户 -->
            <div class="rule-item">
              <el-checkbox label="volume">10. 大量分录异常账户</el-checkbox>
            </div>
            <!-- 规则11: 特殊事件 -->
            <div class="rule-item">
              <el-checkbox label="special">11. 特殊事件</el-checkbox>
            </div>
            <!-- 规则12: 含模糊词 -->
            <div class="rule-item">
              <el-checkbox label="vague">12. 含模糊词</el-checkbox>
              <div v-if="enabledRules.includes('vague')" class="rule-params">
                <span>关键词</span>
                <el-input :model-value="ruleParams.vagueKeywordsText" :disabled="isReadonly" size="small" placeholder="逗号分隔：调整,暂估,其他" @input="onParamChange('vagueKeywordsText', $event)" />
              </div>
            </div>
            <!-- 规则13: 没有摘要 -->
            <div class="rule-item">
              <el-checkbox label="empty">13. 没有摘要</el-checkbox>
            </div>
          </div>
        </el-checkbox-group>
      </el-card>
    </section>

    <!-- 异常分录结果表 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">异常分录（{{ anomalies.length }} 条）</span>
        <span class="unit-label">单位：元</span>
      </div>
      <el-alert v-if="!hasData" type="info" :closable="false" show-icon style="margin-bottom: 12px;">
        尚未导入分录或未执行筛选。
      </el-alert>
      <el-alert v-else-if="anomalies.length === 0" type="success" :closable="false" show-icon style="margin-bottom: 12px;">
        未筛选出异常分录。
      </el-alert>
      <!-- Req 11.3: 建议扩大核查范围 — 异常分录聚集 -->
      <el-alert
        v-if="expandScopeWarning"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 12px;"
        data-testid="expand-scope-alert"
      >
        {{ expandScopeWarning }}
      </el-alert>

      <el-table v-if="anomalies.length > 0" :data="anomalies" border size="small" class="c24-table" max-height="500">
        <el-table-column label="凭证日期" width="100">
          <template #default="{ row }"><span class="formula-cell" title="来源：分录筛选结果 - 凭证日期">{{ row.entry.voucherDate }}</span></template>
        </el-table-column>
        <el-table-column label="凭证编号" width="100">
          <template #default="{ row }"><span class="formula-cell" title="来源：分录筛选结果 - 凭证编号">{{ row.entry.voucherNo }}</span></template>
        </el-table-column>
        <el-table-column label="摘要" min-width="140">
          <template #default="{ row }"><span class="formula-cell" title="来源：分录筛选结果 - 摘要">{{ row.entry.summary || '—' }}</span></template>
        </el-table-column>
        <el-table-column label="科目" min-width="120">
          <template #default="{ row }"><span class="formula-cell" title="来源：分录筛选结果 - 科目">{{ row.entry.accountName }}</span></template>
        </el-table-column>
        <el-table-column label="借方" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell" title="来源：分录筛选结果 - 借方金额">{{ row.entry.debit ? fmtAmount(row.entry.debit) : '' }}</span></template>
        </el-table-column>
        <el-table-column label="贷方" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell" title="来源：分录筛选结果 - 贷方金额">{{ row.entry.credit ? fmtAmount(row.entry.credit) : '' }}</span></template>
        </el-table-column>
        <el-table-column label="异常事项" min-width="150">
          <template #default="{ row }">
            <el-tag v-for="r in row.reasons" :key="r" size="small" type="warning" style="margin: 1px 2px;">{{ r }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="核查内容" min-width="140">
          <template #default="{ row, $index }">
            <el-input :model-value="anomalyNotes[$index]?.checkContent || ''" :disabled="isReadonly" size="small" placeholder="核查说明" @input="onAnomalyChange($index, 'checkContent', $event)" />
          </template>
        </el-table-column>
        <el-table-column label="结论" width="130">
          <template #default="{ row, $index }">
            <el-select :model-value="anomalyNotes[$index]?.conclusion || ''" :disabled="isReadonly" size="small" placeholder="结论" @change="onConclusionSelect($index, $event)">
              <el-option label="正常" value="正常" />
              <el-option label="异常-已解释" value="异常-已解释" />
              <el-option label="异常-错报" value="异常-错报" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="120">
          <template #default="{ row, $index }">
            <GtIndexChip v-if="anomalyNotes[$index]?.indexRef" :value="anomalyNotes[$index].indexRef!" :context="buildIndexContext(row, $index)" />
            <el-input
              v-else
              :model-value="anomalyNotes[$index]?.indexRef || ''"
              :disabled="isReadonly"
              size="small"
              placeholder="索引号"
              @input="onAnomalyChange($index, 'indexRef', $event)"
            />
          </template>
        </el-table-column>
        <!-- 📎 核查证据上传列 (Req 10.2) -->
        <el-table-column label="📎" width="60" align="center">
          <template #default="{ row, $index }">
            <div class="attach-cell">
              <!-- 已有附件 -->
              <el-tooltip
                v-if="evidenceAttachments[$index]"
                :content="evidenceAttachments[$index]!.fileName"
                placement="top"
              >
                <a
                  :href="`/api/attachments/${evidenceAttachments[$index]!.id}/download`"
                  target="_blank"
                  class="attach-link"
                  @click.stop
                >📎</a>
              </el-tooltip>
              <!-- 上传按钮 (非只读) -->
              <el-upload
                v-if="!isReadonly"
                :auto-upload="true"
                :show-file-list="false"
                accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.doc,.docx"
                :http-request="(req: any) => onUploadEvidence($index, req.file)"
              >
                <el-button
                  size="small"
                  :icon="UploadFilled"
                  circle
                  :loading="uploadingRow === $index"
                  :title="evidenceAttachments[$index] ? '重新上传' : '上传证据'"
                />
              </el-upload>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 测试结论 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">测试结论</span>
        <el-button v-if="!isReadonly" size="small" @click="$emit('ai-suggest', 'C24-5-conclusion')">AI 辅助</el-button>
      </div>
      <el-input
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :model-value="conclusion"
        :disabled="isReadonly"
        placeholder="请填写异常分录测试结论"
        @input="$emit('update:conclusion', $event)"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * C24AnomalyEntrySheet — C24-5 异常分录测试
 *
 * 📎 核查证据上传 + OCR 辅助（Req 10.2, 10.4, 10.5）
 *
 * Task: 8.2
 * Requirements: 10.2, 10.4, 10.5
 */
import { ref, computed, onMounted, defineAsyncComponent } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { api } from '@/services/apiProxy'
import { uploadAttachment } from '@/services/commonApi'
import type { AnomalyResult } from '@/composables/useC24AnalyticsEngine'
import { fmtAmount } from '@/utils/formatters'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

export interface RuleParams {
  nightStartHour: number
  nightEndHour: number
  largeAmountThreshold: number
  approvalLimit: number
  roundAmountDigits: number
  vagueKeywordsText: string  // comma-separated
}

export interface AnomalyNote {
  checkContent: string
  conclusion: string
  indexRef?: string
}

/** 证据附件信息 */
export interface EvidenceAttachment {
  id: string
  fileName: string
  ocrMerged: boolean
}

const props = defineProps<{
  wpId: string
  projectId?: string
  enabledRules: string[]
  ruleParams: RuleParams
  anomalies: AnomalyResult[]
  anomalyNotes: AnomalyNote[]
  hasData: boolean
  conclusion: string
  isReadonly: boolean
  totalEntryCount?: number  // 总分录数，用于计算异常占比
}>()

const emit = defineEmits<{
  (e: 'update:conclusion', val: string): void
  (e: 'update:enabled-rules', rules: string[]): void
  (e: 'update:rule-param', key: keyof RuleParams, value: any): void
  (e: 'update:anomaly-note', index: number, field: string, value: string): void
  (e: 'run-screen'): void
  (e: 'ai-suggest', fieldId: string): void
  (e: 'evidence-uploaded', index: number, attachment: EvidenceAttachment): void
  (e: 'conclusion-change', conclusion: string): void
}>()

// ─── Req 11.3: 扩大核查范围提示 (异常分录聚集) ───
const ANOMALY_COUNT_THRESHOLD = 10
const ANOMALY_RATIO_THRESHOLD = 0.05 // 5%

const expandScopeWarning = computed<string>(() => {
  if (!props.hasData || props.anomalies.length === 0) return ''
  const total = props.totalEntryCount || 0
  if (props.anomalies.length > ANOMALY_COUNT_THRESHOLD) {
    if (total > 0) {
      const ratio = props.anomalies.length / total
      if (ratio > ANOMALY_RATIO_THRESHOLD) {
        return `建议扩大核查范围：异常分录占比较高（${props.anomalies.length}/${total}，${(ratio * 100).toFixed(1)}%）`
      }
    }
    return `建议扩大核查范围：异常分录数量较多（${props.anomalies.length} 条）`
  }
  if (total > 0 && (props.anomalies.length / total) > ANOMALY_RATIO_THRESHOLD) {
    return `建议扩大核查范围：异常分录占比较高（${props.anomalies.length}/${total}，${((props.anomalies.length / total) * 100).toFixed(1)}%）`
  }
  return ''
})

// ─── Req 11.1: 异常确认错报 → 自动设置 indexRef=A13 + GtIndexChip 跳转 ───

/**
 * 当结论选择为"异常-错报"时，自动填入 indexRef = "A13"
 * 并可跳转到相关循环底稿（根据科目编码推断循环）
 */
function onConclusionSelect(index: number, value: string) {
  emit('update:anomaly-note', index, 'conclusion', value)
  // Req 11.1: 确认错报 → 自动设置 A13 跳转
  if (value === '异常-错报') {
    const currentRef = props.anomalyNotes[index]?.indexRef
    if (!currentRef) {
      // 自动填入 A13（错报汇总底稿）
      emit('update:anomaly-note', index, 'indexRef', 'A13')
    }
  }
  // 通知父组件结论变更（用于 C24-0 回填）
  emit('conclusion-change', value)
}

/**
 * 构建 GtIndexChip 上下文 — 带入分录摘要等信息
 * 供 A13 跳转时携带上下文参数
 */
function buildIndexContext(row: AnomalyResult, index: number): Record<string, string> {
  const ctx: Record<string, string> = {}
  if (row.entry) {
    if (row.entry.voucherDate) ctx.voucherDate = row.entry.voucherDate
    if (row.entry.debit) ctx.amount = String(row.entry.debit)
    else if (row.entry.credit) ctx.amount = String(row.entry.credit)
    if (row.entry.accountName) ctx.account = row.entry.accountName
    if (row.entry.accountCode) ctx.accountCode = row.entry.accountCode
    if (row.entry.summary) ctx.summary = row.entry.summary
    if (row.entry.voucherNo) ctx.voucherNo = row.entry.voucherNo
  }
  ctx.source = 'C24-5'
  return ctx
}

// ─── Evidence attachment state ───
const evidenceAttachments = ref<Array<EvidenceAttachment | null>>([])
const uploadingRow = ref<number | null>(null)

onMounted(async () => {
  evidenceAttachments.value = new Array(props.anomalies.length).fill(null)
  await loadEvidenceAttachments()
})

/** 从 checklist_responses 加载已有证据附件 */
async function loadEvidenceAttachments() {
  if (!props.wpId) return
  try {
    const res = await api.get<any[]>(
      `/api/workpapers/${props.wpId}/checklist-responses`,
      { _silent: true } as any,
    )
    const items: Array<{ item_id: string; conclusion?: string; remark?: string }> =
      Array.isArray(res) ? res : (res as any)?.data || []

    for (const item of items) {
      // item_id 格式: C24-5-anomaly-{i}-evidence
      const m = item.item_id?.match(/^C24-5-anomaly-(\d+)-evidence$/)
      if (m && item.remark) {
        const idx = parseInt(m[1])
        if (idx >= 0 && idx < evidenceAttachments.value.length) {
          try {
            evidenceAttachments.value[idx] = JSON.parse(item.remark)
          } catch { /* ignore */ }
        }
      }
    }
  } catch { /* silent */ }
}

/** 上传核查证据 + OCR 辅助识别 */
async function onUploadEvidence(index: number, file: File) {
  if (props.isReadonly) return
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('文件大小不能超过 50MB')
    return
  }

  uploadingRow.value = index
  try {
    // 1) 上传附件
    const fd = new FormData()
    fd.append('file', file)
    fd.append('attachment_type', 'evidence')
    fd.append('reference_type', 'workpaper')
    fd.append('reference_id', props.wpId)
    fd.append('title', `${file.name} [C24-5 异常分录${index + 1} 核查证据]`)

    const uploadResp = await uploadAttachment(props.projectId || '', fd)
    const attachmentId: string | undefined = uploadResp?.id || uploadResp?.attachment_id
    if (!attachmentId) throw new Error('上传响应缺少 attachment_id')

    // 关联到底稿
    try {
      await api.post(`/api/attachments/${attachmentId}/associate`, {
        wp_id: props.wpId,
        association_type: 'evidence',
        notes: `C24-5-anomaly-${index}`,
      })
    } catch { /* 关联失败不阻断 */ }

    // 存储附件引用
    const attachment: EvidenceAttachment = { id: attachmentId, fileName: file.name, ocrMerged: false }
    // 确保数组足够长
    while (evidenceAttachments.value.length <= index) {
      evidenceAttachments.value.push(null)
    }
    evidenceAttachments.value[index] = attachment
    emit('evidence-uploaded', index, attachment)

    // 持久化
    await persistEvidence(index, attachment)

    ElMessage.success(`核查证据 "${file.name}" 已上传`)

    // 2) OCR 辅助（图片/PDF）
    if (isOcrEligible(file.name)) {
      await doOcrAssist(file, index)
    }
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || '上传失败'
    ElMessage.error(`核查证据上传失败：${detail}`)
  } finally {
    uploadingRow.value = null
  }
}

function isOcrEligible(filename: string): boolean {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  return ['pdf', 'png', 'jpg', 'jpeg', 'tif', 'tiff'].includes(ext)
}

/**
 * OCR 辅助填充核查内容（Req 10.2）
 * 识别证据内容，辅助填充核查描述
 */
async function doOcrAssist(file: File, index: number): Promise<void> {
  const formData = new FormData()
  formData.append('file', file)
  let ocrFields: Record<string, any>
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    ocrFields = (res.data?.data ?? res.data)?.extracted_fields || {}
  } catch {
    // OCR 失败（Req 10.4）：不阻断，附件已保留
    ElMessage.info('OCR 辅助识别失败，请手动填写核查内容')
    return
  }

  if (!ocrFields || Object.keys(ocrFields).length === 0) {
    return // 静默
  }

  // 组织可填充信息
  const parts: string[] = []
  if (ocrFields.summary || ocrFields['摘要']) parts.push(`摘要：${ocrFields.summary || ocrFields['摘要']}`)
  if (ocrFields.voucher_no || ocrFields['凭证号']) parts.push(`凭证号：${ocrFields.voucher_no || ocrFields['凭证号']}`)
  if (ocrFields.date || ocrFields['日期']) parts.push(`日期：${ocrFields.date || ocrFields['日期']}`)
  if (ocrFields.amount || ocrFields['金额']) parts.push(`金额：${ocrFields.amount || ocrFields['金额']}`)
  if (ocrFields.preparer || ocrFields['制单人']) parts.push(`制单人：${ocrFields.preparer || ocrFields['制单人']}`)

  if (parts.length === 0) return

  const previewMsg = parts.join('\n')
  try {
    await ElMessageBox.confirm(
      `OCR 识别到以下信息，是否填入核查内容？\n\n${previewMsg}`,
      'OCR 辅助识别',
      { confirmButtonText: '填入核查内容', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return // 用户取消
  }

  // merge 到核查内容
  const mergeText = parts.join('；')
  const current = props.anomalyNotes[index]?.checkContent || ''
  const sep = current.trim() ? '；' : ''
  emit('update:anomaly-note', index, 'checkContent', current + sep + mergeText)

  // 标记 OCR 已 merge
  if (evidenceAttachments.value[index]) {
    evidenceAttachments.value[index]!.ocrMerged = true
    await persistEvidence(index, evidenceAttachments.value[index]!)
  }
  ElMessage.success('已将 OCR 信息填入核查内容')
}

/** 持久化证据附件信息（Req 10.5） */
async function persistEvidence(index: number, attachment: EvidenceAttachment) {
  if (!props.wpId) return
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId || undefined,
      items: [{
        item_id: `C24-5-anomaly-${index}-evidence`,
        conclusion: null,
        remark: JSON.stringify(attachment),
      }],
    })
  } catch { /* silent */ }
}

function onRulesChange(rules: string[]) {
  emit('update:enabled-rules', rules)
}

function onParamChange(key: keyof RuleParams, value: any) {
  emit('update:rule-param', key, value)
}

function onAnomalyChange(index: number, field: string, value: string) {
  emit('update:anomaly-note', index, field, value)
}
</script>

<style scoped>
.c24-anomaly-entry { font-size: 13px; }
.methodology-context { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; margin-bottom: 16px; background: #fffbf0; border-radius: 4px; }
.methodology-bar { width: 3px; min-height: 20px; align-self: stretch; background: #e6a23c; border-radius: 2px; flex-shrink: 0; }
.methodology-context p { margin: 0; font-size: 13px; color: #606266; line-height: 1.6; }
.c24-section { margin-bottom: 20px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.section-title { font-weight: 600; font-size: 14px; color: #303133; }
.c24-table { font-size: 13px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; color: #409eff; }
.rules-card { margin-bottom: 16px; }
.rules-card :deep(.el-card__body) { padding: 12px 16px; }
.rules-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.rule-item { display: flex; flex-direction: column; gap: 4px; padding: 4px 0; }
.rule-params { display: flex; align-items: center; gap: 6px; padding-left: 24px; font-size: 12px; color: #606266; }
.rule-params .el-input-number { width: 100px; }
.rule-params .el-input { width: 200px; }
.unit-label { font-size: 12px; color: #909399; font-weight: normal; }

/* 📎 附件单元格 */
.attach-cell { display: flex; align-items: center; justify-content: center; gap: 4px; }
.attach-link { text-decoration: none; font-size: 14px; cursor: pointer; }
.attach-link:hover { opacity: 0.7; }
.attach-cell :deep(.el-upload) { display: inline-flex; }
.attach-cell :deep(.el-button.is-circle) { width: 24px; height: 24px; padding: 0; }
</style>
