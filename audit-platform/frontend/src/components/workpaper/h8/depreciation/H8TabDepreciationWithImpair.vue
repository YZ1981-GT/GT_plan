<template>
  <div class="h8-tab-depreciation-with-impair">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS21第21条+CAS8：含减值版本折旧测算。减值后折旧基数=使用权资产账面价值-减值准备。折旧期=min(租赁期, 使用寿命)。</p>
    </div>

    <!-- 公式说明Banner -->
    <div class="formula-banner">
      <div class="formula-icon">📐</div>
      <div class="formula-content">
        <div class="formula-title">折旧计算公式（含减值）</div>
        <div class="formula-text">折旧基数 = 入账值 - 已提减值 ｜ 月折旧额 = 折旧基数 / 剩余折旧期 ｜ 本期折旧 = 月折旧 × 当期月数</div>
      </div>
    </div>

    <!-- 索引 + 行数 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-8" />
      <el-tag size="small" type="info">共 {{ depRows.length }} 行</el-tag>
    </div>

    <!-- 折旧参数摘要 -->
    <el-card shadow="never" class="params-card">
      <template #header>
        <div class="section-title">
          <span>折旧测算参数（含减值 49行27列86公式）</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAddRow">+ 新增行</el-button>
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'dep-with-impair')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'dep-with-impair')">复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="depRows" border size="small" class="formula-table" show-summary :summary-method="getDepSummary">
        <el-table-column prop="contractNo" label="合同号" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.contractNo" size="small"
              @change="updateDepCell(row.rowId, 'contractNo', row.contractNo)" />
            <span v-else>{{ row.contractNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetName" label="资产名称" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small"
              @change="updateDepCell(row.rowId, 'assetName', row.assetName)" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rouAmount" label="入账值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.rouAmount" :controls="false" size="small"
              @change="(v: number | undefined) => updateDepCell(row.rowId, 'rouAmount', v)" />
            <span v-else>{{ fmtAmt(row.rouAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="impairmentAmount" label="减值准备" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.impairmentAmount" :controls="false" size="small"
              @change="(v: number | undefined) => updateDepCell(row.rowId, 'impairmentAmount', v)" />
            <span v-else>{{ fmtAmt(row.impairmentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="折旧基数" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：入账值 - 减值准备">{{ fmtAmt(row.rouAmount - row.impairmentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="leaseTermMonths" label="租赁期(月)" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.leaseTermMonths" :controls="false" size="small" :min="0"
              @change="(v: number | undefined) => updateDepCell(row.rowId, 'leaseTermMonths', v)" />
            <span v-else>{{ row.leaseTermMonths }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="usefulLifeMonths" label="使用寿命(月)" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.usefulLifeMonths" :controls="false" size="small" :min="0"
              @change="(v: number | undefined) => updateDepCell(row.rowId, 'usefulLifeMonths', v)" />
            <span v-else>{{ row.usefulLifeMonths }}</span>
          </template>
        </el-table-column>
        <el-table-column label="折旧期(月)" width="95" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：min(租赁期, 使用寿命)">{{ row.depPeriodMonths }}</span>
          </template>
        </el-table-column>
        <el-table-column label="月折旧额" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：(入账值-减值) / 折旧期">
              {{ fmtAmt(row.depPeriodMonths > 0 ? (row.rouAmount - row.impairmentAmount) / row.depPeriodMonths : 0) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="monthsInPeriod" label="当期月数" width="85" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.monthsInPeriod" :controls="false" size="small" :min="0" :max="12"
              @change="(v: number | undefined) => updateDepCell(row.rowId, 'monthsInPeriod', v)" />
            <span v-else>{{ row.monthsInPeriod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期折旧" width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：月折旧 × 当期月数">{{ fmtAmt(row.currentPeriodDep) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accumulatedDep" label="累计折旧" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.accumulatedDep" :controls="false" size="small"
              @change="(v: number | undefined) => updateDepCell(row.rowId, 'accumulatedDep', v)" />
            <span v-else>{{ fmtAmt(row.accumulatedDep) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="deleteDepRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- OO渲染区域 -->
    <el-card shadow="never" class="oo-card">
      <template #header>
        <div class="section-title">
          <span>OO明细渲染（49行27列86公式）</span>
          <el-tag type="info" size="small">OnlyOffice 渲染</el-tag>
        </div>
      </template>
      <div class="oo-placeholder">
        <GtOnlyOfficeSheet
          v-if="wpId && showOO"
          :wp-id="wpId"
          :sheet-name="'折旧测算表（含减值）H8-8'"
          :project-id="projectId"
          :readonly="isReadonly"
        />
        <div v-else class="oo-fallback">
          <el-empty description="OnlyOffice未加载，显示参数区计算结果">
            <template #image><span style="font-size:40px">📊</span></template>
          </el-empty>
        </div>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>减值后需重新计算折旧基数=账面价值-已提减值</li>
        <li>减值后月折旧额=(入账值-减值准备)/剩余折旧期</li>
        <li>减值准备不得转回（CAS8规定）</li>
        <li>折旧合计应与H8-1累计折旧本期计提交叉验证</li>
        <li>如无减值迹象，建议切换"不含减值"版本简化处理</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabDepreciationWithImpair.vue — H8-8(B) 折旧测算表（含减值）
 * 49行27列86公式，OO渲染+参数摘要
 * Spec: Task 4.6 | Requirements: 6.1-6.6
 */
import { ref, toRef, defineAsyncComponent } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH8Depreciation } from '../../composables/useH8Depreciation'
import GtIndexChip from '../../GtIndexChip.vue'

const GtOnlyOfficeSheet = defineAsyncComponent(() =>
  import('../../GtOnlyOfficeSheet.vue').catch(() => ({ template: '<div>OO不可用</div>' })),
)

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
}>()

const showOO = ref(true)

const {
  depRows, depTotal, accDepTotal,
  addDepRow, deleteDepRow, updateDepCell,
} = useH8Depreciation({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入合同号', '新增折旧行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：LEASE-2024-001',
  })
  if (value) addDepRow(value)
}

function getDepSummary({ columns }: { columns: any[] }) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '合计'
    if (idx === 10) return fmtAmt(depTotal.value)
    if (idx === 11) return fmtAmt(accDepTotal.value)
    return ''
  })
}
</script>

<style scoped>
.h8-tab-depreciation-with-impair { padding: 16px; font-size: 13px; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.formula-banner {
  display: flex; gap: 12px; align-items: flex-start;
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  border: 1px solid #fbbf24; border-radius: 8px; padding: 14px 16px; margin-bottom: 16px;
}
.formula-icon { font-size: 28px; }
.formula-content { flex: 1; }
.formula-title { font-weight: 700; font-size: 14px; color: #92400e; margin-bottom: 4px; }
.formula-text { font-size: 13px; color: #a16207; }

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }

.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 6px; }

.params-card { margin-bottom: 16px; }
.formula-table { font-size: 13px; }
.formula-table :deep(.formula-col) { background: #fffbeb; }
.formula-value { border-bottom: 1px dashed #f59e0b; cursor: help; color: #d97706; }

.oo-card { margin-bottom: 16px; }
.oo-placeholder { min-height: 400px; }
.oo-fallback { padding: 40px 0; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
