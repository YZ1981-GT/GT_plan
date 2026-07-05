<script setup lang="ts">
/**
 * D2TabBadDebt — 坏账准备D2-3
 * 14列, 固定行+可展开子行, ECL差异警告
 */
import { ref, inject, toRef, type Ref } from 'vue'
import { useD2BadDebt, type BadDebtRow } from '../composables/useD2BadDebt'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const { onExportTemplate, onExportData, onImportFile } = useD2TabImportExport(
  toRef(props, 'wpId') as Ref<string>,
  toRef(props, 'projectId') as Ref<string>,
  'D2-3',
)

const displayPrefs = inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {
  fmtAmount: (v: number) => v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
})

// 复核对话集成 (Task 47.1)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function handleCellContextMenu(row: any, column: any, event: MouseEvent): void {
  if (!openReviewDialog) return
  event.preventDefault()
  const field = column?.property || 'unknown'
  const rowKey = row?.rowId || row?.category || 'unknown'
  openReviewDialog(`D2-baddebt-${rowKey}-${field}`)
}

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)
const eclTestTotal = ref(0)

const {
  individualRows,
  agingRows,
  customerTypeRows,
  totalRow,
  eclDifference,
  eclWarning,
  addSubRow,
  removeSubRow,
  updateCell,
} = useD2BadDebt({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  eclTestTotal,
})

type Category = 'individual' | 'aging' | 'customer-type'

const sections: Array<{ category: Category; title: string; rows: Ref<BadDebtRow[]> }> = [
  { category: 'individual', title: '按单项计提', rows: individualRows },
  { category: 'aging', title: '按账龄组合', rows: agingRows },
  { category: 'customer-type', title: '按客户类型组合', rows: customerTypeRows },
]
</script>

<template>
  <div class="d2-tab-bad-debt">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </div>
      </div>
    </div>

    <!-- ECL差异警告 -->
    <el-alert v-if="eclWarning" type="warning" :closable="false" class="ecl-alert">
      <span>{{ eclWarning }}</span>
      <GtIndexChip
        v-if="jumpToSection"
        label="D2-9"
        class="ecl-chip"
        @click="jumpToSection('应收坏账准备测算D2-9')"
      />
    </el-alert>

    <!-- 三分类区块 -->
    <div v-for="section in sections" :key="section.category" class="section-block">
      <div class="section-header">
        <span class="section-title">{{ section.title }}</span>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          link
          @click="addSubRow(section.category)"
        >+ 添加子行</el-button>
      </div>

      <el-table :data="section.rows.value" border size="small" style="width: 100%">
        <el-table-column prop="label" label="项目" width="160">
          <template #default="{ row }">
            <el-input
              v-if="row.isSubRow && !isReadonly"
              :model-value="row.label"
              size="small"
              placeholder="债务人/组合名称"
              @change="(v: string) => updateCell(row.rowId, 'label', v as any)"
            />
            <span v-else :style="{ fontWeight: row.isFixed ? '600' : 'normal' }">{{ row.label }}</span>
            <GtReviewDot row-prefix="D2-baddebt" :row-key="row.rowId" />
          </template>
        </el-table-column>

        <!-- 期初 -->
        <el-table-column label="期初未审" width="100" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorUnadjusted) }}</template>
        </el-table-column>
        <el-table-column label="期初AJE" width="90" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorAje) }}</template>
        </el-table-column>
        <el-table-column label="期初RJE" width="90" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorRje) }}</template>
        </el-table-column>
        <el-table-column label="期初审定" width="100" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.priorAudited) }}</template>
        </el-table-column>

        <!-- 本期增加 -->
        <el-table-column label="计提" width="100" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentProvision) }}</template>
        </el-table-column>
        <el-table-column label="转入" width="90" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentTransferIn) }}</template>
        </el-table-column>

        <!-- 本期减少 -->
        <el-table-column label="收回" width="90" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentRecovery) }}</template>
        </el-table-column>
        <el-table-column label="转回" width="90" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentReversal) }}</template>
        </el-table-column>
        <el-table-column label="核销" width="90" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentWriteOff) }}</template>
        </el-table-column>

        <!-- 期末 -->
        <el-table-column label="期末未审" width="100" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentUnadjusted) }}</template>
        </el-table-column>
        <el-table-column label="期末AJE" width="90" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentAje) }}</template>
        </el-table-column>
        <el-table-column label="期末RJE" width="90" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.currentRje) }}</template>
        </el-table-column>
        <el-table-column label="期末审定" width="100" align="right">
          <template #default="{ row }">
            <span style="font-weight: 600">{{ displayPrefs.fmtAmount(row.currentAudited) }}</span>
          </template>
        </el-table-column>

        <!-- 操作 -->
        <el-table-column label="操作" width="60" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button v-if="row.isSubRow" type="danger" link size="small" @click="removeSubRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 合计行 -->
    <div class="total-bar">
      <span class="total-label">合计</span>
      <span>期初审定: {{ displayPrefs.fmtAmount(totalRow.priorAudited) }}</span>
      <span>期末审定: {{ displayPrefs.fmtAmount(totalRow.currentAudited) }}</span>
    </div>
  </div>
</template>

<style scoped>
.d2-tab-bad-debt { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.ecl-alert { margin-bottom: 12px; }
.ecl-chip { margin-left: 8px; vertical-align: middle; }
.section-block { margin-bottom: 16px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.section-title { font-weight: 600; font-size: 14px; }
.total-bar {
  display: flex; gap: 24px; align-items: center;
  padding: 8px 12px; margin-top: 8px;
  background: #fafafa; border: 1px solid #ebeef5; border-radius: 4px; font-size: 13px; font-weight: 600;
}
.total-label { font-weight: 700; }
</style>
