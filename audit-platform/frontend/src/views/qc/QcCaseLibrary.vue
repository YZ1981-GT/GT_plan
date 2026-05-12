<template>
  <div class="qc-case-library">
    <GtPageHeader title="质控案例库" :show-back="false">
      <template #actions>
        <el-button size="small" @click="loadCases" :loading="loading">刷新</el-button>
      </template>
    </GtPageHeader>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-select
        v-model="filters.category"
        placeholder="分类"
        clearable
        size="default"
        style="width: 160px;"
        @change="onFilterChange"
      >
        <el-option label="全部分类" value="" />
        <el-option label="底稿质量" value="workpaper_quality" />
        <el-option label="审计程序" value="audit_procedure" />
        <el-option label="报告编制" value="report_preparation" />
        <el-option label="独立性" value="independence" />
        <el-option label="职业判断" value="professional_judgment" />
      </el-select>

      <el-select
        v-model="filters.severity"
        placeholder="严重级别"
        clearable
        size="default"
        style="width: 140px;"
        @change="onFilterChange"
      >
        <el-option label="全部级别" value="" />
        <el-option label="阻断" value="blocking" />
        <el-option label="警告" value="warning" />
        <el-option label="提示" value="info" />
      </el-select>

      <el-input
        v-model="filters.search"
        placeholder="搜索案例标题..."
        clearable
        style="width: 240px;"
        @clear="onFilterChange"
        @keyup.enter="onFilterChange"
      >
        <template #prefix>
          <span>🔎</span>
        </template>
      </el-input>
    </div>

    <!-- 案例表格 -->
    <el-table
      :data="cases"
      v-loading="loading"
      stripe
      style="width: 100%;"
      @row-click="onRowClick"
      row-class-name="clickable-row"
    >
      <el-table-column label="标题" prop="title" min-width="280" />

      <el-table-column label="分类" prop="category" width="140" align="center">
        <template #default="{ row }">
          {{ categoryLabel(row.category) }}
        </template>
      </el-table-column>

      <el-table-column label="严重级别" prop="severity" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="severityTagType(row.severity)" size="small" effect="dark">
            {{ severityLabel(row.severity) }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="发布时间" prop="published_at" width="160">
        <template #default="{ row }">
          {{ formatDate(row.published_at) }}
        </template>
      </el-table-column>

      <el-table-column label="浏览量" prop="view_count" width="100" align="center">
        <template #default="{ row }">
          {{ row.view_count ?? 0 }}
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pagination-wrapper">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next, total"
        @current-change="onPageChange"
      />
    </div>

    <!-- 案例详情对话框 -->
    <el-dialog v-model="detailVisible" :title="detailData.title" width="700px" top="5vh">
      <div v-loading="loadingDetail" class="case-detail">
        <div class="detail-meta">
          <el-tag :type="severityTagType(detailData.severity)" size="small" effect="dark">
            {{ severityLabel(detailData.severity) }}
          </el-tag>
          <span class="detail-category">{{ categoryLabel(detailData.category) }}</span>
          <span class="detail-date">{{ formatDate(detailData.published_at) }}</span>
        </div>

        <el-divider />

        <h4>案例描述</h4>
        <p class="detail-text">{{ detailData.description || '暂无描述' }}</p>

        <h4>经验教训</h4>
        <p class="detail-text">{{ detailData.lessons_learned || '暂无' }}</p>

        <h4>相关准则</h4>
        <div v-if="detailData.related_standards && detailData.related_standards.length">
          <el-tag
            v-for="(std, idx) in detailData.related_standards"
            :key="idx"
            size="small"
            style="margin-right: 6px; margin-bottom: 4px;"
          >
            {{ std }}
          </el-tag>
        </div>
        <p v-else class="no-data">暂无相关准则</p>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getCases, getCaseDetail } from '@/services/qcCaseApi'
import { handleApiError } from '@/utils/errorHandler'

// ─── Types ──────────────────────────────────────────────────────────────────

interface CaseItem {
  id: string
  title: string
  category: string
  severity: string
  published_at: string
  view_count: number
}

interface CaseDetail extends CaseItem {
  description: string
  lessons_learned: string
  related_standards: string[]
}

// ─── State ──────────────────────────────────────────────────────────────────

const cases = ref<CaseItem[]>([])
const loading = ref(false)
const total = ref(0)
const currentPage = ref(1)
const pageSize = 20

const filters = ref({
  category: '',
  severity: '',
  search: '',
})

// Detail dialog
const detailVisible = ref(false)
const loadingDetail = ref(false)
const detailData = ref<CaseDetail>({
  id: '',
  title: '',
  category: '',
  severity: '',
  published_at: '',
  view_count: 0,
  description: '',
  lessons_learned: '',
  related_standards: [],
})

// ─── Helpers ────────────────────────────────────────────────────────────────

function categoryLabel(cat: string): string {
  const map: Record<string, string> = {
    workpaper_quality: '底稿质量',
    audit_procedure: '审计程序',
    report_preparation: '报告编制',
    independence: '独立性',
    professional_judgment: '职业判断',
  }
  return map[cat] || cat
}

function severityTagType(severity: string): 'danger' | 'warning' | 'info' {
  switch (severity) {
    case 'blocking': return 'danger'
    case 'warning': return 'warning'
    default: return 'info'
  }
}

function severityLabel(severity: string): string {
  switch (severity) {
    case 'blocking': return '阻断'
    case 'warning': return '警告'
    case 'info': return '提示'
    default: return severity
  }
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '—'
  return dateStr.replace('T', ' ').slice(0, 10)
}

// ─── Data Loading ───────────────────────────────────────────────────────────

async function loadCases() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    params.set('page', String(currentPage.value))
    params.set('page_size', String(pageSize))
    if (filters.value.category) params.set('category', filters.value.category)
    if (filters.value.severity) params.set('severity', filters.value.severity)
    if (filters.value.search) params.set('search', filters.value.search)

    const data = await getCases({
      category: filters.value.category || undefined,
      severity: filters.value.severity || undefined,
      search: filters.value.search || undefined,
    })
    cases.value = (data.items || []) as any
    total.value = data.total || 0
  } catch {
    cases.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  currentPage.value = 1
  loadCases()
}

function onPageChange(page: number) {
  currentPage.value = page
  loadCases()
}

async function onRowClick(row: CaseItem) {
  detailVisible.value = true
  loadingDetail.value = true
  try {
    const data = await getCaseDetail(row.id)
    detailData.value = data as any
  } catch (e: any) {
    handleApiError(e, '加载案例详情')
    detailData.value = { ...row, description: '', lessons_learned: '', related_standards: [] }
  } finally {
    loadingDetail.value = false
  }
}

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  loadCases()
})
</script>

<style scoped>
.qc-case-library {
  padding: 0;
}

.filter-bar {
  display: flex;
  gap: 12px;
  padding: 16px;
  align-items: center;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  padding: 16px;
}

.clickable-row {
  cursor: pointer;
}

.case-detail .detail-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-category {
  color: #606266;
  font-size: 14px;
}

.detail-date {
  color: #909399;
  font-size: 13px;
}

.detail-text {
  color: #303133;
  line-height: 1.7;
  white-space: pre-wrap;
}

.no-data {
  color: #c0c4cc;
}
</style>
