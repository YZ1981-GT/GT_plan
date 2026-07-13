<!--
  G6TabReversalWriteOff.vue — G6-14 减值准备转回（收回）、核销检查表

  42行×8列简洁动态行表格：
  序号|投资项目|转回/核销类型(下拉:转回/核销/收回)|金额|原因(textarea)|审批程序|合理性结论(下拉)|索引

  功能：
  - 动态行增删（ElMessageBox.prompt输入投资项目名称）
  - 底部金额合计行
  - 导入导出 el-dropdown（G6-14 单sheet）
  - AI按钮（reversal-write-off section结论）
  - 复核按钮（inject openReviewDialog）
  - GtIndexChip索引列

  Spec: .kiro/specs/g6-other-bond-investment-ecl/ Task 9.1
  Requirements: 5.1, 5.4
-->
<template>
  <div class="g6-reversal-writeoff">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>
        <strong>转回/核销判定标准：</strong>
        当导致减值的因素已消除且客观上与确认减值后发生事项有关时，可予转回（金额不超过原计提额）；
        当确认债务人确实无法偿还或以物抵债/债务重组等实质性处置完成时，经审批可予核销；
        收回指已核销坏账后续实际收到款项。三类操作均需充分审批程序和合理性说明。
      </p>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实其他债权投资减值准备转回、核销及收回的真实性与合规性，验证转回不超过原计提额、核销经恰当审批，评价各项操作的合理性。"
      class="objective-alert"
    />

    <!-- 工具栏：索引 + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G6-14" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 顶部标题+操作 -->
    <div class="section-head">
      <h3 class="sheet-title">G6-14 减值准备转回（收回）、核销检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 新增行
        </el-button>
        <!-- 导入导出 -->
        <el-dropdown trigger="click" @command="handleImportExportCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <!-- AI -->
        <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleAi">
          🤖 AI生成
        </el-button>
        <!-- 复核 -->
        <el-button size="small" @click="openReviewDialog('G6-14-reversal-writeoff')">💬复核</el-button>
      </div>
    </div>

    <!-- 主表格 -->
    <el-table
      :data="displayRows"
      border
      size="small"
      max-height="560"
      highlight-current-row
      row-key="id"
      :row-class-name="rowClassName"
      class="reversal-table"
    >
      <!-- 序号 -->
      <el-table-column label="序号" width="55" align="center">
        <template #default="{ row }">
          <span v-if="row._isTotal" class="total-label">合计</span>
          <span v-else>{{ row.seq }}</span>
        </template>
      </el-table-column>

      <!-- 投资项目 -->
      <el-table-column label="投资项目" min-width="130">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <span v-else>{{ row.investProject }}</span>
        </template>
      </el-table-column>

      <!-- 转回/核销类型 -->
      <el-table-column label="转回/核销类型" width="125" align="center">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <template v-else>
            <el-select v-if="!isReadonly" v-model="row.type" size="small" placeholder="请选择"
              style="width: 100px" @change="handleFieldChange">
              <el-option label="转回" value="转回" />
              <el-option label="核销" value="核销" />
              <el-option label="收回" value="收回" />
            </el-select>
            <span v-else>{{ row.type }}</span>
          </template>
        </template>
      </el-table-column>

      <!-- 金额 -->
      <el-table-column label="金额" min-width="120" align="right">
        <template #default="{ row }">
          <template v-if="row._isTotal">
            <span class="total-num">{{ fmtNum(totalAmount) }}</span>
          </template>
          <template v-else>
            <el-input-number v-if="!isReadonly" v-model="row.amount" size="small"
              :controls="false" class="compact-num" @change="handleFieldChange" />
            <span v-else>{{ fmtNum(row.amount) }}</span>
          </template>
        </template>
      </el-table-column>

      <!-- 原因 -->
      <el-table-column label="原因" min-width="160">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <template v-else>
            <el-input v-if="!isReadonly" v-model="row.reason" size="small" type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }" @change="handleFieldChange" />
            <span v-else>{{ row.reason }}</span>
          </template>
        </template>
      </el-table-column>

      <!-- 审批程序 -->
      <el-table-column label="审批程序" min-width="140">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <template v-else>
            <el-input v-if="!isReadonly" v-model="row.approvalProcedure" size="small"
              @change="handleFieldChange" />
            <span v-else>{{ row.approvalProcedure }}</span>
          </template>
        </template>
      </el-table-column>

      <!-- 合理性结论 -->
      <el-table-column label="合理性结论" width="115" align="center">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <template v-else>
            <el-select v-if="!isReadonly" v-model="row.reasonConclusion" size="small"
              placeholder="请选择" style="width: 95px" @change="handleFieldChange">
              <el-option label="合理" value="合理" />
              <el-option label="基本合理" value="基本合理" />
              <el-option label="不合理" value="不合理" />
            </el-select>
            <span v-else>{{ row.reasonConclusion }}</span>
          </template>
        </template>
      </el-table-column>

      <!-- 索引 -->
      <el-table-column label="索引" width="100">
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <template v-else>
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
            <el-input v-else-if="!isReadonly" v-model="row.indexRef" size="small" placeholder="索引"
              @change="handleFieldChange" />
          </template>
        </template>
      </el-table-column>

      <!-- 操作列（删除） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-popconfirm v-if="!row._isTotal" title="确认删除此行？" @confirm="handleDeleteRow(row.id)">
            <template #reference>
              <el-icon class="delete-icon"><Delete /></el-icon>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 审计说明 -->
    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="audit-note-header"><span>审计说明</span></div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述转回/核销/收回检查执行的审计程序、审批程序核查情况与结果、拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 底部审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <div class="conclusion-header">
        <span class="conclusion-title">审计结论</span>
      </div>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请输入转回核销检查的审计结论..."
        :disabled="isReadonly"
        @change="handleConclusionChange"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>转回：原计提减值的事由已消除，需说明具体消除原因</li>
        <li>核销：债务人确无偿还能力或完成债务重组/以物抵债，需附审批文件</li>
        <li>收回：已核销坏账后续实际收款，关注对当期损益影响</li>
        <li>三类操作均需充分的审批程序说明和合理性分析</li>
        <li>合理性结论：基于审批流程完整性和商业理由充分性综合判断</li>
      </ul>
    </details>

    <!-- 隐藏文件上传（导入数据用） -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display: none"
      @change="handleFileImport"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabReversalWriteOff.vue — G6-14 减值准备转回（收回）、核销检查表
 *
 * 42行×8列简洁动态行表格
 * 动态行增删（ElMessageBox.prompt输入投资项目名）+ 底部金额合计
 * 导入导出dropdown + AI结论 + 复核 + GtIndexChip
 *
 * Requirements: 5.1, 5.4
 */
import { ref, computed, inject, onMounted } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useG6EclFormData, type ReversalWriteOffRow } from '../../composables/useG6EclFormData'
import { useG6EclImportExport } from '../../composables/useG6EclImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

// ─── Props ──────────────────────────────────────────────────────────────────

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── inject openReviewDialog ────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── 数据状态 ───────────────────────────────────────────────────────────────

const rows = ref<ReversalWriteOffRow[]>([])
const conclusion = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

// ─── useG6EclFormData 用于持久化 ────────────────────────────────────────────

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)

const formData = useG6EclFormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

// ─── 审计说明（持久化 checklist_responses, conclusion:null） ───
const NOTE_KEY = 'G6-14-reversal-writeoff-audit-note'
const auditNote = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { conclusion: null, remark: val })
}

// ─── 导入导出 ───────────────────────────────────────────────────────────────

const importExport = useG6EclImportExport({
  wpId: wpIdRef,
  onImported: async () => {
    await loadData()
  },
})

// ─── 显示行（含底部合计行） ─────────────────────────────────────────────────

interface DisplayRow extends ReversalWriteOffRow {
  _isTotal?: boolean
}

const displayRows = computed<DisplayRow[]>(() => {
  const result: DisplayRow[] = [...rows.value]
  result.push({
    id: '__total__',
    seq: 0,
    investProject: '',
    type: '转回',
    amount: 0,
    reason: '',
    approvalProcedure: '',
    reasonConclusion: '合理',
    indexRef: '',
    _isTotal: true,
  })
  return result
})

/** 金额合计 */
const totalAmount = computed(() => {
  return rows.value.reduce((sum, r) => sum + (r.amount || 0), 0)
})

// ─── 行样式 ─────────────────────────────────────────────────────────────────

function rowClassName({ row }: { row: DisplayRow }): string {
  if (row._isTotal) return 'row-total'
  if (row.reasonConclusion === '不合理') return 'row-unreasonable'
  return ''
}

// ─── 动态行增删 ─────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '投资项目名称',
      inputValidator: (v: string) => (v && v.trim() ? true : '项目名称不能为空'),
    })
    if (!value?.trim()) return

    const newRow: ReversalWriteOffRow = {
      id: `rwo-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seq: rows.value.length + 1,
      investProject: value.trim(),
      type: '转回',
      amount: 0,
      reason: '',
      approvalProcedure: '',
      reasonConclusion: '合理',
      indexRef: '',
    }
    rows.value.push(newRow)
    handleFieldChange()
  } catch {
    // 用户取消
  }
}

function handleDeleteRow(rowId: string): void {
  const idx = rows.value.findIndex((r) => r.id === rowId)
  if (idx >= 0) {
    rows.value.splice(idx, 1)
    // 重新编号
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    handleFieldChange()
  }
}

// ─── 保存 ───────────────────────────────────────────────────────────────────

function handleFieldChange(): void {
  formData.debouncedSave('G6-14-reversal-writeoff-data', {
    conclusion: null,
    remark: JSON.stringify({ rows: rows.value, conclusion: conclusion.value }),
  })
}

function handleConclusionChange(): void {
  formData.saveImmediate('G6-14-reversal-writeoff-conclusion', {
    conclusion: conclusion.value,
  })
}

// ─── 导入导出 ───────────────────────────────────────────────────────────────

function handleImportExportCommand(command: string): void {
  switch (command) {
    case 'export-template':
      importExport.exportTemplate('G6-14')
      break
    case 'export-data':
      importExport.exportData('G6-14')
      break
    case 'import-data':
      fileInputRef.value?.click()
      break
  }
}

function handleFileImport(event: Event): void {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  importExport.importData('G6-14', file)
  target.value = ''
}

// ─── AI生成结论 ─────────────────────────────────────────────────────────────

async function handleAi(): Promise<void> {
  try {
    const { data } = await http.post(`/api/workpapers/${props.wpId}/g6-ecl/ai/reversal-write-off`, {
      rows: rows.value,
    })
    const text = data?.data?.conclusion || data?.conclusion
    if (text) {
      conclusion.value = text
      handleConclusionChange()
      ElMessage.success('AI结论已生成')
    }
  } catch {
    ElMessage.warning('AI生成暂不可用，请手动填写')
  }
}

// ─── 数字格式化 ─────────────────────────────────────────────────────────────

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

// ─── 数据加载 ───────────────────────────────────────────────────────────────

async function loadData(): Promise<void> {
  // 优先从 htmlData prop 加载
  const source = props.htmlData?.reversalWriteOff ?? props.htmlData
  if (source?.rows && Array.isArray(source.rows)) {
    rows.value = source.rows.map((r: any, idx: number) => ({
      id: r.id || `rwo-${idx}-${Date.now()}`,
      seq: r.seq ?? idx + 1,
      investProject: r.investProject || '',
      type: r.type || '转回',
      amount: r.amount ?? 0,
      reason: r.reason || '',
      approvalProcedure: r.approvalProcedure || '',
      reasonConclusion: r.reasonConclusion || '合理',
      indexRef: r.indexRef || '',
    }))
    if (source.conclusion) conclusion.value = source.conclusion
    return
  }

  // fallback: checklist-responses 加载
  await formData.loadAll()
  const resp = formData.allResponses.value.get('G6-14-reversal-writeoff-data')
  if (resp?.remark) {
    try {
      const parsed = JSON.parse(resp.remark)
      if (Array.isArray(parsed.rows)) {
        rows.value = parsed.rows
      }
      if (parsed.conclusion) conclusion.value = parsed.conclusion
    } catch { /* ignore parse error */ }
  }
  const conclResp = formData.allResponses.value.get('G6-14-reversal-writeoff-conclusion')
  if (conclResp?.conclusion) {
    conclusion.value = conclResp.conclusion
  }
}

// ─── 生命周期 ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadData()
  await formData.loadAll()
  const n = formData.allResponses.value.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
})

// ─── 暴露序列化接口 ─────────────────────────────────────────────────────────

defineExpose({
  toJSON: () => ({
    rows: rows.value,
    conclusion: conclusion.value,
    totalAmount: totalAmount.value,
  }),
})
</script>

<style scoped>
.g6-reversal-writeoff {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* 方法论上下文 */
.methodology-context {
  margin-bottom: 12px;
  padding: 10px 14px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: #606266;
}
.methodology-context p {
  margin: 0;
}
.methodology-context strong {
  color: #303133;
}

/* 审计目标 / 工具栏 */
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 审计说明卡片 */
.audit-note-card {
  margin-top: 16px;
}
.audit-note-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

/* 标题栏 */
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 表格 */
.reversal-table {
  font-size: var(--wp-font-size, 13px);
}

.compact-num {
  width: 100%;
}

.compact-num :deep(.el-input__inner) {
  text-align: right;
}

/* 不合理行 */
:deep(.row-unreasonable) {
  background-color: #fef0f0 !important;
}
:deep(.row-unreasonable td) {
  background-color: #fef0f0 !important;
}

/* 合计行 */
:deep(.row-total) {
  background-color: #ecf5ff !important;
  font-weight: 700;
}
:deep(.row-total td) {
  background-color: #ecf5ff !important;
}

.total-label {
  color: #409eff;
  font-weight: 700;
}

.total-num {
  font-weight: 700;
  color: #303133;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

/* 审计结论卡片 */
.conclusion-card {
  margin-top: 16px;
}

.conclusion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.conclusion-title {
  font-weight: 600;
  font-size: 14px;
}

/* 编制提示 */
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
.prep-hint li {
  margin-bottom: 4px;
}
</style>
