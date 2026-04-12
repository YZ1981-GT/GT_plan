<template>
  <div class="goodwill-view">
    <div class="section-header">
      <h3>商誉减值测试</h3>
      <el-button type="primary" size="small" @click="showDialog()">新增记录</el-button>
    </div>

    <el-table :data="store.goodwillRows" v-loading="store.loading" border stripe size="small">
      <el-table-column prop="cash_generating_unit" label="现金产出单元" width="180" />
      <el-table-column prop="acquisition_name" label="收购项目" width="160" />
      <el-table-column prop="initial_amount" label="初始金额" width="140" align="right">
        <template #default="{ row }">{{ formatNum(row.initial_amount) }}</template>
      </el-table-column>
      <el-table-column prop="cumulative_impairment" label="累计减值" width="140" align="right">
        <template #default="{ row }">{{ formatNum(row.cumulative_impairment) }}</template>
      </el-table-column>
      <el-table-column prop="net_amount" label="账面净值" width="140" align="right">
        <template #default="{ row }">{{ formatNum(row.net_amount) }}</template>
      </el-table-column>
      <el-table-column prop="recoverable_amount" label="可收回金额" width="140" align="right">
        <template #default="{ row }">{{ formatNum(row.recoverable_amount) }}</template>
      </el-table-column>
      <el-table-column prop="impairment_test_date" label="测试日期" width="120" />
      <el-table-column prop="notes" label="备注" min-width="200" show-overflow-tooltip />
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text @click="showDialog(row)">编辑</el-button>
          <el-button type="danger" size="small" text @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑商誉' : '新增商誉'" width="640px">
      <el-form :model="form" label-width="120px">
        <el-form-item label="现金产出单元"><el-input v-model="form.cash_generating_unit" /></el-form-item>
        <el-form-item label="收购项目"><el-input v-model="form.acquisition_name" /></el-form-item>
        <el-form-item label="初始金额"><el-input-number v-model="form.initial_amount" :precision="2" style="width:100%" /></el-form-item>
        <el-form-item label="累计减值"><el-input-number v-model="form.cumulative_impairment" :precision="2" style="width:100%" /></el-form-item>
        <el-form-item label="可收回金额"><el-input-number v-model="form.recoverable_amount" :precision="2" style="width:100%" /></el-form-item>
        <el-form-item label="测试日期"><el-date-picker v-model="form.impairment_test_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.notes" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useConsolidationStore } from '@/stores/consolidation'
import { createGoodwillRow, updateGoodwillRow, deleteGoodwillRow } from '@/services/consolidationApi'
import type { GoodwillRow } from '@/services/consolidationApi'

const props = defineProps<{ projectId: string; year: number }>()
const store = useConsolidationStore()
const dialogVisible = ref(false)
const editing = ref<GoodwillRow | null>(null)
const form = ref({ cash_generating_unit: '', acquisition_name: '', initial_amount: '0', cumulative_impairment: '0', net_amount: '0', recoverable_amount: '0', impairment_test_date: '', notes: '', year: props.year })

function formatNum(v: string | null) {
  if (!v) return '—'
  const n = Number(v)
  return isNaN(n) ? v : n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function showDialog(row?: GoodwillRow) {
  editing.value = row || null
  if (row) {
    form.value = { cash_generating_unit: row.cash_generating_unit, acquisition_name: row.acquisition_name, initial_amount: row.initial_amount, cumulative_impairment: row.cumulative_impairment, net_amount: row.net_amount, recoverable_amount: row.recoverable_amount, impairment_test_date: row.impairment_test_date, notes: row.notes, year: row.year }
  } else {
    form.value = { cash_generating_unit: '', acquisition_name: '', initial_amount: '0', cumulative_impairment: '0', net_amount: '0', recoverable_amount: '0', impairment_test_date: '', notes: '', year: props.year }
  }
  dialogVisible.value = true
}

async function onSave() {
  try {
    const payload = { ...form.value, project_id: props.projectId }
    if (editing.value) {
      await updateGoodwillRow(editing.value.id, props.projectId, payload)
    } else {
      await createGoodwillRow(props.projectId, payload)
    }
    dialogVisible.value = false
    await store.fetchGoodwillRows(props.projectId, props.year)
    ElMessage.success('保存成功')
  } catch { ElMessage.error('保存失败') }
}

async function onDelete(row: GoodwillRow) {
  await ElMessageBox.confirm('确认删除？', '提示')
  await deleteGoodwillRow(row.id, props.projectId)
  store.goodwillRows = store.goodwillRows.filter(r => r.id !== row.id)
  ElMessage.success('删除成功')
}

onMounted(() => store.fetchGoodwillRows(props.projectId, props.year))
</script>

<style scoped>
.goodwill-view { display: flex; flex-direction: column; gap: var(--gt-space-3); }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header h3 { margin: 0; font-size: 16px; color: var(--gt-color-primary-dark); }
</style>
