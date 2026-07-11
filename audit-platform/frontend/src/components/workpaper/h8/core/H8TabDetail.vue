<template>
  <div class="h8-tab-detail">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实使用权资产各租赁合同初始计量、折旧计提及后续变更的准确性与完整性，确认与 H9 租赁负债初始确认的勾稽关系符合 CAS21。"
    />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS21第16条：使用权资产入账值 = H9租赁负债初始确认 + 初始直接费用 - 租赁激励。58列分4区段Tab展示。</p>
    </div>

    <!-- 索引 + 行数 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-2" />
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <!-- 4区段切换 -->
    <div class="segment-bar">
      <el-segmented v-model="activeTab" :options="tabOptions" size="default" />
      <div class="bar-actions">
        <el-button v-if="!isReadonly" size="small" type="primary" @click="handleAddRow">+ 新增合同</el-button>
        <el-button size="small" type="primary" plain @click="$emit('open-ai', 'detail')">AI 辅助</el-button>
        <el-button size="small" @click="$emit('open-review', 'detail')">复核</el-button>
      </div>
    </div>

    <!-- 区段1: 基础信息 -->
    <el-table v-if="activeTab === '基础'" :data="rows" border size="small" class="detail-table" show-summary :summary-method="getSummaryBasic">
      <el-table-column prop="contractNo" label="租赁合同号" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.contractNo" size="small" @change="onCell(row.rowId, 'contractNo', row.contractNo)" />
          <span v-else>{{ row.contractNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="H9" width="70" align="center">
        <template #default="{ row }">
          <GtIndexChip v-if="row.contractNo" value="H9-2" :context-project-id="props.projectId"
            context="H9租赁负债明细对应行" @click="emit('navigate-sheet', 'H9-2')" :prevent-navigate="true" />
        </template>
      </el-table-column>
      <el-table-column prop="assetName" label="承租资产" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="onCell(row.rowId, 'assetName', row.assetName)" />
          <span v-else>{{ row.assetName }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="lessor" label="出租方" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.lessor" size="small" @change="onCell(row.rowId, 'lessor', row.lessor)" />
          <span v-else>{{ row.lessor }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="leaseType" label="租赁类型" width="100">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.leaseType" size="small" placeholder="选择" @change="onCell(row.rowId, 'leaseType', row.leaseType)">
            <el-option label="房屋" value="房屋" />
            <el-option label="车辆" value="车辆" />
            <el-option label="设备" value="设备" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.leaseType }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="startDate" label="起始日" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.startDate" size="small" placeholder="YYYY-MM-DD" @change="onCell(row.rowId, 'startDate', row.startDate)" />
          <span v-else>{{ row.startDate }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="endDate" label="到期日" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.endDate" size="small" placeholder="YYYY-MM-DD" @change="onCell(row.rowId, 'endDate', row.endDate)" />
          <span v-else>{{ row.endDate }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="handleDelete(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 区段2: 初始计量 -->
    <el-table v-if="activeTab === '初始计量'" :data="rows" border size="small" class="detail-table" show-summary :summary-method="getSummaryInitial">
      <el-table-column prop="contractNo" label="合同号" width="130" />
      <el-table-column label="H9" width="70" align="center">
        <template #default="{ row }">
          <GtIndexChip v-if="row.contractNo" value="H9-2" :context-project-id="props.projectId"
            context="H9初始确认金额来源" @click="emit('navigate-sheet', 'H9-2')" :prevent-navigate="true" />
        </template>
      </el-table-column>
      <el-table-column prop="h9InitialAmount" label="H9租赁负债初始" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.h9InitialAmount" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'h9InitialAmount', v)" />
          <span v-else>{{ fmtAmt(row.h9InitialAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="directCost" label="初始直接费用" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.directCost" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'directCost', v)" />
          <span v-else>{{ fmtAmt(row.directCost) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="incentive" label="租赁激励" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.incentive" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'incentive', v)" />
          <span v-else>{{ fmtAmt(row.incentive) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="入账值" width="140" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：H9初始+直接费用-激励">{{ fmtAmt(row.initialAmount) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 区段3: 折旧 -->
    <el-table v-if="activeTab === '折旧'" :data="rows" border size="small" class="detail-table" show-summary :summary-method="getSummaryDep">
      <el-table-column prop="contractNo" label="合同号" width="130" />
      <el-table-column label="入账值" width="130" align="right">
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmt(row.initialAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="accDepBegin" label="累计折旧期初" width="130" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.accDepBegin" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'accDepBegin', v)" />
          <span v-else>{{ fmtAmt(row.accDepBegin) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="depCurrentPeriod" label="本期计提" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.depCurrentPeriod" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'depCurrentPeriod', v)" />
          <span v-else>{{ fmtAmt(row.depCurrentPeriod) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="累计折旧期末" width="130" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：期初+本期计提">{{ fmtAmt(row.accDepEnd) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末净值" width="130" align="right" class-name="formula-col">
        <template #default="{ row }">
          <span class="formula-value" title="公式：入账值-累计折旧期末">{{ fmtAmt(row.netValue) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 区段4: 变更 -->
    <el-table v-if="activeTab === '变更'" :data="rows" border size="small" class="detail-table">
      <el-table-column prop="contractNo" label="合同号" width="130" />
      <el-table-column prop="modificationAmount" label="租赁变更调整额" width="140" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.modificationAmount" :controls="false" size="small"
            @change="(v: number | undefined) => onCell(row.rowId, 'modificationAmount', v)" />
          <span v-else>{{ fmtAmt(row.modificationAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="terminationDate" label="终止日" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.terminationDate" size="small" placeholder="YYYY-MM-DD"
            @change="onCell(row.rowId, 'terminationDate', row.terminationDate)" />
          <span v-else>{{ row.terminationDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remark" label="备注" min-width="180">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onCell(row.rowId, 'remark', row.remark)" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部统计 -->
    <div class="stat-bar">
      <span>合同总数：{{ rows.length }}</span>
      <span>入账值合计：{{ fmtAmt(initialTotal) }}元</span>
      <span>期末净值合计：{{ fmtAmt(subtotalRow.netValue) }}元</span>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>逐笔租赁合同登记，58列分基础/初始计量/折旧/变更4区段展示</li>
        <li>入账值 = H9租赁负债初始确认 + 初始直接费用 - 租赁激励（CAS21第16条）</li>
        <li>H9初始金额可点击"H9"索引跳转至 H9-2 租赁负债明细核对</li>
        <li>累计折旧期末 = 期初 + 本期计提；期末净值 = 入账值 - 累计折旧期末</li>
        <li>明细表合计应与 H8-1 审定表、H8-8 折旧测算表交叉验证</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabDetail.vue — H8-2 明细表（58列4区段Tab + CAS21初始计量公式）
 * Spec: Task 4.3 | Requirements: 3.1-3.3
 */
import { ref, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH8Detail } from '../../composables/useH8Detail'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const tabOptions = ['基础', '初始计量', '折旧', '变更']
const activeTab = ref('基础')

const {
  rows, subtotalRow, initialTotal,
  addRow, deleteRow, updateCell,
} = useH8Detail({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onCell(rowId: string, field: string, value: any) {
  updateCell(rowId, field, value)
}

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入租赁合同号', '新增明细行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：ZL-2024-001',
  })
  if (value) addRow(value)
}

function handleDelete(rowId: string) {
  deleteRow(rowId)
}

function getSummaryBasic({ columns }: any) {
  return columns.map((_: any, idx: number) => idx === 0 ? `合计（${rows.value.length}笔）` : '')
}
function getSummaryInitial({ columns }: any) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '合计'
    if (idx === 4) return fmtAmt(initialTotal.value)
    return ''
  })
}
function getSummaryDep({ columns }: any) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '合计'
    if (idx === 4) return fmtAmt(subtotalRow.value.accDepEnd)
    if (idx === 5) return fmtAmt(subtotalRow.value.netValue)
    return ''
  })
}
</script>

<style scoped>
.h8-tab-detail { padding: 16px; font-size: 13px; }

.objective-alert { margin-bottom: 12px; }
.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }

.segment-bar {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.bar-actions { display: flex; gap: 6px; }

.detail-table { font-size: 13px; margin-bottom: 12px; }
.detail-table :deep(.formula-col) { background: #f0f9ff; }
.formula-value { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; }

.stat-bar {
  display: flex; gap: 24px; padding: 10px 0; font-size: 12px;
  color: var(--el-text-color-secondary); border-top: 1px solid var(--el-border-color-lighter);
}
</style>
