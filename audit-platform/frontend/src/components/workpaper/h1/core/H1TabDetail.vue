<template>
  <div class="h1-tab-detail">
    <!-- 引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 基础信息：资产名称/编号/分类/年限/折旧方法</div>
        <div class="guide-step"><span class="step-num">②</span> 原值变动：期初+增加-减少=期末（自动计算）</div>
        <div class="guide-step"><span class="step-num">③</span> 折旧：期初+计提-转回=期末；月折旧/净值自动</div>
        <div class="guide-step"><span class="step-num">④</span> 减值准备：期初+计提-转回=期末</div>
      </div>
    </div>

    <!-- 区段Tab切换 -->
    <el-segmented v-model="activeSegment" :options="segmentOptions" class="segment-bar" />

    <!-- 操作栏 -->
    <div class="toolbar" v-if="!isReadonly">
      <el-button size="small" type="primary" @click="handleAddRow">+ 新增资产</el-button>
      <el-button size="small" @click="handleRemoveSelected" :disabled="!selectedRowId">删除选中</el-button>
      <span class="row-count">共 {{ rows.length }} 项</span>
    </div>

    <!-- 区段1: 基础信息 -->
    <div v-show="activeSegment === 'basic'" class="segment-panel">
      <el-table :data="rows" border stripe size="small" highlight-current-row
        @current-change="onRowSelect" max-height="520" class="detail-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="category" label="分类" width="100" fixed />
        <el-table-column prop="name" label="资产名称" min-width="140" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onFieldChange(row, 'name')" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetNo" label="资产编号" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetNo" size="small" @change="onFieldChange(row, 'assetNo')" />
            <span v-else>{{ row.assetNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="acquisitionDate" label="入账日期" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.acquisitionDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%"
              @change="onFieldChange(row, 'acquisitionDate')" />
            <span v-else>{{ row.acquisitionDate }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="usefulLife" label="年限(年)" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.usefulLife" :min="1" :max="99" :controls="false" size="small"
              @change="onFieldChange(row, 'usefulLife')" />
            <span v-else>{{ row.usefulLife }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="salvageRate" label="残值率%" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.salvageRate" :min="0" :max="99" :controls="false" size="small"
              @change="onFieldChange(row, 'salvageRate')" />
            <span v-else>{{ row.salvageRate }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="depMethod" label="折旧方法" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.depMethod" size="small" @change="onFieldChange(row, 'depMethod')">
              <el-option label="直线法" value="straight" />
              <el-option label="双倍余额" value="double" />
              <el-option label="年数总和" value="sum_of_years" />
              <el-option label="工作量法" value="units" />
            </el-select>
            <span v-else>{{ row.depMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="location" label="存放地点" width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.location" size="small" @change="onFieldChange(row, 'location')" />
            <span v-else>{{ row.location }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="department" label="使用部门" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.department" size="small" @change="onFieldChange(row, 'department')" />
            <span v-else>{{ row.department }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="quantity" label="数量" width="60" align="right" />
        <el-table-column prop="unit" label="单位" width="50" />
        <el-table-column prop="spec" label="规格型号" width="120" />
        <el-table-column prop="supplier" label="供应商" width="120" />
      </el-table>
    </div>

    <!-- 区段2: 原值变动 -->
    <div v-show="activeSegment === 'cost'" class="segment-panel">
      <el-table :data="rows" border stripe size="small" highlight-current-row
        @current-change="onRowSelect" max-height="520" class="detail-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="category" label="分类" width="100" fixed />
        <el-table-column prop="name" label="资产名称" min-width="120" fixed />
        <el-table-column prop="originalCostBegin" label="原值期初" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.originalCostBegin" :controls="false" size="small"
              @change="onFieldChange(row, 'originalCostBegin')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCostBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="originalCostIncrease" label="本期增加" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.originalCostIncrease" :controls="false" size="small"
              @change="onFieldChange(row, 'originalCostIncrease')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCostIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="originalCostDecrease" label="本期减少" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.originalCostDecrease" :controls="false" size="small"
              @change="onFieldChange(row, 'originalCostDecrease')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCostDecrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原值期末" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末=期初+增加-减少">{{ fmtAmt(row.originalCostEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increaseReason" label="增加原因" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.increaseReason" size="small" @change="onFieldChange(row, 'increaseReason')" />
            <span v-else>{{ row.increaseReason }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decreaseReason" label="减少原因" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.decreaseReason" size="small" @change="onFieldChange(row, 'decreaseReason')" />
            <span v-else>{{ row.decreaseReason }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 区段3: 折旧 -->
    <div v-show="activeSegment === 'dep'" class="segment-panel">
      <el-table :data="rows" border stripe size="small" highlight-current-row
        @current-change="onRowSelect" max-height="520" class="detail-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="category" label="分类" width="100" fixed />
        <el-table-column prop="name" label="资产名称" min-width="120" fixed />
        <el-table-column prop="accDepBegin" label="折旧期初" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.accDepBegin" :controls="false" size="small"
              @change="onFieldChange(row, 'accDepBegin')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accDepBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accDepProvision" label="本期计提" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.accDepProvision" :controls="false" size="small"
              @change="onFieldChange(row, 'accDepProvision')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accDepProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accDepReversal" label="转回(处置)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.accDepReversal" :controls="false" size="small"
              @change="onFieldChange(row, 'accDepReversal')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accDepReversal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="折旧期末" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="备抵期末=期初+贷方计提-借方转回">{{ fmtAmt(row.accDepEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="annualDep" label="年折旧额" width="110" align="right">
          <template #default="{ row }"><span class="formula-cell" title="按折旧方法计算">{{ fmtAmt(row.annualDep) }}</span></template>
        </el-table-column>
        <el-table-column prop="monthlyDep" label="月折旧额" width="110" align="right">
          <template #default="{ row }"><span class="formula-cell" title="年折旧÷12">{{ fmtAmt(row.monthlyDep) }}</span></template>
        </el-table-column>
        <el-table-column label="净值" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="净值=原值-折旧-减值">{{ fmtAmt(row.netValue) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 区段4: 减值 -->
    <div v-show="activeSegment === 'impairment'" class="segment-panel">
      <el-table :data="rows" border stripe size="small" highlight-current-row
        @current-change="onRowSelect" max-height="520" class="detail-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="category" label="分类" width="100" fixed />
        <el-table-column prop="name" label="资产名称" min-width="120" fixed />
        <el-table-column prop="impairmentBegin" label="减值期初" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.impairmentBegin" :controls="false" size="small"
              @change="onFieldChange(row, 'impairmentBegin')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.impairmentBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="impairmentProvision" label="本期计提" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.impairmentProvision" :controls="false" size="small"
              @change="onFieldChange(row, 'impairmentProvision')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.impairmentProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="impairmentReversal" label="本期转回" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.impairmentReversal" :controls="false" size="small"
              @change="onFieldChange(row, 'impairmentReversal')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.impairmentReversal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值期末" width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="减值期末=期初+计提-转回">{{ fmtAmt(row.impairmentEnd) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 合计行 + 交叉验证 -->
    <div class="summary-section">
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="原值合计">{{ fmtAmt(subtotals.originalCostEnd) }}</el-descriptions-item>
        <el-descriptions-item label="折旧合计">{{ fmtAmt(subtotals.accDepEnd) }}</el-descriptions-item>
        <el-descriptions-item label="减值合计">{{ fmtAmt(subtotals.impairmentEnd) }}</el-descriptions-item>
        <el-descriptions-item label="净值合计">{{ fmtAmt(subtotals.netValue) }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>4个区段展示同一批资产的不同维度，切换区段行保持同步</li>
        <li>原值期末 = 期初 + 增加 - 减少（自动）</li>
        <li>折旧期末 = 期初 + 计提 - 转回（备抵类，贷方增加）</li>
        <li>净值 = 原值期末 - 折旧期末 - 减值期末</li>
        <li>合计行与H1-1审定表交叉验证，差异自动标红</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH1Detail, type DetailRow } from '../../composables/useH1Detail'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const allResponsesRef = computed(() => props.allResponses)

const activeSegment = ref('basic')
const segmentOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '原值变动', value: 'cost' },
  { label: '折旧', value: 'dep' },
  { label: '减值', value: 'impairment' },
]

const selectedRowId = ref<string | null>(null)

const { rows, subtotalRow: subtotals, addRow, removeRow, updateCell: updateField } = useH1Detail(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
)

function onRowSelect(row: DetailRow | null) {
  selectedRowId.value = row?.rowId ?? null
}

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('请输入资产名称', '新增固定资产', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPlaceholder: '如：XX办公楼、XX生产设备',
  })
  if (name) {
    addRow(name)
  }
}

function handleRemoveSelected() {
  if (selectedRowId.value) {
    removeRow(selectedRowId.value)
    selectedRowId.value = null
  }
}

function onFieldChange(row: DetailRow, field: string) {
  updateField(row.rowId, field, (row as any)[field])
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }
.segment-bar { margin-bottom: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.row-count { font-size: 12px; color: var(--el-text-color-secondary); margin-left: auto; }
.segment-panel { margin-bottom: 12px; }
.detail-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.summary-section { margin: 12px 0; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
