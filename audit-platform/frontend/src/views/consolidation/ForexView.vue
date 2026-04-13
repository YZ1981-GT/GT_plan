<template>
  <div class="gt-forex-view">
    <div class="section-header">
      <h3>外币报表折算</h3>
      <el-button type="primary" size="small" @click="showDialog()">新增记录</el-button>
    </div>

    <el-table :data="store.forexRows" v-loading="store.loading" border stripe size="small">
      <el-table-column prop="entity_name" label="主体" width="160" />
      <el-table-column prop="currency" label="外币" width="100" />
      <el-table-column prop="functional_currency" label="功能货币" width="120" />
      <el-table-column prop="exchange_rate_used" label="折算汇率" width="120" align="right" />
      <el-table-column prop="monetary_assets" label="货币性资产" width="140" align="right">
        <template #default="{ row }">{{ formatNum(row.monetary_assets) }}</template>
      </el-table-column>
      <el-table-column prop="monetary_liabilities" label="货币性负债" width="140" align="right">
        <template #default="{ row }">{{ formatNum(row.monetary_liabilities) }}</template>
      </el-table-column>
      <el-table-column prop="translation_differences" label="折算差额" width="140" align="right">
        <template #default="{ row }">{{ formatNum(row.translation_differences) }}</template>
      </el-table-column>
      <el-table-column prop="notes" label="备注" min-width="200" show-overflow-tooltip />
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text @click="showDialog(row)">编辑</el-button>
          <el-button type="danger" size="small" text @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑折算' : '新增折算'" width="600px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="主体"><el-input v-model="form.entity_name" /></el-form-item>
        <el-form-item label="外币"><el-input v-model="form.currency" /></el-form-item>
        <el-form-item label="功能货币"><el-input v-model="form.functional_currency" /></el-form-item>
        <el-form-item label="折算汇率"><el-input-number v-model="form.exchange_rate_used" :precision="6" style="width:100%" /></el-form-item>
        <el-form-item label="货币性资产"><el-input-number v-model="form.monetary_assets" :precision="2" style="width:100%" /></el-form-item>
        <el-form-item label="货币性负债"><el-input-number v-model="form.monetary_liabilities" :precision="2" style="width:100%" /></el-form-item>
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
import { createForexRow, updateForexRow, deleteForexRow } from '@/services/consolidationApi'
import type { ForexRow } from '@/services/consolidationApi'

const props = defineProps<{ projectId: string; year: number }>()
const store = useConsolidationStore()
const dialogVisible = ref(false)
const editing = ref<ForexRow | null>(null)
const form = ref({ entity_name: '', currency: '', functional_currency: 'CNY', exchange_rate_used: '1', monetary_assets: '0', monetary_liabilities: '0', translation_differences: '0', notes: '', year: props.year })

function formatNum(v: string | null) {
  if (!v) return '—'
  const n = Number(v)
  return isNaN(n) ? v : n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function showDialog(row?: ForexRow) {
  editing.value = row || null
  if (row) {
    form.value = { entity_name: row.entity_name, currency: row.currency, functional_currency: row.functional_currency, exchange_rate_used: row.exchange_rate_used, monetary_assets: row.monetary_assets, monetary_liabilities: row.monetary_liabilities, translation_differences: row.translation_differences, notes: row.notes, year: row.year }
  } else {
    form.value = { entity_name: '', currency: '', functional_currency: 'CNY', exchange_rate_used: '1', monetary_assets: '0', monetary_liabilities: '0', translation_differences: '0', notes: '', year: props.year }
  }
  dialogVisible.value = true
}

async function onSave() {
  try {
    const payload = { ...form.value, project_id: props.projectId }
    if (editing.value) {
      await updateForexRow(editing.value.id, props.projectId, payload)
    } else {
      await createForexRow(props.projectId, payload)
    }
    dialogVisible.value = false
    await store.fetchForexRows(props.projectId, props.year)
    ElMessage.success('保存成功')
  } catch { ElMessage.error('保存失败') }
}

async function onDelete(row: ForexRow) {
  await ElMessageBox.confirm('确认删除？', '提示')
  await deleteForexRow(row.id, props.projectId)
  store.forexRows = store.forexRows.filter(r => r.id !== row.id)
  ElMessage.success('删除成功')
}

onMounted(() => store.fetchForexRows(props.projectId, props.year))
</script>

<style scoped>
.gt-forex-view { display: flex; flex-direction: column; gap: var(--gt-space-3); }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-header h3 { margin: 0; font-size: 16px; color: var(--gt-color-primary-dark); }
</style>
