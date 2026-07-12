<!--
  GtA38GoodwillImpairment.vue — A3-8 商誉减值测试专属组件（合并报表层面）
  双模式：结构化视图（4 Tab）+ OnlyOffice Word 编辑
  联动：GtIndexChip → I3-2/I3-6/I3-7 单体商誉底稿核对（只跳转，不取数）
-->
<template>
  <div class="gt-a38" v-loading="loading">
    <div class="gt-a38__header">
      <el-segmented v-model="activeMode" :options="modeOptions" size="default" />
      <div class="gt-a38__xref">
        <span class="gt-a38__xref-label">单体层核对：</span>
        <GtIndexChip v-for="ref in xrefCodes" :key="ref" :value="ref" :validate="true" @click="onChipClick" />
      </div>
    </div>

    <div v-if="activeMode === 'html'" class="gt-a38__html">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="减值主表" name="impairment">
          <div class="gt-a38__toolbar">
            <span class="gt-a38__hint">资产组账面价值为其在<strong>合并报表层面</strong>的账面价值（含已分配商誉 B1 + 未确认少数股东权益商誉 B2）</span>
            <el-button v-if="!readonly" size="small" type="primary" plain :icon="Plus" @click="addImpairmentRow">新增资产组</el-button>
          </div>
          <el-table :data="impairmentRows" border size="small" class="gt-a38__table">
            <el-table-column label="项目名称（资产组）" min-width="160">
              <template #default="{ row }">
                <el-input v-if="!readonly" v-model="row.name" size="small" placeholder="资产组名称" />
                <span v-else>{{ row.name || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="资产组账面价值(A)" width="130">
              <template #default="{ row }"><el-input-number v-model="row.carrying_a" :disabled="readonly" :controls="false" size="small" style="width:100%" /></template>
            </el-table-column>
            <el-table-column label="应分配商誉(B1)" width="120">
              <template #default="{ row }"><el-input-number v-model="row.goodwill_b1" :disabled="readonly" :controls="false" size="small" style="width:100%" /></template>
            </el-table-column>
            <el-table-column label="未确认少数股东商誉(B2)" width="140">
              <template #default="{ row }"><el-input-number v-model="row.minority_b2" :disabled="readonly" :controls="false" size="small" style="width:100%" /></template>
            </el-table-column>
            <el-table-column label="合计(A+B1+B2)" width="120" align="right">
              <template #default="{ row }"><span class="gt-a38__calc">{{ fmt(calcTotal(row)) }}</span></template>
            </el-table-column>
            <el-table-column label="可收回金额" width="120">
              <template #default="{ row }"><el-input-number v-model="row.recoverable" :disabled="readonly" :controls="false" size="small" style="width:100%" /></template>
            </el-table-column>
            <el-table-column label="差额=(1)-(2)" width="110" align="right">
              <template #default="{ row }"><span class="gt-a38__calc">{{ fmt(calcDiff(row)) }}</span></template>
            </el-table-column>
            <el-table-column label="计提减值准备[(3)>0]" width="130" align="right">
              <template #default="{ row }">
                <span class="gt-a38__calc" :class="{ 'gt-a38__calc--warn': calcImpairment(row) > 0 }">{{ fmt(calcImpairment(row)) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="减值原因" min-width="140">
              <template #default="{ row }">
                <el-input v-if="!readonly" v-model="row.reason" size="small" placeholder="导致减值的原因" />
                <span v-else>{{ row.reason || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!readonly" label="操作" width="60" align="center">
              <template #default="{ row }">
                <el-button type="danger" text size="small" :icon="Delete" @click="removeImpairmentRow(row.id)" />
              </template>
            </el-table-column>
          </el-table>
          <div class="gt-a38__totals">
            <span>合计：</span>
            <span>A {{ fmt(impairmentTotals.carrying_a) }}</span>
            <span>B1 {{ fmt(impairmentTotals.goodwill_b1) }}</span>
            <span>B2 {{ fmt(impairmentTotals.minority_b2) }}</span>
            <span>合计 {{ fmt(impairmentTotals.total) }}</span>
            <span>可收回 {{ fmt(impairmentTotals.recoverable) }}</span>
            <span class="gt-a38__totals-impair">减值准备 {{ fmt(impairmentTotals.impairment) }}</span>
          </div>
          <p v-if="impairmentTotals.impairment > 0" class="gt-a38__xref-note">
            已确认商誉减值，请核对 <strong>I3-6</strong> 单体层减值测试结论是否一致。
          </p>
        </el-tab-pane>

        <el-tab-pane label="减值损失分摊" name="allocation">
          <div class="gt-a38__toolbar">
            <span class="gt-a38__hint">减值损失先全额冲减商誉，剩余按其他资产账面价值比例分摊（不得减记至低于各自可收回金额，CAS 8 §23）</span>
            <el-button v-if="!readonly" size="small" type="primary" plain :icon="Plus" @click="addAllocationRow">新增资产</el-button>
          </div>
          <el-form :inline="true" class="gt-a38__alloc-loss">
            <el-form-item label="待分摊减值损失">
              <el-input-number v-model="allocLoss" :disabled="readonly" :controls="false" size="small" style="width:160px" />
            </el-form-item>
          </el-form>
          <el-table :data="allocationRows" border size="small" class="gt-a38__table">
            <el-table-column label="商誉分摊（资产）" min-width="140">
              <template #default="{ row }">
                <el-input v-if="!readonly" v-model="row.asset_type" size="small" placeholder="资产类别" />
                <span v-else>{{ row.asset_type || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="账面价值" width="120">
              <template #default="{ row }"><el-input-number v-model="row.carrying" :disabled="readonly" :controls="false" size="small" style="width:100%" /></template>
            </el-table-column>
            <el-table-column label="未确认少数股东权益" width="140">
              <template #default="{ row }"><el-input-number v-model="row.minority" :disabled="readonly" :controls="false" size="small" style="width:100%" /></template>
            </el-table-column>
            <el-table-column label="可收回金额" width="120">
              <template #default="{ row }"><el-input-number v-model="row.recoverable" :disabled="readonly" :controls="false" size="small" style="width:100%" /></template>
            </el-table-column>
            <el-table-column label="减值损失第一分配(冲商誉)" width="150" align="right">
              <template #default="{ row }"><span class="gt-a38__calc">{{ fmt(allocOf(row.id).alloc_first) }}</span></template>
            </el-table-column>
            <el-table-column label="减值损失第二分配(按比例)" width="150" align="right">
              <template #default="{ row }">
                <span class="gt-a38__calc" :class="{ 'gt-a38__calc--warn': belowRecoverable(row) }">{{ fmt(allocOf(row.id).alloc_second) }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!readonly" label="操作" width="60" align="center">
              <template #default="{ row }">
                <el-button type="danger" text size="small" :icon="Delete" @click="removeAllocationRow(row.id)" />
              </template>
            </el-table-column>
          </el-table>
          <p class="gt-a38__xref-note">分摊合计：{{ fmt(allocSum) }}（应等于待分摊减值损失 {{ fmt(allocLoss) }}）</p>
        </el-tab-pane>

        <el-tab-pane label="可收回金额" name="recoverable">
          <div class="gt-a38__section-title">（一）公允价值减去处置费用后的净额</div>
          <div class="gt-a38__toolbar">
            <el-button v-if="!readonly" size="small" plain :icon="Plus" @click="addFairValueRow">新增项目</el-button>
          </div>
          <el-table :data="recoverable.fair_value_rows" border size="small" class="gt-a38__table">
            <el-table-column label="项目名称" min-width="160">
              <template #default="{ row }">
                <el-input v-if="!readonly" v-model="row.name" size="small" />
                <span v-else>{{ row.name || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="公允价值" width="140">
              <template #default="{ row }"><el-input-number v-model="row.fair_value" :disabled="readonly" :controls="false" size="small" style="width:100%" /></template>
            </el-table-column>
            <el-table-column label="处置费用" width="140">
              <template #default="{ row }"><el-input-number v-model="row.disposal_cost" :disabled="readonly" :controls="false" size="small" style="width:100%" /></template>
            </el-table-column>
            <el-table-column label="公允价值-处置费用" width="150" align="right">
              <template #default="{ row }"><span class="gt-a38__calc">{{ fmt(num(row.fair_value) - num(row.disposal_cost)) }}</span></template>
            </el-table-column>
            <el-table-column v-if="!readonly" label="操作" width="60" align="center">
              <template #default="{ row }">
                <el-button type="danger" text size="small" :icon="Delete" @click="removeFairValueRow(row.id)" />
              </template>
            </el-table-column>
          </el-table>
          <p class="gt-a38__xref-note">公允价值净额合计：<strong>{{ fmt(fairValueNet) }}</strong></p>

          <div class="gt-a38__section-title">（二）预计未来现金流量的现值（最多 5 年）</div>
          <el-table :data="dcfTableRows" border size="small" class="gt-a38__table">
            <el-table-column label="" width="130" prop="label" />
            <el-table-column v-for="(_, i) in 5" :key="i" :label="`第${i + 1}年`" align="right">
              <template #default="{ row }">
                <el-input-number v-if="row.editable" v-model="recoverable.dcf.cash_flows[i]" :disabled="readonly" :controls="false" size="small" style="width:100%" />
                <span v-else class="gt-a38__calc">{{ row.values[i] }}</span>
              </template>
            </el-table-column>
          </el-table>
          <el-form :inline="true" class="gt-a38__dcf-params">
            <el-form-item label="折现率">
              <el-input-number v-model="recoverable.dcf.discount_rate" :disabled="readonly" :controls="false" size="small" :step="0.01" style="width:120px" />
            </el-form-item>
            <el-form-item label="基数现金流">
              <el-input-number v-model="recoverable.dcf.base_cash_flow" :disabled="readonly" :controls="false" size="small" style="width:140px" />
            </el-form-item>
            <el-form-item label="永续增长率">
              <el-input-number v-model="recoverable.dcf.perpetual_growth" :disabled="readonly" :controls="false" size="small" :step="0.01" style="width:120px" />
            </el-form-item>
          </el-form>
          <p class="gt-a38__xref-note">
            预测期现值合计：<strong>{{ fmt(dcfPv) }}</strong>；终值现值：<strong>{{ fmt(terminalPv) }}</strong>
            <span v-if="dcfOver5">（现金流预测最多涵盖 5 年，超出需证明合理性）</span>
          </p>

          <div class="gt-a38__section-title">（三）可收回金额（孰高）</div>
          <div class="gt-a38__recoverable-result">
            <span class="gt-a38__rr-value">{{ fmt(recoverableResult.value) }}</span>
            <el-tag size="small" :type="recoverableResult.path === 'dcf' ? 'warning' : 'success'">
              采用：{{ recoverableResult.path === 'dcf' ? '未来现金流量现值' : '公允价值减处置费用净额' }}
            </el-tag>
          </div>
        </el-tab-pane>

        <el-tab-pane label="WACC 折现率" name="wacc">
          <div class="gt-a38__hint" style="margin-bottom:12px">税后 WACC = E/(D+E)·Ke + D/(D+E)·Kd·(1-税率)；Ke = Rf + β·(Rm-Rf)。折现率口径应与现金流口径一致。</div>
          <el-form label-width="160px" class="gt-a38__wacc-form">
            <el-form-item label="所得税率"><el-input-number v-model="recoverable.wacc.tax_rate" :disabled="readonly" :controls="false" size="small" :step="0.01" style="width:160px" /></el-form-item>
            <el-form-item label="债务总额 (D)"><el-input-number v-model="recoverable.wacc.debt_d" :disabled="readonly" :controls="false" size="small" style="width:160px" /></el-form-item>
            <el-form-item label="资本总额 (E)"><el-input-number v-model="recoverable.wacc.equity_e" :disabled="readonly" :controls="false" size="small" style="width:160px" /></el-form-item>
            <el-form-item label="税前债务成本 (Kd)"><el-input-number v-model="recoverable.wacc.cost_debt_kd" :disabled="readonly" :controls="false" size="small" :step="0.01" style="width:160px" /></el-form-item>
            <el-form-item label="无风险报酬率 (Rf)"><el-input-number v-model="recoverable.wacc.rf" :disabled="readonly" :controls="false" size="small" :step="0.01" style="width:160px" /></el-form-item>
            <el-form-item label="β 系数"><el-input-number v-model="recoverable.wacc.beta" :disabled="readonly" :controls="false" size="small" :step="0.01" style="width:160px" /></el-form-item>
            <el-form-item label="市场平均收益率 (Rm)"><el-input-number v-model="recoverable.wacc.rm" :disabled="readonly" :controls="false" size="small" :step="0.01" style="width:160px" /></el-form-item>
          </el-form>
          <div class="gt-a38__wacc-result">
            <div>权益成本 Ke（CAPM）：<strong>{{ fmtPct(keResult) }}</strong></div>
            <div>加权平均资金成本 WACC（税后）：<strong>{{ waccResult == null ? '—' : fmtPct(waccResult) }}</strong></div>
          </div>
        </el-tab-pane>
      </el-tabs>

      <el-collapse v-if="guidance" class="gt-a38__guidance">
        <el-collapse-item title="编制说明与 CAS 8 准则要点" name="g">
          <div class="gt-a38__g-block">
            <strong>导致商誉减值的原因：</strong>
            <ol><li v-for="(r, i) in guidance.impairment_reasons" :key="i">{{ r }}</li></ol>
          </div>
          <div class="gt-a38__g-block">
            <strong>测试要点：</strong>
            <ul><li v-for="(nt, i) in guidance.notes" :key="i">{{ nt }}</li></ul>
          </div>
          <div class="gt-a38__g-block">
            <strong>WACC 参数定义：</strong>
            <ul><li v-for="(v, k) in guidance.wacc_params" :key="k">{{ v }}</li></ul>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <div v-else-if="activeMode === 'docx'" class="gt-a38__docx">
      <GtOnlyOfficeSheet
        :wp-id="wpId"
        sheet-name="A3-8商誉减值测试"
        :project-id="projectId"
        :whole-workbook="true"
        :readonly="readonly"
        @fallback="docxDirty = true"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Plus, Delete } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import GtOnlyOfficeSheet from '@/components/workpaper/GtOnlyOfficeSheet.vue'
import {
  useA38Goodwill, calcTotal, calcDiff, calcImpairment,
  calcFairValueNet, calcDcfPv, calcTerminalPv, allocateImpairment,
} from '@/components/workpaper/composables/useA38Goodwill'
import type { ResolvedIndexRef } from '@/utils/parseIndexRef'

defineOptions({ name: 'GtA38GoodwillImpairment' })

const props = withDefaults(defineProps<{
  wpId: string
  readonly?: boolean
  projectId?: string
  year?: number
}>(), { readonly: false })

const emit = defineEmits<{ 'jump-to-workpaper': [wpCode: string]; save: [] }>()

const route = useRoute()
const projectId = computed(() => props.projectId || (route.params.projectId as string) || '')
const auditYear = computed(() => props.year || parseInt(route.query.year as string) || new Date().getFullYear())

const activeMode = ref<'html' | 'docx'>('html')
const activeTab = ref('impairment')
const docxDirty = ref(false)
const allocLoss = ref<number | null>(null)
const modeOptions = [{ label: '结构化视图', value: 'html' }, { label: 'Word编辑', value: 'docx' }]
const xrefCodes = ['I3-2', 'I3-6', 'I3-7']

const eng = useA38Goodwill(() => props.wpId, () => projectId.value, () => auditYear.value, () => props.readonly)
const {
  impairmentRows, allocationRows, recoverable, guidance, loading,
  impairmentTotals, waccResult, keResult, recoverableResult,
  load, flushSave,
  addImpairmentRow, removeImpairmentRow, addAllocationRow, removeAllocationRow,
  addFairValueRow, removeFairValueRow,
} = eng

const num = (v: number | null | undefined): number => (v == null || isNaN(v as number) ? 0 : Number(v))

const fairValueNet = computed(() => calcFairValueNet(recoverable.value.fair_value_rows))
const dcfPv = computed(() => calcDcfPv(recoverable.value.dcf))
const terminalPv = computed(() => calcTerminalPv(recoverable.value.dcf))
const dcfOver5 = computed(() => recoverable.value.dcf.cash_flows.filter((c) => c != null).length > 5)

const dcfTableRows = computed(() => {
  const r = recoverable.value.dcf.discount_rate
  const factors = Array.from({ length: 5 }, (_, i) => (r == null || r <= -1 ? '—' : (1 / Math.pow(1 + r, i + 1)).toFixed(4)))
  const pvs = Array.from({ length: 5 }, (_, i) => {
    if (r == null || r <= -1) return '—'
    const cf = recoverable.value.dcf.cash_flows[i]
    return fmt(num(cf) * (1 / Math.pow(1 + r, i + 1)))
  })
  return [
    { label: '现金净流量(税前)', editable: true, values: [] as string[] },
    { label: '折现系数', editable: false, values: factors },
    { label: '现值', editable: false, values: pvs },
  ]
})

const allocResult = computed(() => allocateImpairment(allocationRows.value, num(allocLoss.value)))
function allocOf(id: string) {
  return allocResult.value.find((x) => x.id === id) ?? { alloc_first: 0, alloc_second: 0 }
}
const allocSum = computed(() => allocResult.value.reduce((s, x) => s + x.alloc_first + x.alloc_second, 0))
function belowRecoverable(row: any): boolean {
  const a = allocOf(row.id)
  const afterAlloc = num(row.carrying) - a.alloc_first - a.alloc_second
  return row.recoverable != null && afterAlloc < num(row.recoverable)
}

function fmt(v: number | null | undefined): string {
  if (v == null || isNaN(v as number) || v === 0) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPct(v: number | null | undefined): string {
  if (v == null || isNaN(v as number)) return '—'
  return (Number(v) * 100).toFixed(2) + '%'
}

function onChipClick(resolved: ResolvedIndexRef) {
  if (resolved.ns === 'wp' && resolved.target) emit('jump-to-workpaper', resolved.target)
}

watch(activeMode, async (newMode, oldMode) => {
  if (newMode === 'html' && oldMode === 'docx' && docxDirty.value) {
    docxDirty.value = false
    await load()
  }
  if (newMode === 'docx') docxDirty.value = true
})

onMounted(load)
onBeforeUnmount(flushSave)

defineExpose({ activeMode, reload: load, flushSave })
</script>

<style scoped>
.gt-a38 { padding: 16px; display: flex; flex-direction: column; gap: 14px; }
.gt-a38__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.gt-a38__xref { display: flex; align-items: center; gap: 6px; }
.gt-a38__xref-label { font-size: 12px; color: #909399; }
.gt-a38__toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
.gt-a38__hint { font-size: 12px; color: #909399; line-height: 1.6; }
.gt-a38__table { width: 100%; }
.gt-a38__calc { font-variant-numeric: tabular-nums; color: #2c5282; }
.gt-a38__calc--warn { color: #c0392b; font-weight: 600; }
.gt-a38__totals { display: flex; gap: 16px; flex-wrap: wrap; padding: 10px 14px; margin-top: 8px; background: #f7f9fc; border-radius: 8px; font-size: var(--wp-font-size, 13px); }
.gt-a38__totals-impair { color: #c0392b; font-weight: 600; }
.gt-a38__xref-note { font-size: 12px; color: #606266; margin: 8px 0 0; }
.gt-a38__alloc-loss { margin-bottom: 8px; }
.gt-a38__section-title { font-size: 14px; font-weight: 600; color: #2c5282; margin: 16px 0 8px; padding-bottom: 4px; border-bottom: 2px solid #c6d4e1; }
.gt-a38__dcf-params, .gt-a38__wacc-form { margin-top: 12px; }
.gt-a38__recoverable-result { display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: #edf2f7; border-radius: 8px; }
.gt-a38__rr-value { font-size: 18px; font-weight: 700; color: #2c5282; font-variant-numeric: tabular-nums; }
.gt-a38__wacc-result { padding: 12px 16px; background: #f7f9fc; border-radius: 8px; line-height: 2; }
.gt-a38__guidance { margin-top: 8px; }
.gt-a38__g-block { margin-bottom: 12px; font-size: var(--wp-font-size, 13px); line-height: 1.7; }
.gt-a38__g-block ol, .gt-a38__g-block ul { margin: 4px 0 0; padding-left: 20px; }
.gt-a38__docx { min-height: calc(100vh - 240px); }
</style>
