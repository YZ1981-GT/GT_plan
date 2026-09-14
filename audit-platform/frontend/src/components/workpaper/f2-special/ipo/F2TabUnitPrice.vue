<template>
  <div class="f2-val-sheet f2-unit-price f2-ipo-soft">
    <header class="sheet-header">
      <div>
        <h3>原材料单价分析表</h3>
        <span class="code">F2-62 · 供应商/材料/规格三维交叉比较</span>
      </div>
      <div class="stat-row">
        <span class="stat">比较组 {{ up.filledGroupCount.value }}</span>
        <span class="stat sub">第一层采购额 {{ fmt(up.totalPurchaseAmount.value) }}</span>
        <el-tag v-if="up.abnormalCount.value" type="danger" size="small">
          异常 {{ up.abnormalCount.value }} 项
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 第一层固定同一供应商，比较其不同物料的逐月单价，识别同一交易对手对不同物料的异常定价。</p>
        <p>2. 第二层固定同一原材料，比较不同供应商的逐月单价，识别供应商间异常价差或利益输送。</p>
        <p>3. 第三层固定同类原材料，比较不同规格跨年度的数量、金额和采购单价，分析规格及年度价格差异。</p>
        <p>4. 只填写采购金额和数量，采购单价均由系统自动计算；组内平均价偏离或年度变动超过 ±20% 自动标红。</p>
      </div>
    </details>

    <el-alert type="info" :closable="false" :title="objectiveText" class="objective-alert" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly"
          @click="up.addMonthlyGroup('supplierGroups')">+ 供应商分析组</el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly"
          @click="up.addMonthlyGroup('materialGroups')">+ 原材料分析组</el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly"
          @click="up.addSpecGroup()">+ 规格分析组</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-62"
          :disabled="isReadonly"
          review-section="F2-62-price"
        />
        <GtIndexChip value="wp:F2-62" />
      </div>
    </div>

    <!-- 一、同一供应商/二、同一原材料：月份为行，对比对象为三列一组 -->
    <section
      v-for="section in monthlySections"
      :key="section.key"
      class="analysis-section"
    >
      <div class="major-title">
        <span>{{ section.order }}、{{ section.title }}</span>
        <el-button size="small" link type="primary" :disabled="isReadonly"
          @click="up.addMonthlyGroup(section.key)">新增{{ section.groupLabel }}组</el-button>
      </div>

      <el-card
        v-for="(group, groupIndex) in section.groups"
        :key="group.id"
        shadow="never"
        class="group-card"
      >
        <template #header>
          <div class="group-header">
            <div class="group-name">
              <span class="group-seq">{{ groupIndex + 1 }}</span>
              <span>{{ section.groupLabel }}：</span>
              <el-input
                v-if="!isReadonly"
                :model-value="group.name"
                size="small"
                class="group-name-input"
                :placeholder="`填写${section.groupLabel}名称`"
                @update:model-value="(v: string) => up.updateMonthlyGroup(section.key, group.id, { name: v })"
              />
              <strong v-else>{{ group.name || `未填写${section.groupLabel}` }}</strong>
              <el-tag v-if="group.abnormalCount" size="small" type="danger">
                {{ group.abnormalCount }} 项异常
              </el-tag>
            </div>
            <div class="group-actions">
              <el-button size="small" type="primary" plain :disabled="isReadonly"
                @click="up.addMonthlyItem(section.key, group.id)">+ {{ section.itemLabel }}</el-button>
              <el-button size="small" type="danger" plain :disabled="isReadonly || section.groups.length <= 1"
                @click="up.removeMonthlyGroup(section.key, group.id)">删除组</el-button>
            </div>
          </div>
        </template>

        <div class="table-scroll">
          <table class="compare-table" :style="{ minWidth: `${120 + group.items.length * 260}px` }">
            <thead>
              <tr>
                <th rowspan="2" class="sticky col-month">月份</th>
                <th v-for="item in group.items" :key="item.id" colspan="3" class="item-header">
                  <div class="item-header-content">
                    <el-input
                      v-if="!isReadonly"
                      :model-value="item.name"
                      size="small"
                      :placeholder="`填写${section.itemLabel}名称`"
                      @update:model-value="(v: string) => up.updateMonthlyItem(section.key, group.id, item.id, { name: v })"
                    />
                    <span v-else>{{ item.name || `未填写${section.itemLabel}` }}</span>
                    <el-button v-if="!isReadonly && group.items.length > 1" link type="danger" size="small"
                      @click="up.removeMonthlyItem(section.key, group.id, item.id)">删</el-button>
                  </div>
                </th>
              </tr>
              <tr>
                <template v-for="item in group.items" :key="`${item.id}-sub`">
                  <th>入库金额</th>
                  <th>入库数量</th>
                  <th class="calc-head">单价</th>
                </template>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(_, monthIndex) in monthLabels" :key="monthIndex">
                <td class="sticky col-month">{{ monthLabels[monthIndex] }}</td>
                <template v-for="item in group.items" :key="`${item.id}-${monthIndex}`">
                  <td>
                    <el-input-number v-if="!isReadonly"
                      :model-value="item.enrichedMonths[monthIndex].amount"
                      size="small" :controls="false" class="compact-num"
                      @change="(v: number | undefined) => up.updateMonth(section.key, group.id, item.id, monthIndex, { amount: v ?? 0 })" />
                    <span v-else class="num">{{ fmt(item.enrichedMonths[monthIndex].amount) }}</span>
                  </td>
                  <td>
                    <el-input-number v-if="!isReadonly"
                      :model-value="item.enrichedMonths[monthIndex].qty"
                      size="small" :controls="false" class="compact-num"
                      @change="(v: number | undefined) => up.updateMonth(section.key, group.id, item.id, monthIndex, { qty: v ?? 0 })" />
                    <span v-else class="num">{{ fmt(item.enrichedMonths[monthIndex].qty) }}</span>
                  </td>
                  <td class="calc-cell">{{ fmtPrice(item.enrichedMonths[monthIndex].unitPrice) }}</td>
                </template>
              </tr>
              <tr class="row-total">
                <td class="sticky col-month">合计</td>
                <template v-for="item in group.items" :key="`${item.id}-total`">
                  <td class="num">{{ fmt(item.totalAmount) }}</td>
                  <td class="num">{{ fmt(item.totalQty) }}</td>
                  <td class="calc-cell" :class="{ 'price-warn': item.isAbnormal }">
                    {{ fmtPrice(item.avgPrice) }}
                    <small v-if="item.groupDeviation !== null">
                      （{{ fmtRate(item.groupDeviation) }}）
                    </small>
                  </td>
                </template>
              </tr>
            </tbody>
          </table>
        </div>
      </el-card>
    </section>

    <!-- 三、同类原材料不同规格跨年度分析 -->
    <section class="analysis-section">
      <div class="major-title">
        <span>三、同一类原材料，不同规格材料采购单价分析</span>
        <el-button size="small" link type="primary" :disabled="isReadonly"
          @click="up.addSpecGroup()">新增类别组</el-button>
      </div>

      <el-card
        v-for="(group, groupIndex) in up.specGroups.value"
        :key="group.id"
        shadow="never"
        class="group-card"
      >
        <template #header>
          <div class="group-header">
            <div class="group-name">
              <span class="group-seq">{{ groupIndex + 1 }}</span>
              <span>原材料类别：</span>
              <el-input v-if="!isReadonly" :model-value="group.categoryName" size="small"
                class="group-name-input" placeholder="如：钢材、铜材"
                @update:model-value="(v: string) => up.updateSpecGroup(group.id, { categoryName: v })" />
              <strong v-else>{{ group.categoryName || '未填写类别' }}</strong>
              <el-tag v-if="group.abnormalCount" size="small" type="danger">
                {{ group.abnormalCount }} 项异常
              </el-tag>
            </div>
            <div class="group-actions">
              <el-button size="small" type="primary" plain :disabled="isReadonly"
                @click="up.addSpecItem(group.id)">+ 规格</el-button>
              <el-button size="small" type="danger" plain
                :disabled="isReadonly || up.specGroups.value.length <= 1"
                @click="up.removeSpecGroup(group.id)">删除组</el-button>
            </div>
          </div>
        </template>

        <div class="table-scroll">
          <table class="compare-table spec-table">
            <thead>
              <tr>
                <th rowspan="2" class="sticky col-spec">规格</th>
                <th v-for="period in periodLabels" :key="period" colspan="3">{{ period }}</th>
                <th rowspan="2" class="calc-head">本期较上期</th>
                <th rowspan="2" class="col-act" />
              </tr>
              <tr>
                <template v-for="period in periodLabels" :key="`${period}-sub`">
                  <th>数量</th>
                  <th>金额</th>
                  <th class="calc-head">采购单价</th>
                </template>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in group.items" :key="item.id" :class="{ 'row-error': item.isAbnormal }">
                <td class="sticky col-spec">
                  <el-input v-if="!isReadonly" :model-value="item.spec" size="small" placeholder="规格型号"
                    @update:model-value="(v: string) => up.updateSpecItem(group.id, item.id, { spec: v })" />
                  <span v-else>{{ item.spec || '—' }}</span>
                </td>
                <template v-for="(period, periodIndex) in item.periods" :key="`${item.id}-${periodIndex}`">
                  <td>
                    <el-input-number v-if="!isReadonly" :model-value="period.qty" size="small"
                      :controls="false" class="compact-num"
                      @change="(v: number | undefined) => up.updateSpecPeriod(group.id, item.id, periodIndex, { qty: v ?? 0 })" />
                    <span v-else class="num">{{ fmt(period.qty) }}</span>
                  </td>
                  <td>
                    <el-input-number v-if="!isReadonly" :model-value="period.amount" size="small"
                      :controls="false" class="compact-num"
                      @change="(v: number | undefined) => up.updateSpecPeriod(group.id, item.id, periodIndex, { amount: v ?? 0 })" />
                    <span v-else class="num">{{ fmt(period.amount) }}</span>
                  </td>
                  <td class="calc-cell">{{ fmtPrice(period.unitPrice) }}</td>
                </template>
                <td class="calc-cell" :class="{ 'price-warn': item.isAbnormal }">
                  {{ fmtRate(item.latestChangeRate) }}
                </td>
                <td class="col-act">
                  <el-button v-if="!isReadonly && group.items.length > 1" link type="danger" size="small"
                    @click="up.removeSpecItem(group.id, item.id)">删</el-button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </el-card>
    </section>

    <!-- 四、审计说明 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">四、审计说明</span>
          <el-button size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('unit-price-note')">AI 填写审计说明</el-button>
        </div>
      </template>
      <el-input v-model="up.auditNote.value" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }"
        placeholder="分别说明三个比较维度的执行范围、异常价格差异、管理层解释及核查结果…"
        :disabled="isReadonly" />
    </el-card>

    <!-- 五、分析结论 / 审计结论 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">五、分析结论（审计结论）</span>
          <el-button size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('unit-price-conclusion')">AI 生成分析结论</el-button>
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
import { computed, onMounted, ref, toRef, type Ref } from 'vue'
import { useF2UnitPrice, type MonthlySection } from '../../composables/useF2UnitPrice'
import {
  F2_62_FRAUD_TIP,
  F2_62_OBJECTIVE,
  UNIT_PRICE_MONTH_LABELS,
} from '../../composables/useF2UnitPriceFormulas'
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

const up = useF2UnitPrice({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const monthLabels = UNIT_PRICE_MONTH_LABELS
const periodLabels = ['本期', '上期', '上上期'] as const
const objectiveText = F2_62_OBJECTIVE
const fraudTip = F2_62_FRAUD_TIP

const monthlySections = computed(() => [
  {
    key: 'supplierGroups' as MonthlySection,
    order: '一',
    title: '同一供应商，采购不同物料单价分析',
    groupLabel: '供应商',
    itemLabel: '物料',
    groups: up.supplierGroups.value,
  },
  {
    key: 'materialGroups' as MonthlySection,
    order: '二',
    title: '同一原材料，在不同供应商处各月采购单价分析',
    groupLabel: '原材料',
    itemLabel: '供应商',
    groups: up.materialGroups.value,
  },
])

const CONCLUSION_KEY = 'F2-62-audit-conclusion'
const LEGACY_NOTE_KEY = 'F2-62-audit-note'
const auditConclusion = ref('')

function saveAuditConclusion(value: string): void {
  if (props.isReadonly) return
  auditConclusion.value = value
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: value }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}

onMounted(() => {
  const conclusion = props.allResponses.get(CONCLUSION_KEY)
  if (conclusion?.remark) auditConclusion.value = conclusion.remark
  // 旧页面第二个“审计说明”迁入新版第四部分，避免历史文本丢失。
  const legacyNote = props.allResponses.get(LEGACY_NOTE_KEY)?.remark
  if (!up.auditNote.value && legacyNote) up.auditNote.value = legacyNote
})

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const {
  aiAvailable,
  loading: aiLoading,
  generateAndConfirm,
} = useF2SpecialAiGenerate(wpIdRef)

function aiContext(): Record<string, unknown> {
  const monthly = (groups: typeof up.supplierGroups.value) =>
    groups.slice(0, 10).map((group) => ({
      groupName: group.name,
      groupAvgPrice: group.avgPrice,
      abnormalCount: group.abnormalCount,
      items: group.items.slice(0, 10).map((item) => ({
        name: item.name,
        totalAmount: item.totalAmount,
        totalQty: item.totalQty,
        avgPrice: item.avgPrice,
        groupDeviation: item.groupDeviation,
      })),
    }))
  return {
    sheet: 'F2-62',
    comparisonGroupCount: up.filledGroupCount.value,
    abnormalCount: up.abnormalCount.value,
    totalPurchaseAmount: up.totalPurchaseAmount.value,
    supplierDimension: monthly(up.supplierGroups.value),
    materialDimension: monthly(up.materialGroups.value),
    specificationDimension: up.specGroups.value.slice(0, 10).map((group) => ({
      categoryName: group.categoryName,
      abnormalCount: group.abnormalCount,
      items: group.items.map((item) => ({
        spec: item.spec,
        prices: item.periods.map((period) => ({
          period: period.label,
          unitPrice: period.unitPrice,
        })),
        latestChangeRate: item.latestChangeRate,
      })),
    })),
  }
}

async function runAi(section: F2SpeAiSection): Promise<void> {
  const isNote = section === 'unit-price-note'
  const existing = isNote ? up.auditNote.value : auditConclusion.value
  const title = isNote ? 'AI 生成 · 原材料单价审计说明' : 'AI 生成 · 原材料单价分析结论'
  const text = await generateAndConfirm(section, existing || '', aiContext(), title)
  if (!text) return
  if (isNote) up.auditNote.value = text
  else saveAuditConclusion(text)
}

function fmt(value: number): string {
  if (!Number.isFinite(value) || value === 0) return '—'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPrice(value: number | null): string {
  if (value === null || !Number.isFinite(value) || value === 0) return '—'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

function fmtRate(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(1)}%`
}
</script>

<style scoped src="../../f2/valuation/f2ValSheetStyles.css"></style>
<style scoped src="./f2IpoSoftStyles.css"></style>
<style scoped>
.f2-unit-price { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }

.analysis-section { margin: 18px 0; }
.major-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: linear-gradient(90deg, #ede5f5, #faf8fc);
  border-left: 4px solid var(--gt-purple);
  color: #3f2465;
  font-size: 14px;
  font-weight: 700;
}
.group-card { margin-bottom: 12px; border-color: #d8cce5; }
.group-card :deep(.el-card__header) { padding: 8px 12px; background: #faf8fc; }
.group-card :deep(.el-card__body) { padding: 0; }
.group-header, .group-name, .group-actions, .item-header-content {
  display: flex;
  align-items: center;
  gap: 8px;
}
.group-header { justify-content: space-between; flex-wrap: wrap; }
.group-seq {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--gt-purple);
  color: #fff;
  font-size: 12px;
}
.group-name-input { width: 220px; }
.group-actions { margin-left: auto; }
.item-header-content { justify-content: center; min-width: 220px; }
.item-header-content :deep(.el-input) { max-width: 180px; }

.table-scroll { overflow-x: auto; max-width: 100%; }
.compare-table {
  width: 100%;
  min-width: 900px;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 11px;
}
.compare-table th,
.compare-table td {
  border: 1px solid #d4c8e0;
  padding: 4px;
  text-align: center;
  vertical-align: middle;
  background: #fff;
}
.compare-table thead th {
  background: var(--gt-purple);
  color: #fff;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 2;
}
.compare-table thead th.calc-head { background: #6b4d8f; }
.item-header { background: #55347f !important; min-width: 240px; }
.sticky { position: sticky; left: 0; z-index: 3; background: #faf8fc !important; }
.compare-table thead th.sticky { background: var(--gt-purple) !important; z-index: 4; }
.col-month { width: 70px; min-width: 70px; font-weight: 600; }
.col-spec { width: 110px; min-width: 110px; text-align: left !important; }
.col-act { width: 38px; min-width: 38px; }
.calc-cell {
  color: #4b2d77;
  font-weight: 500;
  background: #faf8fc !important;
  text-align: right !important;
  white-space: nowrap;
}
.calc-cell small { display: block; color: #909399; font-size: 9px; }
.num { display: block; text-align: right; white-space: nowrap; }
.row-total td { background: #f0ebf5 !important; font-weight: 600; }
.row-error td { background: #fef0f0 !important; }
.price-warn { color: #c45656 !important; font-weight: 700; background: #fef0f0 !important; }
.spec-table { min-width: 1100px; }

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

:deep(.compact-num) { width: 76px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 4px; font-size: 11px; }
</style>
