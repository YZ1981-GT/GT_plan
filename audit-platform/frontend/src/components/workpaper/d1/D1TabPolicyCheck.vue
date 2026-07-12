<script setup lang="ts">
/**
 * D1TabPolicyCheck.vue — D1-14 应收票据坏账准备会计政策检查
 *
 * Spec: .kiro/specs/d1-ecl-provision/
 * Task: 6.1
 *
 * 段落式左右分栏布局的5个section：
 * - Section 1: 底稿抬头 + 审计目标（只读info alert）
 * - Section 2: 政策概述（左侧描述4个textarea + 右侧核查意见）
 * - Section 3: ECL模型描述（左侧3个textarea + 右侧核查意见）
 * - Section 4: 政策变更（是/否条件展开）
 * - Section 5: 审计结论（合理性评价 + AI + 复核对话）
 *
 * Requirements: 1.1-5.5, 11.1-11.5, 15.6
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useD1PolicyCheck,
  type PolicyConclusion,
  type PolicyChangeFlag,
} from '../composables/useD1PolicyCheck'
import type { ChecklistResponse } from '../composables/useD1FormData'
import type { Ref } from 'vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useD1AiGenerate } from '../composables/useD1AiGenerate'
import { useD1TabImportExport } from '../composables/useD1TabImportExport'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

interface Props {
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
  displayPrefs: any
}

const props = withDefaults(defineProps<Props>(), {
  isReadonly: false,
})

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const wpIdImportRef = toRef(props, 'wpId') as unknown as Ref<string>
const { onExportTemplate, onExportData, onImportFile } = useD1TabImportExport(wpIdImportRef, 'D1-14')

// ─── Save helpers ────────────────────────────────────────────────────────────

async function saveImmediate(items: any[]): Promise<void> {
  if (props.isReadonly) return
  try {
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
  } catch {
    ElMessage.warning('保存失败，请重试')
  }
}

let debounceTimer: ReturnType<typeof setTimeout> | null = null
async function debouncedSave(items: any[]): Promise<void> {
  if (props.isReadonly) return
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(async () => {
    try {
      await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
    } catch {
      ElMessage.warning('保存失败，请重试')
    }
  }, 2000)
}

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  // Section 2
  policyOverviewLeft,
  policyOverviewRight,
  savePolicyOverview,
  // Section 3
  eclModelPortfolio,
  eclModelIndividual,
  eclModelMigration,
  eclModelRight,
  saveEclModel,
  // Section 4
  policyChangeFlag,
  policyChangeContent,
  policyChangeReason,
  showPolicyChangeDetails,
  setPolicyChangeFlag,
  savePolicyChange,
  // Section 5
  policyConclusion,
  conclusionText,
  setPolicyConclusion,
  saveConclusionText,
  // Loading
  isLoading,
  hydrate,
} = useD1PolicyCheck({
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  saveImmediate,
  debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
})

// ─── Audit Objective (static) ────────────────────────────────────────────────

const auditObjectiveText = '检查公司应收票据坏账准备的会计政策是否符合《企业会计准则第22号——金融工具确认和计量》的规定，评价预期信用损失模型的适当性，核实会计政策在各期间是否一贯适用，并对政策合理性形成审计结论。'

// ─── AI Generate ─────────────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD1AiGenerate(wpIdRef)
const aiLoadingOverview = ref(false)
const aiLoadingEclModel = ref(false)
const writebackPreviewVisible = ref(false)
const writebackPreviewTitle = ref('')
const writebackPreviewItems = ref<Array<{ key: string; label: string; value: string; checked: boolean }>>([])
const pendingWritebackScope = ref<'overview' | 'ecl' | ''>('')

function escapeRegex(input: string): string {
  return input.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 容错解析 AI 文本中的“标签：内容”多段结构。
 * 支持：
 * - 中文/英文冒号（：/:）
 * - 标签前编号（1. / 1、 / （1））
 * - 多行段落内容，直到下一个标签开始
 */
function extractLabelSections(text: string, labels: string[]): Record<string, string> {
  const result: Record<string, string> = {}
  const normalized = (text || '').replace(/\r\n/g, '\n')
  if (!normalized.trim()) return result

  const positions: Array<{ label: string; idx: number; start: number }> = []
  for (const label of labels) {
    const marker = new RegExp(String.raw`(?:^|\s)(?:[（(]?\d+[)）.、]?\s*)?${escapeRegex(label)}\s*[：:]`, 'm')
    const matched = marker.exec(normalized)
    if (!matched || matched.index < 0) continue
    const start = matched.index + matched[0].length
    positions.push({ label, idx: matched.index, start })
  }
  if (positions.length === 0) return result
  positions.sort((a, b) => a.idx - b.idx)

  for (let i = 0; i < positions.length; i++) {
    const current = positions[i]
    const next = positions[i + 1]
    const end = next ? next.idx : normalized.length
    const content = normalized.slice(current.start, end).trim()
    if (content) {
      result[current.label] = content
    }
  }
  return result
}

function openWritebackPreview(
  title: string,
  scope: 'overview' | 'ecl',
  sectionMap: Record<string, string>,
  labels: string[],
) {
  const items = labels
    .map((label) => ({
      key: label,
      label,
      value: sectionMap[label] || '',
      checked: Boolean(sectionMap[label]),
    }))
    .filter((item) => item.value)
  if (items.length === 0) {
    ElMessage.warning('AI 未生成可回写字段')
    return
  }
  writebackPreviewTitle.value = title
  pendingWritebackScope.value = scope
  writebackPreviewItems.value = items
  writebackPreviewVisible.value = true
}

function applySelectedWriteback() {
  const selected = writebackPreviewItems.value.filter((item) => item.checked)
  if (selected.length === 0) {
    ElMessage.info('请至少勾选一个字段')
    return
  }
  if (pendingWritebackScope.value === 'overview') {
    for (const item of selected) {
      if (item.key === '公司政策描述') policyOverviewLeft.value = item.value
      if (item.key === '审计师核查意见') policyOverviewRight.value = item.value
    }
    savePolicyOverview()
  } else if (pendingWritebackScope.value === 'ecl') {
    for (const item of selected) {
      if (item.key === '组合评估方法') eclModelPortfolio.value = item.value
      if (item.key === '单项评估标准') eclModelIndividual.value = item.value
      if (item.key === '迁徙率法参数') eclModelMigration.value = item.value
      if (item.key === '审计师核查意见') eclModelRight.value = item.value
    }
    saveEclModel()
  }
  writebackPreviewVisible.value = false
  pendingWritebackScope.value = ''
  ElMessage.success(`已回写 ${selected.length} 个字段`)
}

function selectAllWritebackItems() {
  writebackPreviewItems.value.forEach((item) => { item.checked = true })
}

function clearAllWritebackItems() {
  writebackPreviewItems.value.forEach((item) => { item.checked = false })
}

function buildPolicyContext(): string {
  return [
    `【政策概述-公司描述】${policyOverviewLeft.value || '（未填写）'}`,
    `【政策概述-核查意见】${policyOverviewRight.value || '（未填写）'}`,
    `【ECL模型-组合评估】${eclModelPortfolio.value || '（未填写）'}`,
    `【ECL模型-单项评估】${eclModelIndividual.value || '（未填写）'}`,
    `【ECL模型-迁徙率法】${eclModelMigration.value || '（未填写）'}`,
    `【ECL模型-核查意见】${eclModelRight.value || '（未填写）'}`,
    `【政策变更】${policyChangeFlag.value === '是' ? `是。变更内容：${policyChangeContent.value || '（未填写）'}；变更原因：${policyChangeReason.value || '（未填写）'}` : '否'}`,
    `【合理性评价】${policyConclusion.value || '（未选择）'}`,
  ].join('\n')
}

async function generateConclusionWithAI() {
  const text = await generateAndConfirm(
    'policy-conclusion',
    buildPolicyContext(),
    { guidance: guidanceContent, currentConclusion: conclusionText.value },
    'AI辅助生成',
  )
  if (text) {
    conclusionText.value = text
    saveConclusionText()
  }
}

async function generateOverviewWithAI() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingOverview.value = true
  try {
    const text = await generateAndConfirm(
      'ecl-audit-note',
      [
        `公司政策描述：${policyOverviewLeft.value || ''}`,
        `审计师核查意见：${policyOverviewRight.value || ''}`,
      ].join('\n'),
      {
        sheet: 'D1-14',
        section: 'policy-overview',
        task: '请生成“公司政策描述”和“审计师核查意见”两部分，使用“公司政策描述：”“审计师核查意见：”作为前缀。',
      },
      'AI · 会计政策概述',
    )
    if (!text) return
    const sections = extractLabelSections(text, ['公司政策描述', '审计师核查意见'])
    openWritebackPreview('AI回写预览 · 会计政策概述', 'overview', sections, ['公司政策描述', '审计师核查意见'])
  } finally {
    aiLoadingOverview.value = false
  }
}

async function generateEclModelWithAI() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingEclModel.value = true
  try {
    const text = await generateAndConfirm(
      'ecl-audit-note',
      [
        `组合评估方法：${eclModelPortfolio.value || ''}`,
        `单项评估标准：${eclModelIndividual.value || ''}`,
        `迁徙率法参数：${eclModelMigration.value || ''}`,
        `审计师核查意见：${eclModelRight.value || ''}`,
      ].join('\n'),
      {
        sheet: 'D1-14',
        section: 'ecl-model',
        task: '请生成“组合评估方法、单项评估标准、迁徙率法参数、审计师核查意见”四部分，分别用同名前缀输出。',
      },
      'AI · ECL模型描述',
    )
    if (!text) return
    const sections = extractLabelSections(text, ['组合评估方法', '单项评估标准', '迁徙率法参数', '审计师核查意见'])
    openWritebackPreview(
      'AI回写预览 · ECL模型描述',
      'ecl',
      sections,
      ['组合评估方法', '单项评估标准', '迁徙率法参数', '审计师核查意见'],
    )
  } finally {
    aiLoadingEclModel.value = false
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  hydrate()
})

// ─── Review Dialog ───────────────────────────────────────────────────────────

function handleOpenReview() {
  openReviewDialog?.('D1-policy-conclusion')
}

// ─── Guidance Content ────────────────────────────────────────────────────────

const guidanceContent = `1. CAS 22 金融工具确认与计量中ECL三阶段模型说明：
   - 第一阶段：信用风险自初始确认后未显著增加，按12个月预期信用损失计量
   - 第二阶段：信用风险显著增加但尚未发生信用减值，按整个存续期预期信用损失计量
   - 第三阶段：已发生信用减值，按整个存续期预期信用损失计量

2. 组合评估vs单项评估的选择标准：
   - 单项评估：单项金额重大或虽不重大但有客观证据表明已发生减值
   - 组合评估：未单项评估或单项评估未减值的，按信用风险特征分组计算

3. 政策变更需关注的会计估计变更披露要求（CAS 28）：
   - 变更性质和原因、对当期和未来各期的影响金额
   - 区分会计政策变更与会计估计变更（ECL参数调整通常为估计变更）

4. 预期信用损失率合理性判断标准：
   - 与同行业上市公司披露的损失率比较
   - 与历史实际损失率趋势一致性
   - 前瞻性因素调整的合理性（宏观经济、行业风险）`
</script>

<template>
  <div class="d1-policy-check">
    <div>
      <!-- Loading Skeleton -->
      <el-skeleton v-if="isLoading" :rows="12" animated />

      <template v-else>
        <div class="tab-header">
          <h4>会计政策检查 D1-14</h4>
          <div class="toolbar-right">
            <GtReviewTrigger section-id="D1-policy-header" />
            <el-button size="small" @click="onExportTemplate">导出模板</el-button>
            <el-button size="small" @click="onExportData">导出数据</el-button>
            <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
              <el-button size="small">导入数据</el-button>
            </el-upload>
          </div>
        </div>
        <div class="section">
          <el-alert
            type="info"
            :closable="false"
            show-icon
          >
            <template #title>
              <strong>审计目标</strong>
            </template>
            {{ auditObjectiveText }}
          </el-alert>
        </div>

        <!-- Section 2: 政策概述 左右分栏 -->
        <div class="section">
          <div class="section-title-row">
            <h3 class="section-title">一、公司坏账准备会计政策概述</h3>
            <el-tooltip :content="aiAvailable ? 'AI辅助生成本模块内容' : 'AI服务暂不可用'" placement="top">
              <el-button
                size="small"
                :loading="aiLoadingOverview"
                :disabled="isReadonly || !aiAvailable"
                @click="generateOverviewWithAI"
              >
                🤖 AI
              </el-button>
            </el-tooltip>
          </div>
          <el-row :gutter="16">
            <el-col :lg="14" :md="12">
              <div class="left-panel">
                <div class="panel-label">公司政策描述</div>
                <el-input
                  v-model="policyOverviewLeft"
                  type="textarea"
                  :rows="8"
                  :disabled="isReadonly"
                  placeholder="请描述公司应收票据坏账准备会计政策内容（ECL方法概述、组合评估范围、账龄划分标准、损失率确定依据）"
                  @input="savePolicyOverview"
                />
              </div>
            </el-col>
            <el-col :lg="10" :md="12">
              <div class="right-panel" :class="{ filled: !!policyOverviewRight }">
                <div class="panel-label">审计师核查意见</div>
                <el-input
                  v-model="policyOverviewRight"
                  type="textarea"
                  :rows="8"
                  :disabled="isReadonly"
                  placeholder="请填写对公司坏账准备政策的核查意见"
                  @input="savePolicyOverview"
                />
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- Section 3: ECL模型描述 左右分栏 -->
        <div class="section">
          <div class="section-title-row">
            <h3 class="section-title">二、预期信用损失模型描述</h3>
            <el-tooltip :content="aiAvailable ? 'AI辅助生成本模块内容' : 'AI服务暂不可用'" placement="top">
              <el-button
                size="small"
                :loading="aiLoadingEclModel"
                :disabled="isReadonly || !aiAvailable"
                @click="generateEclModelWithAI"
              >
                🤖 AI
              </el-button>
            </el-tooltip>
          </div>
          <el-row :gutter="16">
            <el-col :lg="14" :md="12">
              <div class="left-panel">
                <div class="panel-label">组合评估方法</div>
                <el-input
                  v-model="eclModelPortfolio"
                  type="textarea"
                  :rows="4"
                  :disabled="isReadonly"
                  placeholder="描述按账龄/信用风险特征分组的方法和分组标准"
                  @input="saveEclModel"
                />

                <div class="panel-label" style="margin-top: 12px">单项评估标准</div>
                <el-input
                  v-model="eclModelIndividual"
                  type="textarea"
                  :rows="4"
                  :disabled="isReadonly"
                  placeholder="描述何时对单项应收款进行个别减值评估的条件"
                  @input="saveEclModel"
                />

                <div class="panel-label" style="margin-top: 12px">迁徙率法参数</div>
                <el-input
                  v-model="eclModelMigration"
                  type="textarea"
                  :rows="4"
                  :disabled="isReadonly"
                  placeholder="描述迁徙率计算的历史期间选择、数据来源、调整因素"
                  @input="saveEclModel"
                />
              </div>
            </el-col>
            <el-col :lg="10" :md="12">
              <div class="right-panel" :class="{ filled: !!eclModelRight }">
                <div class="panel-label">审计师核查意见</div>
                <el-input
                  v-model="eclModelRight"
                  type="textarea"
                  :rows="14"
                  :disabled="isReadonly"
                  placeholder="请填写对ECL模型适当性的核查意见"
                  @input="saveEclModel"
                />
              </div>
            </el-col>
          </el-row>
        </div>

        <!-- Section 4: 政策变更 -->
        <div class="section">
          <h3 class="section-title">三、会计政策变更说明</h3>
          <div class="change-flag-row">
            <span class="change-label">本期坏账准备会计政策是否发生变更：</span>
            <el-radio-group
              :model-value="policyChangeFlag"
              :disabled="isReadonly"
              @change="(val: PolicyChangeFlag) => setPolicyChangeFlag(val)"
            >
              <el-radio-button value="是">是</el-radio-button>
              <el-radio-button value="否">否</el-radio-button>
            </el-radio-group>
          </div>

          <template v-if="showPolicyChangeDetails">
            <div class="change-detail">
              <div class="panel-label">变更内容</div>
              <el-input
                v-model="policyChangeContent"
                type="textarea"
                :rows="4"
                :disabled="isReadonly"
                placeholder="请描述政策变更的具体内容"
                @input="savePolicyChange"
              />
            </div>
            <div class="change-detail">
              <div class="panel-label">变更原因及合理性说明</div>
              <el-input
                v-model="policyChangeReason"
                type="textarea"
                :rows="4"
                :disabled="isReadonly"
                placeholder="请描述政策变更的原因及合理性"
                @input="savePolicyChange"
              />
            </div>
          </template>
          <div v-else-if="policyChangeFlag === '否'" class="no-change-hint">
            本期无政策变更
          </div>
        </div>

        <!-- Section 5: 审计结论 -->
        <div class="section">
          <h3 class="section-title">四、审计结论</h3>
          <div class="conclusion-radio">
            <span class="change-label">政策合理性评价：</span>
            <el-radio-group
              :model-value="policyConclusion"
              :disabled="isReadonly"
              @change="(val: PolicyConclusion) => setPolicyConclusion(val)"
            >
              <el-radio-button value="合理">合理</el-radio-button>
              <el-radio-button value="基本合理但需关注">基本合理但需关注</el-radio-button>
              <el-radio-button value="不合理">不合理</el-radio-button>
            </el-radio-group>
          </div>

          <div class="conclusion-text">
            <div class="panel-label">审计结论</div>
            <el-input
              v-model="conclusionText"
              type="textarea"
              :rows="6"
              :disabled="isReadonly"
              placeholder="请填写审计结论"
              @input="saveConclusionText"
            />
            <div class="conclusion-actions">
              <el-tooltip :content="aiAvailable ? 'AI辅助生成' : 'AI服务暂不可用'" placement="top">
                <el-button
                  size="small"
                  :disabled="!aiAvailable || aiLoading"
                  :loading="aiLoading"
                  @click="generateConclusionWithAI"
                >
                  🤖 AI生成
                </el-button>
              </el-tooltip>
              <el-tooltip content="发起复核对话" placement="top">
                <el-button
                  size="small"
                  @click="handleOpenReview"
                >
                  💬 复核
                </el-button>
              </el-tooltip>
            </div>
          </div>

          <!-- 编制提示折叠区 -->
          <details class="guidance-details">
            <summary>📋 编制提示</summary>
            <pre class="guidance-content">{{ guidanceContent }}</pre>
          </details>
        </div>
      </template>
    </div>
    <el-dialog v-model="writebackPreviewVisible" :title="writebackPreviewTitle" width="640px" destroy-on-close>
      <div class="writeback-preview">
        <div class="writeback-toolbar">
          <el-button size="small" @click="selectAllWritebackItems">全选</el-button>
          <el-button size="small" @click="clearAllWritebackItems">全不选</el-button>
        </div>
        <div
          v-for="item in writebackPreviewItems"
          :key="item.key"
          class="writeback-item"
        >
          <el-checkbox v-model="item.checked" class="writeback-item-check" />
          <div class="writeback-item-content">
            <div class="writeback-item-label">{{ item.label }}</div>
            <div class="writeback-item-value">{{ item.value }}</div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="writebackPreviewVisible = false">取消</el-button>
        <el-button type="primary" @click="applySelectedWriteback">确认回写</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.d1-policy-check {
  padding: 16px;
}

.tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tab-header h4 {
  margin: 0;
  font-size: 15px;
}

.section {
  margin-bottom: 24px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 0;
  color: #303133;
}

.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.left-panel {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
}

.right-panel {
  padding: 12px;
  border-radius: 4px;
}

.right-panel.filled {
  border-left: 3px solid #409eff;
}

.panel-label {
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  margin-bottom: 6px;
  font-weight: 500;
}

.change-flag-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.change-label {
  font-size: 14px;
  color: #303133;
}

.change-detail {
  margin-top: 12px;
}

.no-change-hint {
  color: #909399;
  font-size: 14px;
  padding: 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-top: 8px;
}

.conclusion-radio {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.conclusion-text {
  margin-top: 8px;
}

.conclusion-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.guidance-details {
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  padding: 12px;
  margin-top: 16px;
  border-radius: 4px;
}

.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
  font-size: 14px;
}

.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  white-space: pre-wrap;
  line-height: 1.6;
}

.writeback-preview {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 420px;
  overflow-y: auto;
  padding-right: 4px;
}

.writeback-toolbar {
  display: flex;
  gap: 8px;
}

.writeback-item {
  margin: 0;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.writeback-item-check {
  margin-top: 2px;
}

.writeback-item-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-left: 0;
  flex: 1;
  min-width: 0;
}

.writeback-item-label {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: #303133;
}

.writeback-item-value {
  font-size: 12px;
  line-height: 1.6;
  color: #606266;
  white-space: pre-wrap;
  word-break: break-word;
  background: #f5f7fa;
  border-radius: 4px;
  padding: 6px 8px;
}
</style>
