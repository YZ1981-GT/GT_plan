<template>
  <div class="gt-template-market">
    <div class="gt-page-header">
      <h2 class="gt-page-title">模板市场</h2>
      <el-input v-model="searchQuery" placeholder="搜索模板..." size="small" clearable
        :prefix-icon="Search" style="width: 240px" @keyup.enter="loadTemplates" />
    </div>

    <div class="gt-market-grid" v-loading="loading">
      <el-card
        v-for="t in templates"
        :key="t.id"
        class="gt-market-card"
        shadow="hover"
      >
        <template #header>
          <div class="gt-card-head">
            <span class="gt-card-name">{{ t.template_name }}</span>
            <el-tag size="small" :type="categoryTag(t.category)">{{ categoryLabel(t.category) }}</el-tag>
          </div>
        </template>
        <p class="gt-card-desc">{{ t.description || '暂无描述' }}</p>
        <div class="gt-card-meta">
          <span>版本 {{ t.version }}</span>
          <span>{{ fmtDate(t.updated_at) }}</span>
        </div>
        <div class="gt-card-actions">
          <el-button size="small" @click="previewTemplate(t)">预览</el-button>
          <el-button type="primary" size="small" @click="copyToMine(t)" :loading="t._copying">
            复制到我的模板
          </el-button>
        </div>
      </el-card>
      <el-empty v-if="!loading && templates.length === 0" description="暂无已发布的模板" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { listCustomTemplates, copyCustomTemplate } from '@/services/commonApi'

const loading = ref(false)
const templates = ref<any[]>([])
const searchQuery = ref('')

async function loadTemplates() {
  loading.value = true
  try {
    const params: any = { published: true }
    if (searchQuery.value) params.search = searchQuery.value
    templates.value = (await listCustomTemplates(params)).map((t: any) => ({ ...t, _copying: false }))
  } catch { templates.value = [] }
  finally { loading.value = false }
}

async function copyToMine(t: any) {
  t._copying = true
  try {
    await copyCustomTemplate(t.id)
    ElMessage.success('已复制到我的模板')
  } catch { ElMessage.error('复制失败') }
  finally { t._copying = false }
}

function previewTemplate(_t: any) {
  ElMessage.info('模板预览功能开发中')
}

function categoryTag(c: string) {
  const m: Record<string, string> = { industry: '', client: 'success', personal: 'warning' }
  return m[c] || 'info'
}
function categoryLabel(c: string) {
  const m: Record<string, string> = { industry: '行业专用', client: '客户专用', personal: '个人收藏' }
  return m[c] || c
}
function fmtDate(d: string) { return d ? new Date(d).toLocaleDateString('zh-CN') : '-' }

onMounted(loadTemplates)
</script>

<style scoped>
.gt-template-market { padding: var(--gt-space-4); }
.gt-page-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: var(--gt-space-4);
}
.gt-page-title { font-size: var(--gt-font-size-xl); font-weight: 600; margin: 0; }
.gt-market-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--gt-space-4);
}
.gt-market-card { border-radius: var(--gt-radius-md); }
.gt-card-head { display: flex; justify-content: space-between; align-items: center; }
.gt-card-name { font-weight: 600; font-size: var(--gt-font-size-base); }
.gt-card-desc {
  color: var(--gt-color-text-secondary); font-size: var(--gt-font-size-sm);
  margin: 0 0 var(--gt-space-3); line-height: 1.5; min-height: 40px;
}
.gt-card-meta {
  display: flex; justify-content: space-between;
  font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);
  margin-bottom: var(--gt-space-3);
}
.gt-card-actions { display: flex; gap: var(--gt-space-2); }
</style>
