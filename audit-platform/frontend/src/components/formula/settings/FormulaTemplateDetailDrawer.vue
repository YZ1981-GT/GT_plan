<!--
  公式模板详情（spec formula-global-settings-sync，design §16.6，R13.4 / R13.6 / R13.7 / R13.8 / R13.9）。
  定义（按域）、与当前全局不一致的提示（可一键并入模板）、版本历史、订阅项目（所有者 / 管理员）。
  所有者 / 管理员：暂存修改 → 发布新版本（订阅项目走预览、逐项目应用 / 暂缓、冲突决策与待确认）；
  改名与共享范围；删除（有订阅时不可删）；设为全局（管理员）/ 提交为全局候选（其他人）。
-->
<template>
  <el-drawer v-model="visible" :title="detail?.name || '模板详情'" size="64%" append-to-body destroy-on-close
    data-testid="formula-template-detail">
    <div v-loading="loading" class="gt-ftd">
      <template v-if="detail">
        <el-descriptions :column="3" size="small" border class="gt-ftd-gap">
          <el-descriptions-item label="共享范围">{{ detail.share_scope_label }}</el-descriptions-item>
          <el-descriptions-item label="适用范围">{{ scopeLabel(detail.applicable_scope) }}</el-descriptions-item>
          <el-descriptions-item label="当前版本">v{{ detail.version }}</el-descriptions-item>
          <el-descriptions-item label="公式域">{{ detail.domains.map(domainLabel).join('、') }}</el-descriptions-item>
          <el-descriptions-item label="订阅项目">{{ detail.subscriber_count }} 个</el-descriptions-item>
          <el-descriptions-item label="说明">{{ detail.description || '—' }}</el-descriptions-item>
        </el-descriptions>

        <div class="gt-ftd-actions">
          <template v-if="detail.can_manage">
            <el-button size="small" @click="openMeta">改名 / 共享范围</el-button>
            <el-button size="small" type="primary" :disabled="!stagedCount" :loading="previewLoading"
              data-testid="ftd-publish" @click="onPublishPreview">发布新版本（{{ stagedCount }}）</el-button>
            <el-button v-if="stagedCount" size="small" @click="clearStaged">放弃暂存</el-button>
          </template>
          <el-button v-for="d in detail.domains" :key="d" size="small" :loading="promoting === d" @click="onPromote(d)">
            {{ isAdmin ? '设为全局' : '提交为全局候选' }}：{{ domainLabel(d) }}
          </el-button>
          <span class="gt-ftd-spacer" />
          <el-button v-if="detail.can_manage" size="small" type="danger" plain @click="onDelete">删除模板</el-button>
        </div>

        <el-alert v-if="hints.length" type="warning" :closable="false" show-icon class="gt-ftd-gap"
          :title="`全局设置已更新：模板里有 ${hints.length} 处与当前全局不一致（模板写入后全局又改了）`">
          <el-button v-if="detail.can_manage" size="small" type="warning" plain data-testid="ftd-merge-all"
            @click="mergeAll">全部并入模板（暂存后发布新版本）</el-button>
        </el-alert>

        <el-tabs v-model="tab">
          <el-tab-pane label="公式定义" name="defs">
            <div class="gt-ftd-definition-bar">
              <el-radio-group v-model="activeDomain" size="small" class="gt-ftd-gap">
                <el-radio-button v-for="d in detail.domains" :key="d" :value="d">{{ domainLabel(d) }}</el-radio-button>
              </el-radio-group>
              <el-button v-if="detail.can_manage" size="small" type="primary" plain data-testid="ftd-add-slot"
                @click="openNewSlot">+ 新增公式位</el-button>
            </div>
            <el-table :data="domainRows" size="small" border max-height="calc(100vh - 420px)" row-key="slot_key">
              <el-table-column prop="label" label="公式位" min-width="220" show-overflow-tooltip />
              <el-table-column label="定义" min-width="260">
                <template #default="{ row }">
                  <el-tag v-if="row.staged" size="small" type="warning">已暂存</el-tag>
                  <code class="gt-ftd-code">{{ definitionText(row.definition) }}</code>
                </template>
              </el-table-column>
              <el-table-column v-if="detail.can_manage" label="操作" width="110" align="center">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
                  <el-button link type="danger" size="small" @click="stageDelete(row)">移除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane :label="`与全局不一致（${hints.length}）`" name="hints">
            <el-table :data="hints" size="small" border max-height="calc(100vh - 380px)" empty-text="模板与当前全局一致">
              <el-table-column prop="label" label="公式位" min-width="180" show-overflow-tooltip />
              <el-table-column label="模板定义" min-width="160">
                <template #default="{ row }"><code class="gt-ftd-code">{{ definitionText(row.template_definition) }}</code></template>
              </el-table-column>
              <el-table-column label="写入时的全局" min-width="160">
                <template #default="{ row }"><code class="gt-ftd-code">{{ definitionText(row.base_definition) }}</code></template>
              </el-table-column>
              <el-table-column label="当前全局" min-width="160">
                <template #default="{ row }"><code class="gt-ftd-code gt-ftd-new">{{ definitionText(row.global_definition) }}</code></template>
              </el-table-column>
              <el-table-column v-if="detail.can_manage" label="操作" width="100" align="center">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="mergeHint(row)">并入模板</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane label="版本历史" name="versions">
            <el-table :data="versions" size="small" border max-height="calc(100vh - 380px)">
              <el-table-column label="版本" width="70" align="center">
                <template #default="{ row }">v{{ row.version }}</template>
              </el-table-column>
              <el-table-column label="时间" width="170">
                <template #default="{ row }">{{ fmtTime(row.published_at) }}</template>
              </el-table-column>
              <el-table-column label="变更" width="80" align="center">
                <template #default="{ row }">{{ (row.change_set || []).length }}</template>
              </el-table-column>
              <el-table-column prop="note" label="说明" min-width="200" show-overflow-tooltip />
              <el-table-column label="操作" width="190" align="center">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" :loading="diffLoading && diffVersion === row.version"
                    @click="openDiff(row)">与当前对比</el-button>
                  <el-button v-if="detail.can_manage && row.version < detail.version" link type="warning" size="small"
                    @click="openRollback(row)">回滚到此版本</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
          <el-tab-pane v-if="detail.can_manage" label="订阅项目" name="subscribers">
            <el-table :data="subscribers" size="small" border max-height="calc(100vh - 380px)" empty-text="暂无项目订阅">
              <el-table-column prop="project_name" label="项目" min-width="200" show-overflow-tooltip />
              <el-table-column label="公式域" width="140">
                <template #default="{ row }">{{ domainLabel(row.domain) }}</template>
              </el-table-column>
              <el-table-column label="订阅版本" width="110">
                <template #default="{ row }">
                  v{{ row.template_version }}
                  <el-tag v-if="row.behind" size="small" type="warning">落后</el-tag>
                  <el-tag v-if="row.pinned" size="small" type="danger">暂缓</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="local_modified" label="本地改过" width="90" align="center" />
              <el-table-column prop="pending" label="待确认" width="80" align="center" />
              <el-table-column label="入口" width="130" align="center">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="goSubscribe(row)">到项目中订阅</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </template>
    </div>
  </el-drawer>

  <FormulaDefinitionEditDialog v-model="editVisible" :title="`编辑模板公式：${editing?.label || ''}`"
    :exec-fields="fieldsOf(activeDomain).exec" :desc-fields="fieldsOf(activeDomain).desc"
    :definition="editing?.definition || null" @save="onEditSave" />
  <FormulaPublishPreviewDialog v-model="previewVisible" :preview="preview" :loading="previewLoading" :title="previewTitle"
    :submit="onSubmitPreview" :submit-text="previewKind === 'publish' ? '发布新版本' : previewKind === 'rollback' ? '回滚并发布新版本' : '确认发布'"
    :conflict-options="previewKind === 'promote' ? undefined : TEMPLATE_CHOICES"
    :new-label="previewKind === 'publish' ? '模板新定义' : previewKind === 'rollback' ? '目标历史版本' : '新全局'" />
  <el-dialog v-model="metaVisible" title="改名 / 共享范围" width="480px" append-to-body destroy-on-close>
    <el-form ref="metaFormRef" :model="meta" :rules="metaRules" label-width="90px">
      <el-form-item label="名称" prop="name"><el-input v-model="meta.name" maxlength="200" /></el-form-item>
      <el-form-item label="说明"><el-input v-model="meta.description" type="textarea" :rows="2" /></el-form-item>
      <el-form-item label="共享范围">
        <el-radio-group v-model="meta.share_scope">
          <el-radio v-for="o in metaShareOptions" :key="o.value" :value="o.value">{{ o.label }}</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="metaVisible = false">取消</el-button>
      <el-button type="primary" :loading="metaSaving" @click="onMetaSave">保存</el-button>
    </template>
  </el-dialog>
  <el-dialog v-model="diffVisible" title="版本差异" width="900px" append-to-body destroy-on-close>
    <div v-if="diff" class="gt-ftd-diff-summary">v{{ diff.from_version }} → v{{ diff.to_version }}，共 {{ diff.changes.length }} 处变化</div>
    <el-table v-if="diff" :data="diff.changes" size="small" border max-height="520px" empty-text="两个版本没有差异">
      <el-table-column prop="domain" label="公式域" width="120" />
      <el-table-column prop="label" label="公式位" min-width="180" show-overflow-tooltip />
      <el-table-column prop="kind" label="变化" width="90" />
      <el-table-column label="旧定义" min-width="220">
        <template #default="{ row }"><code class="gt-ftd-code">{{ definitionText(row.old) }}</code></template>
      </el-table-column>
      <el-table-column label="新定义" min-width="220">
        <template #default="{ row }"><code class="gt-ftd-code gt-ftd-new">{{ definitionText(row.new) }}</code></template>
      </el-table-column>
    </el-table>
  </el-dialog>
  <el-dialog v-model="newSlotVisible" title="新增公式位" width="480px" append-to-body destroy-on-close>
    <el-form label-width="90px">
      <el-form-item label="公式域"><el-select v-model="newSlotDomain" style="width: 100%">
        <el-option v-for="d in detail?.domains || []" :key="d" :value="d" :label="domainLabel(d)" />
      </el-select></el-form-item>
      <el-form-item label="公式位"><el-input v-model="newSlotKey" maxlength="300" placeholder="请输入唯一公式位" /></el-form-item>
      <el-form-item label="显示名称"><el-input v-model="newSlotLabel" maxlength="300" placeholder="可选，默认使用公式位" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="newSlotVisible = false">取消</el-button>
      <el-button type="primary" data-testid="ftd-add-slot-next" @click="beginNewSlot">下一步填写定义</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { confirmDelete, confirmDangerous } from '@/utils/confirm'
import FormulaDefinitionEditDialog from './FormulaDefinitionEditDialog.vue'
import FormulaPublishPreviewDialog from './FormulaPublishPreviewDialog.vue'
import {
  SHARE_SCOPE_OPTIONS, definitionText, formulaErrorText, formulaSettingsApi, newRequestId, scopeLabel,
  type ConflictChoice, type Decisions, type Definition, type FormulaDomainInfo, type ShareScope, type SyncPreview,
  type TemplateDetail, type TemplateDiff, type TemplateGlobalHint, type TemplateSubscriber, type TemplateVersion,
} from '@/composables/formula/useFormulaSettings'

defineOptions({ name: 'FormulaTemplateDetailDrawer' })

const props = withDefaults(defineProps<{
  modelValue: boolean
  templateId: string
  domains: FormulaDomainInfo[]
  isAdmin?: boolean
}>(), { isAdmin: false })
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; changed: [] }>()

const TEMPLATE_CHOICES: ReadonlyArray<{ value: ConflictChoice; label: string }> = [
  { value: 'adopt', label: '采用模板新版' }, { value: 'keep', label: '保留项目' }, { value: 'ask', label: '交项目确认' },
]

const router = useRouter()
const visible = computed({ get: () => props.modelValue, set: (v: boolean) => emit('update:modelValue', v) })
const detail = ref<TemplateDetail | null>(null)
const versions = ref<TemplateVersion[]>([])
const subscribers = ref<TemplateSubscriber[]>([])
const loading = ref(false)
const tab = ref('defs')
const activeDomain = ref('')
/** 暂存的改动：`{域|公式位 → 新定义（null = 移除）}` */
const staged = reactive(new Map<string, { domain: string; slot_key: string; label: string; definition: Definition | null }>())
const stagedCount = computed(() => staged.size)
const editing = ref<{ slot_key: string; label: string; definition: Definition | null } | null>(null)
const editVisible = ref(false)
const preview = ref<SyncPreview | null>(null)
const previewVisible = ref(false)
const previewLoading = ref(false)
const previewKind = ref<'publish' | 'promote' | 'rollback'>('publish')
const rollbackVersion = ref<number | null>(null)
const diff = ref<TemplateDiff | null>(null)
const diffVisible = ref(false)
const diffLoading = ref(false)
const diffVersion = ref<number | null>(null)
const newSlotVisible = ref(false)
const newSlotDomain = ref('')
const newSlotKey = ref('')
const newSlotLabel = ref('')
const promoting = ref('')
let promoteDomain = ''
let requestId = ''

const hints = computed<TemplateGlobalHint[]>(() => detail.value?.global_hints || [])
const previewTitle = computed(() => {
  if (previewKind.value === 'publish') return `发布模板新版本 v${(detail.value?.version || 0) + 1}：订阅项目影响预览`
  if (previewKind.value === 'rollback') return `回滚到 v${rollbackVersion.value || ''} 并发布新版本：订阅项目影响预览`
  return '设为全局：发布前影响预览'
})
const domainRows = computed(() => (detail.value?.definitions[activeDomain.value] || []).map((r) => {
  const s = staged.get(`${activeDomain.value}|${r.slot_key}`)
  return s ? { ...r, definition: s.definition, staged: true } : { ...r, staged: false }
}))

function domainLabel(key: string): string {
  return props.domains.find((d) => d.key === key)?.label || key
}
function fieldsOf(key: string): { exec: string[]; desc: string[] } {
  const d = props.domains.find((x) => x.key === key)
  return { exec: d?.exec_fields || ['formula'], desc: d?.desc_fields || [] }
}
function fmtTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString('zh-CN', { hour12: false }) : '—'
}
function clearStaged() { staged.clear() }

function openNewSlot() {
  newSlotDomain.value = activeDomain.value || detail.value?.domains[0] || ''
  newSlotKey.value = ''
  newSlotLabel.value = ''
  newSlotVisible.value = true
}

function beginNewSlot() {
  const domain = newSlotDomain.value
  const slotKey = newSlotKey.value.trim()
  if (!domain || !slotKey) {
    ElMessage.warning('请填写公式域和公式位')
    return
  }
  const exists = (detail.value?.definitions[domain] || []).some((row) => row.slot_key === slotKey)
    || staged.has(`${domain}|${slotKey}`)
  if (exists) {
    ElMessage.warning('该公式位已存在，请换一个公式位')
    return
  }
  activeDomain.value = domain
  editing.value = { slot_key: slotKey, label: newSlotLabel.value.trim() || slotKey, definition: {} }
  newSlotVisible.value = false
  editVisible.value = true
}

async function openDiff(row: TemplateVersion) {
  if (!detail.value) return
  diffVersion.value = row.version
  diffLoading.value = true
  try {
    diff.value = await formulaSettingsApi.templateDiff(detail.value.id, {
      from: row.version, to: detail.value.version,
    })
    diffVisible.value = true
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '加载版本差异失败'))
  } finally {
    diffLoading.value = false
  }
}

async function openRollback(row: TemplateVersion) {
  if (!detail.value || row.version >= detail.value.version) return
  previewKind.value = 'rollback'
  rollbackVersion.value = row.version
  previewLoading.value = true
  try {
    preview.value = await formulaSettingsApi.templateRollbackPreview(detail.value.id, {
      target_version: row.version, expected_version: detail.value.version,
    })
    requestId = newRequestId()
    previewVisible.value = true
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '回滚预览失败'))
  } finally {
    previewLoading.value = false
  }
}

async function goSubscribe(row: TemplateSubscriber) {
  if (!detail.value || !row.project_id) return
  try {
    await router.push({
      name: 'ProjectDashboard', params: { projectId: row.project_id },
      query: {
        formulaTemplateId: detail.value.id, formulaAction: 'subscribe', formulaDomain: row.domain,
      },
    })
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '打开项目订阅入口失败'))
  }
}

async function load() {
  if (!props.templateId) return
  loading.value = true
  try {
    const d = await formulaSettingsApi.template(props.templateId)
    detail.value = d
    if (!activeDomain.value || !d.domains.includes(activeDomain.value)) activeDomain.value = d.domains[0] || ''
    versions.value = (await formulaSettingsApi.templateVersions(props.templateId))?.items || []
    subscribers.value = d.can_manage ? (await formulaSettingsApi.templateSubscribers(props.templateId))?.items || [] : []
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '加载模板失败'))
  } finally {
    loading.value = false
  }
}

watch(() => [props.modelValue, props.templateId] as const, ([open]) => {
  if (!open) return
  staged.clear()
  tab.value = 'defs'
  activeDomain.value = ''
  void load()
}, { immediate: true })

function openEdit(row: { slot_key: string; label: string; definition: Definition | null }) {
  editing.value = row
  editVisible.value = true
}
function onEditSave(definition: Definition) {
  if (!editing.value) return
  const { slot_key, label } = editing.value
  staged.set(`${activeDomain.value}|${slot_key}`, { domain: activeDomain.value, slot_key, label, definition })
}
function stageDelete(row: { slot_key: string; label: string }) {
  staged.set(`${activeDomain.value}|${row.slot_key}`, { domain: activeDomain.value, slot_key: row.slot_key, label: row.label, definition: null })
}
function mergeHint(h: TemplateGlobalHint) {
  staged.set(`${h.domain}|${h.slot_key}`, { domain: h.domain, slot_key: h.slot_key, label: h.label, definition: h.global_definition })
}
function mergeAll() {
  for (const h of hints.value) mergeHint(h)
  ElMessage.info(`已暂存 ${hints.value.length} 处，点「发布新版本」预览订阅项目的影响后发布`)
}

function stagedChanges() {
  return [...staged.values()].map(({ domain, slot_key, definition }) => ({ domain, slot_key, definition }))
}

async function onPublishPreview() {
  if (!detail.value || !staged.size) return
  previewKind.value = 'publish'
  previewLoading.value = true
  try {
    preview.value = await formulaSettingsApi.templatePublishPreview(detail.value.id, {
      expected_version: detail.value.version, changes: stagedChanges(),
    })
    requestId = newRequestId()
    previewVisible.value = true
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '发布预览失败'))
  } finally {
    previewLoading.value = false
  }
}

async function onPromote(domain: string) {
  if (!detail.value) return
  if (!props.isAdmin) {
    try {
      await confirmDangerous({
        title: '提交为全局候选',
        message: `把模板「${detail.value.name}」的${domainLabel(domain)}提交给管理员审核，通过后发布到使用该准则的全部项目。`,
        confirmText: '提交候选',
      })
    } catch { return }
    promoting.value = domain
    try {
      await formulaSettingsApi.templatePromote(detail.value.id, { domain, request_id: newRequestId() })
      ElMessage.success('已提交为全局候选，管理员审核通过后发布')
    } catch (e: any) {
      ElMessage.error(formulaErrorText(e, '提交候选失败'))
    } finally {
      promoting.value = ''
    }
    return
  }
  previewKind.value = 'promote'
  promoteDomain = domain
  promoting.value = domain
  try {
    preview.value = await formulaSettingsApi.templatePromotePreview(detail.value.id, { domain })
    requestId = newRequestId()
    previewVisible.value = true
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '设为全局预览失败'))
  } finally {
    promoting.value = ''
  }
}

async function onSubmitPreview(payload: { decisions: Decisions; note: string }): Promise<boolean> {
  if (!detail.value) return false
  try {
    if (previewKind.value === 'publish') {
      const r = await formulaSettingsApi.templatePublish(detail.value.id, {
        expected_version: detail.value.version, changes: stagedChanges(), decisions: payload.decisions,
        request_id: requestId || newRequestId(), note: payload.note || undefined,
      })
      ElMessage.success(`已发布 v${r?.version ?? detail.value.version + 1}，订阅项目按所选处理`)
      staged.clear()
    } else if (previewKind.value === 'rollback' && rollbackVersion.value !== null) {
      const r = await formulaSettingsApi.templateRollback(detail.value.id, {
        target_version: rollbackVersion.value, expected_version: detail.value.version,
        decisions: payload.decisions, request_id: requestId || newRequestId(), note: payload.note || undefined,
      })
      ElMessage.success(`已回滚到 v${rollbackVersion.value}，并发布新版本 v${r?.version ?? detail.value.version + 1}`)
      rollbackVersion.value = null
    } else {
      await formulaSettingsApi.templatePromote(detail.value.id, {
        domain: promoteDomain, decisions: payload.decisions, request_id: requestId || newRequestId(),
        note: payload.note || undefined,
      })
      ElMessage.success('已设为全局并发布')
    }
    emit('changed')
    await load()
    return true
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e,
      previewKind.value === 'publish' ? '发布失败' : previewKind.value === 'rollback' ? '回滚失败' : '设为全局失败'))
    return false
  }
}

async function onDelete() {
  if (!detail.value) return
  try { await confirmDelete(`模板「${detail.value.name}」`) } catch { return }
  try {
    await formulaSettingsApi.deleteTemplate(detail.value.id, detail.value.version)
    ElMessage.success('模板已删除')
    emit('changed')
    visible.value = false
  } catch (e: any) {
    if (e?.response?.status === 409 || e?.response?.status === 428) {
      ElMessage.warning(formulaErrorText(e, '模板已被修改，请刷新后重试'))
      await load()
      return
    }
    ElMessage.error(formulaErrorText(e, '删除模板失败'))
  }
}

// ── 改名 / 共享范围 ──
const metaVisible = ref(false)
const metaSaving = ref(false)
const metaFormRef = ref<FormInstance>()
const meta = reactive({ name: '', description: '', share_scope: 'personal' as ShareScope })
const metaRules: FormRules = { name: [{ required: true, message: '请输入名称', trigger: 'blur' }] }
const metaShareOptions = computed(() => SHARE_SCOPE_OPTIONS.filter((o) => (o.value !== 'firm' || props.isAdmin)
  && ((o.value !== 'team' && o.value !== 'group') || !!detail.value?.owner_project_id)))

function openMeta() {
  if (!detail.value) return
  Object.assign(meta, { name: detail.value.name, description: detail.value.description || '', share_scope: detail.value.share_scope })
  metaVisible.value = true
}
async function onMetaSave() {
  if (!detail.value || !(await metaFormRef.value?.validate().catch(() => false))) return
  metaSaving.value = true
  try {
    detail.value = await formulaSettingsApi.updateTemplate(detail.value.id, {
      name: meta.name.trim(), description: meta.description.trim() || null, share_scope: meta.share_scope,
    })
    ElMessage.success('已保存')
    metaVisible.value = false
    emit('changed')
  } catch (e: any) {
    ElMessage.error(formulaErrorText(e, '保存失败'))
  } finally {
    metaSaving.value = false
  }
}
</script>

<style scoped>
.gt-ftd { min-height: 200px; }
.gt-ftd-gap { margin-bottom: 10px; }
.gt-ftd-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
.gt-ftd-definition-bar { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.gt-ftd-diff-summary { margin-bottom: 8px; color: var(--gt-color-text-secondary); }
.gt-ftd-spacer { flex: 1; }
.gt-ftd-code { font-size: var(--gt-font-size-xs); word-break: break-all; white-space: normal; }
.gt-ftd-new { color: var(--gt-color-primary); }
</style>
