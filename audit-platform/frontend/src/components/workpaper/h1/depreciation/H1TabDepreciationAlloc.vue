<template>
  <div class="h1-tab-dep-alloc">
    <div class="methodology-context">
      <p>折旧费用分配：将H1-12测算的折旧总额按使用部门分配到制造费用(D5)、管理费用(K8)、销售费用(K9)等科目。分配比例基于部门使用比例。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-13 折旧费用分配表</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-13')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" class="alloc-table">
        <el-table-column type="index" width="40" />
        <el-table-column prop="department" label="使用部门/科目" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.department" size="small" />
            <span v-else>{{ row.department }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accountCode" label="科目编码" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.accountCode" size="small" />
            <span v-else>{{ row.accountCode }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="allocRatio" label="分配比例%" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.allocRatio" :controls="false" :min="0" :max="100" size="small" />
            <span v-else>{{ row.allocRatio }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="分配金额" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="分配=折旧总额×比例%">{{ fmtAmt(row.allocAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookAmount" label="账面金额" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookAmount" :controls="false" size="small" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异" width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.difference) > 0.01 }]" title="差异=分配-账面">
              {{ fmtAmt(row.difference) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="跳转" width="80" align="center">
          <template #default="{ row }">
            <GtIndexChip v-if="row.refWpCode" :value="row.refWpCode" @click="navigateTo(row.refWpCode)" />
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100" />
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 核对行 -->
      <div class="verify-row">
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="折旧总额(H1-12)">
            <span class="amount-cell">{{ fmtAmt(state.depTotal.value) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="分配合计">
            <span class="formula-cell">{{ fmtAmt(state.allocSum.value) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="核对差异">
            <span :class="['amount-cell', { 'error-amount': Math.abs(state.verifyDiff.value) > 0.01 }]">
              {{ fmtAmt(state.verifyDiff.value) }}
            </span>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="publishAllocated" :disabled="isReadonly">📤 发布折旧分配</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" />
    </el-card>

    <div class="jump-targets">
      <span style="font-size:12px;color:var(--el-text-color-secondary)">跳转目标:</span>
      <GtIndexChip value="D5" @click="navigateTo('D5')" />
      <GtIndexChip value="K8" @click="navigateTo('K8')" />
      <GtIndexChip value="K9" @click="navigateTo('K9')" />
    </div>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>分配比例合计应=100%，分配金额合计应=折旧总额</li>
        <li>跳转列GtIndexChip→D5营业成本/K8管理费用/K9销售费用</li>
        <li>核对行验证分配是否与H1-12测算一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H1TabDepreciationAlloc.vue — H1-13 折旧费用分配表
 * Task 6.7: 折旧分配跨底稿联动
 * - publish 'h1:depreciation-allocated' event
 * - GtIndexChip 跳转 D5/K8/K9
 */
import { ref, computed, inject, toRef } from 'vue'
import { useH1DepreciationAlloc } from '../../composables/useH1DepreciationAlloc'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const state = useH1DepreciationAlloc(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any, {
  onPublishEvent(event: string, payload: any) {
    // 6.7 — publish 'h1:depreciation-allocated'
    console.log('[H1-13] publish', event, payload)
  },
})

function handleAddRow() { state.addRow() }
function publishAllocated() { state.publishAllocated() }
function navigateTo(wpCode: string) { emit('navigate-sheet', wpCode) }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-dep-alloc { padding: 16px; font-size: 13px; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.alloc-table { font-size: 13px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.index-chip { padding: 2px 6px; background: var(--el-color-primary-light-9); border-radius: 4px; cursor: pointer; font-size: 11px; color: var(--el-color-primary); }
.verify-row { margin-top: 16px; }
.note-card { margin-top: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.jump-targets { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
