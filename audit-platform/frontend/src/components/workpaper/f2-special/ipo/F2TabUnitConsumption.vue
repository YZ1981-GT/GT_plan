<template>
  <div class="f2-val-sheet f2-unit-consumption f2-ipo-soft">
    <header class="uc-hero">
      <div class="uc-hero-text">
        <div class="uc-title-row">
          <h3>主要产品生产成本及单耗分析表</h3>
          <span class="uc-code">F2-64</span>
        </div>
        <p class="uc-desc">成本构成 / 成本衔接 / 单位成本 / 原材料单耗</p>
      </div>
      <div class="uc-metrics">
        <div class="uc-metric">
          <span class="uc-metric-val">{{ uc.sheet.value.productName || '未填写' }}</span>
          <span class="uc-metric-label">分析产品</span>
        </div>
        <div class="uc-metric" :class="{ danger: uc.abnormalCount.value > 0 }">
          <span class="uc-metric-val">{{ uc.abnormalCount.value }}</span>
          <span class="uc-metric-label">异常项</span>
        </div>
        <div class="uc-metric muted">
          <span class="uc-metric-val">{{ uc.sheet.value.currentYear }}/{{ uc.sheet.value.priorYear }}</span>
          <span class="uc-metric-label">对比年度</span>
        </div>
      </div>
    </header>

    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 按本年、上年逐月分析生产成本构成及各成本项目占比，自动计算月度与年度合计。</p>
        <p>2. 通过期初在产品、本期投入、期末在产品与产量衔接测算单位生产成本；通过产成品成本衔接复核单位材料、人工、制造费用及单位成本。</p>
        <p>3. 与同行业公司单位成本结构比较，并按主要原材料测算单位产量耗用量和单位成本。</p>
        <p>4. 浅灰底列为自动计算项；月度行固定生成，可切换「本年 / 上年 / 两年对照」查看。</p>
      </div>
    </details>
    <el-alert type="info" :closable="false" :title="objectiveText" class="objective-alert" />

    <div class="uc-meta-card">
      <label class="uc-field">
        <span>产品名称</span>
        <el-input
          :model-value="uc.sheet.value.productName"
          size="small"
          placeholder="填写主要产品名称"
          :disabled="isReadonly"
          @update:model-value="(v: string) => uc.updateMeta({ productName: v })"
        />
      </label>
      <label class="uc-field year">
        <span>本年</span>
        <el-input
          :model-value="uc.sheet.value.currentYear"
          size="small"
          :disabled="isReadonly"
          @update:model-value="(v: string) => uc.updateMeta({ currentYear: v })"
        />
      </label>
      <label class="uc-field year">
        <span>上年</span>
        <el-input
          :model-value="uc.sheet.value.priorYear"
          size="small"
          :disabled="isReadonly"
          @update:model-value="(v: string) => uc.updateMeta({ priorYear: v })"
        />
      </label>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-64"
          :disabled="isReadonly"
          review-section="F2-64-consumption"
        />
        <GtIndexChip value="wp:F2-64" />
      </div>
    </div>

    <div class="uc-nav">
      <nav class="uc-section-nav" aria-label="区块导航">
        <button
          v-for="sec in sectionNav"
          :key="sec.id"
          type="button"
          class="uc-nav-btn"
          :class="{ active: activeSection === sec.id }"
          @click="scrollToSection(sec.id)"
        >
          <span class="uc-nav-idx">{{ sec.idx }}</span>
          {{ sec.label }}
        </button>
      </nav>
      <el-radio-group v-model="periodMode" size="small" class="uc-period">
        <el-radio-button value="current">本年 {{ uc.sheet.value.currentYear }}</el-radio-button>
        <el-radio-button value="prior">上年 {{ uc.sheet.value.priorYear }}</el-radio-button>
        <el-radio-button value="both">两年对照</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 一、生产成本构成及占比 -->
    <section id="uc-structure" class="uc-card analysis-section">
      <header class="uc-card-head">
        <span class="uc-card-idx">01</span>
        <div>
          <h4>一、生产成本构成及上期各月发生额分析</h4>
          <p>逐月金额与占比，合计自动汇总</p>
        </div>
      </header>
      <div class="material-name-row">
        <span class="field-label">主要材料名称</span>
        <el-input
          v-for="(_, i) in uc.sheet.value.materialNames"
          :key="i"
          :model-value="uc.sheet.value.materialNames[i]"
          size="small"
          :disabled="isReadonly"
          :placeholder="`材料${i + 1}`"
          @update:model-value="(v: string) => updateTuple('materialNames', i, v)"
        />
      </div>
      <div class="table-scroll">
        <table class="matrix-table structure-table">
          <thead>
            <tr>
              <th rowspan="2">年度</th>
              <th rowspan="2">月份</th>
              <th colspan="7">金额</th>
              <th colspan="6">占比</th>
            </tr>
            <tr>
              <th v-for="name in structureAmountHeaders" :key="`a-${name}`">{{ name }}</th>
              <th v-for="name in structureRateHeaders" :key="`r-${name}`">{{ name }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="period in visiblePeriods" :key="period.key">
              <tr v-for="(row, index) in structureByPeriod(period.key)" :key="row.id">
                <td
                  v-if="index === 0"
                  :rowspan="structureByPeriod(period.key).length + 1"
                  class="year-cell"
                >
                  {{ periodLabel(period.key) }}
                </td>
                <td>{{ row.month }}月</td>
                <td v-for="field in structureFields" :key="field">
                  <el-input-number
                    :model-value="row[field]"
                    size="small"
                    :controls="false"
                    class="compact-num"
                    :disabled="isReadonly"
                    @change="(v: number | undefined) => uc.updateCostStructure(row.id, { [field]: v ?? 0 })"
                  />
                </td>
                <td class="calc-cell">{{ fmt(row.total) }}</td>
                <td
                  v-for="field in structureFields"
                  :key="`rate-${field}`"
                  class="calc-cell"
                >
                  {{ fmtPct(row.rates[field]) }}
                </td>
              </tr>
              <tr class="row-total">
                <td>合计</td>
                <td
                  v-for="field in structureFields"
                  :key="`total-${field}`"
                  class="num"
                >
                  {{ fmt(sumStructure(period.key, field)) }}
                </td>
                <td class="calc-cell">{{ fmt(sumStructure(period.key, 'total')) }}</td>
                <td
                  v-for="field in structureFields"
                  :key="`tr-${field}`"
                  class="calc-cell"
                >
                  {{ fmtPct(totalStructureRate(period.key, field)) }}
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <AuditNoteBlock
        title="审计说明"
        :value="notes.structure"
        :readonly="isReadonly"
        :loading="aiLoading"
        :ai-disabled="!aiAvailable"
        @update="saveNote('structure', $event)"
        @ai="runAi('production-cost-structure-note')"
      />
    </section>

    <!-- 二、生产成本衔接 -->
    <section id="uc-flow" class="uc-card analysis-section">
      <header class="uc-card-head">
        <span class="uc-card-idx">02</span>
        <div>
          <h4>二、生产成本本期期初、上期期月结转、产量、产成品单位成本分析</h4>
          <p>期初 / 投入 / 期末衔接，单位成本自动测算</p>
        </div>
      </header>
      <div class="table-scroll">
        <table class="matrix-table flow-table">
          <thead>
            <tr>
              <th>年度</th>
              <th>月份</th>
              <th>期初余额</th>
              <th>本期投入</th>
              <th>转入产品</th>
              <th>转入其他</th>
              <th>期末余额</th>
              <th>产量</th>
              <th class="calc-head">单位成本</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="period in visiblePeriods" :key="period.key">
              <tr v-for="(row, index) in flowByPeriod(period.key)" :key="row.id">
                <td
                  v-if="index === 0"
                  :rowspan="flowByPeriod(period.key).length + 1"
                  class="year-cell"
                >
                  {{ periodLabel(period.key) }}
                </td>
                <td>{{ row.month }}月</td>
                <td v-for="field in flowFields" :key="field">
                  <el-input-number
                    :model-value="row[field]"
                    size="small"
                    :controls="false"
                    class="compact-num"
                    :disabled="isReadonly"
                    @change="(v: number | undefined) => uc.updateCostFlow(row.id, { [field]: v ?? 0 })"
                  />
                </td>
                <td class="calc-cell">{{ fmtPrice(row.unitCost) }}</td>
              </tr>
              <tr class="row-total">
                <td>合计</td>
                <td v-for="field in flowFields" :key="field" class="num">
                  {{ fmt(sumFlow(period.key, field)) }}
                </td>
                <td class="calc-cell">{{ fmtPrice(totalFlowUnitCost(period.key)) }}</td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <AuditNoteBlock
        title="审计说明"
        :value="notes.flow"
        :readonly="isReadonly"
        :loading="aiLoading"
        :ai-disabled="!aiAvailable"
        @update="saveNote('flow', $event)"
        @ai="runAi('production-cost-flow-note')"
      />
    </section>

    <!-- 三、产品单位成本 -->
    <section id="uc-unit" class="uc-card analysis-section">
      <header class="uc-card-head">
        <span class="uc-card-idx">03</span>
        <div>
          <h4>三、产品单位成本分析</h4>
          <p>产成品成本衔接与单位成本拆解；同行业比较</p>
        </div>
      </header>
      <div class="table-scroll">
        <table class="matrix-table unit-table">
          <thead>
            <tr>
              <th rowspan="2">年度</th>
              <th rowspan="2">月份</th>
              <th rowspan="2">期初产成品</th>
              <th colspan="3">投入在产品</th>
              <th rowspan="2">期末产成品</th>
              <th rowspan="2" class="calc-head">成本小计</th>
              <th rowspan="2">产量</th>
              <th colspan="4">单位成本</th>
            </tr>
            <tr>
              <th>直接材料</th>
              <th>直接人工</th>
              <th>制造费用</th>
              <th class="calc-head">单位材料</th>
              <th class="calc-head">单位人工</th>
              <th class="calc-head">单位制造费用</th>
              <th class="calc-head">单位成本</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="period in visiblePeriods" :key="period.key">
              <tr v-for="(row, index) in unitByPeriod(period.key)" :key="row.id">
                <td
                  v-if="index === 0"
                  :rowspan="unitByPeriod(period.key).length + 1"
                  class="year-cell"
                >
                  {{ periodLabel(period.key) }}
                </td>
                <td>{{ row.month }}月</td>
                <td v-for="field in unitInputFields" :key="field">
                  <el-input-number
                    :model-value="row[field]"
                    size="small"
                    :controls="false"
                    class="compact-num"
                    :disabled="isReadonly"
                    @change="(v: number | undefined) => uc.updateUnitCost(row.id, { [field]: v ?? 0 })"
                  />
                </td>
                <td class="calc-cell">{{ fmt(row.costTotal) }}</td>
                <td>
                  <el-input-number
                    :model-value="row.outputQty"
                    size="small"
                    :controls="false"
                    class="compact-num"
                    :disabled="isReadonly"
                    @change="(v: number | undefined) => uc.updateUnitCost(row.id, { outputQty: v ?? 0 })"
                  />
                </td>
                <td class="calc-cell">{{ fmtPrice(row.unitMaterial) }}</td>
                <td class="calc-cell">{{ fmtPrice(row.unitLabor) }}</td>
                <td class="calc-cell">{{ fmtPrice(row.unitManufacturing) }}</td>
                <td class="calc-cell">{{ fmtPrice(row.unitCost) }}</td>
              </tr>
              <tr class="row-total">
                <td>合计</td>
                <td v-for="field in unitInputFields" :key="field" class="num">
                  {{ fmt(sumUnit(period.key, field)) }}
                </td>
                <td class="calc-cell">{{ fmt(sumUnit(period.key, 'costTotal')) }}</td>
                <td class="num">{{ fmt(sumUnit(period.key, 'outputQty')) }}</td>
                <td class="calc-cell">{{ fmtPrice(totalUnitComponent(period.key, 'directMaterial')) }}</td>
                <td class="calc-cell">{{ fmtPrice(totalUnitComponent(period.key, 'directLabor')) }}</td>
                <td class="calc-cell">{{ fmtPrice(totalUnitComponent(period.key, 'manufacturing')) }}</td>
                <td class="calc-cell">{{ fmtPrice(totalUnitComponent(period.key, 'costTotal')) }}</td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <div class="sub-panel">
        <div class="sub-title">本年单位成本与同行业公司比较</div>
        <div class="peer-name-row">
          <el-input
            v-for="(_, i) in uc.sheet.value.peerCompanies"
            :key="i"
            :model-value="uc.sheet.value.peerCompanies[i]"
            size="small"
            :disabled="isReadonly"
            :placeholder="`同业公司${i + 1}`"
            @update:model-value="(v: string) => updateTuple('peerCompanies', i, v)"
          />
        </div>
        <div class="table-scroll">
          <table class="matrix-table peer-table">
            <thead>
              <tr>
                <th>项目</th>
                <th>被审计单位单耗</th>
                <th v-for="name in uc.sheet.value.peerCompanies" :key="name">{{ name }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in uc.sheet.value.peerRows" :key="row.id">
                <td class="row-label">{{ row.item }}</td>
                <td v-for="field in peerFields" :key="field">
                  <el-input-number
                    :model-value="row[field]"
                    size="small"
                    :controls="false"
                    class="compact-num"
                    :disabled="isReadonly"
                    @change="(v: number | undefined) => uc.updatePeer(row.id, { [field]: v ?? 0 })"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <AuditNoteBlock
        title="审计说明"
        :value="notes.unit"
        :readonly="isReadonly"
        :loading="aiLoading"
        :ai-disabled="!aiAvailable"
        @update="saveNote('unit', $event)"
        @ai="runAi('product-unit-cost-note')"
      />
    </section>

    <!-- 四、主要原材料耗用 -->
    <section id="uc-material" class="uc-card analysis-section">
      <header class="uc-card-head">
        <span class="uc-card-idx">04</span>
        <div>
          <h4>四、产品主要原材料耗用分析</h4>
          <p>投入量、金额与单位产量耗用 / 单位成本</p>
        </div>
      </header>
      <div class="material-name-row">
        <span class="field-label">主要原材料</span>
        <el-input
          v-for="(_, i) in uc.sheet.value.consumptionMaterialNames"
          :key="i"
          :model-value="uc.sheet.value.consumptionMaterialNames[i]"
          size="small"
          :disabled="isReadonly"
          :placeholder="`原材料${i + 1}`"
          @update:model-value="(v: string) => updateTuple('consumptionMaterialNames', i, v)"
        />
      </div>
      <div class="table-scroll">
        <table class="matrix-table material-table">
          <thead>
            <tr>
              <th rowspan="2">年度</th>
              <th rowspan="2">月份</th>
              <th rowspan="2">产量</th>
              <th
                v-for="name in uc.sheet.value.consumptionMaterialNames"
                :key="name"
                colspan="5"
              >
                {{ name }}
              </th>
            </tr>
            <tr>
              <template
                v-for="name in uc.sheet.value.consumptionMaterialNames"
                :key="`sub-${name}`"
              >
                <th>投入量</th>
                <th>单位</th>
                <th>投入金额</th>
                <th class="calc-head">单位产量</th>
                <th class="calc-head">单位成本</th>
              </template>
            </tr>
          </thead>
          <tbody>
            <template v-for="period in visiblePeriods" :key="period.key">
              <tr v-for="(row, index) in materialByPeriod(period.key)" :key="row.id">
                <td
                  v-if="index === 0"
                  :rowspan="materialByPeriod(period.key).length + 1"
                  class="year-cell"
                >
                  {{ periodLabel(period.key) }}
                </td>
                <td>{{ row.month }}月</td>
                <td>
                  <el-input-number
                    :model-value="row.outputQty"
                    size="small"
                    :controls="false"
                    class="compact-num"
                    :disabled="isReadonly"
                    @change="(v: number | undefined) => uc.updateMaterialConsumption(row.id, { outputQty: v ?? 0 })"
                  />
                </td>
                <template v-for="key in materialKeys" :key="key">
                  <td>
                    <el-input-number
                      :model-value="row[key].inputQty"
                      size="small"
                      :controls="false"
                      class="compact-num"
                      :disabled="isReadonly"
                      @change="(v: number | undefined) => uc.updateMaterialCell(row.id, key, { inputQty: v ?? 0 })"
                    />
                  </td>
                  <td>
                    <el-input
                      :model-value="row[key].unit"
                      size="small"
                      :disabled="isReadonly"
                      @update:model-value="(v: string) => uc.updateMaterialCell(row.id, key, { unit: v })"
                    />
                  </td>
                  <td>
                    <el-input-number
                      :model-value="row[key].inputAmount"
                      size="small"
                      :controls="false"
                      class="compact-num"
                      :disabled="isReadonly"
                      @change="(v: number | undefined) => uc.updateMaterialCell(row.id, key, { inputAmount: v ?? 0 })"
                    />
                  </td>
                  <td class="calc-cell">{{ fmtPrice(row[key].unitOutput) }}</td>
                  <td class="calc-cell">{{ fmtPrice(row[key].unitCost) }}</td>
                </template>
              </tr>
              <tr class="row-total">
                <td>合计</td>
                <td class="num">{{ fmt(sumMaterial(period.key, 'outputQty')) }}</td>
                <template v-for="key in materialKeys" :key="key">
                  <td class="num">{{ fmt(sumMaterialCell(period.key, key, 'inputQty')) }}</td>
                  <td>—</td>
                  <td class="num">{{ fmt(sumMaterialCell(period.key, key, 'inputAmount')) }}</td>
                  <td class="calc-cell">{{ fmtPrice(totalMaterialMetric(period.key, key, 'inputQty')) }}</td>
                  <td class="calc-cell">{{ fmtPrice(totalMaterialMetric(period.key, key, 'inputAmount')) }}</td>
                </template>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <AuditNoteBlock
        title="审计说明"
        :value="notes.material"
        :readonly="isReadonly"
        :loading="aiLoading"
        :ai-disabled="!aiAvailable"
        @update="saveNote('material', $event)"
        @ai="runAi('material-consumption-note')"
      />
    </section>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">五、审计结论</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('unit-consumption-conclusion')"
          >
            AI 生成结论
          </el-button>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="A、未见异常。B、除已识别事项外，其余未见异常。C、不可确认。"
        @update:model-value="saveConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, onUnmounted, reactive, ref, toRef, type Ref } from 'vue'
import { ElButton, ElInput } from 'element-plus'
import { useF2UnitConsumption } from '../../composables/useF2UnitConsumption'
import { F2_64_OBJECTIVE, type UnitConsumptionSheet } from '../../composables/useF2UnitConsumptionFormulas'
import { useF2SpecialAiGenerate, type F2SpeAiSection } from '../../composables/useF2SpecialAiGenerate'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const uc = useF2UnitConsumption({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
const objectiveText = F2_64_OBJECTIVE
const periods = [{ key: 'current' as const }, { key: 'prior' as const }]
const periodMode = ref<'current' | 'prior' | 'both'>('current')
const activeSection = ref('uc-structure')
const visiblePeriods = computed(() => {
  if (periodMode.value === 'both') return periods
  return periods.filter((p) => p.key === periodMode.value)
})

const sectionNav = [
  { id: 'uc-structure', idx: '01', label: '成本构成' },
  { id: 'uc-flow', idx: '02', label: '成本衔接' },
  { id: 'uc-unit', idx: '03', label: '单位成本' },
  { id: 'uc-material', idx: '04', label: '原材料单耗' },
]

function scrollToSection(id: string) {
  activeSection.value = id
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

let sectionObserver: IntersectionObserver | null = null
onMounted(() => {
  sectionObserver = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((e) => e.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
      if (visible?.target?.id) activeSection.value = visible.target.id
    },
    { rootMargin: '-20% 0px -55% 0px', threshold: [0.1, 0.35, 0.6] },
  )
  for (const sec of sectionNav) {
    const el = document.getElementById(sec.id)
    if (el) sectionObserver.observe(el)
  }
})
onUnmounted(() => {
  sectionObserver?.disconnect()
  sectionObserver = null
})

const structureFields = ['material1', 'material2', 'material3', 'otherMaterial', 'directLabor', 'manufacturing'] as const
const structureAmountHeaders = ['主要原材料1', '主要原材料2', '主要原材料3', '其他材料', '直接人工', '制造费用', '小计']
const structureRateHeaders = ['主要原材料1', '主要原材料2', '主要原材料3', '其他材料', '直接人工', '制造费用']
const flowFields = ['openingWip', 'materialInput', 'laborInput', 'manufacturingInput', 'endingWip', 'outputQty'] as const
const unitInputFields = ['openingFinished', 'directMaterial', 'directLabor', 'manufacturing', 'endingFinished'] as const
const peerFields = ['auditedUnit', 'peer1Unit', 'peer2Unit', 'peer3Unit'] as const
const materialKeys = ['material1', 'material2'] as const

function periodLabel(period: 'current' | 'prior'): string {
  return period === 'current' ? uc.sheet.value.currentYear : uc.sheet.value.priorYear
}
function structureByPeriod(period: 'current' | 'prior') {
  return uc.costStructureRows.value.filter((r) => r.period === period)
}
function flowByPeriod(period: 'current' | 'prior') {
  return uc.costFlowRows.value.filter((r) => r.period === period)
}
function unitByPeriod(period: 'current' | 'prior') {
  return uc.unitCostRows.value.filter((r) => r.period === period)
}
function materialByPeriod(period: 'current' | 'prior') {
  return uc.materialConsumptionRows.value.filter((r) => r.period === period)
}
function sum<T>(rows: T[], getter: (row: T) => number): number {
  return rows.reduce((s, row) => s + (getter(row) || 0), 0)
}
function sumStructure(period: 'current' | 'prior', field: typeof structureFields[number] | 'total') {
  return sum(structureByPeriod(period), (r) => r[field])
}
function totalStructureRate(period: 'current' | 'prior', field: typeof structureFields[number]) {
  const total = sumStructure(period, 'total')
  return total ? sumStructure(period, field) / total : null
}
function sumFlow(period: 'current' | 'prior', field: typeof flowFields[number]) {
  return sum(flowByPeriod(period), (r) => r[field])
}
function totalFlowUnitCost(period: 'current' | 'prior') {
  const rows = flowByPeriod(period)
  const qty = sum(rows, (r) => r.outputQty)
  return qty ? sum(rows, (r) => r.productionCost) / qty : null
}
function sumUnit(period: 'current' | 'prior', field: typeof unitInputFields[number] | 'costTotal' | 'outputQty') {
  return sum(unitByPeriod(period), (r) => r[field])
}
function totalUnitComponent(
  period: 'current' | 'prior',
  field: 'directMaterial' | 'directLabor' | 'manufacturing' | 'costTotal',
) {
  const qty = sumUnit(period, 'outputQty')
  return qty ? sumUnit(period, field) / qty : null
}
function sumMaterial(period: 'current' | 'prior', field: 'outputQty') {
  return sum(materialByPeriod(period), (r) => r[field])
}
function sumMaterialCell(
  period: 'current' | 'prior',
  key: typeof materialKeys[number],
  field: 'inputQty' | 'inputAmount',
) {
  return sum(materialByPeriod(period), (r) => r[key][field])
}
function totalMaterialMetric(
  period: 'current' | 'prior',
  key: typeof materialKeys[number],
  field: 'inputQty' | 'inputAmount',
) {
  const output = sumMaterial(period, 'outputQty')
  return output ? sumMaterialCell(period, key, field) / output : null
}
function updateTuple(
  key: 'materialNames' | 'consumptionMaterialNames' | 'peerCompanies',
  index: number,
  value: string,
) {
  const next = [...uc.sheet.value[key]]
  next[index] = value
  uc.updateMeta({ [key]: next } as Partial<UnitConsumptionSheet>)
}
function fmt(value: number): string {
  return value ? value.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) : '—'
}
function fmtPrice(value: number | null): string {
  return value === null || !Number.isFinite(value)
    ? '—'
    : value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}
function fmtPct(value: number | null): string {
  return value === null ? '—' : `${(value * 100).toFixed(2)}%`
}

const AuditNoteBlock = defineComponent({
  props: {
    title: { type: String, required: true },
    value: { type: String, required: true },
    readonly: Boolean,
    loading: Boolean,
    aiDisabled: Boolean,
  },
  emits: ['update', 'ai'],
  setup(p, { emit }) {
    return () => h('div', { class: 'inline-note' }, [
      h('div', { class: 'inline-note-head' }, [
        h('strong', p.title),
        h(ElButton, {
          size: 'small',
          type: 'primary',
          plain: true,
          disabled: p.readonly || p.aiDisabled || p.loading,
          loading: p.loading,
          onClick: () => emit('ai'),
        }, () => 'AI 起草'),
      ]),
      h(ElInput, {
        modelValue: p.value,
        type: 'textarea',
        autosize: { minRows: 2, maxRows: 8 },
        disabled: p.readonly,
        placeholder: '说明所执行程序、月度波动及异常原因与核查结果……',
        'onUpdate:modelValue': (value: string) => emit('update', value),
      }),
    ])
  },
})

type NoteKind = 'structure' | 'flow' | 'unit' | 'material'
const noteKeys: Record<NoteKind, string> = {
  structure: 'F2-64-note-structure',
  flow: 'F2-64-note-flow',
  unit: 'F2-64-note-unit',
  material: 'F2-64-note-material',
}
const notes = reactive<Record<NoteKind, string>>({
  structure: '',
  flow: '',
  unit: '',
  material: '',
})
const auditConclusion = ref('')
const CONCLUSION_KEY = 'F2-64-audit-conclusion'
function persistText(key: string, value: string) {
  const item = { item_id: key, conclusion: null, remark: value }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}
function saveNote(kind: NoteKind, value: string) {
  if (props.isReadonly) return
  notes[kind] = value
  persistText(noteKeys[kind], value)
}
function saveConclusion(value: string) {
  if (props.isReadonly) return
  auditConclusion.value = value
  persistText(CONCLUSION_KEY, value)
}
onMounted(() => {
  for (const kind of Object.keys(noteKeys) as NoteKind[]) {
    notes[kind] = props.allResponses.get(noteKeys[kind])?.remark || ''
  }
  if (!notes.structure && uc.auditNote.value) notes.structure = uc.auditNote.value
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
})

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2SpecialAiGenerate(wpIdRef)
function aiContext() {
  return {
    sheet: 'F2-64',
    productName: uc.sheet.value.productName,
    currentYear: uc.sheet.value.currentYear,
    priorYear: uc.sheet.value.priorYear,
    costStructure: uc.costStructureRows.value,
    costFlow: uc.costFlowRows.value,
    unitCost: uc.unitCostRows.value,
    peerRows: uc.sheet.value.peerRows,
    materialConsumption: uc.materialConsumptionRows.value,
  }
}
async function runAi(section: F2SpeAiSection) {
  const map: Record<string, { kind?: NoteKind; title: string }> = {
    'production-cost-structure-note': { kind: 'structure', title: 'AI 起草 · 生产成本构成说明' },
    'production-cost-flow-note': { kind: 'flow', title: 'AI 起草 · 生产成本衔接说明' },
    'product-unit-cost-note': { kind: 'unit', title: 'AI 起草 · 产品单位成本说明' },
    'material-consumption-note': { kind: 'material', title: 'AI 起草 · 原材料耗用说明' },
    'unit-consumption-conclusion': { title: 'AI 生成 · F2-64审计结论' },
  }
  const config = map[section]
  const existing = config.kind ? notes[config.kind] : auditConclusion.value
  const text = await generateAndConfirm(section, existing, aiContext(), config.title)
  if (!text) return
  if (config.kind) saveNote(config.kind, text)
  else saveConclusion(text)
}
</script>

<style scoped src="../../f2/valuation/f2ValSheetStyles.css"></style>
<style scoped src="./f2IpoSoftStyles.css"></style>
<style scoped>
.f2-unit-consumption {
  --uc-ink: #1f2937;
  --uc-muted: #6b7280;
  --uc-line: #e5e7eb;
  --uc-soft: #f8fafc;
  --uc-accent: #334155;
  --uc-accent-soft: #f1f5f9;
  --uc-calc: #eff6ff;
  --uc-calc-ink: #1d4ed8;
  font-size: var(--wp-font-size, 13px);
}

.uc-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 12px;
  padding: 14px 16px;
  border: 1px solid var(--uc-line);
  border-radius: 10px;
  background: linear-gradient(180deg, #fff 0%, var(--uc-soft) 100%);
}
.uc-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.uc-title-row h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 650;
  color: var(--uc-ink);
  letter-spacing: 0.01em;
}
.uc-code {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--uc-accent-soft);
  color: var(--uc-accent);
  font-size: 11px;
  font-weight: 600;
}
.uc-desc {
  margin: 6px 0 0;
  color: var(--uc-muted);
  font-size: 12px;
}
.uc-metrics {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.uc-metric {
  min-width: 88px;
  padding: 8px 12px;
  border: 1px solid var(--uc-line);
  border-radius: 8px;
  background: #fff;
  text-align: center;
}
.uc-metric.danger {
  border-color: #fecaca;
  background: #fff7f7;
}
.uc-metric.muted .uc-metric-val {
  font-size: 13px;
}
.uc-metric-val {
  display: block;
  font-size: 15px;
  font-weight: 700;
  color: var(--uc-ink);
  line-height: 1.2;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.uc-metric.danger .uc-metric-val {
  color: #b91c1c;
}
.uc-metric-label {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--uc-muted);
}

.uc-meta-card {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  align-items: end;
  margin: 10px 0 12px;
  padding: 12px 14px;
  border: 1px solid var(--uc-line);
  border-radius: 10px;
  background: #fff;
}
.uc-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 180px;
  flex: 1;
}
.uc-field.year {
  min-width: 96px;
  flex: 0 0 110px;
}
.uc-field > span,
.field-label {
  font-size: 11px;
  color: var(--uc-muted);
  font-weight: 500;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-left: auto;
}

.uc-nav {
  position: sticky;
  top: 0;
  z-index: 8;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  padding: 8px 10px;
  border: 1px solid var(--uc-line);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(8px);
}
.uc-section-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.uc-nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--uc-muted);
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.uc-nav-btn:hover {
  background: var(--uc-soft);
  color: var(--uc-ink);
}
.uc-nav-btn.active {
  background: var(--uc-accent-soft);
  border-color: #cbd5e1;
  color: var(--uc-ink);
  font-weight: 600;
}
.uc-nav-idx {
  font-size: 10px;
  font-weight: 700;
  color: #94a3b8;
  letter-spacing: 0.04em;
}
.uc-nav-btn.active .uc-nav-idx {
  color: #64748b;
}

.uc-card {
  margin: 0 0 14px;
  padding: 14px;
  border: 1px solid var(--uc-line);
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
  scroll-margin-top: 64px;
}
.uc-card-head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f1f5f9;
}
.uc-card-idx {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--uc-accent-soft);
  color: var(--uc-accent);
  font-size: 12px;
  font-weight: 700;
}
.uc-card-head h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 650;
  color: var(--uc-ink);
}
.uc-card-head p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--uc-muted);
}

.material-name-row,
.peer-name-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin: 0 0 10px;
}
.material-name-row :deep(.el-input),
.peer-name-row :deep(.el-input) {
  max-width: 160px;
}

.sub-panel {
  margin-top: 14px;
  padding: 12px;
  border: 1px dashed #dbe3ee;
  border-radius: 10px;
  background: #fbfdff;
}
.sub-title {
  margin: 0 0 8px;
  font-weight: 650;
  color: #334155;
  font-size: 13px;
}

.table-scroll {
  overflow-x: auto;
  max-width: 100%;
  border: 1px solid var(--uc-line);
  border-radius: 8px;
}
.matrix-table {
  width: 100%;
  min-width: 1000px;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 12px;
}
.structure-table {
  min-width: 1450px;
}
.unit-table {
  min-width: 1300px;
}
.material-table {
  min-width: 1250px;
}
.matrix-table th,
.matrix-table td {
  border-right: 1px solid #eef2f7;
  border-bottom: 1px solid #eef2f7;
  padding: 5px 6px;
  text-align: center;
  vertical-align: middle;
  background: #fff;
}
.matrix-table th:last-child,
.matrix-table td:last-child {
  border-right: none;
}
.matrix-table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #f8fafc;
  color: #475569;
  font-weight: 600;
  font-size: 11px;
  border-bottom: 1px solid #e2e8f0;
}
.matrix-table thead th.calc-head {
  background: #eff6ff;
  color: #1e40af;
}
.year-cell {
  min-width: 64px;
  background: #f8fafc !important;
  font-weight: 700;
  color: #334155;
}
.row-label {
  text-align: left !important;
  font-weight: 500;
  color: #334155;
  background: #fafbfc !important;
}
.calc-cell {
  background: var(--uc-calc) !important;
  color: var(--uc-calc-ink);
  text-align: right !important;
  white-space: nowrap;
  font-weight: 500;
}
.num {
  text-align: right !important;
  white-space: nowrap;
}
.row-total td {
  background: #f1f5f9 !important;
  font-weight: 700;
  color: #0f172a;
}

.inline-note {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid var(--uc-line);
  background: #fcfdff;
  border-radius: 8px;
}
.inline-note-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  color: #334155;
}
.inline-note textarea {
  width: 100%;
  min-height: 64px;
  resize: vertical;
  box-sizing: border-box;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 8px;
  font: inherit;
}

.opinion-card {
  margin-top: 8px;
  border-radius: 12px !important;
  border: 1px solid var(--uc-line) !important;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-weight: 650;
  color: var(--uc-ink);
}

:deep(.compact-num) {
  width: 78px;
}
:deep(.compact-num .el-input__inner) {
  text-align: right;
  padding: 0 3px;
  font-size: 12px;
}

@media (max-width: 1000px) {
  .uc-hero {
    flex-direction: column;
  }
  .toolbar-right {
    margin-left: 0;
    width: 100%;
    justify-content: flex-start;
  }
  .uc-nav {
    position: static;
  }
}
</style>
