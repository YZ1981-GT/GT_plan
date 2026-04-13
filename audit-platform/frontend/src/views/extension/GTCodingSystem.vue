<template>
  <div class="gt-coding-page">
    <div class="gt-page-header">
      <h2 class="gt-page-title">致同底稿编码体系</h2>
      <el-button size="small" @click="loadCoding" :loading="loading">刷新</el-button>
    </div>

    <div class="gt-coding-layout">
      <!-- 左侧编码树 -->
      <div class="gt-coding-tree-panel">
        <GTWPCodingTree :data="codingData" @node-click="onNodeClick" />
      </div>

      <!-- 右侧详情 -->
      <div class="gt-coding-detail">
        <template v-if="selectedNode">
          <el-descriptions :column="1" border size="small" title="编码详情">
            <el-descriptions-item label="编码前缀">{{ selectedNode.code_prefix }}</el-descriptions-item>
            <el-descriptions-item label="编码范围">{{ selectedNode.code_range }}</el-descriptions-item>
            <el-descriptions-item label="审计循环">{{ selectedNode.cycle_name }}</el-descriptions-item>
            <el-descriptions-item label="底稿类型">
              <el-tag size="small">{{ wpTypeLabel(selectedNode.wp_type) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="描述">{{ selectedNode.description || '-' }}</el-descriptions-item>
          </el-descriptions>
        </template>
        <el-empty v-else description="点击左侧编码查看详情" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import GTWPCodingTree from '@/components/extension/GTWPCodingTree.vue'
import http from '@/utils/http'

const loading = ref(false)
const codingData = ref<any[]>([])
const selectedNode = ref<any>(null)

async function loadCoding() {
  loading.value = true
  try {
    const { data } = await http.get('/api/gt-coding')
    codingData.value = data.data ?? data ?? []
  } catch { codingData.value = [] }
  finally { loading.value = false }
}

function onNodeClick(node: any) {
  selectedNode.value = node
}

function wpTypeLabel(t: string) {
  const m: Record<string, string> = {
    preliminary: 'B-初步业务活动',
    risk_assessment: 'B-风险评估',
    control_test: 'C-控制测试',
    substantive: 'D-N 实质性程序',
    completion: 'A-完成阶段',
    specific: 'S-特定项目',
    general: 'T-通用',
    permanent: 'Z-永久性档案',
  }
  return m[t] || t
}

onMounted(loadCoding)
</script>

<style scoped>
.gt-coding-page { padding: var(--gt-space-4); height: 100%; display: flex; flex-direction: column; }
.gt-page-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: var(--gt-space-4);
}
.gt-page-title { font-size: var(--gt-font-size-xl); font-weight: 600; margin: 0; }
.gt-coding-layout { display: flex; gap: var(--gt-space-4); flex: 1; min-height: 0; }
.gt-coding-tree-panel {
  width: 360px; flex-shrink: 0; overflow: auto;
  border: 1px solid var(--gt-color-border-light); border-radius: var(--gt-radius-md);
  padding: var(--gt-space-3);
}
.gt-coding-detail { flex: 1; }
</style>
