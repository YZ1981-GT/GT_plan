<!--
  ConsolLockedBanner — 子公司被合并项目锁定只读横幅
  当当前项目被合并项目锁定（consol_lock=true）时，在视图顶部显示橙色横幅提示。
  仿 ArchivedBanner：无 props，内部读取 useAuditContext 拿 projectId + 调 checkLockStatus 拉锁定态。

  用法：
    <ConsolLockedBanner />
    <!-- 无需 props，内部读取锁定态 -->

  关联：consol-phase1-arch-lock 需求 4.1 / 4.2（F2/F4）
-->
<template>
  <div v-if="isConsolLocked" class="consol-locked-banner">
    <span class="consol-locked-banner__text">
      🔒 本项目已被合并项目锁定，暂不可编辑
    </span>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useAuditContext } from '@/composables/useAuditContext'
import { checkLockStatus } from '@/services/commonApi'
import { eventBus } from '@/utils/eventBus'

const { projectId } = useAuditContext()

const locked = ref(false)

const isConsolLocked = computed(() => locked.value)

async function refreshLockStatus() {
  const pid = projectId.value
  if (!pid) {
    locked.value = false
    return
  }
  try {
    const res = await checkLockStatus(pid)
    // checkLockStatus 返回后端包装体 {code, message, data:{locked,...}}；兼容已解包两种形态
    const payload = res?.data ?? res
    locked.value = Boolean(payload?.locked)
  } catch {
    // 拉取失败不误报锁定（放行，与后端 EH4 放行一致）
    locked.value = false
  }
}

onMounted(refreshLockStatus)

// 项目切换时刷新锁定态
watch(projectId, refreshLockStatus)

// 423 拦截器检测到合并锁定 → 刷新锁定态（需求 4.3）
eventBus.on('consol-lock:detected', refreshLockStatus)
onUnmounted(() => {
  eventBus.off('consol-lock:detected', refreshLockStatus)
})

// 暴露刷新方法供 423 拦截器触发（通过 ref 调用）
defineExpose({ refreshLockStatus })
</script>

<style scoped>
.consol-locked-banner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  width: 100%;
  height: 40px;
  padding: 8px 16px;
  background: linear-gradient(135deg, #d46b08, #fa8c16);
  color: #fff;
  font-size: 14px;
  box-sizing: border-box;
}

.consol-locked-banner__text {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
