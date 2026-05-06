<!--
  GtToolbar — 标准工具栏组件 [R5.1]
  统一各模块工具栏的通用操作按钮（导出/导入/全屏/公式/模板/编辑切换/显示设置），
  同时保留 left slot 供模块放置特有按钮。

  用法（横幅内，白色半透明按钮）：
    <GtToolbar variant="banner" :show-export="true" @export="onExport">
      <template #left>
        <el-button size="small" @click="onRecalc">🔄 全量重算</el-button>
      </template>
    </GtToolbar>

  用法（普通白色背景工具栏）：
    <GtToolbar variant="default" :show-export="true" @export="onExport" />
-->
<template>
  <div class="gt-toolbar" :class="`gt-toolbar--${variant}`">
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
  /**
   * 外观变体
   * - 'banner'：用于紫色横幅内，按钮为白色半透明风格
   * - 'default'：用于普通白色背景，按钮为标准 Element Plus 风格
   */
  variant?: 'banner' | 'default'
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
  variant: 'banner',
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

/* banner 模式：紫色横幅内白色半透明按钮 */
.gt-toolbar--banner .el-button {
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.25);
  color: #fff;
}
.gt-toolbar--banner .el-button:hover {
  background: rgba(255, 255, 255, 0.25);
}
.gt-toolbar--banner .el-button--primary {
  background: rgba(255, 255, 255, 0.3);
  border-color: rgba(255, 255, 255, 0.4);
}

/* default 模式：普通背景，使用 Element Plus 默认按钮样式（不覆盖） */
.gt-toolbar--default .el-button {
  /* 继承 Element Plus 默认样式，不做覆盖 */
}
</style>
