<script setup lang="ts">
/**
 * D2TabPledgeCheck — 质押保理D2-12
 * 双区块: 质押情况(9列) + 保理终止确认(8列)
 * 质押比例>50%红色警告, CAS23自动终止确认
 */
import { inject, toRef, type Ref } from 'vue'
import { useD2PledgeCheck } from '../composables/useD2PledgeCheck'
import { useD2TabImportExport } from '../composables/useD2TabImportExport'
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
  'D2-12',
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
  const rowKey = row?.rowId || row?.customerName || 'unknown'
  openReviewDialog(`D2-pledge-${rowKey}-${field}`)
}


const {
  pledgeRows,
  factoringRows,
  pledgeTotal,
  pledgeRatio,
  pledgeRatioWarning,
  addPledgeRow,
  addFactoringRow,
  removeRow,
  updateCell,
} = useD2PledgeCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})
</script>

<template>
  <div class="d2-tab-pledge">
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload :show-file-list="false" accept=".xlsx" :before-upload="onImportFile">
          <el-button size="small">导入数据</el-button>
        </el-upload>
      </div>
    </div>

    <!-- 质押比例警告 -->
    <el-alert v-if="pledgeRatioWarning" type="error" :closable="false" class="pledge-alert">
      {{ pledgeRatioWarning }}
    </el-alert>

    <!-- 质押区域 -->
    <div class="section-block">
      <div class="section-header">
        <span class="section-title">
          质押情况
          <el-tag size="small" :type="pledgeRatio > 0.5 ? 'danger' : 'info'" style="margin-left:8px">
            质押比例: {{ (pledgeRatio * 100).toFixed(1) }}%
          </el-tag>
        </span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addPledgeRow">添加</el-button>
      </div>
      <el-table :data="pledgeRows" border size="small" style="width: 100%">
        <el-table-column label="质押债务人" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small" @change="(v: string) => updateCell(row.rowId, 'debtorName', v)" />
            <span v-else>{{ row.debtorName || '-' }}</span>
            <GtReviewDot row-prefix="D2-pledge" :row-key="row.rowId" />
          </template>
        </el-table-column>
        <el-table-column label="质押金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.pledgeAmount" size="small" :controls="false" :precision="2" @change="(v: number) => updateCell(row.rowId, 'pledgeAmount', v)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.pledgeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="质押日期" width="110">
          <template #default="{ row }">{{ row.pledgeDate || '-' }}</template>
        </el-table-column>
        <el-table-column label="质权人" width="100">
          <template #default="{ row }">{{ row.pledgee || '-' }}</template>
        </el-table-column>
        <el-table-column label="质押目的" width="100">
          <template #default="{ row }">{{ row.pledgePurpose || '-' }}</template>
        </el-table-column>
        <el-table-column label="到期日" width="100">
          <template #default="{ row }">{{ row.expiryDate || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === '有效' ? 'success' : 'info'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="80">
          <template #default="{ row }">{{ row.remark || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="60" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="removeRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="total-line">质押合计: {{ displayPrefs.fmtAmount(pledgeTotal) }}</div>
    </div>

    <!-- 保理终止确认区域 -->
    <div class="section-block">
      <div class="section-header">
        <span class="section-title">保理终止确认 (CAS 23)</span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addFactoringRow">添加</el-button>
      </div>
      <el-table :data="factoringRows" border size="small" style="width: 100%">
        <el-table-column label="债务人" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small" @change="(v: string) => updateCell(row.rowId, 'debtorName', v)" />
            <span v-else>{{ row.debtorName || '-' }}</span>
            <GtReviewDot row-prefix="D2-pledge" :row-key="row.rowId" />
          </template>
        </el-table-column>
        <el-table-column label="保理金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.factoringAmount" size="small" :controls="false" :precision="2" @change="(v: number) => updateCell(row.rowId, 'factoringAmount', v)" />
            <span v-else>{{ displayPrefs.fmtAmount(row.factoringAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="保理日期" width="110">
          <template #default="{ row }">{{ row.factoringDate || '-' }}</template>
        </el-table-column>
        <el-table-column label="保理商" width="100">
          <template #default="{ row }">{{ row.factor || '-' }}</template>
        </el-table-column>
        <el-table-column label="风险已转移" width="90" align="center">
          <template #default="{ row }">
            <el-switch v-if="!isReadonly" :model-value="row.riskTransferred" @change="(v: boolean) => updateCell(row.rowId, 'riskTransferred', v)" size="small" />
            <span v-else>{{ row.riskTransferred ? 'Y' : 'N' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="保留控制" width="90" align="center">
          <template #default="{ row }">
            <el-switch v-if="!isReadonly" :model-value="row.controlRetained" @change="(v: boolean) => updateCell(row.rowId, 'controlRetained', v)" size="small" />
            <span v-else>{{ row.controlRetained ? 'Y' : 'N' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="终止确认" width="100">
          <template #default="{ row }">
            <el-tag :type="row.derecognition === '终止确认' ? 'success' : 'warning'" size="small">
              {{ row.derecognition }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="removeRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.d2-tab-pledge { padding: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.toolbar-left { display: flex; gap: 8px; }
.pledge-alert { margin-bottom: 12px; }
.section-block { margin-bottom: 20px; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.section-title { font-weight: 600; font-size: 14px; }
.total-line { text-align: right; font-size: 13px; font-weight: 600; margin-top: 6px; padding: 4px 8px; background: #fafafa; border-radius: 4px; }
</style>
