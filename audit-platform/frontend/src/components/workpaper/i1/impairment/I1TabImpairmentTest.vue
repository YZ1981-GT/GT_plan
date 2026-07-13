<template>
  <div class="i1-tab-impairment-test">
    <!-- 方法论上下文 -->
    <div class="methodology-block">
      <p><strong>CAS8 资产减值</strong>：企业应当在资产负债表日判断资产是否存在减值迹象。资产存在减值迹象的，应当估计其可收回金额。可收回金额应当根据资产的公允价值减去处置费用后的净额与资产预计未来现金流量的现值两者之间较高者确定。资产的账面价值超过其可收回金额的，应当将资产的账面价值减记至可收回金额，减记的金额确认为资产减值损失。无形资产减值损失一经确认，在以后会计期间不得转回。</p>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实无形资产减值测试的完整性与减值准备计提的充分性（账面净值与可收回金额比较），确认减值损失一经确认不得转回。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:I1-12" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ impairmentRows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 主表区域 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">I1-12 减值准备测试表</span>
          <div class="section-header-actions">
            <el-dropdown v-if="!isReadonly" trigger="click" @command="handleExportImport">
              <el-button size="small">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" circle @click="openReview('I1-12')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="impairmentRows"
        border
        stripe
        size="small"
        class="impairment-table"
        :row-class-name="getRowClassName"
      >
        <el-table-column type="index" label="序号" width="50" align="center" />

        <!-- 资产名称 -->
        <el-table-column prop="name" label="资产名称" min-width="130" fixed>
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small"
              @blur="handleFieldUpdate($index, 'name', row.name)" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 账面原值 -->
        <el-table-column prop="cost" label="账面原值" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" v-model="row.cost" :controls="false"
              size="small" class="amt-input" @change="handleFieldUpdate($index, 'cost', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.cost) }}</span>
          </template>
        </el-table-column>

        <!-- 累计摊销 -->
        <el-table-column prop="accAmort" label="累计摊销" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" v-model="row.accAmort" :controls="false"
              size="small" class="amt-input" @change="handleFieldUpdate($index, 'accAmort', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.accAmort) }}</span>
          </template>
        </el-table-column>

        <!-- 减值准备 -->
        <el-table-column prop="impairmentProvision" label="减值准备" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" v-model="row.impairmentProvision" :controls="false"
              size="small" class="amt-input" @change="handleFieldUpdate($index, 'impairmentProvision', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.impairmentProvision) }}</span>
          </template>
        </el-table-column>

        <!-- 账面净值(公式) -->
        <el-table-column label="账面净值" min-width="110" align="right">
          <template #header>
            <span class="formula-header" title="= 账面原值 - 累计摊销 - 减值准备">账面净值</span>
          </template>
          <template #default="{ row }">
            <span class="formula-cell" title="= 原值 - 摊销 - 减值准备">{{ fmtAmt(row.netBookValue) }}</span>
          </template>
        </el-table-column>

        <!-- 可收回金额(联动I1-13) -->
        <el-table-column label="可收回金额" min-width="140" align="right">
          <template #header>
            <span class="formula-header" title="来源：I1-13 DCF测试或手工输入">可收回金额</span>
          </template>
          <template #default="{ row, $index }">
            <div class="recoverable-cell">
              <el-input-number v-if="!isReadonly && !row.linkedToDcf" v-model="row.recoverableAmount"
                :controls="false" size="small" class="amt-input"
                @change="handleFieldUpdate($index, 'recoverableAmount', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.recoverableAmount) }}</span>
              <GtIndexChip value="I1-13" label="DCF" @click="navigateToSheet('I1-13')" />
            </div>
          </template>
        </el-table-column>

        <!-- 应计提减值(公式) -->
        <el-table-column label="应计提减值" min-width="110" align="right">
          <template #header>
            <span class="formula-header" title="= MAX(账面净值 - 可收回金额, 0)">应计提减值</span>
          </template>
          <template #default="{ row }">
            <span class="formula-cell" title="= MAX(净值 - 可收回, 0)">{{ fmtAmt(row.shouldProvision) }}</span>
          </template>
        </el-table-column>

        <!-- 已计提 -->
        <el-table-column prop="alreadyProvided" label="已计提" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" v-model="row.alreadyProvided" :controls="false"
              size="small" class="amt-input" @change="handleFieldUpdate($index, 'alreadyProvided', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.alreadyProvided) }}</span>
          </template>
        </el-table-column>

        <!-- 差额(公式) -->
        <el-table-column label="差额" min-width="100" align="right">
          <template #header>
            <span class="formula-header" title="= 应计提减值 - 已计提">差额</span>
          </template>
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.difference) > 0.005 }]"
              title="= 应计提 - 已计提">
              {{ fmtAmt(row.difference) }}
            </span>
          </template>
        </el-table-column>

        <!-- 结论 -->
        <el-table-column prop="conclusion" label="结论" min-width="100" align="center">
          <template #default="{ row, $index }">
            <el-select v-if="!isReadonly" v-model="row.conclusion" size="small" style="width:100%"
              @change="handleFieldUpdate($index, 'conclusion', $event)">
              <el-option label="适当" value="适当" />
              <el-option label="需补提" value="需补提" />
              <el-option label="需关注" value="需关注" />
            </el-select>
            <el-tag v-else :type="row.conclusion === '适当' ? 'success' : 'danger'" size="small">
              {{ row.conclusion || '待判' }}
            </el-tag>
          </template>
        </el-table-column>

        <!-- 操作 -->
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link @click="handleRemoveRow($index)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计行 -->
      <div class="summary-row">
        <span class="summary-label">合计</span>
        <span class="summary-item">账面净值: <strong>{{ fmtAmt(impairmentSummary.totalNetBookValue) }}</strong></span>
        <span class="summary-item">应计提: <strong>{{ fmtAmt(impairmentSummary.totalShouldProvision) }}</strong></span>
        <span class="summary-item">已计提: <strong>{{ fmtAmt(impairmentSummary.totalAlreadyProvided) }}</strong></span>
        <span class="summary-item" :class="{ 'error-amount': Math.abs(impairmentSummary.totalDifference) > 0.005 }">
          差额合计: <strong>{{ fmtAmt(impairmentSummary.totalDifference) }}</strong>
        </span>
      </div>

      <!-- 新增行 -->
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增资产行</el-button>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计说明</span></div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5, maxRows: 10 }"
        placeholder="填写减值测试审计说明：减值迹象识别、测试方法与假设、可收回金额来源(I1-13)及核对情况等。"
        :disabled="isReadonly" @blur="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计结论</span></div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="填写审计结论：如经减值测试，各项无形资产可收回金额均高于其账面价值，无需计提减值准备…"
        :disabled="isReadonly" @blur="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>账面净值 = 账面原值 - 累计摊销 - 已计提减值准备</li>
        <li>应计提减值 = MAX(账面净值 - 可收回金额, 0)，不能为负</li>
        <li>差额 = 应计提 - 已计提，差额≠0表示需要补提或多提</li>
        <li>可收回金额来源：跳转I1-13 DCF测试表获取，或手工输入评估值</li>
        <li>CAS8规定：无形资产减值损失一经确认不得转回</li>
        <li>使用寿命不确定的无形资产，无论是否存在减值迹象，每年均应进行减值测试</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I1TabImpairmentTest.vue — I1-12 减值准备测试表
 * 14 formulas: 账面净值=原值-摊销-减值; 应计提=MAX(净值-可收回,0); 差额=应计提-已计提
 * + 合计行(4 SUM) + 红色高亮(差额≠0)
 * Spec: .kiro/specs/i1-intangible-assets/ | Requirements: 12.1-12.4
 */
import { ref, inject, toRef, computed, onMounted, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useI1Impairment } from '../../composables/useI1Impairment'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
  (e: 'save', itemId?: string, value?: any): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  impairmentRows,
  impairmentSummary,
  highlightedRowIds,
  addImpairmentRow,
  removeImpairmentRow,
  updateImpairmentField,
  importImpairmentRows,
  exportImpairmentRows,
} = useI1Impairment(
  toRef(props, 'wpId'),
  allResponsesRef as any,
  {
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

// ─── Local State: 审计说明 / 审计结论 ─────────────────────────────────────────

const auditNote = ref('')
const auditConclusion = ref('')

const NOTE_KEY = 'I1-12-audit-note'
const CONCLUSION_KEY = 'I1-12-audit-conclusion'

function loadAuditText(): void {
  const n = props.allResponses.get(NOTE_KEY)
  if (n) auditNote.value = (n.remark ?? n.conclusion ?? '') as string
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c) auditConclusion.value = (c.remark ?? c.conclusion ?? '') as string
}

onMounted(loadAuditText)
watch(() => props.allResponses, loadAuditText, { deep: true })

function saveAuditNote(): void {
  if (props.isReadonly) return
  emit('save', NOTE_KEY, auditNote.value)
}

function saveAuditConclusion(): void {
  if (props.isReadonly) return
  emit('save', CONCLUSION_KEY, auditConclusion.value)
}

// ─── Row Highlight (Req 12.4) ────────────────────────────────────────────────

function getRowClassName({ row }: { row: any }): string {
  if (highlightedRowIds.value.has(row.rowId)) {
    return 'row-highlight-danger'
  }
  return ''
}

// ─── Actions ─────────────────────────────────────────────────────────────────

function handleFieldUpdate(index: number, field: string, value: any) {
  updateImpairmentField(index, field as any, value)
}

async function handleAddRow() {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入资产名称', '新增减值测试行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '资产名称不能为空',
    })
    if (name) {
      addImpairmentRow({ name: name.trim(), cost: 0, accAmort: 0 })
    }
  } catch { /* cancelled */ }
}

function handleRemoveRow(index: number) {
  removeImpairmentRow(index)
}

function navigateToSheet(code: string) {
  emit('navigate-sheet', code)
}

function handleExportImport(command: string) {
  switch (command) {
    case 'export-template':
      console.log('[I1-12] Export template')
      break
    case 'export-data':
      console.log('[I1-12] Export data:', exportImpairmentRows())
      break
    case 'import-data':
      console.log('[I1-12] Import data')
      break
  }
}

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-impairment-test { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 方法论上下文 */
.methodology-block {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.objective-alert { margin-bottom: 12px; }

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-left { display: flex; gap: 8px; align-items: center; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-weight: 600; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }

/* 表格 */
.impairment-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }

/* 公式列样式 */
.formula-header {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

/* 差额≠0红色高亮 */
.error-amount { color: var(--el-color-danger); font-weight: 600; }
:deep(.row-highlight-danger) {
  background-color: #fef0f0 !important;
}
:deep(.row-highlight-danger td) {
  background-color: #fef0f0 !important;
}

/* 可收回金额单元格 */
.recoverable-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 合计行 */
.summary-row {
  padding: 12px 0;
  font-size: var(--wp-font-size, 13px);
  border-top: 2px solid var(--el-border-color);
  margin-top: 12px;
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  align-items: center;
}
.summary-label { font-weight: 700; min-width: 40px; }
.summary-item { font-variant-numeric: tabular-nums; }

.add-row-bar { margin-top: 12px; }
.audit-note-card { margin-bottom: 12px; }

/* 编制提示 */
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
