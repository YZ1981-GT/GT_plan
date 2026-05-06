<template>
  <div class="gt-sig-history">
    <el-timeline v-if="records.length > 0">
      <el-timeline-item
        v-for="r in records"
        :key="r.id"
        :timestamp="fmtTime(r.created_at)"
        :type="levelType(r.signature_level)"
        placement="top"
      >
        <el-card shadow="never" class="gt-sig-card">
          <div class="gt-sig-info">
            <span class="gt-sig-signer">{{ r.signer_name || r.signer_id }}</span>
            <el-tag size="small" :type="(levelType(r.signature_level)) || undefined">{{ levelLabel(r.signature_level) }}</el-tag>
          </div>
          <div class="gt-sig-meta">
            <span v-if="r.ip_address">IP: {{ r.ip_address }}</span>
            <span>{{ fmtTime(r.created_at) }}</span>
          </div>
        </el-card>
      </el-timeline-item>
    </el-timeline>
    <el-empty v-else description="暂无签名记录" :image-size="60" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  objectType: string
  objectId: string
}>()

const records = ref<any[]>([])

async function loadRecords() {
  if (!props.objectType || !props.objectId) return
  try {
    const data = await api.get(`/api/signatures/${props.objectType}/${props.objectId}`)
    records.value = data ?? []
  } catch { records.value = [] }
}

function levelType(l: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = { level1: 'primary', level2: 'success', level3: 'warning' }
  return m[l] || 'info'
}
function levelLabel(l: string) {
  const m: Record<string, string> = { level1: '密码确认', level2: '手写签名', level3: 'CA证书' }
  return m[l] || l
}
function fmtTime(d: string) {
  return d ? new Date(d).toLocaleString('zh-CN') : '-'
}

watch(() => [props.objectType, props.objectId], loadRecords)
onMounted(loadRecords)
</script>

<style scoped>
.gt-sig-history { padding: var(--gt-space-2); }
.gt-sig-card { border-radius: var(--gt-radius-sm); }
.gt-sig-info { display: flex; align-items: center; gap: var(--gt-space-2); margin-bottom: 4px; }
.gt-sig-signer { font-weight: 600; font-size: var(--gt-font-size-base); }
.gt-sig-meta {
  display: flex; gap: var(--gt-space-4);
  font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);
}
</style>
