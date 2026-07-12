<template>
  <div class="n5-rd-super-deduction">
    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <p><strong>研发加计扣除（N5-6-1）</strong>：企业研发费用按六大类（人员人工/直接投入/折旧/无形资产摊销/新产品设计费/其他费用）归集，区分费用化与资本化。加计扣除额 = 研发费用 × 加计比例（一般企业100%，特定行业120%）。费用化部分当期加计；资本化部分按摊销加计。接收I6研发费用(费用化)和I2开发支出(资本化)联动。</p>
    </div>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>加计扣除研发费用情况明细表 N5-6-1</span>
        <el-tag type="success" size="small">17公式</el-tag>
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

    <!-- ═══ I6/I2联动状态 ═══ -->
    <div class="linkage-status">
      <div class="linkage-item" :class="rd.expensedTotal.value > 0 ? 'linked' : 'pending'">
        <span class="lk-icon">{{ rd.expensedTotal.value > 0 ? '✓' : '○' }}</span>
        <GtIndexChip value="I6" />
        <span class="lk-label">研发费用（费用化）</span>
        <span class="lk-value">{{ fmtAmount(rd.expensedTotal.value) }}</span>
      </div>
      <div class="linkage-item" :class="rd.capitalizedTotal.value > 0 ? 'linked' : 'pending'">
        <span class="lk-icon">{{ rd.capitalizedTotal.value > 0 ? '✓' : '○' }}</span>
        <GtIndexChip value="I2" />
        <span class="lk-label">开发支出（资本化）</span>
        <span class="lk-value">{{ fmtAmount(rd.capitalizedTotal.value) }}</span>
      </div>
    </div>

    <!-- ═══ 加计比例编辑 ═══ -->
    <div class="super-rate-section">
      <span class="rate-label">加计扣除比例：</span>
      <el-select v-if="!isReadonly" v-model="selectedRate" size="small" style="width: 220px" @change="handleRateChange">
        <el-option :value="1.0" label="100%（一般企业，2023年起）" />
        <el-option :value="1.2" label="120%（集成电路/工业母机）" />
        <el-option :value="0.75" label="75%（2018-2022年政策）" />
        <el-option :value="0.5" label="50%（旧政策参考）" />
      </el-select>
      <span v-else class="rate-value">{{ (rd.superRate.value * 100).toFixed(0) }}%</span>
    </div>

    <!-- ═══ 加计扣除汇总卡片 ═══ -->
    <div class="deduction-summary-cards">
      <div class="ds-card">
        <span class="ds-label">费用化研发费用</span>
        <span class="ds-value">{{ fmtAmount(rd.expensedTotal.value) }}</span>
        <span class="ds-sub">加计: {{ fmtAmount(rd.expensedDeduction.value) }}</span>
      </div>
      <div class="ds-card">
        <span class="ds-label">资本化研发费用</span>
        <span class="ds-value">{{ fmtAmount(rd.capitalizedTotal.value) }}</span>
        <span class="ds-sub">加计: {{ fmtAmount(rd.capitalizedDeduction.value) }}</span>
      </div>
      <div class="ds-card highlight">
        <span class="ds-label">加计扣除额合计</span>
        <span class="ds-value primary">{{ fmtAmount(rd.totalDeduction.value) }}</span>
        <span class="ds-sub">→ N5-5调减项</span>
      </div>
    </div>

    <!-- ═══ 费用化研发项目表 ═══ -->
    <div class="rd-section">
      <div class="rd-section-header">
        <span class="rd-section-title">一、费用化研发项目</span>
        <span class="rd-section-subtotal">小计: {{ fmtAmount(rd.expensedTotal.value) }}</span>
      </div>
      <el-table :data="rd.expensedRows.value" border size="small" class="rd-table">
        <el-table-column prop="index" label="序号" width="55" align="center" />
        <el-table-column prop="projectName" label="研发项目名称" min-width="160">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.projectName" size="small" @change="() => handleRowUpdate($index, 'projectName', row.projectName)" />
            <span v-else class="item-name">{{ row.projectName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="personnelCost" label="人员人工" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" v-model="row.personnelCost" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleRowUpdate($index, 'personnelCost', row.personnelCost)" />
            <span v-else class="cell-value">{{ fmtAmount(row.personnelCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="directInput" label="直接投入" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" v-model="row.directInput" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleRowUpdate($index, 'directInput', row.directInput)" />
            <span v-else class="cell-value">{{ fmtAmount(row.directInput) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="depreciation" label="折旧费用" min-width="100" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" v-model="row.depreciation" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleRowUpdate($index, 'depreciation', row.depreciation)" />
            <span v-else class="cell-value">{{ fmtAmount(row.depreciation) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="amortization" label="摊销" min-width="90" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" v-model="row.amortization" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleRowUpdate($index, 'amortization', row.amortization)" />
            <span v-else class="cell-value">{{ fmtAmount(row.amortization) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="otherExpense" label="其他" min-width="90" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" v-model="row.otherExpense" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleRowUpdate($index, 'otherExpense', row.otherExpense)" />
            <span v-else class="cell-value">{{ fmtAmount(row.otherExpense) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合计" min-width="100" align="right">
          <template #header>
            <span class="formula-header" title="合计 = Σ各类费用">合计</span>
          </template>
          <template #default="{ row }">
            <el-tooltip content="合计 = 人员人工 + 直接投入 + 折旧 + 摊销 + 其他" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.totalExpense) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 资本化研发项目表 ═══ -->
    <div class="rd-section">
      <div class="rd-section-header">
        <span class="rd-section-title">二、资本化研发项目（按摊销加计）</span>
        <span class="rd-section-subtotal">小计: {{ fmtAmount(rd.capitalizedTotal.value) }}</span>
      </div>
      <el-table :data="rd.capitalizedRows.value" border size="small" class="rd-table">
        <el-table-column prop="index" label="序号" width="55" align="center" />
        <el-table-column prop="projectName" label="研发项目名称" min-width="160">
          <template #default="{ row }">
            <span class="item-name">{{ row.projectName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="personnelCost" label="人员人工" min-width="100" align="right">
          <template #default="{ row }"><span class="cell-value">{{ fmtAmount(row.personnelCost) }}</span></template>
        </el-table-column>
        <el-table-column prop="directInput" label="直接投入" min-width="100" align="right">
          <template #default="{ row }"><span class="cell-value">{{ fmtAmount(row.directInput) }}</span></template>
        </el-table-column>
        <el-table-column prop="depreciation" label="折旧费用" min-width="100" align="right">
          <template #default="{ row }"><span class="cell-value">{{ fmtAmount(row.depreciation) }}</span></template>
        </el-table-column>
        <el-table-column prop="amortization" label="摊销" min-width="90" align="right">
          <template #default="{ row }"><span class="cell-value">{{ fmtAmount(row.amortization) }}</span></template>
        </el-table-column>
        <el-table-column prop="otherExpense" label="其他" min-width="90" align="right">
          <template #default="{ row }"><span class="cell-value">{{ fmtAmount(row.otherExpense) }}</span></template>
        </el-table-column>
        <el-table-column label="合计" min-width="100" align="right">
          <template #header>
            <span class="formula-header" title="合计 = Σ各类费用">合计</span>
          </template>
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmount(row.totalExpense) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="rd.capitalizedRows.value.length === 0" description="暂无资本化研发项目" :image-size="40" />
    </div>

    <!-- ═══ 新增项目 ═══ -->
    <div class="dynamic-row-bar" v-if="!isReadonly">
      <el-button size="small" type="primary" plain @click="handleAddProject">
        <el-icon><Plus /></el-icon>新增研发项目
      </el-button>
    </div>

    <!-- ═══ 回填N5-5 ═══ -->
    <div class="action-bar">
      <el-button type="primary" size="small" :disabled="isReadonly" :loading="syncLoading" @click="handleSyncToTaxAdjustment">
        回填加计扣除额 → N5-5纳税调减
      </el-button>
      <span class="action-hint">加计扣除额 {{ fmtAmount(rd.totalDeduction.value) }}</span>
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
        <el-input v-model="auditNotes" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请说明研发费用归集合理性及加计扣除合规性..." :disabled="isReadonly" @change="saveNotes" />
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
        <li>研发费用六大类：人员人工/直接投入/折旧费用/无形资产摊销/新产品设计费/其他费用</li>
        <li>加计扣除额 = 研发费用合计 × 加计比例（一般100%）</li>
        <li>费用化研发费用当期全额加计扣除</li>
        <li>资本化研发费用按无形资产摊销年限分期加计扣除</li>
        <li>I6研发费用底稿提供费用化金额，I2开发支出底稿提供资本化金额</li>
        <li>加计扣除额回填N5-5纳税调整表调减项（研发费用加计扣除行）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N5TabRdSuperDeduction — 加计扣除研发费用情况明细表N5-6-1
 *
 * 43×7 + 17公式 + 研发费用六要素 + 加计比例
 * I6/I2联动(费用化+资本化) + 加计扣除额回填N5-5调减
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 4.10
 * Requirements: 5.1-5.5
 */
import { ref, computed, inject, onMounted, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, Plus } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import { useN5FormData } from '../../composables/useN5FormData'
import { useN5RdSuperDeduction } from '../../composables/useN5RdSuperDeduction'

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

const rd = useN5RdSuperDeduction({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  saveField: formData.setField,
  getField: formData.getField,
})

const selectedRate = ref(1.0)
const syncLoading = ref(false)
const auditNotes = ref('')
const auditConclusion = ref('')

// ─── 初始化 ──────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  selectedRate.value = rd.superRate.value || 1.0
  auditNotes.value = formData.getField('6-1', 'audit-notes') ?? ''
  auditConclusion.value = formData.getField('6-1', 'audit-conclusion') ?? ''
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

async function handleRateChange(rate: number) {
  await rd.setSuperRate(rate)
}

async function handleRowUpdate(index: number, field: string, value: any) {
  await rd.updateRow(index, field as any, value)
}

async function handleAddProject() {
  const { value: name } = await ElMessageBox.prompt('请输入研发项目名称', '新增研发项目', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPlaceholder: '如：XX系统研发',
  }).catch(() => ({ value: '' }))
  if (!name) return
  await rd.addProject(name)
  ElMessage.success(`已新增研发项目：${name}`)
}

async function handleSyncToTaxAdjustment() {
  syncLoading.value = true
  try {
    await rd.syncDeductionToTaxAdjustment()
    ElMessage.success(`加计扣除额${fmtAmount(rd.totalDeduction.value)}已回填N5-5`)
  } catch { ElMessage.error('回填失败') }
  finally { syncLoading.value = false }
}

async function saveNotes() { await formData.setField('6-1', 'audit-notes', auditNotes.value) }
async function saveConclusion() { await formData.setField('6-1', 'audit-conclusion', auditConclusion.value) }
function handleAiAssist() { ElMessage.info('AI辅助分析研发费用归集...') }
function handleNotesAi() { ElMessage.info('AI辅助生成审计说明...') }
function handleReview() { openReviewDialog ? openReviewDialog('N5-6-1-研发加计扣除') : ElMessage.info('复核对话未配置') }

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.n5-rd-super-deduction { padding: 12px; font-size: var(--wp-font-size, 13px); }
.methodology-context { padding: 12px 16px; margin-bottom: 16px; background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #92400e; line-height: 1.7; }
.methodology-context p { margin: 0; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 8px; }

.linkage-status { display: flex; gap: 16px; margin-bottom: 16px; }
.linkage-item { display: flex; align-items: center; gap: 8px; padding: 8px 14px; border-radius: 6px; font-size: var(--wp-font-size, 13px); }
.linkage-item.linked { background: #e8f5e9; border: 1px solid #a5d6a7; }
.linkage-item.pending { background: #f5f7fa; border: 1px solid #ebeef5; }
.lk-icon { font-size: 14px; }
.lk-label { color: #303133; font-weight: 500; }
.lk-value { font-weight: 600; color: #409eff; margin-left: auto; }

.super-rate-section { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; padding: 10px 16px; background: #f5f7fa; border: 1px solid #ebeef5; border-radius: 6px; }
.rate-label { font-weight: 500; color: #303133; }
.rate-value { font-weight: 600; color: #409eff; font-size: 15px; }

.deduction-summary-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
.ds-card { display: flex; flex-direction: column; align-items: center; padding: 12px; background: #fafbfc; border: 1px solid #ebeef5; border-radius: 8px; gap: 4px; }
.ds-card.highlight { background: #ecf5ff; border-color: #b3d8ff; }
.ds-label { font-size: 12px; color: #909399; }
.ds-value { font-size: 16px; font-weight: 700; color: #303133; }
.ds-value.primary { color: #409eff; }
.ds-sub { font-size: 11px; color: #c0c4cc; }

.rd-section { margin-bottom: 20px; }
.rd-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; padding: 6px 12px; background: #f5f7fa; border-radius: 4px; }
.rd-section-title { font-size: 14px; font-weight: 600; color: #303133; }
.rd-section-subtotal { font-size: var(--wp-font-size, 13px); font-weight: 500; color: #409eff; }
.rd-table { margin-bottom: 4px; }
:deep(.rd-table .el-table) { font-size: var(--wp-font-size, 13px); }
.item-name { font-weight: 500; color: #303133; }
.formula-header { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; font-weight: 500; color: #303133; padding-bottom: 1px; }
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
