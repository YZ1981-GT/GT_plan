<script setup lang="ts">
/**
 * E1TabLargeCheck.vue — E1-23 收支检查
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.16
 *
 * - Uses useE1IpoSpecial with sheetCode='E1-23'
 * - Generic table driven by COLUMN_CONFIG['E1-23']
 * - Dynamic rows
 *
 * Requirements: 10.6
 */
import { ref, inject, toRef, onMounted, computed, type Ref } from 'vue'
import {
  useE1IpoSpecial,
  type IpoSheetCode,
  type ColumnDef,
} from '../composables/useE1IpoSpecial'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { amountFormatter, amountParser, isAmountColumn } from '../composables/wpAmountInput'
import { ElMessage } from 'element-plus'
import {
  pullSamplesForWorkpaper,
  listAttachedVouchers,
} from '../composables/useAttachedVouchers'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
  bsDate?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// ─── Composable ──────────────────────────────────────────────────────────────

const sheetCode: IpoSheetCode = 'E1-23'

const options: UseE1BaseOptions & { sheetCode: IpoSheetCode } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  sheetCode,
}

const {
  rows,
  columns,
  isLoading,
  addRow,
  removeRow,
  updateCell,
} = useE1IpoSpecial(options)

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getColWidth(col: ColumnDef): number {
  return col.width || (col.type === 'number' ? 130 : 150)
}

function formatCellValue(row: any, col: ColumnDef): string {
  const val = row[col.key]
  if (col.type === 'number' || col.type === 'computed') {
    return displayPrefs.fmtAmount(Number(val) || 0)
  }
  if (col.type === 'boolean') return val ? '是' : '否'
  return String(val || '')
}

// ─── 审计说明 / 审计结论 ─────────────────────────────────────────────────────

// ─── 抽凭引擎 ─────────────────────────────────────────────────────────────────

const samplingVisible = ref(false)
const samplingYear = computed(() => {
  const bs = props.bsDate || ''
  const match = bs.match(/^(\d{4})/)
  return match ? Number(match[1]) : new Date().getFullYear() - 1
})

/** 科目编码 → 所属科目名称（1001 现金 / 1002 银行存款 / 1012 其他货币资金） */
function accountNameOf(code: string): string {
  const c = String(code || '')
  if (c.startsWith('1001')) return '现金'
  if (c.startsWith('1002')) return '银行存款'
  if (c.startsWith('1012')) return '其他货币资金'
  return c
}

function onSampleFilled(payload: any): void {
  const samples = payload?.samples || []
  if (!Array.isArray(samples) || samples.length === 0) return
  let added = 0
  for (const s of samples) {
    const debit = Number(s.debitAmount) || 0
    const credit = Number(s.creditAmount) || 0
    // 货币资金借方=收入(现金流入)，贷方=支出(现金流出)
    const direction = debit > 0 ? '收' : credit > 0 ? '支' : ''
    // 按凭证号去重
    const voucherNo = s.voucherNo || ''
    if (voucherNo && rows.value.some(r => r.voucherNo === voucherNo)) continue
    addRow()
    const lastRow = rows.value[rows.value.length - 1]
    if (lastRow) {
      updateCell(lastRow.id, 'direction', direction)
      updateCell(lastRow.id, 'accountName', accountNameOf(s.accountCode))
      updateCell(lastRow.id, 'date', s.voucherDate || '')
      updateCell(lastRow.id, 'voucherNo', voucherNo)
      updateCell(lastRow.id, 'content', s.summary || '')
      updateCell(lastRow.id, 'counterAccount', s.counterpartAccount || '')
      updateCell(lastRow.id, 'amount', String(debit || credit || 0))
      if (s.abnormal) {
        updateCell(lastRow.id, 'isAbnormal', true)
        updateCell(lastRow.id, 'issue', '抽凭引擎标记异常，待核查')
      }
    }
    added++
  }
  samplingVisible.value = false
  ElMessage.success(added > 0 ? `已导入 ${added} 笔凭证` : '未新增（凭证号重复已跳过）')
}

// ─── 从序时账挂入导入（挂凭到底稿联动）─────────────────────────────────────

const attachedCount = ref(0)
const importingAttached = ref(false)
/** 货币资金科目前缀（收支检查取现金/银行/其他货币资金那条分录判收/支） */
const MF_ACCOUNT_PREFIXES = ['1001', '1002', '1012']

async function refreshAttachedCount(): Promise<void> {
  if (!props.projectId || !props.wpId) return
  try {
    const recs = await listAttachedVouchers(props.projectId, samplingYear.value, props.wpId)
    attachedCount.value = recs.length
  } catch {
    attachedCount.value = 0
  }
}

/** 拉取挂到本底稿的序时账凭证 → 映射为样本 → 复用 onSampleFilled 导入检查行 */
async function importFromAttached(): Promise<void> {
  if (props.isReadonly) return
  importingAttached.value = true
  try {
    const { samples } = await pullSamplesForWorkpaper(
      props.projectId,
      samplingYear.value,
      props.wpId,
      MF_ACCOUNT_PREFIXES,
    )
    if (samples.length === 0) {
      ElMessage.info('暂无挂入本底稿的序时账凭证。可在「账簿查询」右键凭证「挂凭到底稿」挂入。')
      return
    }
    onSampleFilled({ samples })
  } finally {
    importingAttached.value = false
  }
}

const NOTE_KEY = 'E1-largecheck-audit-note'
const CONCLUSION_KEY = 'E1-largecheck-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

onMounted(() => {
  const noteResp = props.allResponses.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
  const concResp = props.allResponses.get(CONCLUSION_KEY)
  if (concResp?.remark) auditConclusion.value = concResp.remark
  void refreshAttachedCount()
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
  <div class="e1-tab-large-check">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 检查大额及异常现金/银行收支的真实性、合规性与业务实质。</p>
        <p>2. 关注大额现金交易、频繁整数收支、无正常商业理由的资金往来及资金体外循环迹象。</p>
        <p>3. 核对收支凭证、合同、审批手续是否齐全，金额、对方账户是否与业务匹配。</p>
        <p>4. 重点关注与关联方、疑似虚构交易对手的大额资金往来，识别舞弊风险。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：检查大额及异常收支的真实性与合规性，识别资金舞弊及体外循环迹象。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="success">收支检查 (E1-23)</el-tag>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
        <el-button size="small" type="warning" :disabled="isReadonly" @click="samplingVisible = true">🎲 抽凭引擎</el-button>
        <el-badge :value="attachedCount" :hidden="attachedCount === 0" type="warning">
          <el-button
            size="small"
            :disabled="isReadonly"
            :loading="importingAttached"
            title="导入在「账簿查询」右键挂凭到本底稿的序时账凭证"
            @click="importFromAttached"
          >📎 从序时账挂入导入</el-button>
        </el-badge>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <el-table :data="rows" border stripe size="small" max-height="500" style="width: 100%">
          <el-table-column
            v-for="col in columns"
            :key="col.key"
            :label="col.label"
            :width="getColWidth(col)"
            :align="col.type === 'number' || col.type === 'computed' ? 'right' : 'left'"
            :class-name="col.type === 'computed' ? 'auto-calc-col' : ''"
          >
            <template #default="{ row }">
              <!-- Computed: readonly -->
              <span v-if="col.type === 'computed'" class="auto-calc-value">
                {{ formatCellValue(row, col) }}
              </span>
              <!-- Number -->
              <el-input-number
                v-else-if="col.type === 'number'"
                :model-value="row[col.key]"
                :disabled="isReadonly"
                :controls="false"
                :precision="isAmountColumn(col) ? 2 : undefined"
                :formatter="isAmountColumn(col) ? amountFormatter : undefined"
                :parser="isAmountColumn(col) ? amountParser : undefined"
                size="small"
                @change="(val: number) => updateCell(row.id, col.key, val ?? 0)"
              />
              <!-- Boolean -->
              <el-checkbox
                v-else-if="col.type === 'boolean'"
                :model-value="!!row[col.key]"
                :disabled="isReadonly"
                @change="(val: boolean) => updateCell(row.id, col.key, val)"
              />
              <!-- Date -->
              <el-date-picker
                v-else-if="col.type === 'date'"
                :model-value="row[col.key]"
                :disabled="isReadonly"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, col.key, val || '')"
              />
              <!-- Text (default) -->
              <el-input
                v-else
                :model-value="row[col.key]"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, col.key, val)"
              />
            </template>
          </el-table-column>

          <el-table-column label="操作" width="70" align="center" fixed="right">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" type="danger" text size="small"
                @click="removeRow(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 审计说明 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header"><span>审计说明</span></div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditNote"
            :disabled="isReadonly"
            :autosize="{ minRows: 5 }"
            placeholder="填写审计说明：可概述（1）大额及异常货币资金收支抽查的样本与检查内容（凭证、合同、审批手续齐全性）；（2）大额现金交易、频繁整数收支、无商业理由资金往来等异常事项的核查；（3）与关联方、疑似虚构对手方的大额往来及资金体外循环迹象。"
            @change="(val: string) => saveAuditNote(val)"
          />
        </el-card>

        <!-- 审计结论 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header"><span>审计结论</span></div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditConclusion"
            :disabled="isReadonly"
            :autosize="{ minRows: 3 }"
            placeholder="填写审计结论：A、货币资金收支真实、完整，原始凭证齐全，账务处理恰当，未见异常。B、除上述异常事项已查明原因并记录外，其余未见异常。C、由于存在以下疑似舞弊或体外循环迹象（或资料受限），需进一步核查。"
            @change="(val: string) => saveAuditConclusion(val)"
          />
        </el-card>
      </template>
    </el-skeleton>

    <!-- 抽凭引擎弹窗 -->
    <el-dialog
      v-model="samplingVisible"
      title="抽凭引擎 — 货币资金收支检查"
      width="1080px"
      append-to-body
      destroy-on-close
    >
      <GtVoucherSamplingEngine
        account-code="1002"
        phase="final"
        :workpaper-id="wpId"
        :project-id="projectId"
        :year="samplingYear"
        :initial-config-patch="{ accountCodes: ['1001', '1002', '1012'] }"
        config-hint="货币资金收支检查：默认总体含库存现金(1001)/银行存款(1002)/其他货币资金(1012)，可在抽样配置中调整科目范围。"
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<style scoped>
.e1-tab-large-check {
  padding: 12px 0;
}
.e1-tab-large-check :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-large-check :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
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

/* 工具栏 */
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
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc-value {
  color: #606266;
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
