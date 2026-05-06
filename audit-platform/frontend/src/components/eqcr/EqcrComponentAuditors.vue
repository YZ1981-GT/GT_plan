<template>
  <div class="eqcr-component-auditors">
    <div class="eqcr-component-auditors__header">
      <h4>组成部分审计师复核</h4>
      <el-button size="small" @click="fetchData" :loading="loading" round>刷新</el-button>
    </div>

    <el-empty v-if="!loading && auditors.length === 0" description="暂无组成部分审计师数据" />

    <el-table
      v-if="auditors.length > 0"
      :data="auditors"
      border
      stripe
      style="width: 100%"
      :row-class-name="rowClassName"
    >
      <el-table-column prop="company_code" label="公司代码" width="100" />
      <el-table-column prop="firm_name" label="事务所" min-width="150" />
      <el-table-column prop="contact_person" label="联系人" width="100" />
      <el-table-column label="能力评级" width="130" align="center">
        <template #default="{ row }">
          <el-tag
            v-if="row.competence_rating"
            :type="ratingTagType(row.competence_rating)"
            size="small"
          >
            {{ ratingLabel(row.competence_rating) }}
          </el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="独立性" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.independence_confirmed ? 'success' : 'danger'" size="small">
            {{ row.independence_confirmed ? '已确认' : '未确认' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="instruction_count" label="指令数" width="70" align="center" />
      <el-table-column prop="result_count" label="结果数" width="70" align="center" />
      <el-table-column label="EQCR 意见" width="120" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.eqcr_opinions.length > 0" :type="opinionTagType(row.eqcr_opinions[0].verdict)" size="small">
            {{ verdictLabel(row.eqcr_opinions[0].verdict) }}
          </el-tag>
          <el-button v-else size="small" link @click="openOpinionForm(row)">录入</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 意见录入弹窗 -->
    <el-dialog v-model="showOpinionDialog" title="录入 EQCR 意见" width="500px" append-to-body>
      <el-form label-width="80px">
        <el-form-item label="审计师">
          <span>{{ selectedAuditor?.firm_name }} ({{ selectedAuditor?.company_code }})</span>
        </el-form-item>
        <el-form-item label="结论">
          <el-radio-group v-model="opinionForm.verdict">
            <el-radio value="agree">认可</el-radio>
            <el-radio value="disagree">有异议</el-radio>
            <el-radio value="need_more_evidence">需补充证据</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="opinionForm.comment" type="textarea" :rows="3" placeholder="请说明复核意见..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showOpinionDialog = false">取消</el-button>
        <el-button type="primary" @click="submitOpinion" :loading="submitting">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/services/apiProxy'

const props = defineProps<{ projectId: string }>()

const loading = ref(false)
const submitting = ref(false)
const auditors = ref<any[]>([])
const showOpinionDialog = ref(false)
const selectedAuditor = ref<any>(null)
const opinionForm = ref({ verdict: 'agree', comment: '' })

const VERDICT_LABELS: Record<string, string> = {
  agree: '认可',
  disagree: '有异议',
  need_more_evidence: '需补充证据',
}

const RATING_LABELS: Record<string, string> = {
  reliable: '可信赖',
  additional_procedures_needed: '需补充程序',
  unreliable: '不可信赖',
}

type ElTagType = 'success' | 'warning' | 'info' | 'primary' | 'danger'

function verdictLabel(v: string) { return VERDICT_LABELS[v] || v }

function ratingLabel(r: string | null): string {
  if (!r) return '—'
  return RATING_LABELS[r] || r
}

function ratingTagType(rating: string | null): ElTagType {
  if (!rating) return 'info'
  if (rating === 'reliable') return 'success'
  if (rating === 'additional_procedures_needed') return 'warning'
  if (rating === 'unreliable') return 'danger'
  return 'info'
}

function opinionTagType(verdict: string): ElTagType {
  if (verdict === 'agree') return 'success'
  if (verdict === 'disagree') return 'danger'
  return 'warning'
}

function rowClassName({ row }: { row: any }) {
  // 需求 11.4：能力评级"不可信赖"或"需补充程序"时高亮
  if (row.competence_rating === 'unreliable' || row.competence_rating === 'additional_procedures_needed') {
    return 'highlight-row'
  }
  return ''
}

function openOpinionForm(auditor: any) {
  selectedAuditor.value = auditor
  opinionForm.value = { verdict: 'agree', comment: '' }
  showOpinionDialog.value = true
}

async function submitOpinion() {
  if (!selectedAuditor.value) return
  submitting.value = true
  try {
    await api.post('/api/eqcr/opinions', {
      project_id: props.projectId,
      domain: 'component_auditor',
      verdict: opinionForm.value.verdict,
      comment: opinionForm.value.comment,
      extra_payload: {
        auditor_id: selectedAuditor.value.id,
        auditor_name: selectedAuditor.value.firm_name,
      },
    })
    ElMessage.success('意见已提交')
    showOpinionDialog.value = false
    await fetchData()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

async function fetchData() {
  loading.value = true
  try {
    const data = await api.get(`/api/eqcr/projects/${props.projectId}/component-auditors`)
    auditors.value = data.auditors || []
  } catch {
    ElMessage.error('获取组成部分审计师数据失败')
  } finally {
    loading.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.eqcr-component-auditors__header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px;
}
.eqcr-component-auditors__header h4 { margin: 0; font-weight: 600; }
:deep(.highlight-row) {
  background-color: #fef0f0 !important;
}
</style>
