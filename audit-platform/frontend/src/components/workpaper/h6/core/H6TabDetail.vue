<template>
  <div class="h6-tab-detail">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实固定资产清理各项目原值、累计折旧及净损益计算准确，确认清理事项真实、结转及时，为 1606 过渡科目期末应清零及 H10 处置损益提供审定依据。"
    />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>H6-2明细表：逐项登记每笔固定资产清理项目的全过程。25列拆分为2区段Tab展示（基础信息/清理信息）。核心公式：净值=原值-累计折旧；净损益=处置收入-净值-清理费用-税费。过渡科目期末余额应为0。</p>
    </div>

    <!-- Section Title -->
    <div class="section-header">
      <span>固定资产清理明细表 H6-2</span>
      <div class="section-header-actions">
        <el-button size="small" circle @click="openReview('H6-2-detail')">💬</el-button>
      </div>
    </div>

    <!-- 工具栏：底稿索引 + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H6-2" :context-project-id="props.projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 状态摘要 -->
    <div v-if="rows.length > 0" class="status-summary">
      <el-tag size="small" type="info">共 {{ statusSummary.total }} 项</el-tag>
      <el-tag v-if="statusSummary.clearing > 0" size="small" type="warning">清理中 {{ statusSummary.clearing }}</el-tag>
      <el-tag v-if="statusSummary.completed > 0" size="small" type="success">已完成 {{ statusSummary.completed }}</el-tag>
      <el-tag v-if="statusSummary.transferred > 0" size="small" type="primary">已结转 {{ statusSummary.transferred }}</el-tag>
      <!-- 已结转但净损益合计≠0警告 -->
      <el-tag v-if="hasTransferWarning" size="small" type="danger">
        ⚠ 存在已结转项目但净损益异常
      </el-tag>
    </div>

    <!-- 2区段Tab (el-segmented) -->
    <el-segmented v-model="activeTab" :options="segmentOptions" size="small" class="segment-bar" />

    <!-- 基础信息区段 -->
    <el-table
      v-if="activeTab === 'basic'"
      :data="rows"
      border
      stripe
      size="small"
      class="detail-table"
      row-key="rowId"
      max-height="480"
    >
      <el-table-column type="index" label="序号" width="55" align="center" />
      <el-table-column prop="assetName" label="资产名称" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.assetName" size="small"
            @change="updateCell(row.rowId, 'assetName', $event)" />
          <span v-else>{{ row.assetName }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="originalCost" label="原值" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.originalCost" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'originalCost', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.originalCost) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="accumulatedDepreciation" label="累计折旧" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.accumulatedDepreciation" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'accumulatedDepreciation', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.accumulatedDepreciation) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="netBookValue" label="净值" min-width="110" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="净值 = 原值 - 累计折旧">{{ fmtAmt(row.netBookValue) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="disposalReason" label="清理原因" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.disposalReason" size="small"
            @change="updateCell(row.rowId, 'disposalReason', $event)" />
          <span v-else>{{ row.disposalReason }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="startDate" label="开始日期" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.startDate" size="small"
            placeholder="YYYY-MM-DD"
            @change="updateCell(row.rowId, 'startDate', $event)" />
          <span v-else>{{ row.startDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="" width="45" v-if="!props.isReadonly">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleDeleteRow(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 清理信息区段 -->
    <el-table
      v-if="activeTab === 'disposal'"
      :data="rows"
      border
      stripe
      size="small"
      class="detail-table"
      row-key="rowId"
      max-height="480"
    >
      <el-table-column type="index" label="序号" width="55" align="center" />
      <el-table-column prop="assetName" label="资产名称" min-width="120" fixed />
      <el-table-column prop="disposalIncome" label="处置收入" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.disposalIncome" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'disposalIncome', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.disposalIncome) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="disposalExpenses" label="清理费用" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.disposalExpenses" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'disposalExpenses', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.disposalExpenses) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="taxAmount" label="税费" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.taxAmount" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'taxAmount', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.taxAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="gainLoss" label="净损益" min-width="110" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="净损益 = 处置收入 - 净值 - 清理费用 - 税费">
            {{ fmtAmt(row.gainLoss) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="transferAccount" label="结转科目" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.transferAccount" size="small"
            @change="updateCell(row.rowId, 'transferAccount', $event)" />
          <span v-else>{{ row.transferAccount || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="completionDate" label="完成日期" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.completionDate" size="small"
            placeholder="YYYY-MM-DD"
            @change="updateCell(row.rowId, 'completionDate', $event)" />
          <span v-else>{{ row.completionDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" min-width="110">
        <template #default="{ row }">
          <el-select v-if="!props.isReadonly" v-model="row.status" size="small"
            @change="handleStatusChange(row.rowId, $event)">
            <el-option value="清理中" label="清理中" />
            <el-option value="已完成" label="已完成" />
            <el-option value="已结转" label="已结转" />
          </el-select>
          <el-tag v-else :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="refH1Code" label="联动H1编号" min-width="130">
        <template #default="{ row }">
          <template v-if="!props.isReadonly">
            <el-input v-model="row.refH1Code" size="small" placeholder="H1-8-xxx"
              @change="updateCell(row.rowId, 'refH1Code', $event)" />
          </template>
          <GtIndexChip v-else-if="row.refH1Code" :value="row.refH1Code" :context-project-id="props.projectId" />
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="refH10Code" label="联动H10编号" min-width="130">
        <template #default="{ row }">
          <template v-if="!props.isReadonly">
            <el-input v-model="row.refH10Code" size="small" placeholder="H10-xxx"
              @change="updateCell(row.rowId, 'refH10Code', $event)" />
          </template>
          <GtIndexChip v-else-if="row.refH10Code" :value="row.refH10Code" :context-project-id="props.projectId" />
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <!-- 已结转但期末余额≠0红色警告 -->
      <el-table-column label="警告" width="60" align="center">
        <template #default="{ row }">
          <el-tooltip v-if="row.status === '已结转' && row.gainLoss !== 0"
            content="已结转但净损益≠0，请检查" placement="top">
            <span class="warning-icon">⚠</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="" width="45" v-if="!props.isReadonly">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleDeleteRow(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <el-card shadow="never" class="subtotal-card">
      <div class="subtotal-grid">
        <div class="subtotal-item">
          <span class="st-label">原值合计：</span>
          <span class="st-value">{{ fmtAmt(subtotalRow.originalCost) }}</span>
        </div>
        <div class="subtotal-item">
          <span class="st-label">累计折旧合计：</span>
          <span class="st-value">{{ fmtAmt(subtotalRow.accumulatedDepreciation) }}</span>
        </div>
        <div class="subtotal-item">
          <span class="st-label">净值合计：</span>
          <span class="st-value formula-cell" title="Σ净值 = Σ原值 - Σ累计折旧">{{ fmtAmt(subtotalRow.netBookValue) }}</span>
        </div>
        <div class="subtotal-item">
          <span class="st-label">处置收入合计：</span>
          <span class="st-value">{{ fmtAmt(subtotalRow.disposalIncome) }}</span>
        </div>
        <div class="subtotal-item">
          <span class="st-label">清理费用合计：</span>
          <span class="st-value">{{ fmtAmt(subtotalRow.disposalExpenses) }}</span>
        </div>
        <div class="subtotal-item">
          <span class="st-label">净损益合计：</span>
          <span class="st-value formula-cell" title="Σ净损益 = Σ处置收入 - Σ净值 - Σ清理费用 - Σ税费">{{ fmtAmt(subtotalRow.gainLoss) }}</span>
        </div>
      </div>
    </el-card>

    <!-- 操作栏 -->
    <div class="action-bar" v-if="!props.isReadonly">
      <el-button size="small" @click="handleAddRow">+ 添加清理项目</el-button>
      <el-dropdown trigger="click" @command="handleImportExport" style="margin-left: 8px">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计说明</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H6-2-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5, maxRows: 10 }"
        placeholder="请填写审计说明..." :disabled="props.isReadonly"
        @blur="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0">
          <span>审计结论</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H6-2-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计结论..." :disabled="props.isReadonly"
        @blur="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>25列宽表拆分为2区段（基础信息/清理信息），切换后行数据同步不丢失</li>
        <li>核心公式：净值=原值-累计折旧；净损益=处置收入-净值-清理费用-税费</li>
        <li>状态字段选项：清理中→已完成→已结转（依次流转）</li>
        <li>已结转状态但净损益≠0时触发红色警告，需检查是否有遗留差异</li>
        <li>联动H1编号：填写后可跳转至H1-8减少检查对应行</li>
        <li>联动H10编号：填写后可跳转至H10资产处置损益明细对应行</li>
        <li>合计行自动汇总所有项目，与H6-1审定表交叉验证</li>
        <li>公式列：虚线下划线+鼠标悬停显示公式来源（不可编辑）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H6TabDetail.vue — H6-2 明细表（25列2区块+净损益计算+GtIndexChip+动态行+导入导出）
 *
 * 2区段Tab (el-segmented):
 *   基础信息: 序号/资产名称/原值/累计折旧/净值(公式)/清理原因/开始日期
 *   清理信息: 处置收入/清理费用/税费/净损益(公式)/结转科目/完成日期/状态/联动H1编号/联动H10编号
 *
 * 功能：
 * - useH6Detail composable (公式自动计算+动态行+合计行)
 * - useH6ImportExport composable (三级导入导出)
 * - GtIndexChip (H1-8减少检查 / H10明细跳转)
 * - 状态选择：清理中/已完成/已结转 (el-select)
 * - 已结转且期末余额≠0→红色警告
 * - 新增行必须先弹ElMessageBox.prompt输入资产名称
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/
 * Task: 4.3
 * Requirements: 3.1-3.7
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useH6Detail, type H6DetailTab } from '../../composables/useH6Detail'
import { useH6ImportExport } from '../../composables/useH6ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
// 父入口提供的持久化函数（更新共享 Map + 防抖 PUT checklist-responses）。Bug C 修复：此前仅写内存 Map。
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', (itemId, value) => {
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
})

// ─── Composable ──────────────────────────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses)

const {
  rows, activeTab, subtotalRow, statusSummary,
  addRow, deleteRow, updateCell, setActiveTab, save, createFromH1Disposal,
} = useH6Detail({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

// ─── 注册 createFromH1Disposal 到主入口（EventBus联动） ──────────────────────
const registerDetailCreateFn = inject<(fn: (payload: any) => void) => void>('registerDetailCreateFn', () => {})

onMounted(() => {
  // 注册创建函数到主入口，供EventBus subscription使用
  registerDetailCreateFn(createFromH1Disposal)
  // 加载审计说明/结论
  const noteItem = props.allResponses.get('H6-2-note')
  if (noteItem?.remark) auditNote.value = noteItem.remark
  const concItem = props.allResponses.get('H6-2-conclusion')
  if (concItem?.remark) auditConclusion.value = concItem.remark
})

const importExport = useH6ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onImported: () => {
    // Reload data from allResponses after import
  },
})

// ─── Segment Options ─────────────────────────────────────────────────────────
const segmentOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '清理信息', value: 'disposal' },
]

// ─── 已结转+净损益≠0警告 ─────────────────────────────────────────────────────
const hasTransferWarning = computed(() => {
  return rows.value.some(r => r.status === '已结转' && r.gainLoss !== 0)
})

// ─── Audit Note / Conclusion ─────────────────────────────────────────────────
const auditNote = ref('')
function saveAuditNote() {
  saveResponse('H6-2-note', auditNote.value)
}
const auditConclusion = ref('')
function saveAuditConclusion() {
  saveResponse('H6-2-conclusion', auditConclusion.value)
}

// ─── Actions ─────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产名称', '添加清理项目', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '资产名称不能为空',
    })
    if (value) addRow(value)
  } catch { /* cancelled */ }
}

async function handleDeleteRow(rowId: string) {
  try {
    await ElMessageBox.confirm('确认删除该清理项目？删除后不可恢复。', '删除确认', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    deleteRow(rowId)
  } catch { /* cancelled */ }
}

function handleImportExport(command: string) {
  if (command === 'export-template') importExport.exportTemplate('H6-2')
  else if (command === 'export-data') importExport.exportData('H6-2')
  else if (command === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls,.csv'
    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) importExport.importData('H6-2', file)
    }
    input.click()
  }
}

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── Status Tag Type ─────────────────────────────────────────────────────────
function statusTagType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  switch (status) {
    case '清理中': return 'warning'
    case '已完成': return 'success'
    case '已结转': return 'info'
    default: return ''
  }
}

/**
 * 状态变更拦截：当明细行状态变为"已结转"时，
 * 发布 'disposal:completed' CustomEvent 通知 H10 记录处置损益。
 * Requirement 5.4: WHEN H6清理完成结转时, THE H6 SHALL publish 'disposal:completed'事件通知H10
 */
function handleStatusChange(rowId: string, newStatus: string): void {
  updateCell(rowId, 'status', newStatus)

  if (newStatus === '已结转') {
    const row = rows.value.find(r => r.rowId === rowId)
    if (row) {
      // 发布 disposal:completed → H10 资产处置损益
      window.dispatchEvent(new CustomEvent('disposal:completed', {
        detail: {
          wpCode: 'H6',
          assetName: row.assetName,
          gainLoss: row.gainLoss,
          refH10Code: row.refH10Code || '',
          refH1Code: row.refH1Code || '',
          originalCost: row.originalCost,
          netBookValue: row.netBookValue,
          disposalIncome: row.disposalIncome,
          disposalExpenses: row.disposalExpenses,
          taxAmount: row.taxAmount,
          completionDate: row.completionDate,
          linkageId: `h6-${row.rowId}`,
        },
      }))
    }
  }
}

// ─── 金额格式化 ──────────────────────────────────────────────────────────────
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  if (val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h6-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.methodology-context {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  font-size: 12px;
  color: #856404;
  line-height: 1.6;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-weight: 600;
  font-size: 14px;
}
.section-header-actions { display: flex; gap: 4px; align-items: center; }

.status-summary { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }

.tab-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-bottom: 10px;
}
.tab-toolbar .toolbar-right { display: flex; align-items: center; gap: 8px; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }

.segment-bar { margin-bottom: 12px; }

.detail-table { width: 100%; }

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #303133;
}

.amt-input { width: 100%; }
.amt-cell { font-variant-numeric: tabular-nums; }

.warning-icon { color: #f56c6c; font-size: 16px; }
.text-muted { color: #c0c4cc; }

.subtotal-card { margin-top: 12px; }
.subtotal-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px 16px;
}
.subtotal-item { display: flex; align-items: center; }
.st-label { font-size: 12px; color: #606266; white-space: nowrap; }
.st-value { font-weight: 600; font-size: var(--wp-font-size, 13px); color: #303133; margin-left: 4px; }

.action-bar { margin-top: 12px; display: flex; align-items: center; }

.audit-note-card { margin-top: 16px; }

.edit-tips {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
}
.edit-tips summary {
  cursor: pointer;
  font-weight: 500;
  color: #606266;
}
.edit-tips ul {
  margin: 8px 0 0;
  padding-left: 20px;
  line-height: 1.8;
}
</style>
