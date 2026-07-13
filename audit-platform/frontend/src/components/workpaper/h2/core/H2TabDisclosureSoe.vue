<template>
  <div class="h2-tab-disclosure-soe">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：按国企（国资委）披露要求核实在建工程附注的完整性与准确性，含资金来源/政府补助/责任人等额外披露，确保与 H2-1 审定表勾稽一致。" />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H2-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ state.sections.value.length }} 节</el-tag>
      </div>
    </div>

    <!-- 多子节卡片 -->
    <el-card v-for="(section, idx) in state.sections.value" :key="section.id"
      shadow="never" class="disclosure-card" :class="{ 'cross-sheet-card': section.isCrossSheet }">
      <template #header>
        <div class="section-header">
          <span>{{ idx + 1 }}. {{ section.title }}</span>
          <div class="section-header-actions">
            <el-tag v-if="section.isCrossSheet" type="info" size="small">跨sheet取数</el-tag>
            <el-button size="small" circle @click="openReview(`H2-disc-S-${section.id}`)">💬</el-button>
          </div>
        </div>
      </template>

      <!-- 自动取数字段（跨sheet只读） -->
      <div v-if="section.autoFields && section.autoFields.length" class="auto-fields">
        <div v-for="f in section.autoFields" :key="f.key" class="auto-field">
          <span class="af-label">{{ f.label }}</span>
          <span class="af-value formula-cell" :title="'来源：' + f.source">{{ fmtAmt(f.value) }}</span>
        </div>
      </div>

      <!-- 动态明细行 -->
      <el-table :data="section.rows" border stripe size="small" class="disc-table">
        <el-table-column prop="name" label="项目名称" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small"
              @change="onCellChange(section.id, row.rowId, 'name', row.name)" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.beginBalance" :controls="false" size="small"
              class="amt-input" @change="onCellChange(section.id, row.rowId, 'beginBalance', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.increase" :controls="false" size="small"
              class="amt-input" @change="onCellChange(section.id, row.rowId, 'increase', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.decrease" :controls="false" size="small"
              class="amt-input" @change="onCellChange(section.id, row.rowId, 'decrease', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期转固" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.transfer" :controls="false" size="small"
              class="amt-input" @change="onCellChange(section.id, row.rowId, 'transfer', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.transfer) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.endBalance" :controls="false" size="small"
              class="amt-input" @change="onCellChange(section.id, row.rowId, 'endBalance', $event)" />
            <span v-else class="amt-cell">{{ fmtAmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="onCellChange(section.id, row.rowId, 'remark', row.remark)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemoveRow(section.id, row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="section-total-line">
        本节期末合计：<strong>{{ fmtAmt(state.sectionTotals.value[section.id] || 0) }}</strong>
      </div>
      <div v-if="!isReadonly" class="add-row-bar">
        <el-button size="small" @click="handleAddRow(section.id)">+ 新增行</el-button>
      </div>

      <!-- 披露说明文本 -->
      <div class="note-text-block">
        <div class="note-label">披露说明</div>
        <el-input v-model="section.noteText" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
          placeholder="请填写披露说明..." :disabled="isReadonly"
          @blur="onTextChange(section.id, section.noteText)" />
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计说明</span></div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述附注各子节取数来源、资金来源/政府补助/责任人等额外披露的核查情况。" :disabled="isReadonly"
        @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：如附注披露完整、额外披露事项齐全、与审定表勾稽一致，符合国企披露要求，未见异常。" :disabled="isReadonly"
        @change="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>附注(国企版)按国资委要求披露在建工程相关信息</li>
        <li>浅蓝色卡片表示数据从其他sheet自动取入(跨sheet)</li>
        <li>国企版额外披露：资金来源/政府补助/责任人信息</li>
        <li>各子节合计应与H2-1审定表对应行一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabDisclosureSoe.vue — 附注(国企版)
 * 多子节卡片 + 跨sheet浅蓝色 + 动态行 + 合计
 * Spec: Task 4.6 | Requirements: 14.6
 */
import { ref, inject, toRef, computed, onMounted } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2Disclosure } from '../../composables/useH2Disclosure'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2Disclosure({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  variant: computed(() => 'soe' as const) as any,
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
  onPublishEvent(event: string, payload: any) {
    // Task 6.8 — publish 'disclosure:note-text-updated' 通知外部
    console.log('[H2-DiscSoe] publish', event, payload)
    http.post(`/api/projects/${props.projectId}/events/publish`, {
      event_type: event,
      payload,
    }, { _silent: true } as any).catch(() => { /* best effort */ })
  },
})

const isReadonly = computed(() => props.isReadonly)

// H2 附注(国企)审计说明/结论：本地变体键（listed/soe 共用同一 composable，避免串写）。
const NOTE_KEY = 'H2-disc-soe-audit-note'
const CONCLUSION_KEY = 'H2-disc-soe-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  saveResponse(NOTE_KEY, val)
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  saveResponse(CONCLUSION_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function onCellChange(sectionId: string, rowId: string, field: string, value: any) {
  state.updateRow(sectionId, rowId, field, value)
}

function onTextChange(sectionId: string, content: string) {
  state.updateSectionNote(sectionId, content)
}

function handleAddRow(sectionId: string) {
  state.addRow(sectionId, '')
}

function handleRemoveRow(sectionId: string, rowId: string) {
  state.removeRow(sectionId, rowId)
}


function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-disclosure-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-bottom: 12px; }
.disclosure-card { margin-bottom: 16px; }
.cross-sheet-card { background: #f0f7ff; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.disc-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.total-line { padding: 8px 0; font-size: var(--wp-font-size, 13px); text-align: right; }
.section-total-line { padding: 8px 0; font-size: var(--wp-font-size, 13px); text-align: right; }
.add-row-bar { margin-top: 8px; }
.auto-fields { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 12px; padding: 8px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.auto-field { display: flex; align-items: center; gap: 6px; font-size: var(--wp-font-size, 13px); }
.af-label { color: var(--el-text-color-secondary); }
.af-value { font-weight: 600; }
.note-text-block { margin-top: 12px; }
.note-label { font-size: var(--wp-font-size, 13px); color: var(--el-text-color-secondary); margin-bottom: 6px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
