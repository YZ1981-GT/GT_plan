<template>
  <div class="gt-review-recommend">
    <div class="gt-recommend-header">
      <span class="gt-recommend-title">推荐复核人</span>
      <el-tag size="small" type="info">Top {{ candidates.length }}</el-tag>
    </div>

    <div v-if="loading" v-loading="true" style="min-height: 120px;" />
    <div v-else-if="candidates.length === 0" class="gt-recommend-empty">
      <el-empty description="暂无推荐候选人" :image-size="60" />
    </div>
    <div v-else class="gt-recommend-list">
      <div
        v-for="(candidate, index) in candidates"
        :key="candidate.user_id"
        class="gt-recommend-item"
      >
        <div class="gt-recommend-rank">{{ index + 1 }}</div>
        <div class="gt-recommend-info">
          <div class="gt-recommend-name">{{ candidate.user_name }}</div>
          <div class="gt-recommend-scores">
            <el-tooltip content="综合评分">
              <el-tag size="small" :type="index === 0 ? 'success' : 'info'">
                {{ (candidate.score * 100).toFixed(0) }}分
              </el-tag>
            </el-tooltip>
            <span class="gt-score-detail">
              历史 {{ (candidate.history_score * 100).toFixed(0) }}%
              · 余量 {{ (candidate.capacity_score * 100).toFixed(0) }}%
              · 专长 {{ (candidate.expertise_score * 100).toFixed(0) }}%
            </span>
          </div>
          <div class="gt-recommend-meta">
            本周 {{ candidate.current_week_hours }}h · 本循环复核 {{ candidate.review_count_in_cycle }} 次
          </div>
        </div>
        <el-button
          type="primary"
          size="small"
          @click="$emit('select', candidate.user_id)"
        >
          选择
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { api } from '@/services/apiProxy'

interface Candidate {
  user_id: string
  user_name: string
  score: number
  history_score: number
  capacity_score: number
  expertise_score: number
  current_week_hours: number
  review_count_in_cycle: number
}

const props = defineProps<{
  projectId: string
  cycle: string
  wpCode?: string
}>()

defineEmits<{
  (e: 'select', userId: string): void
}>()

const loading = ref(false)
const candidates = ref<Candidate[]>([])

async function loadRecommendations() {
  if (!props.projectId || !props.cycle) return
  loading.value = true
  try {
    const params = new URLSearchParams({ cycle: props.cycle })
    if (props.wpCode) params.set('wp_code', props.wpCode)
    const res = await api.get(
      `/api/projects/${props.projectId}/review-recommend?${params.toString()}`
    ) as { candidates: Candidate[] }
    candidates.value = res.candidates || []
  } catch {
    candidates.value = []
  } finally {
    loading.value = false
  }
}

watch(() => [props.projectId, props.cycle], loadRecommendations)
onMounted(loadRecommendations)
</script>

<style scoped>
.gt-review-recommend {
  border: 1px solid var(--gt-color-border-light);
  border-radius: var(--gt-radius-md);
  padding: 16px;
  background: var(--gt-color-bg-white);
}
.gt-recommend-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.gt-recommend-title { font-weight: 600; font-size: 14px; }
.gt-recommend-list { display: flex; flex-direction: column; gap: 12px; }
.gt-recommend-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--gt-color-border-light);
  border-radius: var(--gt-radius-sm);
  transition: background 0.2s;
}
.gt-recommend-item:hover { background: var(--gt-color-bg-hover); }
.gt-recommend-rank {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--gt-color-primary, #4b2d77);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}
.gt-recommend-info { flex: 1; min-width: 0; }
.gt-recommend-name { font-weight: 500; margin-bottom: 4px; }
.gt-recommend-scores { display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }
.gt-score-detail { font-size: 11px; color: var(--gt-color-text-secondary); }
.gt-recommend-meta { font-size: 12px; color: var(--gt-color-text-tertiary); }
.gt-recommend-empty { padding: 20px; text-align: center; }
</style>
