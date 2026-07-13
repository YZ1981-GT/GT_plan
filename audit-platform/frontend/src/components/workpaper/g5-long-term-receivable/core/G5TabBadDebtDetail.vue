<template>
  <div class="g5-bad-debt-detail">
    <div class="section-head">
      <h3 class="sheet-title">G5-3 坏账准备明细表</h3>
      <div class="head-actions tab-toolbar">
        <GtIndexChip value="wp:G5-3" />
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
        <GtReviewTrigger section-id="g5-3-bad-debt-detail" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：复核长期应收款坏账准备的计提方式、损失率与计提金额，验证审定余额、审定坏账及净值勾稽，核对本年计提与转回。
    </el-alert>

    <!-- 区段Tab切换 -->
    <div class="segment-tabs">
      <el-segmented v-model="detail.activeTab.value" :options="tabOptions" size="small" />
      <div class="tab-actions">
        <el-button size="small" type="primary" plain @click="detail.addRow()" :disabled="props.readonly">
          + 新增
        </el-button>
      </div>
    </div>

    <!-- Tab1: 未审数+审计调整 -->
    <el-table
      v-show="detail.activeTab.value === 'unadjusted'"
      :data="detail.rows.value"
      :height="450"
      border stripe
      style="width: 100%; font-size: 13px"
      highlight-current-row
      @current-change="onRowChange"
    >
      <el-table-column type="index" label="序号" width="50" />
      <el-table-column prop="debtorOrGroup" label="债务人/组合" min-width="120" />
      <el-table-column prop="provisionMethod" label="计提方式" width="80">
        <template #default="{ row }">
          <el-select v-model="row.provisionMethod" size="small" :disabled="props.readonly">
            <el-option label="组合" value="group" />
            <el-option label="单项" value="individual" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="closingBalance" label="期末余额①" min-width="100" align="right" />
      <el-table-column prop="creditLossRate" label="损失率②" width="80" align="right">
        <template #default="{ row }">{{ (row.creditLossRate * 100).toFixed(2) }}%</template>
      </el-table-column>
      <el-table-column label="未审坏账③" min-width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="①×②">{{ fmt(row.unadjustedProvision) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="balanceAdjustment" label="余额调整⑤" min-width="90" align="right" />
      <el-table-column prop="adjustedLossRate" label="调整后率②A" width="80" align="right">
        <template #default="{ row }">{{ (row.adjustedLossRate * 100).toFixed(2) }}%</template>
      </el-table-column>
      <el-table-column label="坏账调整⑥" min-width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="⑤×②A+①×(②A-②)">{{ fmt(row.provisionAdjustment) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="adjustmentDesc" label="调整说明" min-width="100" />
      <el-table-column prop="indexRef" label="索引" width="60" />
    </el-table>

    <!-- Tab2: 审定数 -->
    <el-table
      v-show="detail.activeTab.value === 'adjusted'"
      :data="detail.rows.value"
      :height="450"
      border stripe
      style="width: 100%; font-size: 13px"
      highlight-current-row
      @current-change="onRowChange"
    >
      <el-table-column type="index" label="序号" width="50" />
      <el-table-column prop="debtorOrGroup" label="债务人/组合" min-width="120" />
      <el-table-column label="审定余额⑦" min-width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="①+⑤">{{ fmt(row.adjustedBalance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审定坏账⑧" min-width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="③+⑥">{{ fmt(row.adjustedProvision) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审定净值⑨" min-width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="⑦-⑧">{{ fmt(row.adjustedNetValue) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="priorYearProvision" label="上年坏账" min-width="90" align="right" />
      <el-table-column label="本年计提" min-width="90" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="⑧-上年+转回">{{ fmt(row.currentYearProvision) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="currentYearReversal" label="本年转回" min-width="80" align="right" />
      <el-table-column prop="remark" label="备注" min-width="100" />
    </el-table>

    <!-- 合计 -->
    <div class="totals-bar">
      审定余额合计: {{ fmt(detail.totals.value.adjustedBalance) }} |
      审定坏账合计: {{ fmt(detail.totals.value.adjustedProvision) }} |
      审定净值合计: {{ fmt(detail.totals.value.adjustedNetValue) }} |
      本年计提合计: {{ fmt(detail.totals.value.currentYearProvision) }}
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="props.readonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：可概述坏账准备计提方式、损失率合理性、审定坏账勾稽及本年计提/转回核对情况。"
        @change="(val: string) => saveAuditNote(val)" />
    </el-card>
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="props.readonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项，不可确认。"
        @change="(val: string) => saveAuditConclusion(val)" />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>未审坏账③ = 期末余额① × 损失率②</li>
        <li>坏账调整⑥ = 余额调整⑤ × 调整后率②A + ①×(②A − ②)，可为负（冲回）</li>
        <li>审定余额⑦ = ① + ⑤；审定坏账⑧ = ③ + ⑥；审定净值⑨ = ⑦ − ⑧</li>
        <li>本年计提 = ⑧ − 上年坏账 + 本年转回</li>
        <li>组合计提关注账龄损失率；单项计提关注现金流量现值（CAS 22 / ECL 模型）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, onMounted } from 'vue'
import { useG5BadDebtDetail } from '../../composables/useG5BadDebtDetail'
import { useG5LonRecFormData } from '../../composables/useG5LonRecFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  htmlData?: any
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const detail = useG5BadDebtDetail()

// ─── 审计说明 / 审计结论（持久化 checklist_responses，item_id 前缀 G5-）───
const g5Notes = useG5LonRecFormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const auditNote = ref('')
const auditConclusion = ref('')
const G5_NOTE_KEY = 'G5-3-audit-note'
const G5_CONCLUSION_KEY = 'G5-3-audit-conclusion'
function saveAuditNote(val: string): void {
  if (props.readonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}
function saveAuditConclusion(val: string): void {
  if (props.readonly) return
  auditConclusion.value = val
  void g5Notes.saveImmediate(G5_CONCLUSION_KEY, { conclusion: null, remark: val })
}
onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

const tabOptions = [
  { label: '未审数+审计调整', value: 'unadjusted' },
  { label: '审定数', value: 'adjusted' },
]

function onRowChange(row: any) {
  if (row) {
    const idx = detail.rows.value.findIndex(r => r.id === row.id)
    if (idx >= 0) detail.activeRowIndex.value = idx
  }
}

function fmt(v: number): string {
  return v?.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '-'
}
</script>

<style scoped>
.g5-bad-debt-detail { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 8px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
.segment-tabs { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.tab-actions { margin-left: auto; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.totals-bar { margin-top: 8px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-size: 12px; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
</style>
