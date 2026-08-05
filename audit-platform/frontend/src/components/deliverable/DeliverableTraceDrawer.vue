<template>
  <el-drawer
    :model-value="visible"
    :title="`溯源 — ${title}`"
    size="46%"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <div class="trace-drawer">
      <!-- 章节选择：trace 端点按 section_code 查询，故先取章节清单 -->
      <div class="trace-drawer__bar">
        <span class="trace-drawer__bar-label">章节</span>
        <el-select
          v-model="sectionCode"
          filterable
          allow-create
          default-first-option
          size="small"
          placeholder="选择章节"
          class="trace-drawer__select"
          :disabled="sectionsLoading || !sections.length"
          @change="runTrace"
        >
          <el-option
            v-for="s in sections"
            :key="s.section_code"
            :label="s.is_stale ? `${s.section_code}（已过期）` : s.section_code"
            :value="s.section_code"
          />
        </el-select>
        <el-button
          size="small"
          type="primary"
          :loading="loading"
          :disabled="!sectionCode"
          @click="runTrace"
        >
          溯源
        </el-button>
      </div>

      <el-alert
        v-if="sectionsError"
        type="error"
        :closable="false"
        show-icon
        :title="sectionsError"
        class="trace-drawer__alert"
      />

      <!-- 需求 11.6：无匹配也要给明确原因，不得空白 -->
      <el-alert
        v-else-if="!sectionsLoading && !sections.length"
        type="info"
        :closable="false"
        show-icon
        title="本交付件没有章节锚点，无法逐章节溯源"
        class="trace-drawer__alert"
      >
        锚点在生成交付件时写入。该交付件可能生成于溯源能力上线之前，或属于不按章节组织的类型
        （如财务报表 xlsx）。重新生成后即可溯源。
      </el-alert>

      <el-alert
        v-if="error"
        type="warning"
        :closable="false"
        show-icon
        :title="error"
        class="trace-drawer__alert"
      />

      <el-skeleton v-if="loading" :rows="4" animated />

      <template v-else-if="sectionCode && !error">
        <div v-if="sectionState" class="trace-drawer__state">
          <el-tag v-if="sectionState.is_stale" size="small" type="warning">源数据已变更</el-tag>
          <el-tag v-else size="small" type="success">与生成时一致</el-tag>
          <span v-if="sectionState.anchor_name" class="trace-drawer__muted">
            锚点 {{ sectionState.anchor_name }}
          </span>
        </div>

        <!-- 固定链条：交付件 → 附注章节 → 底稿 → 试算表 → 调整分录 -->
        <div class="trace-chain">
          <div v-for="(stage, idx) in stages" :key="stage.key" class="trace-chain__stage">
            <div class="trace-chain__head">
              <span class="trace-chain__seq">{{ idx + 1 }}</span>
              <span class="trace-chain__name">{{ stage.label }}</span>
              <span class="trace-chain__count">
                {{ stage.items.length ? `${stage.items.length} 项` : '未匹配' }}
              </span>
            </div>
            <ul v-if="stage.items.length" class="trace-chain__list">
              <li v-for="(c, i) in stage.items" :key="`${stage.key}-${i}`">
                <el-button
                  link
                  type="primary"
                  class="trace-chain__link"
                  @click="emit('navigate', c)"
                >
                  {{ c.source_id }}
                </el-button>
                <span v-if="c.source_cell" class="trace-drawer__muted">@{{ c.source_cell }}</span>
                <span v-if="c.amount" class="trace-chain__amount">{{ amount(c.amount) }}</span>
                <el-tag size="small" :type="statusTag(c.status)">{{ statusLabel(c.status) }}</el-tag>
                <span v-if="c.basis" class="trace-drawer__muted">{{ c.basis }}</span>
              </li>
            </ul>
            <p v-else class="trace-chain__empty">{{ stage.emptyHint }}</p>
          </div>
        </div>
      </template>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
/**
 * 交付件列表行级溯源抽屉（需求 11.5 / 11.6）。
 *
 * 与 OO 编辑器右侧栏的 `LineagePanel` 的分工：
 * - `LineagePanel` 依赖 OnlyOffice 书签跟随光标，**必须先打开编辑器**；
 * - 本抽屉从**列表**直接进入，按章节清单选章节 → 调同一个 `/trace` 端点，
 *   不需要打开编辑器（审计师复核时的主路径）。
 *
 * 🔴 trace 与错误处理**复用** `useDeliverableLineage`（含 504 超时的明确文案），
 * 不重写一份请求逻辑。
 */
import { computed, ref, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useDeliverableLineage } from '@/composables/useDeliverableLineage'
import type { LinkageContract, LinkageStatus, SourceType } from '@/types/linkageContract'

const props = defineProps<{
  visible: boolean
  projectId: string
  taskId: string
  title: string
}>()

const emit = defineEmits<{
  'update:visible': [v: boolean]
  navigate: [contract: LinkageContract]
}>()

const displayPrefs = useDisplayPrefsStore()

const taskIdRef = computed(() => props.taskId)
const projectIdRef = computed(() => props.projectId)
const { contracts, sectionState, loading, error, traceSection } = useDeliverableLineage(
  taskIdRef,
  projectIdRef,
)

interface SectionStateRow {
  section_code: string
  is_stale: boolean
  anchor_name: string | null
}

const sections = ref<SectionStateRow[]>([])
const sectionsLoading = ref(false)
const sectionsError = ref<string | null>(null)
const sectionCode = ref<string>('')

async function loadSections() {
  if (!props.projectId || !props.taskId) return
  sectionsLoading.value = true
  sectionsError.value = null
  sections.value = []
  try {
    const data = await api.get<{ sections: SectionStateRow[] }>(
      `/api/projects/${props.projectId}/deliverables/${props.taskId}/section-states`,
    )
    sections.value = Array.isArray(data?.sections) ? data.sections : []
    if (sections.value.length) {
      sectionCode.value = sections.value[0].section_code
      await traceSection(sectionCode.value)
    }
  } catch (e: unknown) {
    const err = e as { message?: string }
    // 需求 11.6：失败也要给原因，不得静默空白
    sectionsError.value = `章节清单加载失败：${err?.message || '未知错误'}`
  } finally {
    sectionsLoading.value = false
  }
}

async function runTrace() {
  if (!sectionCode.value) return
  await traceSection(sectionCode.value)
}

watch(
  () => [props.visible, props.taskId],
  ([open]) => {
    if (open) loadSections()
  },
  { immediate: true },
)

/** 链条阶段定义：顺序即需求 11.5 的链条顺序，禁按 contracts 里出现的顺序排。 */
const STAGE_DEFS: ReadonlyArray<{
  key: string
  label: string
  types: SourceType[]
  emptyHint: string
}> = Object.freeze([
  {
    key: 'note',
    label: '附注章节',
    types: ['note'],
    emptyHint: '该章节未登记附注层来源',
  },
  {
    key: 'workpaper',
    label: '底稿',
    types: ['workpaper', 'audit_sheet'],
    emptyHint: '未匹配到推送该章节的底稿',
  },
  {
    key: 'trial_balance',
    label: '试算表 / 序时账',
    types: ['trial_balance', 'ledger'],
    emptyHint: '未匹配到试算表层来源',
  },
  {
    key: 'adjustment',
    label: '调整分录',
    types: ['adjustment'],
    emptyHint: '本章节无相关调整分录',
  },
  {
    key: 'other',
    label: '其他来源（报表 / 附件 / AI）',
    types: ['report', 'attachment', 'ai'],
    emptyHint: '无',
  },
])

const stages = computed(() =>
  STAGE_DEFS.map((def) => ({
    ...def,
    items: contracts.value.filter((c) => def.types.includes(c.source_type)),
  })),
)

const STATUS_LABEL: Record<LinkageStatus, string> = {
  current: '最新',
  stale: '已过期',
  conflict: '冲突',
  manual_override: '人工覆盖',
}

const STATUS_TAG: Record<LinkageStatus, 'success' | 'warning' | 'danger' | 'info'> = {
  current: 'success',
  stale: 'warning',
  conflict: 'danger',
  manual_override: 'info',
}

function statusLabel(s: LinkageStatus) {
  return STATUS_LABEL[s] ?? s
}

function statusTag(s: LinkageStatus) {
  return STATUS_TAG[s] ?? 'info'
}

function amount(v: string | null | undefined) {
  if (v === null || v === undefined || v === '') return ''
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  return displayPrefs.fmtAmount(n)
}
</script>

<style scoped>
.trace-drawer {
  font-size: 13px;
}

.trace-drawer__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.trace-drawer__bar-label {
  color: var(--el-text-color-regular);
}

.trace-drawer__select {
  width: 240px;
}

.trace-drawer__alert {
  margin-bottom: 10px;
}

.trace-drawer__state {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.trace-drawer__muted {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

.trace-chain__stage {
  border-left: 2px solid var(--el-border-color);
  padding: 0 0 10px 12px;
  margin-left: 6px;
}

.trace-chain__head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.trace-chain__seq {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 9px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 12px;
}

.trace-chain__name {
  font-weight: 600;
}

.trace-chain__count {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

.trace-chain__list {
  margin: 4px 0 0;
  padding-left: 26px;
}

.trace-chain__list li {
  display: flex;
  align-items: center;
  gap: 8px;
  line-height: 1.9;
  flex-wrap: wrap;
}

.trace-chain__link {
  font-family: var(--el-font-family-monospace, monospace);
}

.trace-chain__amount {
  font-variant-numeric: tabular-nums;
}

.trace-chain__empty {
  margin: 4px 0 0 26px;
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}
</style>
