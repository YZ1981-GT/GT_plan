<!--
  全局公式设置（spec formula-global-settings-sync，design §11 / §16.6，R2 / R3 / R4 / R13）。
  - 全局公式：按公式域 + 作用范围查看全局定义（无全局时显示系统预设）；管理员编辑后统一「预览并发布」：
    先看影响（各分类计数、受影响项目、冲突三方对比），逐项目应用 / 暂缓、逐条冲突决策后发布；
  - 发布记录：变更、发布人、时间、各分类计数；全局候选由管理员预览后通过或驳回；
  - 公式模板：可见模板列表与详情（发布新版本、并入全局、设为全局、删除）；
  - 校对规则目录：平台各处校对 / 勾稽 / 质控规则的只读目录（spec formula-governance-coverage-closure R3）。
  非管理员只读（项目侧调整走公式管理中心的本项目适配）。路由参数 `?tab=&domain=&scope=&source=` 可直达。
-->
<template>
  <div class="gt-fgs gt-fade-in">
    <GtPageHeader title="全局公式设置" :show-back="true" back-mode="history" />
    <el-alert v-if="!isAdmin" type="info" :closable="false" show-icon class="gt-fgs-gap"
      title="只读：全局公式仅管理员可修改。项目里可调整本项目公式，保存后可「提交为全局候选」由管理员审核。" />
    <el-tabs v-model="tab">
      <el-tab-pane label="全局公式" name="global">
        <div class="gt-fgs-bar">
          <el-select v-model="domainKey" size="small" style="width: 200px" data-testid="fgs-domain" @change="onDomainChange">
            <el-option v-for="d in domains" :key="d.key" :value="d.key" :label="d.label" />
          </el-select>
          <el-select v-model="scope" size="small" style="width: 180px" data-testid="fgs-scope" @change="onScopeChange">
            <el-option v-for="s in currentDomain?.scopes || []" :key="s.value" :value="s.value" :label="s.label" />
          </el-select>
          <!-- spec formula-management-repair-closure R5：按报表类型 / 底稿编码 / 附注章节 / 科目大类分组筛选 -->
          <el-select v-model="groupKey" size="small" clearable filterable placeholder="全部分组" style="width: 200px"
            data-testid="fgs-group">
            <el-option v-for="g in groupOptions" :key="g.value" :value="g.value" :label="`${g.label}（${g.count}）`" />
          </el-select>
          <el-input v-model="keyword" size="small" clearable placeholder="搜索公式位 / 公式" style="width: 220px" />
          <el-button size="small" :loading="loading" @click="loadSlots">刷新</el-button>
          <span class="gt-fgs-spacer" />
          <template v-if="isAdmin">
            <span class="gt-fgs-muted">待发布 {{ staged.size }} 处</span>
            <el-button size="small" :disabled="!staged.size" data-testid="fgs-clear" @click="clearStaged">清空</el-button>
            <el-button size="small" type="primary" :disabled="!staged.size" :loading="previewLoading"
              data-testid="fgs-preview" @click="onPreview">预览并发布</el-button>
          </template>
        </div>
        <el-alert v-if="notWiredText" type="warning" :closable="false" show-icon class="gt-fgs-gap"
          data-testid="fgs-not-wired" :title="notWiredText" />
        <el-table v-loading="loading" :data="pagedSlots" size="small" border max-height="calc(100vh - 370px)"
          row-key="slot_key" empty-text="该作用范围下暂无公式">
          <el-table-column prop="label" label="公式位" min-width="240" show-overflow-tooltip />
          <el-table-column label="定义" min-width="320">
            <template #default="{ row }">
              <el-tag v-if="staged.has(row.slot_key)" size="small" type="warning">已暂存</el-tag>
              <code class="gt-fgs-code">{{ definitionText(displayDefinition(row), row.structure) }}</code>
            </template>
          </el-table-column>
          <el-table-column label="层级" width="90" align="center">
            <template #default="{ row }">
              <el-tag size="small" effect="plain" :type="isPresetSlot(row) ? 'info' : 'primary'">{{ isPresetSlot(row) ? '系统预设' : '全局' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="版本" width="70" align="center">
            <template #default="{ row }">{{ row.version ?? '—' }}</template>
          </el-table-column>
          <el-table-column v-if="isAdmin" label="操作" width="110" align="center">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
              <el-button v-if="!isPresetSlot(row)" link type="danger" size="small" @click="stageDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="filteredSlots.length > PAGE_SIZE" class="gt-pagination gt-fgs-pager">
          <el-pagination v-model:current-page="page" :page-size="PAGE_SIZE" :total="filteredSlots.length"
            layout="total, prev, pager, next" background small data-testid="fgs-pager" />
        </div>
      </el-tab-pane>
      <el-tab-pane label="发布记录" name="records" lazy>
        <FormulaPublishRecords ref="recordsRef" :domains="domains" :is-admin="isAdmin" @published="loadSlots" />
      </el-tab-pane>
      <el-tab-pane label="公式模板" name="templates" lazy>
        <FormulaTemplateManager :domains="domains" :is-admin="isAdmin" />
      </el-tab-pane>
      <el-tab-pane label="校对规则目录" name="checks" lazy>
        <FormulaCheckCatalog :initial-source="String(route.query.source || '')" />
      </el-tab-pane>
    </el-tabs>

    <FormulaDefinitionEditDialog v-if="editSession" :key="editSession.id" :model-value="editVisible"
      :title="`编辑全局公式：${editSession.row.label || ''}`"
      :exec-fields="currentDomain?.exec_fields || ['formula']" :desc-fields="currentDomain?.desc_fields || []"
      :definition="displayDefinition(editSession.row)"
      v-on="{ save: onStage, 'update:modelValue': editSession.setVisible }" />
    <FormulaPublishPreviewDialog v-if="previewSession" :key="previewSession.snapshot.requestId"
      :model-value="previewVisible" :preview="preview" :loading="previewLoading"
      :title="previewSession.title" :submit="onPublish"
      v-on="{ 'update:modelValue': previewSession.setVisible }" :conflict-options="GLOBAL_CHOICES" new-label="新全局" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import FormulaDefinitionEditDialog from '@/components/formula/settings/FormulaDefinitionEditDialog.vue'
import FormulaPublishPreviewDialog from '@/components/formula/settings/FormulaPublishPreviewDialog.vue'
import FormulaPublishRecords from '@/components/formula/settings/FormulaPublishRecords.vue'
import FormulaTemplateManager from '@/components/formula/settings/FormulaTemplateManager.vue'
import FormulaCheckCatalog from '@/components/formula/settings/FormulaCheckCatalog.vue'
import {
  definitionText, domainNotWiredText, formulaSettingsApi, isPresetSlot, newRequestId, scopeLabel, showFormulaError,
  slotGroupKey, slotGroupLabel,
  type ConflictChoice, type Decisions, type Definition, type FormulaDomainInfo, type GlobalSlot, type SlotChange,
  type SyncPreview,
} from '@/composables/formula/useFormulaSettings'

defineOptions({ name: 'FormulaGlobalSettings' })

const GLOBAL_CHOICES: ReadonlyArray<{ value: ConflictChoice; label: string }> = [
  { value: 'adopt', label: '采用新全局' }, { value: 'keep', label: '保留项目' }, { value: 'ask', label: '交项目确认' },
]

const route = useRoute()
const tab = ref(String(route.query.tab || 'global'))
const domains = ref<FormulaDomainInfo[]>([])
const isAdmin = ref(false)
const domainKey = ref(String(route.query.domain || 'report'))
const scope = ref(String(route.query.scope || ''))
const slots = ref<GlobalSlot[]>([])
const loading = ref(false)
const keyword = ref('')
/** 暂存的全局改动：`{公式位 → 新定义（null = 删除）}`，发布前统一预览 */
const staged = reactive(new Map<string, SlotChange>())
type Context = { domain: string; scope: string; generation: number }
type PublishPayload = { decisions: Decisions; note: string }
type PublishSnapshot = Context & { revision: number; changes: SlotChange[]; requestId: string }
const editSession = ref<{
  id: number; row: GlobalSlot; save: (definition: Definition) => void; setVisible: (visible: boolean) => void
} | null>(null)
const editVisible = ref(false)
const preview = ref<SyncPreview | null>(null)
const previewSession = ref<{
  snapshot: PublishSnapshot; title: string; submit: (payload: PublishPayload) => Promise<boolean>
  setVisible: (visible: boolean) => void
} | null>(null)
const previewVisible = ref(false)
const previewLoading = ref(false)
// 对外保留处理器，但每次打开都换成绑定该会话的闭包；旧组件持有的回调不会改投新范围。
const onStage = computed(() => editSession.value?.save || (() => {}))
const onPublish = computed(() => previewSession.value?.submit || (async () => false))
const recordsRef = ref<InstanceType<typeof FormulaPublishRecords> | null>(null)
let generation = 0
let stagedRevision = 0
let loadSequence = 0
let previewSequence = 0
let editSequence = 0
let publishing = false

const currentDomain = computed(() => domains.value.find((d) => d.key === domainKey.value) || null)
/** 未接入计算的域：显示后端说明（spec formula-management-repair-closure R3.1） */
const notWiredText = computed(() => domainNotWiredText(currentDomain.value))

// spec formula-management-repair-closure R5：分组筛选 + 分页（报表一个准则就有上千个公式位，原先一张表全铺开）
const PAGE_SIZE = 50
const groupKey = ref('')
const page = ref(1)
const groupOptions = computed(() => {
  const counts = new Map<string, number>()
  for (const s of slots.value) {
    const g = slotGroupKey(domainKey.value, s.slot_key)
    counts.set(g, (counts.get(g) || 0) + 1)
  }
  return [...counts].map(([value, count]) => ({ value, count, label: slotGroupLabel(domainKey.value, value) }))
})
const filteredSlots = computed(() => {
  const kw = keyword.value.trim()
  return slots.value.filter((s) => (!groupKey.value || slotGroupKey(domainKey.value, s.slot_key) === groupKey.value)
    && (!kw || s.label.includes(kw) || s.slot_key.includes(kw) || definitionText(s.definition, s.structure).includes(kw)))
})
const pagedSlots = computed(() => filteredSlots.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))
// 换筛选条件回到第一页；换域 / 作用范围后旧分组可能不存在 ⇒ 清掉
watch([keyword, groupKey], () => { page.value = 1 })
watch(slots, () => {
  if (groupKey.value && !groupOptions.value.some((g) => g.value === groupKey.value)) groupKey.value = ''
  page.value = 1
})

/** 暂存过的显示暂存值（删除显示原值，标签区分） */
function displayDefinition(row: GlobalSlot): Definition | null {
  const s = staged.get(row.slot_key)
  return s && s.definition ? s.definition : row.definition
}

function pickScope() {
  const options = currentDomain.value?.scopes || []
  if (!options.some((o) => o.value === scope.value)) scope.value = options[0]?.value || ''
}

function captureContext(): Context {
  return { domain: domainKey.value, scope: scope.value, generation }
}
function isCurrent(context: Context): boolean {
  return context.generation === generation && context.domain === domainKey.value && context.scope === scope.value
}
/** 定义都是 JSON 载荷，复制以隔离响应式编辑对象。 */
function copyPayload<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}
function invalidatePreview() {
  previewSequence++
  previewLoading.value = false
  previewVisible.value = false
  preview.value = null
  previewSession.value = null
}
function closeEditor() {
  editSequence++
  editVisible.value = false
  editSession.value = null
}
function clearStaged() {
  staged.clear()
  stagedRevision++
  invalidatePreview()
  closeEditor()
}
function resetContext(label: string) {
  generation++
  loadSequence++
  loading.value = false
  slots.value = []
  groupKey.value = ''
  if (staged.size) ElMessage.warning(`切换${label}已放弃 ${staged.size} 处未发布的暂存`)
  clearStaged()
}

async function loadSlots() {
  const context = captureContext()
  const sequence = ++loadSequence
  if (!context.domain || !context.scope) { slots.value = []; loading.value = false; return }
  loading.value = true
  try {
    const data = await formulaSettingsApi.global(context.domain, context.scope)
    if (isCurrent(context) && sequence === loadSequence) slots.value = data?.slots || []
  } catch (e: any) {
    if (!isCurrent(context) || sequence !== loadSequence) return
    slots.value = []
    showFormulaError(e, '加载全局公式失败')
  } finally {
    if (isCurrent(context) && sequence === loadSequence) loading.value = false
  }
}

async function onDomainChange() {
  resetContext('公式域')
  pickScope()
  await loadSlots()
}
async function onScopeChange() {
  resetContext('作用范围')
  await loadSlots()
}

function openEdit(row: GlobalSlot) {
  if (loading.value) return
  invalidatePreview()
  const context = captureContext()
  const id = ++editSequence
  const snapshot = copyPayload(row)
  editSession.value = {
    id, row: snapshot,
    save: (definition) => {
      if (!isCurrent(context) || editSession.value?.id !== id || !editVisible.value) return
      invalidatePreview()
      stagedRevision++
      staged.set(snapshot.slot_key, {
        slot_key: snapshot.slot_key, definition: copyPayload(definition), label: snapshot.label,
        expected_version: snapshot.version, structure: snapshot.structure || null,
      })
      closeEditor()
    },
    setVisible: (visible) => {
      if (editSession.value?.id !== id) return
      if (!visible) closeEditor()
    },
  }
  editVisible.value = true
}
function stageDelete(row: GlobalSlot) {
  if (loading.value) return
  invalidatePreview()
  closeEditor()
  stagedRevision++
  staged.set(row.slot_key, { slot_key: row.slot_key, definition: null, label: row.label, expected_version: row.version })
  ElMessage.info(`已暂存删除「${row.label}」，预览并发布后生效（有系统预设的会回到预设）`)
}

function isSnapshotCurrent(snapshot: PublishSnapshot): boolean {
  return isCurrent(snapshot) && snapshot.revision === stagedRevision
}
async function onPreview() {
  if (!staged.size || publishing) return
  invalidatePreview()
  closeEditor()
  const sequence = previewSequence
  const snapshot: PublishSnapshot = {
    ...captureContext(), revision: stagedRevision, changes: copyPayload([...staged.values()]), requestId: newRequestId(),
  }
  const title = `发布全局公式：${currentDomain.value?.label || ''} · ${scopeLabel(snapshot.scope)}`
  previewLoading.value = true
  try {
    const result = await formulaSettingsApi.previewGlobal(snapshot.domain, {
      scope: snapshot.scope, changes: copyPayload(snapshot.changes),
    })
    if (!isSnapshotCurrent(snapshot) || sequence !== previewSequence) return
    preview.value = result
    previewSession.value = {
      snapshot, title, submit: (payload) => publishSnapshot(snapshot, payload),
      setVisible: (visible) => {
        if (previewSession.value?.snapshot.requestId === snapshot.requestId && !visible) invalidatePreview()
      },
    }
    previewVisible.value = true
  } catch (e: any) {
    if (isSnapshotCurrent(snapshot) && sequence === previewSequence) showFormulaError(e, '预览影响失败')
  } finally {
    if (isSnapshotCurrent(snapshot) && sequence === previewSequence) previewLoading.value = false
  }
}

async function publishSnapshot(snapshot: PublishSnapshot, payload: PublishPayload): Promise<boolean> {
  if (publishing || !isSnapshotCurrent(snapshot) || !previewVisible.value
    || previewSession.value?.snapshot.requestId !== snapshot.requestId) return false
  publishing = true
  try {
    const result = await formulaSettingsApi.publishGlobal(snapshot.domain, {
      scope: snapshot.scope, changes: copyPayload(snapshot.changes), decisions: copyPayload(payload.decisions),
      request_id: snapshot.requestId, note: payload.note || undefined,
    })
    const pending = result?.summary?.pending_total || 0
    ElMessage.success(`已发布：${result?.changed_project_count ?? 0} 个项目的有效公式已更新`
      + (pending ? `，${pending} 处交项目确认` : ''))
    if (isSnapshotCurrent(snapshot)) {
      clearStaged()
      await loadSlots()
    }
    void recordsRef.value?.load()
    return true
  } catch (e: any) {
    if (isSnapshotCurrent(snapshot) && previewSession.value?.snapshot.requestId === snapshot.requestId) {
      if (Number(e?.response?.status ?? e?.status ?? e?.code) === 409) {
        // 旧版本的暂存不可再次发布；重读后由用户重新编辑、预览并决定。
        clearStaged()
        await loadSlots()
      }
      showFormulaError(e, '发布失败')
    }
    return false
  } finally {
    publishing = false
  }
}

onMounted(async () => {
  try {
    const data = await formulaSettingsApi.domains()
    domains.value = data?.domains || []
    isAdmin.value = !!data?.is_admin
  } catch (e: any) {
    showFormulaError(e, '加载公式域失败')
  }
  if (!domains.value.some((d) => d.key === domainKey.value)) domainKey.value = domains.value[0]?.key || 'report'
  pickScope()
  await loadSlots()
})
</script>

<style scoped>
.gt-fgs { padding: 16px 20px; }
.gt-fgs-gap { margin-bottom: 10px; }
.gt-fgs-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.gt-fgs-spacer { flex: 1; }
.gt-fgs-muted { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-fgs-code { font-size: var(--gt-font-size-xs); word-break: break-all; white-space: normal; }
.gt-fgs-pager { margin-top: 8px; display: flex; justify-content: flex-end; }
</style>
