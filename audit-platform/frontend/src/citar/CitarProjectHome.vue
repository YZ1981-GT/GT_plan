<template>
  <div class="shell-home">
    <p class="shell-home__title">请从左侧选择要进入的环节</p>
    <p class="shell-home__hint">
      数据导入 → 账务查询 → 底稿映射 → 调整分录 → 试算平衡表 → 审定报表 → 税审底稿 → 税审报告
      <br />
      本页后续将显示项目各环节的进度。
    </p>
  </div>
</template>

<script setup lang="ts">
/** 项目空页（移植自 CITAR src/screens/shell/ProjectHomeScreen.tsx）：从项目列表点进来先到这里 */
defineOptions({ name: 'CitarProjectHome' })
</script>

<style scoped src="./styles/shell-home.css"></style>
