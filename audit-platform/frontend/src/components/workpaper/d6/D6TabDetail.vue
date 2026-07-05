<template>
<div class="d6-tab-detail">
  <!-- 工具栏 -->
  <div class="detail-toolbar">
    <el-input
      v-model="searchFilter"
      placeholder="搜索合同名称/客户名称..."
      size="small"
      style="width:240px"
      clearable
    />
    <div class="toolbar-actions">
      <el-segmented v-model="columnGroup" :options="columnGroupOptions" size="small" />
      <GtReviewTrigger section-id="D6-2-header" />
      <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">添加明细行</el-button>
      <el-button size="small" :disabled="isReadonly" @click="importFromAuxBalance">从余额表导入</el-button>
      <el-button size="small" :disabled="isReadonly" @click="exportTemplate">导出空模板</el-button>
      <el-button size="small" :disabled="isReadonly" @click="exportData">导出数据</el-button>
      <el-upload
        :show-file-list="false"
        accept=".xlsx"
        :auto-upload="false"
        :disabled="isReadonly || importing"
        @change="(f: any) => onImportFile(f.raw || f)"
      >
        <el-button size="small" :disabled="isReadonly || importing">导入数据</el-button>
      </el-upload>
    </div>
  </div>

  <div v-if="useVirtualScroll" class="virtual-toolbar">
    <el-alert type="info" :closable="false" class="virtual-hint">
      行数较多（{{ browseRowCount }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式 · 双击行可切换编辑
    </el-alert>
    <el-button size="small" @click="toggleBrowseMode">
      {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
    </el-button>
  </div>
  <el-table-v2
    v-if="useVirtualScroll && browseMode"
    :columns="virtualColumns"
    :data="browseRows"
    :width="tableWidth"
    :height="tableHeight"
    :row-height="36"
    :header-height="40"
    :row-event-handlers="rowEventHandlers"
    fixed
    class="virtual-table"
  />

  <div v-if="!useVirtualScroll || !browseMode">
    <el-table
      :data="displayRows"
      size="small"
      border
      stripe
      max-height="600"
      style="width:100%"
    >
      <el-table-column label="序号" width="60" fixed align="center">
        <template #default="{ row }">
          <span v-if="!row._isSubtotal && !row._isTotal">{{ row.seqNo }}</span>
        </template>
      </el-table-column>

      <el-table-column label="合同名称" width="150" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-label">{{ row.contractName }}</span>
          </template>
          <el-input
            v-else-if="!isReadonly"
            :model-value="row.contractName"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'contractName', v)"
          />
          <span v-else>{{ row.contractName }}</span>
        </template>
      </el-table-column>

      <el-table-column label="类型" width="120" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-label">{{ row.contractType }}</span>
          </template>
          <el-select
            v-else-if="!isReadonly"
            :model-value="row.contractType"
            size="small"
            placeholder="选择类型"
            @change="(v: string) => updateCell(row.rowId, 'contractType', v)"
          >
            <el-option v-for="t in CONTRACT_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
          <span v-else>{{ row.contractType }}</span>
        </template>
      </el-table-column>

      <el-table-column label="客户名称" width="140" fixed>
        <template #default="{ row }">
          <el-input
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            :model-value="row.customerName"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'customerName', v)"
          />
          <span v-else>{{ row.customerName }}</span>
        </template>
      </el-table-column>

      <el-table-column label="公司代码" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            :model-value="row.companyCode"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'companyCode', v)"
          />
          <span v-else>{{ row.companyCode }}</span>
        </template>
      </el-table-column>

      <el-table-column label="关联关系" width="140">
        <template #default="{ row }">
          <el-select
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            :model-value="row.relatedPartyType"
            size="small"
            placeholder="选择"
            @change="(v: string) => updateCell(row.rowId, 'relatedPartyType', v)"
          >
            <el-option v-for="t in RELATED_PARTY_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
          <span v-else>{{ row.relatedPartyType }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期初未审" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.priorUnadjusted) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.priorUnadjusted"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'priorUnadjusted', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.priorUnadjusted) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期初AJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.priorAje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.priorAje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'priorAje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.priorAje) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期初RJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.priorRje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.priorRje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'priorRje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.priorRje) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期初审定" width="110" align="right">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.priorAudited) }}</span>
        </template>
      </el-table-column>

      <template v-if="showAgingCols">
        <el-table-column label="期初≤1年" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.agePrior1y) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.agePrior1y"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'agePrior1y', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.agePrior1y) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初1~2年" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.agePrior1to2y) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.agePrior1to2y"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'agePrior1to2y', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.agePrior1to2y) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初2~3年" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.agePrior2to3y) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.agePrior2to3y"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'agePrior2to3y', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.agePrior2to3y) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初3年+" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.agePrior3yAbove) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.agePrior3yAbove"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'agePrior3yAbove', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.agePrior3yAbove) }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column label="借方发生" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.debitAmount) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.debitAmount"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'debitAmount', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="贷方发生" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.creditAmount) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.creditAmount"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'creditAmount', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期末未审" width="110" align="right">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.endUnadjusted) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期末AJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.endAje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.endAje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'endAje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.endAje) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期末RJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.endRje) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.endRje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'endRje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.endRje) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期末审定" width="110" align="right">
        <template #default="{ row }">
          <span class="auto-calc">{{ fmtAmount(row.endAudited) }}</span>
        </template>
      </el-table-column>

      <template v-if="showAgingCols">
        <el-table-column label="期末≤1年" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.ageEnd1y) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.ageEnd1y"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'ageEnd1y', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.ageEnd1y) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末1~2年" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.ageEnd1to2y) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.ageEnd1to2y"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'ageEnd1to2y', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.ageEnd1to2y) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末2~3年" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.ageEnd2to3y) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.ageEnd2to3y"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'ageEnd2to3y', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.ageEnd2to3y) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末3年+" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-amount">{{ fmtAmount(row.ageEnd3yAbove) }}</span>
            </template>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.ageEnd3yAbove"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updateCell(row.rowId, 'ageEnd3yAbove', v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.ageEnd3yAbove) }}</span>
          </template>
        </el-table-column>
      </template>

      <el-table-column label="1年以内收款权" width="120" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.receivableWithin1y) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.receivableWithin1y"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'receivableWithin1y', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.receivableWithin1y) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="1年以上收款权" width="120" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.receivableAbove1y) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.receivableAbove1y"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'receivableAbove1y', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.receivableAbove1y) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="建设期/质保期" width="110" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            :model-value="row.isInConstructionPeriod"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'isInConstructionPeriod', v)"
          >
            <el-option v-for="o in CONSTRUCTION_PERIOD_OPTIONS" :key="o" :label="o" :value="o" />
          </el-select>
          <span v-else>{{ row.isInConstructionPeriod || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="信用风险组合" width="120">
        <template #default="{ row }">
          <el-select
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            :model-value="row.creditRiskGroup"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'creditRiskGroup', v)"
          >
            <el-option v-for="g in CREDIT_RISK_GROUPS" :key="g" :label="g" :value="g" />
          </el-select>
          <span v-else>{{ row.creditRiskGroup }}</span>
        </template>
      </el-table-column>

      <el-table-column label="是否函证" width="80" align="center">
        <template #default="{ row }">
          <el-input
            v-if="!row._isSubtotal && !row._isTotal && !isReadonly"
            :model-value="row.isConfirmed"
            size="small"
            @change="(v: string) => updateCell(row.rowId, 'isConfirmed', v)"
          />
          <span v-else>{{ row.isConfirmed || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期后结转" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal">
            <span class="subtotal-amount">{{ fmtAmount(row.postPeriodSettlement) }}</span>
          </template>
          <el-input-number
            v-else-if="!isReadonly"
            :model-value="row.postPeriodSettlement"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateCell(row.rowId, 'postPeriodSettlement', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.postPeriodSettlement) }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="60" fixed="right" align="center">
        <template #default="{ row }">
          <el-button
            v-if="!row._isSubtotal && !row._isTotal"
            type="danger"
            text
            size="small"
            @click="removeRow(row.rowId)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>

  <!-- 审计说明 -->
  <div class="audit-notes-section">
    <h4>审计说明</h4>
    <el-input
      v-model="auditExplanation"
      type="textarea"
      :rows="3"
      :disabled="isReadonly"
      placeholder="对合同资产明细本期变动的分析说明..."
    />
    <div class="note-actions">
      <el-button size="small" :disabled="isReadonly || !aiAvailable || aiLoading" :loading="aiLoading" @click="genDetailChange">🤖AI</el-button>
      <GtReviewTrigger section-id="D6-2-note-explanation" label="💬 复核" />
    </div>
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabDetail.vue — 明细表 D6-2（30列69公式）
 */
import { ref, computed, inject, watch, toRef, type Ref } from 'vue'
import {
  useD6Detail,
  CONTRACT_TYPES,
  RELATED_PARTY_TYPES,
  CREDIT_RISK_GROUPS,
  CONSTRUCTION_PERIOD_OPTIONS,
  type DetailRow,
} from '../composables/useD6Detail'
import type { ChecklistResponse } from '../composables/useD6FormData'
import { useD6ImportExport } from '../composables/useD6ImportExport'
import { useD6AiGenerate } from '../composables/useD6AiGenerate'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import { calcSubtotal } from '../composables/useD6FormulaEngine'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import GtReviewTrigger from '../GtReviewTrigger.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const { importing, exportTemplate, exportData, importData } = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-2',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onImportFile(file: File) {
  await importData(file)
}

type ColumnGroup = 'basic' | 'full'
const columnGroup = ref<ColumnGroup>('basic')
const columnGroupOptions = [
  { label: '基本列', value: 'basic' as const },
  { label: '含账龄', value: 'full' as const },
]
const showAgingCols = computed(() => columnGroup.value === 'full')

const {
  addRow,
  removeRow,
  updateCell,
  importFromAuxBalance,
  searchFilter,
  filteredRows,
} = useD6Detail({
  allResponses: props.allResponses,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
})

interface DisplayRow extends DetailRow {
  _isSubtotal?: boolean
  _isTotal?: boolean
}

function sumDisplayRows(rows: DetailRow[], label: string, flags: { _isSubtotal?: boolean; _isTotal?: boolean }): DisplayRow {
  return {
    rowId: `__${label}__`,
    seqNo: 0,
    contractName: label,
    contractType: label,
    customerName: '',
    companyCode: '',
    relatedPartyType: '',
    priorUnadjusted: calcSubtotal(rows.map(r => r.priorUnadjusted)),
    priorAje: calcSubtotal(rows.map(r => r.priorAje)),
    priorRje: calcSubtotal(rows.map(r => r.priorRje)),
    priorAudited: calcSubtotal(rows.map(r => r.priorAudited)),
    agePrior1y: calcSubtotal(rows.map(r => r.agePrior1y)),
    agePrior1to2y: calcSubtotal(rows.map(r => r.agePrior1to2y)),
    agePrior2to3y: calcSubtotal(rows.map(r => r.agePrior2to3y)),
    agePrior3yAbove: calcSubtotal(rows.map(r => r.agePrior3yAbove)),
    debitAmount: calcSubtotal(rows.map(r => r.debitAmount)),
    creditAmount: calcSubtotal(rows.map(r => r.creditAmount)),
    endUnadjusted: calcSubtotal(rows.map(r => r.endUnadjusted)),
    endAje: calcSubtotal(rows.map(r => r.endAje)),
    endRje: calcSubtotal(rows.map(r => r.endRje)),
    endAudited: calcSubtotal(rows.map(r => r.endAudited)),
    ageEnd1y: calcSubtotal(rows.map(r => r.ageEnd1y)),
    ageEnd1to2y: calcSubtotal(rows.map(r => r.ageEnd1to2y)),
    ageEnd2to3y: calcSubtotal(rows.map(r => r.ageEnd2to3y)),
    ageEnd3yAbove: calcSubtotal(rows.map(r => r.ageEnd3yAbove)),
    receivableWithin1y: calcSubtotal(rows.map(r => r.receivableWithin1y)),
    receivableAbove1y: calcSubtotal(rows.map(r => r.receivableAbove1y)),
    isInConstructionPeriod: '',
    creditRiskGroup: '',
    isConfirmed: '',
    postPeriodSettlement: calcSubtotal(rows.map(r => r.postPeriodSettlement)),
    ...flags,
  }
}

const displayRows = computed<DisplayRow[]>(() => {
  const result: DisplayRow[] = []
  const typeSet = new Set<string>(CONTRACT_TYPES)

  for (const cType of CONTRACT_TYPES) {
    const typeRows = filteredRows.value.filter(r => r.contractType === cType)
    if (typeRows.length > 0) {
      result.push(...typeRows.map(r => ({ ...r })))
      result.push(sumDisplayRows(typeRows, `${cType}小计`, { _isSubtotal: true }))
    }
  }

  const uncategorized = filteredRows.value.filter(r => !typeSet.has(r.contractType) || r.contractType === '')
  if (uncategorized.length > 0) {
    result.push(...uncategorized.map(r => ({ ...r })))
  }

  if (filteredRows.value.length > 0) {
    result.push(sumDisplayRows(filteredRows.value, '合计', { _isTotal: true }))
  }

  return result
})

const browseRows = filteredRows
const browseRowCount = computed(() => filteredRows.value.length)

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('contractName', '合同名称', 150),
  virtualTextCol('customerName', '客户名称', 140),
  virtualTextCol('contractType', '类型', 120),
  virtualNumCol('endAudited', '期末审定', 110, fmtAmount),
])

const {
  browseMode,
  useVirtualScroll,
  rowEventHandlers,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  tableWidth: 1400,
})

const auditExplanation = ref('')

watch(
  () => props.allResponses.value.get('D6-2-note-explanation')?.remark,
  (val) => { auditExplanation.value = val || '' },
  { immediate: true },
)

watch(auditExplanation, (val) => {
  props.debouncedSave('D6-2-note-explanation', { remark: val })
})

const { generateAndConfirm, aiAvailable, loading: aiLoading } = useD6AiGenerate(toRef(props, 'wpId'))

async function genDetailChange() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('detail-change', auditExplanation.value, {
    task: '合同资产明细变动分析',
    rowCount: filteredRows.value.length,
    endAuditedTotal: calcSubtotal(filteredRows.value.map(r => r.endAudited)),
  }, 'AI · 变动分析')
  if (text) auditExplanation.value = text
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.d6-tab-detail { padding: 16px; }

.detail-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.toolbar-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }

.virtual-toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.virtual-hint { flex: 1; margin: 0; }

.auto-calc { background: #f5f7fa; padding: 2px 6px; border-radius: 2px; color: #909399; }
.subtotal-label { font-weight: 700; }
.subtotal-amount { font-weight: 700; }

.audit-notes-section { margin-top: 20px; }
.audit-notes-section h4 { font-size: 14px; font-weight: 600; margin-bottom: 10px; }
.note-actions { display: flex; gap: 8px; margin-top: 8px; }
</style>
