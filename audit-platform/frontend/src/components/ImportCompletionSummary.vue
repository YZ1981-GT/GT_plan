<template>
  <div :style="containerStyle">
    <el-icon v-if="showSuccessIcon" style="font-size: 40px /* allow-px: special */; color: var(--gt-color-success)"><CircleCheck /></el-icon>
    <div :style="titleStyle">{{ title }}</div>
    <div v-if="summaryEntries.length" :style="summaryStyle">
      <span v-for="item in summaryEntries" :key="item.key" style="margin-right: 12px">
        {{ item.label }}: {{ item.value }}
      </span>
    </div>
    <ImportValidationPanel
      :summary="validationSummary"
      :grouped-items="groupedValidationItems"
      :title="validationTitle"
      :alert-type="validationAlertType"
      :panel-style="validationPanelStyle"
    />
  </div>
</template>

<script setup lang="ts">
import { CircleCheck } from '@element-plus/icons-vue'
import ImportValidationPanel from '@/components/ImportValidationPanel.vue'
import type { GroupedImportValidationItems, ImportValidationAlertType, ResolvedImportValidationSummary } from '@/utils/importValidation'

interface SummaryEntry {
  key: string
  label: string
  value: string
}

interface ValidationDisplayItem {
  file?: string | null
  sheet?: string | null
  rule_code: string
  message: string
}

withDefaults(defineProps<{
  title: string
  summaryEntries?: SummaryEntry[]
  validationSummary: ResolvedImportValidationSummary
  groupedValidationItems: GroupedImportValidationItems<ValidationDisplayItem>
  validationTitle: string
  validationAlertType: ImportValidationAlertType
  showSuccessIcon?: boolean
  containerStyle?: string
  titleStyle?: string
  summaryStyle?: string
  validationPanelStyle?: string
}>(), {
  summaryEntries: () => [],
  showSuccessIcon: false,
  containerStyle: '',
  titleStyle: 'margin-top: 12px; font-size: var(--gt-font-size-base)',
  summaryStyle: 'margin-top: 8px; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary)',
  validationPanelStyle: 'margin-top: 16px; text-align: left',
})
</script>
