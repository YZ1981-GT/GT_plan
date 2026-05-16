<template>
  <el-alert
    v-if="summary.total > 0"
    :title="title"
    :type="alertType"
    :closable="false"
    show-icon
    :style="panelStyle"
  >
    <template #default>
      <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px">
        <el-tag v-if="summary.fatal > 0" type="danger">fatal {{ summary.fatal }}</el-tag>
        <el-tag v-if="summary.error > 0" type="danger">error {{ summary.error }}</el-tag>
        <el-tag v-if="summary.warning > 0" type="warning">warning {{ summary.warning }}</el-tag>
        <el-tag v-if="summary.info > 0" type="info">info {{ summary.info }}</el-tag>
      </div>

      <div v-if="groupedItems.fatal.length" style="margin-top: 10px">
        <div style="font-size: var(--gt-font-size-xs); font-weight: 600; color: var(--gt-color-coral); margin-bottom: 6px">fatal</div>
        <div
          v-for="(item, idx) in groupedItems.fatal"
          :key="`fatal_${item.rule_code}_${idx}`"
          style="font-size: var(--gt-font-size-sm); margin-bottom: 6px; color: var(--gt-color-coral)"
        >
          <strong>{{ item.file || '当前文件' }}</strong>
          <span v-if="item.sheet"> / {{ item.sheet }}</span>
          <span>：{{ item.message }}</span>
        </div>
      </div>

      <div v-if="groupedItems.error.length" style="margin-top: 10px">
        <div style="font-size: var(--gt-font-size-xs); font-weight: 600; color: var(--gt-color-coral); margin-bottom: 6px">error</div>
        <div
          v-for="(item, idx) in groupedItems.error"
          :key="`error_${item.rule_code}_${idx}`"
          style="font-size: var(--gt-font-size-sm); margin-bottom: 6px; color: var(--gt-color-coral)"
        >
          <strong>{{ item.file || '当前文件' }}</strong>
          <span v-if="item.sheet"> / {{ item.sheet }}</span>
          <span>：{{ item.message }}</span>
        </div>
      </div>

      <div v-if="groupedItems.warning.length" style="margin-top: 10px">
        <div style="font-size: var(--gt-font-size-xs); font-weight: 600; color: var(--gt-color-wheat); margin-bottom: 6px">warning</div>
        <div
          v-for="(item, idx) in groupedItems.warning"
          :key="`warning_${item.rule_code}_${idx}`"
          style="font-size: var(--gt-font-size-sm); margin-bottom: 6px; color: var(--gt-color-wheat)"
        >
          <strong>{{ item.file || '当前文件' }}</strong>
          <span v-if="item.sheet"> / {{ item.sheet }}</span>
          <span>：{{ item.message }}</span>
        </div>
      </div>

      <div v-if="groupedItems.info.length" style="margin-top: 10px">
        <div style="font-size: var(--gt-font-size-xs); font-weight: 600; color: var(--gt-color-info); margin-bottom: 6px">info</div>
        <div
          v-for="(item, idx) in groupedItems.info"
          :key="`info_${item.rule_code}_${idx}`"
          style="font-size: var(--gt-font-size-sm); margin-bottom: 6px; color: var(--gt-color-info)"
        >
          <strong>{{ item.file || '当前文件' }}</strong>
          <span v-if="item.sheet"> / {{ item.sheet }}</span>
          <span>：{{ item.message }}</span>
        </div>
      </div>
    </template>
  </el-alert>
</template>

<script setup lang="ts">
import type { CSSProperties } from 'vue'
import type {
  GroupedImportValidationItems,
  ImportValidationAlertType,
  ImportValidationItemLike,
  ResolvedImportValidationSummary,
} from '@/utils/importValidation'

interface ValidationDisplayItem extends ImportValidationItemLike {
  file?: string | null
  sheet?: string | null
  rule_code: string
  message: string
}

const _props = defineProps<{
  summary: ResolvedImportValidationSummary
  groupedItems: GroupedImportValidationItems<ValidationDisplayItem>
  title: string
  alertType: ImportValidationAlertType
  panelStyle?: CSSProperties | string
}>()
</script>
