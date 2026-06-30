<script setup lang="ts">
/**
 * D2TabDetail — 明细表D2-2 (39列宽表)
 * 横向滚动, 固定前2列, 关联方橙色背景, 搜索过滤, 虚拟滚动>30行
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { useD2Detail, type DetailRow } from '../composables/useD2Detail'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  relatedParties: string[]
}>()

const emit = defineEmits<{
  (e: 'export-template'): void
  (e: 'export-data'): void
  (e: 'import-data'): void
}>()

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话集成 (Task 47.1)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function handleCellContextMenu(row: any, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.property || 'unknown'
  const rowKey = row?.rowId || row?.seq || 'unknown'
  openReviewDialog(`D2-detail-${rowKey}-${field}`)
}

const viewMode = defineModel<'structured' | 'online'>('viewMode', { default: 'structured' })

const {
  rows,
  filteredRows,
  totalRow,
  searchQuery,
  addRow,
  removeRow,
  updateCell,
  useVirtualScroll,
} = useD2Detail({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  relatedParties: toRef(props, 'relatedParties') as Ref<string[]>,
})

const RELATION_OPTIONS = ['非关联方', '控股股东', '实际控制人', '其他关联方']
const CREDIT_RISK_OPTIONS = ['单项计提', '账龄组合', '客户类型组合']

function getRowClassName({ row }: { row: DetailRow }): string {
  if (row.relationType && row.relationType !== '非关联方') return 'related-party-row'
  return ''
}

function handleEdit(row: DetailRow, field: string, value: any) {
  if (props.isReadonly) return
  updateCell(row.rowId, field, value)
}
</script>

<template>
  <div class="d2-tab-detail">
    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="emit('export-template')">导出模板</el-button>
        <el-button size="small" @click="emit('export-data')">导出数据</el-button>
        <el-button size="small" @click="emit('import-data')">导入数据</el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">
          添加客户
        </el-button>
      </div>
      <div class="toolbar-right">
        <el-input
          v-model="searchQuery"
          placeholder="搜索客户名称..."
          size="small"
          clearable
          style="width: 200px; margin-right: 12px"
        />
        <el-segmented v-model="viewMode" :options="[
          { label: '结构化视图', value: 'structured' },
          { label: '在线编辑', value: 'online' },
        ]" size="small" />
      </div>
    </div>

    <!-- 虚拟滚动提示 -->
    <el-tag v-if="useVirtualScroll" type="info" size="small" class="virtual-hint">
      当前{{ rows.length }}行，已启用虚拟滚动
    </el-tag>

    <!-- 主表 -->
    <el-table
      :data="filteredRows"
      border
      stripe
      size="small"
      :row-class-name="getRowClassName"
      :max-height="600"
      style="width: 100%"
    >
      <el-table-column type="index" label="序号" width="60" fixed />
      <el-table-column prop="customerName" label="客户名称" width="160" fixed>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.customerName"
            size="small"
            @change="(v: string) => handleEdit(row, 'customerName', v)"
          />
          <span v-else>{{ row.customerName }}</span>
        </template>
      </el-table-column>

      <!-- 关联方类型 -->
      <el-table-column label="关联方类型" width="130">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.relationType"
            size="small"
            @change="(v: string) => handleEdit(row, 'relationType', v)"
          >
            <el-option v-for="opt in RELATION_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-else>{{ row.relationType }}</span>
        </template>
      </el-table-column>

      <!-- 期初 -->
      <el-table-column label="期初未审" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorUnadjusted) }}</template>
      </el-table-column>
      <el-table-column label="期初AJE" width="100" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorAje) }}</template>
      </el-table-column>
      <el-table-column label="期初RJE" width="100" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorRje) }}</template>
      </el-table-column>
      <el-table-column label="期初审定" width="110" align="right">
        <template #default="{ row }">
          <span style="font-weight: 600">{{ displayPrefs.fmtAmount(row.priorAudited) }}</span>
        </template>
      </el-table-column>

      <!-- 本期发生 -->
      <el-table-column label="借方发生" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.debitOccurrence) }}</template>
      </el-table-column>
      <el-table-column label="贷方发生" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.creditOccurrence) }}</template>
      </el-table-column>
      <el-table-column label="期末余额" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.endBalance) }}</template>
      </el-table-column>

      <!-- 期末 -->
      <el-table-column label="期末未审" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentUnadjusted) }}</template>
      </el-table-column>
      <el-table-column label="期末AJE" width="100" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentAje) }}</template>
      </el-table-column>
      <el-table-column label="期末RJE" width="100" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentRje) }}</template>
      </el-table-column>
      <el-table-column label="期末审定" width="110" align="right">
        <template #default="{ row }">
          <span style="font-weight: 600">{{ displayPrefs.fmtAmount(row.currentAudited) }}</span>
        </template>
      </el-table-column>

      <!-- 信用风险组合方式 -->
      <el-table-column label="信用风险组合方式" width="160">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.creditRiskClassification"
            size="small"
            @change="(v: string) => handleEdit(row, 'creditRiskClassification', v)"
          >
            <el-option v-for="opt in CREDIT_RISK_OPTIONS" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-else>{{ row.creditRiskClassification }}</span>
        </template>
      </el-table-column>

      <!-- 期后回款 -->
      <el-table-column label="期后回款" width="110" align="right">
        <template #default="{ row }">{{ displayPrefs.fmtAmount(row.postPayment) }}</template>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">{{ row.remark || '-' }}</template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column label="操作" width="70" fixed="right" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <div class="total-bar">
      <span class="total-label">合计</span>
      <span class="total-value">期初审定: {{ displayPrefs.fmtAmount(totalRow.priorAudited as number) }}</span>
      <span class="total-value">期末审定: {{ displayPrefs.fmtAmount(totalRow.currentAudited as number) }}</span>
      <span class="total-value">期后回款: {{ displayPrefs.fmtAmount(totalRow.postPayment as number) }}</span>
    </div>
  </div>
</template>

<style scoped>
.d2-tab-detail { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.toolbar-right { display: flex; align-items: center; }
.virtual-hint { margin-bottom: 8px; }
:deep(.related-party-row) { background-color: #fff7e6 !important; }
.total-bar {
  display: flex; gap: 24px; align-items: center;
  padding: 8px 12px; margin-top: 8px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px;
  font-size: 13px;
}
.total-label { font-weight: 600; }
.total-value { color: #606266; }
</style>
