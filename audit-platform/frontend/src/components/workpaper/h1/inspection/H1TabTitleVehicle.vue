<template>
  <div class="h1-tab-title-vehicle">
    <div class="methodology-context">
      <p>核对运输设备行驶证/登记证信息，关注：所有人是否一致、是否年检有效、是否存在抵押查封。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-17 运输设备权属检查（{{ state.rows.value.length }} 项）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-17')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" max-height="480" class="title-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="vehicleName" label="车辆名称" min-width="110" fixed />
        <el-table-column prop="plateNo" label="车牌号" width="100" />
        <el-table-column prop="vin" label="车架号" width="130" />
        <el-table-column prop="certOwner" label="证载所有人" width="110" />
        <el-table-column prop="bookOwner" label="账面所有人" width="110" />
        <el-table-column label="所有人一致" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.ownerMatch ? 'success' : 'danger'" size="small">{{ row.ownerMatch ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="账面价值" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookValue) }}</span></template>
        </el-table-column>
        <el-table-column prop="annualInspection" label="年检状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.annualInspection === '有效' ? 'success' : 'warning'" size="small">{{ row.annualInspection }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="inspectionExpiry" label="年检到期" width="100" />
        <el-table-column prop="hasMortgage" label="抵押" width="60" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.hasMortgage" type="warning" size="small">有</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120" />
      </el-table>

      <div class="summary-bar">
        <span>总计: {{ state.rows.value.length }} 项</span>
        <span>所有人异常: <b :class="{ 'error-amount': state.ownerMismatchCount.value > 0 }">{{ state.ownerMismatchCount.value }}</b></span>
        <span>年检过期: <b :class="{ 'error-amount': state.expiredCount.value > 0 }">{{ state.expiredCount.value }}</b></span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul><li>所有人不一致标红；年检过期标黄</li><li>抵押车辆需确认受限资产披露</li></ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH1TitleCheck } from '../../composables/useH1TitleCheck'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const state = useH1TitleCheck(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any, { variant: 'vehicle' })

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('车辆名称', '新增', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (name) state.addRow(name)
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-title-vehicle { padding: 16px; font-size: 13px; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.title-table { font-size: 13px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); }
.summary-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
