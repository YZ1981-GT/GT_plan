<!--
  GtToolbar — 标准工具栏组件 [R5.1]
  统一各模块工具栏的通用操作按钮（导出/导入/全屏/公式/模板/编辑切换/显示设置），
  同时保留 left slot 供模块放置特有按钮。

  用法：
    <GtToolbar
      :show-export="true"
      :show-import="true"
      :show-fullscreen="true"
      :show-formula="true"
      :is-fullscreen="isFullscreen"
      @export="onExport"
      @import="showImport = true"
      @fullscreen="toggleFullscreen()"
      @formula="showFormulaManager = true"
    >
      <template #left>
        <el-button size="small" @click="onRecalc">🔄 全量重算</el-button>
      </template>
    </GtToolbar>
-->
<template>
  <div class="gt-toolbar">
    <!-- 左侧：模块特有按钮 -->
    <div class="gt-toolbar__left">
      <slot name="left" />
    </div>

    <!-- 右侧：通用操作按钮 -->
    <div class="gt-toolbar__right">
      <slot name="right">
        <!-- 复制整表 -->
        <el-tooltip v-if="showCopy" content="复制整个表格（可粘贴到 Word/Excel）" placement="bottom">
          <el-button size="small" @click="$emit('copy')">📋 复制整表</el-button>
        </el-tooltip>

        <!-- 全屏 -->
        <el-tooltip v-if="showFullscreen" :content="isFullscreen ? '退出全屏（ESC）' : '全屏查看（ESC 退出）'" placement="bottom">
          <el-button size="small" @click="$emit('fullscreen')">
            {{ isFullscreen ? '退出全屏' : '全屏' }}
          </el-button>
        </el-tooltip>

        <!-- 导出 -->
        <el-button v-if="showExport" size="small" @click="$emit('export')">
          📤 {{ exportLabel }}
        </el-button>

        <!-- 导入 -->
        <el-button v-if="showImport" size="small" @click="$emit('import')">
          📥 {{ importLabel }}
        </el-button>

        <!-- 公式管理 -->
        <el-button v-if="showFormula" size="small" @click="$emit('formula')">
          ⚙️ 公式管理
        </el-button>

        <!-- 模板选择 -->
        <el-button v-if="showTemplate" size="small" @click="$emit('template')">
          📐 模板选择
        </el-button>

        <!-- 编辑切换 -->
        <el-tooltip v-if="showEditToggle" :content="isEditing ? '切换到查看模式' : '切换到编辑模式'" placement="bottom">
          <el-button size="small" :type="isEditing ? 'primary' : ''" @click="$emit('edit-toggle')">
            {{ isEditing ? '✏️ 编辑中' : '👁️ 查看' }}
          </el-button>
        </el-tooltip>

        <!-- 显示设置 -->
        <el-button v-if="showDisplaySettings" size="small" @click="$emit('display-settings')">
          🎨 显示设置
        </el-button>

        <!-- 右侧额外插槽（在通用按钮之后） -->
        <slot name="right-extra" />
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  /** 显示复制整表按钮 */
  showCopy?: boolean
  /** 显示全屏按钮 */
  showFullscreen?: boolean
  /** 当前是否全屏 */
  isFullscreen?: boolean
  /** 显示导出按钮 */
  showExport?: boolean
  /** 导出按钮文字 */
  exportLabel?: string
  /** 显示导入按钮 */
  showImport?: boolean
  /** 导入按钮文字 */
  importLabel?: string
  /** 显示公式管理按钮 */
  showFormula?: boolean
  /** 显示模板选择按钮 */
  showTemplate?: boolean
  /** 显示编辑切换按钮 */
  showEditToggle?: boolean
  /** 当前是否编辑模式 */
  isEditing?: boolean
  /** 显示显示设置按钮 */
  showDisplaySettings?: boolean
}>(), {
  showCopy: false,
  showFullscreen: false,
  isFullscreen: false,
  showExport: false,
  exportLabel: '导出Excel',
  showImport: false,
  importLabel: 'Excel导入',
  showFormula: false,
  showTemplate: false,
  showEditToggle: false,
  isEditing: false,
  showDisplaySettings: false,
})

defineEmits<{
  (e: 'copy'): void
  (e: 'fullscreen'): void
  (e: 'export'): void
  (e: 'import'): void
  (e: 'formula'): void
  (e: 'template'): void
  (e: 'edit-toggle'): void
  (e: 'display-settings'): void
}>()
</script>

<style scoped>
.gt-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  position: relative;
  z-index: 1;
}

.gt-toolbar__left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.gt-toolbar__right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-left: auto;
}

/* 在紫色横幅内使用时，按钮样式继承父级 */
.gt-toolbar .el-button {
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.25);
  color: #fff;
}
.gt-toolbar .el-button:hover {
  background: rgba(255, 255, 255, 0.25);
}
.gt-toolbar .el-button--primary {
  background: rgba(255, 255, 255, 0.3);
  border-color: rgba(255, 255, 255, 0.4);
}
</style>
