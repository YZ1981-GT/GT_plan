<template>
  <div class="g7-navbar">
    <div class="g7-navbar__head">
      <span class="g7-navbar__title">{{ title }}</span>
      <el-progress
        class="g7-navbar__progress"
        :percentage="progressPercent"
        :stroke-width="8"
        :show-text="false"
      />
      <span class="g7-navbar__progress-text">已编制 {{ filledCount }}/{{ sheets.length }}</span>
      <span class="g7-navbar__spacer" />
      <el-button size="small" @click="openHandbook('preparation')">📖 编制手册</el-button>
      <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
    </div>

    <div class="g7-navbar__chips">
      <el-tag
        v-for="s in sheets"
        :key="s.code"
        class="g7-navbar__chip"
        :type="chipType(s.code)"
        :effect="s.code === currentCode ? 'dark' : 'plain'"
        size="small"
        @click="onNavigate(s)"
      >
        {{ s.code }} {{ s.shortLabel || s.code }}
        <span v-if="filled.has(s.code)" class="g7-navbar__dot" title="已有编制数据">●</span>
      </el-tag>
    </div>

    <details v-if="workflowHint" class="g7-navbar__hint">
      <summary>编制提示</summary>
      <p>{{ workflowHint }}</p>
    </details>

    <component
      :is="HandbookDialog"
      v-if="handbookVisible"
      v-model="handbookVisible"
      :initial-tab="handbookTab"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * G7SheetNavBar — G7 权益法组 / 子公司组 的底稿导航条 + 编制手册入口。
 *
 * 背景：`g7-long-term-equity-method`（G7-4~G7-17）与 `-subsidiary`（G7-7~G7-18）
 * 两册的源工作簿**没有「底稿目录」sheet**（只有 main 组有），因此这两册在 E1 目录
 * 标准里缺「目录页 / 编制手册 / 编制进度」入口。本组件在两册**每张 HTML sheet 顶部**
 * 提供等效能力，无需新增 sheet（不依赖 DB classification）。
 *
 * 自包含：直接读 `checklist-responses` 判定各 sheet 是否已有编制数据（同 E1TabDirectory
 * 范式），父入口只需传 sheets / currentCode / wpId。
 *
 * 跳转：emit('navigate', sheetName) → 父入口转发 `navigate-sheet` → GtWpRenderer 切 tab。
 */
import { computed, onMounted, ref, watch, defineAsyncComponent } from 'vue'
import { api } from '@/services/apiProxy'

/** 导航条 sheet 项（`<script setup>` 内不可 export，父组件用结构等价的字面量类型即可） */
interface G7NavSheet {
  /** 底稿编码，如 G7-14 */
  code: string
  /** 真实 sheet 名（用于跳转精确匹配），如「权益法测算表G7-14」 */
  sheetName: string
  /** chip 上的短标签 */
  shortLabel?: string
}

const props = defineProps<{
  sheets: G7NavSheet[]
  currentCode: string
  wpId: string
  projectId?: string
  title?: string
  workflowHint?: string
}>()

const emit = defineEmits<{ navigate: [sheetName: string] }>()

const HandbookDialog = defineAsyncComponent(
  () => import('../g7-long-term-equity-main/G7PreparationHandbookDialog.vue'),
)

const title = computed(() => props.title || 'G7 底稿导航')
const filled = ref<Set<string>>(new Set())
const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')

const filledCount = computed(() => props.sheets.filter((s) => filled.value.has(s.code)).length)
const progressPercent = computed(() =>
  props.sheets.length ? Math.round((filledCount.value / props.sheets.length) * 100) : 0,
)

function chipType(code: string): 'primary' | 'success' | 'info' {
  if (code === props.currentCode) return 'primary'
  return filled.value.has(code) ? 'success' : 'info'
}

function onNavigate(s: G7NavSheet): void {
  if (s.code === props.currentCode) return
  emit('navigate', s.sheetName || s.code)
}

function openHandbook(tab: 'preparation' | 'usage'): void {
  handbookTab.value = tab
  handbookVisible.value = true
}

/** 判定某 item 是否有实质内容（空数组/空对象/空串视为未填） */
function hasContent(value: unknown): boolean {
  const text = String(value ?? '').trim()
  if (!text) return false
  return text !== '[]' && text !== '{}' && text !== 'null'
}

/** 扫描 checklist-responses，按 `{code}-` 前缀判定该 sheet 是否已有编制数据 */
async function loadFilled(): Promise<void> {
  if (!props.wpId) return
  try {
    const res: any = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const items: any[] = Array.isArray(res) ? res : (res?.data ?? res?.items ?? [])
    const next = new Set<string>()
    for (const it of items) {
      const itemId = String(it?.item_id || '')
      if (!itemId) continue
      if (!hasContent(it?.conclusion) && !hasContent(it?.remark)) continue
      for (const s of props.sheets) {
        // 前缀需带连字符，避免 G7-1 误命中 G7-14 的 item_id
        if (itemId.startsWith(`${s.code}-`)) next.add(s.code)
      }
    }
    filled.value = next
  } catch {
    /* 状态获取失败静默降级：导航与手册仍可用 */
  }
}

onMounted(loadFilled)
watch(() => props.wpId, loadFilled)
</script>

<style scoped>
.g7-navbar {
  font-size: 13px;
  padding: 8px 12px;
  margin-bottom: 10px;
  background: var(--el-fill-color-lighter);
  border-left: 3px solid var(--el-color-primary);
  border-radius: 6px;
}
.g7-navbar__head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.g7-navbar__title {
  font-weight: 600;
  color: var(--el-color-primary);
}
.g7-navbar__progress {
  width: 140px;
}
.g7-navbar__progress-text {
  color: var(--el-text-color-secondary);
}
.g7-navbar__spacer {
  flex: 1 1 auto;
}
.g7-navbar__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.g7-navbar__chip {
  cursor: pointer;
}
.g7-navbar__dot {
  margin-left: 4px;
  font-size: 10px;
}
.g7-navbar__hint {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.g7-navbar__hint summary {
  cursor: pointer;
}
</style>
