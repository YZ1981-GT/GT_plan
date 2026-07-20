<template>
  <div class="g9-l3" data-testid="g9-l3-reconciliation">
    <div class="methodology">
      {{ FORMULA_HINT }}；「企业报告期末」与公式期末差异 &gt; 0.01 须核查说明。
    </div>

    <div class="section-head">
      <h3 class="sheet-title">G9-5 第三层次公允价值计量的调节表</h3>
      <div class="head-actions tab-toolbar">
        <G9ImportExportDropdown :wp-id="wpId" sheet="G9-5" @imported="onImported" />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="l3.addRow()">新增调节行</el-button>
        <el-button size="small" :disabled="isReadonly" @click="l3.pullFromDetail()">从 G9-2 带入</el-button>
        <el-button size="small" :disabled="isReadonly" @click="l3.pullFromFairValueTest()">从 G9-4 带入</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G9-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G9-4" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G9-5" /></span>
        <el-tag size="small" type="info">共 {{ l3.rows.value.length }} 行</el-tag>
        <GtReviewTrigger section-id="G9-5-l3" />
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：确定第三层次公允价值计量的调节过程披露是否恰当；验证期初至期末十因子变动完整、准确，公式期末与企业报告期末勾稽一致。"
    />

    <details class="audit-process" open>
      <summary>二、审计过程</summary>
      <ol>
        <li>获取第三层次公允价值计量的金融资产明细清单，验证加计是否正确（可自 G9-2 Level3 带入）。</li>
        <li>逐项填列期初、购入/处置、层次转入转出、计入损益/OCI 的公允价值变动、利息、减值及其他变动，核对公式期末。</li>
        <li>将公式期末与企业报告（或 G9-4 Level3 审定 FV）勾稽，差异须查明原因并记录。</li>
        <li>判断第三层次公允价值计量的调节过程披露是否恰当（与附注披露格式勾稽）。</li>
      </ol>
    </details>

    <el-alert
      v-if="l3.varianceRows.value.length"
      type="warning"
      :closable="false"
      class="var-alert"
      :title="`${l3.varianceRows.value.length} 行存在差异（企业报告期末 ≠ 公式期末）`"
    />
    <el-alert
      v-if="l3.unrealizedWarnings.value.length"
      type="warning"
      :closable="false"
      class="var-alert"
      :title="`仍持有未实现校验：${l3.unrealizedWarnings.value.map(w => `${w.assetName}（${w.reason}）`).join('；')}`"
    />
    <el-alert
      v-for="c in crossAlerts"
      :key="c.code"
      type="warning"
      :closable="false"
      class="var-alert"
      data-testid="g9-l3-cross-alert"
    >
      {{ c.message }}
      <el-button
        v-if="!isReadonly && (c.code === 'fv4-l3-total-vs-g95-reported' || c.code === 'fv4-vs-g95-asset')"
        link
        size="small"
        type="primary"
        @click="l3.pullFromFairValueTest()"
      >从 G9-4 带入</el-button>
      <el-button
        v-if="!isReadonly && c.code === 'detail-l3-vs-g95-reported'"
        link
        size="small"
        type="primary"
        @click="l3.pullFromDetail()"
      >从 G9-2 带入</el-button>
    </el-alert>

    <el-table :data="l3.rows.value" border size="small" class="l3-table" max-height="520">
      <el-table-column label="序号" width="52" fixed>
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>
      <el-table-column label="资产名称" min-width="120" fixed>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.assetName"
            size="small"
            @update:model-value="(v: string) => l3.updateRow(row.rowId, 'assetName', v)"
          />
          <span v-else>{{ row.assetName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初公允价值" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.openingFairValue"
            size="small"
            :controls="false"
            style="width:100%"
            @update:model-value="(v: number) => l3.updateRow(row.rowId, 'openingFairValue', v ?? 0)"
          />
          <span v-else>{{ fmt(row.openingFairValue) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="购买与处置" align="center">
        <el-table-column label="本期购入" width="88" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.purchaseAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => l3.updateRow(row.rowId, 'purchaseAmount', v ?? 0)"
            />
            <span v-else>{{ fmt(row.purchaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期处置" width="88" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.disposalAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => l3.updateRow(row.rowId, 'disposalAmount', v ?? 0)"
            />
            <span v-else>{{ fmt(row.disposalAmount) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="转入/转出第三层次" align="center">
        <el-table-column label="转入" width="80" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.transferIn"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => l3.updateRow(row.rowId, 'transferIn', v ?? 0)"
            />
            <span v-else>{{ fmt(row.transferIn) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转出" width="80" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.transferOut"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => l3.updateRow(row.rowId, 'transferOut', v ?? 0)"
            />
            <span v-else>{{ fmt(row.transferOut) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="当期利得或损失" align="center">
        <el-table-column label="FV损益" width="88" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.fvChangePL"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => l3.updateRow(row.rowId, 'fvChangePL', v ?? 0)"
            />
            <span v-else>{{ fmt(row.fvChangePL) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="FV(OCI)" width="88" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.fvChangeOCI"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => l3.updateRow(row.rowId, 'fvChangeOCI', v ?? 0)"
            />
            <span v-else>{{ fmt(row.fvChangeOCI) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="利息" width="80" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.interestIncome"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => l3.updateRow(row.rowId, 'interestIncome', v ?? 0)"
            />
            <span v-else>{{ fmt(row.interestIncome) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值" width="80" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.impairmentLoss"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => l3.updateRow(row.rowId, 'impairmentLoss', v ?? 0)"
            />
            <span v-else>{{ fmt(row.impairmentLoss) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="其他变动" width="80" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.otherChanges"
            size="small"
            :controls="false"
            style="width:100%"
            @update:model-value="(v: number) => l3.updateRow(row.rowId, 'otherChanges', v ?? 0)"
          />
          <span v-else>{{ fmt(row.otherChanges) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末(公式)" width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" :title="FORMULA_HINT">{{ fmt(row.closingFairValue) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="仍持有未实现" width="120" align="right">
        <template #header>
          <el-tooltip
            content="对于在报告期末持有的资产，计入损益的当期未实现利得或损失的变动（CAS 39 披露项，不进期末公式）"
            placement="top"
          >
            <span>仍持有未实现</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.unrealizedHeld"
            size="small"
            :controls="false"
            style="width:100%"
            :class="{ 'uh-warn': hasUnrealizedWarn(row.rowId) }"
            @update:model-value="(v: number) => l3.updateRow(row.rowId, 'unrealizedHeld', v ?? 0)"
          />
          <span v-else :class="{ 'var-warn': hasUnrealizedWarn(row.rowId) }">{{ fmt(row.unrealizedHeld) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="企业报告" width="96" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.reportedClosing"
            size="small"
            :controls="false"
            style="width:100%"
            @update:model-value="(v: number) => l3.updateRow(row.rowId, 'reportedClosing', v ?? 0)"
          />
          <span v-else>{{ fmt(row.reportedClosing) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="差异" width="88" align="right">
        <template #default="{ row }">
          <span :class="{ 'var-warn': row.varianceHighlight }">{{ fmt(row.variance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            size="small"
            placeholder="转入转出原因/差异说明"
            @update:model-value="(v: string) => l3.updateRow(row.rowId, 'remark', v)"
          />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="l3.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals-row" data-testid="g9-l3-totals">
      <span class="total-label">合计</span>
      <span>期初 {{ fmt(l3.totals.value.openingFairValue) }}</span>
      <span>购入 {{ fmt(l3.totals.value.purchaseAmount) }}</span>
      <span>处置 {{ fmt(l3.totals.value.disposalAmount) }}</span>
      <span>转入 {{ fmt(l3.totals.value.transferIn) }}</span>
      <span>转出 {{ fmt(l3.totals.value.transferOut) }}</span>
      <span>FV损益 {{ fmt(l3.totals.value.fvChangePL) }}</span>
      <span>FV(OCI) {{ fmt(l3.totals.value.fvChangeOCI) }}</span>
      <span>公式期末 {{ fmt(l3.totals.value.closingFairValue) }}</span>
      <span>仍持有未实现 {{ fmt(l3.totals.value.unrealizedHeld) }}</span>
      <span>企业报告 {{ fmt(l3.totals.value.reportedClosing) }}</span>
      <span :class="{ 'var-warn': Math.abs(l3.totals.value.variance) > 0.01 }">
        差异 {{ fmt(l3.totals.value.variance) }}
      </span>
    </div>

    <G9AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      :conclusion="l3.conclusion.value"
      @update:conclusion="(v: string) => l3.updateConclusion(v)"
      note-ai-section="l3-note"
      conclusion-ai-section="l3-reconciliation-conclusion"
      note-placeholder="填写审计说明：可概述 L3 十因子取数与核对、层次转入转出原因、公式期末与企业报告/G9-4 勾稽、仍持有未实现及差异原因；并评价调节过程披露是否恰当。"
      note-hint="覆盖十因子勾稽、层次转移、仍持有未实现及与 G9-4 / 附注勾稽。"
      :related-context="{
        行数: l3.rows.value.length,
        差异行数: l3.varianceRows.value.length,
        未实现告警数: l3.unrealizedWarnings.value.length,
        合计: l3.totals.value,
      }"
    />

    <details class="methodology-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>{{ FORMULA_HINT }}，系统自动计算期末；差异 = 公式期末 − 企业报告期末。</li>
        <li>「仍持有未实现」对齐 CAS 39 / 纸质底稿披露项，不进入期末公式；有期末余额且本期有 FV 损益时通常应填列。</li>
        <li>本表采用十因子模型（相对交易性金融资产 G1-7）：增加 FV(OCI)、利息、减值，以覆盖其他非流动金融资产混合计量（FVTPL / FVOCI / 含减值情形）。</li>
        <li>优先「从 G9-2 带入」拉取 Level3 明细变动；「从 G9-4 带入」补填企业报告期末勾稽。</li>
        <li>转入/转出第三层次须在备注说明触发层次调整的原因；FV(损益) 与 FV(OCI) 不得混淆。</li>
        <li>估值方法、不可观察输入值、敏感性分析在 G9-4 记录；本表聚焦期初至期末数量金额调节及披露勾稽。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, ref, watch } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G9ImportExportDropdown from '../G9ImportExportDropdown.vue'
import G9AuditTextCards from '../G9AuditTextCards.vue'
import { useG9L3Reconciliation, G9_L3_FORMULA_HINT } from '../../composables/useG9L3Reconciliation'
import { buildG9CrossChecks } from '../../composables/g9CrossHelpers'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const FORMULA_HINT = G9_L3_FORMULA_HINT

const l3 = useG9L3Reconciliation({
  wpId: toRef(props, 'wpId'),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

const crossAlerts = computed(() =>
  buildG9CrossChecks(props.allResponses).filter((c) =>
    c.code === 'fv4-l3-total-vs-g95-reported'
    || c.code === 'detail-l3-vs-g95-reported'
    || c.code === 'fv4-vs-g95-asset',
  ),
)

function onImported() { emit('imported') }

function hasUnrealizedWarn(rowId: string): boolean {
  return l3.unrealizedWarnings.value.some((w) => w.rowId === rowId)
}

function fmt(v: unknown): string {
  if (typeof v !== 'number' || Number.isNaN(v)) return String(v ?? '')
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const NOTE_KEY = 'G9-l3-audit-note'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) {
    props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
  }
})
</script>

<style scoped>
.g9-l3 { font-size: var(--wp-font-size, 13px); padding: 4px 0; }
.g9-l3 :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.methodology {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 8px 12px;
  margin-bottom: 10px;
  font-size: 12px;
  color: #606266;
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; color: #1f2a37; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  background: #f5f7fa;
  display: inline-block;
  width: 100%;
  text-align: right;
}
.methodology-hint { margin-top: 12px; font-size: 12px; color: #606266; }
.methodology-hint summary { cursor: pointer; }
.methodology-hint ul { margin: 8px 0 0; padding-left: 18px; }
.var-warn { color: #f56c6c; font-weight: 600; }
.uh-warn :deep(.el-input__inner) { color: #e6a23c; font-weight: 600; }
.var-alert { margin-bottom: 8px; }
.totals-row {
  margin-top: 8px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #303133;
}
.total-label { margin-right: 4px; }
.audit-objective { margin: 8px 0; }
.audit-process {
  margin-bottom: 10px;
  padding: 8px 12px;
  background: #f8f9fb;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 12px;
  color: #606266;
}
.audit-process summary { cursor: pointer; font-weight: 500; color: #303133; }
.audit-process ol { margin: 6px 0 0; padding-left: 18px; }
</style>
