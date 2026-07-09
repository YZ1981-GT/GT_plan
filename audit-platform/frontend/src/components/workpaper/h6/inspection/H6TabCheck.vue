<template>
  <div class="h6-tab-check">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>H6-4检查表：对每个固定资产清理项目进行合规性逐项检查，涵盖清理审批/资产评估/税务处理/会计处理/收入确认/费用归集/结转时点/核查结论8个维度。每个检查行对应H6-2明细表的一个清理项目。</p>
    </div>

    <!-- Section Title -->
    <div class="section-header">
      <span>检查表 H6-4</span>
      <div class="section-header-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" circle @click="openReview('H6-4-check')">💬</el-button>
      </div>
    </div>

    <!-- 不合规摘要 -->
    <el-alert
      v-if="summary.hasNonCompliant"
      type="error"
      :closable="false"
      show-icon
      class="non-compliant-alert"
    >
      <template #title>
        {{ summary.warning }}
      </template>
    </el-alert>

    <!-- 统计摘要条 -->
    <div class="summary-bar">
      <el-tag type="success" size="small">合规 {{ summary.compliantCount }}</el-tag>
      <el-tag type="danger" size="small">不合规 {{ summary.nonCompliantCount }}</el-tag>
      <el-tag type="info" size="small">不适用 {{ summary.notApplicableCount }}</el-tag>
      <span class="summary-total">共 {{ summary.totalChecks }} 项检查</span>
    </div>

    <!-- 检查表 -->
    <el-table
      :data="rows"
      border
      stripe
      size="small"
      class="check-table"
      row-key="rowId"
      max-height="560"
    >
      <el-table-column prop="seq" label="序号" width="48" align="center" fixed>
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>

      <el-table-column label="清理项目" min-width="120" fixed>
        <template #default="{ row }">
          <div class="project-name-cell">
            <span>{{ row.projectName || '-' }}</span>
            <el-button
              v-if="row.linkedDetailRowId"
              size="small"
              type="primary"
              link
              class="chip-jump"
              @click="handleJumpH6_2(row.linkedDetailRowId)"
            >↗H6-2</el-button>
          </div>
        </template>
      </el-table-column>

      <!-- 8个检查维度列 -->
      <el-table-column
        v-for="col in checkColumns"
        :key="col.field"
        :label="col.label"
        width="100"
        align="center"
      >
        <template #default="{ row }">
          <template v-if="!props.isReadonly">
            <el-radio-group
              :model-value="row[col.field]"
              size="small"
              class="compliance-radio"
              @change="(v: string) => handleUpdateCell(row.rowId, col.field, v)"
            >
              <el-radio-button
                v-for="opt in COMPLIANCE_OPTIONS"
                :key="opt"
                :value="opt"
                :class="getComplianceClass(opt)"
              >
                {{ optionShort(opt) }}
              </el-radio-button>
            </el-radio-group>
          </template>
          <el-tag v-else size="small" :type="getTagType(row[col.field])">
            {{ row[col.field] }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column label="备注" min-width="110">
        <template #default="{ row }">
          <el-input
            v-if="!props.isReadonly"
            :model-value="row.remark"
            size="small"
            placeholder="备注"
            @change="(v: string) => handleUpdateCell(row.rowId, 'remark', v)"
          />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 行级合规判定 -->
      <el-table-column label="行判定" width="72" align="center" fixed="right">
        <template #default="{ row }">
          <el-tag :type="isRowCompliant(row) ? 'success' : 'danger'" size="small">
            {{ isRowCompliant(row) ? '合规' : '不合规' }}
          </el-tag>
        </template>
      </el-table-column>

      <!-- 删除列 -->
      <el-table-column v-if="!props.isReadonly" label="" width="40" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleDeleteRow(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 操作栏 -->
    <div class="action-bar" v-if="!props.isReadonly">
      <el-button size="small" @click="handleAddRow">+ 添加检查行</el-button>
      <el-button size="small" type="primary" @click="handleSyncFromH6_2">
        从H6-2同步
      </el-button>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0">
          <span>审计说明</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI生成
            </el-button>
            <el-button size="small" circle @click="openReview('H6-4-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计说明..."
        :disabled="props.isReadonly"
        @blur="saveAuditNote"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>检查表每行对应H6-2明细表的一个清理项目</li>
        <li>8个检查维度：清理审批/资产评估/税务处理/会计处理/收入确认/费用归集/结转时点/核查结论</li>
        <li>每项选择"合规"（绿色）/"不合规"（红色）/"不适用"（灰色）</li>
        <li>存在"不合规"项时顶部显示红色警告摘要</li>
        <li>点击"从H6-2同步"可批量导入明细表全部清理项目</li>
        <li>点击"↗H6-2"可跳转到对应清理项目明细</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H6TabCheck.vue — H6-4 检查表（18列，清理过程逐项检查）
 *
 * 18列 = 序号 + 清理项目 + 8检查维度 + 备注 + 行判定
 * 8检查维度：清理审批/资产评估/税务处理/会计处理/收入确认/费用归集/结转时点/核查结论
 * 每项：合规/不合规/不适用
 * 不合规 → 顶部红色摘要 "发现x项不合规，请关注"
 * 与H6-2联动：每行对应一个清理项目，支持从H6-2同步
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/
 * Task: 4.5
 * Requirements: 4.3-4.6
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH6Check, type H6CheckRow, type CheckField, type ComplianceOption } from '../../composables/useH6Check'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string, label?: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  summary,
  nonCompliantRows,
  COMPLIANCE_OPTIONS,
  CHECK_FIELDS,
  addRow,
  addRowFromDetail,
  deleteRow,
  updateCell,
  syncFromDetailRows,
  save,
} = useH6Check({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  onSave: (itemId: string, value: any) => {
    const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
    props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
  },
})

// ─── 检查维度列定义 ──────────────────────────────────────────────────────────
const checkColumns: Array<{ field: CheckField; label: string }> = [
  { field: 'disposalApproval', label: '清理审批' },
  { field: 'assetValuation', label: '资产评估' },
  { field: 'taxTreatment', label: '税务处理' },
  { field: 'accountingTreatment', label: '会计处理' },
  { field: 'incomeRecognition', label: '收入确认' },
  { field: 'expenseAllocation', label: '费用归集' },
  { field: 'transferTiming', label: '结转时点' },
  { field: 'conclusion', label: '核查结论' },
]

// ─── Audit Note ──────────────────────────────────────────────────────────────
const auditNote = ref<string>('')

// 初始化加载
const existingNote = props.allResponses.get('H6-4-note')
if (existingNote) {
  auditNote.value = existingNote.remark || existingNote.conclusion || ''
}

function saveAuditNote() {
  props.allResponses.set('H6-4-note', { item_id: 'H6-4-note', remark: auditNote.value, conclusion: null })
}

// ─── Actions ─────────────────────────────────────────────────────────────────

function handleUpdateCell(rowId: string, field: string, value: any) {
  updateCell(rowId, field, value)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入清理项目名称', '添加检查行', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '项目名称不能为空',
    })
    if (value) addRow(value)
  } catch { /* cancelled */ }
}

function handleDeleteRow(rowId: string) {
  deleteRow(rowId)
}

/**
 * 从H6-2明细表同步：读取allResponses中的H6-2-rows数据，
 * 将每个清理项目创建为检查行
 */
function handleSyncFromH6_2() {
  const detailData = props.allResponses.get('H6-2-rows')
  if (!detailData) {
    ElMessageBox.alert('H6-2明细表暂无数据，请先在H6-2中添加清理项目。', '提示', { type: 'warning' })
    return
  }
  let detailRows: Array<{ rowId: string; assetName: string }> = []
  try {
    const raw = detailData.remark ?? detailData.conclusion ?? detailData
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (Array.isArray(parsed)) {
      detailRows = parsed.map((r: any) => ({
        rowId: r.rowId || r.id || '',
        assetName: r.assetName || r.projectName || r.name || '',
      }))
    }
  } catch { /* parse error */ }

  if (detailRows.length === 0) {
    ElMessageBox.alert('H6-2明细表暂无数据，请先在H6-2中添加清理项目。', '提示', { type: 'warning' })
    return
  }

  syncFromDetailRows(detailRows)
  ElMessageBox.alert(`已同步${detailRows.length}个清理项目到检查表。`, '同步完成', { type: 'success' })
}

function handleJumpH6_2(linkedDetailRowId: string) {
  emit('navigate-sheet', '明细表H6-2')
}

function handleAiGenerate() {
  console.log('[H6-4] AI generate')
}

function openReview(id: string) {
  openReviewDialog(id, 'H6-4 检查表')
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 行级合规判定：所有维度均为合规或不适用 → 合规 */
function isRowCompliant(row: H6CheckRow): boolean {
  return CHECK_FIELDS.every(f => row[f] !== '不合规')
}

/** 合规标签类型 */
function getTagType(val: ComplianceOption): '' | 'success' | 'danger' | 'info' {
  if (val === '合规') return 'success'
  if (val === '不合规') return 'danger'
  return 'info'
}

/** radio-button CSS类 */
function getComplianceClass(opt: ComplianceOption): string {
  if (opt === '合规') return 'compliance-green'
  if (opt === '不合规') return 'compliance-red'
  return 'compliance-gray'
}

/** 选项缩写（用于radio-button显示） */
function optionShort(opt: ComplianceOption): string {
  if (opt === '合规') return '✓'
  if (opt === '不合规') return '✗'
  return '—'
}
</script>

<style scoped>
.h6-tab-check { padding: 16px; font-size: 13px; }

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.6;
}

.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600; margin-bottom: 12px;
}
.section-header-actions { display: flex; align-items: center; gap: 4px; }

.non-compliant-alert { margin-bottom: 12px; }

.summary-bar {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 12px; padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}
.summary-total { margin-left: auto; font-size: 12px; color: var(--el-text-color-secondary); }

.check-table { font-size: 13px; margin-bottom: 12px; }

.project-name-cell { display: flex; align-items: center; gap: 4px; }
.chip-jump { font-size: 11px; padding: 0 4px; white-space: nowrap; }

/* 合规性 radio-button 组 */
.compliance-radio { display: flex; flex-wrap: nowrap; }
.compliance-radio :deep(.el-radio-button__inner) {
  padding: 4px 6px; font-size: 12px;
}
.compliance-green :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background-color: #67c23a; border-color: #67c23a; color: #fff;
}
.compliance-red :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background-color: #f56c6c; border-color: #f56c6c; color: #fff;
}
.compliance-gray :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background-color: #909399; border-color: #909399; color: #fff;
}

.action-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }

.audit-note-card { margin-bottom: 12px; }

.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
