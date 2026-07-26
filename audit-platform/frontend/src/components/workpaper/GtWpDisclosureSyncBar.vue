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
  </div>
</template>

<script setup lang="ts">
/**
 * 底稿披露 sheet 顶部「附注同步状态条」（附注模块联动复盘 P0-2）
 *
 * 一处接入 GtWpRenderer → 覆盖全部循环的披露 sheet：告诉审计师本页披露表
 * 是否已同步到附注、上次同步于何时。解决"46 个 buildXSyncPayload 就绪但
 * 生产零同步记录"的根因之一：UI 上没有"还没做"的可见信号。
 *
 * 只读：不代替页内「同步到附注」动作（推送依赖各 tab 的 payload builder）。
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import http from '@/utils/http'
import { disclosureNotes as P_dn } from '@/services/apiPaths/report'
import { resolveDisclosureVariantFromSheet } from './composables/disclosureSyncBar'

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
