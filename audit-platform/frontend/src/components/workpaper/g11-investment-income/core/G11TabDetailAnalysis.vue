<template>
  <div class="g11-detail">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表按投资类型（交易性金融资产、长期股权投资、债权投资、其他）分组列示投资收益的本期/上期发生额及占比。</p>
        <p>2. 投资收益为损益类科目（6111），取发生额而非余额递推；权益法确认的投资损益、处置收益、公允价值变动结转等分项列示。</p>
        <p>3. |变动率|&gt;20% 或占比重大的项目应在"变动原因/索引"注明原因并交叉索引至明细底稿。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实各类投资收益的构成、金额及占比，验证本期与上期发生额的完整与准确，为 G11-1 审定表提供明细支持。"
    />

    <div class="section-head">
      <h3 class="sheet-title">G11-2 投资收益明细分析表</h3>
      <div class="head-actions">
        <G11ImportExportDropdown :wp-id="wpId" sheet="G11-2" @imported="onImported" />
        <GtReviewTrigger section-id="G11-2-detail" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="detail.addRow()">+ 新增</el-button>
      </div>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G11-2" /></span>
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="detail.rows.value" border stripe size="small" style="font-size:13px" max-height="560" data-testid="g11-detail-table">
      <el-table-column prop="seq" label="序号" width="48" align="center" fixed />
      <el-table-column label="项目" min-width="130" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small"
            @update:model-value="(v: string) => detail.updateRow(row.id, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="投资类型" width="120">
        <template #default="{ row }">
          <span class="group-tag">{{ row.group }}</span>
        </template>
      </el-table-column>
      <el-table-column label="被投资单位" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.investeeName" size="small"
            @update:model-value="(v: string) => detail.updateRow(row.id, { investeeName: v })" />
          <span v-else>{{ row.investeeName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期数" align="center">
        <el-table-column label="未审" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.currentUnadjusted" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { currentUnadjusted: v ?? 0 })" />
            <span v-else>{{ fmt(row.currentUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.currentAdjustment" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { currentAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.currentAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="88" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.currentAudited) }}</span></template>
        </el-table-column>
        <el-table-column label="占比" width="64" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtPct(row.currentShare) }}</span></template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="上期数" align="center">
        <el-table-column label="未审" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorUnadjusted" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { priorUnadjusted: v ?? 0 })" />
            <span v-else>{{ fmt(row.priorUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整" width="88" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.priorAdjustment" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { priorAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.priorAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="88" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.priorAudited) }}</span></template>
        </el-table-column>
        <el-table-column label="占比" width="64" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtPct(row.priorShare) }}</span></template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="变动额" width="88" align="right">
        <template #default="{ row }">{{ fmt(row.changeAmount) }}</template>
      </el-table-column>
      <el-table-column label="变动率" width="72" align="right">
        <template #default="{ row }">{{ fmtRate(row.changeRate) }}</template>
      </el-table-column>
      <el-table-column label="变动原因/索引" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.reasonIndex" size="small"
            @update:model-value="(v: string) => detail.updateRow(row.id, { reasonIndex: v })" />
          <GtIndexChip v-else-if="row.reasonIndex" :value="row.reasonIndex" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" v-if="!isReadonly" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="detail.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="group-summary" v-if="detail.groupedRows.value.length">
      <span v-for="g in detail.groupedRows.value" :key="g.groupName" class="group-chip">
        {{ g.groupName }} {{ fmt(g.subtotal.currentAudited) }}
      </span>
    </div>
    <div class="total-bar">
      合计 本期审定 {{ fmt(detail.totalRow.value.currentAudited) }}
      · 上期审定 {{ fmt(detail.totalRow.value.priorAudited) }}
      · 变动 {{ fmt(detail.totalRow.value.changeAmount) }}
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：可概述（1）投资收益明细分析程序的执行情况与结果；（2）重大变动项目的原因分析与拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受限无法获取充分适当证据），不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, onMounted } from 'vue'
import { useG11DetailAnalysis } from '../../composables/useG11DetailAnalysis'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G11ImportExportDropdown from '../G11ImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const detail = useG11DetailAnalysis({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

// ─── 审计说明 / 审计结论 ───
const NOTE_KEY = 'G11-detail-audit-note'
const CONCLUSION_KEY = 'G11-detail-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  props.debouncedSave(NOTE_KEY, { remark: val, conclusion: null })
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  props.debouncedSave(CONCLUSION_KEY, { remark: val, conclusion: null })
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

async function onImported() {
  emit('imported')
  detail.reloadFromStore()
}

function fmt(v: number) { return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function fmtRate(r: number | null) { return r === null ? 'N/A' : (r * 100).toFixed(1) + '%' }
function fmtPct(v: number | null) { return v === null ? '-' : (v * 100).toFixed(1) + '%' }
</script>

<style scoped>
.g11-detail { font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.group-tag { font-size: 11px; color: #606266; }
.group-summary { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; }
.group-chip { padding: 2px 8px; background: #ecf5ff; border-radius: 4px; font-size: 12px; }
.total-bar { margin-top: 8px; padding: 8px; background: #f5f7fa; font-size: 12px; }
</style>
