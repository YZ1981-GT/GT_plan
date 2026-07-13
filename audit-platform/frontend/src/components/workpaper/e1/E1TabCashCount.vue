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
  type RmbCountRow,
  type FxCountRow,
} from '../composables/useE1CashCount'
import { useE1ImportExport } from '../composables/useE1ImportExport'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

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

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

// ─── Variant Detection ───────────────────────────────────────────────────────

const variant = computed<CashCountVariant>(() => {
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

// ─── FX 折算合计 / 差异 ───────────────────────────────────────────────────────

/** FX 模式实盘折算合计 = SUM(rmbAmount) */
const fxActualTotal = computed(() =>
  variant.value === 'fx'
    ? rows.value.reduce((sum, r) => sum + Number((r as FxCountRow).rmbAmount || 0), 0)
    : 0,
)
/** FX 模式盘点差异 = 实盘折算合计 - 账面余额 */
const fxCountDiff = computed(() => fxActualTotal.value - (fxSummary.value.bookBalance || 0))
function fxHasDiff(): boolean {
  return Math.abs(fxCountDiff.value) > 0.005
}

// ─── 持久化键（按 variant 区分，避免 E1-7/E1-8 同工作簿共享时冲突） ───────────

const ELEMENTS_KEY = computed(() => `E1-cashcount-elements-${variant.value}`)
const FX_SUMMARY_KEY = computed(() => `E1-cashcount-fx-summary-${variant.value}`)
const NOTE_KEY = computed(() => `E1-cashcount-audit-note-${variant.value}`)
const CONCLUSION_KEY = computed(() => `E1-cashcount-audit-conclusion-${variant.value}`)

// ─── 监盘要素（盘点日期/时间/地点/参加人员/会计主管/出纳/监盘人） ─────────────

interface CountElements {
  countDate: string
  countTime: string
  countPlace: string
  participants: string
  accountant: string   // 会计主管人员
  cashier: string       // 出纳
  supervisor: string    // 监盘人（审计人员）
}
const countElements = ref<CountElements>({
  countDate: '',
  countTime: '',
  countPlace: '',
  participants: '',
  accountant: '',
  cashier: '',
  supervisor: '',
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

// ─── FX 汇总（账面余额 / 差异原因） ───────────────────────────────────────────

interface FxSummary { bookBalance: number; diffReason: string }
const fxSummary = ref<FxSummary>({ bookBalance: 0, diffReason: '' })

function saveFxSummary(): void {
  if (props.isReadonly) return
  const json = JSON.stringify(fxSummary.value)
  const item = { item_id: FX_SUMMARY_KEY.value, conclusion: null, remark: json }
  props.allResponses.set(FX_SUMMARY_KEY.value, item)
  void props.saveImmediate([item])
}

function updateFxBookBalance(val: number | undefined): void {
  if (props.isReadonly) return
  fxSummary.value = { ...fxSummary.value, bookBalance: val ?? 0 }
  saveFxSummary()
}

function updateFxDiffReason(val: string): void {
  if (props.isReadonly) return
  fxSummary.value = { ...fxSummary.value, diffReason: val ?? '' }
  saveFxSummary()
}

// ─── 审计说明 / 审计结论 ──────────────────────────────────────────────────────

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

// ─── Hydration ─────────────────────────────────────────────────────────────

onMounted(() => {
  const elemResp = props.allResponses.get(ELEMENTS_KEY.value)
  if (elemResp?.remark) {
    try {
      const parsed = JSON.parse(elemResp.remark)
      countElements.value = { ...countElements.value, ...parsed }
    } catch { /* keep defaults */ }
  }
  const fxResp = props.allResponses.get(FX_SUMMARY_KEY.value)
  if (fxResp?.remark) {
    try {
      const parsed = JSON.parse(fxResp.remark)
      fxSummary.value = {
        bookBalance: Number(parsed.bookBalance) || 0,
        diffReason: String(parsed.diffReason || ''),
      }
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
        <el-descriptions-item label="会计主管人员">
          <el-input
            :model-value="countElements.accountant"
            :disabled="isReadonly"
            placeholder="会计主管签字确认"
            size="small"
            @change="(val: string) => updateElement('accountant', val)"
          />
        </el-descriptions-item>
        <el-descriptions-item label="出纳">
          <el-input
            :model-value="countElements.cashier"
            :disabled="isReadonly"
            placeholder="现金出纳签字确认"
            size="small"
            @change="(val: string) => updateElement('cashier', val)"
          />
        </el-descriptions-item>
        <el-descriptions-item label="监盘人（审计人员）">
          <el-input
            :model-value="countElements.supervisor"
            :disabled="isReadonly"
            placeholder="现场监盘审计人员"
            size="small"
            @change="(val: string) => updateElement('supervisor', val)"
          />
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

          <!-- Summary Card -->
          <el-card class="summary-card" shadow="never">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="实盘合计">
                <span class="auto-calc-value">{{ displayPrefs.fmtAmount(rmbTotal) }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="账面余额">
                <el-input-number
                  :model-value="rmbSummary.bookBalance"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateSummary('bookBalance', val ?? 0)"
                />
              </el-descriptions-item>
              <el-descriptions-item label="盘点差异">
                <span :class="['auto-calc-value', { 'orange-text': hasDiff() }]">
                  {{ displayPrefs.fmtAmount(rmbSummary.countDiff) }}
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="差异原因">
                <el-input
                  :model-value="rmbSummary.diffReason"
                  :disabled="isReadonly"
                  placeholder="差异≠0时必填"
                  size="small"
                  @change="(val: string) => updateSummary('diffReason', val)"
                />
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
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
                <el-input-number
                  :model-value="asFx(row).fcAmount"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="(val: number) => updateCell(row.id, 'fcAmount', val ?? 0)"
                />
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

          <!-- FX 盘盈盘亏汇总 -->
          <el-card class="summary-card" shadow="never">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="实盘折算合计（本位币）">
                <span class="auto-calc-value">{{ displayPrefs.fmtAmount(fxActualTotal) }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="账面余额（本位币）">
                <el-input-number
                  :model-value="fxSummary.bookBalance"
                  :disabled="isReadonly"
                  :controls="false"
                  size="small"
                  @change="updateFxBookBalance"
                />
              </el-descriptions-item>
              <el-descriptions-item label="盘盈盘亏差异">
                <span :class="['auto-calc-value', { 'orange-text': fxHasDiff() }]">
                  {{ displayPrefs.fmtAmount(fxCountDiff) }}
                </span>
              </el-descriptions-item>
              <el-descriptions-item label="差异原因">
                <el-input
                  :model-value="fxSummary.diffReason"
                  :disabled="isReadonly"
                  placeholder="差异≠0时必填（含汇兑损益、长短款等）"
                  size="small"
                  @change="updateFxDiffReason"
                />
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </template>

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
            placeholder="填写审计说明：可概述（1）现金监盘程序的实施情况与结果；（2）长（短）款原因、白条抵库/坐支等异常事项；（3）非资产负债表日盘点倒轧至基准日的调整过程；（4）外币汇率折算测试结果。"
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
