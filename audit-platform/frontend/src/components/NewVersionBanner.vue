<!-- Feature: zero-downtime-deployment, Component 4b -->
<template>
  <Transition name="banner-slide">
    <div v-if="updateAvailable" class="new-version-banner">
      <span class="banner-text">新版本可用，建议刷新页面获取最新功能</span>
      <button class="banner-btn" @click="handleRefresh">刷新</button>
      <button class="banner-close" @click="dismiss" aria-label="关闭">×</button>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { useVersionCheck } from '@/composables/useVersionCheck'

const { updateAvailable, dismiss } = useVersionCheck()

function handleRefresh() {
  window.location.reload()
}
</script>

<style scoped>
.new-version-banner {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 10px 16px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  border-bottom: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  font-size: 14px;
  color: var(--gt-color-primary, #4b2d77);
}

.banner-btn {
  padding: 4px 12px;
  border-radius: 4px;
  border: 1px solid var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary, #4b2d77);
  color: #fff;
  cursor: pointer;
  font-size: 13px;
}

.banner-btn:hover {
  opacity: 0.9;
}

.banner-close {
  position: absolute;
  right: 16px;
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: var(--gt-color-primary, #4b2d77);
  line-height: 1;
}

.banner-slide-enter-active,
.banner-slide-leave-active {
  transition: transform 0.3s ease, opacity 0.3s ease;
}

.banner-slide-enter-from,
.banner-slide-leave-to {
  transform: translateY(-100%);
  opacity: 0;
}
</style>
