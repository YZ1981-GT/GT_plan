<script setup lang="ts">
/**
 * F2TabOverallAnalysis — F2-18 存货总体分析表
 * A 构成 / B 指标三期 / C 同行业 / D 产品大类周转 + 分段说明 + 结论
 */
import { toRef, type Ref } from 'vue'
import { useF2OverallAnalysis } from '../../composables/useF2OverallAnalysis'
import { useF2AiGenerate } from '../../composables/useF2AiGenerate'
import { useStickySectionNav } from '../../composables/useStickySectionNav'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import type { useF2CrossSheet } from '../../composables/useF2CrossSheet'
import F2ReviewChip from '../shared/F2ReviewChip.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'

const oaNav = [
  { id: 'st-oa-a', label: 'A 构成' },
  { id: 'st-oa-b', label: 'B 指标' },
  { id: 'st-oa-c', label: 'C 同行业' },
  { id: 'st-oa-d', label: 'D 周转' },
  { id: 'st-oa-conclusion', label: '结论' },
]
const { activeId, scrollTo } = useStickySectionNav(oaNav)

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  crossSheet: ReturnType<typeof useF2CrossSheet>
}>()

const oa = useF2OverallAnalysis({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  crossSheet: props.crossSheet,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const {
  yearLabels,
  compositionRows,
  compositionTotals,
  indicatorRows,
  industryRows,
  productRows,
  abnormalCount,
  notesA,
  notesB,
  notesC,
  notesD,
  analysisConclusion,
  updateYearLabel,
  updateComposition,
  updateInput,
  updateAbnormalB,
  updateIndustryPeer,
  updateIndustryAbnormal,
  updateNotes,
  addProductRow,
  removeProductRow,
  updateProduct,
  syncCompositionFromDetail,
  aiContext,
  pack,
} = oa

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

const YES_NO = [
  { label: '是', value: '是' },
  { label: '否', value: '否' },
  { label: '—', value: '' },
]

function fmt(v: number): string {
  if (!v) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '-'
  return `${v.toFixed(2)}%`
}

function fmtInd(v: number, unit: string): string {
  if (!v && v !== 0) return '-'
  if (unit === '%') return `${v.toFixed(2)}%`
  if (unit === '天') return v.toFixed(1)
  return v.toFixed(2)
}

async function genSection(
  section: 'f2-18-note-a' | 'f2-18-note-b' | 'f2-18-note-c' | 'f2-18-note-d' | 'f2-18-abnormal' | 'f2-18-conclusion' | 'analysis-conclusion',
  existing: string,
  title: string,
  apply: (text: string) => void,
) {
  const text = await generateAndConfirm(section, existing, aiContext(), title)
  if (text) apply(text)
}

function saveConclusion(v: string) {
  analysisConclusion.value = v
}

function inputVal(yearIdx: number, field: 'cogs' | 'invAvg' | 'invBal' | 'impairment' | 'caAvg' | 'writeOff'): number {
  const key = `${field}${yearIdx}` as keyof typeof pack.value.inputs
  return pack.value.inputs[key]
}

function setInput(yearIdx: number, field: 'cogs' | 'invAvg' | 'invBal' | 'impairment' | 'caAvg' | 'writeOff', v: number) {
  updateInput(`${field}${yearIdx}` as any, v)
}
</script>

<template>
  <div class="f2-overall-analysis">
    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. A 构成：优先从 F2-3~F2-13 回写本期/上期金额；结构比自动计算；人工可覆盖并勾选是否异常。</p>
        <p>2. B 指标：录入营业成本、平均存货、跌价、流动资产、核销等，系统计算周转率/天数及比例与变动率。</p>
        <p>3. C 同行业：填行业平均与对标公司，看偏差；跌价风险高时可拆分至原材料/库存商品等再比。</p>
        <p>4. D 产品大类：按主要产品录入平均存货与营业成本，计算周转率及变动；各段填写审计说明与异常原因后给总体结论。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：分析存货构成、周转与占比是否合理；与历史及同行业比较识别异常，为减值与深挖程序提供依据。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag v-if="abnormalCount > 0" size="small" type="danger">异常标记 {{ abnormalCount }} 项</el-tag>
        <el-button size="small" :disabled="isReadonly" @click="syncCompositionFromDetail">同步明细金额</el-button>
        <F2ReviewChip section-id="F2-18-analysis" />
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown
          :wp-id="wpId"
          api-prefix="f2"
          sheet="F2-18"
          :disabled="isReadonly"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F2-18" :context-project-id="projectId" :validate="false" /></span>
      </div>
    </div>

    <div class="year-labels">
      <span>期间标签：</span>
      <el-input
        v-for="(lab, idx) in yearLabels"
        :key="idx"
        size="small"
        style="width: 120px"
        :model-value="lab"
        :disabled="isReadonly"
        @change="(v: string) => updateYearLabel(idx as 0 | 1 | 2, v)"
      />
    </div>

    <nav class="st-sec-nav oa-sec-nav" aria-label="分区导航">
      <button
        v-for="item in oaNav"
        :key="item.id"
        type="button"
        class="st-sec-btn"
        :class="{ active: activeId === item.id }"
        @click="scrollTo(item.id)"
      >{{ item.label }}</button>
    </nav>

    <!-- A 构成 -->
    <el-card id="st-oa-a" shadow="never" class="block-card">
      <template #header><span class="block-title">一、存货构成分析（三期对比）</span></template>
      <el-table :data="compositionRows" border size="small">
        <el-table-column prop="label" label="存货项目" width="160" fixed />
        <el-table-column :label="yearLabels[0]" align="center">
          <el-table-column label="金额" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.amt0"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(v: number | undefined) => updateComposition(row.key, 'amt0', v ?? 0)"
              />
              <span v-else>{{ fmt(row.amt0) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="结构比" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.share0) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column :label="yearLabels[1]" align="center">
          <el-table-column label="金额" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.amt1"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(v: number | undefined) => updateComposition(row.key, 'amt1', v ?? 0)"
              />
              <span v-else>{{ fmt(row.amt1) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="结构比" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.share1) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column :label="yearLabels[2]" align="center">
          <el-table-column label="金额" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.amt2"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(v: number | undefined) => updateComposition(row.key, 'amt2', v ?? 0)"
              />
              <span v-else>{{ fmt(row.amt2) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="结构比" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.share2) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="是否异常" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.abnormal"
              size="small"
              @change="(v: string) => updateComposition(row.key, 'abnormal', v)"
            >
              <el-option v-for="o in YES_NO" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ row.abnormal || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="total-bar">
        合计：{{ yearLabels[0] }} {{ fmt(compositionTotals.amt0) }}
        | {{ yearLabels[1] }} {{ fmt(compositionTotals.amt1) }}
        | {{ yearLabels[2] }} {{ fmt(compositionTotals.amt2) }}
      </div>
      <div class="section-notes">
        <div class="note-head">
          <span>审计说明</span>
          <el-button
            size="small"
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="genSection('f2-18-note-a', notesA.note, 'AI · A构成说明', (t) => updateNotes('notesA', 'note', t))"
          >AI辅助</el-button>
        </div>
        <el-input
          type="textarea"
          :model-value="notesA.note"
          :disabled="isReadonly"
          :autosize="{ minRows: 3 }"
          placeholder="概述构成分析程序与结果…"
          @change="(v: string) => updateNotes('notesA', 'note', v)"
        />
        <div class="note-head" style="margin-top:8px">
          <span>异常原因</span>
          <el-button
            size="small"
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="genSection('f2-18-abnormal', notesA.abnormalReason, 'AI · A异常原因', (t) => updateNotes('notesA', 'abnormalReason', t))"
          >AI辅助</el-button>
        </div>
        <el-input
          type="textarea"
          :model-value="notesA.abnormalReason"
          :disabled="isReadonly"
          :autosize="{ minRows: 2 }"
          placeholder="对标为异常的项目说明原因…"
          @change="(v: string) => updateNotes('notesA', 'abnormalReason', v)"
        />
      </div>
    </el-card>

    <!-- B 指标三期 -->
    <el-card id="st-oa-b" shadow="never" class="block-card">
      <template #header><span class="block-title">二、存货指标分析（三期数据对比）</span></template>
      <el-collapse>
        <el-collapse-item title="指标计算输入（营业成本/平均存货/跌价/流动资产/核销）" name="inputs">
          <div class="input-grid">
            <template v-for="(yl, yi) in yearLabels" :key="yl">
              <div class="input-year">
                <strong>{{ yl }}</strong>
                <label>营业成本
                  <el-input-number :model-value="inputVal(yi, 'cogs')" :controls="false" size="small" :disabled="isReadonly"
                    @change="(v: number | undefined) => setInput(yi, 'cogs', v ?? 0)" />
                </label>
                <label>平均存货
                  <el-input-number :model-value="inputVal(yi, 'invAvg')" :controls="false" size="small" :disabled="isReadonly"
                    @change="(v: number | undefined) => setInput(yi, 'invAvg', v ?? 0)" />
                </label>
                <label>存货余额
                  <el-input-number :model-value="inputVal(yi, 'invBal')" :controls="false" size="small" :disabled="isReadonly"
                    @change="(v: number | undefined) => setInput(yi, 'invBal', v ?? 0)" />
                </label>
                <label>跌价准备
                  <el-input-number :model-value="inputVal(yi, 'impairment')" :controls="false" size="small" :disabled="isReadonly"
                    @change="(v: number | undefined) => setInput(yi, 'impairment', v ?? 0)" />
                </label>
                <label>平均流动资产
                  <el-input-number :model-value="inputVal(yi, 'caAvg')" :controls="false" size="small" :disabled="isReadonly"
                    @change="(v: number | undefined) => setInput(yi, 'caAvg', v ?? 0)" />
                </label>
                <label>核销净额
                  <el-input-number :model-value="inputVal(yi, 'writeOff')" :controls="false" size="small" :disabled="isReadonly"
                    @change="(v: number | undefined) => setInput(yi, 'writeOff', v ?? 0)" />
                </label>
              </div>
            </template>
          </div>
        </el-collapse-item>
      </el-collapse>

      <el-table :data="indicatorRows" border size="small" style="margin-top:8px">
        <el-table-column prop="label" label="指标" min-width="220" />
        <el-table-column :label="yearLabels[0]" align="center">
          <el-table-column label="指标值" width="100" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtInd(row.v0, row.unit) }}</template>
          </el-table-column>
          <el-table-column label="变动率" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.change01) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column :label="yearLabels[1]" align="center">
          <el-table-column label="指标值" width="100" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtInd(row.v1, row.unit) }}</template>
          </el-table-column>
          <el-table-column label="变动率" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.change12) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column :label="yearLabels[2]" align="center">
          <el-table-column label="指标值" width="100" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtInd(row.v2, row.unit) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="是否异常" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.abnormal"
              size="small"
              @change="(v: string) => updateAbnormalB(row.key, v)"
            >
              <el-option v-for="o in YES_NO" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ row.abnormal || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="section-notes">
        <div class="note-head">
          <span>审计说明</span>
          <el-button size="small" :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="genSection('f2-18-note-b', notesB.note, 'AI · B指标说明', (t) => updateNotes('notesB', 'note', t))">AI辅助</el-button>
        </div>
        <el-input type="textarea" :model-value="notesB.note" :disabled="isReadonly" :autosize="{ minRows: 3 }"
          @change="(v: string) => updateNotes('notesB', 'note', v)" />
        <div class="note-head" style="margin-top:8px"><span>异常原因</span></div>
        <el-input type="textarea" :model-value="notesB.abnormalReason" :disabled="isReadonly" :autosize="{ minRows: 2 }"
          @change="(v: string) => updateNotes('notesB', 'abnormalReason', v)" />
      </div>
    </el-card>

    <!-- C 同行业 -->
    <el-card id="st-oa-c" shadow="never" class="block-card">
      <template #header>
        <div class="card-header-flex">
          <span class="block-title">三、存货指标分析（与同行业数据对比）</span>
        </div>
      </template>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="hint-alert"
        title="对于存货跌价准备错报风险较高的项目，可进一步拆分原材料、库存商品等分别与行业数据比较。"
      />
      <div class="peer-names">
        <label>行业平均名称 <el-input size="small" style="width:140px" :model-value="pack.industry.avg.name" :disabled="isReadonly"
          @change="(v: string) => updateIndustryPeer('avg', 'name', v)" /></label>
        <label>公司A <el-input size="small" style="width:120px" :model-value="pack.industry.companyA.name" :disabled="isReadonly"
          @change="(v: string) => updateIndustryPeer('companyA', 'name', v)" /></label>
        <label>公司B <el-input size="small" style="width:120px" :model-value="pack.industry.companyB.name" :disabled="isReadonly"
          @change="(v: string) => updateIndustryPeer('companyB', 'name', v)" /></label>
        <label>公司C <el-input size="small" style="width:120px" :model-value="pack.industry.companyC.name" :disabled="isReadonly"
          @change="(v: string) => updateIndustryPeer('companyC', 'name', v)" /></label>
      </div>
      <el-table :data="industryRows" border size="small">
        <el-table-column prop="label" label="指标" min-width="200" />
        <el-table-column :label="yearLabels[0]" align="center">
          <el-table-column label="指标值" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtInd(row.client, row.unit) }}</template>
          </el-table-column>
          <el-table-column label="偏差" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.deviation) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="行业平均" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.industry" :controls="false" size="small" style="width:100%"
              @change="(v: number | undefined) => updateIndustryPeer('avg', row.key, v ?? 0)" />
            <span v-else>{{ fmtInd(row.industry, row.unit) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="pack.industry.companyA.name || '公司A'" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.companyA" :controls="false" size="small" style="width:100%"
              @change="(v: number | undefined) => updateIndustryPeer('companyA', row.key, v ?? 0)" />
            <span v-else>{{ fmtInd(row.companyA, row.unit) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="pack.industry.companyB.name || '公司B'" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.companyB" :controls="false" size="small" style="width:100%"
              @change="(v: number | undefined) => updateIndustryPeer('companyB', row.key, v ?? 0)" />
            <span v-else>{{ fmtInd(row.companyB, row.unit) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="pack.industry.companyC.name || '公司C'" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.companyC" :controls="false" size="small" style="width:100%"
              @change="(v: number | undefined) => updateIndustryPeer('companyC', row.key, v ?? 0)" />
            <span v-else>{{ fmtInd(row.companyC, row.unit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.abnormal" size="small"
              @change="(v: string) => updateIndustryAbnormal(row.key, v)">
              <el-option v-for="o in YES_NO" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ row.abnormal || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="section-notes">
        <div class="note-head">
          <span>审计说明</span>
          <el-button size="small" :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="genSection('f2-18-note-c', notesC.note, 'AI · C行业说明', (t) => updateNotes('notesC', 'note', t))">AI辅助</el-button>
        </div>
        <el-input type="textarea" :model-value="notesC.note" :disabled="isReadonly" :autosize="{ minRows: 3 }"
          @change="(v: string) => updateNotes('notesC', 'note', v)" />
        <div class="note-head" style="margin-top:8px"><span>异常原因</span></div>
        <el-input type="textarea" :model-value="notesC.abnormalReason" :disabled="isReadonly" :autosize="{ minRows: 2 }"
          @change="(v: string) => updateNotes('notesC', 'abnormalReason', v)" />
      </div>
    </el-card>

    <!-- D 产品大类 -->
    <el-card id="st-oa-d" shadow="never" class="block-card">
      <template #header>
        <div class="card-header-flex">
          <span class="block-title">四、主要产品大类存货周转（三期对比）</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addProductRow">+ 新增产品</el-button>
        </div>
      </template>
      <el-table :data="productRows" border size="small">
        <el-table-column label="产品名称" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.productName" size="small"
              @change="(v: string) => updateProduct(row.rowId, 'productName', v)" />
            <span v-else>{{ row.productName }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="yearLabels[0]" align="center">
          <el-table-column label="平均存货" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.avgInv0" :controls="false" size="small" style="width:100%"
                @change="(v: number | undefined) => updateProduct(row.rowId, 'avgInv0', v ?? 0)" />
              <span v-else>{{ fmt(row.avgInv0) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="营业成本" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.cogs0" :controls="false" size="small" style="width:100%"
                @change="(v: number | undefined) => updateProduct(row.rowId, 'cogs0', v ?? 0)" />
              <span v-else>{{ fmt(row.cogs0) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="周转率" width="80" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ row.turnover0 ? row.turnover0.toFixed(2) : '-' }}</template>
          </el-table-column>
          <el-table-column label="变动率" width="80" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ fmtPct(row.change01) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column :label="yearLabels[1]" align="center">
          <el-table-column label="平均存货" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.avgInv1" :controls="false" size="small" style="width:100%"
                @change="(v: number | undefined) => updateProduct(row.rowId, 'avgInv1', v ?? 0)" />
              <span v-else>{{ fmt(row.avgInv1) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="营业成本" width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.cogs1" :controls="false" size="small" style="width:100%"
                @change="(v: number | undefined) => updateProduct(row.rowId, 'cogs1', v ?? 0)" />
              <span v-else>{{ fmt(row.cogs1) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="周转率" width="80" align="right" class-name="auto-calc-col">
            <template #default="{ row }">{{ row.turnover1 ? row.turnover1.toFixed(2) : '-' }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column :label="yearLabels[2] + '周转率'" width="100" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <div v-if="!isReadonly" class="mini-inputs">
              <el-input-number :model-value="row.avgInv2" :controls="false" size="small" placeholder="均存"
                @change="(v: number | undefined) => updateProduct(row.rowId, 'avgInv2', v ?? 0)" />
              <el-input-number :model-value="row.cogs2" :controls="false" size="small" placeholder="成本"
                @change="(v: number | undefined) => updateProduct(row.rowId, 'cogs2', v ?? 0)" />
            </div>
            <span>{{ row.turnover2 ? row.turnover2.toFixed(2) : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="100" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.abnormal" size="small"
              @change="(v: string) => updateProduct(row.rowId, 'abnormal', v)">
              <el-option v-for="o in YES_NO" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <span v-else>{{ row.abnormal || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center">
          <template #default="{ row }">
            <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeProductRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="section-notes">
        <div class="note-head">
          <span>审计说明</span>
          <el-button size="small" :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="genSection('f2-18-note-d', notesD.note, 'AI · D周转说明', (t) => updateNotes('notesD', 'note', t))">AI辅助</el-button>
        </div>
        <el-input type="textarea" :model-value="notesD.note" :disabled="isReadonly" :autosize="{ minRows: 3 }"
          @change="(v: string) => updateNotes('notesD', 'note', v)" />
        <div class="note-head" style="margin-top:8px"><span>异常原因</span></div>
        <el-input type="textarea" :model-value="notesD.abnormalReason" :disabled="isReadonly" :autosize="{ minRows: 2 }"
          @change="(v: string) => updateNotes('notesD', 'abnormalReason', v)" />
      </div>
    </el-card>

    <!-- 总体结论 -->
    <el-card id="st-oa-conclusion" class="opinion-card audit-note-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">分析结论（四、审计结论）</span>
          <div class="opinion-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="genSection('f2-18-conclusion', analysisConclusion, 'AI 生成 · 总体分析结论', saveConclusion)"
            >AI辅助</el-button>
            <F2ReviewChip section-id="F2-18-conclusion" />
          </div>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="analysisConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 4, maxRows: 12 }"
        placeholder="A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制），不可确认。"
        @change="saveConclusion"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f2-overall-analysis { padding: 12px; font-size: 13px; font-size: var(--wp-font-size, 13px); }
.f2-overall-analysis :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f2-overall-analysis :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.hint-alert { margin-bottom: 8px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.year-labels { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.block-card { margin-bottom: 12px; }
.block-title { font-weight: 600; }
.card-header-flex { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.total-bar { margin-top: 8px; text-align: right; font-weight: 600; color: #606266; }
.section-notes { margin-top: 12px; }
.note-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 6px; font-weight: 500;
}
.input-grid { display: flex; gap: 16px; flex-wrap: wrap; }
.input-year {
  display: flex; flex-direction: column; gap: 6px; min-width: 200px;
  padding: 8px; background: #fafafa; border-radius: 4px;
}
.input-year label { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 12px; }
.peer-names { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; align-items: center; }
.peer-names label { display: flex; align-items: center; gap: 4px; font-size: 12px; }
.mini-inputs { display: flex; flex-direction: column; gap: 2px; margin-bottom: 4px; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
.audit-note-card { margin-top: 16px; }
</style>

<style src="../stocktake/f2StocktakeSoftNav.css"></style>
