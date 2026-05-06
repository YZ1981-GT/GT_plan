<template>
  <div class="qc-case-library">
    <!-- 顶部横幅 -->
    <div class="gt-page-banner">
      <div class="gt-banner-content">
        <h2>📚 质控案例库</h2>
        <span class="gt-banner-sub">
          共 {{ total }} 个案例
        </span>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-select
        v-model="filters.category"
        placeholder="分类"
        clearable
        style="width: 160px"
        @change="handleFilterChange"
      >
        <el-option
          v-for="cat in categoryOptions"
          :key="cat.value"
          :label="cat.label"
          :value="cat.value"
        />
      </el-select>

      <el-select
        v-model="filters.severity"
        placeholder="严重程度"
        clearable
        style="width: 140px"
        @change="handleFilterChange"
      >
        <el-option
          v-for="sev in severityOptions"
          :key="sev.value"
          :label="sev.label"
          :value="sev.value"
        />
      </el-select>

      <el-input
        v-model="filters.search"
        placeholder="搜索案例标题或描述..."
        clearable
        style="width: 280px"
        :prefix-icon="SearchIcon"
        @clear="handleFilterChange"
        @keyup.enter="handleFilterChange"
      />

      <el-button type="primary" @click="handleFilterChange">搜索</el-button>
    </div>

    <!-- 案例卡片列表 -->
    <div class="case-list" v-loading="loading">
      <template v-if="cases.length">
        <div
          v-for="item in cases"
          :key="item.id"
          class="case-card"
          @click="openDetail(item)"
        >
          <div class="case-card-header">
            <span class="case-title">{{ item.title }}</span>
            <div class="case-tags">
              <el-tag size="small" :type="severityTagType(item.severity)">
                {{ severityLabel(item.severity) }}
              </el-tag>
              <el-tag size="small" type="info">{{ categoryLabel(item.category) }}</el-tag>
            </div>
          </div>
          <div class="case-card-body">
            <p class="case-desc">{{ truncate(item.description, 120) }}</p>
          </div>
          <div class="case-card-footer">
            <span class="case-meta">
              <el-icon><View /></el-icon>
              {{ item.review_count }} 次阅读
            </span>
            <span class="case-meta">
              {{ formatDate(item.published_at) }}
            </span>
            <span class="case-standards" v-if="item.related_standards?.length">
              <el-tag
                v-for="std in item.related_standards.slice(0, 2)"
                :key="std.code"
                size="small"
                effect="plain"
                type="warning"
              >
                {{ std.code }}{{ std.section ? ' §' + std.section : '' }}
              </el-tag>
              <span v-if="item.related_standards.length > 2" class="more-tag">
                +{{ item.related_standards.length - 2 }}
              </span>
            </span>
          </div>
        </div>
      </template>
      <el-empty v-else-if="!loading" description="暂无案例数据" />
    </div>

    <!-- 分页 -->
    <div class="pagination-bar" v-if="total > pageSize">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next, total"
        @current-change="handlePageChange"
      />
    </div>

    <!-- 案例详情对话框 -->
    <el-dialog
      v-model="detailVisible"
      :title="detailCase?.title || '案例详情'"
      width="720px"
      destroy-on-close
    >
      <div class="case-detail" v-if="detailCase" v-loading="detailLoading">
        <!-- 基本信息 -->
        <div class="detail-meta">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="分类">
              {{ categoryLabel(detailCase.category) }}
            </el-descriptions-item>
            <el-descriptions-item label="严重程度">
              <el-tag size="small" :type="severityTagType(detailCase.severity)">
                {{ severityLabel(detailCase.severity) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="发布时间">
              {{ formatDate(detailCase.published_at) }}
            </el-descriptions-item>
            <el-descriptions-item label="阅读次数">
              {{ detailCase.review_count }}
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 问题描述 -->
        <div class="detail-section">
          <h4>问题描述</h4>
          <div class="detail-content">{{ detailCase.description }}</div>
        </div>

        <!-- 经验教训 -->
        <div class="detail-section" v-if="detailCase.lessons_learned">
          <h4>经验教训</h4>
          <div class="detail-content">{{ detailCase.lessons_learned }}</div>
        </div>

        <!-- 关联准则 -->
        <div class="detail-section" v-if="detailCase.related_standards?.length">
          <h4>关联审计准则</h4>
          <div class="standards-list">
            <el-tag
              v-for="std in detailCase.related_standards"
              :key="std.code"
              size="default"
              effect="plain"
              type="warning"
              class="standard-tag"
            >
              {{ std.code }}{{ std.section ? ' §' + std.section : '' }}
              <span v-if="std.name" class="std-name">{{ std.name }}</span>
            </el-tag>
          </div>
        </div>

        <!-- 关联底稿引用（脱敏） -->
        <div class="detail-section" v-if="detailCase.related_wp_refs?.length">
          <h4>关联底稿引用（已脱敏）</h4>
          <el-table :data="detailCase.related_wp_refs" size="small" border>
            <el-table-column prop="wp_code" label="底稿编号" width="140" />
            <el-table-column prop="cycle" label="循环" width="100" />
            <el-table-column prop="snippet" label="摘要" />
          </el-table>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Search as SearchIcon, View } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  getCases,
  getCaseDetail,
  type QcCase,
  type QcCaseListParams,
} from '@/services/qcCaseApi'

// ── 筛选选项 ──

const categoryOptions = [
  { label: '底稿质量', value: 'workpaper_quality' },
  { label: '程序执行', value: 'procedure_execution' },
  { label: '判断偏差', value: 'judgment_bias' },
  { label: '披露遗漏', value: 'disclosure_omission' },
  { label: '合规问题', value: 'compliance' },
  { label: '其他', value: 'other' },
]

const severityOptions = [
  { label: '阻断', value: 'blocking' },
  { label: '警告', value: 'warning' },
  { label: '提示', value: 'info' },
]

// ── 状态 ──

const loading = ref(false)
const detailLoading = ref(false)
const detailVisible = ref(false)

const cases = ref<QcCase[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = 12

const filters = reactive<QcCaseListParams>({
  category: '',
  severity: '',
  search: '',
})

const detailCase = ref<QcCase | null>(null)

// ── 数据加载 ──

async function loadCases() {
  loading.value = true
  try {
    const params: QcCaseListParams = {
      page: currentPage.value,
      page_size: pageSize,
    }
    if (filters.category) params.category = filters.category
    if (filters.severity) params.severity = filters.severity
    if (filters.search) params.search = filters.search

    const res = await getCases(params)
    cases.value = res.items
    total.value = res.total
  } catch (e: any) {
    ElMessage.error('加载案例列表失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

function handleFilterChange() {
  currentPage.value = 1
  loadCases()
}

function handlePageChange(page: number) {
  currentPage.value = page
  loadCases()
}

// ── 详情 ──

async function openDetail(item: QcCase) {
  detailVisible.value = true
  detailCase.value = item
  detailLoading.value = true
  try {
    const detail = await getCaseDetail(item.id)
    detailCase.value = detail
  } catch (e: any) {
    ElMessage.error('加载案例详情失败: ' + (e.message || '未知错误'))
  } finally {
    detailLoading.value = false
  }
}

// ── 辅助函数 ──

function severityLabel(s: string): string {
  const map: Record<string, string> = {
    blocking: '阻断',
    warning: '警告',
    info: '提示',
  }
  return map[s] || s
}

function severityTagType(s: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'primary'> = {
    blocking: 'danger',
    warning: 'warning',
    info: 'info',
  }
  return map[s] || 'info'
}

function categoryLabel(c: string): string {
  const map: Record<string, string> = {
    workpaper_quality: '底稿质量',
    procedure_execution: '程序执行',
    judgment_bias: '判断偏差',
    disclosure_omission: '披露遗漏',
    compliance: '合规问题',
    other: '其他',
  }
  return map[c] || c
}

function truncate(text: string, maxLen: number): string {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleDateString('zh-CN')
}

// ── 生命周期 ──

onMounted(() => {
  loadCases()
})
</script>

<style scoped>
.qc-case-library {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-wrap: wrap;
}

.case-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
  align-content: start;
}

.case-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
}
.case-card:hover {
  border-color: var(--gt-color-primary, #6e3fd4);
  box-shadow: 0 2px 12px rgba(110, 63, 212, 0.08);
}

.case-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 10px;
}

.case-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  flex: 1;
  line-height: 1.4;
}

.case-tags {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.case-card-body {
  flex: 1;
  margin-bottom: 12px;
}

.case-desc {
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.5;
  margin: 0;
}

.case-card-footer {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  flex-wrap: wrap;
}

.case-meta {
  display: flex;
  align-items: center;
  gap: 4px;
}

.case-standards {
  display: flex;
  gap: 4px;
  align-items: center;
  margin-left: auto;
}

.more-tag {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

.pagination-bar {
  display: flex;
  justify-content: center;
  padding: 12px 20px;
  border-top: 1px solid var(--el-border-color-lighter);
}

/* 详情对话框 */
.case-detail {
  padding: 0 4px;
}

.detail-meta {
  margin-bottom: 20px;
}

.detail-section {
  margin-bottom: 20px;
}

.detail-section h4 {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--el-text-color-primary);
}

.detail-content {
  font-size: 13px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  background: var(--el-fill-color-lighter);
  padding: 12px;
  border-radius: 6px;
}

.standards-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.standard-tag {
  cursor: default;
}

.std-name {
  margin-left: 4px;
  color: var(--el-text-color-secondary);
}
</style>
