<script setup lang="ts">
/**
 * D4TabContract — D4-12 合同检查表（重写）
 *
 * 对齐源模板：纵向20+1字段 × 横向N份合同卡片
 * 支持：OCR附件智能填充 / AI结论生成 / 双模式 / 导入导出 / 编制提示
 *
 * Spec: .kiro/specs/d4-12-contract-inspection/
 */
import { ref, computed, inject, toRef, defineAsyncComponent, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useD4ContractInspection,
  CONTRACT_GUIDANCE,
  type ContractInspectionItem,
  type OcrExtractedFields,
} from '../../composables/useD4ContractInspection'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import D4ContractCard from './D4ContractCard.vue'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const D4ContractMatrix = defineAsyncComponent(() => import('./D4ContractMatrix.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── 三模式 ──────────────────────────────────────────────────────────
const editorMode = ref<'structured' | 'matrix' | 'onlyoffice'>('structured')
const ooHealthy = ref(false)
const modeOptions = computed(() => [
  { label: '卡片视图', value: 'structured' },
  { label: '矩阵视图', value: 'matrix' },
  { label: '在线编辑', value: 'onlyoffice', disabled: !ooHealthy.value },
])
async function checkOoHealth() {
  try {
    const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    ooHealthy.value = res.data?.data?.healthy ?? res.data?.healthy ?? false
  } catch { ooHealthy.value = false }
}
checkOoHealth()

// ─── AI 健康检查 ─────────────────────────────────────────────────────
const aiAvailable = ref(false)
async function checkAiHealth() {
  try {
    const res = await http.get('/api/ai/health', { _silent: true } as any)
    const s = res.data?.data?.status ?? res.data?.status
    aiAvailable.value = s === 'healthy' || s === 'degraded'
  } catch { aiAvailable.value = false }
}
checkAiHealth()

// ─── Composable ──────────────────────────────────────────────────────
const {
  contracts,
  auditNote,
  auditConclusion,
  totalContractAmount,
  coverageRate,
  completedCount,
  summaryConclusion,
  addContract,
  removeContract,
  updateField,
  mergeOcrFields,
  setOcrStatus,
  setAttachment,
  updateAuditNote,
  updateAuditConclusion,
} = useD4ContractInspection({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── 导入导出 ────────────────────────────────────────────────────────
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
})
function handleExportTemplate() { exportTemplate('D4-12') }
function handleExportData() { exportData('D4-12') }
function handleImportUpload(file: File): boolean {
  importData('D4-12', file)
  return false
}

// ─── Tab 管理 ────────────────────────────────────────────────────────
const activeTab = ref('')

// 确保有合同时默认选中第一个
if (contracts.value.length > 0) {
  activeTab.value = contracts.value[0].id
}

async function handleAddContract() {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入合同备注名称（如"XX公司采购合同"）',
      '添加合同',
      { confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '合同备注名称' },
    )
    if (value?.trim()) {
      const item = addContract(value.trim())
      activeTab.value = item.id
    }
  } catch { /* cancel */ }
}

function handleRemoveContract(id: string) {
  ElMessageBox.confirm('确定删除该合同检查记录？此操作不可撤销。', '删除确认', {
    type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
  }).then(() => {
    removeContract(id)
    if (activeTab.value === id && contracts.value.length > 0) {
      activeTab.value = contracts.value[0].id
    }
  }).catch(() => {})
}

// ─── OCR 上传 ────────────────────────────────────────────────────────
const ocrLoadingId = ref<string | null>(null)

async function handleContractUpload(contractId: string, file: File) {
  if (props.isReadonly) return
  ocrLoadingId.value = contractId
  setOcrStatus(contractId, 'processing')

  const formData = new FormData()
  formData.append('file', file)

  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const data = res.data?.data ?? res.data
    const { attachment_id, extracted_fields, confidence } = data

    // 保存附件信息
    setAttachment(contractId, attachment_id, file.name)

    // 弹窗确认OCR结果
    const fieldSummary = Object.entries(extracted_fields || {})
      .filter(([, v]) => v != null && v !== '')
      .map(([k, v]) => `${k}: ${v}`)
      .join('\n')

    const confirmMsg = `OCR识别完成（置信度: ${((confidence || 0) * 100).toFixed(0)}%）\n\n提取字段：\n${fieldSummary || '（未提取到有效信息）'}\n\n是否将提取结果填入表单？`

    await ElMessageBox.confirm(confirmMsg, 'OCR提取结果', {
      confirmButtonText: '填入（覆盖空字段）',
      cancelButtonText: '取消',
      distinguishCancelAndClose: true,
      type: 'info',
    })
    mergeOcrFields(contractId, extracted_fields as OcrExtractedFields, false)
    ElMessage.success('OCR结果已填入')
  } catch (err: any) {
    if (err === 'cancel' || err?.message === 'cancel') {
      setOcrStatus(contractId, 'done')
    } else {
      setOcrStatus(contractId, 'failed')
      ElMessage.warning('OCR识别失败，请手动填写')
    }
  } finally {
    ocrLoadingId.value = null
  }
}

// ─── AI 结论生成 ─────────────────────────────────────────────────────
const aiLoading = ref(false)

async function generateConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoading.value = true
  try {
    const context = contracts.value.map(c =>
      `【${c.indexNo} ${c.counterparty || c.label}】金额:${c.contractAmount}元, 时段/时点:${c.recognitionMethod || '未填'}, 签字:${c.isSigned || '未填'}, 盖章:${c.isSealed || '未填'}, 结论:${c.conclusion || '未判定'}`,
    ).join('\n')
    const existing = [
      `汇总：${summaryConclusion.value}`,
      `覆盖率：${coverageRate.value.toFixed(1)}%`,
      auditConclusion.value ? `现有结论：${auditConclusion.value}` : '',
    ].filter(Boolean).join('\n')

    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/ai-generate`,
      { section: 'contract-conclusion', existingContent: existing, relatedContext: { contracts: context } },
      { _silent: true } as any,
    )
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }

    await ElMessageBox.confirm(
      text.length > 400 ? text.slice(0, 400) + '…' : text,
      'AI 生成 · 审计结论',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
    )
    updateAuditConclusion(text)
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') ElMessage.warning('AI 生成失败')
  } finally {
    aiLoading.value = false
  }
}

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成审计结论' : 'AI 服务暂不可用')

// ─── 格式化 ──────────────────────────────────────────────────────────
function fmtAmount(v: number): string {
  if (!v) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <div class="d4-contract">
    <!-- 顶部工具条 -->
    <div class="mode-bar">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      <div class="mode-bar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx,.xls" :before-upload="handleImportUpload" :disabled="importing">
                  <span>{{ importing ? '导入中...' : '导入数据' }}</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-label">关联</span>
        <GtIndexChip value="wp:D4-5" :context-project-id="projectId" />
        <GtIndexChip value="wp:D4-17" :context-project-id="projectId" />
        <GtIndexChip value="wp:D4-4" :context-project-id="projectId" />
      </div>
    </div>

    <!-- 结构化视图 -->
    <template v-if="editorMode === 'structured'">
      <!-- 概览横幅 -->
      <div class="overview-panel">
        <el-progress
          type="circle"
          :percentage="Math.min(coverageRate, 100)"
          :width="56"
          :stroke-width="5"
          :color="coverageRate >= 60 ? '#67c23a' : '#e6a23c'"
        />
        <div class="overview-info">
          <h3 class="overview-title">
            合同检查表
            <el-tag size="small" effect="plain" class="overview-code">D4-12</el-tag>
          </h3>
          <p class="overview-desc">
            已检查 <strong>{{ contracts.length }}</strong> 份合同，
            金额 <strong>{{ fmtAmount(totalContractAmount) }}</strong> 元，
            覆盖率 <strong>{{ coverageRate.toFixed(1) }}%</strong>
            <el-tag v-if="coverageRate < 60 && contracts.length > 0" type="warning" size="small" style="margin-left:6px">覆盖率不足</el-tag>
          </p>
        </div>
        <el-button type="primary" size="small" :disabled="isReadonly" @click="handleAddContract">
          + 添加合同
        </el-button>
      </div>

      <!-- 合同卡片区 -->
      <div v-if="contracts.length === 0" class="empty-state">
        <p>暂无合同检查记录。点击"添加合同"开始，或上传合同附件自动OCR提取信息。</p>
      </div>
      <el-tabs v-else v-model="activeTab" type="card" closable @tab-remove="(id: any) => handleRemoveContract(id as string)">
        <el-tab-pane
          v-for="c in contracts"
          :key="c.id"
          :name="c.id"
          :label="`${c.indexNo} ${c.counterparty || c.label || '待填写'}`"
        >
          <D4ContractCard
            :item="c"
            :is-readonly="isReadonly"
            :ocr-loading="ocrLoadingId === c.id"
            @update="(field, val) => updateField(c.id, field, val)"
            @upload="(file) => handleContractUpload(c.id, file)"
            @remove-attachment="() => { setAttachment(c.id, '', ''); setOcrStatus(c.id, 'none') }"
          />
        </el-tab-pane>
      </el-tabs>

      <!-- 编制提示 -->
      <div class="guidance-section">
        <details v-for="(tip, i) in CONTRACT_GUIDANCE" :key="i" class="guidance-details">
          <summary>📋 {{ tip.title }}</summary>
          <div class="guidance-content">{{ tip.content }}</div>
        </details>
      </div>

      <!-- 审计意见区 -->
      <el-card class="opinion-card" shadow="never">
        <template #header>
          <div class="opinion-header">
            <span class="opinion-title">审计意见区</span>
            <div class="opinion-actions">
              <el-tooltip :content="aiTip" placement="top">
                <el-button size="small" type="primary" plain
                  :loading="aiLoading"
                  :disabled="isReadonly || !aiAvailable"
                  @click="generateConclusion">🤖 AI辅助</el-button>
              </el-tooltip>
              <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-12-note')">💬 复核</el-button>
            </div>
          </div>
        </template>

        <!-- 汇总结论 -->
        <div v-if="summaryConclusion" class="summary-text">
          <el-icon><svg viewBox="0 0 1024 1024" width="14" height="14"><path fill="currentColor" d="M512 64a448 448 0 1 1 0 896 448 448 0 0 1 0-896zm-38.4 300.8a38.4 38.4 0 1 0 76.8 0 38.4 38.4 0 0 0-76.8 0zM448 512v192h128V512H448z"/></svg></el-icon>
          {{ summaryConclusion }}
        </div>

        <div class="opinion-fields">
          <div class="opinion-field">
            <label>审计说明</label>
            <el-input type="textarea" :rows="3" :model-value="auditNote" :disabled="isReadonly"
              placeholder="请输入审计说明（合同检查过程中发现的重要事项）..."
              @input="(v: string) => updateAuditNote(v)" />
          </div>
          <div class="opinion-field">
            <label>审计结论</label>
            <el-input type="textarea" :rows="3" :model-value="auditConclusion" :disabled="isReadonly"
              placeholder="请输入审计结论..."
              @input="(v: string) => updateAuditConclusion(v)" />
          </div>
        </div>
      </el-card>
    </template>

    <!-- 矩阵视图 -->
    <template v-else-if="editorMode === 'matrix'">
      <!-- 概览横幅 -->
      <div class="overview-panel">
        <el-progress
          type="circle"
          :percentage="Math.min(coverageRate, 100)"
          :width="56"
          :stroke-width="5"
          :color="coverageRate >= 60 ? '#67c23a' : '#e6a23c'"
        />
        <div class="overview-info">
          <h3 class="overview-title">
            合同检查表
            <el-tag size="small" effect="plain" class="overview-code">D4-12</el-tag>
          </h3>
          <p class="overview-desc">
            已检查 <strong>{{ contracts.length }}</strong> 份合同，
            金额 <strong>{{ fmtAmount(totalContractAmount) }}</strong> 元，
            覆盖率 <strong>{{ coverageRate.toFixed(1) }}%</strong>
            <el-tag v-if="coverageRate < 60 && contracts.length > 0" type="warning" size="small" style="margin-left:6px">覆盖率不足</el-tag>
          </p>
        </div>
      </div>

      <!-- 矩阵比对表 -->
      <D4ContractMatrix
        :contracts="contracts"
        :total-contract-amount="totalContractAmount"
        :coverage-rate="coverageRate"
      />

      <!-- 审计意见区 -->
      <el-card class="opinion-card" shadow="never" style="margin-top: 16px;">
        <template #header>
          <div class="opinion-header">
            <span class="opinion-title">审计意见区</span>
            <div class="opinion-actions">
              <el-tooltip :content="aiTip" placement="top">
                <el-button size="small" type="primary" plain
                  :loading="aiLoading"
                  :disabled="isReadonly || !aiAvailable"
                  @click="generateConclusion">🤖 AI辅助</el-button>
              </el-tooltip>
              <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-12-note')">💬 复核</el-button>
            </div>
          </div>
        </template>
        <div v-if="summaryConclusion" class="summary-text">
          <el-icon><svg viewBox="0 0 1024 1024" width="14" height="14"><path fill="currentColor" d="M512 64a448 448 0 1 1 0 896 448 448 0 0 1 0-896zm-38.4 300.8a38.4 38.4 0 1 0 76.8 0 38.4 38.4 0 0 0-76.8 0zM448 512v192h128V512H448z"/></svg></el-icon>
          {{ summaryConclusion }}
        </div>
        <div class="opinion-fields">
          <div class="opinion-field">
            <label>审计说明</label>
            <el-input type="textarea" :rows="3" :model-value="auditNote" :disabled="isReadonly"
              placeholder="请输入审计说明（合同检查过程中发现的重要事项）..."
              @input="(v: string) => updateAuditNote(v)" />
          </div>
          <div class="opinion-field">
            <label>审计结论</label>
            <el-input type="textarea" :rows="3" :model-value="auditConclusion" :disabled="isReadonly"
              placeholder="请输入审计结论..."
              @input="(v: string) => updateAuditConclusion(v)" />
          </div>
        </div>
      </el-card>
    </template>

    <!-- OnlyOffice 模式 -->
    <template v-else-if="editorMode === 'onlyoffice'">
      <div style="min-height: 600px; height: calc(100vh - 280px);">
        <GtOnlyOfficeSheet
          :wp-id="props.wpId"
          :project-id="props.projectId"
          sheet-name="合同检查表D4-12"
          :readonly="isReadonly"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.d4-contract { padding: 12px 16px; }

.mode-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 8px;
}
.mode-bar-right { display: flex; gap: 6px; align-items: center; }
.chip-label { font-size: 12px; color: #909399; }

.overview-panel {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 20px;
  background: linear-gradient(135deg, #f3f0ff 0%, #eaf4ff 100%);
  border-radius: 12px;
  margin-bottom: 16px;
  border: 1px solid #e0d8f5;
}
.overview-info { flex: 1; min-width: 0; }
.overview-title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  display: flex;
  align-items: center;
  gap: 8px;
}
.overview-code {
  font-size: 11px;
  color: #7c5cff;
  border-color: #d9c9ff;
  background: #fff;
}
.overview-desc {
  margin: 0;
  font-size: 13px;
  color: #606266;
}

.empty-state {
  padding: 40px 20px;
  text-align: center;
  color: #909399;
  font-size: 13px;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
  margin-bottom: 16px;
}

/* Tab 样式微调 */
:deep(.el-tabs--card > .el-tabs__header .el-tabs__item) {
  font-size: 13px;
}

.guidance-section { margin: 20px 0 16px; }
.guidance-details {
  margin-bottom: 8px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
  font-size: 13px;
}
.guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.7;
  white-space: pre-wrap;
}

.opinion-card { border-radius: 10px; }
.opinion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 8px; }

.summary-text {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 13px;
  color: #303133;
  margin-bottom: 14px;
  line-height: 1.6;
}

.opinion-fields { display: flex; flex-direction: column; gap: 14px; }
.opinion-field label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #606266;
  margin-bottom: 6px;
}
</style>
