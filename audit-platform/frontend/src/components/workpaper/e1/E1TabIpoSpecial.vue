<script setup lang="ts">
/**
 * E1TabIpoSpecial.vue — E1-26~32 IPO组 (sheetCode分发)
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.17
 *
 * - Uses useE1IpoSpecial composable
 * - Props: sheetCode detected from sheetName
 * - Renders columns from COLUMN_CONFIG[sheetCode] dynamically
 * - Applicability switch: el-switch at top when isApplicable is false shows "未启用IPO程序"
 * - Dynamic rows
 *
 * Requirements: 11.1-11.9
 */
import { ref, computed, inject, toRef, onMounted, watch, type Ref } from 'vue'
import {
  useE1IpoSpecial,
  type IpoSheetCode,
  type ColumnDef,
  COLUMN_CONFIG,
} from '../composables/useE1IpoSpecial'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { amountFormatter, amountParser, isAmountColumn } from '../composables/wpAmountInput'

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

// ─── SheetCode Detection ─────────────────────────────────────────────────────

const sheetCode = computed<IpoSheetCode>(() => {
  const name = props.sheetName || ''
  const match = name.match(/E1-(\d+)/)
  if (match) {
    const code = `E1-${match[1]}` as IpoSheetCode
    if (code in COLUMN_CONFIG) return code
  }
  return 'E1-26'
})

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions & { sheetCode: IpoSheetCode } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  sheetCode: sheetCode.value,
}

const {
  rows,
  columns,
  isApplicable,
  isLoading,
  addRow,
  removeRow,
  updateCell,
} = useE1IpoSpecial(options)

// ─── Per-Sheet Metadata（对照源模板 E1-26~32 审计目标/提示） ───────────────────

interface SheetMeta {
  objective: string
  notePlaceholder: string
  conclusionPlaceholder: string
}

const SHEET_META: Record<string, SheetMeta> = {
  'E1-26': {
    objective: '审计目标：分析现金交易模式，识别异常现金交易与体外循环、虚构业务等舞弊风险。',
    notePlaceholder:
      '填写审计说明：（1）现金收付款总体规模及占当期收入/支出比重；（2）现金交易比例较高是否与行业结算惯例、业务性质匹配；（3）大额、异常时间、异常对象现金交易的核查情况；（4）实际控制人及董监高是否与客户/供应商存在现金往来。',
    conclusionPlaceholder:
      '填写审计结论：A、现金交易规模及模式与业务性质匹配，未见体外循环或虚构业务迹象。B、除下列异常事项外未见异常。C、发现舞弊迹象，已扩大测试并提请项目组关注。',
  },
  'E1-27': {
    objective: '审计目标：检查现金收支的截止性，确保现金收支记入正确会计期间。',
    notePlaceholder:
      '填写审计说明：（1）截止测试抽取的期间（资产负债表日前后各若干天）与金额门槛；（2）测试凭证与收付款凭单、原始凭单核对情况；（3）跨期事项的判定及对相关科目的影响；（4）如发现跨期是否已扩大测试期间至审计报告日。',
    conclusionPlaceholder:
      '填写审计结论：A、现金收支已记入正确会计期间，未见跨期错报。B、除下列跨期事项应提请调整外，其余未见异常。C、发现跨期舞弊迹象，已扩大测试期间。',
  },
  'E1-28': {
    objective: '审计目标：检查现金收支的真实性、完整性和准确性。',
    notePlaceholder:
      '填写审计说明：（1）测试总体、特定样本与抽样样本量、抽样方法及过程；（2）本期借方/贷方检查金额与检查比例；（3）现金销售/采购原始凭证（合同、收发货、收付款单证）的完整性与一致性核查；（4）异常收支事项的识别与处理。',
    conclusionPlaceholder:
      '填写审计结论：A、现金收支真实、完整、准确，原始凭证齐全一致。B、除下列异常外未见异常。C、检查比例偏低已扩大样本或说明原因。',
  },
  'E1-29': {
    objective: '审计目标：分析银行账户变动情况，识别异常账户及舞弊风险。',
    notePlaceholder:
      '填写审计说明：（1）已开立银行结算账户清单与账面、企业信用报告核对情况；（2）账户数量、开户/销户/零余额账户变动是否与业务规模匹配；（3）异地开户、个人账户资金往来、集团现金管理协议等异常情形；（4）募集资金存放使用是否合规。',
    conclusionPlaceholder:
      '填写审计结论：A、银行账户清单与账面、信用报告一致，账户变动合理。B、除下列异常账户外未见异常。C、发现账户异常/舞弊迹象，已作进一步核查。',
  },
  'E1-30': {
    objective: '审计目标：分析存款规模与利息收入的匹配性，识别异常情况。',
    notePlaceholder:
      '填写审计说明：（1）各类存款的规模、期限结构及适用利率；（2）理论利息收入的测算方法与假设；（3）理论利息与账面利息收入的差异及原因；（4）存款真实性、是否存在受限或资金占用迹象。',
    conclusionPlaceholder:
      '填写审计结论：A、存款规模与利息收入匹配，理论利息与账面无重大差异。B、差异已获合理解释。C、发现不匹配迹象，已核查存款真实性及资金占用。',
  },
  'E1-31': {
    objective: '审计目标：实施银行流水双向核对，验证资金往来的真实性与完整性。',
    notePlaceholder:
      '填写审计说明：（1）银行流水与账面记录双向核对（账面→流水、流水→账面）的范围与结果；（2）未入账流水、账外资金的识别；（3）大额、异常对手方、频繁往来资金的业务实质核查。',
    conclusionPlaceholder:
      '填写审计结论：A、银行流水与账面双向核对一致，资金往来真实完整。B、除下列差异外未见异常。C、发现账外资金/未入账流水，已作进一步核查。',
  },
  'E1-32': {
    objective: '审计目标：核查董监高及关键岗位人员银行流水，识别关联方资金占用及舞弊风险。',
    notePlaceholder:
      '填写审计说明：（1）取得董监高及关键岗位人员流水的范围与授权；（2）个人账户与公司、客户、供应商之间资金往来的核查；（3）大额、异常、无商业实质资金往来的识别与解释。',
    conclusionPlaceholder:
      '填写审计结论：A、未发现董监高及关键岗位人员与公司或交易对手存在异常资金往来。B、下列往来已获合理解释。C、发现关联方资金占用/舞弊迹象，已提请项目组关注。',
  },
}

const sheetMeta = computed<SheetMeta>(
  () =>
    SHEET_META[sheetCode.value] || {
      objective: '审计目标：针对 IPO 及舞弊风险执行专项核查，确认货币资金真实、完整且不存在体外循环。',
      notePlaceholder: '填写审计说明',
      conclusionPlaceholder: '填写审计结论',
    },
)

// ─── 审计说明 / 审计结论（按 sheetCode 分别存储） ─────────────────────────────

const NOTE_KEY = computed(() => `E1-ipo-audit-note-${sheetCode.value}`)
const CONCLUSION_KEY = computed(() => `E1-ipo-audit-conclusion-${sheetCode.value}`)
const auditNote = ref('')
const auditConclusion = ref('')

function loadAuditText(): void {
  auditNote.value = props.allResponses.get(NOTE_KEY.value)?.remark || ''
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY.value)?.remark || ''
}

onMounted(loadAuditText)
watch(sheetCode, loadAuditText)

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY.value, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY.value, item)
  void props.saveImmediate([item])
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY.value, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY.value, item)
  void props.saveImmediate([item])
}

// ─── Applicability Toggle ────────────────────────────────────────────────────

function toggleApplicability(val: boolean): void {
  if (props.isReadonly) return
  const key = 'E1-ipo-applicable'
  const conclusion = val ? 'Y' : 'N'
  const item = { item_id: key, conclusion, remark: null }
  props.allResponses.set(key, item)
  props.saveImmediate([item]).catch(() => {})
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getColWidth(col: ColumnDef): number {
  return col.width || (col.type === 'number' ? 130 : col.type === 'date' ? 130 : 150)
}

function formatCellValue(row: any, col: ColumnDef): string {
  const val = row[col.key]
  if (col.type === 'number' || col.type === 'computed') {
    return displayPrefs.fmtAmount(Number(val) || 0)
  }
  if (col.type === 'boolean') return val ? '是' : '否'
  return String(val || '')
}
</script>

<template>
  <div class="e1-tab-ipo-special">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 针对 IPO 及舞弊风险执行更严格的货币资金核查程序（E1-26~32），先确认本程序是否适用。</p>
        <p>2. 全额函证银行账户，核查资金流水的完整性，穿行测试大额资金往来的业务实质。</p>
        <p>3. 重点关注资金体外循环、大额异常资金往来、关联方资金占用与资金归集迹象。</p>
        <p>4. 执行未预先告知的现场监盘与银行流水穿行测试，评估管理层凌驾于控制之上的风险。</p>
      </div>
    </details>

    <!-- 审计目标（按 sheetCode 动态） -->
    <el-alert
      type="info"
      :closable="false"
      :title="sheetMeta.objective"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-switch
          :model-value="isApplicable"
          :disabled="isReadonly"
          active-text="已启用IPO/舞弊应对程序"
          inactive-text="未启用"
          @change="toggleApplicability"
        />
        <el-button v-if="isApplicable" size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
        <el-tag v-if="isApplicable" size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- Not applicable state -->
    <div v-if="!isApplicable" class="not-applicable">
      <el-empty description="未启用IPO程序" :image-size="80" />
    </div>

    <!-- Applicable: show table -->
    <el-skeleton v-else :loading="isLoading" :rows="10" animated>
      <template #default>
        <el-table :data="rows" border stripe size="small" max-height="550" style="width: 100%">
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
            :placeholder="sheetMeta.notePlaceholder"
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
            :placeholder="sheetMeta.conclusionPlaceholder"
            @change="(val: string) => saveAuditConclusion(val)"
          />
        </el-card>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-ipo-special {
  padding: 12px 0;
}
.e1-tab-ipo-special :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-ipo-special :deep(.el-table .cell) {
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
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

.not-applicable {
  padding: 40px 0;
}

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc-value {
  color: #606266;
}

/* 审计说明/结论卡片 */
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
