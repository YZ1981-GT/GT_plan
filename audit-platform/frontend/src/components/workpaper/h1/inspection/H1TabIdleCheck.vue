<template>
  <div class="h1-tab-idle-check">
    <div class="methodology-context">
      <p>检查闲置固定资产，判断是否存在减值迹象（CAS8第5条"资产已经或者将被闲置、终止使用或者计划提前处置"），为H1-14减值测算提供输入。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-4 闲置固定资产检查表</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-4')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" class="idle-table">
        <el-table-column type="index" width="40" />
        <el-table-column prop="name" label="资产名称" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetNo" label="资产编号" width="100" />
        <el-table-column prop="category" label="分类" width="90" />
        <el-table-column prop="originalCost" label="原值" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.originalCost) }}</span></template>
        </el-table-column>
        <el-table-column prop="netValue" label="净值" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.netValue) }}</span></template>
        </el-table-column>
        <el-table-column prop="idleDate" label="闲置起始日" width="110" />
        <el-table-column prop="idleReason" label="闲置原因" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.idleReason" size="small" />
            <span v-else>{{ row.idleReason }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="plan" label="处置计划" width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.plan" size="small">
              <el-option label="继续闲置" value="idle" />
              <el-option label="计划处置" value="dispose" />
              <el-option label="转为使用" value="reuse" />
            </el-select>
            <span v-else>{{ row.plan }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值迹象" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.hasImpairmentSign ? 'danger' : 'success'" size="small">
              {{ row.hasImpairmentSign ? '有' : '无' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 汇总统计 -->
      <div class="summary-bar">
        <span>闲置资产: {{ state.idleCount.value }} 项</span>
        <span>闲置净值合计: <b class="amount-cell">{{ fmtAmt(state.idleNetValueTotal.value) }}</b></span>
        <span>有减值迹象: <b :class="{ 'error-amount': state.impairmentSignCount.value > 0 }">{{ state.impairmentSignCount.value }}</b> 项</span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="闲置检查审计结论..." />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>闲置≥1年且无明确复用计划的资产→减值迹象=有→联动H1-14</li>
        <li>净值自动从明细表取数</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH1IdleCheck } from '../../composables/useH1IdleCheck'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')

const state = useH1IdleCheck(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any)

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('请输入闲置资产名称', '新增闲置资产', {
    confirmButtonText: '确定', cancelButtonText: '取消',
  })
  if (name) state.addRow(name)
}

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-idle-check { padding: 16px; font-size: 13px; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.idle-table { font-size: 13px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); }
.summary-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
