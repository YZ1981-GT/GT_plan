<template>
  <div class="consistency-panel">
    <div class="panel-header">
      <h4>一致性复算</h4>
      <el-button size="small" type="primary" @click="runReplay" :loading="loading">执行复算</el-button>
    </div>

    <div v-if="result" class="replay-result">
      <!-- 总体状态 -->
      <el-alert
        :type="result.overall_status === 'consistent' ? 'success' : 'error'"
        :closable="false"
        show-icon
        style="margin-bottom:12px"
      >
        <template #title>
          {{ result.overall_status === 'consistent' ? '全部一致' : `存在 ${result.blocking_count} 项阻断级差异` }}
        </template>
      </el-alert>

      <!-- 五层链路可视化 -->
      <div class="layer-flow">
        <div
          v-for="(layer, idx) in result.layers" :key="idx"
          :class="['layer-node', layer.status]"
          @click="expandedLayer = expandedLayer === idx ? -1 : idx"
        >
          <div class="layer-header">
            <span class="layer-icon">{{ layer.status === 'consistent' ? '✅' : '❌' }}</span>
            <span class="layer-label">{{ layer.from }} → {{ layer.to }}</span>
            <el-badge v-if="layer.diffs?.length" :value="layer.diffs.length" type="danger" />
          </div>

          <!-- 展开差异明细 -->
          <div v-if="expandedLayer === idx && layer.diffs?.length" class="layer-diffs">
            <el-table :data="layer.diffs" size="small" border>
              <el-table-column prop="object_type" label="对象类型" width="100" />
              <el-table-column prop="object_id" label="对象ID" width="120" show-overflow-tooltip />
              <el-table-column prop="field" label="字段" width="180" />
              <el-table-column prop="expected" label="期望值" width="120" align="right" />
              <el-table-column prop="actual" label="实际值" width="120" align="right" />
              <el-table-column prop="diff" label="差异" width="100" align="right">
                <template #default="{ row }">
                  <span :class="row.severity === 'blocking' ? 'diff-blocking' : 'diff-warning'">
                    {{ row.diff?.toFixed(2) }}
                  </span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>
      </div>

      <div class="trace-info" v-if="result.trace_id">
        trace_id: {{ result.trace_id }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { replayConsistency } from '@/services/governanceApi'

const props = defineProps<{ projectId: string }>()

const loading = ref(false)
const result = ref<any>(null)
const expandedLayer = ref(-1)

async function runReplay() {
  loading.value = true
  try {
    result.value = await replayConsistency(props.projectId)
  } catch (e: any) {
    ElMessage.error('一致性复算失败')
  } finally { loading.value = false }
}
</script>

<style scoped>
.consistency-panel { padding: 16px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.layer-flow { display: flex; flex-direction: column; gap: 8px; }
.layer-node { border: 1px solid #eee; border-radius: 8px; padding: 12px; cursor: pointer; transition: all 0.2s; }
.layer-node:hover { border-color: var(--el-color-primary-light-5); }
.layer-node.consistent { border-left: 3px solid var(--el-color-success); }
.layer-node.inconsistent { border-left: 3px solid var(--el-color-danger); }
.layer-header { display: flex; align-items: center; gap: 8px; }
.layer-icon { font-size: var(--gt-font-size-md); }
.layer-label { flex: 1; font-size: var(--gt-font-size-sm); }
.layer-diffs { margin-top: 8px; }
.diff-blocking { color: var(--el-color-danger); font-weight: 600; }
.diff-warning { color: var(--el-color-warning); }
.trace-info { margin-top: 12px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
</style>
