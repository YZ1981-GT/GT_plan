<template>
  <div class="h7-tab-disclosure-listed">
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：按上市公司年报附注要求，分产业、分类别披露生产性生物资产的四层账面变动
        （账面原值 / 累计折旧 / 减值准备 / 账面价值）与公允价值模式变动，数据与 H7-1 审定表勾稽一致。
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H7-1" :context-project-id="projectId" /></span>
      <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">上市公司版</el-tag>
      <el-button
        size="small"
        type="primary"
        :loading="isSyncing"
        :disabled="isReadonly || !projectId"
        data-testid="h7-disclosure-listed-sync"
        @click="syncToNotes"
      >同步到附注</el-button>
    </div>

    <!-- 源模板红字：方法论上下文 -->
    <div class="src-hint">{{ H7_LISTED_GUIDANCE.publicWelfare }}</div>

    <!-- （1）以成本计量 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>（1）以成本计量</span>
          <div class="title-actions">
            <el-button size="small" link :disabled="isReadonly" @click="openAddCategory">＋ 类别列</el-button>
            <el-button size="small" link @click="handleReview('cost')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <H7ListedMovementTable
        :rows="H7_COST_MOVEMENT_ROWS"
        :categories="orderedCategories"
        :map="costMap"
        :is-readonly="isReadonly"
        table-key="cost"
        @cell-change="onCostCell"
        @rename="onRenameCategory"
        @remove="onRemoveCategory"
      />
    </el-card>

    <!-- （2）以公允价值计量 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>（2）以公允价值计量</span>
          <div class="title-actions">
            <el-button size="small" link @click="handleReview('fair')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <H7ListedMovementTable
        :rows="H7_FAIR_MOVEMENT_ROWS"
        :categories="orderedCategories"
        :map="fairMap"
        :is-readonly="isReadonly"
        table-key="fair"
        @cell-change="onFairCell"
        @rename="onRenameCategory"
        @remove="onRemoveCategory"
      />
    </el-card>

    <!-- 文字披露 -->
    <el-card shadow="never" class="block-card">
      <template #header><div class="section-title"><span>文字披露</span></div></template>
      <div v-for="k in NOTE_KEYS" :key="k" class="note-section">
        <div class="note-head">
          <h4>{{ H7_NOTE_TEXT_TITLES[k] }}</h4>
          <div class="title-actions">
            <el-button
              size="small"
              link
              :loading="aiLoadingSection === k"
              :disabled="isReadonly"
              @click="runAi(k)"
            >🤖 AI 辅助</el-button>
            <el-button size="small" link @click="handleReview(k)">💬 复核</el-button>
          </div>
        </div>
        <div v-if="SRC_HINT[k]" class="src-hint">{{ SRC_HINT[k] }}</div>
        <el-input
          :model-value="noteTexts[k]"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 12 }"
          :disabled="isReadonly"
          :placeholder="`请填写${H7_NOTE_TEXT_TITLES[k]}…`"
          @input="(v: string) => onNoteInput(k, v)"
        />
      </div>
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（CAS 5 生物资产准则 / 15 号文）</summary>
      <ul>
        <li>列结构 = 项目 + 4 个产业（种植业 / 畜牧养殖业 / 林业 / 水产业）下的具体类别 + 合计；
          源模板首个类别表头占位为「类别」，请改成实际类别名（如苹果树、奶牛、杉木）。</li>
        <li>各层 期末余额 = 期初余额 + 本期增加金额 − 本期减少金额；小计行 = 其分项之和。</li>
        <li>账面价值 = 账面原值 − 累计折旧 − 减值准备；合计列 = 各类别列之和。</li>
        <li>公允价值表 本期变动 = 加项之和 − 减项之和 + 公允价值变动 + 其他变动；
          期末余额 = 期初余额 + 本期变动。</li>
        <li>「……」行是可扩明细行，用于列示源模板未预置的增减事项，参与所属小计。</li>
        <li>本表账面价值合计应与审定表 H7-1 审定数一致。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H7TabDisclosureListed.vue — H7 生产性生物资产 附注披露（上市公司）
 *
 * 按源模板 `附注披露信息（上市公司）` 重建：两张**列转置 + 两级表头**表
 * （列 = 项目 + 4 产业下的类别列 + 合计；行 = 34 行四层 / 11 行公允价值变动）。
 *
 * 重建前本组件只有单行只读 `movementRows`（原值/折旧/减值），无产业与类别维度，
 * 故 `disclosure-sync-path-buildout` 曾接线后撤回。现已建立完整同步链路。
 *
 * spec: h7-biological-assets-disclosure-rebuild (Task 6)
 */
import { computed, inject, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import H7ListedMovementTable from './H7ListedMovementTable.vue'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { useDisclosureNoteAi } from '../../composables/useDisclosureNoteAi'
import {
  H7_COST_MOVEMENT_ROWS,
  H7_FAIR_MOVEMENT_ROWS,
  H7_INDUSTRIES,
  H7_LISTED_GUIDANCE,
  H7_LISTED_KEYS,
  createDefaultH7Categories,
  emptyMovement,
  nextH7CategoryKey,
  orderH7Categories,
  setCell,
  type H7IndustryKey,
  type H7ListedCategory,
  type MovementCellMap,
} from '../../composables/h7ListedDisclosureModel'
import {
  H7_NOTE_TEXT_TITLES,
  buildH7ListedSyncPayloads,
} from '../../composables/h7DisclosureSyncPayload'
import { H7_NOTE_SECTION } from '../../composables/h7NoteSectionMap'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{ (e: 'save', itemId: string, value: any): void }>()

const noteSectionId = H7_NOTE_SECTION.listed
const isSyncing = ref(false)

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())

const NOTE_KEYS = ['listed-policy', 'listed-impairment', 'listed-supplement'] as const
type NoteKey = (typeof NOTE_KEYS)[number]

const SRC_HINT: Record<string, string> = {
  'listed-impairment': `${H7_LISTED_GUIDANCE.impairment}${H7_LISTED_GUIDANCE.impairmentNote}`,
  'listed-supplement': H7_LISTED_GUIDANCE.supplement,
}

const NOTE_ITEM_ID: Record<NoteKey, string> = {
  'listed-policy': H7_LISTED_KEYS.notePolicy,
  'listed-impairment': H7_LISTED_KEYS.noteImpairment,
  'listed-supplement': H7_LISTED_KEYS.noteSupplement,
}

const categories = ref<H7ListedCategory[]>(createDefaultH7Categories())
const costMap = ref<MovementCellMap>(emptyMovement())
const fairMap = ref<MovementCellMap>(emptyMovement())
const noteTexts = ref<Record<string, string>>({
  'listed-policy': '', 'listed-impairment': '', 'listed-supplement': '',
})

const orderedCategories = computed(() => orderH7Categories(categories.value))

/**
 * 本地镜像（H7 循环既有范式）。
 *
 * 🔴 **不 watch `props.allResponses`**：宿主的 map 是异步加载的，自持久化后宿主
 * 未必同步刷新 → watch 触发时会用**旧值**重新 hydrate，把刚录入的数据覆盖掉。
 */
const localResponses = ref<Map<string, any>>(new Map(props.allResponses ?? []))

function readRaw(itemId: string): string {
  const item = localResponses.value.get(itemId)
  return String(item?.remark ?? item?.conclusion ?? '')
}

function parseJson<T>(raw: string, fallback: T): T {
  if (!raw.trim()) return fallback
  try {
    const v = JSON.parse(raw)
    return (v && typeof v === 'object') ? (v as T) : fallback
  } catch { return fallback }
}

function hydrate(): void {
  const cats = parseJson<H7ListedCategory[]>(readRaw(H7_LISTED_KEYS.categories), [])
  categories.value = Array.isArray(cats) && cats.length ? cats : createDefaultH7Categories()
  costMap.value = parseJson<MovementCellMap>(readRaw(H7_LISTED_KEYS.cost), emptyMovement())
  fairMap.value = parseJson<MovementCellMap>(readRaw(H7_LISTED_KEYS.fair), emptyMovement())
  for (const k of NOTE_KEYS) noteTexts.value[k] = readRaw(NOTE_ITEM_ID[k])
}

async function loadOwn(): Promise<void> {
  try {
    const list: any = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const rows: any[] = Array.isArray(list) ? list : (list?.data ?? [])
    const m = new Map(localResponses.value)
    for (const r of rows) {
      if (String(r?.item_id || '').startsWith('H7-disc-listed')) {
        m.set(r.item_id, { item_id: r.item_id, conclusion: r.conclusion ?? null, remark: r.remark ?? null })
      }
    }
    localResponses.value = m
  } catch { /* 读失败时用 props 镜像兜底 */ }
  hydrate()
}

onMounted(loadOwn)

/**
 * 持久化。
 *
 * 🔴 **自己写库**：H7 宿主 `GtH7BiologicalAssets.vue` 没有任何 `@save` 处理器
 * （该循环全部 Tab 都自持久化）。只 `emit('save')` 会让录入**只存在于内存**、
 * 刷新即丢 —— 本 spec 浏览器实测踩中：自动同步写进了附注，但
 * `checklist_responses` 一条都没有。`emit` 仍保留，供将来接了处理器的宿主用。
 */
async function persist(itemId: string, value: unknown): Promise<void> {
  const remark = typeof value === 'string' ? value : JSON.stringify(value)
  localResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark })
  emit('save', itemId, remark)
  autoSync.scheduleAutoSync(syncToNotes)
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion: null, remark }],
    })
  } catch {
    ElMessage.error('保存失败，请稍后重试')
  }
}

function onCostCell(rowKey: string, colKey: string, value: number): void {
  costMap.value = setCell(costMap.value, rowKey, colKey, value)
  persist(H7_LISTED_KEYS.cost, costMap.value)
}

function onFairCell(rowKey: string, colKey: string, value: number): void {
  fairMap.value = setCell(fairMap.value, rowKey, colKey, value)
  persist(H7_LISTED_KEYS.fair, fairMap.value)
}

function persistCategories(): void {
  persist(H7_LISTED_KEYS.categories, categories.value)
}

async function openAddCategory(): Promise<void> {
  if (props.isReadonly) return
  try {
    const { value: industry } = await ElMessageBox.prompt(
      `请输入所属产业（${H7_INDUSTRIES.map((i) => i.label).join(' / ')}）`,
      '新增类别列',
      { inputValue: H7_INDUSTRIES[0].label, confirmButtonText: '下一步', cancelButtonText: '取消' },
    )
    const ind = H7_INDUSTRIES.find((i) => i.label === String(industry).trim())
    if (!ind) { ElMessage.warning('产业名称须为源模板四类之一'); return }
    const { value: name } = await ElMessageBox.prompt(
      '请输入类别名称（如 苹果树 / 奶牛 / 杉木）', '新增类别列',
      { confirmButtonText: '创建', cancelButtonText: '取消' },
    )
    const label = String(name ?? '').trim()
    if (!label) { ElMessage.warning('类别名称不能为空'); return }
    addCategory(ind.key, label)
  } catch { /* 用户取消 */ }
}

function addCategory(industry: H7IndustryKey, label: string): void {
  const key = nextH7CategoryKey(categories.value, industry)
  categories.value = [...categories.value, { key, label, industry }]
  persistCategories()
}

async function onRenameCategory(key: string): Promise<void> {
  if (props.isReadonly) return
  const cur = categories.value.find((c) => c.key === key)
  if (!cur) return
  try {
    const { value } = await ElMessageBox.prompt('请输入类别名称', '修改类别列名', {
      inputValue: cur.label, confirmButtonText: '保存', cancelButtonText: '取消',
    })
    const label = String(value ?? '').trim()
    if (!label) { ElMessage.warning('类别名称不能为空'); return }
    categories.value = categories.value.map((c) => (c.key === key ? { ...c, label } : c))
    persistCategories()
  } catch { /* 用户取消 */ }
}

async function onRemoveCategory(key: string): Promise<void> {
  if (props.isReadonly) return
  const rest = categories.value.filter((c) => c.key !== key)
  const target = categories.value.find((c) => c.key === key)
  if (!target) return
  if (!rest.some((c) => c.industry === target.industry)) {
    ElMessage.warning('每个产业至少保留一个类别列')
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除类别列「${target.label}」？该列已录金额将一并移除。`, '删除类别列', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch { return }
  categories.value = rest
  // 同步清掉两张表里该列的数据（避免残留在 MovementCellMap 里）
  for (const map of [costMap, fairMap]) {
    const next: MovementCellMap = {}
    for (const [rowKey, cols] of Object.entries(map.value)) {
      const kept: Record<string, number> = {}
      for (const [colKey, v] of Object.entries(cols)) if (colKey !== key) kept[colKey] = v
      next[rowKey] = kept
    }
    map.value = next
  }
  persist(H7_LISTED_KEYS.cost, costMap.value)
  persist(H7_LISTED_KEYS.fair, fairMap.value)
  persistCategories()
}

function onNoteInput(key: NoteKey, v: string): void {
  noteTexts.value[key] = v
  persist(NOTE_ITEM_ID[key], v)
}

// 🔴 `inject` 只能在 setup 顶层调用（写进函数体会在点击时抛 TypeError 被 catch 吞掉）
const openReviewDialogFn = inject<((p: Record<string, unknown>) => void) | null>(
  'openReviewDialog', null,
)

const { aiLoadingSection, runAi, openReview } = useDisclosureNoteAi({
  wpId: () => props.wpId,
  isReadonly: () => props.isReadonly,
  getText: (k) => noteTexts.value[k] || '',
  setText: (k, text) => onNoteInput(k as NoteKey, text),
  buildSectionId: (k) => `H7-disc-${k}`,
  buildContext: (k) => ({
    section_label: H7_NOTE_TEXT_TITLES[k] || k,
    industries: H7_INDUSTRIES.map((i) => i.label).join('、'),
    categories: orderedCategories.value.map((c) => c.label).join('、'),
  }),
  labelOf: (k) => H7_NOTE_TEXT_TITLES[k] || k,
  openReviewDialog: openReviewDialogFn,
})

function handleReview(key: string): void {
  openReview(key)
}

async function syncToNotes(): Promise<void> {
  if (isSyncing.value || props.isReadonly || !props.projectId || !props.wpId) return
  const payloads = buildH7ListedSyncPayloads(props.wpId, props.applicableStandards || [], {
    categories: categories.value,
    cost: costMap.value,
    fair: fairMap.value,
    notePolicy: noteTexts.value['listed-policy'] || '',
    noteImpairment: noteTexts.value['listed-impairment'] || '',
    noteSupplement: noteTexts.value['listed-supplement'] || '',
  })
  if (!payloads.length) {
    ElMessage.warning('当前不适用上市附注同步')
    return
  }
  isSyncing.value = true
  try {
    let rows = 0
    for (const payload of payloads) {
      const result: any = await api.post(
        `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
        payload,
      )
      const data = result?.data ?? result
      rows += Number(data?.rows_synced ?? 0)
    }
    ElMessage.success(`已同步 ${rows} 行到附注「${noteSectionId}」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}
</script>

<style scoped>
.h7-tab-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; margin-left: auto; }
.note-section { margin-top: 18px; }
.note-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.note-head h4 { font-size: 14px; margin: 0; }
.src-hint {
  border-left: 3px solid var(--el-color-warning);
  background: var(--el-color-warning-light-9);
  padding: 6px 10px;
  margin-bottom: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
