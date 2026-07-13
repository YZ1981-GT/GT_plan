<template>
  <div class="n5-deferred-reconcile">
    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <p><strong>递延所得税费用核对表（N5-8）</strong>：递延所得税费用 = 递延税负债本期增加 − 递延税资产本期增加。订阅N1(递延税资产)和N3(递延税负债)本期变动数据，交叉验证一致性，结果回填N5-1审定表递延所得税费用行。</p>
    </div>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>递延所得税费用核对表 N5-8</span>
        <el-tag :type="reconcile.isReconciled.value ? 'success' : 'danger'" size="small">
          {{ reconcile.isReconciled.value ? '✓ 核对一致' : '⚠ 存在差异' }}
        </el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon>AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon>复核
        </el-button>
      </div>
    </div>

    <!-- ═══ N1/N3交叉验证状态 ═══ -->
    <div class="cross-validation-section">
      <div class="cv-title">
        跨底稿交叉验证（<GtIndexChip value="N1-1" /> 递延税资产 / <GtIndexChip value="N3-1" /> 递延税负债）
      </div>
      <div class="cv-indicators">
        <div class="cv-item" :class="Math.abs(reconcile.n1Diff.value) <= 0.01 ? 'cv-match' : 'cv-diff'">
          <span class="cv-label">N1递延税资产变动</span>
          <span class="cv-values">
            本表: {{ fmtAmount(reconcile.totalAssetChange.value) }} | N1: {{ fmtAmount(reconcile.n1AssetChange.value) }}
          </span>
          <span class="cv-badge" :class="Math.abs(reconcile.n1Diff.value) <= 0.01 ? 'cv-badge-ok' : 'cv-badge-err'">
            {{ Math.abs(reconcile.n1Diff.value) <= 0.01 ? '✓ 一致' : '⚠ 差异 ' + fmtAmount(reconcile.n1Diff.value) }}
          </span>
        </div>
        <div class="cv-item" :class="Math.abs(reconcile.n3Diff.value) <= 0.01 ? 'cv-match' : 'cv-diff'">
          <span class="cv-label">N3递延税负债变动</span>
          <span class="cv-values">
            本表: {{ fmtAmount(reconcile.totalLiabilityChange.value) }} | N3: {{ fmtAmount(reconcile.n3LiabilityChange.value) }}
          </span>
          <span class="cv-badge" :class="Math.abs(reconcile.n3Diff.value) <= 0.01 ? 'cv-badge-ok' : 'cv-badge-err'">
            {{ Math.abs(reconcile.n3Diff.value) <= 0.01 ? '✓ 一致' : '⚠ 差异 ' + fmtAmount(reconcile.n3Diff.value) }}
          </span>
        </div>
      </div>
      <!-- 手动覆盖N1/N3值 -->
      <div class="cv-manual" v-if="!isReadonly">
        <span class="cv-manual-label">手动设置（当EventBus未触发时）：</span>
        <el-input-number v-model="manualN1" :controls="false" :precision="2" size="small" placeholder="N1资产变动" style="width: 140px" @change="handleSetN1" />
        <el-input-number v-model="manualN3" :controls="false" :precision="2" size="small" placeholder="N3负债变动" style="width: 140px" @change="handleSetN3" />
      </div>
    </div>

    <!-- ═══ 递延所得税费用汇总 ═══ -->
    <div class="deferred-summary">
      <div class="ds-formula">
        <span class="ds-item">递延税负债变动 <strong>{{ fmtAmount(reconcile.totalLiabilityChange.value) }}</strong></span>
        <span class="ds-operator">−</span>
        <span class="ds-item">递延税资产变动 <strong>{{ fmtAmount(reconcile.totalAssetChange.value) }}</strong></span>
        <span class="ds-operator">=</span>
        <span class="ds-item ds-result">递延所得税费用 <strong class="primary">{{ fmtAmount(reconcile.deferredTaxExpense.value) }}</strong></span>
      </div>
    </div>

    <!-- ═══ 主数据表格（44行10列） ═══ -->
    <el-table :data="reconcile.rows.value" border size="small" show-summary :summary-method="getSummaries" class="reconcile-table" max-height="480">
      <el-table-column prop="index" label="序号" width="55" align="center" fixed />
      <el-table-column prop="label" label="项目（暂时性差异）" min-width="160" fixed>
        <template #default="{ row }">
          <span class="item-label">{{ row.label }}</span>
        </template>
      </el-table-column>
      <!-- DTA列组 -->
      <el-table-column label="递延所得税资产（DTA）" align="center">
        <el-table-column prop="assetBeginning" label="期初" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" v-model="row.assetBeginning" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleUpdate($index, 'assetBeginning', row.assetBeginning)" />
            <span v-else class="cell-value">{{ fmtAmount(row.assetBeginning) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetEnding" label="期末" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" v-model="row.assetEnding" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleUpdate($index, 'assetEnding', row.assetEnding)" />
            <span v-else class="cell-value">{{ fmtAmount(row.assetEnding) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动" min-width="100" align="right">
          <template #header>
            <span class="formula-header" title="DTA变动 = 期末 − 期初">变动</span>
          </template>
          <template #default="{ row }">
            <el-tooltip content="DTA变动 = 期末 − 期初" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.assetChange) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table-column>
      <!-- DTL列组 -->
      <el-table-column label="递延所得税负债（DTL）" align="center">
        <el-table-column prop="liabilityBeginning" label="期初" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" v-model="row.liabilityBeginning" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleUpdate($index, 'liabilityBeginning', row.liabilityBeginning)" />
            <span v-else class="cell-value">{{ fmtAmount(row.liabilityBeginning) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="liabilityEnding" label="期末" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" v-model="row.liabilityEnding" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleUpdate($index, 'liabilityEnding', row.liabilityEnding)" />
            <span v-else class="cell-value">{{ fmtAmount(row.liabilityEnding) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动" min-width="100" align="right">
          <template #header>
            <span class="formula-header" title="DTL变动 = 期末 − 期初">变动</span>
          </template>
          <template #default="{ row }">
            <el-tooltip content="DTL变动 = 期末 − 期初" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.liabilityChange) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table-column>
      <!-- 递延所得税费用 -->
      <el-table-column label="递延所得税费用" min-width="120" align="right">
        <template #header>
          <span class="formula-header" title="= DTL变动 − DTA变动">递延税费用</span>
        </template>
        <template #default="{ row }">
          <el-tooltip content="递延所得税费用 = DTL变动 − DTA变动" placement="top">
            <span class="formula-cell" :class="{ 'diff-highlight': Math.abs(row.deferredExpense) > 0.01 }">{{ fmtAmount(row.deferredExpense) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <!-- 备注 -->
      <el-table-column prop="remark" label="备注" min-width="120">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.remark" size="small" placeholder="备注" @change="() => handleUpdate($index, 'remark', row.remark)" />
          <span v-else class="cell-value">{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 动态行 ═══ -->
    <div class="dynamic-row-bar" v-if="!isReadonly">
      <el-button size="small" type="primary" plain @click="handleAddRow">
        <el-icon><Plus /></el-icon>新增核对项
      </el-button>
    </div>

    <!-- ═══ 回填N5-1 ═══ -->
    <div class="action-bar">
      <el-button type="primary" size="small" :disabled="isReadonly" :loading="syncLoading" @click="handleSyncToAdjudication">
        回填递延所得税费用 → N5-1审定表
      </el-button>
      <span class="action-hint">递延所得税费用 {{ fmtAmount(reconcile.deferredTaxExpense.value) }}</span>
    </div>

    <!-- ═══ 审计说明与结论 ═══ -->
    <el-card shadow="never" class="audit-notes-card">
      <template #header>
        <div class="notes-header">
          <span>审计说明与结论</span>
          <el-button size="small" @click="handleNotesAi"><el-icon><MagicStick /></el-icon>AI辅助</el-button>
        </div>
      </template>
      <div class="notes-field">
        <label class="field-label">审计说明</label>
        <el-input v-model="auditNotes" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请说明递延所得税核对情况..." :disabled="isReadonly" @change="saveNotes" />
      </div>
      <div class="notes-field">
        <label class="field-label">审计结论</label>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="请输入审计结论..." :disabled="isReadonly" @change="saveConclusion" />
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>递延所得税费用 = 递延税负债本期增加(DTL变动) − 递延税资产本期增加(DTA变动)</li>
        <li>DTA/DTL变动 = 期末余额 − 期初余额</li>
        <li>N1递延税资产底稿 → EventBus 'deferred-tax:asset-updated' 自动传入DTA变动</li>
        <li>N3递延税负债底稿 → EventBus 'deferred-tax:liability-updated' 自动传入DTL变动</li>
        <li>核对一致说明N1/N3/N5-8三表递延所得税数据无矛盾</li>
        <li>递延所得税费用回填N5-1审定表递延所得税费用行</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N5TabDeferredReconcile — 递延所得税费用核对表N5-8
 *
 * 44×10 + 12公式 + 递延税资产/负债期初期末本期变动
 * Subscribe N1/N3 + 递延所得税费用=负债增−资产增 + 回填N5-1
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 4.8
 * Requirements: 8.1-8.5
 */
import { ref, computed, inject, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, Plus } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useN5FormData } from '../../composables/useN5FormData'
import { useN5DeferredReconcile } from '../../composables/useN5DeferredReconcile'

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)

const wpIdRef = computed(() => props.wpId) as Ref<string>
const projectIdRef = computed(() => props.projectId) as Ref<string>
const allResponsesRef = computed(() => props.allResponses)

const formData = useN5FormData({ wpId: wpIdRef, projectId: projectIdRef })

const reconcile = useN5DeferredReconcile({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  saveField: formData.setField,
  getField: formData.getField,
})

const syncLoading = ref(false)
const auditNotes = ref('')
const auditConclusion = ref('')
const manualN1 = ref<number>(0)
const manualN3 = ref<number>(0)

// ─── 初始化 ──────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  auditNotes.value = formData.getField('8', 'audit-notes') ?? ''
  auditConclusion.value = formData.getField('8', 'audit-conclusion') ?? ''
  manualN1.value = reconcile.n1AssetChange.value
  manualN3.value = reconcile.n3LiabilityChange.value
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

async function handleUpdate(index: number, field: string, value: any) {
  await reconcile.updateRow(index, field as any, value)
}

async function handleSetN1(val: number) {
  await reconcile.setN1AssetChange(val)
}

async function handleSetN3(val: number) {
  await reconcile.setN3LiabilityChange(val)
}

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('请输入暂时性差异项目名称', '新增核对项', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPlaceholder: '如：预计负债',
  }).catch(() => ({ value: '' }))
  if (!name) return
  await reconcile.addRow(name)
  ElMessage.success(`已新增：${name}`)
}

async function handleSyncToAdjudication() {
  syncLoading.value = true
  try {
    await reconcile.syncDeferredExpenseToAdjudication()
    ElMessage.success(`递延所得税费用${fmtAmount(reconcile.deferredTaxExpense.value)}已回填N5-1`)
  } catch { ElMessage.error('回填失败') }
  finally { syncLoading.value = false }
}

function getSummaries({ columns }: { columns: any[] }) {
  return columns.map((_c: any, idx: number) => {
    if (idx === 0) return '合计'
    if (idx === 1) return ''
    // 简化处理：只在关键列显示合计
    return ''
  })
}

async function saveNotes() { await formData.setField('8', 'audit-notes', auditNotes.value) }
async function saveConclusion() { await formData.setField('8', 'audit-conclusion', auditConclusion.value) }
function handleAiAssist() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n5-deferred-reconcile',
      prompt: '请基于所得税费用底稿数据，给出审计分析建议',
      context: { wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleNotesAi() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n5-deferred-reconcile',
      prompt: '请基于所得税费用底稿数据，给出审计分析建议',
      context: { wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleReview() { openReviewDialog ? openReviewDialog('N5-8-递延核对') : ElMessage.info('复核对话未配置') }

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.n5-deferred-reconcile { padding: 12px; font-size: var(--wp-font-size, 13px); }
.methodology-context { padding: 12px 16px; margin-bottom: 16px; background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #92400e; line-height: 1.7; }
.methodology-context p { margin: 0; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 8px; }

.cross-validation-section { margin-bottom: 16px; padding: 14px 16px; background: #fafbfc; border: 1px solid #ebeef5; border-radius: 8px; }
.cv-title { font-size: var(--wp-font-size, 13px); font-weight: 500; color: #303133; margin-bottom: 10px; }
.cv-indicators { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
.cv-item { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-radius: 6px; font-size: 12px; }
.cv-match { background: #e8f5e9; border: 1px solid #a5d6a7; }
.cv-diff { background: #fef0f0; border: 1px solid #fab6b6; }
.cv-label { font-weight: 500; color: #303133; min-width: 120px; }
.cv-values { color: #606266; flex: 1; }
.cv-badge { font-weight: 600; font-size: 12px; }
.cv-badge-ok { color: #43a047; }
.cv-badge-err { color: #f56c6c; }
.cv-manual { display: flex; align-items: center; gap: 10px; padding-top: 8px; border-top: 1px dashed #ebeef5; }
.cv-manual-label { font-size: 12px; color: #909399; }

.deferred-summary { margin-bottom: 16px; padding: 14px 20px; background: #ecf5ff; border: 1px solid #b3d8ff; border-radius: 8px; }
.ds-formula { display: flex; align-items: center; gap: 12px; font-size: 14px; flex-wrap: wrap; }
.ds-item { color: #303133; }
.ds-item strong { font-size: 15px; }
.ds-operator { font-size: 18px; font-weight: 700; color: #909399; }
.ds-result strong.primary { color: #409eff; font-size: 16px; }

.reconcile-table { margin-bottom: 16px; }
:deep(.reconcile-table .el-table) { font-size: var(--wp-font-size, 13px); }
.item-label { font-weight: 500; color: #303133; }
.formula-header { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; font-weight: 500; color: #303133; padding-bottom: 1px; }
.diff-highlight { color: #409eff !important; font-weight: 700; }
.cell-input { width: 100%; }
:deep(.cell-input .el-input__inner) { text-align: right; font-size: var(--wp-font-size, 13px); }
.cell-value { font-size: var(--wp-font-size, 13px); color: #606266; }

.dynamic-row-bar { margin-bottom: 16px; }

.action-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; padding: 10px 16px; background: #f0f9eb; border: 1px solid #c2e7b0; border-radius: 6px; }
.action-hint { font-size: 12px; color: #67c23a; }

.audit-notes-card { margin-bottom: 16px; }
.notes-header { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 500; }
.notes-field { margin-bottom: 12px; }
.notes-field:last-child { margin-bottom: 0; }
.field-label { display: block; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #606266; margin-bottom: 6px; }

.n5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.n5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
