<script setup lang="ts">
import { computed, inject, onMounted, ref, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useE1InterestCalc, type DepositType } from '../composables/useE1InterestCalc'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
import { useE1ImportExport } from '../composables/useE1ImportExport'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  wpId: string; projectId: string; allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>; debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean; sheetName?: string
}>()
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const wpIdRef = toRef(props, 'wpId') as unknown as Ref<string>
const options: UseE1BaseOptions & { variant: 'monthly' } = {
  wpId: wpIdRef, projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate, debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>, variant: 'monthly',
}
const interest = useE1InterestCalc(options)
const { generateText, isGenerating } = useE1AiGenerate(wpIdRef)
const activeSection = ref('matrix')
const depositTypes: DepositType[] = ['活期存款', '七天通知存款', '大额存单']
const sheetCode = computed(() => 'E1-15')
const ie = useE1ImportExport({ wpId: wpIdRef, sheet: sheetCode as unknown as Ref<string> })
const isImporting = ie.isImporting

async function exportFile(kind: 'template' | 'data'): Promise<void> {
  await (kind === 'template' ? ie.exportTemplate() : ie.exportData())
}
async function handleImport(file: File): Promise<boolean> {
  const result = await ie.importData(file)
  result.success ? ElMessage.success(result.message) : ElMessage.warning(result.message)
  if (result.success) await reloadWorkpaperData?.()
  return false
}

const NOTE_KEY = 'E1-interest-audit-note'
const CONCLUSION_KEY = 'E1-interest-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
onMounted(() => {
  auditNote.value = props.allResponses.get(NOTE_KEY)?.remark || ''
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
})
function saveText(key: string, target: Ref<string>, value: string): void {
  if (props.isReadonly) return
  target.value = value; const item = { item_id: key, conclusion: null, remark: value }
  props.allResponses.set(key, item); void props.saveImmediate([item])
}
function fmtRate(value: number | ''): string { return value === '' ? '-' : `${(value * 100).toFixed(3)}%` }
async function aiReason(title: string, current: string, context: Record<string, unknown>, apply: (value: string) => void): Promise<void> {
  const text = await generateText({
    section: 'interest-analysis-reason',
    prompt: '结合账户类型、年利率、12个月余额、账面利息和测算差异，生成可核查的原因分析。不要虚构市场数据。',
    context,
    existingContent: current,
    confirmTitle: `AI辅助：${title}`,
  })
  if (text) apply(text)
}
async function aiLongText(kind: 'note' | 'conclusion'): Promise<void> {
  const isNote = kind === 'note'
  const section = isNote ? 'interest-note' : 'interest-conclusion'
  const text = await generateText({
    section,
    prompt: isNote
      ? '根据账户配置、月度测算、利息结构、市场利率和异常事项生成审计说明，说明公式、数据来源、差异及追加程序。'
      : '根据利息测算和异常分析形成审计结论，明确差异是否可接受及是否需要调整或进一步程序。',
    context: { summary: interest.monthlySummary.value, structure: interest.interestStructureRows.value, market: interest.marketRateRows.value, anomalies: interest.anomalyRows.value },
    existingContent: isNote ? auditNote.value : auditConclusion.value,
    confirmTitle: `AI生成${isNote ? '审计说明' : '审计结论'}`,
  })
  if (text) saveText(isNote ? NOTE_KEY : CONCLUSION_KEY, isNote ? auditNote : auditConclusion, text)
}
</script>

<template>
  <div class="e1-interest">
    <div class="method-context"><strong>源模板方法论：</strong>先配置活期、七天通知和大额存单账户，再逐月录入余额与账面利息。测算利息固定按“月均余额 × 年利率 ÷ 12”计算；差异较大时应进一步按每日余额复核并交叉索引 E1-30。</div>
    <el-alert type="info" :closable="false" title="审计目标：分析利息收入合理性及其与货币资金余额的匹配性，识别重大错报风险。" class="objective-alert" />
    <div class="tab-toolbar">
      <div><el-button type="primary" size="small" :disabled="isReadonly" @click="interest.addAccount">+ 新增账户</el-button></div>
      <div class="toolbar-right">
        <el-dropdown trigger="click"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="exportFile('template')">导出模板</el-dropdown-item><el-dropdown-item @click="exportFile('data')">导出数据</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx,.xls" :before-upload="handleImport" :disabled="isImporting"><span>导入数据</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown>
        <GtIndexChip value="wp:E1-1" :context-project-id="projectId" /><el-tag size="small">{{ interest.accounts.value.length }} 个账户</el-tag>
      </div>
    </div>
    <el-card shadow="never" class="config-card"><template #header><strong>一、账户配置</strong></template>
      <el-table :data="interest.accounts.value" border stripe size="small">
        <el-table-column label="存款类型" width="150"><template #default="{ row }"><el-select :model-value="row.depositType" :disabled="isReadonly" @change="(v: DepositType) => interest.updateAccount(row.id, 'depositType', v)"><el-option v-for="item in depositTypes" :key="item" :label="item" :value="item" /></el-select></template></el-table-column>
        <el-table-column label="银行" min-width="150"><template #default="{ row }"><el-input :model-value="row.bank" :disabled="isReadonly" @change="(v: string) => interest.updateAccount(row.id, 'bank', v)" /></template></el-table-column>
        <el-table-column label="账号/账户名称" min-width="180"><template #default="{ row }"><el-input :model-value="row.accountNo" :disabled="isReadonly" @change="(v: string) => interest.updateAccount(row.id, 'accountNo', v)" /></template></el-table-column>
        <el-table-column label="年利率" width="150"><template #default="{ row }"><el-input-number :model-value="row.annualRate" :disabled="isReadonly" :controls="false" :precision="6" :step="0.0001" @change="(v: number) => interest.updateAccount(row.id, 'annualRate', v ?? 0)" /></template></el-table-column>
        <el-table-column label="操作" width="75"><template #default="{ row }"><el-button type="danger" text :disabled="isReadonly || interest.accounts.value.length <= 1" @click="interest.removeRow(row.id)">删除</el-button></template></el-table-column>
      </el-table>
    </el-card>

    <el-tabs v-model="activeSection" type="border-card" class="analysis-tabs">
      <el-tab-pane label="月度矩阵" name="matrix">
        <el-table :data="interest.monthlyMatrix.value" border stripe size="small" max-height="620">
          <el-table-column label="月份" width="70" fixed="left"><template #default="{ row }">{{ row.month }}月</template></el-table-column>
          <el-table-column v-for="account in interest.accounts.value" :key="account.id" :label="`${account.depositType}｜${account.bank || '未填银行'}｜${account.accountNo}`">
            <el-table-column label="月均余额" width="145"><template #default="{ row }"><el-input-number :model-value="row.accounts[account.id]?.balance || 0" :disabled="isReadonly" :controls="false" size="small" @change="(v: number) => interest.updateMonthlyCell(account.id, row.month, 'balance', v ?? 0)" /></template></el-table-column>
            <el-table-column label="账面利息" width="135"><template #default="{ row }"><el-input-number :model-value="row.accounts[account.id]?.bookInterest || 0" :disabled="isReadonly" :controls="false" size="small" @change="(v: number) => interest.updateMonthlyCell(account.id, row.month, 'bookInterest', v ?? 0)" /></template></el-table-column>
            <el-table-column label="测算利息" width="135" class-name="auto-calc-col"><template #default="{ row }">{{ displayPrefs.fmtAmount(row.accounts[account.id]?.calculatedInterest || 0) }}</template></el-table-column>
          </el-table-column>
          <el-table-column label="测算合计" width="140" fixed="right" class-name="auto-calc-col"><template #default="{ row }">{{ displayPrefs.fmtAmount(row.totalCalculated) }}</template></el-table-column>
          <el-table-column label="账面合计" width="140" fixed="right" class-name="auto-calc-col"><template #default="{ row }">{{ displayPrefs.fmtAmount(row.totalBook) }}</template></el-table-column>
          <el-table-column label="差异" width="135" fixed="right" class-name="auto-calc-col"><template #default="{ row }"><span :class="{ danger: Math.abs(row.diff) > 0.005 }">{{ displayPrefs.fmtAmount(row.diff) }}</span></template></el-table-column>
        </el-table>
        <el-descriptions :column="3" border class="summary"><el-descriptions-item label="测算利息合计">{{ displayPrefs.fmtAmount(interest.totalCalculated.value) }}</el-descriptions-item><el-descriptions-item label="账面利息合计">{{ displayPrefs.fmtAmount(interest.totalBookInterest.value) }}</el-descriptions-item><el-descriptions-item label="差异"><span :class="{ danger: Math.abs(interest.monthlySummary.value.diff) > 0.005 }">{{ displayPrefs.fmtAmount(interest.monthlySummary.value.diff) }}</span></el-descriptions-item></el-descriptions>
      </el-tab-pane>

      <el-tab-pane label="利息结构" name="structure">
        <el-table :data="interest.interestStructureRows.value" border stripe size="small">
          <el-table-column prop="name" label="项目" min-width="150" />
          <el-table-column label="本期金额" min-width="135" class-name="auto-calc-col"><template #default="{ row }">{{ displayPrefs.fmtAmount(row.current) }}</template></el-table-column>
          <el-table-column label="上期金额" min-width="140"><template #default="{ row }"><el-input-number :model-value="row.prior" :disabled="isReadonly" :controls="false" size="small" @change="(v: number) => interest.updateStructure(row.key, 'prior', v ?? 0)" /></template></el-table-column>
          <el-table-column label="变动金额" min-width="135" class-name="auto-calc-col"><template #default="{ row }">{{ displayPrefs.fmtAmount(row.change) }}</template></el-table-column>
          <el-table-column label="变动率" width="100" class-name="auto-calc-col"><template #default="{ row }">{{ fmtRate(row.changeRate) }}</template></el-table-column>
          <el-table-column label="分析说明" min-width="270"><template #default="{ row }"><div class="ai-cell"><el-input :model-value="row.note" :disabled="isReadonly" @change="(v: string) => interest.updateStructure(row.key, 'note', v)" /><el-button text type="primary" :disabled="isReadonly" :loading="isGenerating('interest-analysis-reason')" @click="aiReason(row.name, row.note, row, v => interest.updateStructure(row.key, 'note', v))">🤖</el-button></div></template></el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="市场利率" name="market">
        <el-table :data="interest.marketRateRows.value" border stripe size="small">
          <el-table-column prop="name" label="存款类型" min-width="150" />
          <el-table-column label="账户平均利率" width="135" class-name="auto-calc-col"><template #default="{ row }">{{ fmtRate(row.actualRate) }}</template></el-table-column>
          <el-table-column label="市场利率" width="150"><template #default="{ row }"><el-input-number :model-value="row.marketRate" :disabled="isReadonly" :controls="false" :precision="6" :step="0.0001" size="small" @change="(v: number) => interest.updateMarketRate(row.key, 'marketRate', v ?? 0)" /></template></el-table-column>
          <el-table-column label="差异" width="110" class-name="auto-calc-col"><template #default="{ row }">{{ fmtRate(row.diff) }}</template></el-table-column>
          <el-table-column label="差异率" width="110" class-name="auto-calc-col"><template #default="{ row }">{{ fmtRate(row.diffRate) }}</template></el-table-column>
          <el-table-column label="分析说明" min-width="280"><template #default="{ row }"><div class="ai-cell"><el-input :model-value="row.note" :disabled="isReadonly" @change="(v: string) => interest.updateMarketRate(row.key, 'note', v)" /><el-button text type="primary" :disabled="isReadonly" :loading="isGenerating('interest-analysis-reason')" @click="aiReason(row.name, row.note, row, v => interest.updateMarketRate(row.key, 'note', v))">🤖</el-button></div></template></el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="异常分析" name="anomalies">
        <el-table :data="interest.anomalyRows.value" border stripe size="small">
          <el-table-column prop="item" label="异常项目" min-width="150" />
          <el-table-column label="金额" width="145"><template #default="{ row }"><el-input-number :model-value="row.amount" :disabled="isReadonly" :controls="false" size="small" @change="(v: number) => interest.updateAnomaly(row.key, 'amount', v ?? 0)" /></template></el-table-column>
          <el-table-column label="原因分析" min-width="240"><template #default="{ row }"><div class="ai-cell"><el-input :model-value="row.reason" :disabled="isReadonly" @change="(v: string) => interest.updateAnomaly(row.key, 'reason', v)" /><el-button text type="primary" :disabled="isReadonly" :loading="isGenerating('interest-analysis-reason')" @click="aiReason(row.item, row.reason, row, v => interest.updateAnomaly(row.key, 'reason', v))">🤖</el-button></div></template></el-table-column>
          <el-table-column label="风险评估" min-width="180"><template #default="{ row }"><el-input :model-value="row.risk" :disabled="isReadonly" @change="(v: string) => interest.updateAnomaly(row.key, 'risk', v)" /></template></el-table-column>
          <el-table-column label="应对措施" min-width="180"><template #default="{ row }"><el-input :model-value="row.response" :disabled="isReadonly" @change="(v: string) => interest.updateAnomaly(row.key, 'response', v)" /></template></el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-card class="audit-card" shadow="never"><template #header><div class="card-header"><span>审计说明</span><el-button type="primary" plain size="small" :disabled="isReadonly" :loading="isGenerating('interest-note')" @click="aiLongText('note')">🤖 AI辅助</el-button></div></template><el-input type="textarea" :autosize="{ minRows: 5 }" :model-value="auditNote" :disabled="isReadonly" placeholder="说明账户范围、利率来源、月度测算、账面差异及异常应对。" @change="(v: string) => saveText(NOTE_KEY, auditNote, v)" /></el-card>
    <el-card class="audit-card" shadow="never"><template #header><div class="card-header"><span>审计结论</span><el-button type="primary" plain size="small" :disabled="isReadonly" :loading="isGenerating('interest-conclusion')" @click="aiLongText('conclusion')">🤖 AI辅助</el-button></div></template><el-input type="textarea" :autosize="{ minRows: 3 }" :model-value="auditConclusion" :disabled="isReadonly" placeholder="说明利息收入是否合理完整、差异是否需调整或追加程序。" @change="(v: string) => saveText(CONCLUSION_KEY, auditConclusion, v)" /></el-card>
    <details class="guidance"><summary>📋 编制提示</summary><p>年利率按小数录入，例如 1.50% 录入 0.015。旧版12行“月均余额+月利率”JSON会自动迁入“旧版月度数据迁入”账户，并按旧月利率折算平均年利率。</p></details>
  </div>
</template>

<style scoped>
.e1-interest{padding:12px 0}.e1-interest :deep(.el-table){font-size:var(--wp-font-size,13px)}
.method-context{margin-bottom:12px;padding:10px 12px;border-left:4px solid #e6a23c;background:#fdf6ec;color:#7a4b00;line-height:1.65}.objective-alert{margin-bottom:12px}
.tab-toolbar,.toolbar-right,.card-header,.ai-cell{display:flex;align-items:center}.tab-toolbar,.card-header{justify-content:space-between}.tab-toolbar{margin-bottom:8px}.toolbar-right,.ai-cell{gap:8px}.config-card{margin-bottom:12px}.analysis-tabs,.audit-card{margin-top:14px}.summary{margin-top:12px}.ai-cell .el-input{flex:1}
:deep(.auto-calc-col){background:#f5f7fa!important}.danger{color:#f56c6c;font-weight:600}.guidance{margin-top:14px;padding:8px 12px;border-left:3px solid #409eff;background:#ecf5ff}.guidance summary{cursor:pointer;color:#409eff;font-weight:600}
</style>
