<template>
  <div class="j1-tab-adjustment">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：汇总应付职工薪酬相关的审计调整分录（AJE/RJE），核验调整依据、借贷科目与金额的准确性，确保调整正确传导至审定表与报表。
      </template>
    </el-alert>

    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <span class="section-title">应付职工薪酬调整分录汇总表</span>
          <span class="chip-wrap"><GtIndexChip value="wp:J1-1" :context-project-id="projectId" /></span>
          <el-tag size="small" type="info">共 {{ adjustmentRows.length }} 笔</el-tag>
        </div>
      </template>
      <el-table :data="adjustmentRows" border size="small" style="font-size: 13px">
        <el-table-column prop="description" label="调整事项说明" min-width="180" />
        <el-table-column prop="type" label="类别" width="130" />
        <el-table-column prop="reportItem" label="报表项目" width="120" />
        <el-table-column prop="accountName" label="科目名称" width="140" />
        <el-table-column prop="noteItem" label="附注项目" width="100" />
        <el-table-column prop="debitAmount" label="借方金额" width="110" align="right" />
        <el-table-column prop="creditAmount" label="贷方金额" width="110" align="right" />
        <el-table-column prop="indexRef" label="索引" width="80" />
        <el-table-column prop="remark" label="备注" width="100" />
      </el-table>
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 汇总本底稿形成的审计调整分录，区分报表调整（RJE）与账项调整（AJE）。</p>
        <p>2. 每笔调整须注明调整事项说明、报表项目、科目名称、附注项目及索引来源。</p>
        <p>3. 借贷金额应平衡，调整后金额传导至审定表（J1-1）审定数列。</p>
        <p>4. 调整分录应与 A2 调整分录汇总台账保持一致。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { parseNum } from '@/composables/workpaper/j1/useJ1FormulaEngine'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
}>()

interface AdjRow {
  description: string; type: string; reportItem: string
  accountName: string; noteItem: string; debitAmount: number
  creditAmount: number; indexRef: string; remark: string
}

const adjustmentRows = ref<AdjRow[]>([])

onMounted(() => {
  if (props.htmlData?.adjustment_rows) {
    adjustmentRows.value = (props.htmlData.adjustment_rows as Array<Record<string, unknown>>).map(r => ({
      description: String(r.description || ''),
      type: String(r.type || ''),
      reportItem: String(r.report_item || ''),
      accountName: String(r.account_name || ''),
      noteItem: String(r.note_item || ''),
      debitAmount: parseNum(r.debit_amount as number),
      creditAmount: parseNum(r.credit_amount as number),
      indexRef: String(r.index_ref || ''),
      remark: String(r.remark || ''),
    }))
  }
})
</script>

<style scoped>
.j1-tab-adjustment { padding: 16px; }
.audit-objective { margin-bottom: 12px; }
.header-row { display: flex; align-items: center; gap: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.section-title { font-weight: 600; font-size: 15px; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
