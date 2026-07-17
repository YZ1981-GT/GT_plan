<template>
  <div class="f2-val-sheet f2-contract-cost">
    <header class="sheet-header">
      <div>
        <h3>合同履约成本构成明细表</h3>
        <span class="code">F2-55</span>
      </div>
      <div class="stat-row">
        <span class="stat">期末账面 {{ fmt(cc.columnTotals.value.end_subtotal) }}</span>
        <span class="stat sub">审定合计 {{ fmt(cc.columnTotals.value.audited_subtotal) }}</span>
        <el-tag v-if="cc.highlightCount.value" type="warning" size="small">
          关注 {{ cc.highlightCount.value }} 项
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 按项目列示合同履约成本期初、增加、减少、期末构成（设备材料/建安分包/人工/其他）。</p>
        <p>2. 期末 = 期初 + 增加 − 减少；审定 = 期末 + 审计调整（紫色/灰色列为自动计算）。</p>
        <p>3. 核对合同台账一致性、履约进度结转及资本化三条件（直接相关、能收回）。</p>
        <p>4. 审定合计应与科目 1410 余额勾稽一致。</p>
      </div>
    </details>

    <el-alert type="info" :closable="false" :title="objectiveText" class="objective-alert" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="cc.addProduct()">+ 项目</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-55"
          :disabled="isReadonly"
          ai-section="contract-cost-note"
          :existing-content="cc.auditNote.value"
          review-section="F2-55-detail"
          @ai-filled="(t: string) => { cc.auditNote.value = t }"
        />
        <GtIndexChip value="wp:F2-55" />
        <el-tag size="small" type="info">{{ cc.enrichedProducts.value.length }} 个项目</el-tag>
      </div>
    </div>

    <div class="table-scroll">
      <table class="matrix-table">
        <thead>
          <tr>
            <th rowspan="2" class="sticky col-code">项目编号</th>
            <th rowspan="2" class="sticky col-name">项目名称</th>
            <th rowspan="2" class="sticky col-contract">收入合同名称</th>
            <th rowspan="2" class="sticky col-amt">收入合同金额</th>
            <th colspan="5" class="grp grp-open">账面期初余额</th>
            <th colspan="5" class="grp grp-inc">账面本期增加</th>
            <th colspan="5" class="grp grp-dec">账面本期减少</th>
            <th colspan="5" class="grp grp-end">账面期末余额</th>
            <th rowspan="2" class="col-flag">合同<br>台账</th>
            <th rowspan="2" class="col-flag">履约<br>进度</th>
            <th rowspan="2" class="col-flag">直接<br>相关</th>
            <th rowspan="2" class="col-flag">能收回</th>
            <th colspan="5" class="grp grp-adj">审计调整</th>
            <th colspan="5" class="grp grp-aud">期末审定余额</th>
            <th rowspan="2" class="col-remark">备注</th>
            <th rowspan="2" class="col-act" />
          </tr>
          <tr>
            <template v-for="grp in periodGroups" :key="grp">
              <th
                v-for="cat in costCategories"
                :key="`${grp}-${cat.key}`"
                class="sub"
                :class="{ emphasis: cat.emphasis }"
              >{{ cat.label }}</th>
              <th class="sub total">小计</th>
            </template>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in cc.enrichedProducts.value"
            :key="row.id"
            :class="{ 'row-warn': row.highlight }"
          >
            <td class="sticky col-code">
              <el-input v-if="!isReadonly" :model-value="row.projectCode" size="small"
                @update:model-value="(v: string) => cc.updateProduct(row.id, { projectCode: v })" />
              <span v-else>{{ row.projectCode || '—' }}</span>
            </td>
            <td class="sticky col-name">
              <el-input v-if="!isReadonly" :model-value="row.projectName" size="small"
                @update:model-value="(v: string) => cc.updateProduct(row.id, { projectName: v })" />
              <span v-else>{{ row.projectName || '—' }}</span>
            </td>
            <td class="sticky col-contract">
              <el-input v-if="!isReadonly" :model-value="row.contractName" size="small"
                @update:model-value="(v: string) => cc.updateProduct(row.id, { contractName: v })" />
              <span v-else>{{ row.contractName || '—' }}</span>
            </td>
            <td class="sticky col-amt">
              <el-input-number v-if="!isReadonly" :model-value="row.contractAmount" size="small" :controls="false"
                class="compact-num wide"
                @change="(v: number | undefined) => cc.updateProduct(row.id, { contractAmount: v ?? 0 })" />
              <span v-else class="auto">{{ fmt(row.contractAmount) }}</span>
            </td>

            <!-- 期初 -->
            <template v-for="cat in costCategories" :key="`o-${row.id}-${cat.key}`">
              <td>
                <el-input-number v-if="!isReadonly" :model-value="num(row, 'opening', cat.key)" size="small"
                  :controls="false" class="compact-num"
                  @change="(v: number | undefined) => cc.updatePeriodAmount(row.id, 'opening', cat.key, v ?? 0)" />
                <span v-else class="auto">{{ fmt(num(row, 'opening', cat.key)) }}</span>
              </td>
            </template>
            <td class="auto calc">{{ fmt(row.opening_subtotal) }}</td>

            <!-- 增加 -->
            <template v-for="cat in costCategories" :key="`i-${row.id}-${cat.key}`">
              <td>
                <el-input-number v-if="!isReadonly" :model-value="num(row, 'increase', cat.key)" size="small"
                  :controls="false" class="compact-num"
                  @change="(v: number | undefined) => cc.updatePeriodAmount(row.id, 'increase', cat.key, v ?? 0)" />
                <span v-else class="auto">{{ fmt(num(row, 'increase', cat.key)) }}</span>
              </td>
            </template>
            <td class="auto calc">{{ fmt(row.increase_subtotal) }}</td>

            <!-- 减少 -->
            <template v-for="cat in costCategories" :key="`d-${row.id}-${cat.key}`">
              <td>
                <el-input-number v-if="!isReadonly" :model-value="num(row, 'decrease', cat.key)" size="small"
                  :controls="false" class="compact-num"
                  @change="(v: number | undefined) => cc.updatePeriodAmount(row.id, 'decrease', cat.key, v ?? 0)" />
                <span v-else class="auto">{{ fmt(num(row, 'decrease', cat.key)) }}</span>
              </td>
            </template>
            <td class="auto calc">{{ fmt(row.decrease_subtotal) }}</td>

            <!-- 期末（自动） -->
            <template v-for="cat in costCategories" :key="`e-${row.id}-${cat.key}`">
              <td class="auto calc grp-end-cell">{{ fmt(endVal(row, cat.key)) }}</td>
            </template>
            <td class="auto calc grp-end-cell">{{ fmt(row.end_subtotal) }}</td>

            <!-- 核查 -->
            <td v-for="flag in flagFields" :key="`${row.id}-${flag.key}`" class="col-flag">
              <el-select v-if="!isReadonly" :model-value="row[flag.key] || undefined" size="small" clearable
                @update:model-value="(v: string) => cc.updateProduct(row.id, { [flag.key]: v || '' })">
                <el-option label="是" value="是" /><el-option label="否" value="否" />
              </el-select>
              <span v-else>{{ row[flag.key] || '—' }}</span>
            </td>

            <!-- 审计调整 -->
            <template v-for="cat in costCategories" :key="`a-${row.id}-${cat.key}`">
              <td>
                <el-input-number v-if="!isReadonly" :model-value="num(row, 'adj', cat.key)" size="small"
                  :controls="false" class="compact-num"
                  @change="(v: number | undefined) => cc.updatePeriodAmount(row.id, 'adj', cat.key, v ?? 0)" />
                <span v-else class="auto">{{ fmt(num(row, 'adj', cat.key)) }}</span>
              </td>
            </template>
            <td class="auto calc">{{ fmt(row.adj_subtotal) }}</td>

            <!-- 审定（自动） -->
            <template v-for="cat in costCategories" :key="`u-${row.id}-${cat.key}`">
              <td class="auto calc grp-aud-cell">{{ fmt(auditedVal(row, cat.key)) }}</td>
            </template>
            <td class="auto calc grp-aud-cell aud-total">{{ fmt(row.audited_subtotal) }}</td>

            <td class="col-remark">
              <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
                @update:model-value="(v: string) => cc.updateProduct(row.id, { remark: v })" />
              <span v-else class="remark-text">{{ row.remark || '—' }}</span>
            </td>
            <td class="col-act">
              <el-button v-if="!isReadonly" link type="danger" size="small" @click="cc.removeProduct(row.id)">删</el-button>
            </td>
          </tr>

          <tr class="row-total">
            <td colspan="3" class="sticky col-name">合计</td>
            <td class="sticky auto">{{ fmt(cc.columnTotals.value.contractAmount) }}</td>
            <td :colspan="4" />
            <td class="auto">{{ fmt(cc.columnTotals.value.opening_subtotal) }}</td>
            <td :colspan="4" />
            <td class="auto">{{ fmt(cc.columnTotals.value.increase_subtotal) }}</td>
            <td :colspan="4" />
            <td class="auto">{{ fmt(cc.columnTotals.value.decrease_subtotal) }}</td>
            <td :colspan="4" />
            <td class="auto calc">{{ fmt(cc.columnTotals.value.end_subtotal) }}</td>
            <td colspan="4" />
            <td :colspan="4" />
            <td class="auto">{{ fmt(cc.columnTotals.value.adj_subtotal) }}</td>
            <td :colspan="4" />
            <td class="auto calc aud-total">{{ fmt(cc.columnTotals.value.audited_subtotal) }}</td>
            <td colspan="2" />
          </tr>
        </tbody>
      </table>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header><span class="opinion-title">1、审计说明</span></template>
      <el-input v-model="cc.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="说明构成完整性、计量准确性、资本化条件及与1410科目勾稽..." />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header><span class="opinion-title">2、审计结论</span></template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="A、未见异常。B、除上述应调整事项外，其余未见异常。C、不可确认。"
        @update:model-value="saveAuditConclusion" />
    </el-card>

    <div class="tips-box">
      <div class="tips-title">提示</div>
      <ol>
        <li v-for="(tip, i) in tips" :key="i">{{ tip }}</li>
      </ol>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, toRef } from 'vue'
import { useF2ContractCost } from '../../composables/useF2ContractCost'
import {
  CONTRACT_COST_CATEGORIES,
  F2_55_DEFAULT_OBJECTIVE,
  F2_55_TIPS,
  type EnrichedContractCost,
  type CostCategoryKey,
  type ContractCostProject,
} from '../../composables/useF2ContractCostFormulas'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const cc = useF2ContractCost({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const objectiveText = F2_55_DEFAULT_OBJECTIVE
const tips = F2_55_TIPS
const costCategories = CONTRACT_COST_CATEGORIES
const periodGroups = ['opening', 'increase', 'decrease', 'end', 'adj', 'audited'] as const

const flagFields: { key: keyof ContractCostProject; label: string }[] = [
  { key: 'matchesLedger', label: '合同台账' },
  { key: 'carriedByProgress', label: '履约进度' },
  { key: 'isDirectlyRelated', label: '直接相关' },
  { key: 'isRecoverable', label: '能收回' },
]

const CONCLUSION_KEY = 'F2-55-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

type Period = 'opening' | 'increase' | 'decrease' | 'adj'

function num(row: ContractCostProject, period: Period, key: CostCategoryKey): number {
  return Number(row[`${period}_${key}`] || 0)
}

function endVal(row: EnrichedContractCost, key: CostCategoryKey): number {
  return Number(row[`end_${key}`] || 0)
}

function auditedVal(row: EnrichedContractCost, key: CostCategoryKey): number {
  return Number(row[`audited_${key}`] || 0)
}

function fmt(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped src="../../f2/valuation/f2ValSheetStyles.css"></style>
<style scoped>
.f2-contract-cost { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; }
.tab-toolbar { display: flex; gap: 8px; }
.formula { text-decoration: underline dotted #909399; cursor: help; }

.table-scroll { overflow-x: auto; margin-bottom: 12px; }
.matrix-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 10px;
  min-width: 3400px;
}
.matrix-table th,
.matrix-table td {
  border: 1px solid #d4c8e0;
  padding: 2px 2px;
  text-align: center;
  vertical-align: middle;
  background: #fff;
}
.matrix-table thead th {
  background: var(--gt-purple-soft);
  color: #3d2a55;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 2;
}
.matrix-table th.sub { font-weight: 500; font-size: 9px; white-space: nowrap; }
.matrix-table th.sub.emphasis { color: #c45656; }
.grp-open { background: #f8f6fa !important; }
.grp-inc { background: #eef5fc !important; }
.grp-dec { background: #fdf6ec !important; }
.grp-end { background: #f3eef8 !important; }
.grp-adj { background: #fef0f0 !important; }
.grp-aud { background: #f0f9eb !important; }
.grp-end-cell { background: #faf8fc !important; }
.grp-aud-cell { background: #f6fff3 !important; }
.th.sub.total, th.sub.total { font-weight: 600; }

.sticky { position: sticky; left: 0; z-index: 3; background: #faf8fc !important; }
.col-code { left: 0; min-width: 72px; }
.col-name { left: 72px; min-width: 88px; text-align: left !important; padding-left: 4px !important; }
.col-contract { left: 160px; min-width: 96px; }
.col-amt { left: 256px; min-width: 88px; box-shadow: 2px 0 4px rgba(75, 45, 119, 0.08); }
.col-flag { min-width: 52px; }
.col-remark { min-width: 80px; }
.col-act { width: 36px; position: sticky; right: 0; z-index: 3; background: #fff !important; }

.row-total td { background: #f0ebf5 !important; font-weight: 600; }
.row-warn td { background: #fdf6ec !important; }
.auto { text-align: right; padding-right: 2px; white-space: nowrap; color: #606266; }
span.auto { display: block; }
.calc { color: #4b2d77; font-weight: 500; }
.aud-total { color: #67c23a; font-weight: 600; }
.remark-text { font-size: 10px; color: #909399; }

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
.tips-box ol { margin: 0; padding-left: 1.4em; }

:deep(.compact-num) { width: 62px; }
:deep(.compact-num.wide) { width: 80px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 2px; font-size: 10px; }
</style>
