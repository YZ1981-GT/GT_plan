<template>
  <div class="gt-display-settings-view" data-testid="display-settings-view">
    <h2 class="gt-dsv-title">显示设置</h2>
    <p class="gt-dsv-desc">设置保存在当前账号下，换浏览器或换电脑登录后保持一致。</p>
    <el-card shadow="never" class="gt-dsv-card">
      <DisplayPreferencesPanel />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * `/display-settings`：所有登录用户都能进入的显示偏好页（spec platform-global-display-settings-closure R3 / AC-07）。
 *
 * 只挂显示偏好面板；系统配置（`/settings`）仍只对管理员开放。
 */
import DisplayPreferencesPanel from '@/components/settings/DisplayPreferencesPanel.vue'
</script>

<style scoped>
.gt-display-settings-view { max-width: 720px; padding: 16px 24px; }
.gt-dsv-title { margin: 0 0 4px; font-size: var(--gt-font-size-lg, 16px); }
.gt-dsv-desc { margin: 0 0 16px; color: var(--gt-color-text-secondary, #606266); font-size: var(--gt-font-size-sm, 12px); }
.gt-dsv-card { padding: 4px 8px; }
</style>
