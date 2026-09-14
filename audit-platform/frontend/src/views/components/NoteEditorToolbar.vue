<template>
  <GtToolbar
    :show-copy="true"
    :show-fullscreen="true"
    :is-fullscreen="isFullscreen"
    :show-export="true"
    export-label="导出Word"
    :show-import="true"
    :show-formula="true"
    @copy="$emit('copy')"
    @fullscreen="$emit('fullscreen')"
    @export="$emit('export-word')"
    @import="$emit('show-import')"
    @formula="$emit('show-formula')"
  >
    <template #left>
      <NoteTemplateSwitch
        v-if="!isEqcrRole"
        :project-id="projectId"
        :year="year"
        :template-type="templateType"
        @update:template-type="$emit('template-change', $event)"
        @switched="$emit('tree-refresh')"
      />
      <el-button v-if="!isEqcrRole" size="small" @click="$emit('refresh-from-wp')" :loading="refreshLoading">🔄 从底稿刷新</el-button>
      <el-button v-if="!isEqcrRole" size="small" @click="$emit('generate')" :loading="genLoading">📝 生成附注</el-button>
      <el-button v-if="!isEqcrRole" size="small" @click="$emit('validate')" :loading="validateLoading">✅ 执行校验</el-button>
      <el-button v-if="isEqcrRole" size="small" type="info">📋 导出只读副本</el-button>
    </template>
    <template #right-extra>
      <SharedTemplatePicker
        config-type="note_template"
        :project-id="projectId"
        :get-config-data="getConfigData"
        @applied="$emit('template-applied', $event)"
      />
      <el-button
        v-if="!isEqcrRole"
        size="small"
        data-test="de-add-section"
        @click="$emit('add-section')"
      >➕ 新增章节</el-button>
      <el-button size="small" @click="$emit('open-structure-editor')">📐 表样编辑</el-button>
      <el-button size="small" @click="$emit('show-print-preview')">🖨️ 打印预览</el-button>
      <el-button size="small" @click="$emit('show-offline-export')">📦 导出离线包</el-button>
      <el-button size="small" @click="$emit('show-offline-import')">📥 一键导入</el-button>
      <el-button size="small" @click="$emit('show-ai-panel')">🤖 AI建议</el-button>
      <el-button size="small" @click="$emit('show-doc-ai-chat')">💬 AI 对话</el-button>
      <el-button size="small" @click="$emit('show-version-tree')">🗂️ 版本</el-button>
      <el-button size="small" @click="$emit('show-group-baseline')">📦 集团基线</el-button>
      <el-button size="small" @click="$emit('show-paragraph-vars')">✏️ 段落变量</el-button>
      <el-button size="small" @click="$emit('show-prior-year')">📅 上年对比</el-button>
      <el-button-group size="small" style="margin-left: 4px">
        <el-button :type="scope === 'standalone' ? 'primary' : ''" @click="$emit('scope-change', 'standalone')">单体</el-button>
        <el-button :type="scope === 'consolidated' ? 'primary' : ''" @click="$emit('scope-change', 'consolidated')">合并</el-button>
      </el-button-group>
      <el-button size="small" @click="$emit('show-mapping-dialog')">🔄 转换规则</el-button>
    </template>
  </GtToolbar>
</template>

<script setup lang="ts">
import GtToolbar from '@/components/common/GtToolbar.vue'
import NoteTemplateSwitch from '@/components/notes/NoteTemplateSwitch.vue'
import SharedTemplatePicker from '@/components/shared/SharedTemplatePicker.vue'

defineProps<{
  projectId: string
  year: number
  templateType: string
  isEqcrRole: boolean
  isFullscreen: boolean
  refreshLoading: boolean
  genLoading: boolean
  validateLoading: boolean
  scope: string
  getConfigData: () => Record<string, any>
}>()

defineEmits<{
  'copy': []
  'fullscreen': []
  'export-word': []
  'show-import': []
  'show-formula': []
  'template-change': [value: string]
  'tree-refresh': []
  'refresh-from-wp': []
  'generate': []
  'validate': []
  'template-applied': [data: Record<string, any>]
  'add-section': []
  'open-structure-editor': []
  'show-print-preview': []
  'show-offline-export': []
  'show-offline-import': []
  'show-ai-panel': []
  'show-doc-ai-chat': []
  'show-version-tree': []
  'show-group-baseline': []
  'show-paragraph-vars': []
  'show-prior-year': []
  'scope-change': [scope: string]
  'show-mapping-dialog': []
}>()
</script>
