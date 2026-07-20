<template>
  <div class="g9-detail" data-testid="g9-detail-table">
    <div class="toolbar">
      <div class="title-block">
        <h3>G9-2 明细表</h3>
        <p class="sheet-sub">分类计量明细 → 期初/变动/期末勾稽 → 分类合计回写 G9-1</p>
      </div>
      <div class="head-actions tab-toolbar">
        <span class="chip-wrap"><GtIndexChip value="wp:G9-1" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G9-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G9-4" /></span>
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
        <G9ImportExportDropdown :wp-id="wpId" sheet="G9-2" @imported="onImported" />
        <GtReviewTrigger section-id="G9-2-detail" />
      </div>
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 按 CAS 22：FVTPL / FVOCI / 摊余成本分类须与合同现金流量特征及业务模式一致。</p>
        <p>2. 期初审定 = 期初 + 期初调整；期末余额 = 期初审定 + 增加 − 减少 + FV + 利息 − 减值 + OCI；审定 = 期末 + 调整。</p>
        <p>3. 可「辅助核算取数」从 1504 带入；「回写 G9-1」按分类合计写入各组首行未审数。</p>
        <p>4. Level3 须填估值方法，并在 G9-4 补充估值技术与不可观察输入值；可带入 G9-5。</p>
        <p>5. 「工具种类」「指定FVTPL」供附注分项带入；分类非 FVTPL 时指定标记自动清除。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：核对其他非流动金融资产明细的存在、计价与分类，期末审定合计应与 G9-1 审定表勾稽一致。"
    />

    <div class="adj-toolbar">
      <el-button v-if="!isReadonly" size="small" type="primary" @click="detail.addRow()">+ 新增行</el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        plain
        :loading="detail.auxLoading.value"
        :disabled="!projectId"
        data-testid="g9-detail-aux"
        @click="onSeedAux"
      >
        辅助核算取数
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="success"
        plain
        :disabled="!detail.rows.value.length"
        data-testid="g9-detail-push-adj"
        @click="detail.pushTotalsToAdjudication()"
      >
        ↑ 回写 G9-1
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        plain
        data-testid="g9-detail-fv-oci"
        @click="onFillOci"
      >
        FVOCI：FV→OCI
      </el-button>
      <el-tag v-if="detail.level3MissingMethodCount.value" size="small" type="danger">
        L3缺估值方法 {{ detail.level3MissingMethodCount.value }}
      </el-tag>
    </div>

    <el-alert
      v-if="detail.hasAdjCrossMismatch.value"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g9-detail-adj-cross"
      :title="`明细审定合计 ${fmt(detail.totals.value.closingAdjusted)} 与 G9-1 审定合计 ${fmt(detail.adjudicationClosingTotal.value ?? 0)} 差异 ${fmt(detail.adjCrossVariance.value ?? 0)}`"
    />

    <el-alert
      v-if="detail.integrityIssues.value.length"
      type="error"
      :closable="false"
      show-icon
      class="cross-alert"
      title="以下明细行校验未通过"
    >
      <ul class="issue-list">
        <li v-for="(item, i) in detail.integrityIssues.value.slice(0, 8)" :key="`${item.rowId}-${i}`">
          {{ item.assetName }}：{{ item.message }}
        </li>
        <li v-if="detail.integrityIssues.value.length > 8">…共 {{ detail.integrityIssues.value.length }} 项</li>
      </ul>
    </el-alert>

    <el-segmented v-model="detail.activeTab.value" :options="tabOptions" size="small" />

    <el-table
      :data="detail.rows.value"
      border
      size="small"
      style="font-size:13px;margin-top:8px"
      max-height="520"
      highlight-current-row
      :current-row-key="detail.currentRowKey.value"
      row-key="rowId"
      @current-change="onRowChange"
    >
      <el-table-column prop="seq" label="#" width="44" align="center" fixed />
      <template v-if="detail.activeTab.value === 'basic'">
        <el-table-column label="资产名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.assetName" size="small" @update:model-value="(v: string) => detail.updateRow(row.rowId, { assetName: v })" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="108">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.classification" size="small" @update:model-value="(v: string) => detail.updateRow(row.rowId, { classification: v })">
              <el-option v-for="o in detail.classificationOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.classification }}</span>
          </template>
        </el-table-column>
        <el-table-column label="工具种类" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.instrumentType"
              size="small"
              clearable
              placeholder="选填"
              data-testid="g9-detail-instrument-type"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { instrumentType: v ?? '' })"
            >
              <el-option v-for="o in detail.instrumentTypeOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.instrumentType || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="指定FVTPL" width="88" align="center">
          <template #default="{ row }">
            <el-checkbox
              v-if="!isReadonly"
              :model-value="row.isDesignated"
              :disabled="row.classification !== 'FVTPL'"
              data-testid="g9-detail-is-designated"
              @update:model-value="(v: boolean | string | number) => detail.updateRow(row.rowId, { isDesignated: !!v })"
            />
            <span v-else>{{ row.isDesignated ? '是' : '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="初始投资日" width="108">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.initialInvestDate" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { initialInvestDate: v })" />
            <span v-else>{{ row.initialInvestDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="到期日" width="108">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.maturityDate" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { maturityDate: v })" />
            <span v-else>{{ row.maturityDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="面值/成本" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.faceValueOrCost" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { faceValueOrCost: v ?? 0 })" />
            <span v-else>{{ fmt(row.faceValueOrCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="持有数量" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.holdingQuantity" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { holdingQuantity: v ?? 0 })" />
            <span v-else>{{ row.holdingQuantity }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计量属性" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.measurementAttribute" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { measurementAttribute: v })" />
            <span v-else>{{ row.measurementAttribute }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联方" width="72" align="center">
          <template #default="{ row }">
            <el-checkbox v-if="!isReadonly" :model-value="row.isRelatedParty"
              @update:model-value="(v: boolean | string | number) => detail.updateRow(row.rowId, { isRelatedParty: !!v })" />
            <span v-else>{{ row.isRelatedParty ? '是' : '否' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="detail.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </template>

      <template v-else-if="detail.activeTab.value === 'movement'">
        <el-table-column label="资产名称" prop="assetName" min-width="100" fixed />
        <el-table-column label="期初余额" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.openingBalance" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingBalance: v ?? 0 })" />
            <span v-else>{{ fmt(row.openingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初调整" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.openingAdjustment" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.openingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初审定" width="96" align="right">
          <template #default="{ row }"><span class="formula-cell" title="期初审定 = 期初余额 + 期初调整">{{ fmt(row.openingAdjusted) }}</span></template>
        </el-table-column>
        <el-table-column label="本期增加" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.increaseAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { increaseAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.increaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.decreaseAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { decreaseAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.decreaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="FV变动" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.fvChangeAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { fvChangeAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.fvChangeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="利息" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.interestIncome" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { interestIncome: v ?? 0 })" />
            <span v-else>{{ fmt(row.interestIncome) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.impairmentLoss" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { impairmentLoss: v ?? 0 })" />
            <span v-else>{{ fmt(row.impairmentLoss) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="OCI变动" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ociChange" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { ociChange: v ?? 0 })" />
            <span v-else>{{ fmt(row.ociChange) }}</span>
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="资产名称" prop="assetName" min-width="100" fixed />
        <el-table-column label="期末余额" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末余额 = 期初审定 + 增加 − 减少 + FV + 利息 − 减值 + OCI">{{ fmt(row.closingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整数" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.closingAdjustment" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { closingAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.closingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell" title="审定数 = 期末余额 + 调整数">{{ fmt(row.closingAdjusted) }}</span></template>
        </el-table-column>
        <el-table-column label="层次" width="96">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.fairValueLevel" size="small" @update:model-value="(v: string) => detail.updateRow(row.rowId, { fairValueLevel: v })">
              <el-option v-for="o in detail.fvLevelOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.fairValueLevel }}</span>
          </template>
        </el-table-column>
        <el-table-column label="估值方法" width="110">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.valuationMethod"
              size="small"
              filterable
              allow-create
              default-first-option
              :class="{ 'l3-required': row.fairValueLevel === 'Level3' && !row.valuationMethod }"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { valuationMethod: v })"
            >
              <el-option v-for="o in detail.valuationMethodOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.valuationMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="OCI累计" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ociCumulative" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { ociCumulative: v ?? 0 })" />
            <span v-else>{{ fmt(row.ociCumulative) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.impairmentProvision" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { impairmentProvision: v ?? 0 })" />
            <span v-else>{{ fmt(row.impairmentProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发函情况" width="110">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.confirmationStatus"
              size="small"
              clearable
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { confirmationStatus: v || '' })"
            >
              <el-option v-for="o in detail.confirmationOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.confirmationStatus || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { remark: v })" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </template>
    </el-table>

    <div class="summary-bar" data-testid="g9-detail-summary">
      <span>期初审定 <strong>{{ fmt(detail.totals.value.openingAdjusted) }}</strong></span>
      <span>期末余额 <strong>{{ fmt(detail.totals.value.closingBalance) }}</strong></span>
      <span>审定合计 <strong>{{ fmt(detail.totals.value.closingAdjusted) }}</strong></span>
      <span>OCI变动 <strong>{{ fmt(detail.totals.value.ociChange) }}</strong></span>
    </div>

    <div class="subtotals" data-testid="g9-detail-subtotals">
      <span
        v-for="(amt, cls) in detail.classificationSubtotals.value"
        :key="cls"
        :class="{ 'total-line': cls === '总计' }"
      >{{ cls }}: {{ fmt(amt) }}</span>
    </div>

    <G9AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="detail-note"
      conclusion-ai-section="detail-conclusion"
      note-placeholder="填写审计说明：可概述明细核对情况、分类计量恰当性、与 G9-1 审定表合计勾稽情况及拟调整事项。"
      note-hint="覆盖分类计量、明细加计及与 G9-1 / G9-4 / G9-5 勾稽。"
      :related-context="{
        行数: detail.rows.value.length,
        审定合计: detail.totals.value.closingAdjusted,
        与G91差异: detail.adjCrossVariance.value,
        校验问题: detail.integrityIssues.value.length,
      }"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G9ImportExportDropdown from '../G9ImportExportDropdown.vue'
import G9AuditTextCards from '../G9AuditTextCards.vue'
import { useG9Detail } from '../../composables/useG9Detail'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const tabOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '期初+变动', value: 'movement' },
  { label: '期末+公允价值', value: 'closing' },
]

const detail = useG9Detail({
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
  projectId: computed(() => props.projectId || ''),
})

function onImported() { emit('imported') }

function onRowChange(r: { rowId?: string } | null) {
  if (!r?.rowId) return
  const idx = detail.rows.value.findIndex((x) => x.rowId === r.rowId)
  if (idx >= 0) detail.activeRowIndex.value = idx
}

async function onSeedAux() {
  const res = await detail.seedFromAuxBalance()
  if (res.error) {
    ElMessage.warning(res.error)
    return
  }
  ElMessage.success(`辅助核算（${res.dimType}）：新增 ${res.added}，更新 ${res.updated}`)
}

function onFillOci() {
  const n = detail.fillOciFromFvChange()
  if (n > 0) ElMessage.success(`已为 ${n} 行 FVOCI 填入 OCI 变动`)
  else ElMessage.info('无需填入（无 FVOCI 空白 OCI 行）')
}

const NOTE_KEY = 'G9-detail-audit-note'
const CONCLUSION_KEY = 'G9-detail-audit-conclusion'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: v })
})

function fmt(n: number) {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g9-detail { font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.title-block h3 { margin: 0; font-size: 15px; }
.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
.audit-objective { margin-bottom: 10px; }
.adj-toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }
.cross-alert { margin-bottom: 8px; }
.issue-list { margin: 4px 0 0; padding-left: 18px; }
.summary-bar { display: flex; gap: 16px; margin-top: 10px; flex-wrap: wrap; font-size: 13px; }
.subtotals { margin-top: 8px; display: flex; gap: 16px; flex-wrap: wrap; color: #606266; }
.total-line { font-weight: 600; color: #303133; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; background: #f5f7fa; display: inline-block; width: 100%; }
.l3-required :deep(.el-input__wrapper),
.l3-required :deep(.el-select__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }
</style>
