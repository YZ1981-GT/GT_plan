<template>
  <div class="g4-tab-ref-pd-conversion">
    <!-- 蓝色信息条：只读参考提示 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="本sheet为参考材料，仅供查阅，不支持编辑"
      class="ref-info-bar"
    />

    <!-- 20行×2列只读表格（行数少，不需要虚拟滚动） -->
    <el-table
      :data="tableRows"
      border
      stripe
      size="small"
      style="width: 100%; font-size: 13px; max-width: 600px"
      class="ref-table"
    >
      <el-table-column
        v-for="col in columns"
        :key="col.prop"
        :prop="col.prop"
        :label="col.label"
        :min-width="col.minWidth || 160"
        align="center"
      />
    </el-table>

    <!-- 底部编制提示 -->
    <details class="guidance-details">
      <summary>编制提示</summary>
      <ul>
        <li>本sheet为PD（违约概率）折算参考表</li>
        <li>根据债权投资剩余期限查找对应的PD值</li>
        <li>用于G4-10减值准备测算中信用损失率的确定依据</li>
        <li>所有内容为只读，不可编辑</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabRefPdConversion.vue — 参考-根据剩余期限折算PD
 *
 * Spec: .kiro/specs/g4-bond-investment-ecl/ Task 11.1
 * 20行×2列只读HTML表格（剩余期限/PD值）
 * 顶部蓝色信息条"本sheet为参考材料，仅供查阅"
 * 只读保护（无编辑/保存按钮）
 * 行数少（20行），不需要虚拟滚动
 *
 * Requirements: 7.2, 7.5, 7.6, 11.11
 */
import { computed } from 'vue'

interface Props {
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}

const props = defineProps<Props>()

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
      minWidth: col.minWidth || col.width || 160,
    }))
  }

  if (data.headers && Array.isArray(data.headers)) {
    return data.headers.map((h: string, idx: number) => ({
      prop: `col${idx}`,
      label: h,
      minWidth: 160,
    }))
  }

  // fallback: 根据第一行数据的key推导列
  const rows = extractRows(data)
  if (rows.length > 0) {
    const firstRow = rows[0]
    return Object.keys(firstRow).map((key) => ({
      prop: key,
      label: key,
      minWidth: 160,
    }))
  }

  return defaultColumns()
})

const tableRows = computed<Record<string, any>[]>(() => {
  const data = props.htmlData
  if (!data) return []
  return extractRows(data)
})

// ─── 辅助函数 ────────────────────────────────────────────────────────────────

function extractRows(data: Record<string, any>): Record<string, any>[] {
  if (data.rows && Array.isArray(data.rows)) return data.rows
  if (data.data && Array.isArray(data.data)) return data.data
  if (data.tableData && Array.isArray(data.tableData)) return data.tableData
  return []
}

function defaultColumns(): ColumnDef[] {
  // 20行×2列PD折算对照表默认列定义
  return [
    { prop: 'remainingTerm', label: '剩余期限', minWidth: 180 },
    { prop: 'pdValue', label: 'PD值（违约概率）', minWidth: 180 },
  ]
}
</script>

<style scoped>
.g4-tab-ref-pd-conversion {
  padding: 0;
}
.ref-info-bar {
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
</style>
