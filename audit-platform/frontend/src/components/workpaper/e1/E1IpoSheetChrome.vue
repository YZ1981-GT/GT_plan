<script setup lang="ts">
/**
 * E1IpoSheetChrome — IPO/舞弊应对表共用壳
 * 适用性开关 · 状态标签 · 操作区 · 导入导出 · 交叉索引 · 未启用空态 · skeleton
 */
import GtIndexChip from '../GtIndexChip.vue'

defineProps<{
  title: string
  isApplicable: boolean
  isReadonly?: boolean
  isLoading?: boolean
  projectId: string
  /** 如 ['wp:E1-10', 'wp:E1-31'] */
  indexChips?: string[]
  showImportExport?: boolean
  isImporting?: boolean
  applicableActiveText?: string
  applicableInactiveText?: string
  notApplicableText?: string
  skeletonRows?: number
}>()

const emit = defineEmits<{
  'update:applicable': [value: boolean]
  exportTemplate: []
  exportData: []
  /** before-upload 约定：返回 false 阻止清空选中 */
  import: [file: File]
}>()

function onApplicableChange(v: string | number | boolean): void {
  emit('update:applicable', Boolean(v))
}

function onBeforeImport(file: File): boolean {
  emit('import', file)
  return false
}
</script>

<template>
  <div class="e1-ipo-sheet-chrome">
    <slot name="guidance" />
    <slot name="goal" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="warning">{{ title }}</el-tag>
        <el-switch
          :model-value="isApplicable"
          :disabled="isReadonly"
          :active-text="applicableActiveText || '已启用IPO/舞弊应对程序'"
          :inactive-text="applicableInactiveText || '未启用'"
          @change="onApplicableChange"
        />
        <slot name="status" />
      </div>
      <div class="toolbar-right">
        <slot name="actions" />
        <el-dropdown
          v-if="showImportExport !== false"
          size="small"
          trigger="click"
          :disabled="isReadonly || !isApplicable"
        >
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="emit('exportTemplate')">导出模板</el-dropdown-item>
              <el-dropdown-item @click="emit('exportData')">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx,.xls"
                  :before-upload="onBeforeImport"
                  :disabled="isImporting"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span
          v-for="chip in (indexChips || [])"
          :key="chip"
          class="chip-wrap"
        >
          <GtIndexChip :value="chip" :context-project-id="projectId" />
        </span>
      </div>
    </div>

    <div v-if="!isApplicable" class="not-applicable">
      <el-empty :description="notApplicableText || '未启用IPO/舞弊应对程序'" :image-size="80" />
    </div>

    <el-skeleton v-else :loading="!!isLoading" :rows="skeletonRows || 12" animated>
      <template #default>
        <slot />
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.chip-wrap {
  display: inline-flex;
}
.not-applicable {
  padding: 48px 0;
  text-align: center;
}
</style>
