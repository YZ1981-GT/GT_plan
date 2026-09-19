<template>
  <div class="g10-l3" data-testid="g10-l3-reconciliation">
    <div class="methodology">
      负债方向 L3 调节：期末 = 期初 + 本期新增 − 本期终止 + 转入L3 − 转出L3 + FV变动 + 利息费用 + 其他
    </div>
    <div class="toolbar">
      <h3>G10-6 第三层次公允价值调节表</h3>
      <G10ImportExportDropdown :wp-id="wpId" sheet="G10-6" @imported="onImported" />
      <el-button size="small" type="primary" :disabled="isReadonly" @click="l3.addRow()">+ 新增</el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        plain
        data-testid="g10-l3-pull-detail"
        @click="l3.pullFromDetail()"
      >
        ↓ 从 G10-2 带入
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        plain
        data-testid="g10-l3-pull-fv"
        @click="l3.pullFromFairValueTest()"
      >
        ↓ 从 G10-5 带入
      </el-button>
      <el-button
        v-if="jumpToSection"
        size="small"
        plain
        data-testid="g10-l3-goto-fv"
        @click="jumpToSection('G10-5')"
      >
        → G10-5 公允测试
      </el-button>
      <el-button
        v-if="!isReadonly && l3.varianceRows.value.length"
        size="small"
        type="warning"
        plain
        data-testid="g10-l3-push-adj"
        @click="onPushVariance"
      >
        推送差异→G10-3（{{ l3.varianceRows.value.length }}）
      </el-button>
      <el-button
        v-if="!isReadonly && projectId"
        size="small"
        type="success"
        plain
        data-testid="g10-l3-mark-procedure"
        @click="onMarkProcedure"
      >
        {{ l3.procedureMarked.value ? '已回填 G10A（可重写）' : '回填 G10A L3调节' }}
      </el-button>
      <GtReviewTrigger section-id="G10-6-l3" />
    </div>

    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：核实第三层次公允价值负债期初至期末调节过程的完整与准确，验证层次转移的恰当性，确认调节结果与 G10-5 公允价值测试勾稽一致。" />

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G10-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G10-5" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G10-6" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G10-3" /></span>
        <el-tag size="small" type="info">共 {{ l3.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-alert
      v-if="l3.hasFvCrossMismatch.value"
      type="warning"
      :closable="false"
      show-icon
      class="var-alert"
      data-testid="g10-l3-fv-cross"
      :title="`企业期末合计 ${fmt(l3.totals.value.reportedClosing)} 与 G10-5 Level3 审定 FV ${fmt(l3.fvL3AuditedTotal.value)} 差异 ${fmt(l3.fvCrossVariance.value)}`"
    />

    <el-alert v-if="l3.varianceRows.value.length" type="warning" :closable="false" class="var-alert">
      {{ l3.varianceRows.value.length }} 行存在差异（企业期末 ≠ 计算期末）
    </el-alert>

    <el-alert
      v-if="l3.assetMismatches.value.length"
      type="warning"
      :closable="false"
      show-icon
      class="var-alert"
      data-testid="g10-l3-asset-cross"
    >
      <template #title>
        {{ l3.assetMismatches.value.length }} 项 G10-5 Level3 审定 FV 与 G10-6 企业期末逐笔不一致
      </template>
      <ul class="mismatch-list">
        <li v-for="m in l3.assetMismatches.value.slice(0, 5)" :key="m.liabilityName">
          {{ m.liabilityName }}：G10-5 {{ fmt(m.fv5Audited) }} vs G10-6 {{ fmt(m.g96Reported) }}（差 {{ fmt(m.diff) }}）
        </li>
        <li v-if="l3.assetMismatches.value.length > 5">…共 {{ l3.assetMismatches.value.length }} 项</li>
      </ul>
    </el-alert>

    <el-table :data="l3.rows.value" border size="small" style="font-size:13px" max-height="480">
      <el-table-column label="#" prop="seq" width="44" fixed />
      <el-table-column label="负债名称" min-width="120" fixed>
        <template #default="{ row }">
          <div class="name-cell">
            <el-input v-model="row.liabilityName" size="small" :disabled="isReadonly"
              @change="(v: string) => l3.updateCell(row.rowId, 'liabilityName', v)" />
            <el-tag v-if="l3.linkByRowId.value.get(row.rowId)?.hasDetail" size="small" type="success" class="link-tag">G10-2</el-tag>
            <el-tag v-if="l3.linkByRowId.value.get(row.rowId)?.hasFv" size="small" type="info" class="link-tag">G10-5</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="期初" width="96" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.openingBalance" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'openingBalance', v)" />
        </template>
      </el-table-column>
      <el-table-column label="本期新增" width="96" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.currentNew" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'currentNew', v)" />
        </template>
      </el-table-column>
      <el-table-column label="本期终止" width="96" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.currentTerminated" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'currentTerminated', v)" />
        </template>
      </el-table-column>
      <el-table-column label="转入L3" width="88" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.transferIntoL3" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'transferIntoL3', v)" />
        </template>
      </el-table-column>
      <el-table-column label="转出L3" width="88" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.transferOutOfL3" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'transferOutOfL3', v)" />
        </template>
      </el-table-column>
      <el-table-column label="FV变动" width="88" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.fairValueChange" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'fairValueChange', v)" />
        </template>
      </el-table-column>
      <el-table-column label="利息费用" width="88" align="right">
        <template #default="{ row }">
          <WpAmountInput v-model="row.interestExpense" size="small" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'interestExpense', v)" />
        </template>
      </el-table-column>
      <el-table-column label="其他" width="88" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.otherChanges" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'otherChanges', v)" />
        </template>
      </el-table-column>
      <el-table-column label="期末(公式)" width="100" align="right">
        <template #default="{ row }"><span class="formula">{{ fmt(row.closingBalance) }}</span></template>
      </el-table-column>
      <el-table-column label="企业期末" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.reportedClosing" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%" @change="(v: number) => l3.updateCell(row.rowId, 'reportedClosing', v)" />
        </template>
      </el-table-column>
      <el-table-column label="差异" width="88" align="right">
        <template #default="{ row }">
          <span :class="{ 'var-warn': Math.abs(row.variance) > 0.01 }">{{ fmt(row.variance) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="80">
        <template #default="{ row }">
          <el-input v-model="row.remark" size="small" :disabled="isReadonly"
            @change="(v: string) => l3.updateCell(row.rowId, 'remark', v)" />
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="l3.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="summary-bar" data-testid="g10-l3-summary">
      <span>计算期末 <strong>{{ fmt(l3.totals.value.closingBalance) }}</strong></span>
      <span>企业期末 <strong>{{ fmt(l3.totals.value.reportedClosing) }}</strong></span>
      <span>FV变动合计 <strong>{{ fmt(l3.totals.value.fairValueChange) }}</strong></span>
      <span>与 G10-5 L3 差异 <strong>{{ fmt(l3.fvCrossVariance.value) }}</strong></span>
    </div>

    <G10AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="l3-note"
      conclusion-ai-section="l3-conclusion"
      note-placeholder="填写审计说明：可概述第三层次调节表各行变动的核实情况、层次转入转出原因、企业期末与计算期末差异的核查结果。"
      note-hint="覆盖期初至期末调节、层次转移及与 G10-5 勾稽。"
      conclusion-placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
      :related-context="{
        行数: l3.rows.value.length,
        差异行数: l3.varianceRows.value.length,
        与G105L3差异: l3.fvCrossVariance.value,
      }"
    />

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>依据 CAS 37《金融工具列报》，第三层次公允价值须披露期初到期末的调节过程。</p>
        <p>计算期末 = 期初 + 本期新增 − 本期终止 + 转入L3 − 转出L3 + FV变动 + 利息费用 + 其他；「企业期末」与「计算期末」差异大于 0.01 时须核查并说明。</p>
        <p>优先「从 G10-2 带入」拉取 Level3 明细变动；「从 G10-5 带入」补填企业报告期末勾稽；本表企业期末合计应与 G10-5 Level3 审定 FV 一致。</p>
        <p>调节差异（企业期末≠公式期末）可「推送差异→G10-3」生成 AJE（Dr 6101 / Cr 2101）并回写 G10-1。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, toRef, watch, inject, computed } from 'vue'
import { useG10L3Reconciliation } from '../../composables/useG10L3Reconciliation'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G10ImportExportDropdown from '../G10ImportExportDropdown.vue'
import G10AuditTextCards from '../G10AuditTextCards.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  auditYear?: number | null
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const l3 = useG10L3Reconciliation({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  projectId: computed(() => props.projectId || ''),
  auditYear: computed(() => props.auditYear),
})

const NOTE_KEY = 'G10-6-l3-audit-note'
const CONCLUSION_KEY = 'G10-6-l3-audit-conclusion'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: v })
})

function onImported() {
  emit('imported')
  l3.reloadFromStore()
}

async function onPushVariance() {
  await l3.pushVarianceToAdjustment()
}

async function onMarkProcedure() {
  await l3.markProcedureComplete()
}

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g10-l3 { font-size: var(--wp-font-size, 13px); }
.methodology { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar h3 { margin: 0; font-size: 15px; flex: 1; }
.formula { border-bottom: 1px dashed #909399; }
.var-warn { color: #e6a23c; font-weight: 600; }
.var-alert { margin-bottom: 8px; }
.mismatch-list { margin: 4px 0 0; padding-left: 18px; font-size: 12px; }
.name-cell { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.link-tag { flex-shrink: 0; }
.summary-bar {
  margin-top: 8px; padding: 8px; background: #f5f7fa; font-size: 12px;
  display: flex; flex-wrap: wrap; gap: 16px;
}
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
.objective-alert { margin-bottom: 10px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
</style>
