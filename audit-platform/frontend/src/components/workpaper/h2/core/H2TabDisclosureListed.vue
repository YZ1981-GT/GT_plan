<template>
  <div class="h2-tab-disclosure-listed">
    <!-- 多子节卡片 -->
    <el-card v-for="(section, idx) in state.sections.value" :key="section.id"
      shadow="never" class="disclosure-card" :class="{ 'cross-sheet-card': section.isCrossSheet }">
      <template #header>
        <div class="section-header">
          <span>{{ idx + 1 }}. {{ section.title }}</span>
          <div class="section-header-actions">
            <el-tag v-if="section.isCrossSheet" type="info" size="small">跨sheet取数</el-tag>
            <el-button size="small" type="primary" link @click="handleAiGenerate(section.id)">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview(`H2-disc-L-${section.id}`)">💬</el-button>
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

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>附注(上市公司版)按CAS规定披露在建工程相关信息</li>
        <li>浅蓝色卡片表示数据从其他sheet自动取入(跨sheet)</li>
        <li>各子节合计应与H2-1审定表对应行一致</li>
        <li>动态行用于披露各项目明细(可增删)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabDisclosureListed.vue — 附注(上市公司版)
 * 多子节卡片 + 跨sheet浅蓝色 + 动态行 + 合计
 * Spec: Task 4.6 | Requirements: 14.6
 */
import { inject, toRef, computed } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH2Disclosure } from '../../composables/useH2Disclosure'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const state = useH2Disclosure({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  variant: computed(() => 'listed' as const) as any,
  onPublishEvent(event: string, payload: any) {
    // Task 6.8 — publish 'disclosure:note-text-updated' 通知外部
    console.log('[H2-DiscListed] publish', event, payload)
    http.post(`/api/projects/${props.projectId}/events/publish`, {
      event_type: event,
      payload,
    }, { _silent: true } as any).catch(() => { /* best effort */ })
  },
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

function handleAiGenerate(sectionId: string) {
  console.log('AI generate disclosure listed:', sectionId)
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
.h2-tab-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
