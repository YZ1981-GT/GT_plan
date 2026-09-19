<template>
  <div class="f2-val-sheet f2-purchase-price f2-ipo-soft">
    <header class="uc-hero">
      <div class="uc-hero-text">
        <div class="uc-title-row">
          <h3>原材料采购价格分析表</h3>
          <span class="uc-code">F2-61</span>
        </div>
        <p class="uc-desc">报告期逐月采购金额、数量、单价比较</p>
      </div>
      <div class="uc-metrics">
        <div class="uc-metric">
          <span class="uc-metric-val">{{ fmt(pp.columnTotals.value.currentTotalAmount) }}</span>
          <span class="uc-metric-label">本期采购金额</span>
        </div>
        <div class="uc-metric">
          <span class="uc-metric-val">{{ fmtPrice(pp.columnTotals.value.currentAvgPrice) }}</span>
          <span class="uc-metric-label">本期平均单价</span>
        </div>
        <div v-if="pp.varianceCount.value" class="uc-metric warn">
          <span class="uc-metric-val">{{ pp.varianceCount.value }}</span>
          <span class="uc-metric-label">单价波动</span>
        </div>
        <div v-if="pp.marketDiffCount.value" class="uc-metric danger">
          <span class="uc-metric-val">{{ pp.marketDiffCount.value }}</span>
          <span class="uc-metric-label">偏离市场价</span>
        </div>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 按材料逐月填写「入库金额」与「入库数量」，入库单价 = 金额 ÷ 数量 自动计算（灰底列不可编辑）。</p>
        <p>2. 「市场单价」逐月手工录入（询价/行情数据），本期平均市场单价自动按已填月份平均。</p>
        <p>3. 月度单价偏离本期平均 ±30% 标黄，须在「审计说明1」解释；采购均价与市场均价差异 ±10% 标红，须在「审计说明2」解释。</p>
        <p>4. 上期末、上期合计金额/数量为对比手工列，上期平均单价自动 = 上期合计金额 ÷ 上期合计数量。</p>
      </div>
    </details>

    <el-alert type="info" :closable="false" :title="objectiveText" class="objective-alert" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="pp.addMaterial()">+ 材料</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-61"
          :disabled="isReadonly"
          review-section="F2-61-price"
        />
        <GtIndexChip value="wp:F2-61" />
        <el-tag size="small" type="info">{{ pp.filledCount.value }} 种材料</el-tag>
      </div>
    </div>

    <div class="uc-nav">
      <nav class="uc-section-nav" aria-label="区块导航">
        <button
          v-for="sec in sections"
          :key="sec.key"
          type="button"
          class="uc-nav-btn"
          :class="{ active: activeSection === sec.key }"
          @click="scrollToSection(sec.key)"
        >
          <span class="uc-nav-idx">{{ sec.badge }}</span>
          {{ sec.navLabel }}
        </button>
      </nav>
    </div>

    <section
      v-for="sec in sections"
      :id="`pp-${sec.key}`"
      :key="sec.key"
      class="uc-card matrix-section"
    >
      <header class="uc-card-head">
        <span class="uc-card-idx">{{ sec.badge }}</span>
        <div>
          <h4>{{ sec.title }}</h4>
          <p v-if="sec.hint">{{ sec.hint }}</p>
        </div>
      </header>
      <div class="table-scroll">
        <table class="matrix-table">
          <thead>
            <tr>
              <th class="sticky col-name">主要原材料/月份</th>
              <th v-for="(lab, mi) in monthLabels" :key="mi">{{ lab }}</th>
              <th>上期末</th>
              <th :class="{ 'calc-col': sec.totalCalc }">{{ sec.totalLabel }}</th>
              <th :class="{ 'calc-col': sec.priorTotalCalc }">{{ sec.priorTotalLabel }}</th>
              <th class="col-act" />
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in pp.enrichedMaterials.value"
              :key="row.id"
              :class="{ 'row-warn': sec.key === 'price' && row.hasMonthlyVariance, 'row-error': sec.key === 'market' && row.hasMarketDiff }"
            >
              <td class="sticky col-name">
                <template v-if="sec.key === 'amount'">
                  <el-input v-if="!isReadonly" :model-value="row.materialName" size="small"
                    placeholder="材料名称"
                    @update:model-value="(v: string) => pp.updateMaterial(row.id, { materialName: v })" />
                  <span v-else>{{ row.materialName || '—' }}</span>
                </template>
                <template v-else-if="sec.key === 'qty'">
                  <span class="name-with-unit">
                    <span class="name-text">{{ row.materialName || '—' }}</span>
                    <el-input v-if="!isReadonly" :model-value="row.unit" size="small" class="unit-input"
                      placeholder="单位"
                      @update:model-value="(v: string) => pp.updateMaterial(row.id, { unit: v })" />
                    <span v-else-if="row.unit" class="unit-text">（{{ row.unit }}）</span>
                  </span>
                </template>
                <template v-else>
                  <span class="name-text">{{ row.materialName || '—' }}</span>
                </template>
              </td>

              <!-- 逐月单元格 -->
              <td v-for="(m, mi) in row.enrichedMonths" :key="mi"
                :class="sec.key === 'price' ? ['auto', 'calc', { 'price-warn': m.priceAbnormal }] : undefined">
                <template v-if="sec.key === 'amount'">
                  <el-input-number v-if="!isReadonly" :model-value="m.amount" size="small" :controls="false"
                    class="compact-num"
                    @change="(v: number | undefined) => pp.updateMonth(row.id, mi, { amount: v ?? 0 })" />
                  <span v-else class="auto">{{ fmt(m.amount) }}</span>
                </template>
                <template v-else-if="sec.key === 'qty'">
                  <el-input-number v-if="!isReadonly" :model-value="m.qty" size="small" :controls="false"
                    class="compact-num"
                    @change="(v: number | undefined) => pp.updateMonth(row.id, mi, { qty: v ?? 0 })" />
                  <span v-else class="auto">{{ fmt(m.qty) }}</span>
                </template>
                <template v-else-if="sec.key === 'price'">
                  {{ fmtPrice(m.unitPrice) }}
                </template>
                <template v-else>
                  <el-input-number v-if="!isReadonly" :model-value="m.marketPrice" size="small" :controls="false"
                    class="compact-num"
                    @change="(v: number | undefined) => pp.updateMonth(row.id, mi, { marketPrice: v ?? 0 })" />
                  <span v-else class="auto">{{ fmtPrice(m.marketPrice || null) }}</span>
                </template>
              </td>

              <!-- 上期末 -->
              <td :class="sec.key === 'price' ? ['auto', 'calc'] : undefined">
                <template v-if="sec.key === 'amount'">
                  <el-input-number v-if="!isReadonly" :model-value="row.priorEnd.amount" size="small" :controls="false"
                    class="compact-num"
                    @change="(v: number | undefined) => pp.updatePriorEnd(row.id, { amount: v ?? 0 })" />
                  <span v-else class="auto">{{ fmt(row.priorEnd.amount) }}</span>
                </template>
                <template v-else-if="sec.key === 'qty'">
                  <el-input-number v-if="!isReadonly" :model-value="row.priorEnd.qty" size="small" :controls="false"
                    class="compact-num"
                    @change="(v: number | undefined) => pp.updatePriorEnd(row.id, { qty: v ?? 0 })" />
                  <span v-else class="auto">{{ fmt(row.priorEnd.qty) }}</span>
                </template>
                <template v-else-if="sec.key === 'price'">
                  {{ fmtPrice(row.priorEndUnitPrice) }}
                </template>
                <template v-else>
                  <el-input-number v-if="!isReadonly" :model-value="row.priorEnd.marketPrice" size="small" :controls="false"
                    class="compact-num"
                    @change="(v: number | undefined) => pp.updatePriorEnd(row.id, { marketPrice: v ?? 0 })" />
                  <span v-else class="auto">{{ fmtPrice(row.priorEnd.marketPrice || null) }}</span>
                </template>
              </td>

              <!-- 本期合计 / 平均 -->
              <td :class="sec.totalCalc ? ['auto', 'calc', 'calc-col'] : undefined">
                <template v-if="sec.key === 'amount'">{{ fmt(row.currentTotalAmount) }}</template>
                <template v-else-if="sec.key === 'qty'">{{ fmt(row.currentTotalQty) }}</template>
                <template v-else-if="sec.key === 'price'">{{ fmtPrice(row.currentAvgPrice) }}</template>
                <template v-else>
                  <span class="auto calc" :class="{ 'diff-warn': row.hasMarketDiff }">
                    {{ fmtPrice(row.currentAvgMarketPrice) }}
                  </span>
                </template>
              </td>

              <!-- 上期合计 / 平均 -->
              <td :class="sec.priorTotalCalc ? ['auto', 'calc', 'calc-col'] : undefined">
                <template v-if="sec.key === 'amount'">
                  <el-input-number v-if="!isReadonly" :model-value="row.priorTotalAmount" size="small" :controls="false"
                    class="compact-num"
                    @change="(v: number | undefined) => pp.updateMaterial(row.id, { priorTotalAmount: v ?? 0 })" />
                  <span v-else class="auto">{{ fmt(row.priorTotalAmount) }}</span>
                </template>
                <template v-else-if="sec.key === 'qty'">
                  <el-input-number v-if="!isReadonly" :model-value="row.priorTotalQty" size="small" :controls="false"
                    class="compact-num"
                    @change="(v: number | undefined) => pp.updateMaterial(row.id, { priorTotalQty: v ?? 0 })" />
                  <span v-else class="auto">{{ fmt(row.priorTotalQty) }}</span>
                </template>
                <template v-else-if="sec.key === 'price'">{{ fmtPrice(row.priorAvgPrice) }}</template>
                <template v-else>
                  <el-input-number v-if="!isReadonly" :model-value="row.priorAvgMarketPrice" size="small" :controls="false"
                    class="compact-num"
                    @change="(v: number | undefined) => pp.updateMaterial(row.id, { priorAvgMarketPrice: v ?? 0 })" />
                  <span v-else class="auto">{{ fmtPrice(row.priorAvgMarketPrice || null) }}</span>
                </template>
              </td>

              <td class="col-act">
                <el-button v-if="!isReadonly && sec.key === 'amount'" link type="danger" size="small"
                  @click="pp.removeMaterial(row.id)">删</el-button>
              </td>
            </tr>

            <!-- 小计 -->
            <tr class="row-total">
              <td class="sticky col-name">小计</td>
              <td v-for="(_, mi) in monthLabels" :key="mi" class="auto">
                <template v-if="sec.key === 'amount'">{{ fmt(pp.columnTotals.value.monthAmounts[mi]) }}</template>
                <template v-else-if="sec.key === 'qty'">{{ fmt(pp.columnTotals.value.monthQtys[mi]) }}</template>
                <template v-else-if="sec.key === 'price'">{{ fmtPrice(pp.columnTotals.value.monthUnitPrices[mi]) }}</template>
                <template v-else>{{ fmtPrice(pp.columnTotals.value.monthMarketAvgs[mi]) }}</template>
              </td>
              <td class="auto">
                <template v-if="sec.key === 'amount'">{{ fmt(pp.columnTotals.value.priorEndAmount) }}</template>
                <template v-else-if="sec.key === 'qty'">{{ fmt(pp.columnTotals.value.priorEndQty) }}</template>
                <template v-else>—</template>
              </td>
              <td class="auto calc">
                <template v-if="sec.key === 'amount'">{{ fmt(pp.columnTotals.value.currentTotalAmount) }}</template>
                <template v-else-if="sec.key === 'qty'">{{ fmt(pp.columnTotals.value.currentTotalQty) }}</template>
                <template v-else-if="sec.key === 'price'">{{ fmtPrice(pp.columnTotals.value.currentAvgPrice) }}</template>
                <template v-else>—</template>
              </td>
              <td class="auto calc">
                <template v-if="sec.key === 'amount'">{{ fmt(pp.columnTotals.value.priorTotalAmount) }}</template>
                <template v-else-if="sec.key === 'qty'">{{ fmt(pp.columnTotals.value.priorTotalQty) }}</template>
                <template v-else-if="sec.key === 'price'">{{ fmtPrice(pp.columnTotals.value.priorAvgPrice) }}</template>
                <template v-else>—</template>
              </td>
              <td />
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 1、审计说明 -->
    <el-card class="opinion-card" shadow="never">
      <template #header><span class="opinion-title">1、审计说明</span></template>
      <div class="note-block">
        <div class="note-label">
          <span>1. 原材料——××月采购单价变动较大的原因：</span>
          <el-button size="small" type="primary" plain link
            :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('purchase-price-variance-note')">AI</el-button>
        </div>
        <el-input v-model="pp.varianceNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
          placeholder="指出单价波动异常的材料及月份，说明波动原因与核查过程…" :disabled="isReadonly" />
      </div>
      <div class="note-block">
        <div class="note-label">
          <span>2. 原材料——采购单价与市场价格差异较大原因：</span>
          <el-button size="small" type="primary" plain link
            :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('purchase-price-market-note')">AI</el-button>
        </div>
        <el-input v-model="pp.marketNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
          placeholder="说明采购价与市场价差异的方向、幅度、管理层解释及核查情况…" :disabled="isReadonly" />
      </div>
    </el-card>

    <!-- 2、审计结论 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">2、审计结论</span>
          <el-button size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('purchase-price-conclusion')">AI 生成结论</el-button>
        </div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="A、未见异常。B、除上述应调整事项外，其余未见异常。C、不可确认。"
        :disabled="isReadonly" @update:model-value="saveAuditConclusion" />
    </el-card>

    <div class="tips-box">
      <div class="tips-title">提示</div>
      <p>{{ fraudTip }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, toRef, type Ref } from 'vue'
import { useF2PurchasePrice, PURCHASE_MONTH_LABELS } from '../../composables/useF2PurchasePrice'
import { F2_61_OBJECTIVE, F2_61_FRAUD_TIP, isBlankPurchaseMaterial } from '../../composables/useF2PurchasePriceFormulas'
import {
  useF2SpecialAiGenerate,
  type F2SpeAiSection,
} from '../../composables/useF2SpecialAiGenerate'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const pp = useF2PurchasePrice({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const monthLabels = PURCHASE_MONTH_LABELS
const objectiveText = F2_61_OBJECTIVE
const fraudTip = F2_61_FRAUD_TIP
const activeSection = ref('amount')

const sections = [
  {
    key: 'amount', badge: '01', navLabel: '入库金额', title: '入库金额（单位：元）', hint: '本期合计金额自动 = Σ各月',
    totalLabel: '本期合计金额', priorTotalLabel: '上期合计金额', totalCalc: true, priorTotalCalc: false,
  },
  {
    key: 'qty', badge: '02', navLabel: '入库数量', title: '入库数量', hint: '数量单位在材料列填写',
    totalLabel: '本期合计数量', priorTotalLabel: '上期合计数量', totalCalc: true, priorTotalCalc: false,
  },
  {
    key: 'price', badge: '03', navLabel: '入库单价', title: '入库单价（单位：元）', hint: '全自动 = 金额 ÷ 数量',
    totalLabel: '本期平均单价', priorTotalLabel: '上期平均单价', totalCalc: true, priorTotalCalc: true,
  },
  {
    key: 'market', badge: '04', navLabel: '市场单价', title: '市场单价（单位：元）', hint: '逐月手工录入询价/行情数据',
    totalLabel: '本期平均单价', priorTotalLabel: '上期平均单价', totalCalc: true, priorTotalCalc: false,
  },
] as const

function scrollToSection(key: string) {
  activeSection.value = key
  document.getElementById(`pp-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const CONCLUSION_KEY = 'F2-61-audit-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}

let sectionObserver: IntersectionObserver | null = null
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark

  sectionObserver = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((e) => e.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
      const id = visible?.target?.id?.replace(/^pp-/, '')
      if (id) activeSection.value = id
    },
    { rootMargin: '-20% 0px -55% 0px', threshold: [0.1, 0.35, 0.6] },
  )
  for (const sec of sections) {
    const el = document.getElementById(`pp-${sec.key}`)
    if (el) sectionObserver.observe(el)
  }
})
onUnmounted(() => {
  sectionObserver?.disconnect()
  sectionObserver = null
})

// ─── AI ────────────────────────────────────────────────────────────
const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const {
  aiAvailable,
  loading: aiLoading,
  generateAndConfirm,
} = useF2SpecialAiGenerate(wpIdRef)

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-61',
    materialCount: pp.filledCount.value,
    currentTotalAmount: pp.columnTotals.value.currentTotalAmount,
    currentAvgPrice: pp.columnTotals.value.currentAvgPrice,
    priorAvgPrice: pp.columnTotals.value.priorAvgPrice,
    varianceCount: pp.varianceCount.value,
    marketDiffCount: pp.marketDiffCount.value,
    materials: pp.enrichedMaterials.value
      .filter((row) => !isBlankPurchaseMaterial(row))
      .slice(0, 20)
      .map((row) => ({
        materialName: row.materialName,
        unit: row.unit,
        currentTotalAmount: row.currentTotalAmount,
        currentTotalQty: row.currentTotalQty,
        currentAvgPrice: row.currentAvgPrice,
        priorAvgPrice: row.priorAvgPrice,
        currentAvgMarketPrice: row.currentAvgMarketPrice,
        marketDiffRate: row.marketDiffRate,
        abnormalMonths: row.enrichedMonths
          .filter((m) => m.priceAbnormal)
          .map((m) => ({ month: m.monthIndex + 1, unitPrice: m.unitPrice })),
      })),
  }
}

const AI_TARGETS: Partial<Record<F2SpeAiSection, {
  title: string
  get: () => string
  set: (t: string) => void
}>> = {
  'purchase-price-variance-note': {
    title: 'AI 生成 · 单价变动原因说明',
    get: () => pp.varianceNote.value,
    set: (t) => { pp.varianceNote.value = t },
  },
  'purchase-price-market-note': {
    title: 'AI 生成 · 市场价差异原因说明',
    get: () => pp.marketNote.value,
    set: (t) => { pp.marketNote.value = t },
  },
  'purchase-price-conclusion': {
    title: 'AI 生成 · 采购价格分析结论',
    get: () => auditConclusion.value,
    set: (t) => saveAuditConclusion(t),
  },
}

async function runAi(section: F2SpeAiSection): Promise<void> {
  const target = AI_TARGETS[section]
  if (!target) return
  const text = await generateAndConfirm(section, target.get() || '', aiContext(), target.title)
  if (text) target.set(text)
}

function fmt(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPrice(v: number | null): string {
  if (v === null || !Number.isFinite(v) || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}
</script>

<style scoped src="../../f2/valuation/f2ValSheetStyles.css"></style>
<style scoped src="./f2IpoSoftStyles.css"></style>
<style scoped>
.f2-purchase-price { font-size: var(--wp-font-size, 13px); }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.matrix-section { margin-bottom: 0; }
.table-scroll { overflow-x: auto; }
.matrix-table {
  width: 100%;
  font-size: 11px;
  min-width: 1500px;
}
.matrix-table th,
.matrix-table td {
  padding: 3px 4px;
  text-align: center;
  vertical-align: middle;
  background: #fff;
}
.matrix-table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  white-space: nowrap;
  font-size: 10px;
  line-height: 1.3;
  font-weight: 600;
}
.sticky { position: sticky; z-index: 3; }
.matrix-table thead th.sticky { z-index: 4; }
.col-name {
  left: 0;
  min-width: 120px;
  text-align: left !important;
  padding-left: 6px !important;
  box-shadow: 2px 0 4px rgba(15, 23, 42, 0.06);
}
.col-act { width: 32px; position: sticky; right: 0; z-index: 3; background: #fff !important; }
.row-warn td { background: #fdf6ec !important; }
.row-error td { background: #fef0f0 !important; }
.auto { text-align: right; padding-right: 2px; white-space: nowrap; color: #606266; }
span.auto { display: block; }
.calc { color: #1d4ed8; font-weight: 500; background: #eff6ff !important; }
.price-warn { color: #e6a23c; font-weight: 600; background: #fdf6ec !important; }
.diff-warn { color: #c45656; font-weight: 600; }
.name-with-unit { display: flex; align-items: center; gap: 4px; }
.name-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.unit-input { width: 56px; flex-shrink: 0; }
.unit-text { color: #909399; }
.note-block { margin-bottom: 12px; }
.note-block:last-child { margin-bottom: 0; }
.note-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: #303133;
  margin-bottom: 4px;
}
.tips-box {
  margin-top: 16px;
  padding: 12px 16px;
  background: #ecf5ff;
  border-left: 3px solid #409eff;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.7;
}
.tips-title { font-weight: 600; color: #409eff; margin-bottom: 6px; }
.tips-box p { margin: 0; }
:deep(.compact-num) { width: 74px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 4px; font-size: 11px; }
</style>
