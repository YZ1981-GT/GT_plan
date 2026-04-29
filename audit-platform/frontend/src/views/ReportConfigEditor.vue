<template>
  <div class="gt-report-config-editor gt-fade-in">
    <div class="gt-rce-banner">
      <div class="gt-rce-banner-text">
        <h2>报表结构编辑</h2>
        <p>{{ standardLabel }} · {{ reportTypeLabel }} · {{ rows.length }} 行</p>
      </div>
      <div class="gt-rce-banner-actions">
        <el-select v-model="selectedStandard" size="small" style="width: 160px" @change="loadConfig">
          <el-option label="国企版合并" value="soe_consolidated" />
          <el-option label="国企版单体" value="soe_standalone" />
          <el-option label="上市版合并" value="listed_consolidated" />
          <el-option label="上市版单体" value="listed_standalone" />
        </el-select>
        <el-select v-model="selectedReportType" size="small" style="width: 140px" @change="loadConfig">
          <el-option label="资产负债表" value="balance_sheet" />
          <el-option label="利润表" value="income_statement" />
          <el-option label="现金流量表" value="cash_flow_statement" />
          <el-option label="权益变动表" value="equity_change" />
        </el-select>
        <el-button size="small" type="primary" @click="onSaveAll" :loading="saving">保存修改</el-button>
        <el-button size="small" @click="onAddRow">新增行</el-button>
        <el-button size="small" @click="router.back()">返回</el-button>
      </div>
    </div>

    <el-table :data="rows" v-loading="loading" border size="small" style="width: 100%"
      row-key="row_code" :row-class-name="rowClassName">
      <el-table-column prop="row_number" label="序号" width="60" align="center" />
      <el-table-column prop="row_code" label="行次编码" width="100" />
      <el-table-column label="项目名称" min-width="250">
        <template #default="{ row }">
          <div :style="{ paddingLeft: (row.indent_level || 0) * 20 + 'px', display: 'flex', alignItems: 'center', gap: '4px' }">
            <el-tag v-if="row.is_total_row" size="small" type="warning">合计</el-tag>
            <el-input v-if="row._editing" v-model="row.row_name" size="small" style="flex: 1" />
            <span v-else @dblclick="row._editing = true" style="cursor: pointer">{{ row.row_name }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="公式" min-width="300">
        <template #default="{ row }">
          <el-input v-if="row._editing" v-model="row.formula" size="small" placeholder="如 TB('1001','期末余额')" />
          <code v-else-if="row.formula" @dblclick="row._editing = true" style="cursor: pointer; font-size: 11px; color: #666">
            {{ row.formula.length > 60 ? row.formula.slice(0, 60) + '...' : row.formula }}
          </code>
          <span v-else style="color: #ccc">—</span>
        </template>
      </el-table-column>
      <el-table-column label="缩进" width="70" align="center">
        <template #default="{ row }">
          <el-input-number v-if="row._editing" v-model="row.indent_level" :min="0" :max="3" size="small" :controls="false" style="width: 50px" />
          <span v-else>{{ row.indent_level }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" align="center">
        <template #default="{ row, $index }">
          <el-button v-if="!row._editing" size="small" link type="primary" @click="row._editing = true">编辑</el-button>
          <el-button v-if="row._editing" size="small" link type="success" @click="row._editing = false">完成</el-button>
          <el-button size="small" link type="danger" @click="onDeleteRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// const route = useRoute()
const router = useRouter()

const selectedStandard = ref('soe_consolidated')
const selectedReportType = ref('balance_sheet')
const rows = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)

const standardLabel = computed(() => {
  const m: Record<string, string> = {
    soe_consolidated: '国企版合并',
    soe_standalone: '国企版单体',
    listed_consolidated: '上市版合并',
    listed_standalone: '上市版单体',
  }
  return m[selectedStandard.value] || ''
})

const reportTypeLabel = computed(() => {
  const m: Record<string, string> = {
    balance_sheet: '资产负债表',
    income_statement: '利润表',
    cash_flow_statement: '现金流量表',
    equity_change: '权益变动表',
  }
  return m[selectedReportType.value] || ''
})

function rowClassName({ row }: { row: any }) {
  if (row.is_total_row) return 'gt-total-row'
  if (row.indent_level === 0 && !row.formula) return 'gt-section-row'
  return ''
}

async function loadConfig() {
  loading.value = true
  try {
    const { data } = await http.get('/api/report-config', {
      params: {
        report_type: selectedReportType.value,
        applicable_standard: selectedStandard.value,
      },
    })
    const items = Array.isArray(data) ? data : (data?.data || [])
    rows.value = items.map((r: any) => ({ ...r, _editing: false }))
  } catch {
    rows.value = []
    ElMessage.warning('加载报表配置失败')
  } finally {
    loading.value = false
  }
}

function onAddRow() {
  const lastRow = rows.value[rows.value.length - 1]
  const nextNumber = lastRow ? (lastRow.row_number || 0) + 1 : 1
  const nextCode = `NEW-${String(nextNumber).padStart(3, '0')}`
  rows.value.push({
    id: null,
    row_code: nextCode,
    row_number: nextNumber,
    row_name: '新行',
    indent_level: 1,
    formula: null,
    is_total_row: false,
    parent_row_code: null,
    _editing: true,
    _isNew: true,
  })
}

async function onDeleteRow(index: number) {
  const row = rows.value[index]
  await ElMessageBox.confirm(`确认删除行「${row.row_name}」？`, '删除确认')
  if (row.id && !row._isNew) {
    try {
      await http.delete(`/api/report-config/${row.id}`)
    } catch {
      ElMessage.error('删除失败')
      return
    }
  }
  rows.value.splice(index, 1)
  ElMessage.success('已删除')
}

async function onSaveAll() {
  saving.value = true
  try {
    let savedCount = 0
    for (const row of rows.value) {
      if (row._isNew) {
        // TODO: 后端需要 POST /report-config 新增行的端点
        // 暂时跳过新增行的保存
        continue
      }
      if (row.id) {
        await http.put(`/api/report-config/${row.id}`, {
          row_name: row.row_name,
          formula: row.formula,
          indent_level: row.indent_level,
          is_total_row: row.is_total_row,
        })
        savedCount++
      }
    }
    ElMessage.success(`已保存 ${savedCount} 行修改`)
    rows.value.forEach(r => { r._editing = false })
  } catch (e: any) {
    ElMessage.error('保存失败: ' + (e?.message || ''))
  } finally {
    saving.value = false
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.gt-report-config-editor { padding: var(--gt-space-5); }
.gt-rce-banner {
  display: flex; justify-content: space-between; align-items: center;
  background: var(--gt-gradient-primary);
  border-radius: var(--gt-radius-lg);
  padding: 16px 24px;
  margin-bottom: 16px;
  color: #fff;
  position: relative;
  overflow: hidden;
}
.gt-rce-banner-text h2 { margin: 0 0 2px; font-size: 18px; }
.gt-rce-banner-text p { margin: 0; font-size: 12px; opacity: 0.75; }
.gt-rce-banner-actions { display: flex; gap: 8px; align-items: center; }
.gt-rce-banner-actions .el-button { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); color: #fff; }
.gt-rce-banner-actions .el-button:hover { background: rgba(255,255,255,0.25); }

:deep(.gt-total-row) { font-weight: 700; background-color: #fafafa !important; }
:deep(.gt-section-row) { background-color: #f5f0ff !important; font-weight: 600; }
</style>
