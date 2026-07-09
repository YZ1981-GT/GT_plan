<template>
  <div class="h8-tab-depreciation-alloc">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>折旧分配分析表H8-9：将使用权资产本期折旧按费用类型分配（管理费用/销售费用/制造费用等）。分配比例合计应=100%，分配金额合计应=折旧总额。</p>
    </div>

    <!-- 折旧分配表 -->
    <el-card shadow="never" class="alloc-card">
      <template #header>
        <div class="section-title">
          <span>折旧分配分析（H8-9，24行10列11公式）</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAddAlloc">+ 新增行</el-button>
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'dep-alloc')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'dep-alloc')">复核</el-button>
          </div>
        </div>
      </template>

      <!-- 折旧总额信息 -->
      <div class="dep-total-info">
        <span class="info-label">本期折旧总额（来自H8-8）：</span>
        <span class="info-value">{{ fmtAmt(depTotal) }} 元</span>
      </div>

      <el-table :data="allocRows" border size="small" class="formula-table" show-summary :summary-method="getAllocSummary">
        <el-table-column prop="expenseType" label="费用类型" min-width="160">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.expenseType" size="small" filterable allow-create
              @change="updateAllocCell(row.rowId, 'expenseType', row.expenseType)">
              <el-option label="管理费用" value="管理费用" />
              <el-option label="销售费用" value="销售费用" />
              <el-option label="制造费用" value="制造费用" />
              <el-option label="研发费用" value="研发费用" />
              <el-option label="在建工程" value="在建工程" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.expenseType }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="allocRatio" label="分配比例(%)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.allocRatio" :controls="false" size="small"
              :min="0" :max="100" :precision="2"
              @change="(v: number | undefined) => updateAllocCell(row.rowId, 'allocRatio', v)" />
            <span v-else>{{ row.allocRatio }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="分配金额" width="130" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="公式：折旧总额 × 分配比例%">{{ fmtAmt(row.allocAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="deleteAllocRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 校验区域 -->
      <div class="check-area">
        <div class="check-item" :class="allocRatioTotal === 100 ? 'check-ok' : 'check-warn'">
          <span>比例合计：{{ allocRatioTotal.toFixed(2) }}%</span>
          <el-tag :type="allocRatioTotal === 100 ? 'success' : 'warning'" size="small">
            {{ allocRatioTotal === 100 ? '✓ 100%' : '≠ 100%' }}
          </el-tag>
        </div>
        <div class="check-item" :class="Math.abs(allocTotal - depTotal) < 0.01 ? 'check-ok' : 'check-warn'">
          <span>金额合计：{{ fmtAmt(allocTotal) }} 元</span>
          <el-tag :type="Math.abs(allocTotal - depTotal) < 0.01 ? 'success' : 'warning'" size="small">
            {{ Math.abs(allocTotal - depTotal) < 0.01 ? '✓ 匹配折旧总额' : `差额 ${fmtAmt(allocTotal - depTotal)}` }}
          </el-tag>
        </div>
      </div>
    </el-card>

    <!-- OO渲染区域 -->
    <el-card shadow="never" class="oo-card">
      <template #header>
        <div class="section-title">
          <span>OO明细渲染（24行10列11公式）</span>
          <el-tag type="info" size="small">OnlyOffice 渲染</el-tag>
        </div>
      </template>
      <div class="oo-placeholder">
        <GtOnlyOfficeSheet
          v-if="wpId && showOO"
          :wp-id="wpId"
          :sheet-name="'折旧分配分析表H8-9'"
          :project-id="projectId"
          :readonly="isReadonly"
        />
        <div v-else class="oo-fallback">
          <el-empty description="OnlyOffice未加载">
            <template #image><span style="font-size:40px">📊</span></template>
          </el-empty>
        </div>
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>折旧分配比例应依据资产实际用途确定</li>
        <li>办公用房→管理费用；仓库→销售费用或制造费用</li>
        <li>分配比例合计必须=100%</li>
        <li>分配金额合计应=H8-8本期折旧总额</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabDepreciationAlloc.vue — H8-9 折旧分配分析表
 * 24行10列11公式
 * Spec: Task 4.6 | Requirements: 6.4-6.6
 */
import { ref, toRef, defineAsyncComponent } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH8Depreciation } from '../../composables/useH8Depreciation'

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
  allocRows, depTotal, allocTotal, allocRatioTotal,
  addAllocRow, deleteAllocRow, updateAllocCell,
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

async function handleAddAlloc() {
  const { value } = await ElMessageBox.prompt('请输入费用类型', '新增分配行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：管理费用',
  })
  if (value) addAllocRow(value)
}

function getAllocSummary({ columns }: { columns: any[] }) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return '合计'
    if (idx === 1) return `${allocRatioTotal.value.toFixed(2)}%`
    if (idx === 2) return fmtAmt(allocTotal.value)
    return ''
  })
}
</script>

<style scoped>
.h8-tab-depreciation-alloc { padding: 16px; font-size: 13px; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 6px; }

.alloc-card { margin-bottom: 16px; }
.dep-total-info { margin-bottom: 12px; padding: 8px 12px; background: #f0f9ff; border-radius: 6px; }
.info-label { font-size: 12px; color: var(--el-text-color-secondary); }
.info-value { font-size: 15px; font-weight: 700; color: var(--el-color-primary); }

.formula-table { font-size: 13px; }
.formula-table :deep(.formula-col) { background: #f0f9ff; }
.formula-value { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; }

.check-area { display: flex; gap: 24px; margin-top: 12px; padding: 8px 0; }
.check-item { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.check-ok { color: #67c23a; }
.check-warn { color: #e6a23c; }

.oo-card { margin-bottom: 16px; }
.oo-placeholder { min-height: 300px; }
.oo-fallback { padding: 40px 0; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
