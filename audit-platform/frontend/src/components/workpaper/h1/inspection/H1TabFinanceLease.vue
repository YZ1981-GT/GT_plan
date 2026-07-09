<template>
  <div class="h1-tab-finance-lease">
    <div class="methodology-context">
      <p>检查以融资租赁方式租出的固定资产：核实CAS21五项判断条件中任一满足即为融资租赁，验证利息分摊正确性。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-20 融资租出检查（{{ state.rows.value.length }} 项）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" @click="handleAddRow" :disabled="isReadonly">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-20')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.rows.value" border stripe size="small" max-height="420">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="assetName" label="资产名称" min-width="110" fixed />
        <el-table-column prop="lessee" label="承租方" width="100" />
        <el-table-column prop="leaseStart" label="起租日" width="100" />
        <el-table-column prop="leaseTerm" label="租期(月)" width="80" align="right" />
        <el-table-column prop="usefulLife" label="资产寿命(月)" width="95" align="right" />
        <el-table-column label="租期/寿命" width="80" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="≥75%为融资租赁条件之一">{{ row.termLifeRatio?.toFixed(0) }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="leasePvTotal" label="租金现值" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.leasePvTotal) }}</span></template>
        </el-table-column>
        <el-table-column prop="fairValue" label="公允价值" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.fairValue) }}</span></template>
        </el-table-column>
        <el-table-column label="PV/FV" width="80" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="≥90%为融资租赁条件之一">{{ row.pvFvRatio?.toFixed(0) }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="implicitRate" label="内含利率%" width="85" align="right" />
        <el-table-column prop="classificationResult" label="分类判断" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.classificationResult === '融资' ? 'success' : 'warning'" size="small">{{ row.classificationResult }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100" />
      </el-table>

      <!-- 五项分类判断标准 -->
      <div class="classification-criteria">
        <h4>CAS21融资租赁五项判断条件（满足任一即为融资）</h4>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="①所有权转移">租赁期届满时，资产所有权转移给承租人</el-descriptions-item>
          <el-descriptions-item label="②购买选择权">承租人有购买租赁资产的选择权(价格远低于公允)</el-descriptions-item>
          <el-descriptions-item label="③租期≥寿命75%">租赁期占资产使用寿命的大部分</el-descriptions-item>
          <el-descriptions-item label="④PV≥FV 90%">最低租赁付款额现值≥资产公允价值的几乎全部</el-descriptions-item>
          <el-descriptions-item label="⑤专用性资产">租赁资产性质特殊，不做重大改造只有承租人能使用</el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计结论</span></template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>五项满足任一 → 融资租赁；均不满足 → 经营租赁</li>
        <li>融资租出不在本科目核算(转应收融资租赁款)，关注分类正确性</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useH1LeaseCheck } from '../../composables/useH1LeaseCheck'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')
const state = useH1LeaseCheck(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any, { variant: 'financeLease' })

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('资产名称', '新增', { confirmButtonText: '确定', cancelButtonText: '取消' })
  if (name) state.addRow(name)
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-finance-lease { padding: 16px; font-size: 13px; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.classification-criteria { margin-top: 16px; }
.classification-criteria h4 { font-size: 13px; margin-bottom: 8px; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
