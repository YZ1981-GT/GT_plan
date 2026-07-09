<script setup lang="ts">
/**
 * GtS34SubCheckTable.vue — Tab 内子 sheet 切换（核查程序 / 明细检查表）
 *
 * 用于 hasSubTable=true 的专项底稿 Tab，提供子 sheet 分段切换：
 * - "核查程序表" 视图（由父组件 GtS34Bundle 已渲染的 GtAProgramConsole 处理）
 * - "明细检查表" 视图（子 sheet 如 S34-16-1、S34-16-2 等）
 *
 * 🔴 不使用内部 el-tabs！用 el-segmented + v-if 切换
 *
 * Task 7.1: 基础分段切换
 * Task 7.3: 保留合理性/真实性核查判断列 + 动态明细行导入导出
 *
 * Requirements: 5.1, 5.3, 5.4
 */
import { ref, computed, toRef } from 'vue'
import { useS34ImportExport } from './useS34ImportExport'
import type { UploadFile } from 'element-plus'

// ─── Props ───
const props = withDefaults(defineProps<{
  /** 当前专项底稿 wp_id（from wpIdMap） */
  wpId: string
  /** 子 sheet 编码列表（如 ['S34-16-1', 'S34-16-2']） */
  subSheets: string[]
  /** 完整 S34 wpIdMap 用于解析子 sheet wp_id */
  wpIdMap: Record<string, string>
  /** 项目 ID */
  projectId: string
  /** 只读模式 */
  readonly?: boolean
  /** 是否为动态明细行表格（控制导入导出是否可用） */
  isDynamic?: boolean
}>(), {
  readonly: false,
  isDynamic: true,
  projectId: '',
})

// ─── 视图切换 ───
/** 当前激活视图：'program' = 核查程序表，子 sheet code = 明细检查表 */
const activeView = ref<string>('program')

/** el-segmented options：核查程序 | 子表1 | 子表2 ... */
const viewOptions = computed(() => {
  const options: Array<{ label: string; value: string }> = [
    { label: '核查程序', value: 'program' },
  ]
  for (const code of props.subSheets) {
    options.push({ label: code, value: code })
  }
  return options
})

/** 当前选中子 sheet 的 wp_id（明细检查表视图时使用） */
const activeSubWpId = computed(() => {
  if (activeView.value === 'program') return null
  return props.wpIdMap[activeView.value] || null
})

// ─── 判断列选项（合理性/真实性核查） ───

/** 合理性核查判断选项 */
const reasonablenessOptions = [
  { label: '合理', value: 'reasonable' },
  { label: '存疑', value: 'questionable' },
  { label: '不合理', value: 'unreasonable' },
]

/** 真实性核查判断选项 */
const authenticityOptions = [
  { label: '一致', value: 'consistent' },
  { label: '不一致', value: 'inconsistent' },
  { label: '待核实', value: 'pending' },
]

/** 合规风险判断选项 */
const complianceRiskOptions = [
  { label: '无风险', value: 'no_risk' },
  { label: '低风险', value: 'low_risk' },
  { label: '中风险', value: 'medium_risk' },
  { label: '高风险', value: 'high_risk' },
]

// ─── 导入导出（仅动态明细行表格需要） ───

const activeSheetCode = computed(() => activeView.value === 'program' ? '' : activeView.value)

const {
  importing,
  exportTemplate,
  exportData,
  importData,
} = useS34ImportExport({
  wpId: computed(() => activeSubWpId.value || props.wpId) as any,
  projectId: toRef(props, 'projectId') as any,
  sheetCode: activeSheetCode as any,
  onImported: () => {
    // 触发数据刷新（后续由 Task 8+ 完善实际数据加载逻辑）
  },
})

/** 导入导出是否可用：非核查程序视图 + 动态行 + 非只读 */
const importExportEnabled = computed(() =>
  activeView.value !== 'program' && props.isDynamic && !props.readonly,
)

/** 导入导出下拉命令处理 */
function handleIECommand(command: string): void {
  switch (command) {
    case 'template':
      exportTemplate()
      break
    case 'export':
      exportData()
      break
    // import 由 el-upload 处理
  }
}

/** 导入文件选择回调 */
function onImportFile(uploadFile: UploadFile): void {
  if (!uploadFile.raw) return
  importData(uploadFile.raw)
}
</script>

<template>
  <div class="gt-s34-sub-check-table">
    <!-- 工具栏：分段切换器 + 导入导出 -->
    <div class="gt-s34-sub-check-table__toolbar">
      <!-- 分段切换器：核查程序 | 子表1 | 子表2 ... -->
      <el-segmented
        v-model="activeView"
        :options="viewOptions"
        size="small"
        class="gt-s34-sub-check-table__switcher"
      />

      <!-- 导入导出 el-dropdown（仅动态明细行表格 + 非核查程序视图） -->
      <el-dropdown
        v-if="importExportEnabled"
        trigger="click"
        size="small"
        @command="handleIECommand"
      >
        <el-button size="small" :loading="importing">
          导入导出 ▾
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export">导出数据</el-dropdown-item>
            <el-dropdown-item command="import">
              <el-upload
                :show-file-list="false"
                accept=".xlsx"
                :auto-upload="false"
                :disabled="readonly || importing"
                @change="onImportFile"
              >
                <span>导入数据</span>
              </el-upload>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 子检查表渲染区域（activeView !== 'program' 时显示） -->
    <div v-if="activeView !== 'program'" class="gt-s34-sub-check-table__content">
      <!-- 明细检查表 placeholder + 判断列演示 -->
      <div class="sub-table-placeholder">
        <el-icon size="20" style="margin-right: 8px; vertical-align: middle;">
          <Document />
        </el-icon>
        <span>{{ activeView }} 明细检查表</span>
        <span v-if="activeSubWpId" class="sub-table-placeholder__wpid">
          （wp_id: {{ activeSubWpId }}）
        </span>
        <span v-else class="sub-table-placeholder__missing">
          （底稿未生成）
        </span>
      </div>

      <!-- 核查判断列区域（合理性/真实性/合规风险） -->
      <div class="gt-s34-sub-check-table__judgment-columns">
        <div class="judgment-column-header">
          <span class="judgment-title">核查判断列</span>
          <span class="judgment-desc">（点选优先，合理性/真实性核查判断及合规风险评估）</span>
        </div>
        <div class="judgment-column-demos">
          <!-- 合理性核查 -->
          <div class="judgment-item">
            <span class="judgment-label">合理性核查</span>
            <el-select
              size="small"
              placeholder="请选择"
              :disabled="readonly"
              style="width: 120px"
            >
              <el-option
                v-for="opt in reasonablenessOptions"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </div>
          <!-- 真实性核查 -->
          <div class="judgment-item">
            <span class="judgment-label">真实性核查</span>
            <el-select
              size="small"
              placeholder="请选择"
              :disabled="readonly"
              style="width: 120px"
            >
              <el-option
                v-for="opt in authenticityOptions"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </div>
          <!-- 合规风险 -->
          <div class="judgment-item">
            <span class="judgment-label">合规风险</span>
            <el-select
              size="small"
              placeholder="请选择"
              :disabled="readonly"
              style="width: 120px"
            >
              <el-option
                v-for="opt in complianceRiskOptions"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { Document } from '@element-plus/icons-vue'
export default { components: { Document } }
</script>

<style scoped>
.gt-s34-sub-check-table {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--gt-color-border-light, #ebeef5);
}

.gt-s34-sub-check-table__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.gt-s34-sub-check-table__switcher {
  flex: 0 0 auto;
}

.gt-s34-sub-check-table__content {
  min-height: 120px;
}

.sub-table-placeholder {
  display: flex;
  align-items: center;
  padding: 16px 20px;
  background: var(--gt-color-bg-elevated, #fafafa);
  border: 1px dashed var(--gt-color-border, #dcdfe6);
  border-radius: var(--gt-radius-sm, 4px);
  font-size: 13px;
  color: var(--gt-color-text-secondary, #606266);
}

.sub-table-placeholder__wpid {
  margin-left: 4px;
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}

.sub-table-placeholder__missing {
  margin-left: 4px;
  font-size: 12px;
  color: var(--gt-color-warning, #e6a23c);
}

/* ─── 核查判断列样式 ─── */

.gt-s34-sub-check-table__judgment-columns {
  margin-top: 16px;
  padding: 12px 16px;
  background: var(--gt-color-bg-elevated, #fafafa);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: var(--gt-radius-sm, 4px);
}

.judgment-column-header {
  margin-bottom: 10px;
}

.judgment-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}

.judgment-desc {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
  margin-left: 8px;
}

.judgment-column-demos {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.judgment-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.judgment-label {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #606266);
  white-space: nowrap;
}
</style>
