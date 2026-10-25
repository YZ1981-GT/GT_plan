<template>
  <div v-if="loaded" class="ds-coverage-panel">
    <div class="ds-coverage-header">
      <span class="ds-coverage-title">披露同步覆盖率</span>
      <el-button size="small" link @click="load">
        <el-icon><Refresh /></el-icon>
      </el-button>
    </div>
    <div v-if="summary" class="ds-coverage-body">
      <div class="ds-coverage-stats">
        <span class="ds-stat">
          <b>{{ summary.synced }}</b> / {{ summary.expected }} 已同步
        </span>
        <span v-if="summary.stale > 0" class="ds-stat ds-stat-stale">
          {{ summary.stale }} 个已过期
        </span>
        <span v-if="summary.never_synced > 0" class="ds-stat ds-stat-never">
          {{ summary.never_synced }} 个从未同步
        </span>
      </div>
      <el-progress
        :percentage="percentage"
        :color="progressColor"
        :stroke-width="6"
        :show-text="false"
        class="ds-coverage-progress"
      />
      <div v-if="showDetails" class="ds-coverage-details">
        <button
          v-for="item in neverSyncedItems"
          :key="item.note_section"
          type="button"
          class="ds-detail-item"
          :title="`跳到 ${item.wp_codes.join('/')} 底稿的披露表填写并同步`"
          @click="jumpToWorkpaper(item.wp_codes[0])"
        >
          <span class="ds-detail-code">{{ item.wp_codes.join('/') }}</span>
          <span class="ds-detail-variant">{{ item.variant === 'listed' ? '上市' : '国企' }}</span>
          <span class="ds-detail-section">{{ item.note_section }}</span>
        </button>
      </div>
      <el-button
        v-if="summary.never_synced > 0"
        size="small"
        link
        type="primary"
        @click="showDetails = !showDetails"
      >
        {{ showDetails ? '收起详情' : `查看未同步章节（${summary.never_synced}）` }}
      </el-button>
    </div>
    <div v-else class="ds-coverage-empty">暂无数据</div>
  </div>
</template>

<script setup lang="ts">
/**
 * 披露同步覆盖率面板（附注侧 / 底稿侧可复用）
 *
 * 只读，不触发同步。调用 GET /api/projects/{pid}/disclosure-sync-coverage?year=YYYY。
 * UI 文本全中文。
 *
 * spec: disclosure-payload-authority-source / Task 2.4 / ADR-DPA-002
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import api from '@/services/apiProxy'
import { useAcnr } from '@/services/acnr'

const props = defineProps<{
  projectId?: string
  year?: number
}>()

/**
 * 跳转自持（不经宿主 emit）。
 *
 * 🔴 设计取舍：首版让宿主 `DisclosureEditor.vue` 提供 `onCoverageJumpToWorkpaper`
 * handler，宿主净增 39 行。而该宿主已 3398 行（远超 1800 硬上限），pre-commit
 * 文件行数门禁明确要求「抽伴生模块（优先），确有必要再更新 whitelist」。
 * 本面板自身已有 `projectId`，跳转所需的 router / ACNR 都可自取 ⇒ 逻辑内收，
 * 宿主只留 import + 一个标签（净增 5 行）。组件自包含也更好复用。
 */
const router = useRouter()
const { resolveInstance: acnrResolveInstance } = useAcnr()

async function jumpToWorkpaper(wpCode: string): Promise<void> {
  if (!wpCode || !props.projectId) return
  try {
    const res = await acnrResolveInstance({
      project_id: props.projectId,
      parent: wpCode,
      sheet_code: wpCode,
    })
    if (!res?.found || !res.wp_id) {
      ElMessage.warning(`未找到 ${wpCode} 底稿，请先在项目中生成`)
      return
    }
    router.push(`/projects/${props.projectId}/workpapers/${res.wp_id}/edit`)
  } catch {
    ElMessage.warning(`跳转失败，请手动打开 ${wpCode} 底稿`)
  }
}

interface CoverageItem {
  wp_code: string
  variant: string
  note_section: string
  expected: boolean
  synced: boolean
  stale: boolean
  never_synced: boolean
}

interface CoverageSummary {
  /** 应同步章节数（按 note_section 去重；共享章节只算一次） */
  expected: number
  synced: number
  stale: number
  never_synced: number
  /** 职责行数（含跨循环共享章节的重复），仅供诊断 */
  duty_rows: number
  items: CoverageItem[]
}

const loaded = ref(false)
const summary = ref<CoverageSummary | null>(null)
const showDetails = ref(false)

const percentage = computed(() => {
  if (!summary.value || summary.value.expected === 0) return 0
  return Math.round((summary.value.synced / summary.value.expected) * 100)
})

const progressColor = computed(() => {
  const pct = percentage.value
  if (pct >= 80) return 'var(--el-color-success)'
  if (pct >= 40) return 'var(--el-color-warning)'
  return 'var(--el-color-danger)'
})

/**
 * 未同步章节列表，按 note_section 去重。
 *
 * 🔴 必须去重：8 个章节是跨循环共享的（如「五、8」← G2/G3/K1），
 * items 里有多条职责行但只对应一个附注章节，不去重会重复显示同一章节。
 * 多 owner 时把 wp_code 合并展示（「G2/G3/K1」）。
 */
const neverSyncedItems = computed(() => {
  const bySection = new Map<string, { wp_codes: string[]; variant: string; note_section: string }>()
  for (const i of summary.value?.items ?? []) {
    if (!i.never_synced) continue
    const existing = bySection.get(i.note_section)
    if (existing) {
      if (!existing.wp_codes.includes(i.wp_code)) existing.wp_codes.push(i.wp_code)
    } else {
      bySection.set(i.note_section, {
        wp_codes: [i.wp_code],
        variant: i.variant,
        note_section: i.note_section,
      })
    }
  }
  return [...bySection.values()]
})

async function load() {
  loaded.value = false
  summary.value = null
  showDetails.value = false
  if (!props.projectId || !props.year) return
  try {
    const data = await api.get(
      `/api/projects/${props.projectId}/disclosure-sync-coverage`,
      { params: { year: props.year } },
    )
    summary.value = (data?.data ?? data) as CoverageSummary
  } catch {
    summary.value = null
  } finally {
    loaded.value = true
  }
}

watch(
  () => [props.projectId, props.year],
  () => void load(),
  { immediate: true },
)
</script>

<style scoped>
.ds-coverage-panel {
  padding: 8px 12px;
  margin-bottom: 8px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
  font-size: 13px;
}
.ds-coverage-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.ds-coverage-title {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.ds-coverage-stats {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.ds-stat {
  color: var(--el-text-color-regular);
}
.ds-stat b {
  color: var(--el-color-success);
}
.ds-stat-stale {
  color: var(--el-color-warning);
}
.ds-stat-never {
  color: var(--el-color-danger);
}
.ds-coverage-progress {
  margin-bottom: 6px;
}
.ds-coverage-details {
  max-height: 200px;
  overflow-y: auto;
  margin: 6px 0;
}
/* 用 <button> 承载以获得键盘可达性（Tab + Enter），需重置浏览器默认外观 */
.ds-detail-item {
  display: flex;
  gap: 8px;
  width: 100%;
  padding: 2px 4px;
  border: none;
  border-radius: 3px;
  background: transparent;
  font-family: inherit;
  font-size: 12px;
  text-align: left;
  color: var(--el-text-color-secondary);
  cursor: pointer;
}
.ds-detail-item:hover {
  background: var(--el-fill-color);
  color: var(--el-color-primary);
}
.ds-detail-item:focus-visible {
  outline: 2px solid var(--el-color-primary);
  outline-offset: -2px;
}
.ds-detail-code {
  font-weight: 500;
  min-width: 40px;
}
.ds-detail-variant {
  min-width: 28px;
  color: var(--el-text-color-placeholder);
}
.ds-coverage-empty {
  color: var(--el-text-color-placeholder);
  text-align: center;
  padding: 8px 0;
}
</style>
