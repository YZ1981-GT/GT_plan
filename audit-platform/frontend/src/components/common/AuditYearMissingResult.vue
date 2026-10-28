<template>
  <!-- 项目还没有审计年度：整页不读数据、不渲染底稿（spec audit-year-calendar-fallback-ratchet）。
       loading=true 时项目信息还没取回，先显示占位，别把「还没取到」说成「没设置」；
       failed=true 是项目信息没取到（网络 / 服务 / 权限），同样不能说成「没设置」，给重试。 -->
  <div v-if="loading" class="gt-audit-year-loading">正在读取项目审计年度...</div>
  <el-result v-else-if="failed" icon="warning" title="读取项目信息失败">
    <template #sub-title>
      <span>未能取到项目的审计年度，底稿暂不打开，请稍后重试。</span>
    </template>
    <template #extra>
      <el-button type="primary" @click="emit('retry')">重试</el-button>
      <el-button v-if="backable" @click="emit('back')">← 返回</el-button>
    </template>
  </el-result>
  <el-result v-else icon="info" title="未设置审计年度">
    <template #sub-title>
      <span>{{ message }}</span>
    </template>
    <template v-if="backable" #extra>
      <!-- 宿主的工具栏在年度缺失时不渲染（版本 / 查账 / 面板都要年度），返回入口放这里 -->
      <el-button @click="emit('back')">← 返回</el-button>
    </template>
  </el-result>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  loading?: boolean
  /** 项目信息读取失败（与「项目没填年度」分开显示） */
  failed?: boolean
  message?: string
  /** 是否显示「← 返回」（点击发 back 事件，由宿主决定去哪） */
  backable?: boolean
}>(), {
  loading: false,
  failed: false,
  message: '请先在项目基本信息中填写审计年度，再打开底稿读取数据。',
  backable: true,
})

const emit = defineEmits<{ (e: 'back'): void; (e: 'retry'): void }>()
</script>

<style scoped>
.gt-audit-year-loading {
  padding: 40px 0;
  text-align: center;
  color: var(--el-text-color-secondary);
}
</style>
