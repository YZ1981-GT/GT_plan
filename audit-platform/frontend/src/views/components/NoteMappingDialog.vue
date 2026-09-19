<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    title="附注 国企版 ↔ 上市版 转换规则"
    width="75%"
    top="5vh"
    append-to-body
    destroy-on-close
  >
    <p style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); margin-bottom: 10px;">
      配置国企版与上市版附注章节的映射关系。切换模板类型时，系统将按此规则自动转换附注内容。
    </p>
    <div style="display: flex; gap: 8px; margin-bottom: 10px; align-items: center;">
      <el-button size="small" @click="$emit('load-preset')" :loading="loading">一键加载预设</el-button>
      <el-button size="small" type="primary" @click="$emit('save-rules')" :loading="loading" :disabled="!canEdit">保存规则</el-button>
      <SharedTemplatePicker
        config-type="report_mapping"
        :project-id="projectId"
        :get-config-data="getMappingData"
        @applied="$emit('mapping-applied', $event)"
      />
      <span style="flex: 1;" />
      <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">{{ rules.length }} 条规则</span>
    </div>
    <el-table :data="rules" size="small" border max-height="55vh"
      :header-cell-style="{ background: '#f8f6fb', fontSize: '12px', whiteSpace: 'nowrap' }">
      <el-table-column label="国企版章节" min-width="200">
        <template #default="{ row }">
          <span style="font-size: var(--gt-font-size-xs);">{{ row.soe_section }}</span>
        </template>
      </el-table-column>
      <el-table-column label="→" width="40" align="center">
        <template #default><span style="color: var(--gt-color-text-placeholder);">→</span></template>
      </el-table-column>
      <el-table-column label="上市版章节" min-width="200">
        <template #default="{ row }">
          <el-input v-if="row._editing" v-model="row.listed_section" size="small" />
          <span v-else style="font-size: var(--gt-font-size-xs);">{{ row.listed_section || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="60" align="center">
        <template #default="{ row }">
          <span v-if="row.listed_section" style="color: var(--gt-color-success);">✓</span>
          <span v-else style="color: var(--gt-color-text-placeholder);">—</span>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup lang="ts">
import SharedTemplatePicker from '@/components/shared/SharedTemplatePicker.vue'

defineProps<{
  modelValue: boolean
  projectId: string
  loading: boolean
  canEdit: boolean
  rules: any[]
  getMappingData: () => Record<string, any>
}>()

defineEmits<{
  'update:modelValue': [value: boolean]
  'load-preset': []
  'save-rules': []
  'mapping-applied': [data: Record<string, any>]
}>()
</script>
