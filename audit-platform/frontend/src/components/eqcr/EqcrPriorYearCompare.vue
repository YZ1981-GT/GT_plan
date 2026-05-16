<template>
  <div class="eqcr-prior-year">
    <div class="eqcr-prior-year__header">
      <h4>历年 EQCR 对比</h4>
      <el-button size="small" @click="fetchComparison" :loading="loading" round>刷新</el-button>
    </div>

    <el-alert
      v-if="data && data.has_differences"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom: 12px"
    >
      <template #title>存在与上年 EQCR 意见不一致的判断域，请填写差异原因后方可审批</template>
    </el-alert>

    <el-empty v-if="!loading && data && data.prior_years.length === 0" description="未找到同客户历史项目">
      <el-button size="small" @click="showLinkDialog = true">手动关联上年项目</el-button>
    </el-empty>

    <!-- 对比表格 -->
    <el-table
      v-if="data && data.prior_years.length > 0"
      :data="tableData"
      border
      stripe
      style="width: 100%"
    >
      <el-table-column prop="domain_label" label="判断域" width="120" />
      <el-table-column prop="current_verdict" label="本年意见" width="100">
        <template #default="{ row }">
          <el-tag :type="verdictTagType(row.current_verdict)" size="small">
            {{ verdictLabel(row.current_verdict) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        v-for="py in data.prior_years"
        :key="py.project_id"
        :label="`${py.year || '未知'}年`"
        width="100"
      >
        <template #default="{ row }">
          <el-tag
            :type="verdictTagType(row.prior_verdicts[py.project_id])"
            size="small"
            :class="{ 'diff-highlight': row.has_diff[py.project_id] }"
          >
            {{ verdictLabel(row.prior_verdicts[py.project_id]) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="差异" width="60">
        <template #default="{ row }">
          <span v-if="row.is_different" class="diff-marker">⚠️</span>
          <span v-else>✓</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 差异原因填写 -->
    <div v-if="data && data.differences.length > 0" class="eqcr-prior-year__reasons">
      <h5 style="margin: 16px 0 8px">差异原因（必填）</h5>
      <div v-for="diff in data.differences" :key="`${diff.domain}-${diff.prior_year}`" class="diff-reason-item">
        <div class="diff-reason-label">
          {{ domainLabel(diff.domain) }}：本年 {{ verdictLabel(diff.current_verdict) }} vs {{ diff.prior_year }}年 {{ verdictLabel(diff.prior_verdict) }}
        </div>
        <el-input
          v-model="diffReasons[diff.domain]"
          type="textarea"
          :rows="2"
          placeholder="请说明与上年判断不同的原因..."
        />
      </div>
    </div>

    <!-- 手动关联弹窗 -->
    <el-dialog v-model="showLinkDialog" title="手动关联上年项目" width="400px" append-to-body>
      <el-form label-width="80px">
        <el-form-item label="项目 ID">
          <el-input v-model="linkProjectId" placeholder="输入上年项目 UUID" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showLinkDialog = false">取消</el-button>
        <el-button type="primary" @click="onLinkPriorYear" :loading="linkLoading">关联</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/services/apiProxy'
import { eqcr as P_eqcr } from '@/services/apiPaths'

const props = defineProps<{ projectId: string }>()

const loading = ref(false)
const linkLoading = ref(false)
const showLinkDialog = ref(false)
const linkProjectId = ref('')
const data = ref<any>(null)
const diffReasons = ref<Record<string, string>>({})

const DOMAIN_LABELS: Record<string, string> = {
  materiality: '重要性',
  estimate: '会计估计',
  related_party: '关联方',
  going_concern: '持续经营',
  opinion_type: '审计意见',
}

const VERDICT_LABELS: Record<string, string> = {
  agree: '认可',
  disagree: '有异议',
  need_more_evidence: '需补充证据',
}

type ElTagType = 'success' | 'warning' | 'info' | 'primary' | 'danger'

function domainLabel(d: string) { return DOMAIN_LABELS[d] || d }
function verdictLabel(v: string | undefined) { return v ? (VERDICT_LABELS[v] || v) : '—' }
function verdictTagType(v: string | undefined): ElTagType {
  if (!v) return 'info'
  if (v === 'agree') return 'success'
  if (v === 'disagree') return 'danger'
  return 'warning'
}

const tableData = computed(() => {
  if (!data.value) return []
  const domains = ['materiality', 'estimate', 'related_party', 'going_concern', 'opinion_type']
  return domains.map(domain => {
    const currentVerdict = data.value.current_opinions[domain]?.verdict
    const priorVerdicts: Record<string, string | undefined> = {}
    const hasDiff: Record<string, boolean> = {}
    let isDifferent = false

    for (const py of data.value.prior_years) {
      const pv = py.opinions_by_domain[domain]?.verdict
      priorVerdicts[py.project_id] = pv
      const diff = currentVerdict && pv && currentVerdict !== pv
      hasDiff[py.project_id] = !!diff
      if (diff) isDifferent = true
    }

    return {
      domain,
      domain_label: domainLabel(domain),
      current_verdict: currentVerdict,
      prior_verdicts: priorVerdicts,
      has_diff: hasDiff,
      is_different: isDifferent,
    }
  })
})

async function fetchComparison() {
  loading.value = true
  try {
    data.value = await api.get(P_eqcr.priorYearComparison(props.projectId))
  } catch {
    ElMessage.error('获取历年对比数据失败')
  } finally {
    loading.value = false
  }
}

async function onLinkPriorYear() {
  if (!linkProjectId.value.trim()) {
    ElMessage.warning('请输入项目 ID')
    return
  }
  linkLoading.value = true
  try {
    const result = await api.post(P_eqcr.linkPriorYear(props.projectId), {
      prior_project_id: linkProjectId.value.trim(),
    })
    if (result?.linked) {
      // 追加到 prior_years
      if (data.value) {
        data.value.prior_years.push({
          project_id: result.prior_project_id,
          project_name: result.prior_project_name,
          year: result.prior_year,
          opinions_by_domain: result.opinions_by_domain,
        })
      }
      ElMessage.success('已关联上年项目')
      showLinkDialog.value = false
    }
  } catch {
    ElMessage.error('关联失败，请检查项目 ID')
  } finally {
    linkLoading.value = false
  }
}

/** 外部调用：检查差异原因是否全部填写 */
function allDiffReasonsProvided(): boolean {
  if (!data.value || data.value.differences.length === 0) return true
  const domains: string[] = data.value.differences.map((d: any) => String(d.domain))
  const unique = Array.from(new Set(domains))
  for (const domain of unique) {
    if (!diffReasons.value[domain]?.trim()) return false
  }
  return true
}

/** 外部调用：获取差异原因 */
function getDiffReasons() {
  return { ...diffReasons.value }
}

defineExpose({ allDiffReasonsProvided, getDiffReasons })

onMounted(fetchComparison)
</script>

<style scoped>
.eqcr-prior-year__header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px;
}
.eqcr-prior-year__header h4 { margin: 0; font-weight: 600; }
.diff-highlight { border: 2px solid var(--gt-color-wheat) !important; }
.diff-marker { color: var(--gt-color-wheat); font-size: var(--gt-font-size-md); }
.diff-reason-item { margin-bottom: 12px; }
.diff-reason-label { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-regular); margin-bottom: 4px; }
.eqcr-prior-year__reasons { border-top: 1px solid var(--gt-color-border-lighter); padding-top: 8px; }
</style>
