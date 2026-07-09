<template>
  <div class="j1-tab-adjustment">
    <el-card shadow="never">
      <template #header>
        <span class="section-title">应付职工薪酬调整分录汇总表</span>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { parseNum } from '@/composables/workpaper/j1/useJ1FormulaEngine'

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
.section-title { font-weight: 600; font-size: 15px; }
</style>
