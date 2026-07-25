<script setup lang="ts">
/**
 * E1TabAdjustment.vue — E1-5 调整分录汇总
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.5
 *
 * 渲染：
 * - el-table 动态行：调整事项 | 类别(el-select) | 报表项目 | 科目名称 |
 *   附注项目 | 借方 | 贷方 | 索引 | 备注
 * - 底部：借方合计 / 贷方合计 / 平衡状态(✓绿/✗红+差额)
 * - 动态行增删
 * - "推送至A2"按钮
 * - el-skeleton加载占位
 *
 * Requirements: 5.1-5.5
 */
import { ref, inject, toRef, onMounted, type Ref } from 'vue'
import {
  useE1Adjustment,
  type AdjustmentRow,
  type AdjustmentCategory,
} from '../composables/useE1Adjustment'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { amountFormatter, amountParser } from '../composables/wpAmountInput'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '@/components/workpaper/composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import { useRouter } from 'vue-router'
import { Right } from '@element-plus/icons-vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
}

const {
  rows,
  totalDebit,
  totalCredit,
  balanceDiff,
  balanced,
  isLoading,
  addRow,
  removeRow,
  updateCell,
  pushToA2,
} = useE1Adjustment(options)

// ─── 同步到集中登记 ───────────────────────────────────────────────────────────
const { year: auditYear } = useAuditContext()
const {
  centralStatus,
  syncing: centralSyncing,
  syncToCentral,
  refreshStatus,
} = useAdjustmentCentralSync({
  projectId: () => props.projectId,
  year: auditYear,
  wpId: () => props.wpId,
  wpCode: 'E1',
  itemId: 'E1-5-adjustment',
  buildLineItems: () => rows.value.map((r: AdjustmentRow) => ({
    account_name: r.accountName,
    report_line_code: r.reportItem || undefined,
    debit_amount: r.debit,
    credit_amount: r.credit,
  })),
  buildMeta: () => ({
    description: rows.value.find((r: AdjustmentRow) => r.description)?.description || 'E1 调整',
    adjustmentType: rows.value.every((r: AdjustmentRow) => r.category === '报表调整') ? 'rje' : 'aje',
  }),
})
void refreshStatus()

// ─── 跳转到调整分录模块 ────────────────────────────────────────────────────────
const router = useRouter()
function goToAdjustmentModule() {
  if (!props.projectId) return
  router.push({ name: 'Adjustments', params: { projectId: props.projectId } })
}

// ─── Constants ───────────────────────────────────────────────────────────────

const categoryOptions: AdjustmentCategory[] = ['报表调整', '账项调整', '其他']

// ─── 审计说明 / 审计结论 ─────────────────────────────────────────────────────

const NOTE_KEY = 'E1-adjustment-audit-note'
const CONCLUSION_KEY = 'E1-adjustment-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

onMounted(() => {
  const noteResp = props.allResponses.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
  const concResp = props.allResponses.get(CONCLUSION_KEY)
  if (concResp?.remark) auditConclusion.value = concResp.remark
})

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY, item)
  void props.saveImmediate([item])
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  void props.saveImmediate([item])
}
</script>

<template>
  <div class="e1-tab-adjustment">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表汇总货币资金相关的调整分录（账项调整AJE/报表调整RJE）。</p>
        <p>2. 借方合计必须等于贷方合计，平衡时显示"✓ 平衡"，不平衡时显示差额并须查明原因。</p>
        <p>3. 类别选择"账项调整"影响科目余额并回写审定数；"报表调整"仅影响报表列报。</p>
        <p>4. 确认后可点击"推送至A2"将调整分录汇总至未审计报表调整底稿。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：汇总货币资金相关的调整分录，反映审计过程中发现的货币资金相关调整事项，确保借贷平衡并恰当归集至审定表及报表调整底稿。"
      class="objective-alert"
    />

    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <!-- 工具栏 -->
        <div class="tab-toolbar">
          <div class="toolbar-left">
            <el-button v-if="!isReadonly" type="primary" size="small" @click="addRow">
              + 新增行
            </el-button>
            <el-button v-if="!isReadonly" type="warning" size="small" @click="pushToA2">
              推送至A2
            </el-button>
            <el-button
              size="small"
              type="primary"
              plain
              :loading="centralSyncing"
              :disabled="isReadonly || !balanced || rows.length === 0"
              title="把本页调整分录同步到调整分录模块，供合伙人跨循环审阅"
              @click="syncToCentral"
            >
              同步到调整分录模块
            </el-button>
            <el-button
              size="small"
              type="primary"
              link
              :disabled="!projectId"
              title="前往调整分录模块查看全部调整分录"
              @click="goToAdjustmentModule"
            >
              前往调整分录模块<el-icon class="el-icon--right"><Right /></el-icon>
            </el-button>
          </div>
          <div class="toolbar-right">
            <span class="chip-wrap"><GtIndexChip value="wp:A2" :context-project-id="projectId" /></span>
            <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
            <el-tag
              v-if="centralStatus?.review_status"
              size="small"
              :type="centralStatus.review_status === 'approved' ? 'success' : (centralStatus.review_status === 'rejected' ? 'danger' : 'info')"
              :title="centralStatus.rejection_reason || ''"
            >
              集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status] || centralStatus.review_status }}
            </el-tag>
            <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
          </div>
        </div>

        <el-table :data="rows" border stripe size="small" style="width: 100%" max-height="500">
          <!-- 调整事项 -->
          <el-table-column label="调整事项" min-width="160">
            <template #default="{ row }">
              <el-input
                :model-value="row.description"
                :disabled="isReadonly"
                size="small"
                placeholder="调整事项说明"
                @change="(val: string) => updateCell(row.id, 'description', val)"
              />
            </template>
          </el-table-column>

          <!-- 类别 -->
          <el-table-column label="类别" width="120">
            <template #default="{ row }">
              <el-select
                :model-value="row.category"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'category', val)"
              >
                <el-option
                  v-for="cat in categoryOptions"
                  :key="cat"
                  :label="cat"
                  :value="cat"
                />
              </el-select>
            </template>
          </el-table-column>

          <!-- 报表项目 -->
          <el-table-column label="报表项目" width="130">
            <template #default="{ row }">
              <el-input
                :model-value="row.reportItem"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'reportItem', val)"
              />
            </template>
          </el-table-column>

          <!-- 科目名称 -->
          <el-table-column label="科目名称" width="130">
            <template #default="{ row }">
              <el-input
                :model-value="row.accountName"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'accountName', val)"
              />
            </template>
          </el-table-column>

          <!-- 附注项目 -->
          <el-table-column label="附注项目" width="120">
            <template #default="{ row }">
              <el-input
                :model-value="row.noteItem"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'noteItem', val)"
              />
            </template>
          </el-table-column>

          <!-- 借方 -->
          <el-table-column label="借方" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.debit"
                :disabled="isReadonly"
                :controls="false"
                :precision="2"
                :formatter="amountFormatter"
                :parser="amountParser"
                size="small"
                @change="(val: number | undefined) => updateCell(row.id, 'debit', val ?? 0)"
              />
            </template>
          </el-table-column>

          <!-- 贷方 -->
          <el-table-column label="贷方" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.credit"
                :disabled="isReadonly"
                :controls="false"
                :precision="2"
                :formatter="amountFormatter"
                :parser="amountParser"
                size="small"
                @change="(val: number | undefined) => updateCell(row.id, 'credit', val ?? 0)"
              />
            </template>
          </el-table-column>

          <!-- 索引 -->
          <el-table-column label="索引" width="100">
            <template #default="{ row }">
              <el-input
                :model-value="row.indexNo"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'indexNo', val)"
              />
            </template>
          </el-table-column>

          <!-- 备注 -->
          <el-table-column label="备注" min-width="120">
            <template #default="{ row }">
              <el-input
                :model-value="row.note"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'note', val)"
              />
            </template>
          </el-table-column>

          <!-- 操作 -->
          <el-table-column v-if="!isReadonly" label="操作" width="70" fixed="right" align="center">
            <template #default="{ row }">
              <el-button type="danger" text size="small" @click="removeRow(row.id)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- Balance Summary -->
        <div class="balance-summary">
          <div class="balance-item">
            <span class="balance-label">借方合计：</span>
            <span class="balance-val">{{ displayPrefs.fmtAmount(totalDebit) }}</span>
          </div>
          <div class="balance-item">
            <span class="balance-label">贷方合计：</span>
            <span class="balance-val">{{ displayPrefs.fmtAmount(totalCredit) }}</span>
          </div>
          <div class="balance-item">
            <span class="balance-label">平衡状态：</span>
            <span v-if="balanced" class="balance-ok">✓ 平衡</span>
            <span v-else class="balance-err">
              ✗ 不平衡（差额：{{ displayPrefs.fmtAmount(balanceDiff) }}）
            </span>
          </div>
        </div>

        <!-- 审计说明 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>审计说明</span>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditNote"
            :disabled="isReadonly"
            :autosize="{ minRows: 5 }"
            placeholder="填写审计说明..."
            @change="(val: string) => saveAuditNote(val)"
          />
        </el-card>

        <!-- 审计结论 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>审计结论</span>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditConclusion"
            :disabled="isReadonly"
            :autosize="{ minRows: 3 }"
            placeholder="填写审计结论..."
            @change="(val: string) => saveAuditConclusion(val)"
          />
        </el-card>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-adjustment {
  padding: 12px 0;
}
.e1-tab-adjustment :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-adjustment :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }
.balance-summary {
  display: flex;
  gap: 24px;
  padding: 12px;
  margin-top: 12px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  align-items: center;
  flex-wrap: wrap;
}
.balance-item {
  display: flex;
  align-items: center;
  gap: 4px;
}
.balance-label {
  font-weight: 600;
  color: #303133;
  font-size: var(--wp-font-size, 13px);
}
.balance-val {
  font-weight: 600;
  color: #606266;
  font-size: var(--wp-font-size, 13px);
}
.balance-ok {
  color: #67c23a;
  font-weight: 700;
  font-size: 14px;
}
.balance-err {
  color: #f56c6c;
  font-weight: 700;
  font-size: 14px;
}
.audit-note-card {
  margin-top: 16px;
}
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
</style>
