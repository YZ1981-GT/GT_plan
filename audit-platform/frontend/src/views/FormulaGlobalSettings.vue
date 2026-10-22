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
          <el-select v-model="scope" size="small" style="width: 180px" data-testid="fgs-scope" @change="loadSlots">
            <el-option v-for="s in currentDomain?.scopes || []" :key="s.value" :value="s.value" :label="s.label" />
          </el-select>
          <el-input v-model="keyword" size="small" clearable placeholder="搜索公式位 / 公式" style="width: 220px" />
          <el-button size="small" :loading="loading" @click="loadSlots">刷新</el-button>
          <span class="gt-fgs-spacer" />
          <template v-if="isAdmin">
            <span class="gt-fgs-muted">待发布 {{ staged.size }} 处</span>
            <el-button size="small" :disabled="!staged.size" @click="staged.clear()">清空</el-button>
            <el-button size="small" type="primary" :disabled="!staged.size" :loading="previewLoading"
              data-testid="fgs-preview" @click="onPreview">预览并发布</el-button>
          </template>
        </div>
        <el-alert v-if="currentDomain && !currentDomain.wired" type="warning" :closable="false" show-icon class="gt-fgs-gap"
          title="该公式域尚未接入运行时：改动会保存，但暂不参与计算。" />
        <el-table v-loading="loading" :data="filteredSlots" size="small" border max-height="calc(100vh - 330px)"
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

    <FormulaDefinitionEditDialog v-model="editVisible" :title="`编辑全局公式：${editing?.label || ''}`"
      :exec-fields="currentDomain?.exec_fields || ['formula']" :desc-fields="currentDomain?.desc_fields || []"
      :definition="editing ? displayDefinition(editing) : null" @save="onStage" />
    <FormulaPublishPreviewDialog v-model="previewVisible" :preview="preview" :loading="previewLoading"
      :title="`发布全局公式：${currentDomain?.label || ''} · ${scopeLabel(scope)}`" :submit="onPublish"
      :conflict-options="GLOBAL_CHOICES" new-label="新全局" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import FormulaDefinitionEditDialog from '@/components/formula/settings/FormulaDefinitionEditDialog.vue'
import FormulaPublishPreviewDialog from '@/components/formula/settings/FormulaPublishPreviewDialog.vue'
import FormulaPublishRecords from '@/components/formula/settings/FormulaPublishRecords.vue'
import FormulaTemplateManager from '@/components/formula/settings/FormulaTemplateManager.vue'
import FormulaCheckCatalog from '@/components/formula/settings/FormulaCheckCatalog.vue'
import {
  definitionText, formulaSettingsApi, isPresetSlot, newRequestId, scopeLabel, showFormulaError,
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
const editing = ref<GlobalSlot | null>(null)
const editVisible = ref(false)
const preview = ref<SyncPreview | null>(null)
const previewVisible = ref(false)
const previewLoading = ref(false)
const recordsRef = ref<InstanceType<typeof FormulaPublishRecords> | null>(null)
let requestId = ''

const currentDomain = computed(() => domains.value.find((d) => d.key === domainKey.value) || null)
const filteredSlots = computed(() => {
  const kw = keyword.value.trim()
  if (!kw) return slots.value
  return slots.value.filter((s) => s.label.includes(kw) || s.slot_key.includes(kw)
    || definitionText(s.definition, s.structure).includes(kw))
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

async function loadSlots() {
  if (!domainKey.value || !scope.value) { slots.value = []; return }
  loading.value = true
  try {
    slots.value = (await formulaSettingsApi.global(domainKey.value, scope.value))?.slots || []
  } catch (e: any) {
    slots.value = []
    showFormulaError(e, '加载全局公式失败')
  } finally {
    loading.value = false
  }
}

async function onDomainChange() {
  if (staged.size) {
    ElMessage.warning(`切换公式域已放弃 ${staged.size} 处未发布的暂存`)
    staged.clear()
  }
  pickScope()
  await loadSlots()
}

function openEdit(row: GlobalSlot) {
  editing.value = row
  editVisible.value = true
}
function onStage(definition: Definition) {
  const row = editing.value
  if (!row) return
  staged.set(row.slot_key, {
    slot_key: row.slot_key, definition, label: row.label,
    // 带当前版本做并发校验；只有系统预设、尚无全局行的公式位接口给的版本就是 null（= 新建全局行）
    expected_version: row.version,
    structure: row.structure || null,
  })
}
function stageDelete(row: GlobalSlot) {
  staged.set(row.slot_key, { slot_key: row.slot_key, definition: null, label: row.label, expected_version: row.version })
  ElMessage.info(`已暂存删除「${row.label}」，预览并发布后生效（有系统预设的会回到预设）`)
}

async function onPreview() {
  if (!staged.size) return
  previewLoading.value = true
  try {
    preview.value = await formulaSettingsApi.previewGlobal(domainKey.value, { scope: scope.value, changes: [...staged.values()] })
    requestId = newRequestId()
    previewVisible.value = true
  } catch (e: any) {
    showFormulaError(e, '预览影响失败')
  } finally {
    previewLoading.value = false
  }
}

async function onPublish(payload: { decisions: Decisions; note: string }): Promise<boolean> {
  try {
    const result = await formulaSettingsApi.publishGlobal(domainKey.value, {
      scope: scope.value, changes: [...staged.values()], decisions: payload.decisions,
      request_id: requestId || newRequestId(), note: payload.note || undefined,
    })
    const pending = result?.summary?.pending_total || 0
    ElMessage.success(`已发布：${result?.changed_project_count ?? 0} 个项目的有效公式已更新`
      + (pending ? `，${pending} 处交项目确认` : ''))
    staged.clear()
    await loadSlots()
    void recordsRef.value?.load()
    return true
  } catch (e: any) {
    showFormulaError(e, '发布失败')
    return false
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
</style>
