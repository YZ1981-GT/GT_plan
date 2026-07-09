<template>
  <div class="h1-tab-adjustment">
    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-3 调整分录（AJE / RJE）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增分录</el-button>
            <el-button size="small" type="default" link @click="handlePushA13" :disabled="isReadonly">推送A13</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" class="adj-table">
        <el-table-column type="index" label="序" width="40" align="center" />
        <el-table-column prop="adjustType" label="类型" width="70" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.adjustType" size="small" style="width:60px" @change="onFieldUpdate(row)">
              <el-option label="AJE" value="AJE" />
              <el-option label="RJE" value="RJE" />
            </el-select>
            <span v-else>{{ row.adjustType }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accountCode" label="科目编码" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.accountCode" size="small" @change="onFieldUpdate(row)" />
            <span v-else>{{ row.accountCode }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accountName" label="科目名称" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.accountName" size="small" @change="onFieldUpdate(row)" />
            <span v-else>{{ row.accountName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="debit" label="借方" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debit" :controls="false" :min="0" size="small" @change="onFieldUpdate(row)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="credit" label="贷方" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.credit" :controls="false" :min="0" size="small" @change="onFieldUpdate(row)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="摘要" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.description" size="small" @change="onFieldUpdate(row)" />
            <span v-else>{{ row.description }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="reference" label="索引" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.reference" size="small" @change="onFieldUpdate(row)" />
            <span v-else>{{ row.reference }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemove(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 借贷平衡 -->
      <div class="balance-bar" :class="{ 'balance-ok': state.isBalanced.value, 'balance-err': !state.isBalanced.value }">
        <span>借方合计: {{ fmtAmt(state.debitTotal.value) }}</span>
        <span>贷方合计: {{ fmtAmt(state.creditTotal.value) }}</span>
        <el-tag :type="state.isBalanced.value ? 'success' : 'danger'" size="small">
          {{ state.isBalanced.value ? '借贷平衡' : '借贷不平' }}
        </el-tag>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="调整事项说明..." />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>AJE=审计调整分录，影响报表数；RJE=重分类调整，不影响总额</li>
        <li>每笔分录借贷合计必须平衡，整表借贷合计也须平衡</li>
        <li>"推送A13"将分录同步到调整分录汇总表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef } from 'vue'
import { useH1Adjustment } from '../../composables/useH1Adjustment'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const allResponsesRef = computed(() => props.allResponses)
const auditNote = ref('')

const state = useH1Adjustment(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
)

function handleAddRow() { state.addRow() }
function handleRemove(rowId: string) { state.removeRow(rowId) }
function onFieldUpdate(row: any) { state.updateCell(row.rowId, row) }
function handlePushA13() { state.pushToA13?.() }

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-adjustment { padding: 16px; font-size: 13px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.adj-table { font-size: 13px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.balance-bar { display: flex; align-items: center; gap: 16px; padding: 10px 12px; margin-top: 12px; border-radius: 4px; font-size: 13px; }
.balance-ok { background: var(--el-color-success-light-9); }
.balance-err { background: var(--el-color-danger-light-9); }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
