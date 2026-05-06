<template>
  <div class="qc-annual-reports">
    <!-- 顶部横幅 -->
    <div class="gt-page-banner">
      <div class="gt-banner-content">
        <h2>📊 年度质量报告</h2>
        <span class="gt-banner-sub">
          共 {{ total }} 份年报
        </span>
      </div>
      <div class="gt-banner-actions">
        <el-button type="primary" @click="showGenerateDialog = true">
          <el-icon><Plus /></el-icon>
          生成年报
        </el-button>
      </div>
    </div>

    <!-- 年报列表 -->
    <div class="report-list" v-loading="loading">
      <el-table :data="reports" border stripe style="width: 100%">
        <el-table-column prop="year" label="年度" width="120" align="center">
          <template #default="{ row }">
            <span class="year-text">{{ row.year }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="status" label="状态" width="140" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="default">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="created_at" label="创建时间" width="200">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="备注" min-width="200">
          <template #default="{ row }">
            <span class="report-message">{{ row.message || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="160" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'succeeded'"
              type="primary"
              size="small"
              link
              @click="handleDownload(row)"
            >
              <el-icon><Download /></el-icon>
              下载
            </el-button>
            <el-tag v-else-if="row.status === 'running' || row.status === 'queued'" type="warning" size="small">
              生成中...
            </el-tag>
            <el-tag v-else-if="row.status === 'failed'" type="danger" size="small">
              生成失败
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && reports.length === 0" description="暂无年报数据" />
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

    <!-- 生成年报对话框 -->
    <el-dialog
      v-model="showGenerateDialog"
      title="生成年度质量报告"
      width="420px"
      destroy-on-close
    >
      <el-form label-width="80px">
        <el-form-item label="报告年度">
          <el-date-picker
            v-model="selectedYear"
            type="year"
            placeholder="选择年度"
            format="YYYY"
            value-format="YYYY"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item>
          <p class="generate-hint">
            系统将异步生成该年度的质量报告，包含项目规模分布、评级分布、
            典型问题 Top10、复核人表现等章节。每年至多一个生成任务。
          </p>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showGenerateDialog = false">取消</el-button>
        <el-button
          type="primary"
          :loading="generating"
          :disabled="!selectedYear"
          @click="handleGenerate"
        >
          开始生成
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  listAnnualReports,
  generateAnnualReport,
  downloadAnnualReport,
  type AnnualReport,
} from '@/services/qcAnnualReportApi'

// ── 状态 ──

const loading = ref(false)
const generating = ref(false)
const showGenerateDialog = ref(false)

const reports = ref<AnnualReport[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = 20

const selectedYear = ref<string>('')

// ── 数据加载 ──

async function loadReports() {
  loading.value = true
  try {
    const res = await listAnnualReports(currentPage.value, pageSize)
    reports.value = res.items
    total.value = res.total
  } catch (e: any) {
    ElMessage.error('加载年报列表失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

function handlePageChange(page: number) {
  currentPage.value = page
  loadReports()
}

// ── 生成年报 ──

async function handleGenerate() {
  if (!selectedYear.value) {
    ElMessage.warning('请选择报告年度')
    return
  }

  generating.value = true
  try {
    const year = parseInt(selectedYear.value, 10)
    const result = await generateAnnualReport(year)
    if (result.job_id) {
      ElMessage.success(result.message || `${year} 年度报告已开始生成`)
    } else {
      ElMessage.info(result.message || '生成任务已存在')
    }
    showGenerateDialog.value = false
    selectedYear.value = ''
    // 刷新列表
    await loadReports()
  } catch (e: any) {
    ElMessage.error('生成年报失败: ' + (e.message || '未知错误'))
  } finally {
    generating.value = false
  }
}

// ── 下载 ──

async function handleDownload(report: AnnualReport) {
  try {
    await downloadAnnualReport(report.id, report.year)
    ElMessage.success('下载已开始')
  } catch (e: any) {
    ElMessage.error('下载失败: ' + (e.message || '未知错误'))
  }
}

// ── 辅助函数 ──

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    queued: '排队中',
    running: '生成中',
    succeeded: '已完成',
    failed: '失败',
  }
  return map[status] || status
}

function statusTagType(status: string): 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'primary'> = {
    queued: 'info',
    running: 'warning',
    succeeded: 'success',
    failed: 'danger',
  }
  return map[status] || 'info'
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// ── 生命周期 ──

onMounted(() => {
  loadReports()
})
</script>

<style scoped>
.qc-annual-reports {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0;
}

.gt-page-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.gt-banner-content h2 {
  margin: 0 0 4px;
  font-size: 18px;
  font-weight: 600;
}

.gt-banner-sub {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.report-list {
  flex: 1;
  padding: 20px 24px;
  overflow-y: auto;
}

.year-text {
  font-weight: 600;
  font-size: 15px;
}

.report-message {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.pagination-bar {
  display: flex;
  justify-content: center;
  padding: 12px 20px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.generate-hint {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
  margin: 0;
}
</style>
