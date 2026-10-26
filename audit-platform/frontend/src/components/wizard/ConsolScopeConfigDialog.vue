<template>
  <!--
    企业树版本（spec consol-autotree-linkage-closure R1）：企业树按各项目的三码自动生成，合并计算不需要确认；
    推送合并数时自动记录版本，树结构变化只提示不拦截。本弹窗展示当前树、已记录版本与差异，可手动「记录为新版本」。
    mode="created"：向导建完合并项目后打开，只预览自动生成的企业树。
  -->
  <el-dialog
    :model-value="modelValue"
    :title="isCreated ? '企业树预览' : '企业树版本'"
    width="760px"
    append-to-body
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @open="handleOpen"
  >
    <div v-loading="loading">
      <el-alert v-if="loadError" type="error" :closable="false" show-icon :title="loadError" />

      <div v-if="preview" class="gt-scope-summary" data-testid="scope-summary">
        <p class="gt-scope-hint">
          企业树由各项目基本信息中的企业代码、上级代码和与上级关系自动生成，合并计算直接按当前树进行，不需要确认；
          推送合并数时自动记录树版本，树结构变化时只提示、不拦截。
        </p>
        <p v-if="!isCreated" class="gt-scope-version" data-testid="scope-version">
          <template v-if="preview.recorded_revision">
            已记录版本 v{{ preview.recorded_revision }}（{{ recordedModeText }}<template v-if="preview.recorded_at">，{{ fmtDateTime(preview.recorded_at) }}</template>）
            <el-tag :type="matchTag.type" size="small" effect="plain">{{ matchTag.text }}</el-tag>
          </template>
          <template v-else>
            <el-tag type="info" size="small" effect="plain">尚未记录</el-tag> 首次推送合并数时自动记录
          </template>
        </p>
        <el-alert v-if="!isCreated && diffLines.length" :type="preview.structural_change ? 'warning' : 'info'"
          :closable="false" show-icon class="gt-scope-diff" title="当前企业树与已记录版本的差异" data-testid="scope-diff">
          <ul><li v-for="(line, i) in diffLines" :key="i">{{ line }}</li></ul>
        </el-alert>
      </div>

      <el-empty v-if="!loading && preview && !hasSubordinates" description="暂未识别到下级企业" />
      <el-alert
        v-if="!loading && preview && !hasSubordinates && rootCompanyCode"
        type="info"
        :closable="false"
        show-icon
        :title="`请在各子公司/分公司项目的基本信息中把上级代码填为 ${rootCompanyCode}`"
      />

      <el-table v-if="members.length" :data="members" border size="small" max-height="420" data-testid="consol-scope-members">
        <el-table-column label="节点" min-width="230">
          <template #default="{ row }">
            <span :style="{ paddingLeft: row.depth * 14 + 'px' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="企业代码" width="170" prop="company_code" />
        <el-table-column label="角色" width="120" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" :type="row.kind === 'elim' ? 'warning' : 'info'">{{ row.role_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="与上级关系" width="100" align="center">
          <template #default="{ row }">{{ row.relation_label || '—' }}</template>
        </el-table-column>
      </el-table>

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
      <el-button data-testid="scope-close-btn" @click="emit('update:modelValue', false)">{{ isCreated ? '进入合并模块' : '关闭' }}</el-button>
      <el-button
        v-if="!isCreated && preview && preview.can_confirm && !preview.matches_recorded"
        type="primary"
        :loading="confirming"
        data-testid="record-version-btn"
        @click="handleRecord"
      >
        记录为新版本
      </el-button>
      <el-button v-if="!isCreated && preview && !preview.can_confirm" type="info" disabled>项目已锁定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { parseApiError } from '@/composables/useApiError'
import { fmtDateTime } from '@/utils/formatters'
import { relationLabel } from '@/utils/groupRelation'
import type { ConsolTreeNode } from '@/services/consolidationApi'
import { nodeLabel, roleLabel, treeDiffLines } from '@/components/consolidation/composables/consolTreeView'
import {
  previewScopeConfirmation,
  confirmScope,
  type ScopeConfirmationPreview,
} from '@/services/consolScopeConfirmationApi'

interface MemberRow {
  node_key: string
  label: string
  company_code: string
  role: string
  role_label: string
  kind: string
  relation_label: string
  depth: number
}

const props = defineProps<{
  modelValue: boolean
  projectId: string
  /** created = 向导建完合并项目后的预览（只看树）；默认 = 合并页的企业树版本管理 */
  mode?: 'created' | 'manage'
}>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  recorded: [preview: ScopeConfirmationPreview]
}>()

const isCreated = computed(() => props.mode === 'created')
const loading = ref(false)
const confirming = ref(false)
const loadError = ref('')
const preview = ref<ScopeConfirmationPreview | null>(null)
const members = ref<MemberRow[]>([])
const rootCompanyCode = ref('')

const recordedModeText = computed(() => (preview.value?.recorded_mode === 'user' ? '手动记录' : '推送时自动记录'))
const matchTag = computed(() => {
  const p = preview.value
  if (p?.matches_recorded) return { type: 'success' as const, text: '与当前树一致' }
  if (p?.structural_change) return { type: 'warning' as const, text: '当前树结构已变化' }
  return { type: 'info' as const, text: '当前树只改了名称' }
})
const diffLines = computed(() => treeDiffLines(preview.value?.diff))
/** 根节点之外还有企业（子公司 / 分公司 / 下级合并户） */
const hasSubordinates = computed(() => members.value.some((m) => m.depth > 0 && (m.role === 'subsidiary' || m.role === 'branch' || m.role === 'consol')))

/** 企业树（先序）→ 节点行：带层级缩进、展示名、角色（按节点类型）与上级关系 */
function treeMembers(tree: ConsolTreeNode | null): MemberRow[] {
  const out: MemberRow[] = []
  const visit = (node: ConsolTreeNode, depth: number) => {
    out.push({
      node_key: node.node_key,
      label: nodeLabel(node),
      company_code: node.company_code,
      role: node.role,
      role_label: roleLabel(node.role, node.kind) || node.role,
      kind: node.kind,
      relation_label: relationLabel(node.relation),
      depth,
    })
    for (const child of node.children || []) visit(child, depth + 1)
  }
  if (tree && tree.node_key) visit(tree, 0)
  return out
}

function applyPreview(data: ScopeConfirmationPreview) {
  preview.value = data
  const tree = (data.tree || null) as unknown as ConsolTreeNode | null
  rootCompanyCode.value = tree?.company_code || ''
  members.value = treeMembers(tree)
}

async function loadPreview() {
  if (!props.projectId) return
  loading.value = true
  loadError.value = ''
  preview.value = null
  members.value = []
  try {
    applyPreview(await previewScopeConfirmation(props.projectId))
  } catch (err: any) {
    const parsed = parseApiError(err)
    loadError.value = parsed.message || '加载企业树失败'
  } finally {
    loading.value = false
  }
}

async function handleOpen() {
  await loadPreview()
}

async function handleRecord() {
  if (!preview.value || !props.projectId) return
  confirming.value = true
  try {
    const result = await confirmScope(props.projectId, {
      expected_fingerprint: preview.value.fingerprint,
      expected_revision: preview.value.revision,
    })
    applyPreview(result)
    ElMessage.success(`已记录为企业树版本 v${result.recorded_revision || result.revision}`)
    emit('recorded', result)
  } catch (err: any) {
    const parsed = parseApiError(err)
    if (parsed.code === 'SCOPE_FINGERPRINT_CONFLICT' || parsed.code === 'SCOPE_REVISION_CONFLICT') {
      const latestPreview = err?.response?.data?.detail?.latest_preview
      if (latestPreview) applyPreview(latestPreview)
      else await loadPreview()
      ElMessage.warning('企业树已变化，请检查后重新记录')
    } else if (parsed.code === 'CONSOL_PROJECT_LOCKED') {
      ElMessage.error('项目已锁定，不能记录企业树版本')
    } else {
      ElMessage.error(parsed.message || '记录企业树版本失败')
    }
  } finally {
    confirming.value = false
  }
}

defineExpose({ members, preview })
</script>

<style scoped>
.gt-scope-summary { margin-bottom: 12px; }
.gt-scope-hint, .gt-scope-version {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
  line-height: 1.6;
  margin: 0 0 8px;
}
.gt-scope-diff ul, .gt-scope-diagnostics ul { margin: 4px 0 0; padding-left: 18px; font-size: var(--gt-font-size-xs); }
.gt-scope-diagnostics { margin-top: 12px; }
</style>
