<template>
  <div class="gt-ai-insights-dashboard">
    <div class="panel-header">
      <h3>📊 AI 洞察中心</h3>
      <button class="btn-refresh" @click="loadInsights">🔄</button>
    </div>
    <div class="insights-grid">
      <div
        v-for="insight in insights"
        :key="insight.id"
        class="insight-card"
        :class="`risk-${insight.risk_level}`"
      >
        <div class="insight-header">
          <span class="insight-type">{{ insight.insight_type }}</span>
          <span :class="['risk-dot', insight.risk_level]"></span>
        </div>
        <div class="insight-title">{{ insight.title }}</div>
        <div class="insight-desc">{{ insight.description }}</div>
        <div class="insight-meta">
          <span v-if="insight.related_entities?.length">
            关联：{{ insight.related_entities.join(', ') }}
          </span>
        </div>
      </div>
      <div v-if="insights.length === 0" class="empty">暂无AI洞察</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { aiContentApi } from '@/api'

const props = defineProps({ projectId: { type: String, required: true } })
const insights = ref([])

async function loadInsights() {
  const res = await aiContentApi.listInsights(props.projectId)
  insights.value = res.data || []
}

onMounted(loadInsights)
</script>

<style scoped>
.gt-ai-insights-dashboard { padding: 16px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.panel-header h3 { margin: 0; font-size: 16px; }
.btn-refresh { background: none; border: none; cursor: pointer; font-size: 16px; }
.insights-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.insight-card { border: 1px solid #eee; border-radius: 8px; padding: 12px; cursor: pointer; transition: transform 0.2s; }
.insight-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
.insight-card.risk-high { border-left: 3px solid #ff4d4f; }
.insight-card.risk-medium { border-left: 3px solid #faad14; }
.insight-card.risk-low { border-left: 3px solid #52c41a; }
.insight-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.insight-type { font-size: 11px; color: #999; text-transform: uppercase; }
.risk-dot { width: 8px; height: 8px; border-radius: 50%; }
.risk-dot.high { background: #ff4d4f; }
.risk-dot.medium { background: #faad14; }
.risk-dot.low { background: #52c41a; }
.insight-title { font-weight: 600; font-size: 13px; margin-bottom: 4px; color: #333; }
.insight-desc { font-size: 12px; color: #666; line-height: 1.4; margin-bottom: 6px; }
.insight-meta { font-size: 11px; color: #999; }
.empty { grid-column: 1/-1; text-align: center; padding: 20px; color: #999; }
</style>
