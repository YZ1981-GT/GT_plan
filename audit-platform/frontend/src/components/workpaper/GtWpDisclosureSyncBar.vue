<template>
  <div v-if="loaded && variantState" class="gt-wpdsb" :class="synced ? 'is-synced' : 'is-unsynced'">
    <span class="gt-wpdsb-icon">{{ synced ? '✅' : '⚠️' }}</span>
    <span class="gt-wpdsb-text">
      <template v-if="synced">
        本页披露表已同步到附注 <b>{{ variantState.note_section }}</b>
        <span class="gt-wpdsb-time">（{{ fmtTime(variantState.last_sync_at) }}）</span>
        <span class="gt-wpdsb-hint">改动后请再次点本页「同步到附注」</span>
      </template>
      <template v-else>
        本页披露表<b>尚未同步到附注</b>（对应章节 {{ variantState.note_section }}）——
        附注模块看到的仍是模板/取数结果，请点本页的「同步到附注」按钮
      </template>
    </span>
    <el-button size="small" link type="primary" @click="goNote">查看附注章节</el-button>
    <el-button size="small" link @click="load">刷新状态</el-button>
    <!--
      项目级覆盖率（spec disclosure-payload-authority-source / ADR-DPA-002）：
      本状态条是**单页视角**（只说这一页同步没同步），覆盖率面板补**全项目视角**
      （还有哪些披露章节从未同步）。挂这里是因为设计 §四 指定「复用既有
      GtWpDisclosureSyncBar 展示位」，且本组件已一处接入 GtWpRenderer、
      覆盖全部循环的披露 sheet。
      🔴 附注侧（DisclosureEditor）入口本轮未挂：该宿主 3401 行、HARD_CAPS 登记
      ceiling 1800（既有瘦身欠账），pre-commit 门禁硬拒绝任何触碰。
      见 spec design.md §十三。
    -->
    <el-popover placement="bottom-end" :width="380" trigger="click">
      <template #reference>
        <el-button size="small" link>项目覆盖率</el-button>
      </template>
      <DisclosureSyncCoveragePanel :project-id="projectId" :year="year" />
    </el-popover>
  </div>
</template>

<script setup lang="ts">
/**
 * 底稿披露 sheet 顶部「附注同步状态条」（附注模块联动复盘 P0-2）
 *
 * 一处接入 GtWpRenderer → 覆盖全部循环的披露 sheet：告诉审计师本页披露表
 * 是否已同步到附注、上次同步于何时。解决"载荷构造器已大批就绪但生产同步覆盖率
 * 很低"的根因之一：UI 上没有"还没做"的可见信号。
 *
 * 🔴 此处原写死"46 个 buildXSyncPayload"与"生产零同步记录"，两个数字都过期：
 *   实际不是零同步而是低覆盖（真库 disclosure_notes 1052 行 / last_sync_at 非空 93）。
 *   构造器数量**不再写死** —— 它随各循环 spec 增减而漂移，复算口径：
 *     export function build\w*SyncPayload  于 audit-platform/frontend/src/**\/*.{ts,vue}
 *   （spec disclosure-payload-authority-source 曾把 46 纠正为 109，而 109 同样是错数，
 *    穷举 120 种口径组合无一命中，真值 69 —— 教训 T25：换掉过期数字时，新数字必须
 *    和旧数字同标准验证，否则只是把错数换成错数。见其 design §十四。)
 *
 * 只读：不代替页内「同步到附注」动作（推送依赖各 tab 的 payload builder）。
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import http from '@/utils/http'
import { disclosureNotes as P_dn } from '@/services/apiPaths/report'
import { resolveDisclosureVariantFromSheet } from './composables/disclosureSyncBar'
import DisclosureSyncCoveragePanel from '../disclosure/DisclosureSyncCoveragePanel.vue'

const props = defineProps<{
  projectId?: string
  year?: number
  wpCode?: string
  sheetName?: string
}>()

interface VariantState {
  variant: string
  note_section: string
  exists: boolean
  last_sync_at: string | null
  last_sync_source: string | null
  has_data: boolean
}

const router = useRouter()
const loaded = ref(false)
const variants = ref<VariantState[]>([])

/** 由 sheet 名判定当前是上市版还是国企版披露表（与 GtWpRenderer 共用纯函数） */
const variantKey = computed(() => resolveDisclosureVariantFromSheet(props.sheetName))

const variantState = computed<VariantState | null>(() => {
  if (!variants.value.length) return null
  const key = variantKey.value
  if (key) return variants.value.find(v => v.variant === key) || null
  // sheet 名未含变体标识（单变体科目）→ 取唯一项
  return variants.value.length === 1 ? variants.value[0] : null
})

const synced = computed(() => !!variantState.value?.last_sync_at)

async function load() {
  loaded.value = false
  variants.value = []
  if (!props.projectId || !props.year || !props.wpCode) return
  try {
    const { data } = await http.get(P_dn.wpSyncStatus(props.projectId, props.year), {
      params: { wp_code: props.wpCode },
      _silent: true,
    } as any)
    const payload = (data?.data ?? data) || {}
    variants.value = Array.isArray(payload.variants) ? payload.variants : []
  } catch {
    variants.value = []
  } finally {
    loaded.value = true
  }
}

function goNote() {
  const section = variantState.value?.note_section
  if (!section || !props.projectId) return
  router.push({
    path: `/projects/${props.projectId}/disclosure-notes`,
    query: { section, noteTemplate: variantKey.value || undefined },
  })
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

watch(
  () => [props.projectId, props.year, props.wpCode, props.sheetName],
  () => void load(),
  { immediate: true },
)
</script>

<style scoped>
.gt-wpdsb {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 6px 10px; margin-bottom: 8px; border-radius: 6px;
  font-size: 13px; line-height: 1.6;
}
.gt-wpdsb.is-unsynced { background: #fffbeb; border-left: 4px solid #f59e0b; color: #78350f; }
.gt-wpdsb.is-synced { background: var(--el-color-success-light-9); border-left: 4px solid var(--el-color-success); color: var(--el-text-color-regular); }
.gt-wpdsb-text { flex: 1 1 auto; }
.gt-wpdsb-time { color: var(--el-text-color-secondary); }
.gt-wpdsb-hint { margin-left: 6px; color: var(--el-text-color-secondary); font-size: 12px; }
</style>
