<!--
  TimeMachineDrawer — 时光机快照面板（spec global-refinement-v3 Task 11.5）
  =============================================================================
  展示快照列表 + 预览 + 恢复按钮 + confirmDangerous 二次确认。

  用法：
    <TimeMachineDrawer ref="tmDrawerRef" :module="module" :instance-id="instanceId" @restored="onRestored" />
    tmDrawerRef.value?.open()

  Props:
    module: string       业务模块类型（workpaper/adjustment/misstatement/disclosure）
    instanceId: string   实例 ID

  Emits:
    (e: 'restored', snapshot: any): void  恢复成功后触发

  Expose:
    open(): void   打开面板
    close(): void  关闭面板
-->
<template>
  <el-drawer
    v-model="visible"
    title="⏪ 时光机"
    size="640px"
    :destroy-on-close="false"
    direction="rtl"
  >
    <div v-loading="loading" style="min-height: 200px">
      <template v-if="snapshots.length > 0">
        <el-timeline class="tm-timeline">
          <el-timeline-item
            v-for="snap in snapshots"
            :key="snap.id"
            :timestamp="formatTime(snap.created_at)"
            placement="top"
            color="#4b2d77"
          >
            <div class="tm-card">
              <div class="tm-summary">{{ snap.diff_summary }}</div>
              <div class="tm-meta">
                <el-tag size="small" type="info">{{ snap.instance_type }}</el-tag>
              </div>
              <el-button
                type="primary"
                plain
                size="small"
                :disabled="isArchived"
                @click="onRestore(snap)"
              >
                恢复到此时刻
              </el-button>
            </div>
          </el-timeline-item>
        </el-timeline>
      </template>
      <el-empty v-else-if="!loading" description="暂无快照记录" />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useAuditContext } from '@/composables/useAuditContext'
import { confirmDangerous } from '@/utils/confirm'

interface Snapshot {
  id: string
  instance_type: string
  instance_id: string
  user_id: string
  created_at: string
  diff_summary: string
}

const props = defineProps<{
  module: string
  instanceId: string
}>()

const emit = defineEmits<{
  (e: 'restored', snapshot: Snapshot): void
}>()

const { isArchived } = useAuditContext()
const visible = ref(false)
const loading = ref(false)
const snapshots = ref<Snapshot[]>([])

function formatTime(isoStr: string): string {
  if (!isoStr) return ''
  try {
    const d = new Date(isoStr)
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return isoStr
  }
}

async function load() {
  loading.value = true
  try {
    const result: any = await api.get(
      `/api/instances/${props.module}/${props.instanceId}/time-machine/snapshots`,
    )
    snapshots.value = Array.isArray(result) ? result : []
  } catch (e: any) {
    console.error('[TimeMachineDrawer] 加载失败:', e)
    snapshots.value = []
  } finally {
    loading.value = false
  }
}

async function onRestore(snap: Snapshot) {
  try {
    await confirmDangerous({
      title: '恢复快照',
      message: '恢复后当前未保存的变更将丢失。数据将回退到快照时刻，且不可撤销。确认继续？',
      confirmText: '确定恢复',
      cancelText: '取消',
    })
  } catch {
    return // 用户取消
  }

  try {
    await api.post(
      `/api/instances/${props.module}/${props.instanceId}/time-machine/restore/${snap.id}`,
    )
    ElMessage.success('已恢复到 ' + formatTime(snap.created_at))
    visible.value = false
    emit('restored', snap)
  } catch (e: any) {
    const msg = e?.response?.data?.message || e?.message || '恢复失败'
    ElMessage.error(msg)
  }
}

async function open() {
  visible.value = true
  await load()
}

function close() {
  visible.value = false
}

defineExpose({ open, close })
</script>

<style scoped>
.tm-timeline {
  padding: 0 8px;
}

.tm-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.tm-summary {
  flex: 1;
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.tm-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
