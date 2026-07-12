<template>
  <div class="k5-tab-detail">
    <!-- ═══ Section标题 + 操作按钮 ═══ -->
    <div class="section-header">
      <h3>K5-2 预计负债明细表</h3>
      <div class="header-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增行
        </el-button>
        <el-dropdown size="small" :disabled="isReadonly">
          <el-button size="small">导入导出 <el-icon><ArrowDown /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="$emit('save', 'K5-2-export-template', {})">导出模板</el-dropdown-item>
              <el-dropdown-item @click="$emit('save', 'K5-2-export-data', {})">导出数据</el-dropdown-item>
              <el-dropdown-item @click="$emit('save', 'K5-2-import-data', {})">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="$emit('navigate-sheet', '审定表K5-1')">复核</el-button>
      </div>
    </div>

    <!-- ═══ 三区段Tab切换 ═══ -->
    <el-segmented v-model="activeSection" :options="sectionOptions" class="section-segmented" />

    <!-- ═══ 三级可能性色标图例 ═══ -->
    <div v-if="activeSection === 1" class="color-legend">
      <span class="legend-item"><span class="dot dot-red" /> 很可能（>50%）→ 确认</span>
      <span class="legend-item"><span class="dot dot-orange" /> 可能（≤50%）→ 披露</span>
      <span class="legend-item"><span class="dot dot-gray" /> 极小可能 → 不处理</span>
    </div>

    <!-- ═══ 区段0: 基础信息 ═══ -->
    <el-table
      v-if="activeSection === 0"
      :data="detailRows"
      border
      size="small"
      style="width: 100%"
      max-height="560"
      show-summary
      :summary-method="getSummary"
    >
      <el-table-column type="index" label="序" width="48" align="center" />
      <el-table-column label="项目名称" min-width="150">
        <template #default="{ row }">
          <el-input v-model="row.projectName" :disabled="isReadonly" size="small" @blur="handleUpdate(row.rowId, 'projectName', row.projectName)" />
        </template>
      </el-table-column>
      <el-table-column label="类型" width="130">
        <template #default="{ row }">
          <el-select v-model="row.provisionType" :disabled="isReadonly" size="small" placeholder="类型" @change="(v:string) => handleUpdate(row.rowId, 'provisionType', v)">
            <el-option v-for="t in provisionTypeOptions" :key="t" :label="t" :value="t" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="现时义务描述" min-width="180">
        <template #default="{ row }">
          <el-input v-model="row.obligationDesc" :disabled="isReadonly" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" @blur="handleUpdate(row.rowId, 'obligationDesc', row.obligationDesc)" />
        </template>
      </el-table-column>
      <el-table-column label="期初" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.beginBalance" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => handleUpdate(row.rowId, 'beginBalance', v)" />
        </template>
      </el-table-column>
      <el-table-column label="计提" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.provision" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => handleUpdate(row.rowId, 'provision', v)" />
        </template>
      </el-table-column>
      <el-table-column label="转销" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.release" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => handleUpdate(row.rowId, 'release', v)" />
        </template>
      </el-table-column>
      <el-table-column label="期末" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期初 + 计提 − 转销" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.endBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="" width="48" align="center">
        <template #default="{ $index }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="handleRemoveRow($index)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 区段1: 判断信息 ═══ -->
    <el-table
      v-if="activeSection === 1"
      :data="detailRows"
      border
      size="small"
      style="width: 100%"
      max-height="560"
    >
      <el-table-column type="index" label="序" width="48" align="center" />
      <el-table-column prop="projectName" label="项目" width="130" />
      <el-table-column label="可能性级别" width="140">
        <template #default="{ row }">
          <el-select v-model="row.likelihood" :disabled="isReadonly" size="small" placeholder="选择" @change="(v:string) => handleUpdate(row.rowId, 'likelihood', v)">
            <el-option label="很可能(>50%)" value="very_likely" />
            <el-option label="可能(≤50%)" value="possible" />
            <el-option label="极小可能" value="remote" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="确认决策" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.recognition" :type="recognitionTagType(row.recognition)" size="small">
            {{ recognitionLabel(row.recognition) }}
          </el-tag>
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="色标" width="60" align="center">
        <template #default="{ row }">
          <span v-if="row.likelihood" class="likelihood-dot" :style="{ background: likelihoodColorMap[row.likelihood] }" />
        </template>
      </el-table-column>
      <el-table-column label="确认依据" min-width="200">
        <template #default="{ row }">
          <el-input v-model="row.recognitionBasis" :disabled="isReadonly" size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" @blur="handleUpdate(row.rowId, 'recognitionBasis', row.recognitionBasis)" />
        </template>
      </el-table-column>
      <el-table-column label="计量方法" width="140">
        <template #default="{ row }">
          <el-select v-model="row.measurementMethod" :disabled="isReadonly" size="small" placeholder="方法" @change="(v:string) => handleUpdate(row.rowId, 'measurementMethod', v)">
            <el-option v-for="m in measurementOptions" :key="m.value" :label="m.label" :value="m.value" />
          </el-select>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 区段2: 估计信息 ═══ -->
    <el-table
      v-if="activeSection === 2"
      :data="detailRows"
      border
      size="small"
      style="width: 100%"
      max-height="560"
      show-summary
      :summary-method="getEstimateSummary"
    >
      <el-table-column type="index" label="序" width="48" align="center" />
      <el-table-column prop="projectName" label="项目" width="130" />
      <el-table-column label="最佳估计数" width="120" align="right">
        <template #default="{ row }">
          <template v-if="row.measurementMethod === 'single'">
            <el-input-number v-model="row.bestEstimate" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:100px" @change="(v:number) => handleUpdate(row.rowId, 'bestEstimate', v)" />
          </template>
          <template v-else>
            <el-tooltip :content="row.measurementMethod === 'range' ? '(上限+下限)/2' : 'Σ(金额×概率)'" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.bestEstimate) }}</span>
            </el-tooltip>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="区间上限" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.measurementMethod === 'range'" v-model="row.rangeUpper" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => handleUpdate(row.rowId, 'rangeUpper', v)" />
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="区间下限" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="row.measurementMethod === 'range'" v-model="row.rangeLower" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => handleUpdate(row.rowId, 'rangeLower', v)" />
          <span v-else class="text-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="110">
        <template #default="{ row }">
          <el-input v-model="row.voucherRef" :disabled="isReadonly" size="small" placeholder="凭证" @blur="handleUpdate(row.rowId, 'voucherRef', row.voucherRef)" />
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.conclusion" :disabled="isReadonly" size="small" placeholder="结论" @blur="handleUpdate(row.rowId, 'conclusion', row.conclusion)" />
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计统计栏 ═══ -->
    <div class="summary-bar">
      <span>合计行数: {{ subtotals.count }}</span>
      <span>期末合计: <strong>{{ fmtNum(subtotals.endBalance) }}</strong></span>
      <span>最佳估计合计: <strong>{{ fmtNum(subtotals.bestEstimate) }}</strong></span>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="k5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>23列拆为3区段：基础（余额变动）→ 判断（或有事项可能性）→ 估计（最佳估计数计量）</li>
        <li>很可能(>50%)→确认预计负债并填最佳估计数；可能(≤50%)→披露或有负债进附注；极小可能→不处理</li>
        <li>计量方法：单一最可能金额 / 区间中值(上+下)/2 / 期望值加权Σ(金额×概率)</li>
        <li>明细表期末合计应与K5-1审定表审定数一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabDetail.vue — K5-2 预计负债明细表
 * 23列3区段Tab+或有判断+三级色标+42行虚拟滚动+动态行
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 4.3
 * Requirements: 3.1-3.6, 4.3-4.4, 5.5
 */
import { toRef } from 'vue'
import { Plus, Delete, ArrowDown, MagicStick } from '@element-plus/icons-vue'
import { useK5Detail, LIKELIHOOD_COLOR_MAP } from '../../composables/useK5Detail'
import type { Ref } from 'vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// 父组件模板绑定会自动解包 ref → 子组件收到纯 Map；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  detailRows,
  activeSection,
  subtotals,
  provisionTypeOptions,
  measurementOptions,
  likelihoodColorMap,
  updateCell,
  addRow,
  removeRow,
} = useK5Detail({
  allResponses: allResponsesRef,
  saveResponse: async (field: string, value: any) => {
    emit('save', `K5-${field}`, value)
  },
})

// ─── 区段Tab options ─────────────────────────────────────────────────────────

const sectionOptions = [
  { label: '基础', value: 0 },
  { label: '判断', value: 1 },
  { label: '估计', value: 2 },
]

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleUpdate(rowId: string, field: string, value: any) {
  updateCell(rowId, field, value)
}

function handleAddRow() { addRow() }
function handleRemoveRow(idx: number) { removeRow(idx) }
function handleAiGenerate() { emit('save', 'K5-2-ai-trigger', { remark: 'generate' }) }

// ─── 判断列辅助 ──────────────────────────────────────────────────────────────

function recognitionTagType(r: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  if (r === 'recognize') return 'danger'
  if (r === 'disclose') return 'warning'
  return 'info'
}

function recognitionLabel(r: string): string {
  if (r === 'recognize') return '确认'
  if (r === 'disclose') return '披露'
  if (r === 'ignore') return '不处理'
  return ''
}

// ─── Summary methods ─────────────────────────────────────────────────────────

function getSummary({ columns, data }: any) {
  const sums: string[] = []
  columns.forEach((_: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    if (idx === 5) { sums[idx] = fmtNum(subtotals.value.beginBalance); return }
    if (idx === 6) { sums[idx] = fmtNum(subtotals.value.provision); return }
    if (idx === 7) { sums[idx] = fmtNum(subtotals.value.release); return }
    if (idx === 8) { sums[idx] = fmtNum(subtotals.value.endBalance); return }
    sums[idx] = ''
  })
  return sums
}

function getEstimateSummary({ columns }: any) {
  const sums: string[] = []
  columns.forEach((_: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    if (idx === 2) { sums[idx] = fmtNum(subtotals.value.bestEstimate); return }
    sums[idx] = ''
  })
  return sums
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtNum(v: number): string {
  if (!v && v !== 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k5-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }
.section-segmented { margin-bottom: 12px; }
.color-legend { display: flex; gap: 16px; margin-bottom: 10px; font-size: 12px; color: #606266; }
.legend-item { display: flex; align-items: center; gap: 4px; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; }
.dot-red { background: #F56C6C; }
.dot-orange { background: #E6A23C; }
.dot-gray { background: #909399; }
.likelihood-dot { display: inline-block; width: 12px; height: 12px; border-radius: 50%; }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.text-muted { color: #c0c4cc; font-size: 12px; }
.summary-bar { display: flex; gap: 24px; margin-top: 10px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
