<template>
  <div class="g9-fv" data-testid="g9-fv-test">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 有数量/单价时，公允价值 = 数量 × 单价（灰底公式列）；差异 = 数量影响 + 价格影响。</p>
        <p>2. |差异|&gt;0.01 须填差异原因；Level3 须填估值技术、不可观察输入值与文件索引。</p>
        <p>3. 可从 G9-2 带入；审定合计应与 G9-2 期末审定勾稽；Level3 审定结果可带入 G9-5。</p>
        <p>4. 超 B15 差异可推送 G9-3（FVTPL：1504 ↔ 6101），并回填 G9A 程序步骤 8。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：验证其他非流动金融资产公允价值计量的恰当性，核实公允价值层次划分、估值技术与不可观察输入值的合理性，为 G9-1 计价认定提供支撑。"
    />

    <div class="toolbar">
      <div class="methodology">公允价值三层次：Level1 活跃市场报价 / Level2 可观察输入值 / Level3 不可观察输入值（估值技术）</div>
      <div class="head-actions tab-toolbar">
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="fv.syncFromDetail()">
          ↓ 从 G9-2 带入
        </el-button>
        <el-button v-if="!isReadonly" size="small" plain @click="fv.pushToDetail()">
          ↑ 回写 G9-2
        </el-button>
        <el-button
          v-if="!isReadonly && fv.diffCount.value > 0"
          size="small"
          type="warning"
          plain
          @click="onPushDiff"
        >
          推送差异→G9-3
          <template v-if="fv.materialDiffCount.value">（B15:{{ fv.materialDiffCount.value }}）</template>
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="success"
          plain
          :loading="fv.procedureMarking.value"
          :disabled="!fv.rows.value.length"
          @click="onMarkProcedure"
        >
          {{ fv.procedureMarked.value ? '已回填 G9A（可重写）' : '回填 G9A 公允测试' }}
        </el-button>
        <G9ImportExportDropdown :wp-id="wpId" sheet="G9-4" @imported="onImported" />
        <span class="chip-wrap"><GtIndexChip value="wp:G9-4" /></span>
        <GtReviewTrigger section-id="G9-4-fv" />
      </div>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="success">L1: {{ fv.levelSummary.value.Level1 }}</el-tag>
        <el-tag size="small" type="warning">L2: {{ fv.levelSummary.value.Level2 }}</el-tag>
        <el-tag size="small" type="danger">L3: {{ fv.levelSummary.value.Level3 }}</el-tag>
        <el-tag v-if="fv.levelSummary.value.unset > 0" size="small" type="info">
          未设: {{ fv.levelSummary.value.unset }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info">共 {{ fv.rows.value.length }} 行</el-tag>
        <el-tag v-if="fv.diffCount.value > 0" size="small" type="danger">
          {{ fv.diffCount.value }} 项差异
        </el-tag>
        <el-tag v-if="fv.missingDiffReasonCount.value > 0" size="small" type="warning">
          {{ fv.missingDiffReasonCount.value }} 项缺原因
        </el-tag>
      </div>
    </div>

    <el-alert
      v-if="fv.hasCrossRefIssue.value"
      type="warning"
      :closable="false"
      show-icon
      class="cross-ref-alert"
      :title="`审定公允价值合计 ${fmt(fv.totals.value.closingAuditedFV)} 与 G9-2 期末审定合计 ${fmt(fv.detailClosingAdjustedTotal.value)} 差异 ${fmt(fv.crossRefVariance.value)}`"
    />

    <div
      v-if="fv.diffWarningLevel.value !== 'none' || fv.exceedsB15.value"
      class="diff-warn-bar"
      :class="(fv.diffWarningLevel.value === 'hard' || fv.exceedsB15.value) ? 'is-hard' : 'is-soft'"
      data-testid="g9-fv-diff-warn"
    >
      <div class="diff-warn-head">
        <span>{{ (fv.diffWarningLevel.value === 'hard' || fv.exceedsB15.value) ? '差异偏高' : '差异关注' }}</span>
        <span>相对未审合计 {{ fv.diffRatioPct.value }}%</span>
        <span>差异合计 {{ fmt(fv.totals.value.fairValueDiff) }}</span>
        <span v-if="fv.performanceMateriality.value > 0">
          B15 {{ fmt(fv.performanceMateriality.value) }}
          <template v-if="fv.exceedsB15.value">（已超）</template>
        </span>
        <span v-else-if="fv.pmLoading.value">B15 加载中…</span>
        <el-button
          v-else-if="projectId && !isReadonly"
          link
          type="primary"
          size="small"
          @click="fv.loadPerformanceMateriality()"
        >拉取 B15</el-button>
      </div>
      <p class="diff-warn-hint">
        <template v-if="fv.exceedsB15.value">
          差异合计超过实际执行重要性（B15），请追查原因并考虑推送 G9-3 调整分录。
        </template>
        <template v-else-if="fv.diffWarningLevel.value === 'hard'">
          差异≥未审合计 20%，请追查原因并考虑推送 G9-3 调整分录。
        </template>
        <template v-else>
          差异≥未审合计 5%，请核实数量/价格影响并填写差异原因。
        </template>
      </p>
    </div>

    <el-alert
      v-if="fv.l3ValidationSummary.value.length"
      type="error"
      :closable="false"
      show-icon
      class="validation-alert"
      title="以下项目校验未通过"
    >
      <ul class="validation-list">
        <li v-for="item in fv.l3ValidationSummary.value" :key="item.row.rowId">
          {{ item.row.assetName || `第${item.row.seq}行` }}（{{ item.row.fairValueLevel }}）：缺少{{ item.errors.join('、') }}
        </li>
      </ul>
    </el-alert>

    <el-segmented
      v-model="fv.activeTab.value"
      :options="[{ label: '基础+审定', value: 'basic' }, { label: '估值详情', value: 'detail' }]"
      size="small"
    />
    <div class="table-actions">
      <el-button v-if="!isReadonly" size="small" @click="fv.addRow()">+ 新增</el-button>
    </div>

    <el-table
      :data="fv.rows.value"
      border
      size="small"
      style="font-size:13px"
      max-height="480"
      highlight-current-row
      @current-change="onRowChange"
    >
      <el-table-column prop="seq" label="#" width="44" align="center" fixed />
      <el-table-column label="资产名称" min-width="110" fixed>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.assetName"
            size="small"
            @update:model-value="(v: string) => fv.updateRow(row.rowId, { assetName: v })"
          />
          <span v-else>{{ row.assetName }}</span>
        </template>
      </el-table-column>

      <template v-if="fv.activeTab.value === 'basic'">
        <el-table-column label="投资日" width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.initialInvestDate"
              size="small"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { initialInvestDate: v })"
            />
            <span v-else>{{ row.initialInvestDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数量" width="88" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.closingUnadjustedQty"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => fv.updateRow(row.rowId, { closingUnadjustedQty: v ?? 0 })"
            />
            <span v-else>{{ row.closingUnadjustedQty }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审单价" width="88" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.closingUnadjustedPrice"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => fv.updateRow(row.rowId, { closingUnadjustedPrice: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.closingUnadjustedPrice) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审FV" width="96" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="有数量/单价时 = 数量×单价">{{ fmt(row.closingUnadjustedFV) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数量" width="88" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.closingAuditedQty"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => fv.updateRow(row.rowId, { closingAuditedQty: v ?? 0 })"
            />
            <span v-else>{{ row.closingAuditedQty }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定单价" width="88" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.closingAuditedPrice"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => fv.updateRow(row.rowId, { closingAuditedPrice: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.closingAuditedPrice) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定FV" width="96" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="有数量/单价时 = 数量×单价">{{ fmt(row.closingAuditedFV) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异" width="88" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="差异 = 审定FV − 未审FV" :style="fv.getDiffCellStyle(row)">
              {{ fmt(row.fairValueDiff) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="数量影响" width="88" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(row.qtyImpact) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="价格影响" width="88" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(row.priceImpact) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异原因" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.diffReason"
              size="small"
              type="textarea"
              :rows="1"
              :class="{ 'reason-required': fv.hasDifference(row) && !row.diffReason }"
              :placeholder="fv.hasDifference(row) ? '差异>0.01，必填' : ''"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { diffReason: v })"
            />
            <span v-else>{{ row.diffReason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="层次" width="96">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.fairValueLevel"
              size="small"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { fairValueLevel: v })"
            >
              <el-option v-for="o in fv.fvLevelOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <el-tag
              v-else
              size="small"
              :type="row.fairValueLevel === 'Level3' ? 'danger' : row.fairValueLevel === 'Level2' ? 'warning' : 'success'"
            >{{ row.fairValueLevel }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="估值方法" width="100">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.valuationMethod"
              size="small"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { valuationMethod: v })"
            >
              <el-option v-for="o in fv.valuationMethodOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.valuationMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="与上期一致" width="96">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.methodConsistentWithPrior"
              size="small"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { methodConsistentWithPrior: v })"
            >
              <el-option label="是" value="yes" /><el-option label="否" value="no" />
            </el-select>
            <span v-else>{{ row.methodConsistentWithPrior === 'yes' ? '是' : '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="64" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="fv.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="估值技术" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.valuationTechnique"
              size="small"
              :class="{ 'l3-required': row.fairValueLevel === 'Level3' && !row.valuationTechnique }"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { valuationTechnique: v })"
            />
            <span v-else>{{ row.valuationTechnique }}</span>
          </template>
        </el-table-column>
        <el-table-column label="不可观察输入值" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.unobservableInputDesc"
              size="small"
              type="textarea"
              :rows="1"
              :class="{ 'l3-required': row.fairValueLevel === 'Level3' && !row.unobservableInputDesc }"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { unobservableInputDesc: v })"
            />
            <span v-else>{{ row.unobservableInputDesc }}</span>
          </template>
        </el-table-column>
        <el-table-column label="输入值" width="96">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.unobservableInputValue"
              size="small"
              :class="{ 'l3-required': row.fairValueLevel === 'Level3' && !row.unobservableInputValue }"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { unobservableInputValue: v })"
            />
            <span v-else>{{ row.unobservableInputValue }}</span>
          </template>
        </el-table-column>
        <el-table-column label="估值来源" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.valuationSource"
              size="small"
              :class="{ 'l3-required': row.fairValueLevel === 'Level2' && !row.valuationSource }"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { valuationSource: v })"
            />
            <span v-else>{{ row.valuationSource }}</span>
          </template>
        </el-table-column>
        <el-table-column label="输入值来源" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.inputSourceAndAdjustment"
              size="small"
              type="textarea"
              :rows="1"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { inputSourceAndAdjustment: v })"
            />
            <span v-else>{{ row.inputSourceAndAdjustment }}</span>
          </template>
        </el-table-column>
        <el-table-column label="非流动性折扣" width="108" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.nonLiquidityDiscount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => fv.updateRow(row.rowId, { nonLiquidityDiscount: v ?? 0 })"
            />
            <span v-else>{{ row.nonLiquidityDiscount }}</span>
          </template>
        </el-table-column>
        <el-table-column label="底稿索引" width="96">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.valuationDocIndex"
              size="small"
              :class="{ 'l3-required': row.fairValueLevel === 'Level3' && !row.valuationDocIndex }"
              @update:model-value="(v: string) => fv.updateRow(row.rowId, { valuationDocIndex: v })"
            />
            <span v-else>{{ row.valuationDocIndex }}</span>
          </template>
        </el-table-column>
      </template>
    </el-table>

    <div class="summary-bar">
      <span class="sum-item">未审合计 <strong>{{ fmt(fv.totals.value.closingUnadjustedFV) }}</strong></span>
      <span class="sum-item">审定合计 <strong>{{ fmt(fv.totals.value.closingAuditedFV) }}</strong></span>
      <span class="sum-item" :class="{ 'sum-diff': Math.abs(fv.totals.value.fairValueDiff) > 0.01 }">
        差异合计 <strong>{{ fmt(fv.totals.value.fairValueDiff) }}</strong>
      </span>
    </div>

    <G9AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      :conclusion="fv.conclusion.value"
      @update:conclusion="(v: string) => fv.updateConclusion(v)"
      note-ai-section="fair-value-note"
      conclusion-ai-section="fair-value-conclusion"
      note-placeholder="填写审计说明：可概述公允价值取数来源、层次划分依据、数量/价格差异原因、估值技术与不可观察输入值核对情况。"
      note-hint="覆盖层次划分、估值技术、不可观察输入值及与 G9-2 / G9-5 / 附注勾稽。"
      :related-context="{
        行数: fv.rows.value.length,
        差异项: fv.diffCount.value,
        Level3: fv.levelSummary.value.Level3,
      }"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G9ImportExportDropdown from '../G9ImportExportDropdown.vue'
import G9AuditTextCards from '../G9AuditTextCards.vue'
import { useG9FairValueTest } from '../../composables/useG9FairValueTest'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const fv = useG9FairValueTest({
  wpId: toRef(props, 'wpId'),
  projectId: computed(() => props.projectId || ''),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

function onImported() { emit('imported') }

function onRowChange(row: { rowId?: string } | null) {
  if (!row?.rowId) return
  const idx = fv.rows.value.findIndex((r) => r.rowId === row.rowId)
  if (idx >= 0) fv.activeRowIndex.value = idx
}

async function onPushDiff(): Promise<void> {
  const n = await fv.pushDiffToAdjustment()
  if (n <= 0) return
  try {
    await ElMessageBox.confirm(
      `已推送 ${n} 笔公允差异调整。请到 G9-3 查看分录并确认回写 G9-1。`,
      '已推送至 G9-3',
      { type: 'success', confirmButtonText: '知道了', showCancelButton: false },
    )
  } catch { /* ignore */ }
}

async function onMarkProcedure(): Promise<void> {
  await fv.markProcedureComplete()
}

function fmt(n: number): string {
  if (!Number.isFinite(n)) return '0.00'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const NOTE_KEY = 'G9-fairvalue-audit-note'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) {
    props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
  }
})
</script>

<style scoped>
.g9-fv { font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
.audit-objective { margin-bottom: 10px; }
.toolbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.methodology { flex: 1; min-width: 200px; border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; }
.head-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.cross-ref-alert, .validation-alert { margin-bottom: 8px; }
.validation-list { margin: 4px 0 0; padding-left: 18px; }
.diff-warn-bar { margin-bottom: 8px; padding: 8px 12px; border-radius: 4px; }
.diff-warn-bar.is-soft { background: #fdf6ec; border: 1px solid #e6a23c; }
.diff-warn-bar.is-hard { background: #fef0f0; border: 1px solid #f56c6c; }
.diff-warn-head { display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; font-weight: 600; }
.diff-warn-hint { margin: 6px 0 0; font-size: 12px; color: #606266; }
.table-actions { margin: 8px 0; }
.l3-required :deep(.el-input__wrapper),
.reason-required :deep(.el-textarea__inner) { box-shadow: 0 0 0 1px #f56c6c inset; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; background: #f5f7fa; display: inline-block; width: 100%; }
.summary-bar { display: flex; gap: 16px; margin: 10px 0; flex-wrap: wrap; font-size: 13px; }
.sum-item.sum-diff { color: #f56c6c; }
.chip-wrap { display: inline-flex; }
</style>
