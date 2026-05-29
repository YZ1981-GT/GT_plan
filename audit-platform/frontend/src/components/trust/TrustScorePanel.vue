<template>
  <el-drawer
    v-model="visible"
    title="数字信任度"
    size="640px"
    :destroy-on-close="false"
    direction="rtl"
  >
    <div v-loading="loading" style="min-height: 200px">
      <template v-if="data">
        <el-tabs v-model="activeTab">
          <el-tab-pane label="🔍 穿透链路" name="penetration">
            <PenetrationTab :entries="data.penetration" />
          </el-tab-pane>
          <el-tab-pane label="📝 修改历史" name="history">
            <HistoryTab :entries="data.history" />
          </el-tab-pane>
          <el-tab-pane label="🤖 AI 痕迹" name="ai">
            <AiTracesTab :entries="data.ai" />
          </el-tab-pane>
          <el-tab-pane label="∑ 公式依赖" name="formula" :disabled="!data.formula">
            <TrustFormulaTab :tree="data.formula" />
          </el-tab-pane>
          <el-tab-pane label="🔄 一致性" name="consistency">
            <ConsistencyTab :status="data.consistency" />
          </el-tab-pane>
        </el-tabs>
      </template>
      <el-empty v-else-if="!loading" description="暂无数据" />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/services/apiProxy'
import PenetrationTab from './PenetrationTab.vue'
import HistoryTab from './HistoryTab.vue'
import AiTracesTab from './AiTracesTab.vue'
import TrustFormulaTab from './TrustFormulaTab.vue'
import ConsistencyTab from './ConsistencyTab.vue'

const props = defineProps<{
  projectId: string
}>()

const route = useRoute()
const visible = ref(false)
const loading = ref(false)
const data = ref<any>(null)
const activeTab = ref('penetration')
const currentContext = ref('')

async function open(context: string) {
  if (!context) return
  currentContext.value = context
  visible.value = true
  loading.value = true
  data.value = null
  try {
    const pid = props.projectId || route.params.projectId
    const result = await api.get(`/api/projects/${pid}/trust-score`, {
      params: { context },
    })
    data.value = result.data || result
  } catch (e: any) {
    console.error('[TrustScorePanel] 加载失败:', e)
  } finally {
    loading.value = false
  }
}

function close() {
  visible.value = false
}

defineExpose({ open, close })
</script>
