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

      <!-- 表格型子节 -->
      <template v-if="section.type === 'table'">
        <el-table :data="section.rows" border stripe size="small" class="disc-table">
          <el-table-column v-for="col in section.columns" :key="col.prop"
            :prop="col.prop" :label="col.label" :min-width="col.width || 100" :align="col.align || 'left'">
            <template #default="{ row }">
              <template v-if="col.isFormula">
                <span class="formula-cell" :title="col.formulaTip">{{ fmtAmt(row[col.prop]) }}</span>
              </template>
              <template v-else-if="col.isEditable && !isReadonly">
                <el-input-number v-if="col.type === 'number'" v-model="row[col.prop]"
                  :controls="false" size="small" class="amt-input"
                  @change="onCellChange(section.id, row.rowId, col.prop, $event)" />
                <el-input v-else v-model="row[col.prop]" size="small"
                  @change="onCellChange(section.id, row.rowId, col.prop, $event)" />
              </template>
              <template v-else>
                <span :class="{ 'amt-cell': col.type === 'number' }">
                  {{ col.type === 'number' ? fmtAmt(row[col.prop]) : (row[col.prop] || '-') }}
                </span>
              </template>
            </template>
          </el-table-column>
        </el-table>
        <!-- 合计行 -->
        <div v-if="section.showTotal" class="total-line">
          合计: <strong>{{ fmtAmt(section.totalAmount) }}</strong>
        </div>
        <!-- 动态行操作 -->
        <div v-if="section.isDynamic && !isReadonly" class="add-row-bar">
          <el-button size="small" @click="handleAddRow(section.id)">+ 新增行</el-button>
        </div>
      </template>

      <!-- 文本型子节 -->
      <template v-if="section.type === 'text'">
        <el-input v-model="section.content" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
          :placeholder="section.placeholder" :disabled="isReadonly"
          @blur="onTextChange(section.id, section.content)" />
      </template>
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
  state.updateCell(sectionId, rowId, field, value)
}

function onTextChange(sectionId: string, content: string) {
  state.updateText(sectionId, content)
}

function handleAddRow(sectionId: string) {
  state.addRow(sectionId)
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
.h2-tab-disclosure-listed { padding: 16px; font-size: 13px; }
.disclosure-card { margin-bottom: 16px; }
.cross-sheet-card { background: #f0f7ff; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.disc-table { font-size: 13px; }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.total-line { padding: 8px 0; font-size: 13px; text-align: right; }
.add-row-bar { margin-top: 8px; }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
