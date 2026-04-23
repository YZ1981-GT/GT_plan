<template>
  <div class="app-wrapper">
    <el-menu
      :default-active="activeIndex"
      class="top-nav"
      mode="horizontal"
      :router="true"
      background-color="#545c64"
      text-color="#fff"
      active-text-color="#ffd04b"
    >
      <el-menu-item index="/reports/unadjusted">
        <el-icon><Document /></el-icon>未审报表
      </el-menu-item>
      <el-menu-item index="/reports/adjusted">
        <el-icon><DocumentChecked /></el-icon>审定报表
      </el-menu-item>
      <el-menu-item index="/reports/trial-balance">
        <el-icon><List /></el-icon>试算平衡表
      </el-menu-item>
      <el-menu-item index="/reports/adjustment-entries">
        <el-icon><EditPen /></el-icon>调整分录
      </el-menu-item>
      <el-sub-menu index="/ai">
        <template #title>
          <el-icon><ChatDotRound /></el-icon>AI 功能
        </template>
        <el-menu-item index="/ai/chat">AI 问答</el-menu-item>
        <el-menu-item index="/ai/document">文档识别</el-menu-item>
        <el-menu-item index="/ai/contract">合同分析</el-menu-item>
        <el-menu-item index="/ai/evidence">证据链</el-menu-item>
        <el-menu-item index="/ai/workpaper">底稿填充</el-menu-item>
      </el-sub-menu>
    </el-menu>
    <div class="page-content">
      <router-view />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Document, DocumentChecked, List, EditPen, ChatDotRound } from '@element-plus/icons-vue'

const route = useRoute()
const activeIndex = computed(() => route.path)
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  width: 100vw;
  height: 100vh;
}

.app-wrapper {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.top-nav {
  flex-shrink: 0;
}

.page-content {
  flex: 1;
  overflow: auto;
}
</style>
