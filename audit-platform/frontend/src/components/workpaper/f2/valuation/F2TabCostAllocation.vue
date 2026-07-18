<template>
  <div class="f2-val-sheet f2-allocation">
    <header class="sheet-header">
      <div>
        <h3>抽查×月×车间生产成本分配表</h3>
        <span class="code">F2-44</span>
      </div>
      <div class="stat-row">
        <span class="stat">成本池合计 {{ fmt(ca.poolTotal.value) }}</span>
        <span class="stat sub">分配合计 {{ fmt(ca.allocGrandTotal.value) }}</span>
        <el-tag v-if="ca.allocationMismatch.value" type="danger" size="small">分配与成本池不一致</el-tag>
        <el-tag v-if="ca.verifyFailCount.value" type="warning" size="small">
          单价核对异常 {{ ca.verifyFailCount.value }} 项
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 上部录入抽查月份、车间及本期发生成本（直接材料、直接人工、制造费用、其他），可与 F2-41/42/43 联动取数。</p>
        <p>2. 各产品录入产量、入库单价（账面）及分配标准（产量、工时、定额成本等），系统按分配标准占比自动计算分配率与分配额。</p>
        <p>3. 应计单位成本 = 各成本要素分配额合计 ÷ 产量；核对列比较应计单价与账面入库单价。</p>
        <p>4. 分配合计应与上部成本池合计勾稽一致，差异 &gt; 0.01 自动提示复核分配基准。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      :title="objectiveText"
      class="objective-alert"
    />

    <!-- 抽查月份 / 车间 -->
    <div class="meta-row">
      <label>
        抽查月份
        <el-input
          :model-value="ca.sheet.value.sampleMonth"
          size="small"
          :disabled="isReadonly"
          placeholder="如：12月"
          @update:model-value="(v: string) => ca.updateSheet({ sampleMonth: v })"
        />
      </label>
      <label>
        车间
        <el-input
          :model-value="ca.sheet.value.workshop"
          size="small"
          :disabled="isReadonly"
          placeholder="如：一车间"
          @update:model-value="(v: string) => ca.updateSheet({ workshop: v })"
        />
      </label>
    </div>

    <!-- 来源底稿联动 -->
    <div class="source-bar">
      <el-checkbox
        :model-value="ca.sheet.value.pool.linkSource"
        :disabled="isReadonly"
        @change="(v) => ca.updatePool({ linkSource: !!v })"
      >
        联动来源底稿
      </el-checkbox>
      <GtIndexChip value="wp:F2-41" />
      <GtIndexChip value="wp:F2-42" />
      <GtIndexChip value="wp:F2-43" />
      <span class="source-nums">
        材料 {{ fmt(ca.sourceTotals.value.material) }}
        | 人工 {{ fmt(ca.sourceTotals.value.labor) }}
        | 制造费用 {{ fmt(ca.sourceTotals.value.overhead) }}
      </span>
    </div>

    <!-- 本期发生成本 -->
    <div class="section-label">本期发生成本</div>
    <table class="pool-table">
      <thead>
        <tr>
          <th>直接材料</th>
          <th>直接人工</th>
          <th>制造费用</th>
          <th>其他</th>
          <th>合计</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>
            <el-input-number
              :model-value="ca.activePool.value.material"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              class="compact-num pool-num"
              @change="(v: number | undefined) => ca.updatePool({ material: v ?? 0, linkSource: false })"
            />
          </td>
          <td>
            <el-input-number
              :model-value="ca.activePool.value.labor"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              class="compact-num pool-num"
              @change="(v: number | undefined) => ca.updatePool({ labor: v ?? 0, linkSource: false })"
            />
          </td>
          <td>
            <el-input-number
              :model-value="ca.activePool.value.overhead"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              class="compact-num pool-num"
              @change="(v: number | undefined) => ca.updatePool({ overhead: v ?? 0, linkSource: false })"
            />
          </td>
          <td>
            <el-input-number
              :model-value="ca.activePool.value.other"
              size="small"
              :controls="false"
              :disabled="isReadonly"
              class="compact-num pool-num"
              @change="(v: number | undefined) => ca.updatePool({ other: v ?? 0 })"
            />
          </td>
          <td class="auto pool-total">{{ fmt(ca.poolTotal.value) }}</td>
        </tr>
      </tbody>
    </table>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="ca.addProduct()">+ 产品</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-44"
          :disabled="isReadonly"
          review-section="F2-44-conclusion"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-44" /></span>
        <el-tag size="small" type="info">{{ ca.enrichedProducts.value.length }} 个产品</el-tag>
      </div>
    </div>

    <!-- 产品分配宽表 -->
    <div class="table-scroll">
      <table class="matrix-table alloc-table">
        <thead>
          <tr>
            <th rowspan="2" class="col-name">产品品名</th>
            <th rowspan="2" class="col-qty">产量</th>
            <th rowspan="2" class="col-book">入库产品<br>成本单价</th>
            <th rowspan="2" class="col-base">分配标准</th>
            <th colspan="2">直接材料</th>
            <th colspan="2">直接人工</th>
            <th colspan="2">制造费用</th>
            <th colspan="2">其他</th>
            <th rowspan="2" class="col-accrued">应计<br>单位成本</th>
            <th rowspan="2" class="col-verify">核对</th>
            <th rowspan="2" class="col-act" />
          </tr>
          <tr>
            <th class="sub">分配率</th>
            <th class="sub">分配额</th>
            <th class="sub">分配率</th>
            <th class="sub">分配额</th>
            <th class="sub">分配率</th>
            <th class="sub">分配额</th>
            <th class="sub">分配率</th>
            <th class="sub">分配额</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in ca.enrichedProducts.value"
            :key="row.id"
            :class="{ 'row-warn': !row.verifyOk && row.verify !== '—' }"
          >
            <td class="col-name">
              <el-input
                v-if="!isReadonly"
                :model-value="row.productName"
                size="small"
                @update:model-value="(v: string) => ca.updateProduct(row.id, { productName: v })"
              />
              <span v-else>{{ row.productName || '—' }}</span>
            </td>
            <td>
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.outputQty"
                size="small"
                :controls="false"
                class="compact-num"
                @change="(v: number | undefined) => ca.updateProduct(row.id, { outputQty: v ?? 0 })"
              />
              <span v-else class="auto">{{ fmtQty(row.outputQty) }}</span>
            </td>
            <td>
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.bookUnitCost"
                size="small"
                :controls="false"
                :precision="4"
                class="compact-num"
                @change="(v: number | undefined) => ca.updateProduct(row.id, { bookUnitCost: v ?? 0 })"
              />
              <span v-else class="auto">{{ fmtUnit(row.bookUnitCost) }}</span>
            </td>
            <td>
              <div v-if="!isReadonly" class="base-cell">
                <el-input-number
                  :model-value="row.allocationBase"
                  size="small"
                  :controls="false"
                  class="compact-num"
                  @change="(v: number | undefined) => ca.updateProduct(row.id, { allocationBase: v ?? 0 })"
                />
                <el-input
                  :model-value="row.baseNote"
                  size="small"
                  placeholder="产量/工时等"
                  @update:model-value="(v: string) => ca.updateProduct(row.id, { baseNote: v })"
                />
              </div>
              <span v-else class="auto">
                {{ fmtQty(row.allocationBase) }}
                <span v-if="row.baseNote" class="base-note">({{ row.baseNote }})</span>
              </span>
            </td>
            <td class="auto rate">{{ fmtRate(row.materialRate) }}</td>
            <td class="auto">{{ fmt(row.materialAmt) }}</td>
            <td class="auto rate">{{ fmtRate(row.laborRate) }}</td>
            <td class="auto">{{ fmt(row.laborAmt) }}</td>
            <td class="auto rate">{{ fmtRate(row.overheadRate) }}</td>
            <td class="auto">{{ fmt(row.overheadAmt) }}</td>
            <td class="auto rate">{{ fmtRate(row.otherRate) }}</td>
            <td class="auto">{{ fmt(row.otherAmt) }}</td>
            <td class="auto col-accrued">{{ fmtUnit(row.accruedUnitCost) }}</td>
            <td class="col-verify" :class="row.verifyOk ? 'verify-ok' : 'verify-fail'">{{ row.verify }}</td>
            <td class="col-act">
              <el-button
                v-if="!isReadonly"
                link
                type="danger"
                size="small"
                :disabled="ca.enrichedProducts.value.length <= 1 && isBlankAllocationProduct(row)"
                @click.stop="ca.removeProduct(row.id)"
              >删</el-button>
            </td>
          </tr>
          <tr class="row-total">
            <td class="col-name">合计</td>
            <td class="auto">{{ fmtQty(ca.columnTotals.value.outputQty) }}</td>
            <td />
            <td />
            <td />
            <td class="auto">{{ fmt(ca.columnTotals.value.materialAmt) }}</td>
            <td />
            <td class="auto">{{ fmt(ca.columnTotals.value.laborAmt) }}</td>
            <td />
            <td class="auto">{{ fmt(ca.columnTotals.value.overheadAmt) }}</td>
            <td />
            <td class="auto">{{ fmt(ca.columnTotals.value.otherAmt) }}</td>
            <td />
            <td />
            <td />
          </tr>
        </tbody>
      </table>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">1、审计说明</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('allocation-note')"
          >AI 填写审计说明</el-button>
        </div>
      </template>
      <el-input
        v-model="ca.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="说明分配基准选取依据、抽查范围及核对结果..."
      />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">2、审计结论</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="runAi('allocation-conclusion')"
          >AI 生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
        @update:model-value="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, toRef, type Ref } from 'vue'
import { useF2CostAllocation } from '../../composables/useF2CostAllocation'
import { useF2ValuationAiGenerate, type F2ValAiSection } from '../../composables/useF2ValuationAiGenerate'
import { F2_44_DEFAULT_OBJECTIVE, isBlankAllocationProduct } from '../../composables/useF2CostAllocationFormulas'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const ca = useF2CostAllocation({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const objectiveText = F2_44_DEFAULT_OBJECTIVE

const CONCLUSION_KEY = 'F2-44-audit-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-val:save-items', { detail: { items: [item] } }))
}
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2ValuationAiGenerate(
  toRef(() => props.wpId || '') as Ref<string>,
)

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-44',
    sampleMonth: ca.sheet.value.sampleMonth,
    workshop: ca.sheet.value.workshop,
    poolTotal: ca.poolTotal.value,
    allocGrandTotal: ca.allocGrandTotal.value,
    allocationMismatch: ca.allocationMismatch.value,
    verifyFailCount: ca.verifyFailCount.value,
    productCount: ca.enrichedProducts.value.filter((p) => p.productName).length,
  }
}

async function runAi(section: F2ValAiSection) {
  const existing = section === 'allocation-note' ? (ca.auditNote.value || '') : (auditConclusion.value || '')
  const title = section === 'allocation-note' ? 'AI 生成 · 审计说明' : 'AI 生成 · 成本分配结论'
  const text = await generateAndConfirm(section, existing, aiContext(), title)
  if (!text) return
  if (section === 'allocation-note') {
    ca.auditNote.value = text
  } else {
    auditConclusion.value = text
    saveAuditConclusion(text)
  }
}

function fmt(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtQty(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtUnit(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

function fmtRate(pct: number): string {
  if (!Number.isFinite(pct) || pct === 0) return '0.00%'
  return `${pct.toFixed(2)}%`
}
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.f2-allocation { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; }
.meta-row {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.meta-row label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #606266;
}
.meta-row .el-input { width: 120px; }
.source-nums { margin-left: auto; font-weight: 500; color: #303133; }

.section-label {
  margin: 12px 0 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-purple);
}

.pool-table {
  width: 100%;
  max-width: 720px;
  border-collapse: collapse;
  font-size: 13px;
  margin-bottom: 12px;
}
.pool-table th,
.pool-table td {
  border: 1px solid #d4c8e0;
  padding: 6px 8px;
  text-align: center;
}
.pool-table th {
  background: var(--gt-purple-soft);
  color: #3d2a55;
  font-weight: 600;
}
.pool-total { font-weight: 600; background: #f0ebf5 !important; }
:deep(.pool-num) { width: 100px; }

.table-scroll { overflow-x: auto; margin-bottom: 12px; }
.matrix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  min-width: 1400px;
}
.matrix-table th,
.matrix-table td {
  border: 1px solid #d4c8e0;
  padding: 2px 3px;
  text-align: center;
  vertical-align: middle;
}
.matrix-table thead th {
  background: var(--gt-purple-soft);
  color: #3d2a55;
  font-weight: 600;
}
.matrix-table th.sub { font-weight: 500; font-size: 11px; }
.col-name { width: 100px; text-align: left !important; padding-left: 6px !important; background: #faf8fc; }
.col-qty { min-width: 72px; }
.col-book { min-width: 80px; }
.col-base { min-width: 100px; }
.col-accrued { min-width: 80px; background: #f5f0fa !important; }
.col-verify { min-width: 56px; font-weight: 600; }
.col-act { width: 36px; }
.row-total td { background: #f0ebf5; font-weight: 600; }
.row-warn td { background: #fdf6ec; }
.auto { text-align: right; padding-right: 4px; white-space: nowrap; color: #606266; }
span.auto { display: block; }
.rate { color: #909399; font-size: 11px; }
.verify-ok { color: #67c23a; }
.verify-fail { color: #f56c6c; }
.base-cell { display: flex; flex-direction: column; gap: 2px; }
.base-note { font-size: 11px; color: #909399; }

:deep(.compact-num) { width: 72px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 3px; font-size: 11px; }
</style>
