<!--
  ArchivedBanner — 项目归档只读横幅
  当项目处于 archived 状态时，在视图顶部显示紫色横幅提示。
  admin/partner 角色可见「解除归档」按钮：填原因 → 输入项目名称二次确认 → 调解除归档接口 → 刷新页面。
  （spec attachment-archive-and-a-class-evidence ADR-AE-13：改造前按钮只发一个没有任何页面监听的事件，点了没反应；
   归档向导现在真的会锁项目与底稿，这里是唯一的界面出口。）

  用法：
    <ArchivedBanner />
    <!-- 无需 props，内部读取 useAuditContext -->
-->
<template>
  <div v-if="isArchived" class="archived-banner">
    <span class="archived-banner__text">
      🔒 📁 项目已归档（只读）
    </span>
    <el-button
      v-if="canUnarchive"
      class="archived-banner__btn"
      size="small"
      :loading="busy"
      @click="handleUnarchive"
    >
      解除归档
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuditContext } from '@/composables/useAuditContext'
import { useRoleContextStore } from '@/stores/roleContext'
import { useProjectStore } from '@/stores/project'
import { api } from '@/services/apiProxy'
import { projects as projectPaths } from '@/services/apiPaths'
import { unarchiveProject } from '@/services/archiveApi'
import { handleApiError } from '@/utils/errorHandler'

const { isArchived, projectId } = useAuditContext()
const roleContextStore = useRoleContextStore()
const projectStore = useProjectStore()

/** admin/partner 角色可见解除归档按钮 */
const canUnarchive = computed(() => roleContextStore.isPartner)
const busy = ref(false)

/** 成功提示看完再刷新（项目已归档时页面只读，没有未保存的改动） */
const RELOAD_DELAY_MS = 1500

const emit = defineEmits<{
  (e: 'unarchived', workpapersRestored: number): void
}>()

/** 逐步弹框；取消返回 null */
async function promptText(message: string, title: string, options: Record<string, unknown>): Promise<string | null> {
  try {
    const { value } = await ElMessageBox.prompt(message, title, { cancelButtonText: '取消', ...options })
    return value
  } catch {
    return null
  }
}

async function handleUnarchive() {
  const pid = projectId.value
  if (!pid || busy.value) return
  const reason = await promptText(
    '解除后项目与底稿恢复为归档前的可编辑状态。请填写解除原因（记入审计日志）：',
    '解除归档',
    {
      confirmButtonText: '下一步',
      inputPlaceholder: '例如：补充期后事项程序',
      inputValidator: (v: string) => !!(v && v.trim()) || '请填写解除原因',
    },
  )
  if (reason === null) return
  busy.value = true
  try {
    // 后端按项目名称核对二次确认；项目 store 只有客户名，现取一次
    const detail = await api.get<{ name?: string }>(projectPaths.detail(pid), { _dedupe: false } as any)
    const name = detail?.name || ''
    const typed = await promptText(`请输入项目名称「${name}」以确认解除归档：`, '解除归档确认', {
      confirmButtonText: '解除归档',
      confirmButtonClass: 'el-button--danger',
      inputValidator: (v: string) => v === name || '项目名称不一致',
    })
    if (typed === null) return
    const res = await unarchiveProject(pid, { reason: reason.trim(), project_code: typed })
    projectStore.projectStatus = res?.new_status || 'execution'
    const restored = Number(res?.workpapers_restored || 0)
    ElMessage.success(`已解除归档${restored ? `，${restored} 张底稿恢复为归档前状态` : ''}；页面即将刷新`)
    emit('unarchived', restored)
    setTimeout(() => window.location.reload(), RELOAD_DELAY_MS)
  } catch (err: any) {
    handleApiError(err, '解除归档')
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.archived-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  width: 100%;
  height: 40px;
  padding: 8px 16px;
  background: linear-gradient(135deg, #4b2d77, #6b3fa0);
  color: #fff;
  font-size: 14px;
  box-sizing: border-box;
}

.archived-banner__text {
  display: flex;
  align-items: center;
  gap: 4px;
}

.archived-banner__btn {
  --el-button-bg-color: transparent;
  --el-button-border-color: #fff;
  --el-button-text-color: #fff;
  --el-button-hover-bg-color: rgba(255, 255, 255, 0.1);
  --el-button-hover-border-color: #fff;
  --el-button-hover-text-color: #fff;
  border: 1px solid #fff;
  color: #fff;
  background: transparent;
}
</style>
