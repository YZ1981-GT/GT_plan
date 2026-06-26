<!--
  GtA112DualChecklist.vue — A1-12 重大事项决定程序核查表（顶层编排）

  双模式渲染：
  - 结构化视图（HTML）：专属卡片式核查表 UI
  - Word编辑（DOCX）：OnlyOffice 在线编辑

  Task 3.1: 顶层编排 shell。子任务 3.2~3.9 填充具体逻辑。
-->
<template>
  <div class="gt-a112-dual-checklist" v-loading="loading">
    <!-- 顶部：模式切换 -->
    <div class="gt-a112-dual-checklist__header">
      <el-segmented
        v-model="activeMode"
        :options="modeOptions"
        size="default"
      />
      <el-button
        v-if="activeMode === 'docx'"
        size="small"
        :icon="FullScreen"
        @click="isFullscreen = !isFullscreen"
      >
        {{ isFullscreen ? '退出全屏' : '全屏编辑' }}
      </el-button>
    </div>

    <!-- HTML 结构化视图 -->
    <div v-if="activeMode === 'html'" class="gt-a112-dual-checklist__html-view">
      <!-- Task 3.2: 头部信息卡 -->
      <div class="gt-a112-dual-checklist__section">
        <el-skeleton v-if="!checklistData" :rows="3" animated />
        <el-card v-else class="gt-a112-dual-checklist__header-card" shadow="never">
          <el-descriptions :column="2" border size="default">
            <el-descriptions-item label="被审计单位">
              {{ effectiveHeader.entity_name || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="截止日">
              {{ effectiveHeader.period_end || '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="业务分类">
              <el-radio-group
                :model-value="effectiveHeader.business_class || ''"
                :disabled="props.readonly"
                @change="(val: string) => onHeaderFieldChange('business_class', val as 'A' | 'B' | 'C')"
              >
                <el-radio value="A">A</el-radio>
                <el-radio value="B">B</el-radio>
                <el-radio value="C">C</el-radio>
              </el-radio-group>
            </el-descriptions-item>
            <el-descriptions-item label="首次承接">
              <el-radio-group
                :model-value="effectiveHeader.is_first_engagement == null ? '' : String(effectiveHeader.is_first_engagement)"
                :disabled="props.readonly"
                @change="(val: string) => onHeaderFieldChange('is_first_engagement', val === 'true')"
              >
                <el-radio value="true">是</el-radio>
                <el-radio value="false">否</el-radio>
              </el-radio-group>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </div>

      <!-- Task 3.3: 进度汇总条 -->
      <div class="gt-a112-dual-checklist__section">
        <div class="gt-a112-dual-checklist__progress">
          <div class="gt-a112-dual-checklist__progress-stats">
            <span class="gt-a112-dual-checklist__stat gt-a112-dual-checklist__stat--applicable">
              <span class="gt-a112-dual-checklist__stat-dot" />
              适用 {{ progressStats.applicable }} 项
            </span>
            <span class="gt-a112-dual-checklist__stat gt-a112-dual-checklist__stat--not-applicable">
              <span class="gt-a112-dual-checklist__stat-dot" />
              不适用 {{ progressStats.notApplicable }} 项
            </span>
            <span class="gt-a112-dual-checklist__stat gt-a112-dual-checklist__stat--unmarked">
              <span class="gt-a112-dual-checklist__stat-dot" />
              未标记 {{ progressStats.unmarked }} 项
            </span>
            <span class="gt-a112-dual-checklist__stat gt-a112-dual-checklist__stat--percent">
              {{ progressStats.total > 0 ? progressStats.percent : 0 }}% 完成
            </span>
          </div>
          <el-progress
            :percentage="progressStats.total > 0 ? progressStats.percent : 0"
            :stroke-width="8"
            :show-text="false"
            color="#7c3aed"
          />
        </div>
      </div>

      <!-- Task 3.4: 核查卡片列表 -->
      <div class="gt-a112-dual-checklist__section">
        <div class="gt-a112-dual-checklist__cards">
          <template v-for="category in checklistData?.categories ?? []" :key="category.id">
            <!-- 分组标题 -->
            <div class="gt-a112-dual-checklist__category-heading">
              {{ category.title }}
            </div>

            <!-- 卡片列表 -->
            <div
              v-for="item in category.items"
              :key="item.id"
              :class="[
                'gt-a112-dual-checklist__card',
                getCardStateClass(item.id),
              ]"
            >
              <div class="gt-a112-dual-checklist__card-main">
                <!-- 序号 + 描述 -->
                <div class="gt-a112-dual-checklist__card-desc">
                  <span class="gt-a112-dual-checklist__card-seq">{{ item.seq }}</span>
                  <span class="gt-a112-dual-checklist__card-text">{{ item.description }}</span>
                </div>

                <!-- 适用性 radio -->
                <div class="gt-a112-dual-checklist__card-actions">
                  <el-radio-group
                    :model-value="getItemResponse(item.id).applicable"
                    :disabled="props.readonly"
                    size="small"
                    @change="(val: string) => onApplicableChange(item.id, val as 'yes' | 'no')"
                  >
                    <el-radio value="yes">适用</el-radio>
                    <el-radio value="no">不适用</el-radio>
                  </el-radio-group>
                </div>
              </div>

              <!-- 索引号区域（仅适用时展开） -->
              <div
                v-if="getItemResponse(item.id).applicable === 'yes'"
                class="gt-a112-dual-checklist__card-index"
              >
                <span class="gt-a112-dual-checklist__card-index-label">索引号:</span>
                <div class="gt-a112-dual-checklist__card-index-chips">
                  <GtIndexChip
                    v-for="(ref, idx) in parseRefIndices(getItemResponse(item.id).ref_index)"
                    :key="`${item.id}-ref-${idx}`"
                    :value="ref"
                    :validate="true"
                  />
                </div>
                <el-input
                  v-if="!props.readonly"
                  class="gt-a112-dual-checklist__card-index-input"
                  :model-value="getItemResponse(item.id).ref_index"
                  placeholder="输入索引号，多个用逗号分隔"
                  size="small"
                  clearable
                  @change="(val: string) => onRefIndexChange(item.id, val)"
                />
              </div>
            </div>

            <!-- Task 3.5: 第二类动态添加（仅 allow_custom=true 的分类显示） -->
            <template v-if="category.allow_custom">
              <!-- 自定义事项卡片 -->
              <div
                v-for="ci in responses.custom_items"
                :key="ci.id"
                :class="[
                  'gt-a112-dual-checklist__card',
                  'gt-a112-dual-checklist__card--custom',
                  getCustomItemStateClass(ci),
                ]"
              >
                <div class="gt-a112-dual-checklist__card-main">
                  <!-- 可编辑描述 -->
                  <div class="gt-a112-dual-checklist__card-desc gt-a112-dual-checklist__card-desc--custom">
                    <span class="gt-a112-dual-checklist__card-seq gt-a112-dual-checklist__card-seq--custom">+</span>
                    <el-input
                      v-if="!props.readonly"
                      :model-value="ci.description"
                      placeholder="输入事项描述"
                      size="small"
                      class="gt-a112-dual-checklist__custom-desc-input"
                      @change="(val: string) => onCustomItemDescChange(ci.id, val)"
                    />
                    <span v-else class="gt-a112-dual-checklist__card-text">{{ ci.description || '（未填写）' }}</span>
                  </div>

                  <!-- 适用性 radio + 删除按钮 -->
                  <div class="gt-a112-dual-checklist__card-actions">
                    <el-radio-group
                      :model-value="ci.applicable"
                      :disabled="props.readonly"
                      size="small"
                      @change="(val: string) => onCustomItemApplicableChange(ci.id, val as 'yes' | 'no')"
                    >
                      <el-radio value="yes">适用</el-radio>
                      <el-radio value="no">不适用</el-radio>
                    </el-radio-group>
                    <el-button
                      v-if="!props.readonly"
                      type="danger"
                      size="small"
                      text
                      :icon="Delete"
                      class="gt-a112-dual-checklist__custom-delete"
                      @click="removeCustomItem(ci.id)"
                    />
                  </div>
                </div>

                <!-- 索引号区域（仅适用时展开） -->
                <div
                  v-if="ci.applicable === 'yes'"
                  class="gt-a112-dual-checklist__card-index"
                >
                  <span class="gt-a112-dual-checklist__card-index-label">索引号:</span>
                  <div class="gt-a112-dual-checklist__card-index-chips">
                    <GtIndexChip
                      v-for="(ref, idx) in parseRefIndices(ci.ref_index)"
                      :key="`${ci.id}-ref-${idx}`"
                      :value="ref"
                      :validate="true"
                    />
                  </div>
                  <el-input
                    v-if="!props.readonly"
                    class="gt-a112-dual-checklist__card-index-input"
                    :model-value="ci.ref_index"
                    placeholder="输入索引号，多个用逗号分隔"
                    size="small"
                    clearable
                    @change="(val: string) => onCustomItemRefIndexChange(ci.id, val)"
                  />
                </div>
              </div>

              <!-- 添加事项按钮 -->
              <div v-if="!props.readonly" class="gt-a112-dual-checklist__custom-add">
                <el-button
                  type="primary"
                  plain
                  size="small"
                  :icon="Plus"
                  @click="addCustomItem"
                >
                  添加事项
                </el-button>
              </div>
            </template>
          </template>
        </div>
      </div>

      <!-- Task 3.5: 第二类动态添加 (integrated into card list below category with allow_custom) -->

      <!-- Task 3.6: 签字区 -->
      <div class="gt-a112-dual-checklist__section">
        <el-card class="gt-a112-dual-checklist__signatures-card" shadow="never">
          <template #header>
            <span class="gt-a112-dual-checklist__signatures-title">签字</span>
          </template>
          <div class="gt-a112-dual-checklist__signatures-grid">
            <div
              v-for="sig in signatureList"
              :key="sig.role"
              class="gt-a112-dual-checklist__signature-item"
            >
              <div class="gt-a112-dual-checklist__signature-role">{{ sig.role }}</div>
              <div class="gt-a112-dual-checklist__signature-info">
                <span class="gt-a112-dual-checklist__signature-name">{{ sig.name || '—' }}</span>
                <span class="gt-a112-dual-checklist__signature-date">{{ sig.date || '—' }}</span>
              </div>
            </div>
          </div>
        </el-card>
      </div>
    </div>

    <!-- DOCX Word编辑模式 -->
    <div
      v-else-if="activeMode === 'docx'"
      :class="['gt-a112-dual-checklist__docx-view', { 'gt-a112-dual-checklist__docx-view--fullscreen': isFullscreen }]"
    >
      <div v-if="isFullscreen" class="gt-a112-dual-checklist__fullscreen-toolbar">
        <span class="gt-a112-dual-checklist__fullscreen-title">A1-12 重大事项决定程序核查表</span>
        <el-button size="small" @click="isFullscreen = false">退出全屏</el-button>
      </div>
      <GtOnlyOfficeSheet
        :wp-id="props.wpId"
        sheet-name="A1-12"
        :project-id="projectId"
        :whole-workbook="true"
        :readonly="props.readonly"
        @fallback="onOnlyofficeFallback"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * GtA112DualChecklist — A1-12 重大事项决定程序核查表
 *
 * 顶层编排组件：
 * - 双模式切换（el-segmented）
 * - onMounted 加载 render-config
 * - 管理 checklistData / responses / loading 等全局状态
 */
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, FullScreen } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import GtOnlyOfficeSheet from '@/components/workpaper/GtOnlyOfficeSheet.vue'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface A112ChecklistData {
  header: {
    entity_name: string | null
    period_end: string | null
    business_class: 'A' | 'B' | 'C' | null
    is_first_engagement: boolean | null
  }
  categories: A112Category[]
  signatures: A112Signature[]
}

export interface A112Category {
  id: string
  title: string
  items: A112CheckItem[]
  allow_custom: boolean
}

export interface A112CheckItem {
  id: string
  seq: number
  description: string
  category_tag?: string
}

export interface A112Signature {
  role: string
  name: string | null
  date: string | null
}

export interface A112Responses {
  items: Record<string, A112ItemResponse>
  header: Partial<A112ChecklistData['header']>
  custom_items: A112CustomItem[]
}

export interface A112ItemResponse {
  applicable: 'yes' | 'no' | null
  ref_index: string
}

export interface A112CustomItem {
  id: string
  description: string
  applicable: 'yes' | 'no' | null
  ref_index: string
}

// ─── Component Options ──────────────────────────────────────────────────────

defineOptions({ name: 'GtA112DualChecklist' })

// ─── Props / Emits ──────────────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  wpId: string
  readonly?: boolean
}>(), {
  readonly: false,
})

const emit = defineEmits<{
  save: []
}>()

// ─── Route Context (projectId / year) ───────────────────────────────────────

const route = useRoute()
const projectId = computed(() => (route.params.projectId as string) || '')
const auditYear = computed(() => parseInt(route.query.year as string) || new Date().getFullYear())

// ─── State ──────────────────────────────────────────────────────────────────

const activeMode = ref<'html' | 'docx'>('html')
const checklistData = ref<A112ChecklistData | null>(null)
const responses = ref<A112Responses>({ items: {}, header: {}, custom_items: [] })
const loading = ref(false)
const docxDirty = ref(false)
const isFullscreen = ref(false)

// ─── Mode Options ───────────────────────────────────────────────────────────

const modeOptions = [
  { label: '结构化视图', value: 'html' },
  { label: 'Word编辑', value: 'docx' },
]

// ─── Computed: 头部有效值（responses.header 优先覆盖 checklistData.header）────

const effectiveHeader = computed(() => {
  const base = checklistData.value?.header ?? {
    entity_name: null,
    period_end: null,
    business_class: null,
    is_first_engagement: null,
  }
  return {
    entity_name: responses.value.header.entity_name ?? base.entity_name,
    period_end: responses.value.header.period_end ?? base.period_end,
    business_class: responses.value.header.business_class ?? base.business_class,
    is_first_engagement: responses.value.header.is_first_engagement ?? base.is_first_engagement,
  }
})

// ─── Computed: 进度统计（适用/不适用/未标记 + 百分比）────────────────────────

const progressStats = computed(() => {
  // 总项数 = categories 中所有 items + custom_items
  const categoryItems = checklistData.value?.categories?.flatMap(c => c.items) ?? []
  const customItems = responses.value.custom_items ?? []
  const total = categoryItems.length + customItems.length

  let applicable = 0
  let notApplicable = 0

  // 统计 category items
  for (const item of categoryItems) {
    const resp = responses.value.items[item.id]
    if (resp?.applicable === 'yes') applicable++
    else if (resp?.applicable === 'no') notApplicable++
  }

  // 统计 custom_items
  for (const ci of customItems) {
    if (ci.applicable === 'yes') applicable++
    else if (ci.applicable === 'no') notApplicable++
  }

  const unmarked = total - applicable - notApplicable
  const marked = applicable + notApplicable
  const percent = total > 0 ? Math.round((marked / total) * 100) : 0

  return { applicable, notApplicable, unmarked, total, percent }
})

// ─── Computed: 签字区列表（从 checklistData.signatures 获取 4 角色）────────

const DEFAULT_SIGNATURE_ROLES = ['项目负责经理', '项目合伙人', '质量复核合伙人', '质量控制复核人']

const signatureList = computed<A112Signature[]>(() => {
  if (checklistData.value?.signatures?.length) {
    return checklistData.value.signatures
  }
  // 未加载时返回 4 角色空白占位
  return DEFAULT_SIGNATURE_ROLES.map(role => ({ role, name: null, date: null }))
})

// ─── Header Field Change Handler ────────────────────────────────────────────

function onHeaderFieldChange(field: keyof A112ChecklistData['header'], value: any) {
  responses.value.header = {
    ...responses.value.header,
    [field]: value,
  }
}

// ─── Item Response Helpers ──────────────────────────────────────────────────

/** 获取某个 item 的响应数据，不存在时返回默认值 */
function getItemResponse(itemId: string): A112ItemResponse {
  return responses.value.items[itemId] ?? { applicable: null, ref_index: '' }
}

/** 适用性变更处理 */
function onApplicableChange(itemId: string, value: 'yes' | 'no') {
  if (!responses.value.items[itemId]) {
    responses.value.items[itemId] = { applicable: null, ref_index: '' }
  }
  responses.value.items[itemId].applicable = value
}

/** 索引号变更处理 */
function onRefIndexChange(itemId: string, value: string) {
  if (!responses.value.items[itemId]) {
    responses.value.items[itemId] = { applicable: 'yes', ref_index: '' }
  }
  responses.value.items[itemId].ref_index = value
}

/** 解析 ref_index 字符串为单独的索引号数组（逗号/分号分隔） */
function parseRefIndices(refIndex: string): string[] {
  if (!refIndex) return []
  return refIndex.split(/[,;，；]/).map(s => s.trim()).filter(Boolean)
}

/** 获取卡片状态 CSS class */
function getCardStateClass(itemId: string): string {
  const resp = responses.value.items[itemId]
  if (!resp || resp.applicable === null) return 'gt-a112-dual-checklist__card--unmarked'
  if (resp.applicable === 'yes') return 'gt-a112-dual-checklist__card--applicable'
  return 'gt-a112-dual-checklist__card--not-applicable'
}

// ─── Custom Items (Task 3.5) ────────────────────────────────────────────────

/** 获取自定义事项的卡片状态 CSS class */
function getCustomItemStateClass(ci: A112CustomItem): string {
  if (!ci.applicable) return 'gt-a112-dual-checklist__card--unmarked'
  if (ci.applicable === 'yes') return 'gt-a112-dual-checklist__card--applicable'
  return 'gt-a112-dual-checklist__card--not-applicable'
}

/** 添加自定义事项 */
function addCustomItem() {
  const id = `custom-${Date.now()}`
  responses.value.custom_items.push({
    id,
    description: '',
    applicable: null,
    ref_index: '',
  })
}

/** 删除自定义事项（带确认） */
async function removeCustomItem(id: string) {
  try {
    await ElMessageBox.confirm('确定删除此自定义事项？', '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    const idx = responses.value.custom_items.findIndex(ci => ci.id === id)
    if (idx !== -1) {
      responses.value.custom_items.splice(idx, 1)
    }
  } catch {
    // 用户取消，不做任何操作
  }
}

/** 自定义事项描述变更 */
function onCustomItemDescChange(id: string, val: string) {
  const ci = responses.value.custom_items.find(item => item.id === id)
  if (ci) ci.description = val
}

/** 自定义事项适用性变更 */
function onCustomItemApplicableChange(id: string, val: 'yes' | 'no') {
  const ci = responses.value.custom_items.find(item => item.id === id)
  if (ci) ci.applicable = val
}

/** 自定义事项索引号变更 */
function onCustomItemRefIndexChange(id: string, val: string) {
  const ci = responses.value.custom_items.find(item => item.id === id)
  if (ci) ci.ref_index = val
}

// ─── OnlyOffice Fallback (GtOnlyOfficeSheet 降级时标记) ─────────────────────

function onOnlyofficeFallback() {
  // GtOnlyOfficeSheet 内部降级（健康检查失败/加载失败），标记 docxDirty 以便切回时刷新
  docxDirty.value = true
}

// ─── Data Loading ───────────────────────────────────────────────────────────

async function loadRenderConfig() {
  loading.value = true
  isInitialLoad = true
  try {
    const res = await api.get<any>(`/api/workpapers/${props.wpId}/render-config`)
    // render_a112_dual 返回 htmlData = { checklistData, responses }
    const htmlData = res?.sheets?.[0]?.html_data ?? res?.htmlData ?? res
    if (htmlData?.checklistData) {
      checklistData.value = htmlData.checklistData
    }
    if (htmlData?.responses) {
      responses.value = {
        items: htmlData.responses.items ?? {},
        header: htmlData.responses.header ?? {},
        custom_items: htmlData.responses.custom_items ?? [],
      }
    }
  } catch (e: any) {
    ElMessage.error('加载 A1-12 核查表数据失败')
    console.error('[GtA112DualChecklist] loadRenderConfig failed:', e)
  } finally {
    loading.value = false
    // 延迟一个 tick 清除初始化标记，防止加载数据赋值触发 save
    setTimeout(() => { isInitialLoad = false }, 0)
  }
}

// ─── Mode Switch Sync (Task 3.8 + 3.9) ─────────────────────────────────────

watch(activeMode, async (newMode, oldMode) => {
  // 退出全屏
  if (newMode === 'html') {
    isFullscreen.value = false
  }
  // DOCX→HTML 切回：若 docxDirty 需刷新数据
  if (newMode === 'html' && oldMode === 'docx' && docxDirty.value) {
    docxDirty.value = false
    await loadRenderConfig()
  }
  // 进入 DOCX 模式：标记 dirty 以便切回时刷新（OnlyOffice 可能编辑了内容）
  if (newMode === 'docx') {
    docxDirty.value = true
  }
})

// ─── Auto-Save (Task 3.7): Debounced field_overrides 持久化 ─────────────────

let saveTimer: ReturnType<typeof setTimeout> | null = null
const saving = ref(false)
let isInitialLoad = true

/** 将当前 responses 序列化为 field_overrides 批量保存 */
async function persistResponses(retryCount = 0): Promise<void> {
  if (props.readonly || !projectId.value || !props.wpId) return

  const scope = `a112_checklist:${props.wpId}`
  const year = auditYear.value

  // 构建保存的 payload 数组：每个 item/header/custom_items 各一条
  const calls: Promise<any>[] = []

  // 1. 保存 header overrides
  if (Object.keys(responses.value.header).length > 0) {
    calls.push(
      api.post('/api/workpapers/field-overrides', {
        project_id: projectId.value,
        year,
        scope,
        item_key: 'header',
        field: 'value',
        value: responses.value.header,
      })
    )
  }

  // 2. 保存 items overrides
  for (const [itemId, resp] of Object.entries(responses.value.items)) {
    calls.push(
      api.post('/api/workpapers/field-overrides', {
        project_id: projectId.value,
        year,
        scope,
        item_key: itemId,
        field: 'value',
        value: resp,
      })
    )
  }

  // 3. 保存 custom_items 作为一条记录
  if (responses.value.custom_items.length > 0) {
    calls.push(
      api.post('/api/workpapers/field-overrides', {
        project_id: projectId.value,
        year,
        scope,
        item_key: 'custom_items',
        field: 'value',
        value: responses.value.custom_items,
      })
    )
  }

  if (calls.length === 0) return

  saving.value = true
  try {
    await Promise.all(calls)
    emit('save')
  } catch (e: any) {
    if (retryCount < 2) {
      // 重试（最多 3 次）
      await persistResponses(retryCount + 1)
    } else {
      ElMessage.warning('自动保存失败，请手动保存或刷新页面')
      console.error('[GtA112DualChecklist] persistResponses failed:', e)
    }
  } finally {
    saving.value = false
  }
}

/** Debounced save: 2 秒后触发 */
function scheduleSave() {
  if (props.readonly) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    persistResponses()
  }, 2000)
}

/** 立即 flush 未落盘的保存（页面卸载前） */
function flushPendingSave() {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
    persistResponses()
  }
}

// 深度监听 responses 变更触发 debounced save
watch(responses, () => {
  if (isInitialLoad) return
  scheduleSave()
}, { deep: true })

onBeforeUnmount(() => {
  flushPendingSave()
})

// ─── Lifecycle ──────────────────────────────────────────────────────────────

onMounted(() => {
  loadRenderConfig()
})

// ─── Expose for parent (toolbar delegation) ─────────────────────────────────

defineExpose({
  checklistData,
  responses,
  activeMode,
  saving,
  reload: loadRenderConfig,
  flushPendingSave,
})
</script>

<style scoped>
.gt-a112-dual-checklist {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-a112-dual-checklist__header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.gt-a112-dual-checklist__html-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-a112-dual-checklist__section {
  /* 各区域基本容器 */
}

.gt-a112-dual-checklist__docx-view {
  min-height: calc(100vh - 200px);
  height: calc(100vh - 200px);
  display: flex;
  flex-direction: column;
}

.gt-a112-dual-checklist__docx-view :deep(.gt-onlyoffice-sheet) {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.gt-a112-dual-checklist__docx-view :deep(.gt-onlyoffice-sheet__editor-container) {
  flex: 1;
  height: 100%;
}

.gt-a112-dual-checklist__docx-view :deep(.gt-onlyoffice-sheet__editor-container iframe) {
  width: 100%;
  height: 100% !important;
  min-height: calc(100vh - 260px);
  border: none;
}

/* 全屏模式 */
.gt-a112-dual-checklist__docx-view--fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2000;
  background: #fff;
  padding: 0;
  min-height: unset;
}

.gt-a112-dual-checklist__fullscreen-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: #f5f7fa;
  border-bottom: 1px solid #ebeef5;
}

.gt-a112-dual-checklist__fullscreen-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.gt-a112-dual-checklist__header-card {
  :deep(.el-descriptions__label) {
    width: 100px;
    font-weight: 500;
  }
}

/* ─── 进度汇总条样式 ─── */
.gt-a112-dual-checklist__progress {
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}

.gt-a112-dual-checklist__progress-stats {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 8px;
  font-size: 13px;
}

.gt-a112-dual-checklist__stat {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
}

.gt-a112-dual-checklist__stat-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.gt-a112-dual-checklist__stat--applicable .gt-a112-dual-checklist__stat-dot {
  background-color: #7c3aed;
}

.gt-a112-dual-checklist__stat--applicable {
  color: #7c3aed;
}

.gt-a112-dual-checklist__stat--not-applicable .gt-a112-dual-checklist__stat-dot {
  background-color: #9ca3af;
}

.gt-a112-dual-checklist__stat--not-applicable {
  color: #6b7280;
}

.gt-a112-dual-checklist__stat--unmarked .gt-a112-dual-checklist__stat-dot {
  background-color: #f59e0b;
}

.gt-a112-dual-checklist__stat--unmarked {
  color: #d97706;
}

.gt-a112-dual-checklist__stat--percent {
  margin-left: auto;
  color: #374151;
  font-weight: 600;
}

/* ─── 核查卡片列表样式 ─── */
.gt-a112-dual-checklist__cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.gt-a112-dual-checklist__category-heading {
  margin-top: 12px;
  margin-bottom: 4px;
  padding: 8px 0;
  font-size: 14px;
  font-weight: 600;
  color: #374151;
  border-bottom: 2px solid #7c3aed;
}

.gt-a112-dual-checklist__card {
  border: 1px solid #e5e7eb;
  border-left: 4px solid #d1d5db;
  border-radius: 8px;
  padding: 12px 16px;
  background: #fff;
  transition: all 0.2s ease;
}

/* 未标记：白底灰左边框 */
.gt-a112-dual-checklist__card--unmarked {
  border-left-color: #d1d5db;
}

/* 适用：白底紫左边框+高亮 */
.gt-a112-dual-checklist__card--applicable {
  border-left-color: #7c3aed;
  background: #faf5ff;
}

/* 不适用：白底浅灰+半透明 */
.gt-a112-dual-checklist__card--not-applicable {
  border-left-color: #e5e7eb;
  background: #f9fafb;
  opacity: 0.7;
}

.gt-a112-dual-checklist__card-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.gt-a112-dual-checklist__card-desc {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.gt-a112-dual-checklist__card-seq {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #f3f4f6;
  color: #6b7280;
  font-size: 12px;
  font-weight: 600;
}

.gt-a112-dual-checklist__card--applicable .gt-a112-dual-checklist__card-seq {
  background: #ede9fe;
  color: #7c3aed;
}

.gt-a112-dual-checklist__card-text {
  font-size: 13px;
  line-height: 1.5;
  color: #374151;
}

.gt-a112-dual-checklist__card-actions {
  flex-shrink: 0;
}

/* 索引号区域 */
.gt-a112-dual-checklist__card-index {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #e5e7eb;
  flex-wrap: wrap;
}

.gt-a112-dual-checklist__card-index-label {
  font-size: 12px;
  color: #6b7280;
  flex-shrink: 0;
}

.gt-a112-dual-checklist__card-index-chips {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.gt-a112-dual-checklist__card-index-input {
  max-width: 240px;
}

/* ─── 第二类动态添加样式 ─── */
.gt-a112-dual-checklist__card--custom {
  border-style: dashed;
}

.gt-a112-dual-checklist__card-desc--custom {
  flex: 1;
}

.gt-a112-dual-checklist__card-seq--custom {
  background: #ede9fe;
  color: #7c3aed;
  font-size: 14px;
}

.gt-a112-dual-checklist__custom-desc-input {
  flex: 1;
}

.gt-a112-dual-checklist__custom-delete {
  margin-left: 8px;
}

.gt-a112-dual-checklist__custom-add {
  margin-top: 8px;
  display: flex;
  justify-content: center;
}

/* ─── 签字区样式 ─── */
.gt-a112-dual-checklist__signatures-card {
  :deep(.el-card__header) {
    padding: 12px 16px;
    border-bottom: 1px solid #ebeef5;
  }
}

.gt-a112-dual-checklist__signatures-title {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}

.gt-a112-dual-checklist__signatures-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.gt-a112-dual-checklist__signature-item {
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafafa;
}

.gt-a112-dual-checklist__signature-role {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 6px;
}

.gt-a112-dual-checklist__signature-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.gt-a112-dual-checklist__signature-name {
  font-size: 14px;
  font-weight: 500;
  color: #1f2937;
}

.gt-a112-dual-checklist__signature-date {
  font-size: 12px;
  color: #9ca3af;
}
</style>
