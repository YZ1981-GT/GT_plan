<template>
  <div class="h5-tab-depletion-alloc">
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>H5-13 折耗分配分析表（11公式）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate"><el-icon><MagicStick /></el-icon> AI说明</el-button>
            <el-button size="small" type="default" link @click="handleReview('H5-13')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="balance-bar">
        <span>折耗总额: <b>{{ fmtAmt(state.totalCurrentDepletion.value) }}</b></span>
        <span>已分配: <b>{{ fmtAmt(state.totalAllocAmount.value) }}</b></span>
        <el-tag :type="state.allocIsBalanced.value ? 'success' : 'danger'" size="small">
          {{ state.allocIsBalanced.value ? '分配平衡 ✓' : '未平衡' }}
        </el-tag>
      </div>

      <el-table :data="state.allocRows.value" border stripe size="small" class="alloc-table">
        <el-table-column prop="costCenter" label="成本中心" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.costCenter" size="small" @change="state.updateAllocCell(row.rowId, 'costCenter', $event)" />
            <span v-else>{{ row.costCenter }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="allocRatio" label="分配比例(%)" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.allocRatio" :controls="false" :precision="2" :min="0" :max="100" size="small"
              @change="state.updateAllocCell(row.rowId, 'allocRatio', $event ?? 0)" />
            <span v-else>{{ row.allocRatio.toFixed(2) }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="分配金额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="=折耗总额×分配比例">{{ fmtAmt(row.allocAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="state.updateAllocCell(row.rowId, 'remark', $event)" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="action-bar" v-if="!isReadonly">
      <el-button type="primary" size="small" :disabled="!state.allocIsBalanced.value" @click="state.publishDepletionAlloc()">
        发布折耗分配 → D5营业成本
      </el-button>
    </div>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>折耗分配将各油田折耗计入对应的营业成本科目</li>
        <li>分配比例合计应=100%，分配金额合计=折耗总额</li>
        <li>发布后联动D5营业成本底稿(EventBus depletion:allocated)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH5Depletion } from '../../composables/useH5Depletion'
import { useH5FormData } from '../../composables/useH5FormData'
import { eventBus } from '@/utils/eventBus'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)

const formData = useH5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const state = useH5Depletion({
  allResponses: allResponsesRef as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onSave: (itemId: string, value: any) => formData.setResponse(itemId, value),
  onPublishEvent: (event: string, payload: any) => {
    // Emit depletion:allocated → D5 via real EventBus
    eventBus.emit(event as any, { ...payload, timestamp: Date.now() })
  },
})

function handleAiGenerate() {}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string { return val == null ? '-' : val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.h5-tab-depletion-alloc { padding: 16px; font-size: 13px; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.balance-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; font-size: 13px; }
.alloc-table { font-size: 13px; }
.formula-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.action-bar { margin: 12px 0; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
