<template>
  <div class="gt-editor-toolbar">
    <div class="gt-editor-toolbar-left">
      <el-button text @click="$emit('back')">← 返回</el-button>
      <span class="gt-editor-code" v-if="wpCode">{{ wpCode }}</span>
      <span class="gt-editor-name" v-if="wpName">{{ wpName }}</span>
      <el-tag v-if="status" :type="statusTagType(status) || undefined" size="small">
        {{ statusLabel(status) }}
      </el-tag>
      <el-tag :type="componentTypeTag.type || undefined" size="small" style="margin-left: 4px">
        {{ componentTypeTag.label }}
      </el-tag>
    </div>
    <div class="gt-editor-toolbar-right">
      <span v-if="dirty" class="gt-dirty-indicator">● 未保存</span>
      <el-button size="small" @click="$emit('save')" :loading="saving">💾 保存</el-button>
      <el-button size="small" @click="$emit('export')">📥 导出</el-button>
      <el-button size="small" @click="$emit('versions')">📋 版本</el-button>
      <el-button size="small" @click="$emit('formula-refresh')" v-if="showFormulaBtn">🔄 公式</el-button>
      <el-badge :value="panelBadge" :max="99" :hidden="!panelBadge" type="danger">
        <el-button size="small" @click="$emit('toggle-panel')">📋 面板</el-button>
      </el-badge>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  wpCode?: string
  wpName?: string
  status?: string
  componentType?: string
  dirty?: boolean
  saving?: boolean
  showFormulaBtn?: boolean
  panelBadge?: number
}>()

defineEmits<{
  back: []
  save: []
  export: []
  versions: []
  'formula-refresh': []
  'toggle-panel': []
}>()

const componentTypeTag = computed(() => {
  const map: Record<string, { label: string; type: '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' }> = {
    univer: { label: 'Univer', type: 'success' },
    form: { label: '表单', type: 'primary' },
    word: { label: 'Word', type: 'warning' },
    table: { label: '表格', type: 'info' },
    hybrid: { label: '混合', type: 'danger' },
  }
  return map[props.componentType || 'univer'] || map.univer
})

function statusTagType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    not_started: 'info', in_progress: 'warning', draft: 'warning',
    draft_complete: '', edit_complete: '', review_passed: 'success', archived: 'info',
  }
  return m[s] || 'info'
}

function statusLabel(s: string) {
  const m: Record<string, string> = {
    not_started: '未开始', in_progress: '编制中', draft: '草稿',
    draft_complete: '初稿完成', edit_complete: '编辑完成',
    review_passed: '复核通过', archived: '已归档',
  }
  return m[s] || s
}
</script>

<style scoped>
.gt-editor-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--gt-space-2, 8px) var(--gt-space-4, 16px);
  background: var(--gt-color-bg-white, #fff); box-shadow: var(--gt-shadow-sm, 0 1px 3px rgba(0,0,0,.08)); z-index: 10;
}
.gt-editor-toolbar-left { display: flex; align-items: center; gap: 10px; }
.gt-editor-toolbar-right { display: flex; align-items: center; gap: 6px; }
.gt-editor-code { font-weight: 600; color: var(--gt-color-primary, #4b2d77); font-size: var(--gt-font-size-sm); }
.gt-editor-name { color: var(--gt-color-text, #333); font-size: var(--gt-font-size-sm); }
.gt-dirty-indicator { color: var(--gt-color-wheat, #e6a23c); font-size: var(--gt-font-size-xs); font-weight: 500; }
</style>
