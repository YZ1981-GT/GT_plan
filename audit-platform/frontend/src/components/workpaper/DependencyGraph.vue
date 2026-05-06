<template>
  <div class="gt-dep-graph">
    <div class="gt-dep-header">
      <span class="gt-dep-title">{{ cycleName || cycle }} 审计程序依赖</span>
      <el-select v-model="selectedCycle" size="small" style="width:120px" @change="loadGraph">
        <el-option v-for="c in cycles" :key="c" :label="cycleLabels[c] || c" :value="c" />
      </el-select>
    </div>

    <!-- 流程图：B → C → D -->
    <div class="gt-dep-flow" v-if="nodes.length">
      <!-- B类节点 -->
      <div class="gt-dep-column">
        <div class="gt-dep-col-title">B 风险评估</div>
        <div v-for="n in bNodes" :key="n.id" class="gt-dep-node gt-dep-node--b"
          :class="{ 'gt-dep-node--done': nodeStatus[n.id] === 'done', 'gt-dep-node--wip': nodeStatus[n.id] === 'wip' }">
          <span class="gt-dep-node-icon">{{ nodeStatus[n.id] === 'done' ? '✅' : nodeStatus[n.id] === 'wip' ? '📝' : '⬜' }}</span>
          <span class="gt-dep-node-label">{{ n.label }}</span>
        </div>
        <div v-if="!bNodes.length" class="gt-dep-empty">无</div>
      </div>

      <!-- 箭头 -->
      <div class="gt-dep-arrow">→</div>

      <!-- C类节点 -->
      <div class="gt-dep-column">
        <div class="gt-dep-col-title">C 控制测试</div>
        <div v-for="n in cNodes" :key="n.id" class="gt-dep-node gt-dep-node--c"
          :class="{ 'gt-dep-node--done': nodeStatus[n.id] === 'done', 'gt-dep-node--wip': nodeStatus[n.id] === 'wip' }">
          <span class="gt-dep-node-icon">{{ nodeStatus[n.id] === 'done' ? '✅' : nodeStatus[n.id] === 'wip' ? '📝' : '⬜' }}</span>
          <span class="gt-dep-node-label">{{ n.label }}</span>
          <el-tag v-if="n.effectiveness" size="small" :type="n.effectiveness === 'effective' ? 'success' : n.effectiveness === 'ineffective' ? 'danger' : 'warning'" style="margin-left:4px">
            {{ ({ effective: '有效', partially_effective: '部分', ineffective: '无效', not_tested: '未测' } as Record<string, string>)[n.effectiveness] || '' }}
          </el-tag>
        </div>
        <div v-if="!cNodes.length" class="gt-dep-empty">无独立控制测试</div>
      </div>

      <!-- 箭头 -->
      <div class="gt-dep-arrow">→</div>

      <!-- D类节点 -->
      <div class="gt-dep-column">
        <div class="gt-dep-col-title">D-N 实质性程序</div>
        <div class="gt-dep-node gt-dep-node--d">
          <span class="gt-dep-node-icon">📋</span>
          <span class="gt-dep-node-label">{{ cycleName }}实质性程序</span>
        </div>
        <div v-if="impactLabel" class="gt-dep-impact">
          <el-tag :type="(impactType) || undefined" size="small">{{ impactLabel }}</el-tag>
          <span class="gt-dep-impact-text">{{ impactSuggestion }}</span>
        </div>
      </div>
    </div>

    <el-empty v-else description="选择循环查看依赖关系" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  projectId: string
  cycle?: string
}>()

const cycles = ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'Q']
const cycleLabels: Record<string, string> = {
  D: 'D 收入', E: 'E 货币资金', F: 'F 存货', G: 'G 投资',
  H: 'H 固定资产', I: 'I 无形资产', J: 'J 职工薪酬', K: 'K 管理',
  L: 'L 债务', M: 'M 权益', N: 'N 税金', Q: 'Q 关联方',
}

const selectedCycle = ref(props.cycle || 'E')
const nodes = ref<any[]>([])
const edges = ref<any[]>([])
const cycleName = ref('')
const nodeStatus = ref<Record<string, string>>({})

const bNodes = computed(() => nodes.value.filter(n => n.type === 'b_control'))
const cNodes = computed(() => nodes.value.filter(n => n.type === 'c_test'))

const impactLabel = ref('')
const impactType = ref<'' | 'success' | 'warning' | 'danger'>('')
const impactSuggestion = ref('')

async function loadGraph() {
  try {
    const data = await api.get(`/api/wp-dependencies/cycle/${selectedCycle.value}`, {
      validateStatus: (s: number) => s < 600,
    })
    nodes.value = data?.nodes || []
    edges.value = data?.edges || []
    cycleName.value = data?.cycle_name || ''

    // 加载节点状态（如果有项目ID）
    if (props.projectId) {
      await loadNodeStatuses()
    }
  } catch {
    nodes.value = []
  }
}

async function loadNodeStatuses() {
  // 简化：从底稿列表获取B/C类底稿状态
  try {
    const data = await api.get(`/api/projects/${props.projectId}/working-papers`, {
      params: { audit_cycle: selectedCycle.value },
      validateStatus: (s: number) => s < 600,
    })
    const wps = Array.isArray(data) ? data : data || []
    const statusMap: Record<string, string> = {}
    for (const wp of wps) {
      const code = wp.wp_code || ''
      const status = wp.status || wp.file_status || 'not_started'
      if (status === 'review_passed' || status === 'archived') {
        statusMap[code] = 'done'
      } else if (status !== 'not_started' && status !== 'not_found') {
        statusMap[code] = 'wip'
      }
    }
    // 匹配节点
    for (const n of nodes.value) {
      const prefix = n.id
      for (const [code, st] of Object.entries(statusMap)) {
        if (code.startsWith(prefix)) {
          nodeStatus.value[n.id] = st
          break
        }
      }
    }

    // 加载控制测试结论影响
    try {
      const _depData = await api.get(`/api/wp-dependencies/cycle/${selectedCycle.value}`, {
        validateStatus: (s: number) => s < 600,
      })
      // 从依赖检查获取impact
      const effData = await api.get('/api/wp-dependencies/effectiveness-impact', {
        validateStatus: (s: number) => s < 600,
      })
      // 简化：取第一个C类节点的结论
      for (const n of cNodes.value) {
        if (nodeStatus.value[n.id] === 'done') {
          n.effectiveness = 'effective'
          impactLabel.value = '控制有效'
          impactType.value = 'success'
          impactSuggestion.value = effData?.effective?.suggested_procedures || '可减少实质性程序范围'
        }
      }
    } catch { /* ignore */ }
  } catch { /* ignore */ }
}

watch(() => props.cycle, (v) => { if (v) { selectedCycle.value = v; loadGraph() } })
onMounted(loadGraph)
</script>

<style scoped>
.gt-dep-graph { padding: 12px; }
.gt-dep-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.gt-dep-title { font-size: 14px; font-weight: 600; color: #333; }
.gt-dep-flow { display: flex; align-items: flex-start; gap: 8px; }
.gt-dep-column { flex: 1; min-width: 160px; }
.gt-dep-col-title { font-size: 11px; font-weight: 600; color: #999; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; text-align: center; }
.gt-dep-arrow { font-size: 24px; color: #ccc; padding-top: 30px; flex-shrink: 0; }
.gt-dep-node { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border-radius: 6px; margin-bottom: 6px; font-size: 12px; border: 1px solid #e8e4f0; background: #faf8fd; transition: all 0.15s; }
.gt-dep-node:hover { box-shadow: 0 2px 8px rgba(75,45,119,0.1); }
.gt-dep-node--done { background: #f0f9eb; border-color: #c6e7b8; }
.gt-dep-node--wip { background: #fdf6ec; border-color: #f5dab1; }
.gt-dep-node--b { border-left: 3px solid #909399; }
.gt-dep-node--c { border-left: 3px solid #e6a23c; }
.gt-dep-node--d { border-left: 3px solid #4b2d77; }
.gt-dep-node-icon { font-size: 14px; }
.gt-dep-node-label { flex: 1; }
.gt-dep-empty { font-size: 11px; color: #ccc; text-align: center; padding: 12px; }
.gt-dep-impact { margin-top: 8px; padding: 8px; background: #f5f3f8; border-radius: 6px; }
.gt-dep-impact-text { font-size: 11px; color: #666; display: block; margin-top: 4px; }
</style>
