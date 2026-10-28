<!--
  WorkpaperShortLink.vue — 底稿短链 /workpapers/:wpId（spec acnr-foundation-defect-closure T16 / RV7.5-01）

  按底稿 id 查出所属项目后 router.replace 到底稿编辑器（保留 sheet / cell 等查询串）；
  无权 / 不存在 / 回收站 / 网络错误时显示中文原因与下一步，不跳转。
-->
<template>
  <div class="gt-wp-short-link" data-testid="wp-short-link">
    <div v-if="!failure" class="gt-wp-short-link__loading" data-testid="wp-short-link-loading">正在打开底稿…</div>
    <el-result v-else icon="warning" :title="failure.reason" :sub-title="failure.hint" data-testid="wp-short-link-failure">
      <template #extra>
        <el-button data-testid="wp-short-link-back" @click="goBack">返回上一页</el-button>
        <el-button type="primary" data-testid="wp-short-link-projects" @click="goProjects">进入项目列表</el-button>
      </template>
    </el-result>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { resolveShortLink } from '@/views/composables/workpaperShortLink'

const route = useRoute()
const router = useRouter()
const failure = ref<{ reason: string; hint: string } | null>(null)

onMounted(async () => {
  const wpId = String(route.params.wpId || '')
  const result = await resolveShortLink(wpId, route.query)
  if (result.ok) await router.replace(result.target)
  else failure.value = { reason: result.reason, hint: result.hint }
})

function goBack() {
  if (window.history.length > 1) router.back()
  else void router.push({ name: 'Projects' })
}

function goProjects() {
  void router.push({ name: 'Projects' })
}
</script>

<style scoped>
.gt-wp-short-link {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}
.gt-wp-short-link__loading {
  color: var(--gt-color-text-secondary);
}
</style>
