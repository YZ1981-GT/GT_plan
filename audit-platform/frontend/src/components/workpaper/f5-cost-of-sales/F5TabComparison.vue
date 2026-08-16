<template>
  <div class="f5-comparison">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表按产品对比本期与上期的结转数量、平均单位成本与总成本，分析主营业务成本同比变动。</p>
        <p>2. 灰色列为公式列：总成本=数量×平均单位成本；变动额=本期−上期；变动率=变动额/上期（上期为0显示 N/A）。</p>
        <p>3. 合计行仅汇总总成本及总成本变动；数量、单价不纵向合计。总成本变动率绝对值≥30% 标黄。</p>
        <p>4. 差异原因与索引号用于交叉索引至 F5-2 / F5-6 等底稿。可从 F5-2 引用品种名称。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：通过数量、单位成本与总成本同比分析，识别主营业务成本异常波动，验证结转完整性与准确性。"
      class="objective-alert"
    />

    <el-alert
      v-if="cmp.significantChanges.value.length"
      type="warning"
      :closable="false"
      class="change-alert"
      :title="`总成本变动率绝对值≥${threshold}% 的产品：${cmp.significantChanges.value.map((r) => r.product || '（未命名）').join('、')}`"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="promptAddRow">+ 产品</el-button>
        <el-button size="small" :disabled="isReadonly" @click="syncFromMonthly">从F5-2引用品种</el-button>
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
        <span class="chip-wrap"><GtIndexChip value="wp:F5-6" :context-project-id="projectIdStr" /></span>
        <el-tag size="small" type="info">共 {{ cmp.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <F5SheetAttachments
      v-if="projectId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F5-5"
      label="比较分析附件"
    />

    <el-table
      :data="tableData"
      size="small"
      border
      stripe
      :row-class-name="rowClass"
      max-height="520"
    >
      <el-table-column label="产品" width="130" fixed>
        <template #default="{ row }">
          <template v-if="row.__type === 'data'">
            <el-input
              v-if="!isReadonly"
              :model-value="row.product"
              size="small"
              @change="(v: string) => cmp.updateCell(row.id, 'product', v)"
            />
            <span v-else>{{ row.product }}</span>
          </template>
          <strong v-else>合计</strong>
        </template>
      </el-table-column>

      <el-table-column label="本期数" align="center">
        <el-table-column label="数量" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.currentQty"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => cmp.updateCell(row.id, 'currentQty', v ?? 0)"
            />
            <span v-else-if="row.__type === 'data'">{{ fmt(row.currentQty) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平均单位成本" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.currentUnitCost"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => cmp.updateCell(row.id, 'currentUnitCost', v ?? 0)"
            />
            <span v-else-if="row.__type === 'data'">{{ fmt(row.currentUnitCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="总成本" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="f5-formula" title="数量 × 平均单位成本">{{ fmt(row.currentTotalCost) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="上期数" align="center">
        <el-table-column label="数量" width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.priorQty"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => cmp.updateCell(row.id, 'priorQty', v ?? 0)"
            />
            <span v-else-if="row.__type === 'data'">{{ fmt(row.priorQty) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平均单位成本" width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.priorUnitCost"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => cmp.updateCell(row.id, 'priorUnitCost', v ?? 0)"
            />
            <span v-else-if="row.__type === 'data'">{{ fmt(row.priorUnitCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="总成本" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="f5-formula" title="数量 × 平均单位成本">{{ fmt(row.priorTotalCost) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="变动额" align="center">
        <el-table-column label="数量" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span v-if="row.__type === 'data'" class="f5-formula" title="本期数量 − 上期数量">
              {{ fmt(row.qtyChange) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="平均单位成本" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span v-if="row.__type === 'data'" class="f5-formula" title="本期单价 − 上期单价">
              {{ fmt(row.unitCostChange) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="总成本" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="f5-formula" title="本期总成本 − 上期总成本">{{ fmt(row.totalCostChange) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="变动率" align="center">
        <el-table-column label="数量" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span v-if="row.__type === 'data'" class="f5-formula" title="数量变动额 / 上期数量">
              {{ pct(row.qtyChangeRate) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="平均单位成本" width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span v-if="row.__type === 'data'" class="f5-formula" title="单价变动额 / 上期单价">
              {{ pct(row.unitCostChangeRate) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="总成本" width="90" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span
              class="f5-formula"
              :class="{ 'is-warn': isRateWarn(row.totalCostChangeRate) }"
              title="总成本变动额 / 上期总成本"
            >{{ pct(row.totalCostChangeRate) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="差异原因分析" align="center">
        <el-table-column label="变动原因" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.changeReason"
              size="small"
              @change="(v: string) => cmp.updateCell(row.id, 'changeReason', v)"
            />
            <span v-else-if="row.__type === 'data'">{{ row.changeReason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="120">
          <template #default="{ row }">
            <el-input
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.indexRef"
              size="small"
              placeholder="如 F5-2"
              @change="(v: string) => cmp.updateCell(row.id, 'indexRef', v)"
            />
            <span v-else-if="row.__type === 'data'" class="chip-wrap">
              <GtIndexChip v-if="row.indexRef" :value="normalizeIndex(row.indexRef)" :context-project-id="projectIdStr" />
              <template v-else>{{ row.indexRef }}</template>
            </span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="64" fixed="right">
        <template #default="{ row }">
          <el-popconfirm v-if="row.__type === 'data'" title="确认删除？" @confirm="cmp.removeRow(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-card class="opinion-card" shadow="never">
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
        :model-value="cmp.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="说明数量、单位成本、总成本同比变动的主要驱动及交叉索引情况…"
        @change="cmp.saveAuditNote"
      />
    </el-card>

    <el-card class="opinion-card" shadow="never">
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
        :model-value="cmp.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合评价主营业务成本同比分析是否支持结转合理性结论（A/B/C口径）…"
        @change="cmp.saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * F5TabComparison — F5-5 主营业务成本与上年度比较分析表
 * 源表：数量×单价→总成本 + 变动额/率 + 变动原因/索引 + AI说明结论
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useF5Comparison,
  F5_COMPARISON_CHANGE_RATE_THRESHOLD,
} from '../composables/useF5Comparison'
import { useF5AiGenerate } from '../composables/useF5AiGenerate'
import { resolveImportExportSheet, isImportExportSheet } from '../shared/cycleImportExportRegistry'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'
import F5SheetAttachments from './F5SheetAttachments.vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

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

const cmp = useF5Comparison({
  allResponses: allResponsesRef,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF5AiGenerate(wpIdRef)

const threshold = F5_COMPARISON_CHANGE_RATE_THRESHOLD
const projectIdStr = computed(() => props.projectId)
const ieCtx = computed(() =>
  isImportExportSheet('f5', 'F5-5') ? resolveImportExportSheet('f5', 'F5-5') : null,
)

const tableData = computed(() => {
  const rows: any[] = cmp.rows.value.map((r) => ({ __type: 'data', ...r }))
  const total = cmp.totalRow.value
  rows.push({
    __type: 'total',
    id: '__total',
    product: '合计',
    currentTotalCost: total.currentTotalCost,
    priorTotalCost: total.priorTotalCost,
    totalCostChange: total.totalCostChange,
    totalCostChangeRate: total.totalCostChangeRate,
  })
  return rows
})

function rowClass({ row }: { row: any }): string {
  if (row.__type === 'total') return 'f5-row-total'
  if (cmp.isRowHighlighted(row)) return 'f5-row-warn'
  return ''
}

function isRateWarn(rate: number | 'N/A' | null | undefined): boolean {
  return typeof rate === 'number' && Math.abs(rate) >= threshold
}

function normalizeIndex(ref: string): string {
  const t = ref.trim()
  if (!t) return t
  return t.startsWith('wp:') ? t : `wp:${t}`
}

async function promptAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入产品名称', '新增产品', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '产品名称不能为空',
    })
    if (value) cmp.addRow(value.trim())
  } catch { /* 取消 */ }
}

function syncFromMonthly() {
  const raw = allResponsesRef.value.get('F5-2-monthly-rows')?.remark
    ?? allResponsesRef.value.get('F5-2-rows')?.remark
  if (!raw) {
    ElMessage.info('F5-2 暂无品种数据')
    return
  }
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return
    const existing = new Set(cmp.rows.value.map((r) => r.product.trim()).filter(Boolean))
    let added = 0
    for (const r of parsed) {
      const name = String(r?.product ?? r?.variety ?? '').trim()
      if (!name || existing.has(name)) continue
      // 填入空行或新增
      const empty = cmp.rows.value.find((row) => !row.product.trim()
        && row.currentTotalCost === 0 && row.priorTotalCost === 0)
      if (empty) {
        cmp.updateCell(empty.id, 'product', name)
      } else {
        cmp.addRow(name)
      }
      existing.add(name)
      added += 1
    }
    if (added > 0) ElMessage.success(`已从F5-2引用 ${added} 个品种`)
    else ElMessage.info('F5-2中的品种均已存在')
  } catch {
    ElMessage.warning('F5-2 数据解析失败')
  }
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  if (Math.abs(v) < 0.005) return '-'
  const formatted = Math.abs(v).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return v < 0 ? `(${formatted})` : formatted
}

function pct(v: number | 'N/A' | null | undefined): string {
  if (v == null || v === 'N/A') return 'N/A'
  return `${Number(v).toFixed(2)}%`
}

function openReview() {
  openReviewDialog?.('F5-5-conclusion')
}

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F5-5',
    threshold,
    significantChanges: cmp.significantChanges.value.map((r) => ({
      product: r.product,
      currentTotalCost: r.currentTotalCost,
      priorTotalCost: r.priorTotalCost,
      qtyChange: r.qtyChange,
      unitCostChange: r.unitCostChange,
      totalCostChange: r.totalCostChange,
      totalCostChangeRate: r.totalCostChangeRate,
      changeReason: r.changeReason,
    })),
    total: cmp.totalRow.value,
    products: cmp.rows.value
      .filter((r) => r.product.trim() || r.currentTotalCost || r.priorTotalCost)
      .map((r) => ({
        product: r.product,
        currentQty: r.currentQty,
        currentUnitCost: r.currentUnitCost,
        currentTotalCost: r.currentTotalCost,
        priorQty: r.priorQty,
        priorUnitCost: r.priorUnitCost,
        priorTotalCost: r.priorTotalCost,
        qtyChangeRate: r.qtyChangeRate,
        unitCostChangeRate: r.unitCostChangeRate,
        totalCostChangeRate: r.totalCostChangeRate,
        changeReason: r.changeReason,
        indexRef: r.indexRef,
      })),
  }
}

async function generateAiNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'comparison-note',
    cmp.auditNote.value,
    aiContext(),
    'AI 生成 · F5-5审计说明',
  )
  if (text) cmp.saveAuditNote(text)
}

async function generateAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'comparison-conclusion',
    cmp.auditConclusion.value,
    aiContext(),
    'AI 生成 · F5-5审计结论',
  )
  if (text) cmp.saveAuditConclusion(text)
}
</script>

<style scoped>
.f5-comparison { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f5-comparison :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f5-comparison :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

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
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }

.f5-formula { border-bottom: 1px dashed #909399; cursor: help; }
.f5-formula.is-warn { color: #e6a23c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
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
