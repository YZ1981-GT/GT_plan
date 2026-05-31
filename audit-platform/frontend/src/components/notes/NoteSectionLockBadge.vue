<template>
  <!-- A.6.2: 章节列表锁可视化 + A.6.3: 锁冲突弹窗 -->
  <span v-if="lockInfo" class="lock-badge" @click="handleLockClick">
    <el-tooltip :content="`${lockInfo.locked_by_name} 正在编辑`" placement="top">
      <el-tag size="small" type="warning" effect="plain">
        🔒 {{ lockInfo.locked_by_name }}
      </el-tag>
    </el-tooltip>

    <!-- A.6.3: 锁冲突弹窗 -->
    <el-dialog v-model="showConflict" title="章节锁定冲突" width="400px">
      <p>该章节正在被 <strong>{{ lockInfo.locked_by_name }}</strong> 编辑。</p>
      <p style="color: #909399; font-size: 12px">
        锁定时间：{{ lockInfo.locked_at }}
      </p>
      <template #footer>
        <el-button @click="showConflict = false">等待</el-button>
        <el-button type="warning" @click="handleForceAcquire">
          强制抢占
        </el-button>
      </template>
    </el-dialog>
  </span>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

interface LockInfo {
  locked_by: string
  locked_by_name: string
  locked_at: string
  section_id: string
}

interface Props {
  lockInfo: LockInfo | null
  projectId: string
  sectionId: string
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'lock-acquired': [] }>()

const showConflict = ref(false)

function handleLockClick() {
  if (props.lockInfo) {
    showConflict.value = true
  }
}

async function handleForceAcquire() {
  try {
    await ElMessageBox.confirm(
      '强制抢占将中断对方的编辑，确定继续？',
      '确认抢占',
      { type: 'warning' }
    )
    await api.post(`/api/disclosure-notes/${props.projectId}/sections/${props.sectionId}/force-lock`)
    showConflict.value = false
    emit('lock-acquired')
    ElMessage.success('已获取编辑锁')
  } catch (e: any) {
    if (e !== 'cancel') {
      handleApiError(e, '抢占')
    }
  }
}
</script>

<style scoped>
.lock-badge {
  cursor: pointer;
  margin-left: 8px;
}
</style>
