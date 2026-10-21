<!-- 公式依赖关系面板（从 FormulaManagerDialog 提取；spec formula-settings-wiring-closure T11）。 -->
<template>
  <div v-if="visible && data" class="gt-fm-dep-panel" style="margin-top: 8px; padding: 10px; border: 1px solid var(--gt-color-border, #ebeef5); border-radius: 6px; background: var(--gt-bg-page, #fafafa);">
    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
      <span style="font-size: 13px; font-weight: 600;">📊 依赖关系</span>
      <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">{{ data.formula || '（无公式）' }}</span>
      <span style="flex: 1;" />
      <el-button size="small" link @click="visible = false">关闭</el-button>
    </div>
    <div v-if="data.unavailable_domains?.length" style="font-size: 11px; color: var(--gt-color-warning); margin-bottom: 6px;">
      ⚠ 以下域未列入：{{ data.unavailable_domains.map((d: any) => d.label).join('、') }}
    </div>
    <div style="display: flex; gap: 16px;">
      <!-- 引用了谁 -->
      <div style="flex: 1;">
        <div style="font-size: 12px; font-weight: 600; margin-bottom: 4px; color: var(--gt-color-text-secondary);">⬆ 引用了（{{ data.upstream?.length ?? 0 }}）</div>
        <div v-for="dep in data.upstream" :key="dep.addr_id" style="font-size: 11px; padding: 3px 0; border-bottom: 1px solid #f0f0f0;">
          <el-tag size="small" effect="plain" :type="typeTag(dep.type)">{{ typeLabel(dep.type) }}</el-tag>
          <span style="margin-left: 4px;">{{ dep.label }}</span>
        </div>
        <div v-if="!data.upstream?.length" style="font-size: 11px; color: var(--gt-color-text-placeholder);">无上游依赖</div>
      </div>
      <!-- 被谁引用 -->
      <div style="flex: 1;">
        <div style="font-size: 12px; font-weight: 600; margin-bottom: 4px; color: var(--gt-color-text-secondary);">⬇ 被引用（{{ data.downstream?.length ?? 0 }}{{ data.downstream_total > 200 ? `，共 ${data.downstream_total}` : '' }}）</div>
        <div v-for="dep in data.downstream" :key="dep.addr_id" style="font-size: 11px; padding: 3px 0; border-bottom: 1px solid #f0f0f0;">
          <el-tag size="small" effect="plain" :type="typeTag(dep.type)">{{ typeLabel(dep.type) }}</el-tag>
          <span style="margin-left: 4px;">{{ dep.label }}</span>
        </div>
        <div v-if="!data.downstream?.length" style="font-size: 11px; color: var(--gt-color-text-placeholder);">无下游引用</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import api from '@/services/apiProxy'

const props = defineProps<{ projectId?: string }>()

const visible = ref(false)
const data = ref<any>(null)
const loading = ref(false)

async function load(addrId: string) {
  if (!props.projectId || !addrId) return
  loading.value = true
  visible.value = true
  try {
    data.value = await api.get(`/api/projects/${props.projectId}/formula-settings/dependencies`, { params: { addr_id: addrId } }) as any
  } catch { data.value = null }
  finally { loading.value = false }
}

function typeTag(t: string) {
  const m: Record<string, string> = { trial_balance: 'success', report: 'primary', workpaper: 'warning', note: 'info' }
  return m[t] || 'info'
}
function typeLabel(t: string) {
  const m: Record<string, string> = { trial_balance: 'TB', report: '报表', workpaper: '底稿', note: '附注', prior: '上期', cross_check: '表间审核', adjustment: '调整' }
  return m[t] || t
}

defineExpose({ load, visible })
</script>
