<template>
  <div class="report-page">
    <el-card class="toolbar-card" shadow="never">
      <div class="toolbar">
        <div class="left">
          <h2>试算平衡表</h2>
          <el-tag type="info" effect="plain">四列结构：未审数 / 重分类调整 / 审计调整 / 审定数</el-tag>
        </div>
        <div class="right">
          <el-select v-model="currentYear" placeholder="选择年度" style="width:120px;margin-right:12px;">
            <el-option v-for="y in yearOptions" :key="y" :label="y + '年'" :value="y" />
          </el-select>
          <el-button :icon="RefreshRight" @click="loadData">刷新</el-button>
          <el-button :icon="Document" @click="goToUnadjusted">未审报表</el-button>
          <el-button :icon="DocumentChecked" @click="goToAdjusted">审定报表</el-button>
          <el-button :icon="EditPen" @click="goToAdjustments">调整分录</el-button>
        </div>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table
        :data="tableData"
        v-loading="loading"
        size="small"
        border
        stripe
        style="width: 100%"
        :span-method="categorySpanMethod"
      >
        <el-table-column prop="standard_account_code" label="科目代码" width="120" />
        <el-table-column prop="account_name" label="科目名称" min-width="200" />
        <el-table-column prop="account_category" label="科目类别" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ categoryLabel(row.account_category) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="年初余额" align="right" min-width="140">
          <template #default="{ row }">
            <span :class="{ negative: Number(row.opening_balance) < 0 }">
              {{ formatNumber(row.opening_balance) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" align="right" min-width="140">
          <template #default="{ row }">
            <span :class="{ negative: Number(row.unadjusted_amount) < 0, highlight: row.exceeds_materiality }">
              {{ formatNumber(row.unadjusted_amount) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="重分类调整 (RJE)" align="right" min-width="140">
          <template #default="{ row }">
            <span :class="{ negative: Number(row.rje_adjustment) < 0 }">
              {{ formatNumber(row.rje_adjustment) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="审计调整 (AJE)" align="right" min-width="140">
          <template #default="{ row }">
            <span :class="{ negative: Number(row.aje_adjustment) < 0 }">
              {{ formatNumber(row.aje_adjustment) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" align="right" min-width="140">
          <template #default="{ row }">
            <span :class="{ negative: Number(row.audited_amount) < 0, highlight: row.exceeds_materiality }">
              {{ formatNumber(row.audited_amount) }}
            </span>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && tableData.length === 0" description="暂无试算表数据" />
    </el-card>

    <!-- 联动提示 -->
    <el-alert
      v-if="!loading && tableData.length > 0"
      title="试算表与四表联动说明"
      type="info"
      description="未审报表由「未审数」列驱动；审定报表由「审定数」列驱动。调整分录变动将自动更新 RJE/AJE 列并连锁重算审定数。"
      show-icon
      :closable="false"
      style="margin-top:16px"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { RefreshRight, Document, DocumentChecked, EditPen } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { trialBalance } from '@/api/index.js'

const route = useRoute()
const router = useRouter()

const currentProjectId = computed(() => route.query.project_id || localStorage.getItem('current_project_id') || '')
const currentYear = ref(parseInt(route.query.year) || new Date().getFullYear())
const yearOptions = computed(() => {
  const y = new Date().getFullYear()
  return [y, y - 1, y - 2]
})

const tableData = ref([])
const loading = ref(false)

async function loadData() {
  if (!currentProjectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  loading.value = true
  try {
    const data = await trialBalance.get(currentProjectId.value, currentYear.value)
    tableData.value = Array.isArray(data) ? data : []
  } catch (err) {
    ElMessage.error(err.message || '加载试算平衡表失败')
    tableData.value = []
  } finally {
    loading.value = false
  }
}

function formatNumber(v) {
  if (v === null || v === undefined || v === '') return '-'
  const n = Number(v)
  if (isNaN(n)) return v
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function categoryLabel(cat) {
  const map = {
    asset: '资产',
    liability: '负债',
    equity: '权益',
    revenue: '收入',
    expense: '费用',
  }
  return map[cat] || cat
}

function categorySpanMethod({ rowIndex, columnIndex }) {
  // 可扩展按类别合并展示
  return { rowspan: 1, colspan: 1 }
}

function goToUnadjusted() {
  router.push({
    path: '/reports/unadjusted',
    query: { project_id: currentProjectId.value, year: currentYear.value },
  })
}
function goToAdjusted() {
  router.push({
    path: '/reports/adjusted',
    query: { project_id: currentProjectId.value, year: currentYear.value },
  })
}
function goToAdjustments() {
  router.push({
    path: '/reports/adjustment-entries',
    query: { project_id: currentProjectId.value, year: currentYear.value },
  })
}

watch([currentProjectId, currentYear], () => {
  loadData()
}, { immediate: true })
</script>

<style scoped>
.report-page {
  padding: 16px;
  background: #f5f7fa;
  min-height: 100vh;
}
.toolbar-card {
  margin-bottom: 16px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.toolbar .left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.toolbar .left h2 {
  margin: 0;
  font-size: 20px;
}
.toolbar .right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.negative {
  color: #f56c6c;
}
.highlight {
  font-weight: bold;
  color: #e6a23c;
}
</style>
