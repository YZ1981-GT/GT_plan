<template>
  <!-- 底部状态栏 -->
  <div class="gt-wp-editor-statusbar" v-if="wpDetail">
    <span>编制人: {{ resolveUserName(wpDetail.assigned_to) }}</span>
    <span>复核人: {{ resolveUserName(wpDetail.reviewer) }}</span>
    <span>版本: v{{ wpDetail.file_version || 1 }}</span>
    <span v-if="wpDetail.updated_at">最后修改: {{ wpDetail.updated_at.slice(0, 19) }}</span>
    <span v-if="autoSaveMsg" style="color: var(--gt-color-success)">✓ {{ autoSaveMsg }}</span>
    <span v-if="dirty" style="color: var(--gt-color-wheat)">● 未保存</span>
    <span v-if="currentTip" class="gt-wp-smart-tip" @click="showSmartTipDetail = !showSmartTipDetail">
      💡 {{ currentTip.summary }}
    </span>
  </div>

  <!-- 智能提示详情 -->
  <div v-if="showSmartTipDetail && currentTip" class="gt-wp-smart-tip-detail">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <span style="font-weight:600;font-size: var(--gt-font-size-sm)">💡 审计关注点</span>
      <el-button size="small" text @click="showSmartTipDetail = false">收起</el-button>
    </div>
    <div v-if="currentTip.warnings?.length" style="margin-bottom:6px">
      <div v-for="(w, i) in currentTip.warnings" :key="i" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-wheat); padding: 2px 0">⚠️ {{ w }}</div>
    </div>
    <div v-if="currentTip.tips?.length">
      <div v-for="(t, i) in currentTip.tips" :key="i" style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); padding: 1px 0">• {{ t }}</div>
    </div>
  </div>
</template>

<script lang="ts">
/** 智能提示数据结构 */
export interface SmartTipData {
  summary: string
  warnings?: string[]
  tips?: string[]
}
</script>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { type WorkpaperDetail } from '@/services/workpaperApi'
import { listUsers } from '@/services/commonApi'
import { api as httpApi } from '@/services/apiProxy'
import { workpapers as P_wp } from '@/services/apiPaths'

const props = defineProps<{
  wpDetail: WorkpaperDetail | null
  dirty: boolean
  autoSaveMsg: string
  smartTip: SmartTipData | null
}>()

// ─── 智能提示展开/收起 ─────────────────────────────────────────────────────────
const showSmartTipDetail = ref(false)

// 内部加载的智能提示（优先使用 prop 传入的 smartTip）
const internalSmartTip = ref<SmartTipData | null>(null)
const currentTip = computed(() => props.smartTip ?? internalSmartTip.value)

// ─── 用户名映射（UUID → 显示名）─────────────────────────────────────────────────
const userNameMap = ref<Map<string, string>>(new Map())

function resolveUserName(uuid: string | null | undefined): string {
  if (!uuid) return '未分配'
  return userNameMap.value.get(uuid) ?? '未知用户'
}

async function loadUserMap() {
  try {
    const users = await listUsers()
    userNameMap.value = new Map(
      (users || []).map((u: any) => [u.id, u.full_name || u.username || u.id])
    )
  } catch { /* 静默：状态栏降级显示 UUID */ }
}

// ─── 智能提示加载 ────────────────────────────────────────────────────────────────
async function loadSmartTips() {
  if (!props.wpDetail) return
  try {
    const wpName = props.wpDetail.wp_name || ''
    const accountName = wpName.replace(/审定表|明细表|程序表|汇总表|盘点表|调节表|核对表/g, '').trim()
    if (!accountName) return

    const projectId = props.wpDetail.project_id
    const data = await httpApi.get(
      P_wp.wpMappingTsj(projectId, accountName),
      { validateStatus: (s: number) => s < 600 },
    )
    if (data?.tips?.length || data?.risk_areas?.length) {
      internalSmartTip.value = {
        summary: data.risk_areas?.find((a: string) => a.includes('高风险')) || data.tips?.[0]?.slice(0, 30) || '查看审计关注点',
        warnings: (data.risk_areas || []).filter((a: string) => a.includes('高风险')),
        tips: (data.tips || []).slice(0, 3),
      }
    }
  } catch { /* ignore */ }
}

// wpDetail 就绪后加载用户名映射和智能提示
watch(() => props.wpDetail, (val) => {
  if (val) {
    loadUserMap()
    loadSmartTips()
  }
}, { immediate: true })
</script>
