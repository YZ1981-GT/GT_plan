<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
import { ref, inject, toRef, computed, onMounted, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Setting } from '@element-plus/icons-vue'
import {
  useE1BankDetail,
  type BankDetailRow,
  type BankDetailVariant,
  type BankDetailSection,
  type BankDetailGroup,
} from '../composables/useE1BankDetail'
import { useE1ImportExport } from '../composables/useE1ImportExport'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { amountFormatter, amountParser } from '../composables/wpAmountInput'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
  variant?: BankDetailVariant
}>()

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const variant = computed<BankDetailVariant>(() =>
  props.variant ?? (props.sheetName?.includes('人民币及外币') ? 'multi' : 'rmb'),
)

const {
  rows, groupedRows, groupTotals, isLoading, addRow, removeRow, updateCell,
  hasConfirmDiff, GROUP_NAMES, SECTION_NAMES, SECTIONS, GROUPS,
} = useE1BankDetail({
  wpId: wpIdRef,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  variant,
})

const totalRowCount = computed(() => rows.value.length)
const sheetCode = computed(() => 'E1-3')
const { exportTemplate, exportData, importData, isImporting } = useE1ImportExport({ wpId: wpIdRef, sheet: sheetCode })
const { generateText, isGenerating } = useE1AiGenerate(wpIdRef)

async function handleImport(file: File): Promise<boolean> {
  const result = await importData(file)
  if (result.success) {
    ElMessage.success(result.message || '导入成功')
    await reloadWorkpaperData?.()
  } else ElMessage.warning(result.message || '导入失败')
  return false
}

const E1_BANK_COL_STORAGE_KEY = 'e1-bank-detail-column-prefs'
const COLUMN_GROUPS = [
  { label: '账户', keys: ['bankName', 'accountNo', 'accountType'] },
  { label: '外币', keys: ['fxCurrency', 'fxRate'] },
  { label: '余额', keys: ['opening', 'ending', 'audited'] },
  { label: '复核', keys: ['accountStatementDiff', 'confirmDiff', 'restrictedAmount'] },
  { label: '索引及说明', keys: ['confirmIndexNo', 'note'] },
]
const COL_LABELS: Record<string, string> = {
  bankName: '开户银行', accountNo: '银行账号', accountType: '账户性质/用途',
  fxCurrency: '原币币种', fxRate: '期末汇率', opening: '期初余额', ending: '期末余额',
  audited: '期末审定数', accountStatementDiff: '账面对账单差异', confirmDiff: '函证差异',
  restrictedAmount: '受限金额', confirmIndexNo: '询证函索引号', note: '备注',
}
const DEFAULT_HIDDEN = ['accountType', 'opening', 'confirmIndexNo', 'note']
const hiddenCols = ref<Set<string>>(new Set())
try {
  hiddenCols.value = new Set(JSON.parse(localStorage.getItem(E1_BANK_COL_STORAGE_KEY) || JSON.stringify(DEFAULT_HIDDEN)))
} catch { hiddenCols.value = new Set(DEFAULT_HIDDEN) }
function isColVisible(key: string): boolean { return !hiddenCols.value.has(key) }
function toggleCol(key: string): void {
  const next = new Set(hiddenCols.value)
  next.has(key) ? next.delete(key) : next.add(key)
  hiddenCols.value = next
  localStorage.setItem(E1_BANK_COL_STORAGE_KEY, JSON.stringify([...next]))
}
function resetColDefaults(): void {
  hiddenCols.value = new Set(DEFAULT_HIDDEN)
  localStorage.setItem(E1_BANK_COL_STORAGE_KEY, JSON.stringify(DEFAULT_HIDDEN))
}

function getRowClass({ row }: { row: BankDetailRow }): string {
  return hasConfirmDiff(row) || Math.abs(row.accountStatementDiff) > 0.005 ? 'e1-bank-diff-row' : ''
}
function sectionTotal(section: BankDetailSection, field: 'opening' | 'ending' | 'audited'): number {
  return GROUPS.reduce((sum: number, group: BankDetailGroup) => sum + groupTotals.value[section][group][field], 0)
}

const editingRowId = ref('')
const editVisible = ref(false)
const editingRow = computed(() => rows.value.find(row => row.id === editingRowId.value) ?? null)
function openEdit(row: BankDetailRow): void { editingRowId.value = row.id; editVisible.value = true }

const NOTE_KEY = 'E1-bank-audit-note'
const CONCLUSION_KEY = 'E1-bank-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function hydrateNarratives(): void {
  auditNote.value = props.allResponses.get(NOTE_KEY)?.remark || ''
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
}
onMounted(hydrateNarratives)
watch(() => props.allResponses, hydrateNarratives)
function saveNarrative(key: string, target: Ref<string>, value: string): void {
  if (props.isReadonly) return
  target.value = value
  const item = { item_id: key, conclusion: null, remark: value }
  props.allResponses.set(key, item)
  void props.saveImmediate([item])
}
function buildAiContext(): Record<string, unknown> {
  return {
    版本: variant.value, 明细: rows.value, 分组合计: groupTotals.value,
    对账单差异账户: rows.value.filter(row => Math.abs(row.accountStatementDiff) > 0.005),
    函证差异账户: rows.value.filter(hasConfirmDiff),
    受限账户: rows.value.filter(row => row.restrictedAmount !== 0),
  }
}
async function generateNarrative(kind: 'note' | 'conclusion' | 'anomaly'): Promise<void> {
  if (props.isReadonly) return
  const isConclusion = kind === 'conclusion'
  const target = isConclusion ? auditConclusion : auditNote
  const text = await generateText({
    section: `e1-bank-${kind}`,
    prompt: kind === 'anomaly'
      ? '分析对账单差异、函证差异、受限资金、异常利率和外币折算风险，生成可追溯的异常分析及后续审计程序。'
      : isConclusion
        ? '根据分区分组合计、对账及函证差异、受限资金和审计说明形成审慎审计结论；存在证据缺口时不得直接表述未见异常。'
        : '根据账户明细、对账单和余额调节表索引、函证差异、利率、外币折算及受限资金生成专业审计说明。',
    context: { ...buildAiContext(), 审计说明: auditNote.value },
    existingContent: target.value,
    confirmTitle: kind === 'anomaly' ? '确认填入异常分析' : `确认填入审计${isConclusion ? '结论' : '说明'}`,
  })
  if (text) saveNarrative(isConclusion ? CONCLUSION_KEY : NOTE_KEY, target, text)
}
</script>

<template>
  <div class="e1-tab-bank-detail">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>按权威模板恢复“存款本金/应计利息”一级区段，每区段按银行机构、财务公司、其他货币资金归集。</p>
        <p>银行账户应取得对账单并编制余额调节表；对账单索引、余额调节表索引和询证函索引应完整可追溯。</p>
        <p>人民币及外币版须完整填列原币变动、期末汇率和人民币折算链；受限资金、异常利率及差异须说明。</p>
      </div>
    </details>
    <el-alert type="info" :closable="false" title="审计目标：确定银行存款和其他货币资金在资产负债表日确实存在、完整记录、计价准确并恰当披露。" class="objective-alert" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag type="primary">{{ variant === 'multi' ? '人民币及外币' : '仅人民币' }}</el-tag>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown><el-dropdown-menu>
            <el-dropdown-item @click="exportTemplate()">导出模板</el-dropdown-item>
            <el-dropdown-item @click="exportData()">导出数据</el-dropdown-item>
            <el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx,.xls" :before-upload="handleImport" :disabled="isImporting"><span>导入数据</span></el-upload></el-dropdown-item>
          </el-dropdown-menu></template>
        </el-dropdown>
        <el-popover trigger="click" :width="260" placement="bottom-end">
          <template #reference><el-button size="small" circle><el-icon><Setting /></el-icon></el-button></template>
          <div class="col-prefs-popover">
            <div class="col-prefs-header"><span>列显示设置</span><el-button size="small" text type="primary" @click="resetColDefaults">重置默认</el-button></div>
            <div v-for="columnGroup in COLUMN_GROUPS" :key="columnGroup.label" class="col-prefs-group">
              <div class="col-prefs-group-label">{{ columnGroup.label }}</div>
              <div v-for="key in columnGroup.keys" :key="key" class="col-prefs-item">
                <el-checkbox :model-value="isColVisible(key)" size="small" @change="toggleCol(key)">{{ COL_LABELS[key] }}</el-checkbox>
              </div>
            </div>
          </div>
        </el-popover>
        <GtIndexChip value="wp:E1-1" :context-project-id="projectId" />
        <GtIndexChip value="wp:E0" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ totalRowCount }} 行</el-tag>
      </div>
    </div>

    <el-skeleton :loading="isLoading" :rows="10" animated>
      <template #default>
        <section v-for="section in SECTIONS" :key="section" class="primary-section">
          <div class="section-header">
            <strong>{{ SECTION_NAMES[section] }}</strong>
            <span>期初 {{ displayPrefs.fmtAmount(sectionTotal(section, 'opening')) }} · 期末 {{ displayPrefs.fmtAmount(sectionTotal(section, 'ending')) }} · 审定 {{ displayPrefs.fmtAmount(sectionTotal(section, 'audited')) }}</span>
          </div>
          <div v-for="group in GROUPS" :key="`${section}-${group}`" class="group-section">
            <div class="group-header">
              <span>{{ GROUP_NAMES[group] }}</span>
              <el-button v-if="!isReadonly" type="primary" size="small" @click="addRow(section, group)">+ 新增行</el-button>
            </div>
            <el-table :data="groupedRows[section][group]" border size="small" :row-class-name="getRowClass" style="width:100%">
              <el-table-column v-if="isColVisible('bankName')" prop="bankName" label="开户银行" min-width="140" />
              <el-table-column v-if="isColVisible('accountNo')" prop="accountNo" label="银行账号" min-width="150" />
              <el-table-column v-if="isColVisible('accountType')" prop="accountType" label="账户性质/用途" min-width="130" />
              <el-table-column v-if="variant === 'multi' && isColVisible('fxCurrency')" prop="fxCurrency" label="原币" width="80" />
              <el-table-column v-if="variant === 'multi' && isColVisible('fxRate')" label="汇率" width="90" align="right"><template #default="{ row }">{{ row.fxRate }}</template></el-table-column>
              <el-table-column v-if="isColVisible('opening')" label="期初余额" min-width="120" align="right"><template #default="{ row }">{{ displayPrefs.fmtAmount(row.opening) }}</template></el-table-column>
              <el-table-column v-if="isColVisible('ending')" label="期末余额" min-width="120" align="right" class-name="auto-calc-col"><template #default="{ row }">{{ displayPrefs.fmtAmount(row.ending) }}</template></el-table-column>
              <el-table-column v-if="isColVisible('audited')" label="期末审定" min-width="120" align="right" class-name="auto-calc-col"><template #default="{ row }">{{ displayPrefs.fmtAmount(row.audited) }}</template></el-table-column>
              <el-table-column v-if="isColVisible('accountStatementDiff')" label="对账单差异" min-width="120" align="right" class-name="auto-calc-col"><template #default="{ row }"><span :class="{ danger: Math.abs(row.accountStatementDiff) > 0.005 }">{{ displayPrefs.fmtAmount(row.accountStatementDiff) }}</span></template></el-table-column>
              <el-table-column v-if="isColVisible('confirmDiff')" label="函证差异" min-width="110" align="right" class-name="auto-calc-col"><template #default="{ row }"><span :class="{ danger: hasConfirmDiff(row) }">{{ displayPrefs.fmtAmount(row.confirmDiff) }}</span></template></el-table-column>
              <el-table-column v-if="isColVisible('restrictedAmount')" label="受限金额" min-width="115" align="right"><template #default="{ row }">{{ displayPrefs.fmtAmount(row.restrictedAmount) }}</template></el-table-column>
              <el-table-column v-if="isColVisible('confirmIndexNo')" label="询证函索引" min-width="120"><template #default="{ row }"><GtIndexChip v-if="row.confirmIndexNo" value="wp:E0" :context-project-id="projectId" :context="`询证函索引：${row.confirmIndexNo}`" /><span v-else>-</span></template></el-table-column>
              <el-table-column v-if="isColVisible('note')" prop="note" label="备注" min-width="140" />
              <el-table-column label="完整信息" width="88" fixed="right" align="center"><template #default="{ row }"><el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button><el-button v-if="!isReadonly" text type="danger" size="small" @click="removeRow(row.id)">删除</el-button></template></el-table-column>
            </el-table>
            <div class="group-subtotal">小计：期初 {{ displayPrefs.fmtAmount(groupTotals[section][group].opening) }}　期末 {{ displayPrefs.fmtAmount(groupTotals[section][group].ending) }}　审定 {{ displayPrefs.fmtAmount(groupTotals[section][group].audited) }}</div>
          </div>
        </section>

        <el-card shadow="never" class="audit-note-card">
          <template #header><div class="card-header"><span>审计说明</span><div><el-button size="small" type="warning" plain :disabled="isReadonly" :loading="isGenerating('e1-bank-anomaly')" @click="generateNarrative('anomaly')">🤖 异常分析</el-button><el-button size="small" type="primary" plain :disabled="isReadonly" :loading="isGenerating('e1-bank-note')" @click="generateNarrative('note')">🤖 AI辅助</el-button></div></div></template>
          <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly" :autosize="{ minRows: 5 }" placeholder="说明网银对账单获取过程、未函证理由、差异核查、受限资金及外币折算情况。" @change="(value: string) => saveNarrative(NOTE_KEY, auditNote, value)" />
        </el-card>
        <el-card shadow="never" class="audit-note-card">
          <template #header><div class="card-header"><span>审计结论</span><el-button size="small" type="primary" plain :disabled="isReadonly" :loading="isGenerating('e1-bank-conclusion')" @click="generateNarrative('conclusion')">🤖 AI辅助</el-button></div></template>
          <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 3 }" placeholder="根据取得证据及未解决差异形成审慎结论。" @change="(value: string) => saveNarrative(CONCLUSION_KEY, auditConclusion, value)" />
        </el-card>
      </template>
    </el-skeleton>

    <el-dialog v-model="editVisible" :title="isReadonly ? '查看账户完整信息' : '编辑账户完整信息'" width="920px" destroy-on-close>
      <template v-if="editingRow">
        <el-tabs>
          <el-tab-pane label="账户与索引">
            <el-form label-width="150px" class="dialog-grid">
              <el-form-item label="开户银行"><el-input :model-value="editingRow.bankName" :disabled="isReadonly" @change="(v: string) => updateCell(editingRow!.id, 'bankName', v)" /></el-form-item>
              <el-form-item label="总账银行名称"><el-input :model-value="editingRow.totalLedgerBank" :disabled="isReadonly" @change="(v: string) => updateCell(editingRow!.id, 'totalLedgerBank', v)" /></el-form-item>
              <el-form-item label="银行账号"><el-input :model-value="editingRow.accountNo" :disabled="isReadonly" @change="(v: string) => updateCell(editingRow!.id, 'accountNo', v)" /></el-form-item>
              <el-form-item label="账户性质/主要用途"><el-input :model-value="editingRow.accountType" :disabled="isReadonly" @change="(v: string) => updateCell(editingRow!.id, 'accountType', v)" /></el-form-item>
              <el-form-item label="利率"><el-input-number :model-value="editingRow.interestRate" :disabled="isReadonly" :controls="false" :precision="6" @change="(v: number | undefined) => updateCell(editingRow!.id, 'interestRate', v ?? 0)" /></el-form-item>
              <el-form-item label="银行对账单索引号"><el-input :model-value="editingRow.statementIndexNo" :disabled="isReadonly" @change="(v: string) => updateCell(editingRow!.id, 'statementIndexNo', v)" /></el-form-item>
              <el-form-item label="余额调节表索引号"><el-input :model-value="editingRow.reconciliationIndexNo" :disabled="isReadonly" @change="(v: string) => updateCell(editingRow!.id, 'reconciliationIndexNo', v)" /></el-form-item>
              <el-form-item label="询证函索引号"><el-input :model-value="editingRow.confirmIndexNo" :disabled="isReadonly" @change="(v: string) => updateCell(editingRow!.id, 'confirmIndexNo', v)" /></el-form-item>
            </el-form>
          </el-tab-pane>
          <el-tab-pane label="人民币余额链">
            <el-form label-width="150px" class="dialog-grid">
              <el-form-item label="期初余额"><WpAmountInput :model-value="editingRow.opening" :disabled="isReadonly || variant === 'multi'" @change="(v: number | undefined) => updateCell(editingRow!.id, 'opening', v ?? 0)" /></el-form-item>
              <el-form-item label="本期增加"><WpAmountInput :model-value="editingRow.increase" :disabled="isReadonly || variant === 'multi'" @change="(v: number | undefined) => updateCell(editingRow!.id, 'increase', v ?? 0)" /></el-form-item>
              <el-form-item label="本期减少"><WpAmountInput :model-value="editingRow.decrease" :disabled="isReadonly || variant === 'multi'" @change="(v: number | undefined) => updateCell(editingRow!.id, 'decrease', v ?? 0)" /></el-form-item>
              <el-form-item label="期末余额（计算）"><el-input :model-value="displayPrefs.fmtAmount(editingRow.ending)" disabled /></el-form-item>
              <el-form-item label="账项调整"><WpAmountInput :model-value="editingRow.adjustment" :disabled="isReadonly || variant === 'multi'" @change="(v: number | undefined) => updateCell(editingRow!.id, 'adjustment', v ?? 0)" /></el-form-item>
              <el-form-item label="审定数（计算）"><el-input :model-value="displayPrefs.fmtAmount(editingRow.audited)" disabled /></el-form-item>
              <el-form-item label="银行对账单余额"><WpAmountInput :model-value="editingRow.statementBalance" :disabled="isReadonly" @change="(v: number | undefined) => updateCell(editingRow!.id, 'statementBalance', v ?? 0)" /></el-form-item>
              <el-form-item label="账面对账单差异"><el-input :model-value="displayPrefs.fmtAmount(editingRow.accountStatementDiff)" disabled /></el-form-item>
              <el-form-item label="回函确认金额"><WpAmountInput :model-value="editingRow.confirmAmount" :disabled="isReadonly" @change="(v: number | undefined) => updateCell(editingRow!.id, 'confirmAmount', v ?? 0)" /></el-form-item>
              <el-form-item label="函证差异"><el-input :model-value="displayPrefs.fmtAmount(editingRow.confirmDiff)" disabled /></el-form-item>
              <el-form-item label="受限金额"><WpAmountInput :model-value="editingRow.restrictedAmount" :disabled="isReadonly" @change="(v: number | undefined) => updateCell(editingRow!.id, 'restrictedAmount', v ?? 0)" /></el-form-item>
              <el-form-item label="受限原因"><el-input :model-value="editingRow.restrictedReason" :disabled="isReadonly" @change="(v: string) => updateCell(editingRow!.id, 'restrictedReason', v)" /></el-form-item>
            </el-form>
          </el-tab-pane>
          <el-tab-pane v-if="variant === 'multi'" label="外币链">
            <el-form label-width="150px" class="dialog-grid">
              <el-form-item label="原币币种"><el-input :model-value="editingRow.fxCurrency" :disabled="isReadonly" @change="(v: string) => updateCell(editingRow!.id, 'fxCurrency', v)" /></el-form-item>
              <el-form-item label="期末汇率"><el-input-number :model-value="editingRow.fxRate" :disabled="isReadonly" :controls="false" :precision="6" @change="(v: number | undefined) => updateCell(editingRow!.id, 'fxRate', v ?? 1)" /></el-form-item>
              <el-form-item label="期初原币"><WpAmountInput :model-value="editingRow.openingFc" :disabled="isReadonly" @change="(v: number | undefined) => updateCell(editingRow!.id, 'openingFc', v ?? 0)" /></el-form-item>
              <el-form-item label="增加原币"><WpAmountInput :model-value="editingRow.increaseFc" :disabled="isReadonly" @change="(v: number | undefined) => updateCell(editingRow!.id, 'increaseFc', v ?? 0)" /></el-form-item>
              <el-form-item label="减少原币"><WpAmountInput :model-value="editingRow.decreaseFc" :disabled="isReadonly" @change="(v: number | undefined) => updateCell(editingRow!.id, 'decreaseFc', v ?? 0)" /></el-form-item>
              <el-form-item label="期末原币（计算）"><el-input :model-value="displayPrefs.fmtAmount(editingRow.endingFc)" disabled /></el-form-item>
              <el-form-item label="调整原币"><WpAmountInput :model-value="editingRow.adjustmentFc" :disabled="isReadonly" @change="(v: number | undefined) => updateCell(editingRow!.id, 'adjustmentFc', v ?? 0)" /></el-form-item>
              <el-form-item label="审定原币（计算）"><el-input :model-value="displayPrefs.fmtAmount(editingRow.auditedFc)" disabled /></el-form-item>
            </el-form>
          </el-tab-pane>
          <el-tab-pane label="备注"><el-input type="textarea" :autosize="{ minRows: 5 }" :model-value="editingRow.note" :disabled="isReadonly" placeholder="说明财务公司、境外资金、资金池、差异及其他异常事项。" @change="(v: string) => updateCell(editingRow!.id, 'note', v)" /></el-tab-pane>
        </el-tabs>
      </template>
      <template #footer><el-button type="primary" @click="editVisible = false">完成</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.e1-tab-bank-detail{padding:12px 0}.e1-tab-bank-detail :deep(.el-table),.e1-tab-bank-detail :deep(.el-table .cell){font-size:var(--wp-font-size,13px)}
.guidance-details{margin-bottom:12px;border-left:3px solid #409eff;background:#ecf5ff;border-radius:4px;padding:8px 12px}.guidance-details summary{cursor:pointer;font-weight:500;color:#409eff}.guidance-content{margin-top:8px;font-size:13px;color:#606266;line-height:1.6}.guidance-content p{margin:2px 0}.objective-alert{margin-bottom:12px}
.tab-toolbar,.toolbar-left,.toolbar-right,.section-header,.group-header,.card-header{display:flex;align-items:center}.tab-toolbar,.section-header,.group-header,.card-header{justify-content:space-between}.tab-toolbar{margin-bottom:12px;gap:8px;flex-wrap:wrap}.toolbar-left,.toolbar-right{gap:7px}
.primary-section{margin-bottom:22px;border:1px solid #d9ecff;border-radius:6px;padding:10px}.section-header{padding:8px 12px;background:#ecf5ff;color:#303133;margin-bottom:10px}.section-header span{font-size:12px;color:#606266}.group-section{margin-bottom:14px}.group-header{padding:6px 10px;background:#f5f7fa;font-weight:600}.group-subtotal{padding:7px 10px;background:#fafafa;color:#606266;font-size:13px;text-align:right}
:deep(.auto-calc-col){background:#f5f7fa!important}.danger{color:#f56c6c;font-weight:700}:deep(.e1-bank-diff-row){background:#fef0f0!important}.audit-note-card{margin-top:16px}.card-header{font-weight:600}.card-header>div{display:flex;gap:6px}.dialog-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 16px}.dialog-grid :deep(.el-input-number){width:100%}
.col-prefs-popover{max-height:320px;overflow-y:auto}.col-prefs-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;font-weight:600;font-size:13px}.col-prefs-group{margin-bottom:8px}.col-prefs-group-label{font-size:12px;color:#909399;margin-bottom:4px}.col-prefs-item{margin-left:8px}
</style>
