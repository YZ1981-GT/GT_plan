<template>
  <div class="minority-interest-view">
    <div class="section-header">
      <h3>少数股东权益</h3>
      <el-button type="primary" size="small" @click="showDialog()">新增记录</el-button>
    </div>

    <el-table :data="store.miRows" v-loading="store.loading" border stripe size="small">
      <el-table-column prop="subsidiary_name" label="子公司名称" width="200" />
      <el-table-column prop="ownership_percentage" label="母公司在子公司的持股比例" width="140" align="right">
        <template #default="{ row }">{{ row.ownership_percentage }}%</template>
      </el-table-column>
      <el-table-column prop="minority_percentage" label="少数股东比例" width="120" align="right">
        <template #default="{ row }">{{ row.minority_percentage }}%</template>
      </el-table-column>
      <el-table-column prop="total_equity" label="子公司权益总额" width="140" align="right">
        <template #default="{ row }">{{ formatNum(row.total_equity) }}</template>
      </el-table-column>
      <el-table-column prop="minority_interest_amount" label="少数股东权益" width="140" align="right">
        <template #default="{ row }">{{ formatNum(row.minority_interest_amount) }}</template>
      </el-table-column>
      <el-table-column prop="changes" label="权益变动" min-width="200" show-overflow-tooltip />
      <el-table-column prop="notes" label="备注" min-width="200" show-overflow-tooltip />
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text @click="showDialog(row)">编辑</el-button>
          <el-button type="danger" size="small" text @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑少数股东权益' : '新增少数股东权益'" width="640px">
      <el-form :model="form" label-width="140px">
        <el-form-item label="子公司名称"><el-input v-model="form.subsidiary_name" /></el-form-item>
        <el-form-item label="母公司在子公司的持股比例">
          <el-input-number v-model="form.ownership_percentage" :min="0" :max="100" :precision="2" style="width:100%" />
        </el-form-item>
        <el-form-item label="少数股东比例">
          <el-input-number v-model="form.minority_percentage" :min="0" :max="100" :precision="2" style="width:100%" />
        </el-form-item>
        <el-form-item label="子公司权益总额"><el-input-number v-model="form.total_equity" :precision="2" style="width:100%" /></el-form-item>
        <el-form-item label="少数股东权益"><el-input-number v-model="form.minority_interest_amount" :precision="2" style="width:100%" /></el-form-item>
        <el-form-item label="权益变动"><el-input v-model="form.changes" type="textarea" :rows="2" /></el-form-item>
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
import { createMinorityInterestRow, updateMinorityInterestRow, deleteMinorityInterestRow } from '@/services/consolidationApi'
import type { MinorityInterestRow } from '@/services/consolidationApi'

const props = defineProps<{ projectId: string; year: number }>()
const store = useConsolidationStore()
const dialogVisible = ref(false)
const editing = ref<MinorityInterestRow | null>(null)
const form = ref({ subsidiary_name: '', ownership_percentage: '100', minority_percentage: '0', total_equity: '0', minority_interest_amount: '0', changes: '', notes: '', year: props.year })

function formatNum(v: string | null) {
  if (!v) return '—'
  const n = Number(v)
  return isNaN(n) ? v : n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function showDialog(row?: MinorityInterestRow) {
  editing.value = row || null
  if (row) {
    form.value = { subsidiary_name: row.subsidiary_name, ownership_percentage: row.ownership_percentage, minority_percentage: row.minority_percentage, total_equity: row.total_equity, minority_interest_amount: row.minority_interest_amount, changes: row.changes, notes: row.notes, year: row.year }
  } else {
    form.value = { subsidiary_name: '', ownership_percentage: '100', minority_percentage: '0', total_equity: '0', minority_interest_amount: '0', changes: '', notes: '', year: props.year }
  }
  dialogVisible.value = true
}

async function onSave() {
  try {
    const payload = { ...form.value, project_id: props.projectId }
    if (editing.value) {
      await updateMinorityInterestRow(editing.value.id, props.projectId, payload)
    } else {
      await createMinorityInterestRow(props.projectId, payload)
    }
    dialogVisible.value = false
    await store.fetchMinorityInterestRows(props.projectId, props.year)
    ElMessage.success('保存成功')
  } catch { ElMessage.error('保存失败') }
}

async function onDelete(row: MinorityInterestRow) {
  await ElMessageBox.confirm('确认删除？', '提示')
  await deleteMinorityInterestRow(row.id, props.projectId)
  store.miRows = store.miRows.filter(r => r.id !== row.id)
  ElMessage.success('删除成功')
}

onMounted(() => store.fetchMinorityInterestRows(props.projectId, props.year))
</script>

<style scoped>
.minority-interest-view { display: flex; flex-direction: column; gap: var(--gt-space-3); }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header h3 { margin: 0; font-size: 16px; color: var(--gt-color-primary-dark); }
</style>
