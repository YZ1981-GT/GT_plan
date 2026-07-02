<script setup lang="ts">
/**
 * D4TabOccurrence — D4-14 营业收入发生检查表（穿行测试）
 *
 * 三模式：卡片视图 / 矩阵视图 / 在线编辑
 * 多维穿行测试矩阵：每事项 × 7证据链维度
 * 支持维度级OCR、自动一致性校验、D4-12联动、AI穿行分析
 *
 * Spec: .kiro/specs/d4-14-walkthrough-test/ Phase 4
 */
import { ref, computed, inject, onBeforeUnmount } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import useD4WalkthroughTest, {
  type TransactionItem,
  mapD4ContractToDimension,
  mapLedgerToTransaction,
  mapOcrToDimension,
  collectAiContext,
} from '../../composables/useD4WalkthroughTest'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import D4WalkthroughCard from './D4WalkthroughCard.vue'
import D4WalkthroughMatrix from './D4WalkthroughMatrix.vue'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { Plus, Download } from '@element-plus/icons-vue'

// ─── Props ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── Composables ─────────────────────────────────────────────────────
const {
  transactions,
  samplingParams,
  auditNote,
  auditConclusion,
  totalVoucherAmount,
  coverageRate,
  anomalyRate,
  samplingProgress,
  addTransaction,
  removeTransaction,
  updateDimension,
  updateAuditNote,
  updateAuditConclusion,
  updateSamplingParams,
  reindexItems,
} = useD4WalkthroughTest({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  allResponses: computed(() => props.allResponses),
  isReadonly: computed(() => props.isReadonly),
})

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 4.1.1 Mode switching ────────────────────────────────────────────
const editorMode = ref<string>('卡片视图')
const modeOptions = ['卡片视图', '矩阵视图', '在线编辑']

// ─── OO + AI health ──────────────────────────────────────────────────
const ooHealthy = ref(false)
const aiAvailable = ref(false)
async function checkOoHealth() {
  try {
    const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    ooHealthy.value = res.data?.data?.healthy ?? res.data?.healthy ?? false
  } catch { ooHealthy.value = false }
}
async function checkAiHealth() {
  try {
    const res = await http.get('/api/ai/health', { _silent: true } as any)
    const s = res.data?.data?.status ?? res.data?.status
    aiAvailable.value = s === 'healthy' || s === 'degraded'
  } catch { aiAvailable.value = false }
}
checkOoHealth()
checkAiHealth()

// ─── 4.1.2 Overview banner ──────────────────────────────────────────
async function handleAddTransaction() {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入事项名称', '添加事项', {
      confirmButtonText: '确定', cancelButtonText: '取消',
      inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
    })
    const item = addTransaction(value.trim())
    activeTab.value = item.id
  } catch { /* cancelled */ }
}

// ─── 4.1.4 Card view (el-tabs) ──────────────────────────────────────
const activeTab = ref<string>('')

function handleTabRemove(tabId: string | number) {
  if (props.isReadonly) return
  removeTransaction(String(tabId))
  if (activeTab.value === String(tabId)) {
    activeTab.value = transactions.value[0]?.id ?? ''
  }
}

// ensure activeTab valid
function ensureActiveTab() {
  if (!transactions.value.length) { activeTab.value = ''; return }
  if (!transactions.value.find(t => t.id === activeTab.value)) {
    activeTab.value = transactions.value[0].id
  }
}

// ─── D4-12 contract reference ────────────────────────────────────────
const contractDialogVisible = ref(false)
let contractRefTarget = ''

const d4Contracts = computed<any[]>(() => {
  const raw = props.allResponses.get('D4-12-contracts-v2')
  if (!raw?.remark) return []
  try { return JSON.parse(raw.remark) } catch { return [] }
})

function openContractPicker(itemId: string) {
  contractRefTarget = itemId
  contractDialogVisible.value = true
}
function selectContract(contract: any) {
  const mapped = mapD4ContractToDimension(contract)
  for (const [field, val] of Object.entries(mapped)) {
    updateDimension(contractRefTarget, 'contract', field, val)
  }
  contractDialogVisible.value = false
  ElMessage.success('合同信息已填入')
}

// ─── 5.2 序时账导入 ──────────────────────────────────────────────────
const ledgerDialogVisible = ref(false)
const ledgerEntries = ref<any[]>([])
const selectedLedgerEntries = ref<any[]>([])
const ledgerLoading = ref(false)

async function openLedgerImport() {
  if (props.isReadonly) return
  ledgerLoading.value = true
  ledgerDialogVisible.value = true
  try {
    const res = await http.get(`/api/projects/${props.projectId}/auto-data/`, {
      params: { source: 'tb_ledger', account_prefix: '6001' },
      _silent: true,
    } as any)
    ledgerEntries.value = res.data?.data ?? res.data ?? []
  } catch {
    ElMessage.info('暂无可导入的序时账数据')
    ledgerDialogVisible.value = false
  } finally {
    ledgerLoading.value = false
  }
}

function confirmLedgerImport() {
  if (!selectedLedgerEntries.value.length) return
  for (const entry of selectedLedgerEntries.value) {
    const item = mapLedgerToTransaction(entry)
    transactions.value.push(item)
  }
  reindexItems()
  ledgerDialogVisible.value = false
  ElMessage.success(`成功导入 ${selectedLedgerEntries.value.length} 笔凭证`)
  selectedLedgerEntries.value = []
  ensureActiveTab()
}

// ─── OCR handling ────────────────────────────────────────────────────
async function handleOcrUpload(itemId: string, payload: { file: File; dimensionKey: string }) {
  const formData = new FormData()
  formData.append('file', payload.file)
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`, formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const data = res.data?.data ?? res.data
    const fields = data.extracted_fields || {}
    const mapped = mapOcrToDimension(fields, payload.dimensionKey)
    if (Object.keys(mapped).length) {
      const msg = Object.entries(mapped).map(([k, v]) => `${k}: ${v}`).join('\n')
      await ElMessageBox.confirm(`OCR识别到以下字段:\n${msg}\n\n是否填入？`, 'OCR结果', {
        confirmButtonText: '填入', cancelButtonText: '取消', type: 'info',
      })
      for (const [f, v] of Object.entries(mapped)) {
        updateDimension(itemId, payload.dimensionKey, f, v)
      }
    } else {
      ElMessage.info('OCR完成，未识别到可填充字段')
    }
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('OCR识别失败')
  }
}

// ─── AI walkthrough analysis ─────────────────────────────────────────
async function handleAiAnalyze(itemId: string) {
  if (!aiAvailable.value) return
  const item = transactions.value.find(t => t.id === itemId)
  if (!item) return
  try {
    const ctx = collectAiContext(item)
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/ai-generate`,
      { section: 'walkthrough-analysis', existingContent: '', relatedContext: ctx },
      { _silent: true } as any,
    )
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.alert(text, 'AI 穿行分析结果', { confirmButtonText: '确定', customStyle: { maxWidth: '600px' } })
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 分析失败')
  }
}

// ─── 4.1.6 Compilation tips ─────────────────────────────────────────
const COMPILATION_TIPS = [
  '1. 穿行测试应选取具有代表性的交易，从原始凭证追溯至财务报表，或从财务报表追溯至原始凭证',
  '2. 穿行测试的目的是了解交易的处理流程，确认对内部控制的了解是否完整和准确',
  '3. 每类重大交易至少选取一笔交易进行穿行测试',
  '4. 穿行测试应关注：交易的发起、审批、记录、处理和报告的全过程',
  '5. 注意识别控制偏差，评估控制是否按预期运行',
  '6. 穿行测试的结果应记录在工作底稿中，作为进一步审计程序设计的基础',
]

// ─── 4.1.7 Audit opinion AI ─────────────────────────────────────────
const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)

async function genNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiNoteLoading.value = true
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/ai-generate`,
      {
        section: 'adj-note',
        existingContent: auditNote.value || '',
        relatedContext: {
          task: '基于穿行测试已检查事项的覆盖度和一致性情况，生成审计说明',
          totalItems: transactions.value.length,
          anomalyRate: anomalyRate.value.toFixed(1) + '%',
          coverageRate: coverageRate.value.toFixed(1) + '%',
        },
      },
      { _silent: true } as any,
    )
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 审计说明', {
      confirmButtonText: '填入', cancelButtonText: '取消', type: 'info',
      customStyle: { maxWidth: '600px' },
    })
    updateAuditNote(text)
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败')
  } finally { aiNoteLoading.value = false }
}

async function genConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiConclusionLoading.value = true
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/ai-generate`,
      {
        section: 'adj-conclusion',
        existingContent: auditConclusion.value || '',
        relatedContext: {
          task: '基于穿行测试结果，生成审计结论',
          noteText: auditNote.value || '',
          anomalyRate: anomalyRate.value.toFixed(1) + '%',
          totalItems: transactions.value.length,
          targetSampleSize: samplingParams.value.targetSampleSize,
        },
      },
      { _silent: true } as any,
    )
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 审计结论', {
      confirmButtonText: '填入', cancelButtonText: '取消', type: 'info',
      customStyle: { maxWidth: '600px' },
    })
    updateAuditConclusion(text)
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败')
  } finally { aiConclusionLoading.value = false }
}

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

// ─── 4.1.9 Import/Export handlers ────────────────────────────────────
function handleExportTemplate() { exportTemplate('D4-14') }
function handleExportData() { exportData('D4-14') }
async function handleImportFile(uploadFile: any) {
  const file = uploadFile.raw || uploadFile
  await importData('D4-14', file)
}

// ─── Lifecycle ───────────────────────────────────────────────────────
ensureActiveTab()
</script>

<template>
  <div class="d4-occurrence">
    <!-- ═══ 顶部工具条 ═══ -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      </div>
      <div class="toolbar-right">
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false"
                  :disabled="isReadonly || importing" @change="handleImportFile">
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
        <GtIndexChip value="wp:D4-12" :context-project-id="projectId" />
        <GtIndexChip value="wp:D4-4" :context-project-id="projectId" />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-14-walkthrough')">
          💬 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 统计仪表板 ═══ -->
    <div class="stats-dashboard">
      <div class="stat-card stat-primary">
        <div class="stat-value">{{ coverageRate.toFixed(1) }}%</div>
        <div class="stat-label">检查比例</div>
        <el-progress :percentage="coverageRate" :stroke-width="4" :show-text="false"
          :color="coverageRate < 60 ? '#f56c6c' : '#67c23a'" class="stat-progress" />
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ transactions.length }}<span class="stat-unit">笔</span></div>
        <div class="stat-label">已检查事项</div>
        <el-progress :percentage="samplingProgress" :stroke-width="4" :show-text="false" class="stat-progress" />
      </div>
      <div class="stat-card" :class="{ 'stat-warn': anomalyRate > 0 }">
        <div class="stat-value">{{ anomalyRate.toFixed(1) }}%</div>
        <div class="stat-label">异常率</div>
      </div>
      <div class="stat-card stat-amount">
        <div class="stat-value">{{ totalVoucherAmount ? (totalVoucherAmount / 10000).toFixed(2) : '—' }}<span class="stat-unit">万元</span></div>
        <div class="stat-label">检查金额合计</div>
      </div>
      <div class="stat-actions">
        <el-button type="primary" :disabled="isReadonly" @click="handleAddTransaction">
          <el-icon :size="18" style="margin-right: 6px;"><Plus /></el-icon>添加事项
        </el-button>
        <el-button :disabled="isReadonly" @click="openLedgerImport">
          <el-icon :size="18" style="margin-right: 6px;"><Download /></el-icon>从序时账导入
        </el-button>
      </div>
    </div>

    <!-- ═══ 非OO内容区 ═══ -->
    <template v-if="editorMode !== '在线编辑'">
      <!-- 抽样参数区 -->
      <section class="section-block">
        <div class="section-header">
          <div class="section-title"><span>二、样本选取标准与规模</span></div>
          <el-tag type="info" size="small" effect="plain" class="section-ref">CAS 1314</el-tag>
        </div>
        <!-- 抽样方法论说明（源模板红字，默认折叠） -->
        <details class="methodology-collapse">
          <summary class="methodology-summary">📖 样本选取标准与规模说明（点击展开）</summary>
          <div class="sampling-methodology">
            <div class="method-row">
              <div class="method-item">
                <span class="method-key">测试总体</span>
                <span class="method-desc">如营业收入所有销售记账凭证共XX笔、金额XX元。</span>
              </div>
              <div class="method-item">
                <span class="method-key">特殊项目</span>
                <span class="method-desc">XX金额以上（大额）、关联方/关联交易形成的款项、XX异常款项全部纳入测试。</span>
              </div>
            </div>
            <div class="method-row">
              <div class="method-item">
                <span class="method-key">抽样总体</span>
                <span class="method-desc">测试总体扣除特定项目以外的样本，共XX笔、金额XX元。</span>
              </div>
              <div class="method-item">
                <span class="method-key">确定抽样大小</span>
                <span class="method-desc">（如果使用了样本计算器计算样本量，抽取XX笔；样本量计算过程记录见底稿XX；或编）</span>
              </div>
            </div>
            <div class="method-row">
              <div class="method-item full-width">
                <span class="method-key">抽样方法</span>
                <span class="method-desc">随机选样/系统选样/货币单元抽样/随意选样（非审计抽样适用）；使用IDEA（XX软件工具）产生XX笔随机数，金额XX元，占检查比例XX%（或编）。</span>
              </div>
            </div>
          </div>
        </details>
        <!-- 填报说明（引导用户操作流程） -->
        <div class="guide-strip">
          <span class="guide-strip-label">编制流程：</span>
          <el-tooltip content="确定检查总体范围、特定项目、抽样方法（随机/分层/MUS）及目标样本量" placement="bottom" :show-after="300">
            <span class="guide-chip">① 填写抽样参数</span>
          </el-tooltip>
          <span class="guide-arrow">→</span>
          <el-tooltip content="点击「添加事项」手动创建，或点击「从序时账导入」批量导入营业收入凭证作为检查对象" placement="bottom" :show-after="300">
            <span class="guide-chip">② 添加/导入事项</span>
          </el-tooltip>
          <span class="guide-arrow">→</span>
          <el-tooltip content="在卡片视图中按7个维度录入：记账凭证→销售合同→出库单→运输单→签收单→发票→其他。可上传附件📎触发OCR自动识别填充" placement="bottom" :show-after="300">
            <span class="guide-chip">③ 逐维度填写+📎OCR</span>
          </el-tooltip>
          <span class="guide-arrow">→</span>
          <el-tooltip content="系统自动交叉比对各维度的金额、品名、日期，不一致字段标红，生成0~100一致性分数" placement="bottom" :show-after="300">
            <span class="guide-chip">④ 查看一致性校验</span>
          </el-tooltip>
          <span class="guide-arrow">→</span>
          <el-tooltip content="对每笔事项选择结论：无异常 / 存在差异已解释 / 存在重大异常。可点击AI穿行分析辅助判断" placement="bottom" :show-after="300">
            <span class="guide-chip">⑤ 选检查结论</span>
          </el-tooltip>
          <span class="guide-arrow">→</span>
          <el-tooltip content="切换矩阵视图全局检视覆盖率和异常分布，在底部审计意见区填写说明与结论（可AI辅助生成）" placement="bottom" :show-after="300">
            <span class="guide-chip">⑥ 填审计意见</span>
          </el-tooltip>
        </div>
        <!-- 可编辑的实际参数 -->
        <div class="sampling-grid">
          <div class="sampling-item">
            <label>总体</label>
            <el-input v-model="samplingParams.testPopulation" size="small" :disabled="isReadonly"
              placeholder="如：本年度全部营业收入"
              @change="updateSamplingParams({ testPopulation: samplingParams.testPopulation })" />
          </div>
          <div class="sampling-item">
            <label>特定项目</label>
            <el-input v-model="samplingParams.specificItems" size="small" :disabled="isReadonly"
              placeholder="如：大额/期末/关联交易"
              @change="updateSamplingParams({ specificItems: samplingParams.specificItems })" />
          </div>
          <div class="sampling-item">
            <label>抽样总体</label>
            <el-input v-model="samplingParams.samplingPopulation" size="small" :disabled="isReadonly"
              placeholder="如：扣除特定项目后"
              @change="updateSamplingParams({ samplingPopulation: samplingParams.samplingPopulation })" />
          </div>
          <div class="sampling-item">
            <label>抽样方法</label>
            <el-input v-model="samplingParams.samplingMethod" size="small" :disabled="isReadonly"
              placeholder="如：随机抽样/分层抽样"
              @change="updateSamplingParams({ samplingMethod: samplingParams.samplingMethod })" />
          </div>
          <div class="sampling-item">
            <label>目标样本量</label>
            <el-input-number v-model="samplingParams.targetSampleSize" size="small" :min="0"
              :controls="false" style="width: 100%"
              :disabled="isReadonly"
              @change="updateSamplingParams({ targetSampleSize: samplingParams.targetSampleSize })" />
          </div>
          <div class="sampling-item sampling-progress-item">
            <label>已检查 / 目标</label>
            <div class="sampling-progress-display">
              <span class="checked-count">{{ transactions.length }}</span>
              <span class="checked-divider">/</span>
              <span class="checked-target">{{ samplingParams.targetSampleSize || '—' }}</span>
              <el-progress :percentage="samplingProgress" :stroke-width="6" :show-text="false"
                style="flex: 1; margin-left: 10px;" />
            </div>
          </div>
        </div>
      </section>

      <!-- 卡片视图 -->
      <section v-show="editorMode === '卡片视图'" class="section-block">
        <el-tabs v-model="activeTab" type="card" :closable="!isReadonly" @tab-remove="handleTabRemove">
          <el-tab-pane
            v-for="item in transactions" :key="item.id"
            :name="item.id" :label="`${item.indexNo} ${item.label}`"
          >
            <D4WalkthroughCard
              :item="item"
              :is-readonly="isReadonly"
              :wp-id="wpId"
              :project-id="projectId"
              :d4-contracts="d4Contracts"
              @update="(dimKey, field, value) => updateDimension(item.id, dimKey, field, value)"
              @ocr-upload="(payload) => handleOcrUpload(item.id, payload)"
              @ref-contract="openContractPicker(item.id)"
              @ai-analyze="handleAiAnalyze(item.id)"
              @update-conclusion="(v) => updateDimension(item.id, 'conclusion', '', v)"
            />
          </el-tab-pane>
        </el-tabs>
        <div v-if="!transactions.length" class="empty-hint">
          <el-empty description="暂无事项，请点击「添加事项」或「从序时账导入」开始穿行测试" :image-size="80" />
        </div>
      </section>

      <!-- 矩阵视图 -->
      <section v-show="editorMode === '矩阵视图'" class="section-block">
        <D4WalkthroughMatrix
          :items="transactions"
          :total-amount="totalVoucherAmount"
          :coverage-rate="coverageRate"
          :anomaly-rate="anomalyRate"
        />
      </section>

      <!-- 审计意见区 -->
      <el-card class="audit-opinion-card" shadow="never">
        <template #header>
          <div class="opinion-header">
            <span class="opinion-title">审计意见区</span>
            <div class="opinion-chips">
              <GtIndexChip value="wp:D4-12" :context-project-id="projectId" />
            </div>
            <div class="opinion-actions">
              <el-tooltip :content="aiTip" placement="top">
                <el-button size="small" type="primary" plain :loading="aiNoteLoading"
                  :disabled="isReadonly || !aiAvailable" @click="genNote">🤖 AI辅助说明</el-button>
              </el-tooltip>
              <el-tooltip :content="aiTip" placement="top">
                <el-button size="small" type="primary" plain :loading="aiConclusionLoading"
                  :disabled="isReadonly || !aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button>
              </el-tooltip>
            </div>
          </div>
        </template>
        <div class="opinion-body">
          <div class="opinion-field">
            <label>审计说明</label>
            <el-input type="textarea" :autosize="{ minRows: 3, maxRows: 12 }"
              :model-value="auditNote" :disabled="isReadonly"
              placeholder="记录抽样覆盖度、穿行测试中发现的问题、各维度一致性评价结果、异常项目及处理方式"
              @input="(v: string) => updateAuditNote(v)" />
          </div>
          <div class="opinion-field">
            <label>审计结论</label>
            <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 8 }"
              :model-value="auditConclusion" :disabled="isReadonly"
              placeholder="基于穿行测试结果，判断营业收入发生认定是否满足审计目标，是否需追加进一步审计程序"
              @input="(v: string) => updateAuditConclusion(v)" />
          </div>
        </div>
      </el-card>

      <!-- 编制提示（源模板专业指导） -->
      <details class="tips-collapse">
        <summary class="tips-summary">📋 编制提示与虚假交易识别指引</summary>
        <div class="tips-body">
          <div class="tips-group">
            <div class="tips-group-title">穿行测试检查内容</div>
            <ol class="tips-list">
              <li>核对合同、出库单、物流单、验收单等品名、规格一致，数量一致、单价、金额一致。</li>
              <li>核方结转收入的凭证日期是否与客户验收时间或控制权转移日期一致，是否确认合格后方可。</li>
              <li>核对运输单地址是否与客户产品记录发货地址一致，是否存在异常。</li>
              <li>核对是否通过管审计目标及合同约定的收入确认模式认定收入（如：某一时点/某一时段）。</li>
            </ol>
          </div>
          <div class="tips-group tips-group-warn">
            <div class="tips-group-title">虚假交易识别要点</div>
            <div class="tips-warn-content">
              <p>提示：项目组应根据被审计单位企业业务特点确定检查的侧重和交叉以及异类的方向。例如进出口贸易交易，核查自身相关交易、工程施工/设备交易、基础设施及土建设施、资本市场证券交易等均有可能形成的审计策略。除此之外可能存在的虚假收入的资金流程过程如下：</p>
              <div class="tips-scenarios">
                <div class="tips-scenario">
                  <span class="scenario-num">(1)</span>
                  <span>被审计单位通过虚假交易或虚增交易金额获取存款，或者为天额交易增加销售回扣的方式，由某关联方交易资金及利息返还（参考《中国注册会计师审计准则问题解答第10号——运用审计抽样对第三方合作金融机构余额），项目组应核查验收凭证入公司名义及开票的信息，查验关联方交易资金及利息返还的事实，并基于实质对资金流程过程进行判断审计。体现方式/工具中的样本追踪过程还原记录底稿XX（XX；或编）。</span>
                </div>
                <div class="tips-scenario">
                  <span class="scenario-num">(2)</span>
                  <span>虚假交易对于返还资金支付给被审计单位"客户"，为增加隐秘性，但可视为解释资金支付给"过桥"公司，再由"过桥"公司交付给实际取得"交易"。</span>
                </div>
                <div class="tips-scenario">
                  <span class="scenario-num">(3)</span>
                  <span>"客户"再按指令支付款款，形成虚假销售交易的资金闭环。</span>
                </div>
              </div>
            </div>
          </div>
          <div class="tips-group">
            <div class="tips-group-title">一般性编制要求</div>
            <ol class="tips-list">
              <li v-for="(tip, idx) in COMPILATION_TIPS" :key="idx">{{ tip.replace(/^\d+\.\s*/, '') }}</li>
            </ol>
          </div>
        </div>
      </details>
    </template>

    <!-- ═══ OnlyOffice 模式 ═══ -->
    <template v-if="editorMode === '在线编辑'">
      <div class="oo-container">
        <GtOnlyOfficeSheet
          :wp-id="wpId"
          :project-id="projectId"
          sheet-name="营业收入发生检查表D4-14"
          :readonly="isReadonly"
        />
      </div>
    </template>

    <!-- D4-12 合同引用弹窗 -->
    <el-dialog v-model="contractDialogVisible" title="引用D4-12合同" width="640px" destroy-on-close>
      <el-table :data="d4Contracts" border max-height="360" highlight-current-row
        @row-click="selectContract">
        <el-table-column prop="contractNo" label="合同编号" min-width="120" />
        <el-table-column prop="serviceContent" label="服务内容" min-width="160" />
        <el-table-column prop="contractAmount" label="金额" min-width="100" align="right">
          <template #default="{ row }">
            {{ row.contractAmount?.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!d4Contracts.length" class="empty-contracts">暂无 D4-12 合同数据</div>
    </el-dialog>

    <!-- 序时账导入弹窗 -->
    <el-dialog v-model="ledgerDialogVisible" title="从序时账导入" width="700px" destroy-on-close>
      <el-table :data="ledgerEntries" v-loading="ledgerLoading" border
        @selection-change="(rows: any[]) => selectedLedgerEntries = rows">
        <el-table-column type="selection" width="50" />
        <el-table-column prop="date" label="日期" min-width="100" />
        <el-table-column prop="voucherNo" label="凭证号" min-width="100" />
        <el-table-column prop="summary" label="摘要" min-width="200" />
        <el-table-column prop="amount" label="金额" min-width="120" align="right">
          <template #default="{ row }">{{ row.amount?.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) }}</template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="ledgerDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!selectedLedgerEntries.length" @click="confirmLedgerImport">
          导入 {{ selectedLedgerEntries.length }} 笔
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.d4-occurrence { padding: 16px 20px; font-size: 13px; }

/* ─── 工具条 ─── */
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

/* ─── 统计仪表板 ─── */
.stats-dashboard {
  display: flex; align-items: stretch; gap: 12px;
  margin-bottom: 24px; padding: 16px 20px;
  background: linear-gradient(135deg, #f8f9fe 0%, #f0f4ff 100%);
  border-radius: 10px; border: 1px solid #e4e7ed;
}
.stat-card {
  display: flex; flex-direction: column; justify-content: center;
  padding: 10px 16px; min-width: 110px;
  border-radius: 8px; background: #fff;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  border: 1px solid #ebeef5;
  transition: box-shadow 0.2s;
}
.stat-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.stat-card.stat-primary { border-color: #409eff; border-left: 3px solid #409eff; }
.stat-card.stat-warn { border-color: #f56c6c; border-left: 3px solid #f56c6c; }
.stat-card.stat-amount { border-color: #67c23a; border-left: 3px solid #67c23a; }
.stat-value { font-size: 20px; font-weight: 700; color: #303133; line-height: 1.2; font-variant-numeric: tabular-nums; }
.stat-unit { font-size: 12px; font-weight: 400; color: #909399; margin-left: 2px; }
.stat-label { font-size: 12px; color: #909399; margin-top: 4px; }
.stat-progress { margin-top: 6px; }
.stat-actions { display: flex; flex-direction: row; align-items: center; gap: 10px; margin-left: auto; }
.stat-actions .el-button { height: 36px; font-size: 14px; padding: 0 16px; }

/* ─── Section 块 ─── */
.section-block { margin-bottom: 24px; }
.section-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.section-title { font-size: 14px; font-weight: 600; color: #303133; padding-left: 10px; border-left: 3px solid #409eff; }
.section-ref { font-size: 11px; }

/* ─── 抽样方法论说明（源模板红字内容，默认折叠） ─── */
.methodology-collapse {
  margin-bottom: 12px; border-radius: 6px;
  border: 1px solid #faecd8; border-left: 3px solid #e6a23c;
  background: #fffbf0;
}
.methodology-summary {
  cursor: pointer; padding: 8px 14px; font-size: 13px;
  font-weight: 500; color: #b88230; user-select: none;
}
.methodology-summary:hover { color: #866736; }
.sampling-methodology {
  padding: 8px 14px 12px; font-size: 12px; color: #866736;
}
.method-row { display: flex; gap: 20px; margin-bottom: 8px; }
.method-row:last-child { margin-bottom: 0; }
.method-item { flex: 1; display: flex; gap: 6px; align-items: flex-start; }
.method-item.full-width { flex: none; width: 100%; }
.method-key { font-weight: 600; color: #b88230; white-space: nowrap; min-width: 70px; }
.method-desc { color: #8c6d3f; line-height: 1.5; }

/* ─── 编制流程条 ─── */
.guide-strip {
  display: flex; align-items: center; flex-wrap: wrap; gap: 6px;
  margin-top: 12px; padding: 10px 14px;
  background: #f0f9ff; border-radius: 6px; border: 1px solid #d4ecfd;
}
.guide-strip-label { font-size: 12px; font-weight: 600; color: #409eff; white-space: nowrap; }
.guide-chip { font-size: 12px; color: #1a56db; background: #e1effe; padding: 2px 8px; border-radius: 10px; white-space: nowrap; cursor: help; transition: background 0.2s; }
.guide-chip:hover { background: #c3ddfd; }
.guide-arrow { font-size: 11px; color: #93c5fd; }

/* ─── 抽样参数网格 ─── */
.sampling-grid {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 12px 16px; padding: 14px 16px;
  background: #fafbfc; border-radius: 8px; border: 1px solid #ebeef5;
}
.sampling-item label { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; font-weight: 500; }
.sampling-progress-item { grid-column: span 1; }
.sampling-progress-display { display: flex; align-items: center; height: 32px; }
.checked-count { font-size: 18px; font-weight: 700; color: #409eff; }
.checked-divider { color: #c0c4cc; margin: 0 4px; }
.checked-target { font-size: 14px; color: #606266; }

/* ─── 空状态 ─── */
.empty-hint { padding: 20px 0; }

/* ─── 审计意见区 ─── */
.audit-opinion-card { margin-bottom: 24px; border-radius: 8px; }
.audit-opinion-card :deep(.el-card__header) { padding: 14px 20px; background: #fafbfc; }
.opinion-header { display: flex; align-items: center; gap: 12px; }
.opinion-title { font-size: 15px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-actions { display: flex; gap: 8px; margin-left: auto; }
.opinion-body { display: flex; flex-direction: column; gap: 16px; padding-top: 4px; }
.opinion-field label { display: block; font-size: 13px; font-weight: 500; color: #606266; margin-bottom: 6px; }

/* ─── 编制提示（折叠收纳） ─── */
.tips-collapse {
  margin-bottom: 20px; padding: 12px 16px;
  background: #fafbfc; border-radius: 8px;
  border: 1px solid #e4e7ed; border-left: 3px solid #f56c6c;
}
.tips-summary { cursor: pointer; font-size: 13px; font-weight: 600; color: #606266; user-select: none; }
.tips-summary:hover { color: #303133; }
.tips-body { margin-top: 14px; display: flex; flex-direction: column; gap: 16px; }
.tips-group { padding: 12px 14px; background: #fff; border-radius: 6px; border: 1px solid #ebeef5; }
.tips-group-warn { background: #fef0f0; border-color: #fde2e2; }
.tips-group-title { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid #ebeef5; }
.tips-group-warn .tips-group-title { color: #c45656; border-color: #fde2e2; }
.tips-list { margin: 0; padding-left: 20px; }
.tips-list li { font-size: 13px; color: #606266; line-height: 1.8; margin-bottom: 2px; }
.tips-warn-content { font-size: 13px; color: #606266; line-height: 1.7; }
.tips-warn-content p { margin: 0 0 10px; }
.tips-scenarios { display: flex; flex-direction: column; gap: 8px; padding-left: 4px; }
.tips-scenario { display: flex; gap: 6px; align-items: flex-start; }
.scenario-num { font-weight: 600; color: #c45656; flex-shrink: 0; }

/* ─── OO容器 ─── */
.oo-container { min-height: 600px; height: calc(100vh - 280px); border-radius: 8px; overflow: hidden; }

/* ─── 弹窗 ─── */
.empty-contracts { text-align: center; padding: 20px; color: #909399; }
</style>
