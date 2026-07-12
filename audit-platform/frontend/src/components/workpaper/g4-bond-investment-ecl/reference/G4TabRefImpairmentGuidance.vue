<template>
  <div class="g4-tab-ref-impairment-guidance">
    <!-- 蓝色信息条：只读参考提示 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="本sheet为参考材料，仅供查阅，不支持编辑"
      class="ref-info-bar"
    />

    <!-- 搜索栏 -->
    <div class="ref-toolbar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索内容（Ctrl+F）..."
        size="small"
        clearable
        :prefix-icon="Search"
        style="width: 260px"
        @keydown.ctrl.f.prevent="focusSearch"
      />
      <el-tag v-if="searchKeyword && filteredRows.length !== tableRows.length" size="small" type="info">
        匹配 {{ filteredRows.length }} / {{ tableRows.length }} 行
      </el-tag>
    </div>

    <!-- 178行×13列只读HTML表格 + 虚拟滚动(max-height) -->
    <el-table
      :data="filteredRows"
      border
      stripe
      size="small"
      :max-height="600"
      style="width: 100%; font-size: 13px"
      class="ref-table"
    >
      <el-table-column
        v-for="col in columns"
        :key="col.prop"
        :prop="col.prop"
        :label="col.label"
        :min-width="col.minWidth || 120"
      >
        <template #default="{ row }">
          <span
            v-if="searchKeyword"
            v-html="highlightText(String(row[col.prop] ?? ''), searchKeyword)"
          />
          <span v-else>{{ row[col.prop] ?? '' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部编制提示 -->
    <details class="guidance-details">
      <summary>编制提示</summary>
      <ul>
        <li>本sheet内容来源于中证协《证券公司金融工具减值指引》</li>
        <li>共178行×13列，作为减值测算的参考依据</li>
        <li>支持全文搜索（输入关键字过滤匹配行）</li>
        <li>所有内容为只读，不可编辑</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabRefImpairmentGuidance.vue — 参考-中证协金融工具减值指引
 *
 * Spec: .kiro/specs/g4-bond-investment-ecl/ Task 11.1
 * 178行×13列只读HTML表格 + 虚拟滚动(el-table max-height)
 * 顶部蓝色信息条"本sheet为参考材料，仅供查阅"
 * 全文搜索（输入关键字高亮匹配行）
 * 只读保护（无编辑/保存按钮）
 *
 * Requirements: 7.1, 7.3, 7.4, 7.5, 7.6, 11.6, 11.11
 */
import { ref, computed } from 'vue'
import { Search } from '@element-plus/icons-vue'

interface Props {
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}

const props = defineProps<Props>()

// ─── 搜索关键字 ──────────────────────────────────────────────────────────────
const searchKeyword = ref('')

// ─── 从htmlData动态解析列定义和行数据 ────────────────────────────────────────
interface ColumnDef {
  prop: string
  label: string
  minWidth?: number
}

const columns = computed<ColumnDef[]>(() => {
  const data = props.htmlData
  if (!data) return defaultColumns()

  // 从htmlData的columns/headers字段提取列定义
  if (data.columns && Array.isArray(data.columns)) {
    return data.columns.map((col: any, idx: number) => ({
      prop: col.prop || col.field || `col${idx}`,
      label: col.label || col.title || col.header || `列${idx + 1}`,
      minWidth: col.minWidth || col.width || 120,
    }))
  }

  if (data.headers && Array.isArray(data.headers)) {
    return data.headers.map((h: string, idx: number) => ({
      prop: `col${idx}`,
      label: h,
      minWidth: 120,
    }))
  }

  // fallback: 根据第一行数据的key推导列
  const rows = extractRows(data)
  if (rows.length > 0) {
    const firstRow = rows[0]
    return Object.keys(firstRow).map((key, idx) => ({
      prop: key,
      label: key,
      minWidth: idx === 0 ? 60 : 120,
    }))
  }

  return defaultColumns()
})

const tableRows = computed<Record<string, any>[]>(() => {
  const data = props.htmlData
  if (!data) return []
  return extractRows(data)
})

/** 按搜索关键字过滤行 */
const filteredRows = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return tableRows.value

  return tableRows.value.filter((row) => {
    return Object.values(row).some((val) =>
      String(val ?? '').toLowerCase().includes(kw),
    )
  })
})

// ─── 辅助函数 ────────────────────────────────────────────────────────────────

function extractRows(data: Record<string, any>): Record<string, any>[] {
  // 优先取data.rows
  if (data.rows && Array.isArray(data.rows)) return data.rows
  // 取data.data
  if (data.data && Array.isArray(data.data)) return data.data
  // 取data.tableData
  if (data.tableData && Array.isArray(data.tableData)) return data.tableData
  return []
}

function defaultColumns(): ColumnDef[] {
  // 178行×13列中证协减值指引默认列定义
  return [
    { prop: 'col0', label: '序号', minWidth: 60 },
    { prop: 'col1', label: '章节', minWidth: 100 },
    { prop: 'col2', label: '条款编号', minWidth: 90 },
    { prop: 'col3', label: '条款内容', minWidth: 240 },
    { prop: 'col4', label: '适用金融工具', minWidth: 120 },
    { prop: 'col5', label: '减值阶段', minWidth: 80 },
    { prop: 'col6', label: '计量方法', minWidth: 100 },
    { prop: 'col7', label: '参数要求', minWidth: 120 },
    { prop: 'col8', label: '披露要求', minWidth: 120 },
    { prop: 'col9', label: '过渡期规定', minWidth: 100 },
    { prop: 'col10', label: '内控要求', minWidth: 100 },
    { prop: 'col11', label: '备注', minWidth: 100 },
    { prop: 'col12', label: '参考', minWidth: 80 },
  ]
}

/** 高亮匹配文本（用<mark>标签包裹） */
function highlightText(text: string, keyword: string): string {
  if (!keyword) return text
  const escaped = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(`(${escaped})`, 'gi')
  return text.replace(regex, '<mark class="search-highlight">$1</mark>')
}

/** 聚焦搜索框 */
function focusSearch(): void {
  // Ctrl+F默认行为已被preventDefault
}
</script>

<style scoped>
.g4-tab-ref-impairment-guidance {
  padding: 0;
}
.ref-info-bar {
  margin-bottom: 12px;
}
.ref-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.ref-table {
  margin-bottom: 12px;
}
.ref-table :deep(.cell) {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.5;
}
.guidance-details {
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}
.guidance-details ul {
  margin: 8px 0 0 16px;
  padding: 0;
}
.guidance-details li {
  margin-bottom: 4px;
}
:deep(.search-highlight) {
  background-color: #ffd54f;
  padding: 0 2px;
  border-radius: 2px;
}
</style>
