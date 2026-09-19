<script setup lang="ts">
/**
 * E1TabCashCount.vue — E1-7/8 现金盘点 (variant: rmb/fx)
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.7
 *
 * - RMB模式：面值×张数=金额小计 + 汇总卡(实盘/账面/差异/原因)
 * - FX模式：币种+面值+张数+原币+汇率+折算人民币
 * - variant从sheetName检测: E1-7→rmb, E1-8→fx
 *
 * Requirements: 7.1-7.5
 */
import { inject, ref, toRef, computed, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useE1CashCount,
  type CashCountVariant,
  type CashRollForwardSummary,
  type RmbCountRow,
  type FxCountRow,
} from '../composables/useE1CashCount'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
import { useE1ImportExport } from '../composables/useE1ImportExport'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import WpAmountInput from '../shared/WpAmountInput.vue'

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
  variant?: Extract<CashCountVariant, 'rmb' | 'fx'>
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

// ─── Variant Detection ───────────────────────────────────────────────────────

const variant = computed<CashCountVariant>(() => {
  if (props.variant) return props.variant
  const name = props.sheetName || ''
  if (name.includes('E1-8') || name.includes('外币')) return 'fx'
  return 'rmb'
})

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions & { variant: CashCountVariant } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  variant: variant.value,
}

const {
  rows,
  rmbSummary,
  rmbTotal,
  actualTotal,
  isLoading,
  hasDiff,
  addRow,
  removeRow,
  updateCell,
  updateSummary,
} = useE1CashCount(options)

// ─── 导入导出（E1-7 rmb / E1-8 fx） ───────────────────────────────────────────

const sheetCode = computed(() => (variant.value === 'fx' ? 'E1-8' : 'E1-7'))
const { exportTemplate, exportData, importData, isImporting } = useE1ImportExport({
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  sheet: sheetCode as unknown as Ref<string>,
})

async function handleImport(file: File): Promise<boolean> {
  const res = await importData(file)
  if (res.success) {
    ElMessage.success(res.message || '导入成功')
    await reloadWorkpaperData?.()
  } else {
    ElMessage.warning(res.message || '导入失败')
  }
  return false // 阻止 el-upload 自动上传
}

// ─── Formula aliases / persistence keys ─────────────────────────────────────

const fxActualTotal = computed(() => (variant.value === 'fx' ? actualTotal.value : 0))
const fxCountDiff = computed(() => rmbSummary.value.overShort)
function fxHasDiff(): boolean { return hasDiff() }

const ELEMENTS_KEY = computed(() => `E1-cashcount-elements-${variant.value}`)
const NOTE_KEY = computed(() => `E1-cashcount-audit-note-${variant.value}`)
const CONCLUSION_KEY = computed(() => `E1-cashcount-audit-conclusion-${variant.value}`)

// ─── 监盘要素（盘点日期/时间/地点/参加人员/会计主管/出纳/监盘人） ─────────────

interface CountElements {
  countDate: string
  countTime: string
  countPlace: string
  participants: string
  accountant: string
  accountantDate: string
  cashier: string
  cashierDate: string
  supervisor: string
  supervisorDate: string
}
const countElements = ref<CountElements>({
  countDate: '',
  countTime: '',
  countPlace: '',
  participants: '',
  accountant: '',
  accountantDate: '',
  cashier: '',
  cashierDate: '',
  supervisor: '',
  supervisorDate: '',
})

function saveElements(): void {
  if (props.isReadonly) return
  const json = JSON.stringify(countElements.value)
  const item = { item_id: ELEMENTS_KEY.value, conclusion: null, remark: json }
  props.allResponses.set(ELEMENTS_KEY.value, item)
  void props.saveImmediate([item])
}

function updateElement(field: keyof CountElements, val: string): void {
  if (props.isReadonly) return
  countElements.value = { ...countElements.value, [field]: val ?? '' }
  saveElements()
}

// ─── 倒轧链 / 审计说明 / 审计结论 ─────────────────────────────────────────────

function updateRollForward(field: keyof CashRollForwardSummary, val: number | string | undefined): void {
  updateSummary(field, val ?? (field === 'diffReason' ? '' : 0))
}

const auditNote = ref('')
const auditConclusion = ref('')

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

const { generateText, isGenerating } = useE1AiGenerate(toRef(props, 'wpId') as Ref<string>)

function buildAiContext(): Record<string, unknown> {
  return {
    sheet: sheetCode.value,
    variant: variant.value,
    monitoring: countElements.value,
    rollForward: rmbSummary.value,
    countRows: rows.value,
  }
}

async function generateAuditNote(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: 'e1-audit-note',
    prompt: '请根据盘点过程、倒轧链、差异及证据索引生成专业、可追溯的审计说明。',
    context: buildAiContext(),
    existingContent: auditNote.value,
  })
  if (text) saveAuditNote(text)
}

async function generateAuditConclusion(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: 'e1-audit-conclusion',
    prompt: '请根据盘点结果生成审计结论，说明账实是否相符及是否存在需调整事项。',
    context: buildAiContext(),
    existingContent: auditConclusion.value,
  })
  if (text) saveAuditConclusion(text)
}

// ─── Hydration ─────────────────────────────────────────────────────────────

onMounted(() => {
  const elemResp = props.allResponses.get(ELEMENTS_KEY.value)
  if (elemResp?.remark) {
    try {
      const parsed = JSON.parse(elemResp.remark)
      countElements.value = { ...countElements.value, ...parsed }
    } catch { /* keep defaults */ }
  }
  const noteResp = props.allResponses.get(NOTE_KEY.value)
  if (noteResp?.remark) auditNote.value = noteResp.remark
  const concResp = props.allResponses.get(CONCLUSION_KEY.value)
  if (concResp?.remark) auditConclusion.value = concResp.remark
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

function asRmb(row: any): RmbCountRow { return row }
function asFx(row: any): FxCountRow { return row }
</script>

<template>
  <div class="e1-tab-cash-count">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示（现金监盘要点）</summary>
      <div class="guidance-content">
        <p>1. <b>突击监盘</b>：应选择恰当日期（通常为资产负债表日或临近日）对现金实施突击监盘，事先不通知出纳，由审计人员全程控制盘点过程直至结束，出纳当面清点、会计主管在场见证。</p>
        <p>2. <b>两处以上同时监盘</b>：存在两个及以上现金存放地点（含备用金、门店零用金等）时，应同时监盘或封存后逐一盘点，防止资金调剂掩盖短缺。</p>
        <p>3. <b>盘点金额与日记账核对</b>：将盘点实有数与现金日记账（盘点日上一日）余额核对，加减未记账收付凭证倒轧出应有数，与实有数比较得出长（短）款。</p>
        <p>4. <b>非资产负债表日盘点须调整至基准日</b>：盘点日与资产负债表日不一致时，通过"报表日至盘点日上一日累计收入数、累计支出数"倒轧回推至资产负债表日账面余额。</p>
        <p>5. <b>充抵库存现金的借条/未提现支票须注明</b>：列出冲抵库存现金的借条（日期、付款人、金额）及未做报销的费用凭证清单；关注白条抵库、坐支现金、以票充库等异常，差异≠0时须在差异原因中说明。</p>
        <p>6. 人民币按面值×张数汇总；外币按原币金额×期末汇率折算本位币，并执行汇率折算测试。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实资产负债表日库存现金的存在性与准确性，确认账实相符，识别白条抵库、坐支等异常。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" :type="variant === 'fx' ? 'warning' : 'success'">
          {{ variant === 'fx' ? '外币盘点 (E1-8)' : '人民币盘点 (E1-7)' }}
        </el-tag>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate()">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData()">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx,.xls"
                  :before-upload="handleImport"
                  :disabled="isImporting"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 监盘要素 -->
    <el-card class="elements-card" shadow="never">
      <template #header>
        <div class="card-header"><span>监盘要素</span></div>
      </template>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="盘点日期">
          <el-date-picker
            :model-value="countElements.countDate"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择盘点日期"
            :disabled="isReadonly"
            size="small"
            style="width: 100%"
            @update:model-value="(val: string) => updateElement('countDate', val)"
          />
        </el-descriptions-item>
        <el-descriptions-item label="盘点时间">
          <el-input
            :model-value="countElements.countTime"
            :disabled="isReadonly"
            placeholder="如 14:30"
            size="small"
            @change="(val: string) => updateElement('countTime', val)"
          />
        </el-descriptions-item>
        <el-descriptions-item label="盘点地点">
          <el-input
            :model-value="countElements.countPlace"
            :disabled="isReadonly"
            placeholder="如 财务部保险柜"
            size="small"
            @change="(val: string) => updateElement('countPlace', val)"
          />
        </el-descriptions-item>
        <el-descriptions-item label="参加人员">
          <el-input
            :model-value="countElements.participants"
            :disabled="isReadonly"
            placeholder="盘点参加人员"
            size="small"
            @change="(val: string) => updateElement('participants', val)"
          />
        </el-descriptions-item>
        <el-descriptions-item label="会计主管签字">
          <div class="signature-field">
            <el-input
              :model-value="countElements.accountant"
              :disabled="isReadonly"
              placeholder="会计主管姓名/签字"
              size="small"
              @change="(val: string) => updateElement('accountant', val)"
            />
            <el-date-picker
              :model-value="countElements.accountantDate"
              :disabled="isReadonly"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="签字日期"
              size="small"
              @update:model-value="(val: string) => updateElement('accountantDate', val || '')"
            />
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="出纳签字">
          <div class="signature-field">
            <el-input
              :model-value="countElements.cashier"
              :disabled="isReadonly"
              placeholder="出纳姓名/签字"
              size="small"
              @change="(val: string) => updateElement('cashier', val)"
            />
            <el-date-picker
              :model-value="countElements.cashierDate"
              :disabled="isReadonly"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="签字日期"
              size="small"
              @update:model-value="(val: string) => updateElement('cashierDate', val || '')"
            />
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="监盘人签字">
          <div class="signature-field">
            <el-input
              :model-value="countElements.supervisor"
              :disabled="isReadonly"
              placeholder="监盘人姓名/签字"
              size="small"
              @change="(val: string) => updateElement('supervisor', val)"
            />
            <el-date-picker
              :model-value="countElements.supervisorDate"
              :disabled="isReadonly"
              type="date"
              value-format="YYYY-MM-DD"
              placeholder="签字日期"
              size="small"
              @update:model-value="(val: string) => updateElement('supervisorDate', val || '')"
            />
          </div>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <!-- RMB 模式 -->
        <template v-if="variant === 'rmb'">
          <el-table :data="rows" border stripe size="small" max-height="500" style="width: 100%">
            <el-table-column label="面值" width="120" align="center">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asRmb(row).denomination"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'denomination', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="张数" width="120" align="center">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asRmb(row).quantity"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'quantity', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="金额小计" width="150" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span class="auto-calc-value">{{ displayPrefs.fmtAmount(asRmb(row).subtotal) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="!isReadonly"
                  type="danger"
                  text
                  size="small"
                  @click="removeRow(row.id)"
                >删除</el-button>
              </template>
            </el-table-column>
          </el-table>

        </template>

        <!-- FX 模式 -->
        <template v-else>
          <el-table :data="rows" border stripe size="small" max-height="500" style="width: 100%">
            <el-table-column label="币种" width="100">
              <template #default="{ row }">
                <el-input
                  :model-value="asFx(row).currency"
                  :disabled="isReadonly"
                  size="small"
                  @change="(val: string) => updateCell(row.id, 'currency', val)"
                />
              </template>
            </el-table-column>
            <el-table-column label="面值" width="100" align="center">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asFx(row).denomination"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'denomination', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="张数" width="100" align="center">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asFx(row).quantity"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'quantity', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="原币金额" width="130" align="right">
              <template #default="{ row }">
                <WpAmountInput
 :model-value="asFx(row).fcAmount"
 :disabled="isReadonly"
 size="small"
 @change="(val: number) => updateCell(row.id, 'fcAmount', val ?? 0)" />
              </template>
            </el-table-column>
            <el-table-column label="汇率" width="100" align="center">
              <template #default="{ row }">
                <el-input-number
                  :model-value="asFx(row).fxRate"
                  :disabled="isReadonly"
                  :controls="false"
                  :precision="4"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'fxRate', val ?? 0)"
                />
              </template>
            </el-table-column>
            <el-table-column label="折算人民币" width="150" align="right" class-name="auto-calc-col">
              <template #default="{ row }">
                <span class="auto-calc-value">{{ displayPrefs.fmtAmount(asFx(row).rmbAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80" align="center" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-if="!isReadonly"
                  type="danger"
                  text
                  size="small"
                  @click="removeRow(row.id)"
                >删除</el-button>
              </template>
            </el-table-column>
          </el-table>

        </template>

        <!-- E1-7/8 完整倒轧链 -->
        <el-card class="summary-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span>盘点倒轧及账实核对</span>
              <el-tag size="small" type="info">金额单位：元</el-tag>
            </div>
          </template>
          <el-descriptions :column="2" border size="small" class="roll-forward-grid">
            <el-descriptions-item label="报表日现金账面余额">
              <WpAmountInput
 :model-value="rmbSummary.reportDateBookBalance"
 :disabled="isReadonly"
 size="small"
 @change="(val: number) => updateRollForward('reportDateBookBalance', val)" />
            </el-descriptions-item>
            <el-descriptions-item label="报表日至盘点日前一日累计收入">
              <WpAmountInput
 :model-value="rmbSummary.cumulativeIncome"
 :disabled="isReadonly"
 size="small"
 @change="(val: number) => updateRollForward('cumulativeIncome', val)" />
            </el-descriptions-item>
            <el-descriptions-item label="报表日至盘点日前一日累计支出">
              <WpAmountInput
 :model-value="rmbSummary.cumulativeExpense"
 :disabled="isReadonly"
 size="small"
 @change="(val: number) => updateRollForward('cumulativeExpense', val)" />
            </el-descriptions-item>
            <el-descriptions-item label="盘点日前一日账面余额（公式）" class-name="formula-item">
              <span class="formula-value" title="报表日现金账面余额 + 累计收入 - 累计支出">
                {{ displayPrefs.fmtAmount(rmbSummary.priorDayBookBalance) }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item label="收入凭证未记账">
              <WpAmountInput
 :model-value="rmbSummary.receiptVoucherUnposted"
 :disabled="isReadonly"
 size="small"
 @change="(val: number) => updateRollForward('receiptVoucherUnposted', val)" />
            </el-descriptions-item>
            <el-descriptions-item label="支出凭证未记账">
              <WpAmountInput
 :model-value="rmbSummary.paymentVoucherUnposted"
 :disabled="isReadonly"
 size="small"
 @change="(val: number) => updateRollForward('paymentVoucherUnposted', val)" />
            </el-descriptions-item>
            <el-descriptions-item label="未做凭证收入">
              <WpAmountInput
 :model-value="rmbSummary.unvoucheredIncome"
 :disabled="isReadonly"
 size="small"
 @change="(val: number) => updateRollForward('unvoucheredIncome', val)" />
            </el-descriptions-item>
            <el-descriptions-item label="未做凭证支出">
              <WpAmountInput
 :model-value="rmbSummary.unvoucheredExpense"
 :disabled="isReadonly"
 size="small"
 @change="(val: number) => updateRollForward('unvoucheredExpense', val)" />
            </el-descriptions-item>
            <el-descriptions-item label="盘点日应有数（公式）" class-name="formula-item">
              <span class="formula-value" title="盘点日前一日账面余额 + 收入凭证未记账 - 支出凭证未记账 + 未做凭证收入 - 未做凭证支出">
                {{ displayPrefs.fmtAmount(rmbSummary.expectedCountAmount) }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item label="实有数（公式）" class-name="formula-item">
              <span class="formula-value" title="盘点明细金额合计">
                {{ displayPrefs.fmtAmount(variant === 'fx' ? fxActualTotal : rmbTotal) }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item label="长（短）款（公式）" class-name="formula-item">
              <span
                :class="['formula-value', { 'orange-text': variant === 'fx' ? fxHasDiff() : hasDiff() }]"
                title="实有数 - 盘点日应有数；正数为长款，负数为短款"
              >{{ displayPrefs.fmtAmount(variant === 'fx' ? fxCountDiff : rmbSummary.overShort) }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="差异原因">
              <el-input
                :model-value="rmbSummary.diffReason"
                :disabled="isReadonly"
                :class="{ 'required-input': hasDiff() && !rmbSummary.diffReason.trim() }"
                placeholder="长（短）款不为0时必填"
                size="small"
                @change="(val: string) => updateRollForward('diffReason', val)"
              />
            </el-descriptions-item>
            <template v-if="variant === 'fx'">
              <el-descriptions-item label="期末汇率">
                <el-input-number
                  :model-value="rmbSummary.closingFxRate"
                  :disabled="isReadonly"
                  :controls="false"
                  :precision="6"
                  size="small"
                  @change="(val: number) => updateRollForward('closingFxRate', val)"
                />
              </el-descriptions-item>
              <el-descriptions-item label="报表日原币账面">
                <WpAmountInput
 :model-value="rmbSummary.reportDateForeignBookBalance"
 :disabled="isReadonly"
 size="small"
 @change="(val: number) => updateRollForward('reportDateForeignBookBalance', val)" />
              </el-descriptions-item>
              <el-descriptions-item label="应有本位币（公式）" class-name="formula-item">
                <span class="formula-value" title="报表日原币账面 × 期末汇率">
                  {{ displayPrefs.fmtAmount(rmbSummary.expectedFunctionalCurrency) }}
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="汇兑差异（公式）" class-name="formula-item">
                <span class="formula-value" title="应有本位币 - 报表日现金账面余额">
                  {{ displayPrefs.fmtAmount(rmbSummary.exchangeDifference) }}
                </span>
              </el-descriptions-item>
            </template>
          </el-descriptions>
        </el-card>

        <!-- 审计说明 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>审计说明</span>
              <el-button
                size="small"
                type="primary"
                plain
                :loading="isGenerating('e1-audit-note')"
                :disabled="isReadonly"
                @click="generateAuditNote"
              >🤖 AI辅助</el-button>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditNote"
            :disabled="isReadonly"
            :autosize="{ minRows: 5 }"
            placeholder="填写审计说明：可概述（1）现金监盘程序的实施情况与结果；（2）长（短）款原因、白条抵库/坐支等异常事项；（3）非资产负债表日盘点倒轧至基准日的调整过程；（4）外币汇率折算测试结果。"
            @change="(val: string) => saveAuditNote(val)"
          />
        </el-card>

        <!-- 审计结论 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>审计结论</span>
              <el-button
                size="small"
                type="primary"
                plain
                :loading="isGenerating('e1-audit-conclusion')"
                :disabled="isReadonly"
                @click="generateAuditConclusion"
              >🤖 AI辅助</el-button>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditConclusion"
            :disabled="isReadonly"
            :autosize="{ minRows: 3 }"
            placeholder="填写审计结论：A、库存现金账实相符，未见异常。B、除上述长（短）款差异应作调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或监盘范围受到限制无法获取充分、适当证据），不可确认。"
            @change="(val: string) => saveAuditConclusion(val)"
          />
        </el-card>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-cash-count {
  padding: 12px 0;
}
.e1-tab-cash-count :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-cash-count :deep(.el-table .cell) {
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
.orange-text {
  color: #e6a23c;
  font-weight: 600;
}
.summary-card {
  margin-top: 16px;
}
.elements-card {
  margin-bottom: 12px;
}
.elements-card :deep(.el-descriptions__label) {
  width: 140px;
}
.signature-field {
  display: grid;
  grid-template-columns: minmax(140px, 1fr) 150px;
  gap: 8px;
  width: 100%;
}
.roll-forward-grid :deep(.el-descriptions__label) {
  min-width: 210px;
}
.formula-value {
  color: #606266;
  border-bottom: 1px dashed #909399;
  cursor: help;
}
:deep(.formula-item) {
  background: #f5f7fa !important;
}
.required-input :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}
.audit-note-card {
  margin-top: 16px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
</style>
