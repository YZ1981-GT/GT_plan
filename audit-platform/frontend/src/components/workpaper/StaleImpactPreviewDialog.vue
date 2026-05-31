<template>
  <el-dialog
    v-model="visible"
    title="影响预览"
    width="600px"
    :close-on-click-modal="false"
  >
    <div v-loading="loading" class="stale-impact-preview">
      <el-alert
        v-if="summary"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      >
        此操作将影响以下对象，确认后将标记为待更新状态
      </el-alert>

      <div v-if="summary" class="impact-summary">
        <div class="summary-row">
          <el-statistic title="底稿" :value="summary.workpaperCount" />
          <el-statistic title="报表行" :value="summary.reportRowCount" />
          <el-statistic title="附注" :value="summary.noteCount" />
        </div>

        <!-- 底稿详情 -->
        <div v-if="summary.details.workpapers.length" class="detail-section">
          <div class="detail-title">受影响底稿</div>
          <div
            v-for="wp in summary.details.workpapers.slice(0, 10)"
            :key="wp.wp_code"
            class="detail-item"
            @click="handleJump('workpaper', wp.wp_code)"
          >
            <span class="item-code">{{ wp.wp_code }}</span>
            <span class="item-name">{{ wp.wp_name }}</span>
          </div>
          <div v-if="summary.details.workpapers.length > 10" class="detail-more">
            ...还有 {{ summary.details.workpapers.length - 10 }} 张
          </div>
        </div>

        <!-- 报表行详情 -->
        <div v-if="summary.details.reportRows.length" class="detail-section">
          <div class="detail-title">受影响报表行</div>
          <div
            v-for="row in summary.details.reportRows.slice(0, 10)"
            :key="`${row.report_type}-${row.row_code}`"
            class="detail-item"
            @click="handleJump('report', row.row_code)"
          >
            <el-tag size="small" type="info">{{ row.report_type }}</el-tag>
            <span class="item-name">{{ row.row_name }}</span>
          </div>
          <div v-if="summary.details.reportRows.length > 10" class="detail-more">
            ...还有 {{ summary.details.reportRows.length - 10 }} 行
          </div>
        </div>

        <!-- 附注详情 -->
        <div v-if="summary.details.notes.length" class="detail-section">
          <div class="detail-title">受影响附注</div>
          <div
            v-for="note in summary.details.notes.slice(0, 10)"
            :key="note.section"
            class="detail-item"
            @click="handleJump('note', note.section)"
          >
            <span class="item-code">{{ note.section }}</span>
            <span class="item-name">{{ note.title }}</span>
          </div>
          <div v-if="summary.details.notes.length > 10" class="detail-more">
            ...还有 {{ summary.details.notes.length - 10 }} 章节
          </div>
        </div>
      </div>

      <el-empty v-if="!loading && !summary" description="无影响范围数据" />
    </div>

    <template #footer>
      <el-button @click="handleCancel">取消</el-button>
      <el-button type="primary" :loading="confirming" @click="handleConfirm">
        确认修改
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ImpactSummary } from '@/composables/useStaleImpactConfirm'
import { usePenetrate } from '@/composables/usePenetrate'

const props = defineProps<{
  modelValue: boolean
  summary: ImpactSummary | null
  loading: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'confirm': []
  'cancel': []
}>()

const visible = ref(props.modelValue)
const confirming = ref(false)
const { toWorkpaper, toReportRow, toNote } = usePenetrate()

watch(() => props.modelValue, (val) => { visible.value = val })
watch(visible, (val) => { emit('update:modelValue', val) })

function handleConfirm() {
  confirming.value = true
  emit('confirm')
  visible.value = false
  confirming.value = false
}

function handleCancel() {
  emit('cancel')
  visible.value = false
}

function handleJump(type: string, code: string) {
  if (type === 'workpaper') toWorkpaper(code)
  else if (type === 'report') toReportRow('balance_sheet', code)
  else if (type === 'note') toNote(code)
}
</script>

<style scoped>
.stale-impact-preview {
  min-height: 120px;
}

.impact-summary {
  padding: 0 8px;
}

.summary-row {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}

.detail-section {
  margin-bottom: 12px;
}

.detail-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  cursor: pointer;
  border-radius: 4px;
  font-size: 12px;
}

.detail-item:hover {
  background: var(--el-fill-color-light);
}

.item-code {
  font-family: monospace;
  color: var(--el-color-primary);
  min-width: 60px;
}

.item-name {
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-more {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  padding: 4px 8px;
}
</style>
