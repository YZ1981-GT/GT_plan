<template>
  <div class="h7-tab-disclosure-soe">
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：按国有企业财务报表附注要求，分产业及具体类别披露生产性生物资产的
        期初 / 增加 / 减少 / 期末账面价值，数据与 H7-1 审定表勾稽一致。
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H7-1" :context-project-id="projectId" /></span>
      <span class="chip-wrap"><GtIndexChip :value="`Note:${noteSectionId}`" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">国有企业版</el-tag>
      <el-button
        size="small"
        type="primary"
        :loading="isSyncing"
        :disabled="isReadonly || !projectId"
        data-testid="h7-disclosure-soe-sync"
        @click="syncToNotes"
      >同步到附注</el-button>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>（1）以成本计量</span>
          <div class="title-actions">
            <el-button size="small" link @click="handleReview('soe-policy')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <H7SoeIndustryTable
        :rows="costRows"
        :is-readonly="isReadonly"
        @change="(i, c, f, v) => onCellChange('cost', i, c, f, v)"
        @add="(i) => onAddCategory('cost', i)"
        @rename="(i, c) => onRenameCategory('cost', i, c)"
        @remove="(i, c) => onRemoveCategory('cost', i, c)"
      />
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>（2）以公允价值计量</span>
          <div class="title-actions">
            <el-button size="small" link @click="handleReview('soe-fair-basis')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <H7SoeIndustryTable
        :rows="fairRows"
        :is-readonly="isReadonly"
        @change="(i, c, f, v) => onCellChange('fair', i, c, f, v)"
        @add="(i) => onAddCategory('fair', i)"
        @rename="(i, c) => onRenameCategory('fair', i, c)"
        @remove="(i, c) => onRemoveCategory('fair', i, c)"
      />
    </el-card>

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
      <summary>编制提示（CAS 5 生物资产准则）</summary>
      <ul>
        <li>行结构 = 4 个产业（一、种植业 / 二、畜牧养殖业 / 三、林业 / 四、水产业）+
          每产业下「其中：N．」具体类别 + 合计；点产业行的「＋ 类别」新增明细。</li>
        <li>期末账面价值 = 期初账面价值 + 本期增加额 − 本期减少额（只读派生）。</li>
        <li>产业行有类别明细时金额 = 类别之和（只读）；无类别明细时可直接填列产业行。</li>
        <li>合计行 = 4 个产业行之和，应与审定表 H7-1 审定数一致。</li>
        <li>关注国有资产保值增值、重大资产处置审批程序合规性。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H7TabDisclosureSoe.vue — H7 生产性生物资产 附注披露（国有企业）
 *
 * 按源模板 `附注披露信息（国有企业）` 重建：两张 5 列表（4 产业 + 可扩类别行 + 合计）。
 * 重建前本组件只有单行只读 `movementRows`，无产业与类别维度、无同步链路。
 *
 * spec: h7-biological-assets-disclosure-rebuild (Task 7)
 */
import { computed, inject, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import GtIndexChip from '../../GtIndexChip.vue'
import H7SoeIndustryTable from './H7SoeIndustryTable.vue'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { useDisclosureNoteAi } from '../../composables/useDisclosureNoteAi'
import {
  H7_SOE_GUIDANCE,
  H7_SOE_INDUSTRIES,
  H7_SOE_KEYS,
  buildSoeDisplayRows,
  createDefaultSoeBlocks,
  nextSoeCategoryId,
  type H7SoeIndustryBlock,
} from '../../composables/h7SoeDisclosureModel'
import type { H7IndustryKey } from '../../composables/h7ListedDisclosureModel'
import {
  H7_NOTE_TEXT_TITLES,
  buildH7SoeSyncPayloads,
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

const noteSectionId = H7_NOTE_SECTION.soe
const isSyncing = ref(false)

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())

const NOTE_KEYS = ['soe-policy', 'soe-fair-basis', 'soe-supplement'] as const
type NoteKey = (typeof NOTE_KEYS)[number]

const SRC_HINT: Record<string, string> = {
  'soe-fair-basis': H7_SOE_GUIDANCE.fairBasis,
  'soe-supplement': `${H7_SOE_GUIDANCE.supplement}${H7_SOE_GUIDANCE.risk}`,
}

const NOTE_ITEM_ID: Record<NoteKey, string> = {
  'soe-policy': H7_SOE_KEYS.notePolicy,
  'soe-fair-basis': H7_SOE_KEYS.noteFairBasis,
  'soe-supplement': H7_SOE_KEYS.noteSupplement,
}

type Mode = 'cost' | 'fair'

const blocks = ref<Record<Mode, H7SoeIndustryBlock[]>>({
  cost: createDefaultSoeBlocks(),
  fair: createDefaultSoeBlocks(),
})
const noteTexts = ref<Record<string, string>>({
  'soe-policy': '', 'soe-fair-basis': '', 'soe-supplement': '',
})

const costRows = computed(() => buildSoeDisplayRows(blocks.value.cost))
const fairRows = computed(() => buildSoeDisplayRows(blocks.value.fair))

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

function parseBlocks(raw: string): H7SoeIndustryBlock[] {
  if (!raw.trim()) return createDefaultSoeBlocks()
  try {
    const v = JSON.parse(raw)
    if (!Array.isArray(v)) return createDefaultSoeBlocks()
    // 反序列化补齐：缺失产业按源模板四类补空块，顺序归一
    return H7_SOE_INDUSTRIES.map((ind) => {
      const hit = v.find((b: any) => b?.key === ind.key)
      return {
        key: ind.key,
        selfAmounts: {
          begin: Number(hit?.selfAmounts?.begin) || 0,
          increase: Number(hit?.selfAmounts?.increase) || 0,
          decrease: Number(hit?.selfAmounts?.decrease) || 0,
        },
        categories: Array.isArray(hit?.categories)
          ? hit.categories.map((c: any) => ({
              id: String(c?.id ?? ''),
              name: String(c?.name ?? ''),
              begin: Number(c?.begin) || 0,
              increase: Number(c?.increase) || 0,
              decrease: Number(c?.decrease) || 0,
            })).filter((c: any) => c.id && c.name)
          : [],
      }
    })
  } catch { return createDefaultSoeBlocks() }
}

function hydrate(): void {
  blocks.value = {
    cost: parseBlocks(readRaw(H7_SOE_KEYS.cost)),
    fair: parseBlocks(readRaw(H7_SOE_KEYS.fair)),
  }
  for (const k of NOTE_KEYS) noteTexts.value[k] = readRaw(NOTE_ITEM_ID[k])
}

async function loadOwn(): Promise<void> {
  try {
    const list: any = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const rows: any[] = Array.isArray(list) ? list : (list?.data ?? [])
    const m = new Map(localResponses.value)
    for (const r of rows) {
      if (String(r?.item_id || '').startsWith('H7-disc-soe')) {
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

function persistMode(mode: Mode): void {
  persist(mode === 'cost' ? H7_SOE_KEYS.cost : H7_SOE_KEYS.fair, blocks.value[mode])
}

function blockOf(mode: Mode, industryKey: string | undefined): H7SoeIndustryBlock | undefined {
  return blocks.value[mode].find((b) => b.key === industryKey)
}

function onCellChange(
  mode: Mode,
  industryKey: string | undefined,
  categoryId: string | undefined,
  field: 'begin' | 'increase' | 'decrease',
  value: number,
): void {
  const block = blockOf(mode, industryKey)
  if (!block) return
  if (categoryId) {
    const cat = block.categories.find((c) => c.id === categoryId)
    if (!cat) return
    cat[field] = value
  } else {
    block.selfAmounts[field] = value
  }
  persistMode(mode)
}

async function onAddCategory(mode: Mode, industryKey: string | undefined): Promise<void> {
  if (props.isReadonly) return
  const block = blockOf(mode, industryKey)
  if (!block) return
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入类别名称（如 苹果树 / 奶牛 / 杉木）', '新增类别明细行',
      { confirmButtonText: '创建', cancelButtonText: '取消' },
    )
    const name = String(value ?? '').trim()
    if (!name) { ElMessage.warning('类别名称不能为空'); return }
    block.categories.push({
      id: nextSoeCategoryId(block, industryKey as H7IndustryKey),
      name,
      begin: 0, increase: 0, decrease: 0,
    })
    persistMode(mode)
  } catch { /* 用户取消 */ }
}

async function onRenameCategory(
  mode: Mode, industryKey: string | undefined, categoryId: string | undefined,
): Promise<void> {
  if (props.isReadonly) return
  const cat = blockOf(mode, industryKey)?.categories.find((c) => c.id === categoryId)
  if (!cat) return
  try {
    const { value } = await ElMessageBox.prompt('请输入类别名称', '修改类别名称', {
      inputValue: cat.name, confirmButtonText: '保存', cancelButtonText: '取消',
    })
    const name = String(value ?? '').trim()
    if (!name) { ElMessage.warning('类别名称不能为空'); return }
    cat.name = name
    persistMode(mode)
  } catch { /* 用户取消 */ }
}

async function onRemoveCategory(
  mode: Mode, industryKey: string | undefined, categoryId: string | undefined,
): Promise<void> {
  if (props.isReadonly) return
  const block = blockOf(mode, industryKey)
  const cat = block?.categories.find((c) => c.id === categoryId)
  if (!block || !cat) return
  try {
    await ElMessageBox.confirm(`确认删除类别明细行「${cat.name}」？`, '删除类别', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch { return }
  block.categories = block.categories.filter((c) => c.id !== categoryId)
  persistMode(mode)
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
    industries: H7_SOE_INDUSTRIES.map((i) => i.shortLabel).join('、'),
  }),
  labelOf: (k) => H7_NOTE_TEXT_TITLES[k] || k,
  openReviewDialog: openReviewDialogFn,
})

function handleReview(key: string): void {
  openReview(key)
}

async function syncToNotes(): Promise<void> {
  if (isSyncing.value || props.isReadonly || !props.projectId || !props.wpId) return
  const payloads = buildH7SoeSyncPayloads(props.wpId, props.applicableStandards || [], {
    cost: blocks.value.cost,
    fair: blocks.value.fair,
    notePolicy: noteTexts.value['soe-policy'] || '',
    noteFairBasis: noteTexts.value['soe-fair-basis'] || '',
    noteSupplement: noteTexts.value['soe-supplement'] || '',
  })
  if (!payloads.length) {
    ElMessage.warning('当前不适用国企附注同步')
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
.h7-tab-disclosure-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
