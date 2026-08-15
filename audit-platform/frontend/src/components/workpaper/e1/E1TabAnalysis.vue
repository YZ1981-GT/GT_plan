<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
import { inject, onMounted, ref, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useE1Analysis, type AnalysisRow, type AnalysisPeriod } from '../composables/useE1Analysis'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { amountFormatter, amountParser } from '../composables/wpAmountInput'

const props = defineProps<{
  wpId: string; projectId: string; allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>; debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean; sheetName?: string
}>()
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
const wpIdRef = toRef(props, 'wpId') as unknown as Ref<string>
const options: UseE1BaseOptions = {
  wpId: wpIdRef, projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate, debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
}
const analysis = useE1Analysis(options)
const { generateText, isGenerating } = useE1AiGenerate(wpIdRef)
const activeSection = ref('composition')
const NOTE_KEY = 'E1-analysis-audit-note'
const CONCLUSION_KEY = 'E1-analysis-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
onMounted(() => {
  auditNote.value = props.allResponses.get(NOTE_KEY)?.remark || ''
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
})
function saveText(key: string, target: Ref<string>, value: string): void {
  if (props.isReadonly) return
  target.value = value
  const item = { item_id: key, conclusion: null, remark: value }
  props.allResponses.set(key, item); void props.saveImmediate([item])
}
function fmtRate(value: number | ''): string { return value === '' ? '-' : `${(value * 100).toFixed(2)}%` }
function rowClass({ row }: { row: AnalysisRow }): string { return analysis.isRateExceeding(row) ? 'e1-analysis-red-row' : '' }
function structureRatio(row: AnalysisRow): string { return analysis.totalEnding.value ? fmtRate(row.endingAmount / analysis.totalEnding.value) : '-' }
function rowAmount(row: AnalysisRow, period: AnalysisPeriod): number {
  return period === 'current' ? row.endingAmount : period === 'prior' ? row.openingAmount : row.priorAmount
}
function updateLegacyPeriod(row: AnalysisRow, period: AnalysisPeriod, value: number): void {
  if (period === 'prior') analysis.updateCell(row.itemKey, 'openingAmount', value)
  if (period === 'prior2') analysis.updateCell(row.itemKey, 'priorAmount', value)
}
async function aiReason(title: string, current: string, context: Record<string, unknown>, apply: (value: string) => void): Promise<void> {
  const text = await generateText({
    section: 'analysis-reason',
    prompt: '结合三年金额、比例和异常信息，生成简洁、可核查的变动原因与合理性分析。不要虚构未提供事实。',
    context,
    existingContent: current,
    confirmTitle: `AI辅助：${title}`,
  })
  if (text) apply(text)
}
async function aiLongText(kind: 'note' | 'conclusion'): Promise<void> {
  const isNote = kind === 'note'
  const section = isNote ? 'analysis-note' : 'analysis-conclusion'
  const text = await generateText({
    section,
    prompt: isNote
      ? '根据货币资金构成、八项比例、月度变动、银行结构、资金质量和异常事项生成审计说明，明确数据来源、程序和异常应对。'
      : '根据已执行程序生成审计结论，区分未见异常、存在需跟进事项和受限情形，不虚构证据。',
    context: { composition: analysis.rows.value, ratios: analysis.ratioRows.value, anomalies: analysis.anomalyRows.value },
    existingContent: isNote ? auditNote.value : auditConclusion.value,
    confirmTitle: `AI生成${isNote ? '审计说明' : '审计结论'}`,
  })
  if (text) saveText(isNote ? NOTE_KEY : CONCLUSION_KEY, isNote ? auditNote : auditConclusion, text)
}

function handleFillFromAdj(): void {
  const filled = analysis.fillFromAdjudication()
  if (filled > 0) {
    ElMessage.success(`已从E1-1带入 ${filled} 项上期金额`)
  } else {
    ElMessage.info('上期金额已有值或E1-1尚无数据，未覆盖')
  }
}
</script>

<template>
  <div class="e1-analysis">
    <div class="method-context"><strong>源模板方法论：</strong>先做三年构成和七类其他货币资金分析，再计算八项比例，结合月度变动、银行类型、资金质量和异常事项形成结论。“存贷双高”必须同时满足货币资金和贷款总额的可见阈值；银行存款占比高仅提示集中度关注。</div>
    <el-alert type="info" :closable="false" title="审计目标：通过分析程序识别货币资金余额和变动异常，评估重大错报风险。" class="objective-alert" />
    <div class="tab-toolbar">
      <div><el-tag type="info">E1-14 七区段分析</el-tag><el-button size="small" type="success" plain :disabled="isReadonly" style="margin-left:8px" @click="handleFillFromAdj">从E1-1带入上期</el-button></div>
      <div class="toolbar-right"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /><el-tag size="small">货币资金 {{ displayPrefs.fmtAmount(analysis.totalEnding.value) }}</el-tag></div>
    </div>
    <el-tabs v-model="activeSection" type="border-card">
      <el-tab-pane label="三年货币资金构成" name="composition">
        <el-table :data="analysis.rows.value" border stripe size="small" :row-class-name="rowClass">
          <el-table-column prop="itemName" label="项目" min-width="130" fixed="left" />
          <el-table-column label="本期金额" min-width="135" align="right" class-name="auto-calc-col"><template #default="{ row }">{{ displayPrefs.fmtAmount(row.endingAmount) }}</template></el-table-column>
          <el-table-column label="本期结构比" width="105" align="center" class-name="auto-calc-col"><template #default="{ row }">{{ structureRatio(row) }}</template></el-table-column>
          <el-table-column v-for="period in (['prior','prior2'] as AnalysisPeriod[])" :key="period" :label="period === 'prior' ? '上期金额' : '前期金额'" min-width="140" align="right">
            <template #default="{ row }"><el-input-number :model-value="rowAmount(row, period)" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" @change="(v: number) => updateLegacyPeriod(row, period, v ?? 0)" /></template>
          </el-table-column>
          <el-table-column label="本期变动率" width="110" align="center" class-name="auto-calc-col"><template #default="{ row }"><span :class="{ danger: analysis.isRateExceeding(row) }">{{ fmtRate(row.changeRate) }}</span></template></el-table-column>
          <el-table-column label="变动原因" min-width="260"><template #default="{ row }"><div class="ai-cell"><el-input type="textarea" :autosize="{ minRows: 2 }" :model-value="row.varianceNote" :disabled="isReadonly" @change="(v: string) => analysis.updateCell(row.itemKey, 'varianceNote', v)" /><el-button text type="primary" :disabled="isReadonly" :loading="isGenerating('analysis-reason')" @click="aiReason(row.itemName, row.varianceNote, row, v => analysis.updateCell(row.itemKey, 'varianceNote', v))">🤖</el-button></div></template></el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="其他货币资金七类" name="other">
        <el-table :data="analysis.otherFundRows.value" border stripe size="small">
          <el-table-column prop="name" label="项目" min-width="150" fixed="left" />
          <el-table-column v-for="period in (['current','prior','prior2'] as AnalysisPeriod[])" :key="period" :label="period === 'current' ? '本期金额' : period === 'prior' ? '上期金额' : '前期金额'" min-width="135" align="right">
            <template #default="{ row }"><el-input-number :model-value="row[period]" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" @change="(v: number) => analysis.updateOtherFund(row.key, period, v ?? 0)" /></template>
          </el-table-column>
          <el-table-column label="变动原因" min-width="260"><template #default="{ row }"><div class="ai-cell"><el-input type="textarea" :autosize="{ minRows: 2 }" :model-value="row.reason" :disabled="isReadonly" @change="(v: string) => analysis.updateOtherFund(row.key, 'reason', v)" /><el-button text type="primary" :disabled="isReadonly" :loading="isGenerating('analysis-reason')" @click="aiReason(row.name, row.reason, row, v => analysis.updateOtherFund(row.key, 'reason', v))">🤖</el-button></div></template></el-table-column>
        </el-table>
        <el-alert class="section-alert" type="info" :closable="false" title="银行承兑汇票保证金测算请交叉索引应付票据底稿 F3-2。" />
      </el-tab-pane>

      <el-tab-pane label="八项比例" name="ratios">
        <h4>比例输入与跨表值</h4>
        <el-table :data="analysis.metricRows.value" border size="small">
          <el-table-column prop="name" label="输入项目" min-width="170" />
          <el-table-column v-for="period in (['current','prior','prior2'] as AnalysisPeriod[])" :key="period" :label="period === 'current' ? '本期' : period === 'prior' ? '上期' : '前期'" min-width="150" align="right">
            <template #default="{ row }"><el-input-number :model-value="row[period]" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" @change="(v: number) => analysis.updateMetric(row.key, period, v ?? 0)" /></template>
          </el-table-column>
        </el-table>
        <div class="thresholds">
          <label>货币资金高位阈值<el-input-number :model-value="analysis.cashThreshold.value" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" @change="(v: number) => analysis.updateThreshold('cashThreshold', v ?? 0)" /></label>
          <label>贷款总额高位阈值<el-input-number :model-value="analysis.loanThreshold.value" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" @change="(v: number) => analysis.updateThreshold('loanThreshold', v ?? 0)" /></label>
          <label>银行存款集中度阈值<el-input-number :model-value="analysis.concentrationThreshold.value" :disabled="isReadonly" :controls="false" :min="0" :max="1" :step="0.05" :precision="2" @change="(v: number) => analysis.updateThreshold('concentrationThreshold', v ?? 0)" /></label>
        </div>
        <el-table :data="analysis.ratioRows.value" border stripe size="small">
          <el-table-column prop="name" label="比例项目" min-width="235" fixed="left" />
          <el-table-column label="本期" width="95" class-name="auto-calc-col"><template #default="{ row }">{{ fmtRate(row.current) }}</template></el-table-column>
          <el-table-column label="上期" width="95" class-name="auto-calc-col"><template #default="{ row }">{{ fmtRate(row.prior) }}</template></el-table-column>
          <el-table-column label="前期" width="95" class-name="auto-calc-col"><template #default="{ row }">{{ fmtRate(row.prior2) }}</template></el-table-column>
          <el-table-column label="本期变动" width="105" class-name="auto-calc-col"><template #default="{ row }">{{ fmtRate(row.currentChange) }}</template></el-table-column>
          <el-table-column label="差异原因及合理性" min-width="250"><template #default="{ row }"><div class="ai-cell"><el-input :model-value="row.reason" :disabled="isReadonly" @change="(v: string) => analysis.updateRatioReason(row.key, v)" /><el-button text type="primary" :disabled="isReadonly" :loading="isGenerating('analysis-reason')" @click="aiReason(row.name, row.reason, row, v => analysis.updateRatioReason(row.key, v))">🤖</el-button></div></template></el-table-column>
        </el-table>
        <el-alert v-if="analysis.showDualHighWarning.value" class="section-alert" type="warning" show-icon :closable="false" title="存贷双高：货币资金与贷款总额均达到用户设定高位阈值，请核查商业理由、资金受限及资金占用风险。" />
        <el-alert v-else-if="analysis.showConcentrationConcern.value" class="section-alert" type="warning" show-icon :closable="false" title="银行存款占比较高，仅构成集中度关注；未同时满足货币资金和贷款阈值，不标记为存贷双高。" />
      </el-tab-pane>

      <el-tab-pane label="月度变动" name="monthly">
        <el-table :data="analysis.monthlyRows.value" border stripe size="small">
          <el-table-column label="月份" width="70"><template #default="{ row }">{{ row.month }}月</template></el-table-column>
          <el-table-column v-for="field in ['opening','increase','decrease']" :key="field" :label="field === 'opening' ? '期初余额' : field === 'increase' ? '本期增加' : '本期减少'" min-width="135" align="right"><template #default="{ row }"><el-input-number :model-value="row[field]" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" @change="(v: number) => analysis.updateMonthly(row.month, field as any, v ?? 0)" /></template></el-table-column>
          <el-table-column label="期末余额" min-width="130" class-name="auto-calc-col"><template #default="{ row }">{{ displayPrefs.fmtAmount(row.ending) }}</template></el-table-column>
          <el-table-column label="月均余额" min-width="130" class-name="auto-calc-col"><template #default="{ row }">{{ displayPrefs.fmtAmount(row.average) }}</template></el-table-column>
          <el-table-column label="分析说明" min-width="230"><template #default="{ row }"><el-input :model-value="row.note" :disabled="isReadonly" @change="(v: string) => analysis.updateMonthly(row.month, 'note', v)" /></template></el-table-column>
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="银行类型结构" name="banks">
        <el-table :data="analysis.bankRows.value" border stripe size="small">
          <el-table-column prop="name" label="银行类型" min-width="130" />
          <el-table-column label="账户数量" width="110"><template #default="{ row }"><el-input-number :model-value="row.accountCount" :disabled="isReadonly" :controls="false" :min="0" size="small" @change="(v: number) => analysis.updateBank(row.key, 'accountCount', v ?? 0)" /></template></el-table-column>
          <el-table-column v-for="field in ['ending','opening']" :key="field" :label="field === 'ending' ? '期末余额' : '期初余额'" min-width="140" align="right"><template #default="{ row }"><el-input-number :model-value="row[field]" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" @change="(v: number) => analysis.updateBank(row.key, field, v ?? 0)" /></template></el-table-column>
          <el-table-column label="占比" width="95" class-name="auto-calc-col"><template #default="{ row }">{{ fmtRate(row.ratio) }}</template></el-table-column>
          <el-table-column label="变动" min-width="125" class-name="auto-calc-col"><template #default="{ row }">{{ displayPrefs.fmtAmount(row.change) }}</template></el-table-column>
          <el-table-column label="变动分析" min-width="220"><template #default="{ row }"><el-input :model-value="row.note" :disabled="isReadonly" @change="(v: string) => analysis.updateBank(row.key, 'note', v)" /></template></el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="资金质量" name="quality">
        <el-table :data="analysis.qualityRows.value" border stripe size="small">
          <el-table-column prop="name" label="分析项目" min-width="150" />
          <el-table-column v-for="field in ['ending','opening']" :key="field" :label="field === 'ending' ? '期末金额' : '期初金额'" min-width="150" align="right"><template #default="{ row }"><el-input-number :model-value="row[field]" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" @change="(v: number) => analysis.updateQuality(row.key, field, v ?? 0)" /></template></el-table-column>
          <el-table-column label="占比" width="100" class-name="auto-calc-col"><template #default="{ row }">{{ fmtRate(row.ratio) }}</template></el-table-column>
          <el-table-column label="分析结论" min-width="280"><template #default="{ row }"><div class="ai-cell"><el-input :model-value="row.conclusion" :disabled="isReadonly" @change="(v: string) => analysis.updateQuality(row.key, 'conclusion', v)" /><el-button text type="primary" :disabled="isReadonly" :loading="isGenerating('analysis-reason')" @click="aiReason(row.name, row.conclusion, row, v => analysis.updateQuality(row.key, 'conclusion', v))">🤖</el-button></div></template></el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="异常分析" name="anomalies">
        <div class="section-actions"><el-button type="primary" size="small" :disabled="isReadonly" @click="analysis.addAnomaly">+ 新增异常</el-button></div>
        <el-table :data="analysis.anomalyRows.value" border stripe size="small">
          <el-table-column label="异常项目" min-width="150"><template #default="{ row }"><el-input :model-value="row.item" :disabled="isReadonly" @change="(v: string) => analysis.updateAnomaly(row.id, 'item', v)" /></template></el-table-column>
          <el-table-column label="金额" min-width="130" align="right"><template #default="{ row }"><WpAmountInput :model-value="row.amount" :disabled="isReadonly" size="small" @change="(v: number) => analysis.updateAnomaly(row.id, 'amount', v ?? 0)" /></template></el-table-column>
          <el-table-column label="原因分析" min-width="230"><template #default="{ row }"><div class="ai-cell"><el-input :model-value="row.reason" :disabled="isReadonly" @change="(v: string) => analysis.updateAnomaly(row.id, 'reason', v)" /><el-button text type="primary" :disabled="isReadonly" :loading="isGenerating('analysis-reason')" @click="aiReason(row.item || '异常项目', row.reason, row, v => analysis.updateAnomaly(row.id, 'reason', v))">🤖</el-button></div></template></el-table-column>
          <el-table-column label="风险评估" min-width="180"><template #default="{ row }"><el-input :model-value="row.risk" :disabled="isReadonly" @change="(v: string) => analysis.updateAnomaly(row.id, 'risk', v)" /></template></el-table-column>
          <el-table-column label="应对措施" min-width="180"><template #default="{ row }"><el-input :model-value="row.response" :disabled="isReadonly" @change="(v: string) => analysis.updateAnomaly(row.id, 'response', v)" /></template></el-table-column>
          <el-table-column label="操作" width="70"><template #default="{ row }"><el-button type="danger" text :disabled="isReadonly" @click="analysis.removeAnomaly(row.id)">删除</el-button></template></el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-card class="audit-card" shadow="never"><template #header><div class="card-header"><span>审计说明</span><el-button type="primary" plain size="small" :disabled="isReadonly" :loading="isGenerating('analysis-note')" @click="aiLongText('note')">🤖 AI辅助</el-button></div></template><el-input type="textarea" :autosize="{ minRows: 5 }" :model-value="auditNote" :disabled="isReadonly" @change="(v: string) => saveText(NOTE_KEY, auditNote, v)" /></el-card>
    <el-card class="audit-card" shadow="never"><template #header><div class="card-header"><span>审计结论</span><el-button type="primary" plain size="small" :disabled="isReadonly" :loading="isGenerating('analysis-conclusion')" @click="aiLongText('conclusion')">🤖 AI辅助</el-button></div></template><el-input type="textarea" :autosize="{ minRows: 3 }" :model-value="auditConclusion" :disabled="isReadonly" @change="(v: string) => saveText(CONCLUSION_KEY, auditConclusion, v)" /></el-card>
    <details class="guidance"><summary>📋 编制提示</summary><p>金额单位默认元。比例分母为零时显示“-”。定期存款比例偏高应取得商业理由支持文件；受限资金、财务公司资金及异常波动应与函证、披露和后续程序交叉核对。</p></details>
  </div>
</template>

<style scoped>
.e1-analysis{padding:12px 0}.e1-analysis :deep(.el-table){font-size:var(--wp-font-size,13px)}
.method-context{margin-bottom:12px;padding:10px 12px;border-left:4px solid #e6a23c;background:#fdf6ec;color:#7a4b00;line-height:1.65}.objective-alert{margin-bottom:12px}
.tab-toolbar,.toolbar-right,.card-header,.section-actions,.thresholds{display:flex;align-items:center}.tab-toolbar,.card-header{justify-content:space-between}.tab-toolbar{margin-bottom:8px}.toolbar-right,.thresholds{gap:10px}.thresholds{flex-wrap:wrap;margin:12px 0}.thresholds label{display:flex;align-items:center;gap:6px;color:#606266}
h4{margin:10px 0}.section-alert,.audit-card{margin-top:14px}.section-actions{justify-content:flex-end;margin-bottom:8px}.ai-cell{display:flex;align-items:flex-start;gap:4px}.ai-cell .el-input,.ai-cell .el-textarea{flex:1}.danger{color:#f56c6c;font-weight:600}:deep(.auto-calc-col){background:#f5f7fa!important}:deep(.e1-analysis-red-row td){background:#fef0f0!important}.guidance{margin-top:14px;padding:8px 12px;border-left:3px solid #409eff;background:#ecf5ff}.guidance summary{cursor:pointer;color:#409eff;font-weight:600}
</style>
