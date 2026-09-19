<template>
  <div class="f2-supplier-structure f2-ipo-soft">
    <header class="sheet-header">
      <div>
        <h3>重要供应商结构分析</h3>
        <span class="code">F2-68 · 本年/上年主要供应商采购结构与业务合理性</span>
      </div>
      <div class="stats">
        <el-tag size="small">本年 {{ ss.currentSummary.value.supplierCount }} 家</el-tag>
        <el-tag size="small" type="warning">
          前5大占比 {{ fmtRate(ss.currentSummary.value.top5Ratio) }}
        </el-tag>
        <el-tag v-if="ss.currentSummary.value.riskCount" size="small" type="danger">
          风险项 {{ ss.currentSummary.value.riskCount }}
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 分别填列本年和上年重要供应商，比较采购金额、集中度、主要采购产品及交易条件变化。</p>
        <p>2. 采购占比、排名、数量×单价复核及同比变化自动计算；异常差异会提示关注。</p>
        <p>3. 重点检查采购额是否与供应商规模匹配、采购产品是否在其经营范围内，并识别新增或异常供应商。</p>
        <p>4. 对关联方、规模或经营范围不匹配、金额复核差异，应在备注中记录原因及支持性证据索引。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：分析主要供应商采购数量、金额、单价、信用期、支付及运输方式变动，评价交易合理性、持续性及供应商结构风险。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="ss.addRow('current')">
          + 本年供应商
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="ss.addRow('prior')">
          + 上年供应商
        </el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-68"
          :disabled="isReadonly"
          review-section="F2-68-structure"
        />
        <GtIndexChip value="wp:F2-68" />
      </div>
    </div>

    <section
      v-for="section in sections"
      :key="section.period"
      class="period-section"
    >
      <div class="section-title">
        <div>
          <span class="period-badge">{{ section.period === 'current' ? '本' : '上' }}</span>
          <strong>{{ section.title }}</strong>
        </div>
        <div class="section-summary">
          合计 {{ fmtAmount(section.summary.total) }}
          · 前5大 {{ fmtRate(section.summary.top5Ratio) }}
          · 前10大 {{ fmtRate(section.summary.top10Ratio) }}
        </div>
      </div>

      <div class="table-scroll-wrap">
        <table class="supplier-table">
          <thead>
            <tr>
              <th rowspan="2" class="sticky seq">序号</th>
              <th rowspan="2" class="sticky supplier">重要供应商名称</th>
              <th rowspan="2">采购金额</th>
              <th rowspan="2" class="calc-head">占比</th>
              <th rowspan="2" class="calc-head">排名</th>
              <th rowspan="2" class="calc-head">较上年变动</th>
              <th rowspan="2">主要采购产品</th>
              <th colspan="6">采购业务情况</th>
              <th rowspan="2">是否关联方</th>
              <th rowspan="2">采购额与供应商规模是否匹配</th>
              <th rowspan="2">采购产品与经营范围是否匹配</th>
              <th rowspan="2" class="remark-col">备注/异常原因</th>
              <th rowspan="2">索引号</th>
              <th rowspan="2">操作</th>
            </tr>
            <tr>
              <th>数量</th>
              <th>单价</th>
              <th>信用期</th>
              <th>支付方式</th>
              <th>运输方式</th>
              <th>其他条款</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(row, index) in section.rows"
              :key="row.id"
              :class="{ 'warn-row': row.isRisk }"
            >
              <td class="sticky seq">{{ index + 1 }}</td>
              <td class="sticky supplier">
                <CellInput
                  :value="row.supplierName"
                  :readonly="isReadonly"
                  placeholder="供应商名称"
                  @change="(value) => update(section.period, row.id, 'supplierName', value)"
                />
              </td>
              <td>
                <NumberInput
                  :value="row.purchaseAmount"
                  :readonly="isReadonly"
                  @change="(value) => update(section.period, row.id, 'purchaseAmount', value)"
                />
              </td>
              <td class="calc-cell"><span class="formula">{{ fmtRate(row.ratio) }}</span></td>
              <td class="calc-cell"><span class="formula">{{ row.rank || '—' }}</span></td>
              <td class="calc-cell" :class="{ danger: changeRate(row, section.period)?.abnormal }">
                <span class="formula">{{ changeRate(row, section.period)?.text || '—' }}</span>
              </td>
              <td>
                <CellInput
                  :value="row.relatedProduct"
                  :readonly="isReadonly"
                  @change="(value) => update(section.period, row.id, 'relatedProduct', value)"
                />
              </td>
              <td>
                <NumberInput
                  :value="row.purchaseQuantity"
                  :readonly="isReadonly"
                  @change="(value) => update(section.period, row.id, 'purchaseQuantity', value)"
                />
              </td>
              <td :class="{ 'amount-mismatch': row.isAmountMismatch }">
                <NumberInput
                  :value="row.unitPrice"
                  :readonly="isReadonly"
                  @change="(value) => update(section.period, row.id, 'unitPrice', value)"
                />
              </td>
              <td>
                <CellInput
                  :value="row.creditPeriod"
                  :readonly="isReadonly"
                  @change="(value) => update(section.period, row.id, 'creditPeriod', value)"
                />
              </td>
              <td>
                <CellInput
                  :value="row.paymentMethod"
                  :readonly="isReadonly"
                  @change="(value) => update(section.period, row.id, 'paymentMethod', value)"
                />
              </td>
              <td>
                <CellInput
                  :value="row.transportMethod"
                  :readonly="isReadonly"
                  @change="(value) => update(section.period, row.id, 'transportMethod', value)"
                />
              </td>
              <td>
                <CellInput
                  :value="row.otherTerms"
                  :readonly="isReadonly"
                  @change="(value) => update(section.period, row.id, 'otherTerms', value)"
                />
              </td>
              <td v-for="field in yesNoFields" :key="field.key">
                <el-select
                  v-if="!isReadonly"
                  :model-value="row[field.key] || undefined"
                  size="small"
                  clearable
                  @change="(value) => update(section.period, row.id, field.key, (value as YesNo) || '')"
                >
                  <el-option label="是" value="是" />
                  <el-option label="否" value="否" />
                </el-select>
                <span v-else>{{ row[field.key] || '—' }}</span>
              </td>
              <td class="remark-col">
                <CellInput
                  :value="row.remark"
                  :readonly="isReadonly"
                  placeholder="变动或异常原因"
                  @change="(value) => update(section.period, row.id, 'remark', value)"
                />
              </td>
              <td>
                <CellInput
                  :value="row.indexRef"
                  :readonly="isReadonly"
                  @change="(value) => update(section.period, row.id, 'indexRef', value)"
                />
              </td>
              <td>
                <el-button
                  link
                  type="danger"
                  size="small"
                  :disabled="isReadonly || rawRows(section.period).length <= 1"
                  @click="ss.removeRow(section.period, row.id)"
                >删除</el-button>
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td colspan="2">合计</td>
              <td class="amount">{{ fmtAmount(section.summary.total) }}</td>
              <td class="calc-cell">{{ section.summary.total ? '100.00%' : '—' }}</td>
              <td colspan="15"></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span>审计说明</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('supplier-structure-note')"
          >AI 填写审计说明</el-button>
        </div>
      </template>
      <el-input
        v-model="ss.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="说明主要供应商集中度、年度变动、新增/异常供应商、交易条件及供应商规模和经营范围匹配情况……"
      />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span>审计结论</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('supplier-structure-conclusion')"
          >AI 生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合评价重要供应商结构、采购集中度、交易合理性和持续性。"
        @update:model-value="saveConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, ref, toRef, type Ref } from 'vue'
import { ElInput, ElInputNumber } from 'element-plus'
import { useF2SupplierStructure } from '../../composables/useF2SupplierStructure'
import type {
  EnrichedSupplierStructureRow,
  SupplierPeriod,
  SupplierStructureRow,
  YesNo,
} from '../../composables/useF2SupplierStructureFormulas'
import { useF2SpecialAiGenerate, type F2SpeAiSection } from '../../composables/useF2SpecialAiGenerate'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const ss = useF2SupplierStructure({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const CellInput = defineComponent({
  props: {
    value: { type: String, default: '' },
    readonly: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
  },
  emits: ['change'],
  setup(componentProps, { emit }) {
    return () => componentProps.readonly
      ? h('span', componentProps.value || '—')
      : h(ElInput, {
          modelValue: componentProps.value,
          size: 'small',
          placeholder: componentProps.placeholder,
          'onUpdate:modelValue': (value: string) => emit('change', value),
        })
  },
})

const NumberInput = defineComponent({
  props: {
    value: { type: Number, default: 0 },
    readonly: { type: Boolean, default: false },
  },
  emits: ['change'],
  setup(componentProps, { emit }) {
    return () => componentProps.readonly
      ? h('span', { class: 'amount' }, fmtAmount(componentProps.value))
      : h(ElInputNumber, {
          modelValue: componentProps.value,
          size: 'small',
          controls: false,
          min: 0,
          class: 'number-input',
          'onUpdate:modelValue': (value: number | undefined) => emit('change', value ?? 0),
        })
  },
})

const sections = computed(() => [
  {
    period: 'current' as const,
    title: '本年重要供应商',
    rows: ss.currentRows.value,
    summary: ss.currentSummary.value,
  },
  {
    period: 'prior' as const,
    title: '上年重要供应商',
    rows: ss.priorRows.value,
    summary: ss.priorSummary.value,
  },
])

const yesNoFields: Array<{
  key: 'isRelatedParty' | 'scaleMatches' | 'scopeMatches'
  label: string
}> = [
  { key: 'isRelatedParty', label: '是否关联方' },
  { key: 'scaleMatches', label: '规模匹配' },
  { key: 'scopeMatches', label: '经营范围匹配' },
]

function rawRows(period: SupplierPeriod): SupplierStructureRow[] {
  return period === 'current' ? ss.sheet.value.currentRows : ss.sheet.value.priorRows
}

function update<K extends keyof SupplierStructureRow>(
  period: SupplierPeriod,
  id: string,
  field: K,
  value: SupplierStructureRow[K],
): void {
  ss.updateRow(period, id, { [field]: value } as Pick<SupplierStructureRow, K>)
}

function fmtAmount(value: number): string {
  return value
    ? value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : '—'
}

function fmtRate(value: number): string {
  return `${(value * 100).toFixed(2)}%`
}

function changeRate(row: EnrichedSupplierStructureRow, period: SupplierPeriod) {
  if (period === 'prior' || !row.supplierName.trim()) return null
  const prior = ss.priorRows.value.find((item) => item.supplierName.trim() === row.supplierName.trim())
  if (!prior?.purchaseAmount) {
    return row.purchaseAmount ? { text: '新增', abnormal: true } : null
  }
  const rate = (row.purchaseAmount - prior.purchaseAmount) / prior.purchaseAmount
  return { text: `${(rate * 100).toFixed(1)}%`, abnormal: Math.abs(rate) >= 0.3 }
}

const CONCLUSION_KEY = 'F2-68-audit-conclusion'
const auditConclusion = ref('')

function saveConclusion(value: string): void {
  if (props.isReadonly) return
  auditConclusion.value = value
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: value }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}

onMounted(() => {
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
  const legacy = props.allResponses.get('F2-68-audit-note')?.remark
  if (!ss.auditNote.value && legacy) ss.auditNote.value = legacy
})

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2SpecialAiGenerate(wpIdRef)

function aiContext(): Record<string, unknown> {
  const mapRows = (rows: EnrichedSupplierStructureRow[]) => rows
    .filter((row) => row.supplierName.trim())
    .slice(0, 30)
    .map((row) => ({
      supplierName: row.supplierName,
      amount: row.purchaseAmount,
      ratio: row.ratio,
      rank: row.rank,
      relatedProduct: row.relatedProduct,
      isRelatedParty: row.isRelatedParty,
      scaleMatches: row.scaleMatches,
      scopeMatches: row.scopeMatches,
      amountMismatch: row.isAmountMismatch,
      remark: row.remark,
    }))
  return {
    sheet: 'F2-68',
    currentSummary: ss.currentSummary.value,
    priorSummary: ss.priorSummary.value,
    currentRows: mapRows(ss.currentRows.value),
    priorRows: mapRows(ss.priorRows.value),
    auditNote: ss.auditNote.value,
  }
}

async function runAi(section: F2SpeAiSection): Promise<void> {
  const isNote = section === 'supplier-structure-note'
  const content = await generateAndConfirm(
    section,
    isNote ? ss.auditNote.value : auditConclusion.value,
    aiContext(),
    isNote ? 'AI 生成 · 重要供应商结构审计说明' : 'AI 生成 · 重要供应商结构审计结论',
  )
  if (!content) return
  if (isNote) ss.auditNote.value = content
  else saveConclusion(content)
}
</script>

<style scoped>
.f2-supplier-structure{padding:14px 18px;font-size:var(--wp-font-size, 13px);background:linear-gradient(180deg,#faf8fc 0,#fff 130px);--purple:#4b2d77}
.sheet-header,.stats,.tab-toolbar,.toolbar-left,.toolbar-right,.section-title,.opinion-header{display: flex;align-items:center}.sheet-header,.tab-toolbar,.section-title,.opinion-header{justify-content:space-between}.sheet-header{gap:12px;margin-bottom:12px}.sheet-header h3{margin:0;color:#35204f}.code{font-size:12px;color:#8c7b9d}.stats,.toolbar-left,.toolbar-right{gap:8px;flex-wrap:wrap}
.guidance-details{margin-bottom:12px;border-left:3px solid var(--purple);background:#f7f2fa;border-radius:5px;padding:8px 12px}.guidance-details summary{cursor:pointer;font-weight:600;color:var(--purple)}.guidance-content{margin-top:8px;color:#606266;line-height:1.7}.guidance-content p{margin:3px 0}.objective-alert{margin-bottom:12px}.tab-toolbar{gap:10px;margin-bottom:14px}
.period-section{margin-bottom:18px;border:1px solid #d7cae2;border-radius:7px;overflow:hidden}.section-title{padding:9px 12px;background:#f5f0f8;color:#4b2d77}.period-badge{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;margin-right:7px;border-radius:50%;background:var(--purple);color:#fff}.section-summary{font-size:12px;color:#72558e}.table-scroll-wrap{max-width:100%;overflow-x: auto}
.supplier-table{width:100%;min-width:2050px;border-collapse:separate;border-spacing:0;font-size:11px}.supplier-table th,.supplier-table td{border-right:1px solid #d8cce3;border-bottom:1px solid #d8cce3;padding:4px;text-align:center;vertical-align:middle;background:#fff}.supplier-table th{position:sticky;top:0;z-index:3;background:var(--purple);color:#fff;font-weight:600;line-height:1.25}.supplier-table .sticky{position:sticky;z-index:4}.supplier-table th.sticky{z-index:5}.supplier-table td.sticky{background:#fff}.seq{left:0;width:45px;min-width:45px}.supplier{left:45px;width:150px;min-width:150px}.calc-head{background:#6b4b89!important}.calc-cell{background:#f2ecf7!important;color:#4b2d77;font-weight:600}.formula{border-bottom:1px dotted #8d78a2;cursor:help}.remark-col{width:170px;min-width:170px;text-align:left!important}.warn-row td{background:#fef0f0}.warn-row td.sticky{background:#fef0f0}.amount-mismatch{box-shadow:inset 0 0 0 2px #e6a23c}.danger{color:#c45656!important;font-weight:700}.amount{display:block;text-align:right;white-space:nowrap}.supplier-table tfoot td{background:#eee6f4;font-weight:700}
:deep(.number-input){width:92px}:deep(.number-input .el-input__inner){text-align:right;padding:0 4px}
.opinion-card{margin-top:16px;border-color:#ded3e8}.opinion-card :deep(.el-card__header){padding:10px 14px;background:#faf8fc}.opinion-header span{font-weight:700;color:var(--purple)}
</style>
