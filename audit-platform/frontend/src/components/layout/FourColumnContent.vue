<template>
  <div class="gt-four-content">
    <!-- 未选择项目 -->
    <el-empty v-if="!project" description="请从左侧选择一个项目" :image-size="80" />

    <!-- 未选择目录项 -->
    <div v-else-if="!catalogItem" class="gt-four-placeholder">
      <DetailProjectPanel :project="project" />
    </div>

    <!-- 报表内容 -->
    <div v-else-if="catalogItem.type === 'report'" class="gt-four-report">
      <h3>{{ catalogItem.label }} — {{ catalogItem.year }}年度</h3>
      <div v-if="reportLoading" v-loading="true" style="height: 200px" />
      <el-table v-else-if="reportRows.length" :data="reportRows" size="small" stripe border max-height="calc(100vh - 160px)">
        <el-table-column prop="row_name" label="项目" min-width="200" fixed />
        <el-table-column label="期末数" width="140" align="right">
          <template #default="{ row }">{{ fmtAmt(row.current_period_amount) }}</template>
        </el-table-column>
        <el-table-column label="年初数" width="140" align="right">
          <template #default="{ row }">{{ fmtAmt(row.prior_period_amount) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="暂无报表数据" :image-size="60" />
    </div>

    <!-- 附注内容 -->
    <div v-else-if="catalogItem.type === 'note'" class="gt-four-note">
      <h3>{{ catalogItem.code }} {{ catalogItem.title }}</h3>
      <div v-if="noteContent" v-html="noteContent" class="gt-note-body" />
      <el-empty v-else description="暂无附注内容" :image-size="60" />
    </div>

    <!-- 底稿内容 -->
    <div v-else-if="catalogItem.type === 'workpaper'" class="gt-four-wp">
      <h3>{{ catalogItem.wp_code }} {{ catalogItem.name }}</h3>
      <p style="color: var(--gt-color-text-secondary)">点击下方按钮进入底稿编辑</p>
      <el-button type="primary" @click="goToWp">打开底稿</el-button>
    </div>

    <!-- 试算表科目详情 -->
    <div v-else-if="catalogItem.type === 'trial_balance'" class="gt-four-tb">
      <h3>{{ catalogItem.code }} {{ catalogItem.name }}</h3>
      <el-descriptions :column="2" border size="small" v-if="tbDetail">
        <el-descriptions-item label="未审数">{{ fmtAmt(tbDetail.unadjusted_amount) }}</el-descriptions-item>
        <el-descriptions-item label="期初余额">{{ fmtAmt(tbDetail.opening_balance) }}</el-descriptions-item>
        <el-descriptions-item label="AJE调整">{{ fmtAmt(tbDetail.aje_adjustment) }}</el-descriptions-item>
        <el-descriptions-item label="RJE调整">{{ fmtAmt(tbDetail.rje_adjustment) }}</el-descriptions-item>
        <el-descriptions-item label="审定数">{{ fmtAmt(tbDetail.audited_amount) }}</el-descriptions-item>
      </el-descriptions>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import http from '@/utils/http'
import DetailProjectPanel from './DetailProjectPanel.vue'

const props = defineProps<{
  project: any | null
  catalogItem: any | null
}>()

const router = useRouter()
const reportRows = ref<any[]>([])
const reportLoading = ref(false)
const noteContent = ref('')
const tbDetail = ref<any>(null)
const selectedYear = computed(() => Number(props.catalogItem?.year || props.project?.audit_year) || new Date().getFullYear())

function fmtAmt(v: any): string {
  const n = Number(v)
  if (!n && n !== 0) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function goToWp() {
  if (!props.project || !props.catalogItem) return
  router.push(`/projects/${props.project.id}/workpapers/${props.catalogItem.id}/edit`)
}

watch(() => props.catalogItem, async (item) => {
  if (!item || !props.project) return
  const pid = props.project.id

  if (item.type === 'report') {
    reportLoading.value = true
    try {
      const { data } = await http.get(
        `/api/reports/${pid}/${item.year}/${item.type_key || 'balance_sheet'}`,
        { validateStatus: (s: number) => s < 600 }
      )
      const d = data?.data ?? data
      reportRows.value = Array.isArray(d) ? d : (d?.rows ?? [])
    } catch { reportRows.value = [] }
    finally { reportLoading.value = false }
  }

  if (item.type === 'note') {
    try {
      const { data } = await http.get(
        `/api/disclosure-notes/${pid}/${selectedYear.value}/${item.code}`,
        { validateStatus: (s: number) => s < 600 }
      )
      const section = data?.data ?? data
      noteContent.value = section?.text_content || section?.content || '<p>暂无内容</p>'
    } catch { noteContent.value = '' }
  }

  if (item.type === 'trial_balance') {
    try {
      const { data } = await http.get(`/api/projects/${pid}/trial-balance`, {
        params: { year: selectedYear.value },
        validateStatus: (s: number) => s < 600,
      })
      const rows = data.data ?? data ?? []
      tbDetail.value = rows.find((r: any) => r.standard_account_code === item.code) || null
    } catch { tbDetail.value = null }
  }
}, { immediate: true })
</script>

<style scoped>
.gt-four-content { padding: var(--gt-space-4); height: 100%; overflow-y: auto; }
.gt-four-content h3 {
  font-size: var(--gt-font-size-lg); font-weight: 700;
  color: var(--gt-color-primary-dark); margin-bottom: var(--gt-space-3);
}
.gt-four-placeholder { height: 100%; }
.gt-note-body { font-size: var(--gt-font-size-sm); line-height: 1.6; }
</style>
