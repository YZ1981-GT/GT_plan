<template>
  <div class="h4-tab-disposal-check">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>H4-5减少检查：核查本期工程物资减少的合规性。分"基础信息"和"证据信息"两区块展示29列。减少原因为"领用出库"时必须填写对应H2编号（跳转H2在建工程），未填时黄色警告。</p>
    </div>

    <!-- Section Title -->
    <div class="section-header">
      <span>减少检查表 H4-5</span>
      <div class="section-header-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" circle @click="openReview('H4-5-disposal')">💬</el-button>
      </div>
    </div>

    <!-- H2联动警告 -->
    <el-alert v-if="missingH2Refs.length > 0" type="warning" :closable="false" show-icon
      style="margin-bottom: 12px">
      <template #title>
        {{ missingH2Refs.length }}行"领用出库"未填写对应H2编号
      </template>
    </el-alert>

    <!-- 区块1: 基础信息 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-header">基础信息</div>
      </template>
      <el-table :data="rows" border stripe size="small" class="check-table" row-key="rowId">
        <el-table-column prop="seq" label="序号" width="50" align="center" fixed />
        <el-table-column label="物资名称" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!props.isReadonly" v-model="row.name" size="small"
              @change="updateCell(row.rowId, 'name', $event)" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="规格型号" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!props.isReadonly" v-model="row.spec" size="small"
              @change="updateCell(row.rowId, 'spec', $event)" />
            <span v-else>{{ row.spec }}</span>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="70" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!props.isReadonly" v-model="row.quantity" :controls="false"
              size="small" class="amt-input"
              @change="updateCell(row.rowId, 'quantity', $event)" />
            <span v-else>{{ row.quantity || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!props.isReadonly" v-model="row.amount" :controls="false"
              size="small" class="amt-input"
              @change="updateCell(row.rowId, 'amount', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减少原因" width="110">
          <template #default="{ row }">
            <el-select v-if="!props.isReadonly" v-model="row.reason" size="small" placeholder="请选择"
              @change="updateCell(row.rowId, 'reason', $event)">
              <el-option v-for="opt in reasonOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <el-tag v-else size="small" :type="getReasonTagType(row.reason)">{{ row.reason || '-' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="减少日期" width="100">
          <template #default="{ row }">
            <el-input v-if="!props.isReadonly" v-model="row.disposalDate" size="small" placeholder="YYYY-MM-DD"
              @change="updateCell(row.rowId, 'disposalDate', $event)" />
            <span v-else>{{ row.disposalDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="40" v-if="!props.isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleDeleteRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 区块2: 证据信息 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-header">证据信息</div>
      </template>
      <el-table :data="rows" border stripe size="small" class="check-table" row-key="rowId">
        <el-table-column prop="seq" label="序号" width="50" align="center" fixed />
        <el-table-column prop="name" label="物资名称" min-width="90" fixed />
        <el-table-column label="领料单号" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!props.isReadonly" v-model="row.pickingNo" size="small"
              @change="updateCell(row.rowId, 'pickingNo', $event)" />
            <span v-else>{{ row.pickingNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="领用部门" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!props.isReadonly" v-model="row.department" size="small"
              @change="updateCell(row.rowId, 'department', $event)" />
            <span v-else>{{ row.department }}</span>
          </template>
        </el-table-column>
        <el-table-column label="领用工程项目" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!props.isReadonly" v-model="row.projectName" size="small"
              @change="updateCell(row.rowId, 'projectName', $event)" />
            <span v-else>{{ row.projectName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审批人" width="80">
          <template #default="{ row }">
            <el-input v-if="!props.isReadonly" v-model="row.approver" size="small"
              @change="updateCell(row.rowId, 'approver', $event)" />
            <span v-else>{{ row.approver }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对应H2编号" min-width="110">
          <template #default="{ row }">
            <div class="h2-ref-cell">
              <el-input v-if="!props.isReadonly" v-model="row.h2Ref" size="small"
                :class="{ 'h2-warning': row.reason === '领用出库' && !row.h2Ref }"
                placeholder="领用出库时必填"
                @change="updateCell(row.rowId, 'h2Ref', $event)" />
              <span v-else>{{ row.h2Ref }}</span>
              <el-button v-if="row.h2Ref" size="small" type="primary" link
                class="chip-jump" @click="handleJumpH2(row.h2Ref)">
                ↗H2
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="抽凭" width="55" align="center">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="handleVoucherSampling(row)">抽凭</el-button>
          </template>
        </el-table-column>
        <el-table-column label="核查结论" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!props.isReadonly" v-model="row.conclusion" size="small"
              @change="updateCell(row.rowId, 'conclusion', $event)" />
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="80">
          <template #default="{ row }">
            <el-input v-if="!props.isReadonly" v-model="row.remark" size="small"
              @change="updateCell(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="70">
          <template #default="{ row }">
            <el-input v-if="!props.isReadonly" v-model="row.refIndex" size="small"
              @change="updateCell(row.rowId, 'refIndex', $event)" />
            <span v-else>{{ row.refIndex }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 合计行 -->
    <div class="subtotal-bar">
      <span class="st-label">本期减少合计金额：</span>
      <span class="st-value">{{ fmtAmt(disposalTotal) }}</span>
    </div>

    <!-- 操作栏 -->
    <div class="action-bar" v-if="!props.isReadonly">
      <el-button size="small" @click="handleAddRow">+ 添加检查行</el-button>
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
        <div class="section-header" style="margin-bottom:0">
          <span>审计说明</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI生成
            </el-button>
            <el-button size="small" circle @click="openReview('H4-5-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计说明..." :disabled="props.isReadonly"
        @blur="saveAuditNote" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>减少原因：领用出库/退货/报废/盘亏/其他（下拉选择）</li>
        <li>领用出库时必须填写"对应H2编号"，点击"↗H2"可跳转到H2在建工程</li>
        <li>未填写H2编号时显示黄色警告</li>
        <li>支持行级抽凭（GtVoucherSamplingEngine dialog）</li>
        <li>底部显示本期减少合计金额</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabDisposalCheck.vue — H4-5 减少检查表（29列+联动H2）
 *
 * 2区块: 基础(序号/物资名/规格/数量/金额/减少原因/日期)
 *        证据(领料单号/领用部门/领用工程/审批人/H2编号/抽凭/结论/备注/索引)
 * H2联动: reason='领用出库' → require h2Ref → GtIndexChip跳转
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 4.6
 * Requirements: 6.1-6.6
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH4DisposalCheck, DISPOSAL_REASON_OPTIONS, type H4DisposalCheckRow } from '../../composables/useH4DisposalCheck'
import { useH4ImportExport } from '../../composables/useH4ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses)

const {
  rows, disposalTotal, missingH2Refs,
  addRow, deleteRow, updateCell, save,
} = useH4DisposalCheck({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  onSave: (itemId: string, value: any) => {
    const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
    props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
  },
})

const importExport = useH4ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

const reasonOptions = DISPOSAL_REASON_OPTIONS

// ─── Audit Note ──────────────────────────────────────────────────────────────
const auditNote = ref('')
function saveAuditNote() {
  props.allResponses.set('H4-5-note', { item_id: 'H4-5-note', remark: auditNote.value, conclusion: null })
}

// ─── Actions ─────────────────────────────────────────────────────────────────

function getReasonTagType(reason: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  switch (reason) {
    case '领用出库': return 'success'
    case '退货': return 'warning'
    case '报废': return 'danger'
    case '盘亏': return 'danger'
    default: return 'info'
  }
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入物资名称', '添加检查行', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) addRow(value)
  } catch { /* cancelled */ }
}

function handleDeleteRow(rowId: string) {
  deleteRow(rowId)
}

function handleVoucherSampling(row: H4DisposalCheckRow) {
  console.log('[H4-5] Voucher sampling for:', row.name)
}

function handleJumpH2(h2Ref: string) {
  // GtIndexChip跳转 to H2 在建工程：通过 navigate-sheet 事件通知外层切换底稿
  // h2Ref 格式如 "H2-3" → 跳转到 H2 在建工程对应行
  const targetSheet = h2Ref.startsWith('H2') ? `${h2Ref}` : `H2-1`
  emit('navigate-sheet', targetSheet)
}

function handleImportExport(command: string) {
  if (command === 'export-template') importExport.exportTemplate('H4-5')
  else if (command === 'export-data') importExport.exportData('H4-5')
  else if (command === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls,.csv'
    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) importExport.importData('H4-5', file)
    }
    input.click()
  }
}

function handleAiGenerate() {
  console.log('[H4-5] AI generate')
}

function openReview(id: string) {
  openReviewDialog(id)
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
.h4-tab-disposal-check { padding: 16px; font-size: 13px; }

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

.block-card { margin-bottom: 12px; }
.block-header { font-size: 13px; font-weight: 600; color: var(--el-text-color-regular); }

.check-table { font-size: 13px; }
.amt-input { width: 100%; }
.amt-cell { display: block; text-align: right; }

.h2-ref-cell { display: flex; align-items: center; gap: 4px; }
.h2-warning :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #e6a23c inset !important; background: #fdf6ec; }
.chip-jump { font-size: 11px; padding: 0 4px; white-space: nowrap; }

.subtotal-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; margin-bottom: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}
.st-label { color: var(--el-text-color-secondary); font-size: 12px; }
.st-value { font-weight: 700; font-variant-numeric: tabular-nums; font-size: 14px; }

.action-bar { display: flex; align-items: center; margin-bottom: 12px; }
.audit-note-card { margin-bottom: 12px; }
.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
