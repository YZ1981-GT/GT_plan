<template>
  <div class="h5-tab-detail">
    <!-- 区段Tab切换 -->
    <el-segmented v-model="state.activeSegment.value" :options="segmentOptions" class="segment-bar" />

    <!-- Section标题 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-2 油气资产明细表</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI说明
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('H5-2')">
              💬 复核
            </el-button>
          </div>
        </div>
      </template>

      <!-- 区段1: 基础信息 -->
      <el-table v-if="state.activeSegment.value === 'basic'" :data="displayRows" border stripe size="small" class="detail-table">
        <el-table-column prop="category" label="资产分类" min-width="100">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.category" size="small"
              @change="onUpdate(row.rowId, 'category', $event)" />
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="资产名称" min-width="140">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.name" size="small"
              @change="onUpdate(row.rowId, 'name', $event)" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="oilField" label="油田/气田" min-width="110">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.oilField" size="small"
              @change="onUpdate(row.rowId, 'oilField', $event)" />
            <span v-else>{{ row.oilField }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="block" label="区块" min-width="100">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.block" size="small"
              @change="onUpdate(row.rowId, 'block', $event)" />
            <span v-else>{{ row.block }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 区段2: 原值变动 -->
      <el-table v-if="state.activeSegment.value === 'cost'" :data="displayRows" border stripe size="small" class="detail-table">
        <el-table-column prop="name" label="资产" min-width="100" fixed />
        <el-table-column prop="originalCostBegin" label="期初原值" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.originalCostBegin" :controls="false" size="small"
              @change="onUpdate(row.rowId, 'originalCostBegin', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCostBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="originalCostIncrease" label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.originalCostIncrease" :controls="false" size="small"
              @change="onUpdate(row.rowId, 'originalCostIncrease', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCostIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="originalCostDecrease" label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.originalCostDecrease" :controls="false" size="small"
              @change="onUpdate(row.rowId, 'originalCostDecrease', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCostDecrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末原值" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末=期初+增加-减少">{{ fmtAmt(row.originalCostEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increaseReason" label="增加原因" min-width="120">
          <template #default="{ row }">
            <el-input v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.increaseReason" size="small"
              @change="onUpdate(row.rowId, 'increaseReason', $event)" />
            <span v-else>{{ row.increaseReason }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 区段3: 折耗 -->
      <el-table v-if="state.activeSegment.value === 'depletion'" :data="displayRows" border stripe size="small" class="detail-table">
        <el-table-column prop="name" label="资产" min-width="100" fixed />
        <el-table-column prop="accDepletionBegin" label="期初折耗" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.accDepletionBegin" :controls="false" size="small"
              @change="onUpdate(row.rowId, 'accDepletionBegin', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accDepletionBegin) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accDepletionProvision" label="本期计提" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.accDepletionProvision" :controls="false" size="small"
              @change="onUpdate(row.rowId, 'accDepletionProvision', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accDepletionProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accDepletionReversal" label="本期转回" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.rowId !== 'subtotal' && !isReadonly" v-model="row.accDepletionReversal" :controls="false" size="small"
              @change="onUpdate(row.rowId, 'accDepletionReversal', $event)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accDepletionReversal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末折耗" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="备抵期末=期初+计提-转回">{{ fmtAmt(row.accDepletionEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="净值" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="净值=原值期末-折耗期末">{{ fmtAmt(row.netValue) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 交叉验证提示 -->
    <el-alert v-if="state.crossValidation.value.hasCostWarning || state.crossValidation.value.hasDepWarning"
      type="warning" :closable="false" show-icon class="cross-alert">
      <template #title>
        交叉验证（H5-1审定表）：
        <span v-if="state.crossValidation.value.hasCostWarning">原值差异 {{ fmtAmt(state.crossValidation.value.costDiff) }}</span>
        <span v-if="state.crossValidation.value.hasDepWarning"> 折耗差异 {{ fmtAmt(state.crossValidation.value.deplDiff) }}</span>
      </template>
    </el-alert>

    <!-- 操作按钮 -->
    <div class="action-bar" v-if="!isReadonly">
      <el-button size="small" @click="handleAddRow">+ 新增资产行</el-button>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请填写审计说明..." :disabled="isReadonly" @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>明细表分3区段Tab(基础信息/原值变动/折耗)，行保持同步</li>
        <li>原值期末=期初+增加-减少（资产类方向）</li>
        <li>折耗期末=期初+计提-转回（备抵类方向）</li>
        <li>净值=原值期末-折耗期末</li>
        <li>合计行与H5-1审定表自动交叉验证</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useH5Detail, SEGMENT_CONFIGS } from '../../composables/useH5Detail'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)

const state = useH5Detail({
  allResponses: allResponsesRef as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onSave: (itemId, value) => { /* persist via parent */ },
})

const segmentOptions = SEGMENT_CONFIGS.map((s) => ({ label: s.label, value: s.key }))

const displayRows = computed(() => {
  const rows = [...state.rows.value]
  rows.push(state.subtotalRow.value as any)
  return rows
})

function onUpdate(rowId: string, field: string, value: any) {
  state.updateCell(rowId, field as any, value ?? 0)
}

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入资产名称', '新增资产行', {
    confirmButtonText: '确定', cancelButtonText: '取消',
  })
  if (value) state.addRow(value)
}

function handleAiGenerate() { /* AI generate */ }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h5-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }
.segment-bar { margin-bottom: 16px; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.detail-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.cross-alert { margin-bottom: 12px; }
.action-bar { margin: 12px 0; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
