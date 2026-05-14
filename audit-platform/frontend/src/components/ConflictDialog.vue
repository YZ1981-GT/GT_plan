<script setup lang="ts">
/**
 * ConflictDialog — 冲突提示对话框 [enterprise-linkage 3.4]
 *
 * 显示编辑锁冲突或版本冲突提示。
 */
defineProps<{
  visible: boolean
  lockHolder?: string | null
  conflictType: 'lock' | 'version'
}>()

const emit = defineEmits<{
  close: []
  refresh: []
}>()

function onClose() {
  emit('close')
}

function onRefresh() {
  emit('refresh')
  emit('close')
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="conflictType === 'lock' ? '编辑冲突' : '版本冲突'"
    width="400px"
    :close-on-click-modal="false"
    @close="onClose"
  >
    <div class="conflict-content">
      <template v-if="conflictType === 'lock'">
        <el-alert type="warning" :closable="false" show-icon>
          <template #title>
            该分录正在被 <strong>{{ lockHolder || '其他用户' }}</strong> 编辑中
          </template>
        </el-alert>
        <p class="conflict-hint">请等待对方完成编辑后再试，或联系对方释放锁定。</p>
      </template>

      <template v-else>
        <el-alert type="error" :closable="false" show-icon>
          <template #title>该分录已被他人修改</template>
        </el-alert>
        <p class="conflict-hint">数据已更新，点击"刷新"获取最新版本后重新编辑。</p>
      </template>
    </div>

    <template #footer>
      <el-button @click="onClose">关闭</el-button>
      <el-button v-if="conflictType === 'version'" type="primary" @click="onRefresh">
        刷新最新版本
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.conflict-content {
  padding: 8px 0;
}
.conflict-hint {
  margin-top: 12px;
  font-size: 13px;
  color: #606266;
}
</style>
