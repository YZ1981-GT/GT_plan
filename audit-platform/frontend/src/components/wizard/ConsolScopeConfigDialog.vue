<template>
  <el-dialog
    :model-value="modelValue"
    title="合并范围确认"
    width="720px"
    append-to-body
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @open="handleOpen"
  >
    <div v-loading="loading">
      <el-alert v-if="loadError" type="error" :closable="false" show-icon :title="loadError" />

      <!-- 确认状态摘要 -->
      <div v-if="preview" class="gt-scope-summary" data-testid="scope-summary">
        <p class="gt-scope-hint">
          合并范围由各项目基本信息中的企业代码、上级代码和与上级关系自动推导。
          <template v-if="preview.confirmed">
            <el-tag type="success" size="small" effect="plain">已确认</el-tag>
            版本 {{ preview.revision }}
          </template>
          <template v-else>
            <el-tag type="warning" size="small" effect="plain">待确认</el-tag>
          </template>
        </p>
        <el-alert
          v-if="preview.pending_legacy"
          type="info"
          :closable="false"
          show-icon
          title="该项目在新确认机制上线前已有合并数据，建议尽快确认当前范围"
          data-testid="legacy-hint"
        />
      </div>

      <!-- 节点表格（从 D5 nodes 读取，不再依赖旧 forest） -->
      <el-empty v-if="!loading && members.length === 0" description="暂未识别到下级企业" />
      <el-alert
        v-if="!loading && members.length === 0 && rootCompanyCode"
        type="info"
        :closable="false"
        show-icon
        :title="`请在各子公司/分公司项目的基本信息中把上级代码填为 ${rootCompanyCode}`"
      />

      <el-table
        v-if="members.length"
        :data="members"
        border
        size="small"
        max-height="420"
        data-testid="consol-scope-members"
      >
        <el-table-column label="企业名称" min-width="200">
          <template #default="{ row }">{{ row.company_name || '未命名企业' }}</template>
        </el-table-column>
        <el-table-column label="企业代码" width="170" prop="company_code" />
        <el-table-column label="角色" width="110" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ roleLabel(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="与上级关系" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.relation" size="small" effect="plain">
              {{ row.relation === 'branch' ? '分公司' : '子公司' }}
            </el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 诊断 -->
      <el-alert
        v-if="preview && preview.diagnostics.length"
        type="warning"
        :closable="false"
        show-icon
        class="gt-scope-diagnostics"
        title="企业树还有需要关注的提示"
      >
        <ul>
          <li v-for="(item, index) in preview.diagnostics" :key="`${item.code}-${index}`">
            {{ item.message }}
          </li>
        </ul>
      </el-alert>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
      <el-button
        v-if="preview && !preview.confirmed && preview.can_confirm"
        type="primary"
        :loading="confirming"
        data-testid="confirm-scope-btn"
        @click="handleConfirm"
      >
        确认当前合并范围
      </el-button>
      <el-button v-if="preview && preview.confirmed" type="success" disabled>
        已确认（版本 {{ preview.revision }}）
      </el-button>
      <el-button v-if="preview && !preview.can_confirm && !preview.confirmed" type="info" disabled>
        项目已锁定
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { parseApiError } from '@/composables/useApiError'
import {
  previewScopeConfirmation,
  confirmScope,
  type ScopeConfirmationPreview,
  type ScopeConfirmationNode,
} from '@/services/consolScopeConfirmationApi'

interface MemberRow {
  company_code: string
  company_name: string
  role: string
  relation: string | null
}

const ROLE_LABELS: Record<string, string> = {
  consol: '合并',
  consol_elim: '合并差额',
  parent: '母公司',
  hq: '本部',
  branch_elim: '母分差额',
  subsidiary: '子公司',
  branch: '分公司',
}
function roleLabel(role: string): string {
  return ROLE_LABELS[role] || role
}

const props = defineProps<{ modelValue: boolean; projectId: string }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  attached: [count: number]
  confirmed: [preview: ScopeConfirmationPreview]
}>()

const loading = ref(false)
const confirming = ref(false)
const loadError = ref('')
const preview = ref<ScopeConfirmationPreview | null>(null)
const members = ref<MemberRow[]>([])
const rootCompanyCode = ref('')

function extractMembers(nodes: ScopeConfirmationNode[]): MemberRow[] {
  return nodes
    .filter(n => n.role !== 'consol' && n.role !== 'consol_elim' && n.role !== 'branch_elim')
    .map(n => ({
      company_code: n.company_code,
      company_name: n.company_name,
      role: n.role,
      relation: n.relation,
    }))
}

async function loadPreview() {
  if (!props.projectId) return
  loading.value = true
  loadError.value = ''
  preview.value = null
  members.value = []
  try {
    const data = await previewScopeConfirmation(props.projectId)
    preview.value = data
    rootCompanyCode.value = (data.tree as any)?.company_code || ''
    members.value = extractMembers(data.nodes)
  } catch (err: any) {
    const parsed = parseApiError(err)
    loadError.value = parsed.message || '加载合并范围预览失败'
  } finally {
    loading.value = false
  }
}

async function handleOpen() {
  await loadPreview()
}

async function handleConfirm() {
  if (!preview.value || !props.projectId) return
  confirming.value = true
  try {
    const result = await confirmScope(props.projectId, {
      expected_fingerprint: preview.value.fingerprint,
      expected_revision: preview.value.revision,
    })
    preview.value = result
    members.value = extractMembers(result.nodes)
    ElMessage.success('合并范围已确认')
    emit('confirmed', result)
  } catch (err: any) {
    const parsed = parseApiError(err)
    if (parsed.code === 'SCOPE_FINGERPRINT_CONFLICT' || parsed.code === 'SCOPE_REVISION_CONFLICT') {
      const latestPreview = err?.response?.data?.detail?.latest_preview
      if (latestPreview) {
        preview.value = latestPreview
        members.value = extractMembers(latestPreview.nodes)
      } else {
        await loadPreview()
      }
      ElMessage.warning('合并范围已变化，请检查后重新确认')
    } else if (parsed.code === 'CONSOL_PROJECT_LOCKED') {
      ElMessage.error('项目已锁定，不能确认合并范围')
    } else {
      ElMessage.error(parsed.message || '确认合并范围失败')
    }
  } finally {
    confirming.value = false
  }
}
</script>

<style scoped>
.gt-scope-summary { margin-bottom: 12px; }
.gt-scope-hint {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  line-height: 1.6;
  margin: 0 0 8px;
}
.gt-scope-diagnostics { margin-top: 12px; }
.gt-scope-diagnostics ul { margin: 4px 0 0; padding-left: 18px; font-size: var(--gt-font-size-xs); }
</style>
