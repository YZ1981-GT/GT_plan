<!--
  ProjectEntryHome — 进入项目后的落地页。

  点击项目列表里的项目节点后落在这里：中央只给流程提示，
  具体环节由用户从左侧项目子菜单（ThreeColumnLayout 的 PROJECT_STAGES）选择。

  🔴 本页刻意不做数据请求：它是「选环节」的分流页，不是看板。
     项目名称 / 审核年度 / 三个角色由布局层的 ProjectEntryBar 展示，不在本页重复。
-->
<template>
  <div class="gt-pe-home">
    <div class="gt-pe-home__box">
      <h2 class="gt-pe-home__title">请从左侧选择要进入的环节</h2>
      <p class="gt-pe-home__flow">{{ flowText }}</p>
      <p class="gt-pe-home__hint">本页后续将展示项目各环节的进度。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { projectStageFlowText } from '@/constants/projectStages'

defineOptions({ name: 'ProjectEntryHome' })

// 流程文案与左侧子菜单同源（PROJECT_STAGES），改菜单即改这里
const flowText = projectStageFlowText()
</script>

<style scoped>
.gt-pe-home {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.gt-pe-home__box {
  text-align: center;
  padding: 0 var(--gt-space-4);
}
.gt-pe-home__title {
  margin: 0;
  font-size: var(--gt-font-size-lg, 16px);
  font-weight: 600;
  color: var(--gt-color-text, #303133);
}
.gt-pe-home__flow {
  margin: 14px 0 0;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary, #606266);
}
.gt-pe-home__hint {
  margin: 4px 0 0;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-primary, #4b2d77);
}
</style>
