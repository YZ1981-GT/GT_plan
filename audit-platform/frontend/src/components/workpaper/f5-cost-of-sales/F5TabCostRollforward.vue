<template>
  <div class="f5-rollforward">
    <details class="guidance-details">
      <summary>📋 编制思路（灵魂表 · 四段倒轧链）</summary>
      <div class="guidance-content">
        <p><b>① 直接材料成本 ⑹</b>＝期初原材料⑴＋购入净额⑵＋其他增加⑶−期末原材料⑷−其他发出⑸</p>
        <p><b>② 产品生产成本 ⑽</b>＝直接材料⑹＋直接人工⑺＋制造费用⑻＋专用工模具⑼（「其中：材料费用」仅明细，不计入合计）</p>
        <p><b>③ 产成品成本 ⒀</b>＝产品生产成本⑽＋在产品期初⑾−在产品期末⑿</p>
        <p><b>④ 主营业务成本 ⒇</b>＝产成品成本⒀＋产成品期初⒁＋其他增加⒂−产成品期末⒃−自制自用⒄−内部领用⒅−其他发出⒆</p>
        <p>每行：审定＝未审＋审计调整；公式行对未审/调整/上期分别轧差。悬停「计算说明」或审定数可查看公式。索引号链接试算表、F2 存货、F5-1 审定等。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实营业成本的发生、完整与准确；通过材料→生产→产成品→主营成本倒轧，与 F5-1 审定核对。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="warning">灵魂表</el-tag>
        <span class="toolbar-hint">科目 6401 · 交叉引用 TB / F2 / F5-1 / F5-2</span>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F5-1" :context-project-id="projectIdStr" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F5-2" :context-project-id="projectIdStr" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F2" :context-project-id="projectIdStr" /></span>
      </div>
    </div>

    <F5SheetAttachments
      v-if="projectId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F5-7"
      label="成本倒轧附件"
    />

    <nav class="st-sec-nav" aria-label="F5-7 分区导航">
      <button
        v-for="item in f5RollNav"
        :key="item.id"
        type="button"
        class="st-sec-btn"
        :class="{ active: activeId === item.id }"
        @click="scrollTo(item.id)"
      >{{ item.label }}</button>
    </nav>

    <el-table
      id="f5-7-roll"
      :data="roll.rows.value"
      size="small"
      border
      stripe
      :row-class-name="rowClass"
      max-height="560"
      class="roll-table"
    >
      <el-table-column label="项目内容" min-width="200" fixed>
        <template #default="{ row }">
          <el-tooltip :content="row.formulaExpr" placement="top" :show-after="300">
            <span :class="{ 'result-label': row.isResult, 'detail-label': row.rowType === 'detail' }">
              {{ row.label }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>

      <el-table-column label="计算说明" width="160">
        <template #default="{ row }">
          <el-tooltip :content="row.formulaExpr" placement="top" :show-after="200">
            <span class="f5-formula formula-legend">{{ row.formulaLegend || '—' }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <el-table-column label="数据来源" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <span class="data-source">{{ row.dataSource }}</span>
        </template>
      </el-table-column>

      <el-table-column label="索引号" width="130">
        <template #default="{ row }">
          <template v-if="row.rowType !== 'formula'">
            <el-input
              v-if="!isReadonly"
              :model-value="row.indexRef"
              size="small"
              placeholder="tb:1401 / wp:F2"
              @change="(v: string) => roll.updateIndexRef(row.rowKey, v)"
            />
            <span v-else-if="row.indexRef" class="chip-wrap">
              <GtIndexChip :value="normalizeIndex(row.indexRef)" :context-project-id="projectIdStr" />
            </span>
          </template>
          <span v-else-if="row.indexRef" class="chip-wrap">
            <GtIndexChip :value="normalizeIndex(row.indexRef)" :context-project-id="projectIdStr" />
          </span>
        </template>
      </el-table-column>

      <el-table-column label="未审数" width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="row.rowType !== 'formula' && !isReadonly"
            :model-value="row.unadjusted"
            size="small"
            style="width:100%"
            @change="(v: number | undefined) => roll.updateAmount(row.rowKey, 'unadjusted', v ?? 0)"
          />
          <el-tooltip v-else-if="row.rowType === 'formula'" :content="row.formulaExpr" placement="top">
            <span class="f5-formula">{{ fmt(row.unadjusted) }}</span>
          </el-tooltip>
          <span v-else :class="{ 'tb-val': roll.isTbField(row.rowKey) }">{{ fmt(row.unadjusted) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="审计调整" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowType !== 'formula' && !isReadonly"
            :model-value="row.aje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number | undefined) => roll.updateAmount(row.rowKey, 'aje', v ?? 0)"
          />
          <el-tooltip v-else-if="row.rowType === 'formula'" :content="`调整轧差：${row.formulaLegend}`" placement="top">
            <span class="f5-formula">{{ fmt(row.aje) }}</span>
          </el-tooltip>
          <span v-else>{{ fmt(row.aje) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="审定数" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip
            :content="row.rowType === 'formula'
              ? row.formulaExpr
              : `审定 = 未审 + 审计调整 = ${row.unadjusted} + ${row.aje}`"
            placement="top"
            :show-after="200"
          >
            <span class="f5-formula" :class="{ 'result-val': row.isResult }">{{ fmt(row.audited) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>

      <el-table-column label="上期数" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.rowType !== 'formula' && !isReadonly"
            :model-value="row.prior"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number | undefined) => roll.updateAmount(row.rowKey, 'prior', v ?? 0)"
          />
          <el-tooltip v-else-if="row.rowType === 'formula'" :content="`上期轧差：${row.formulaLegend}`" placement="top">
            <span class="f5-formula">{{ fmt(row.prior) }}</span>
          </el-tooltip>
          <span v-else>{{ fmt(row.prior) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 校验区（HTML 扩展，与 F5-1 EventBus 联动） -->
    <el-card id="f5-7-verify" class="verify-card" shadow="never" :class="{ 'verify-warn': roll.varianceExceedsMateriality.value }">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">与 F5-1 审定营业成本核对</span>
          <span class="chip-wrap"><GtIndexChip value="wp:F5-1" :context-project-id="projectIdStr" /></span>
        </div>
      </template>
      <div class="verify-grid">
        <div>
          <span class="verify-label">倒轧主营业务成本（审定）</span>
          <el-tooltip :content="roll.mainCogsRow.value?.formulaExpr" placement="top">
            <b class="f5-formula">{{ fmt(d.cogsAudited) }}</b>
          </el-tooltip>
        </div>
        <div>
          <span class="verify-label">F5-1 审定营业成本</span>
          <b>{{ fmt(d.adjudicatedCOGS) }}</b>
        </div>
        <div>
          <span class="verify-label">差异（审定 − 倒轧）</span>
          <b :class="{ 'is-warn': roll.varianceExceedsMateriality.value }">{{ fmt(d.rollforwardVariance) }}</b>
        </div>
      </div>
      <p v-if="roll.varianceExceedsMateriality.value" class="verify-hint">
        差异超过重要性水平（或非零），请查明倒轧链条断点或调整未入账原因。
      </p>
    </el-card>

    <el-card id="f5-7-note" class="opinion-card" shadow="never">
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
        :model-value="roll.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="说明倒轧各环节取数来源、重大调整、与 F5-1 / 存货底稿勾稽情况…"
        @change="roll.saveAuditNote"
      />
    </el-card>

    <el-card id="f5-7-conclusion" class="opinion-card" shadow="never">
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
        :model-value="roll.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合评价倒轧结果与审定营业成本是否相符（A/B/C口径）…"
        @change="(v: string) => roll.saveAuditConclusion(v)"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * F5TabCostRollforward — F5-7 主营业务成本倒轧表（灵魂表）
 * 21 行源表网格 + 公式悬停 + 交叉索引 + F5-1 校验 + AI
 */
import { computed, inject, toRef, watch, type Ref } from 'vue'
import { useF5CostRollforward } from '../composables/useF5CostRollforward'
import { useF5AiGenerate } from '../composables/useF5AiGenerate'
import { useStickySectionNav } from '../composables/useStickySectionNav'
import F5SheetAttachments from './F5SheetAttachments.vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

const f5RollNav = [
  { id: 'f5-7-roll', label: '倒轧' },
  { id: 'f5-7-verify', label: '核对' },
  { id: 'f5-7-note', label: '说明' },
  { id: 'f5-7-conclusion', label: '结论' },
]
const { activeId, scrollTo } = useStickySectionNav(f5RollNav)

const props = withDefaults(defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
  adjudicatedCOGS?: number
  tbData?: Record<string, number> | null
  materiality?: number
}>(), {
  projectId: '',
  adjudicatedCOGS: 0,
  tbData: null,
  materiality: 0,
})

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const roll = useF5CostRollforward({
  allResponses: allResponsesRef,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  materiality: computed(() => props.materiality ?? 0) as unknown as Ref<number>,
  adjudicatedCOGS: computed(() => props.adjudicatedCOGS ?? 0) as unknown as Ref<number>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF5AiGenerate(wpIdRef)

const d = computed(() => roll.data.value)
const projectIdStr = computed(() => props.projectId)

// TB 自动取数灌入：仅填充空/零字段，避免覆盖人工改数
watch(
  () => props.tbData,
  (tb) => {
    if (!tb || props.isReadonly) return
    const patch: Record<string, number> = {}
    const data = roll.data.value as Record<string, unknown>
    for (const k of roll.tbFields) {
      if (tb[k] == null) continue
      const current = Number(data[k] ?? 0)
      if (Math.abs(current) < 0.005) patch[k] = Number(tb[k])
    }
    if (Object.keys(patch).length) roll.setTbValues(patch as any)
  },
  { immediate: true, deep: true },
)

function rowClass({ row }: { row: any }): string {
  if (row.isResult) return 'f5-row-result'
  if (row.rowType === 'detail') return 'f5-row-detail'
  return ''
}

function normalizeIndex(ref: string): string {
  const t = ref.trim()
  if (!t) return t
  if (t.startsWith('wp:') || t.startsWith('tb:')) return t
  if (/^\d{4}/.test(t)) return `tb:${t}`
  return `wp:${t}`
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

function openReview() {
  openReviewDialog?.('F5-7-conclusion')
}

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F5-7',
    chain: {
      directMaterial: roll.rows.value.find((r) => r.rowKey === 'directMaterialCost'),
      productionCost: roll.rows.value.find((r) => r.rowKey === 'productProductionCost'),
      finishedGoods: roll.rows.value.find((r) => r.rowKey === 'finishedGoodsCost'),
      mainCOGS: roll.mainCogsRow.value,
    },
    verification: {
      cogsAudited: d.value.cogsAudited,
      adjudicatedCOGS: d.value.adjudicatedCOGS,
      variance: d.value.rollforwardVariance,
      exceedsMateriality: roll.varianceExceedsMateriality.value,
    },
    rows: roll.rows.value.map((r) => ({
      seqNo: r.seqNo,
      label: r.label,
      formulaLegend: r.formulaLegend,
      unadjusted: r.unadjusted,
      aje: r.aje,
      audited: r.audited,
      prior: r.prior,
      indexRef: r.indexRef,
      rowType: r.rowType,
    })),
  }
}

async function generateAiNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'rollforward-note',
    roll.auditNote.value,
    aiContext(),
    'AI 生成 · F5-7审计说明',
  )
  if (text) roll.saveAuditNote(text)
}

async function generateAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'rollforward-evaluation',
    roll.auditConclusion.value,
    aiContext(),
    'AI 生成 · F5-7审计结论',
  )
  if (text) roll.saveAuditConclusion(text)
}
</script>

<style scoped>
.f5-rollforward { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f5-rollforward :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f5-rollforward :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #b88230;
  background: #fdf6ec;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 600; color: #b88230; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.7; }
.guidance-content p { margin: 4px 0; }
.objective-alert { margin-bottom: 12px; }

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-hint { color: #909399; font-size: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }

.f5-formula { border-bottom: 1px dashed #909399; cursor: help; }
.formula-legend { color: #315a8a; font-weight: 500; }
.result-label { font-weight: 700; color: #303133; }
.detail-label { padding-left: 12px; color: #909399; font-size: 12px; }
.result-val { font-weight: 700; color: #315a8a; }
.tb-val { color: #67c23a; }
.data-source { color: #909399; font-size: 12px; }
.is-warn { color: #f56c6c; font-weight: 700; }

:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.f5-row-result) { background: #eef4fa !important; font-weight: 600; }
:deep(.f5-row-detail) { background: #fafafa !important; color: #909399; }

.verify-card {
  margin-top: 16px;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
}
.verify-card.verify-warn { border-color: #f56c6c; background: #fef0f0; }
.verify-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.verify-label { display: block; color: #909399; font-size: 12px; margin-bottom: 4px; }
.verify-hint { margin: 10px 0 0; color: #f56c6c; font-size: 13px; }

.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }

@media (max-width: 900px) {
  .verify-grid { grid-template-columns: 1fr; }
}
</style>

<style src="../f2/stocktake/f2StocktakeSoftNav.css"></style>
