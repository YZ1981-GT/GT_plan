<template>
  <div class="g1-derivative-check">
    <div class="section-head">
      <h3 class="sheet-title">G1-14 衍生金融工具核查表</h3>
      <div class="head-actions tab-toolbar">
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-14"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="dc.addRow()">新增衍生工具</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-1" /></span>
        <el-tag size="small" type="info">共 {{ dc.rows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-14-conclusion')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核查衍生金融工具（期权/期货/互换/远期）的存在、名义金额、对手方及保证金安排，评价会计处理适当性，确认非套期衍生工具计入交易性金融资产恰当。"
      class="objective-alert"
    />

    <div class="stats-bar">
      衍生工具：<b>{{ dc.rows.value.length }}</b> 项 ·
      名义金额合计：{{ dc.notionalTotal.value.toLocaleString() }} ·
      保证金合计：{{ dc.marginTotal.value.toLocaleString() }} ·
      会计处理不适当：<b :class="{ warn: dc.inappropriateCount.value > 0 }">{{ dc.inappropriateCount.value }}</b>
    </div>

    <el-table :data="dc.rows.value" border size="small" max-height="500">
      <el-table-column
        v-for="col in dc.columns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :align="col.type === 'number' ? 'right' : 'left'"
        :fixed="col.prop === 'instrumentName' ? 'left' : undefined"
      >
        <template #default="{ row, $index }">
          <span v-if="col.prop === 'seq'">{{ $index + 1 }}</span>
          <el-select
            v-else-if="col.type === 'type-select'"
            v-model="row.instrumentType"
            size="small"
            :disabled="isReadonly"
            @change="dc.updateRow(row.id, { instrumentType: row.instrumentType })"
          >
            <el-option v-for="o in dc.typeOptions" :key="o.value" :value="o.value" :label="o.label" />
          </el-select>
          <el-select
            v-else-if="col.type === 'accounting-select'"
            v-model="row.accountingAppropriateness"
            size="small"
            :disabled="isReadonly"
            @change="dc.updateRow(row.id, { accountingAppropriateness: row.accountingAppropriateness })"
          >
            <el-option v-for="o in dc.accountingOptions" :key="o.value" :value="o.value" :label="o.label" />
          </el-select>
          <el-input-number
            v-else-if="col.type === 'number'"
            v-model="row[col.prop]"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="dc.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <el-input
            v-else
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            @change="dc.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="dc.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>


    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      :conclusion="dc.auditConclusion.value"
      @update:conclusion="(v: string) => { dc.auditConclusion.value = v }"
      note-ai-section="derivative-note"
      conclusion-ai-section="derivative-conclusion"
      note-placeholder="填写审计说明：（1）衍生工具存在性、名义金额、对手方及保证金的核查情况；（2）会计处理适当性的判断依据。"
      note-hint="覆盖存在性、名义金额、对手方、保证金及会计处理。"
    />


    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>衍生工具类型：期权/期货/互换/远期，需关注名义金额、对手方及保证金安排。</li>
        <li>会计处理适当性下拉判定，标记为「不适当」的项目应在合规结论中说明并提出调整建议。</li>
        <li>套期工具需单独判断套期关系有效性，非套期衍生工具计入交易性金融资产。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import {ref, toRef, inject, watch , computed} from 'vue'
import { useG1DerivativeCheck } from '../../composables/useG1DerivativeCheck'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
}>()

const wpId = computed(() => props.wpId ?? '')

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const dc = useG1DerivativeCheck({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const AUDIT_NOTE_KEY = 'G1-14-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})
</script>

<style scoped>
.g1-derivative-check { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g1-derivative-check :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g1-derivative-check :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; color: #1f2a37; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.stats-bar { margin-bottom: 10px; padding: 8px 12px; background: #f8f9fb; border: 1px solid #ebeef5; border-radius: 6px; font-size: 12px; color: #606266; }
.stats-bar { margin-bottom: 10px; font-size: 12px; color: #606266; }
.stats-bar .warn { color: #f56c6c; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>
