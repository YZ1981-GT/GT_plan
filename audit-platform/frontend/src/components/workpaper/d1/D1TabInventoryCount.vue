<script setup lang="ts">
/**
 * D1TabInventoryCount.vue — D1-10 应收票据监盘表 HTML渲染
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Task: 9.1
 *
 * 渲染（HTML 模式）：
 * - el-segmented 双模式切换（结构化视图 | 在线编辑）
 * - 审计目标区域（只读静态文本）
 * - el-table 15列宽表（横向滚动 max-height），嵌套分组表头：
 *   - "监盘日结存"二级表头（A-L 12列）
 *   - "核查结果"二级表头（M-O 3列）
 * - 差异="是"的行红色背景（row-class-name）
 * - "添加票据"按钮 + 动态行增删（el-popconfirm）
 * - 合计行（H21 sumAmount 自动计算）
 * - 核对区（A25-N25）
 * - 审计说明/结论（textarea + 🤖AI + 💬复核）
 * - 编制提示折叠区（<details>）
 * - GtOnlyOfficeSheet v-if isOOMode
 *
 * Requirements: 1.1-1.6, 2.1-2.5, 3.1-3.5, 14.1-14.5, 18.1-18.3, 18.6-18.7
 */
import { ref, inject, toRef, computed, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD1InventoryCount } from '../composables/useD1InventoryCount'
import {
  NOTE_TYPE_OPTIONS,
  NOTE_STATUS_OPTIONS,
  DIFFERENCE_OPTIONS,
  formatNegativeAmount,
  type InventoryCountRow,
} from '../composables/d1InspectionFormulas'
import type { ChecklistItem, ChecklistResponse } from '../composables/useD1FormData'
import GtOnlyOfficeSheet from '../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../GtIndexChip.vue'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
  displayPrefs: any
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const injectedDisplayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) =>
    v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话
const openReviewDialog = inject<any>('openReviewDialog', null)

// ─── Dual Mode (HTML ↔ OnlyOffice) ──────────────────────────────────────────

const editorMode = ref<'html' | 'oo'>('html')
const ooHealthy = ref(true)
const modeOptions = computed(() => [
  { label: '结构化视图', value: 'html' },
  { label: '在线编辑', value: 'oo', disabled: !ooHealthy.value },
])

const isOOMode = computed(() => editorMode.value === 'oo')
const ooSheetName = computed(() => props.sheetName || '应收票据监盘表D1-10')

onMounted(async () => {
  try {
    const health = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    ooHealthy.value = health.data?.data?.healthy ?? health.data?.healthy ?? false
  } catch { ooHealthy.value = false }
})

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  rows,
  addRow,
  removeRow,
  updateRow,
  sumAmount,
  reconArea,
  bookBalance,
  bookBalanceLoaded,
  differenceAmount,
  hasDifference,
  updateReconExplanation,
  updateReconConclusion,
  updateReconIndexRef,
  auditNote,
  auditConclusion,
  saveAuditNote,
  saveAuditConclusion,
} = useD1InventoryCount({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items: ChecklistItem[]) => {
    try {
      await http.post(`/api/workpapers/${props.wpId}/checklist-responses/batch`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  saveDebouncedText: (item: ChecklistItem) => {
    http.post(`/api/workpapers/${props.wpId}/checklist-responses/batch`, { items: [item] })
      .catch(() => { /* silent */ })
  },
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── Audit Conclusion Options ─────────────────────────────────────────────────

const CONCLUSION_OPTIONS = [
  '无差异，监盘结果与账面一致',
  '存在差异，已获合理解释',
  '存在差异，需进一步追查',
  '存在重大差异',
]

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) {
    const formatted = formatNegativeAmount(val)
    return `<span class="negative-amount">${formatted}</span>`
  }
  return injectedDisplayPrefs.fmtAmount(val)
}

// ─── Row Class ────────────────────────────────────────────────────────────────

function getRowClass({ row }: { row: InventoryCountRow }): string {
  return row.hasDifference === '是' ? 'difference-row' : ''
}

// ─── Review ────────────────────────────────────────────────────────────────────

function onReview(sectionId: string) {
  if (openReviewDialog) openReviewDialog({ sectionId })
}

// ─── 编制提示 ────────────────────────────────────────────────────────────────────

const GUIDANCE_TEXTS = [
  '票据监盘程序：监盘日逐笔清点在库票据，记录票据类型、号码、金额、出票日、到期日等关键信息，并与票据实物核对一致。',
  '监盘日倒推说明：若监盘日与资产负债表日不一致，需执行倒推程序——将监盘日结存加上监盘日至报表日期间收到的票据，减去该期间已背书/贴现/到期的票据，推算资产负债表日应有余额。',
  '差异追查：如存在监盘差异（票据缺失、金额不符、状态不一致），应逐笔查明原因，判断是否涉及舞弊或错报风险，并在审计说明中完整记录差异追查过程及最终结论。',
]

</script>

<template>
  <div class="d1-tab-inventory-count">
    <!-- Mode Switcher -->
    <div class="mode-switcher">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      <el-tooltip v-if="!ooHealthy" content="OnlyOffice服务不可用" placement="top">
        <span class="oo-disabled-hint">⚠️</span>
      </el-tooltip>
    </div>

    <!-- OnlyOffice mode -->
    <GtOnlyOfficeSheet
      v-if="isOOMode"
      :wp-id="wpId"
      :sheet-name="ooSheetName"
      :project-id="projectId"
    />

    <!-- HTML mode -->
    <template v-if="!isOOMode">
      <!-- 审计目标 -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="审计目标"
        class="audit-objective"
      >
        <template #default>
          <p>核实监盘日应收票据的实际结存情况，验证账面记录的存在性和完整性。</p>
          <p class="audit-procedure">审计程序：在监盘日对在库票据逐笔清点，记录票据关键信息（类型、号码、金额、出票人、承兑人、到期日等），与账面记录逐笔核对，确认是否存在差异。如监盘日与报表日不一致，需执行倒推程序。</p>
        </template>
      </el-alert>

      <!-- Toolbar -->
      <div class="table-toolbar">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">
          + 添加票据
        </el-button>
      </div>

      <!-- 15列宽表 -->
      <el-table
        :data="rows"
        border
        size="small"
        :row-class-name="getRowClass"
        max-height="500"
        class="inventory-table"
        style="width: 100%"
      >
        <!-- 监盘日结存（A-L 12列） -->
        <el-table-column label="监盘日结存" header-align="center">
          <!-- A: 票据类型 -->
          <el-table-column label="票据类型" width="130">
            <template #default="{ row }: { row: InventoryCountRow }">
              <el-select
                :model-value="row.noteType"
                placeholder="选择类型"
                size="small"
                clearable
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => updateRow(row.id, 'noteType', v || '')"
              >
                <el-option v-for="o in NOTE_TYPE_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
            </template>
          </el-table-column>

          <!-- B: 票据号 -->
          <el-table-column label="票据号" min-width="140">
            <template #default="{ row }: { row: InventoryCountRow }">
              <el-input
                :model-value="row.noteNo"
                size="small"
                placeholder="票据号"
                :disabled="isReadonly"
                @change="(v: string) => updateRow(row.id, 'noteNo', v || '')"
              />
            </template>
          </el-table-column>

          <!-- C: 出票日 -->
          <el-table-column label="出票日" width="120">
            <template #default="{ row }: { row: InventoryCountRow }">
              <el-date-picker
                :model-value="row.issueDate"
                type="date"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                size="small"
                placeholder="出票日"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => updateRow(row.id, 'issueDate', v || '')"
              />
            </template>
          </el-table-column>

          <!-- D: 出票人 -->
          <el-table-column label="出票人" min-width="100">
            <template #default="{ row }: { row: InventoryCountRow }">
              <el-input
                :model-value="row.drawer"
                size="small"
                placeholder="出票人"
                :disabled="isReadonly"
                @change="(v: string) => updateRow(row.id, 'drawer', v || '')"
              />
            </template>
          </el-table-column>

          <!-- E: 承兑人 -->
          <el-table-column label="承兑人" min-width="100">
            <template #default="{ row }: { row: InventoryCountRow }">
              <el-input
                :model-value="row.acceptor"
                size="small"
                placeholder="承兑人"
                :disabled="isReadonly"
                @change="(v: string) => updateRow(row.id, 'acceptor', v || '')"
              />
            </template>
          </el-table-column>

          <!-- F: 金额 -->
          <el-table-column label="金额" width="110" align="right">
            <template #default="{ row }: { row: InventoryCountRow }">
              <el-input-number
                :model-value="row.amount"
                size="small"
                :controls="false"
                :precision="2"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: number) => updateRow(row.id, 'amount', v || 0)"
              />
            </template>
          </el-table-column>

          <!-- G: 到期日 -->
          <el-table-column label="到期日" width="120">
            <template #default="{ row }: { row: InventoryCountRow }">
              <el-date-picker
                :model-value="row.maturityDate"
                type="date"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                size="small"
                placeholder="到期日"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => updateRow(row.id, 'maturityDate', v || '')"
              />
            </template>
          </el-table-column>

          <!-- H: 前手 -->
          <el-table-column label="前手" min-width="100">
            <template #default="{ row }: { row: InventoryCountRow }">
              <el-input
                :model-value="row.predecessor"
                size="small"
                placeholder="前手"
                :disabled="isReadonly"
                @change="(v: string) => updateRow(row.id, 'predecessor', v || '')"
              />
            </template>
          </el-table-column>

          <!-- I: 收到日期 -->
          <el-table-column label="收到日期" width="120">
            <template #default="{ row }: { row: InventoryCountRow }">
              <el-date-picker
                :model-value="row.receiveDate"
                type="date"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                size="small"
                placeholder="收到日期"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => updateRow(row.id, 'receiveDate', v || '')"
              />
            </template>
          </el-table-column>

          <!-- J: 背书/贴现日 -->
          <el-table-column label="背书贴现日" width="120">
            <template #default="{ row }: { row: InventoryCountRow }">
              <el-date-picker
                :model-value="row.endorseDate"
                type="date"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                size="small"
                placeholder="背书贴现日"
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => updateRow(row.id, 'endorseDate', v || '')"
              />
            </template>
          </el-table-column>

          <!-- K: 被背书人 -->
          <el-table-column label="被背书人" min-width="100">
            <template #default="{ row }: { row: InventoryCountRow }">
              <el-input
                :model-value="row.endorsee"
                size="small"
                placeholder="被背书人"
                :disabled="isReadonly"
                @change="(v: string) => updateRow(row.id, 'endorsee', v || '')"
              />
            </template>
          </el-table-column>

          <!-- L: 票据状态 -->
          <el-table-column label="票据状态" width="110">
            <template #default="{ row }: { row: InventoryCountRow }">
              <el-select
                :model-value="row.noteStatus"
                placeholder="状态"
                size="small"
                clearable
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => updateRow(row.id, 'noteStatus', v || '')"
              >
                <el-option v-for="o in NOTE_STATUS_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 核查结果（M-O 3列） -->
        <el-table-column label="核查结果" header-align="center">
          <!-- M: 是否存在差异 -->
          <el-table-column label="是否存在差异" width="120">
            <template #default="{ row }: { row: InventoryCountRow }">
              <el-select
                :model-value="row.hasDifference"
                placeholder="—"
                size="small"
                clearable
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => updateRow(row.id, 'hasDifference', v || '')"
              >
                <el-option v-for="o in DIFFERENCE_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
            </template>
          </el-table-column>

          <!-- N: 差异原因 -->
          <el-table-column label="差异原因" min-width="150">
            <template #default="{ row }: { row: InventoryCountRow }">
              <el-input
                type="textarea"
                :rows="2"
                :model-value="row.differenceReason"
                placeholder="差异原因..."
                :disabled="isReadonly || row.hasDifference !== '是'"
                @change="(v: string) => updateRow(row.id, 'differenceReason', v || '')"
              />
            </template>
          </el-table-column>

          <!-- O: 索引号 -->
          <el-table-column label="索引号" width="130">
            <template #default="{ row }: { row: InventoryCountRow }">
              <div class="index-cell">
                <el-input
                  :model-value="row.indexRef"
                  size="small"
                  placeholder="索引号"
                  :disabled="isReadonly"
                  @change="(v: string) => updateRow(row.id, 'indexRef', v || '')"
                />
                <GtIndexChip
                  v-if="row.indexRef"
                  :value="row.indexRef"
                  :context-project-id="projectId"
                />
              </div>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 操作列：删除 -->
        <el-table-column label="" width="50" fixed="right">
          <template #default="{ row }: { row: InventoryCountRow }">
            <el-popconfirm
              title="确定删除该行？"
              confirm-button-text="删除"
              cancel-button-text="取消"
              @confirm="removeRow(row.id)"
            >
              <template #reference>
                <el-button
                  v-if="!isReadonly"
                  type="danger"
                  size="small"
                  text
                  class="delete-btn"
                >
                  ✕
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计行 -->
      <div class="summary-row">
        <span class="summary-label">合计金额：</span>
        <span class="summary-value" v-html="fmtAmount(sumAmount)" />
      </div>

      <!-- 核对区 A25-N25 -->
      <div class="section-title">核对区</div>
      <table class="recon-table">
        <thead>
          <tr>
            <th>监盘日结存合计</th>
            <th>账面余额</th>
            <th>差异金额</th>
            <th>差异说明</th>
            <th>审计结论</th>
            <th>索引号</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <!-- 监盘日结存合计 -->
            <td class="recon-num" v-html="fmtAmount(sumAmount)" />

            <!-- 账面余额 -->
            <td class="recon-num">
              <template v-if="bookBalanceLoaded">
                <span v-html="fmtAmount(bookBalance)" />
              </template>
              <template v-else>
                <el-tooltip content="跨Spec审定表数据未加载" placement="top">
                  <span class="book-balance-warn">- ⚠️</span>
                </el-tooltip>
              </template>
            </td>

            <!-- 差异金额 -->
            <td
              class="recon-num"
              :class="{ 'diff-nonzero': differenceAmount !== 0 }"
              v-html="fmtAmount(differenceAmount)"
            />

            <!-- 差异说明 -->
            <td>
              <el-input
                type="textarea"
                :rows="2"
                :model-value="reconArea.explanation"
                placeholder="监盘差异说明..."
                :disabled="isReadonly"
                @change="(v: string) => updateReconExplanation(v || '')"
              />
            </td>

            <!-- 审计结论 -->
            <td>
              <el-select
                :model-value="reconArea.conclusion"
                placeholder="选择结论"
                size="small"
                clearable
                :disabled="isReadonly"
                style="width: 100%"
                @change="(v: string) => updateReconConclusion(v || '')"
              >
                <el-option v-for="o in CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
            </td>

            <!-- 索引号 -->
            <td>
              <div class="index-cell">
                <el-input
                  :model-value="reconArea.indexRef"
                  size="small"
                  placeholder="索引号"
                  :disabled="isReadonly"
                  @change="(v: string) => updateReconIndexRef(v || '')"
                />
                <GtIndexChip
                  v-if="reconArea.indexRef"
                  :value="reconArea.indexRef"
                  :context-project-id="projectId"
                />
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 审计说明 -->
      <div class="section-title">审计说明</div>
      <div class="note-section">
        <el-input
          type="textarea"
          :rows="4"
          :model-value="auditNote"
          placeholder="请输入审计说明..."
          :disabled="isReadonly"
          @change="(v: string) => saveAuditNote(v || '')"
        />
        <div class="note-actions">
          <el-tooltip content="AI生成（开发中）" placement="top">
            <el-button size="small" disabled>🤖 AI</el-button>
          </el-tooltip>
          <el-button
            v-if="openReviewDialog"
            size="small"
            @click="onReview('D1-inventory-note')"
          >
            💬 复核
          </el-button>
        </div>
      </div>

      <!-- 审计结论 -->
      <div class="section-title">审计结论</div>
      <div class="note-section">
        <el-input
          type="textarea"
          :rows="4"
          :model-value="auditConclusion"
          placeholder="请输入审计结论..."
          :disabled="isReadonly"
          @change="(v: string) => saveAuditConclusion(v || '')"
        />
        <div class="note-actions">
          <el-tooltip content="AI生成（开发中）" placement="top">
            <el-button size="small" disabled>🤖 AI</el-button>
          </el-tooltip>
          <el-button
            v-if="openReviewDialog"
            size="small"
            @click="onReview('D1-inventory-conclusion')"
          >
            💬 复核
          </el-button>
        </div>
      </div>

      <!-- 编制提示 -->
      <details class="guidance-fold">
        <summary>📋 编制提示</summary>
        <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
      </details>
    </template>
  </div>
</template>

<style scoped>
.d1-tab-inventory-count {
  padding: 12px;
}

.mode-switcher {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.oo-disabled-hint {
  cursor: help;
  font-size: 14px;
}

.audit-objective {
  margin-bottom: 12px;
}

.audit-objective p {
  margin: 0 0 4px;
  font-size: 13px;
  line-height: 1.6;
}

.audit-procedure {
  color: #606266;
  font-size: 12px;
}

.table-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
}

.inventory-table {
  margin-bottom: 12px;
}

/* 差异行红色背景 */
:deep(.el-table .difference-row td) {
  background-color: #fef0f0 !important;
}

/* 负数红色括号 */
:deep(.negative-amount) {
  color: #f56c6c;
}

/* 合计行 */
.summary-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 16px;
}

.summary-label {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.summary-value {
  font-size: 14px;
  font-weight: 700;
  color: #303133;
}

/* 段落标题 */
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 18px 0 10px;
}

/* 核对区表格 */
.recon-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-bottom: 16px;
}

.recon-table th,
.recon-table td {
  border: 1px solid #ebeef5;
  padding: 8px 10px;
  vertical-align: middle;
}

.recon-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
  text-align: center;
}

.recon-num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.diff-nonzero {
  color: #f56c6c !important;
  font-weight: 600;
}

.book-balance-warn {
  color: #e6a23c;
  font-size: 13px;
}

/* 索引号单元格 */
.index-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.index-cell .el-input {
  flex: 1;
}

/* 删除按钮 */
.delete-btn {
  padding: 2px 4px;
  min-height: auto;
}

/* 审计说明/结论 */
.note-section {
  margin-bottom: 8px;
}

.note-actions {
  margin-top: 6px;
  display: flex;
  gap: 8px;
}

/* 编制提示折叠区 */
.guidance-fold {
  margin: 16px 0;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  padding: 10px 14px;
  border-radius: 0 4px 4px 0;
  font-size: 13px;
  color: #606266;
}

.guidance-fold summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}

.guidance-fold p {
  margin: 6px 0;
  line-height: 1.6;
}
</style>
