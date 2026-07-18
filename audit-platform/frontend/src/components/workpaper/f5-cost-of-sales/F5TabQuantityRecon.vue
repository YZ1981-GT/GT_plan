<template>
  <div class="f5-qty-recon">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表验算主营业务收入确认数量与成本结转数量是否匹配；适用于制造业产品销售，其他行业可改参考格式。</p>
        <p>2. 分厂→产品层级：产品行录入 1~12 月数量；分厂行与总计行为公式汇总；总计列=各月合计。</p>
        <p>3. 「差异」= 本期销售数量 − 本期结转销售成本数量（各月及总计只读）。差异≠0 的产品标黄。</p>
        <p>4. 可增删分厂/产品；销售与结转两表结构同步。交叉索引见 F5-2 / F5-5。</p>
        <p>5. 可上传出库单/发货单 OCR，确认后回填结转数量对应月份。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实销售数量与结转成本数量的完整与匹配，识别月度及全年数量差异。"
      class="objective-alert"
    />

    <el-alert
      v-if="recon.significantDiffs.value.length"
      type="warning"
      :closable="false"
      class="change-alert"
      :title="`存在数量差异的产品：${recon.significantDiffs.value.map((d) => `${d.plant}/${d.product}(${d.diffTotal})`).join('、')}`"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="promptAddPlant">+ 分厂</el-button>
        <el-upload
          :show-file-list="false"
          :auto-upload="false"
          accept=".pdf,.png,.jpg,.jpeg"
          :disabled="isReadonly || ocrLoading"
          @change="(upload: any) => uploadOutboundOcr(upload.raw || upload)"
        >
          <el-button size="small" :loading="ocrLoading" :disabled="isReadonly">出库单OCR</el-button>
        </el-upload>
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown
          v-if="ieCtx"
          :wp-id="wpId"
          :api-prefix="ieCtx.apiPrefix"
          :sheet="ieCtx.sheet"
          :disabled="isReadonly"
          @imported="$emit('imported')"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F5-2" :context-project-id="projectIdStr" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F5-5" :context-project-id="projectIdStr" /></span>
        <el-tag size="small" type="info">{{ recon.plants.value.length }} 个分厂</el-tag>
      </div>
    </div>

    <F5SheetAttachments
      v-if="projectId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F5-6"
      label="数量核对附件"
    />

    <nav class="st-sec-nav" aria-label="F5-6 分区导航">
      <button
        v-for="item in f5QtyNav"
        :key="item.id"
        type="button"
        class="st-sec-btn"
        :class="{ active: activeId === item.id }"
        @click="scrollTo(item.id)"
      >{{ item.label }}</button>
    </nav>

    <!-- 1. 销售数量 -->
    <div id="f5-6-sales" class="section-block">
      <div class="section-title">1、本期销售数量表</div>
      <el-table
        :data="salesTableData"
        size="small"
        border
        stripe
        :row-class-name="rowClass"
        max-height="360"
      >
        <el-table-column label="项目" width="160" fixed>
          <template #default="{ row }">
            <template v-if="row.__type === 'plant'">
              <el-input
                v-if="!isReadonly"
                :model-value="row.name"
                size="small"
                @change="(v: string) => recon.updatePlantName(row.plantId, v)"
              />
              <strong v-else>{{ row.name }}</strong>
            </template>
            <template v-else-if="row.__type === 'product'">
              <div class="product-cell">
                <el-input
                  v-if="!isReadonly"
                  :model-value="row.name"
                  size="small"
                  @change="(v: string) => recon.updateProductName(row.plantId, row.productId, v)"
                />
                <span v-else class="product-name">{{ row.name }}</span>
              </div>
            </template>
            <strong v-else>总计</strong>
          </template>
        </el-table-column>
        <el-table-column
          v-for="(label, mi) in monthLabels"
          :key="`s-${label}`"
          :label="label"
          width="78"
          align="right"
        >
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'product' && !isReadonly"
              :model-value="row.months[mi]"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => recon.updateMonth(row.plantId, row.productId, 'sales', mi, v ?? 0)"
            />
            <span v-else class="f5-formula">{{ fmt(row.months[mi]) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="总计" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="f5-formula" title="Σ(1~12月)">{{ fmt(row.total) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <template v-if="row.__type === 'plant'">
              <el-button size="small" link type="primary" @click="promptAddProduct(row.plantId)">+产品</el-button>
              <el-popconfirm title="删除该分厂？" @confirm="recon.removePlant(row.plantId)">
                <template #reference>
                  <el-button size="small" link type="danger">删</el-button>
                </template>
              </el-popconfirm>
            </template>
            <el-popconfirm
              v-else-if="row.__type === 'product'"
              title="删除该产品？"
              @confirm="recon.removeProduct(row.plantId, row.productId)"
            >
              <template #reference>
                <el-button size="small" link type="danger">删</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 2. 结转成本数量 -->
    <div id="f5-6-cost" class="section-block">
      <div class="section-title">2、本期结转销售成本数量表</div>
      <el-table
        :data="costTableData"
        size="small"
        border
        stripe
        :row-class-name="rowClass"
        max-height="360"
      >
        <el-table-column label="项目" width="160" fixed>
          <template #default="{ row }">
            <strong v-if="row.__type === 'plant'">{{ row.name }}</strong>
            <span v-else-if="row.__type === 'product'" class="product-name">{{ row.name }}</span>
            <strong v-else>总计</strong>
          </template>
        </el-table-column>
        <el-table-column
          v-for="(label, mi) in monthLabels"
          :key="`c-${label}`"
          :label="label"
          width="78"
          align="right"
        >
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'product' && !isReadonly"
              :model-value="row.months[mi]"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => recon.updateMonth(row.plantId, row.productId, 'cost', mi, v ?? 0)"
            />
            <span v-else class="f5-formula">{{ fmt(row.months[mi]) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="总计" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="f5-formula" title="Σ(1~12月)">{{ fmt(row.total) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 3. 差异 -->
    <div id="f5-6-diff" class="section-block">
      <div class="section-title">3、差异（销售数量 − 结转成本数量）</div>
      <el-table
        :data="diffTableData"
        size="small"
        border
        stripe
        :row-class-name="diffRowClass"
        max-height="360"
      >
        <el-table-column label="项目" width="160" fixed>
          <template #default="{ row }">
            <strong v-if="row.__type === 'plant'">{{ row.name }}</strong>
            <span v-else-if="row.__type === 'product'" class="product-name">{{ row.name }}</span>
            <strong v-else>总计</strong>
          </template>
        </el-table-column>
        <el-table-column
          v-for="(label, mi) in monthLabels"
          :key="`d-${label}`"
          :label="label"
          width="78"
          align="right"
          class-name="auto-calc-col"
        >
          <template #default="{ row }">
            <span class="f5-formula" :class="{ 'is-warn': row.months[mi] !== 0 }" title="销售 − 结转">
              {{ fmt(row.months[mi]) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="总计" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="f5-formula" :class="{ 'is-warn': row.total !== 0 }" title="销售总计 − 结转总计">
              {{ fmt(row.total) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-card id="f5-6-note" class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">三、审计说明</span>
          <div class="opinion-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="generateAiNote"
            >🤖 AI生成说明</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReview">复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="recon.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="说明销售数量与结转数量的勾稽情况、月度/全年差异原因及交叉索引…"
        @change="recon.saveAuditNote"
      />
    </el-card>

    <el-card id="f5-6-conclusion" class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">四、审计结论</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="generateAiConclusion"
          >🤖 AI生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="recon.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合评价量本数量核对是否支持成本结转完整性结论（A/B/C口径）…"
        @change="recon.saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * F5TabQuantityRecon — F5-6 销售数量与结转成本数量核对明细表
 * 源表：分厂→产品 × 销售/结转/差异 三表（1~12月+总计）+ AI说明结论
 */
import { computed, inject, ref, toRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import {
  useF5QuantityRecon,
  F5_QTY_MONTH_LABELS,
} from '../composables/useF5QuantityRecon'
import { useF5AiGenerate } from '../composables/useF5AiGenerate'
import { useStickySectionNav } from '../composables/useStickySectionNav'
import { resolveImportExportSheet, isImportExportSheet } from '../shared/cycleImportExportRegistry'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'
import F5SheetAttachments from './F5SheetAttachments.vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

const f5QtyNav = [
  { id: 'f5-6-sales', label: '销售' },
  { id: 'f5-6-cost', label: '结转' },
  { id: 'f5-6-diff', label: '差异' },
  { id: 'f5-6-note', label: '说明' },
  { id: 'f5-6-conclusion', label: '结论' },
]
const { activeId, scrollTo } = useStickySectionNav(f5QtyNav)

defineEmits<{ imported: [] }>()

const props = withDefaults(defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
}>(), {
  projectId: '',
})

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const recon = useF5QuantityRecon({
  allResponses: allResponsesRef,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF5AiGenerate(wpIdRef)

const ocrLoading = ref(false)
const monthLabels = F5_QTY_MONTH_LABELS
const projectIdStr = computed(() => props.projectId)
const ieCtx = computed(() =>
  isImportExportSheet('f5', 'F5-6') ? resolveImportExportSheet('f5', 'F5-6') : null,
)

async function uploadOutboundOcr(file: File): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  ocrLoading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const res = await http.post(`/api/workpapers/${props.wpId}/f5/contract-ocr`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      _silent: true,
    } as any)
    const data = res.data?.data ?? res.data ?? {}
    const fields = data.extracted_fields ?? {}
    const confidence = Number(data.confidence ?? 0)
    const summary = [
      fields.product && `产品：${fields.product}`,
      fields.quantity != null && `数量：${fields.quantity}`,
      fields.date && `日期：${fields.date}`,
      fields.voucherNo && `单号：${fields.voucherNo}`,
    ].filter(Boolean).join('\n')
    await ElMessageBox.confirm(
      `OCR置信度 ${(confidence * 100).toFixed(0)}%\n\n${summary || '未提取到有效字段'}\n\n是否回填到结转数量表？`,
      '出库单OCR',
      { confirmButtonText: '回填', cancelButtonText: '取消', type: 'info' },
    )
    const applied = recon.applyOcrOutbound({
      product: fields.product,
      quantity: fields.quantity,
      date: fields.date,
      voucherNo: fields.voucherNo,
    })
    if (applied) {
      ElMessage.success(`已回填至 ${F5_QTY_MONTH_LABELS[applied.monthIndex]} 结转数量`)
    } else {
      ElMessage.warning('未能回填，请检查分厂/产品')
    }
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.warning('OCR识别失败')
    }
  } finally {
    ocrLoading.value = false
  }
}

type SeriesKey = 'sales' | 'cost' | 'diff'

function buildTableData(series: SeriesKey) {
  const rows: any[] = []
  for (const plant of recon.plants.value) {
    const plantSeries = plant[series]
    rows.push({
      __type: 'plant',
      plantId: plant.id,
      name: plant.name,
      months: plantSeries.months,
      total: plantSeries.total,
    })
    for (const prod of plant.products) {
      const ps = prod[series]
      rows.push({
        __type: 'product',
        plantId: plant.id,
        productId: prod.id,
        name: prod.name,
        months: ps.months,
        total: ps.total,
        diffTotal: prod.diff.total,
      })
    }
  }
  const gt = recon.grandTotal.value[series]
  rows.push({
    __type: 'total',
    name: '总计',
    months: gt.months,
    total: gt.total,
  })
  return rows
}

const salesTableData = computed(() => buildTableData('sales'))
const costTableData = computed(() => buildTableData('cost'))
const diffTableData = computed(() => buildTableData('diff'))

function rowClass({ row }: { row: any }): string {
  if (row.__type === 'plant') return 'f5-row-plant'
  if (row.__type === 'total') return 'f5-row-total'
  return ''
}

function diffRowClass({ row }: { row: any }): string {
  if (row.__type === 'plant') return 'f5-row-plant'
  if (row.__type === 'total') return 'f5-row-total'
  if (row.__type === 'product' && recon.isDiffHighlighted(row.diffTotal ?? row.total)) {
    return 'f5-row-warn'
  }
  return ''
}

async function promptAddPlant() {
  try {
    const { value } = await ElMessageBox.prompt('请输入分厂名称', '新增分厂', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '分厂名称不能为空',
    })
    if (value) recon.addPlant(value.trim())
  } catch { /* 取消 */ }
}

async function promptAddProduct(plantId: string) {
  try {
    const { value } = await ElMessageBox.prompt('请输入产品名称', '新增产品', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '产品名称不能为空',
    })
    if (value) recon.addProduct(plantId, value.trim())
  } catch { /* 取消 */ }
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  if (Math.abs(v) < 0.0005) return '-'
  const formatted = Math.abs(v).toLocaleString('zh-CN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 4,
  })
  return v < 0 ? `(${formatted})` : formatted
}

function openReview() {
  openReviewDialog?.('F5-6-conclusion')
}

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F5-6',
    significantDiffs: recon.significantDiffs.value,
    grandTotal: {
      sales: recon.grandTotal.value.sales.total,
      cost: recon.grandTotal.value.cost.total,
      diff: recon.grandTotal.value.diff.total,
      salesMonths: recon.grandTotal.value.sales.months,
      costMonths: recon.grandTotal.value.cost.months,
      diffMonths: recon.grandTotal.value.diff.months,
    },
    plants: recon.plants.value.map((p) => ({
      name: p.name,
      salesTotal: p.sales.total,
      costTotal: p.cost.total,
      diffTotal: p.diff.total,
      products: p.products.map((pr) => ({
        name: pr.name,
        salesTotal: pr.sales.total,
        costTotal: pr.cost.total,
        diffTotal: pr.diff.total,
        salesMonths: pr.sales.months,
        costMonths: pr.cost.months,
        diffMonths: pr.diff.months,
      })),
    })),
  }
}

async function generateAiNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'quantity-reconciliation-note',
    recon.auditNote.value,
    aiContext(),
    'AI 生成 · F5-6审计说明',
  )
  if (text) recon.saveAuditNote(text)
}

async function generateAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'quantity-reconciliation-conclusion',
    recon.auditConclusion.value,
    aiContext(),
    'AI 生成 · F5-6审计结论',
  )
  if (text) recon.saveAuditConclusion(text)
}
</script>

<style scoped>
.f5-qty-recon { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f5-qty-recon :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f5-qty-recon :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #315a8a;
  background: #eef4fa;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 600; color: #315a8a; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.65; }
.guidance-content p { margin: 3px 0; }
.objective-alert, .change-alert { margin-bottom: 12px; }

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }

.section-block { margin-bottom: 20px; }
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
  padding-left: 4px;
  border-left: 3px solid #315a8a;
}

.product-cell { padding-left: 12px; }
.product-name { padding-left: 12px; color: #c45656; }

.f5-formula { border-bottom: 1px dashed #909399; cursor: help; }
.f5-formula.is-warn { color: #e6a23c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.f5-row-plant) { background: #e8eaf6 !important; font-weight: 600; }
:deep(.f5-row-total) { background: #f0f5fa !important; font-weight: 600; }
:deep(.f5-row-warn) { background: #fdf6ec !important; }

.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>

<style src="../f2/stocktake/f2StocktakeSoftNav.css"></style>
