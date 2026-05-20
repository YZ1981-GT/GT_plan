<template>
  <div class="review-opinion-list">
    <!-- 空状态：openReviews 为 null 或 total === 0 -->
    <template v-if="!openReviews || openReviews.total === 0">
      <el-empty
        :image-size="64"
        description="所有复核意见已解决"
      />
    </template>

    <!-- 正常状态 -->
    <template v-else>
      <!-- 顶部统计：总未解决数 + 按层级分布 -->
      <div class="review-stats-header">
        <div class="review-total">
          <span class="review-total-count">{{ openReviews.total }}</span>
          <span class="review-total-label">条未解决</span>
        </div>
        <div class="review-layer-tags">
          <el-tag
            v-for="(count, layer) in openReviews.by_layer"
            :key="layer"
            :type="getLayerTagType(layer as string)"
            size="small"
            effect="plain"
            class="review-layer-tag"
          >
            {{ LAYER_LABELS[layer as string] || layer }} {{ count }}
          </el-tag>
        </div>
      </div>

      <!-- 列表 -->
      <el-scrollbar max-height="320px" class="review-list-scrollbar">
        <div class="review-list">
          <div
            v-for="item in openReviews.items"
            :key="item.id"
            class="review-item"
            @click="navigateToWorkpaper(item)"
          >
            <div class="review-item-header">
              <el-tag
                :type="getLayerTagType(item.review_layer)"
                size="small"
                effect="dark"
                class="review-item-layer"
              >
                {{ LAYER_LABELS[item.review_layer] || item.review_layer }}
              </el-tag>
              <span class="review-item-wp-code">{{ item.wp_code }}</span>
              <span class="review-item-time">{{ formatTime(item.created_at) }}</span>
            </div>
            <div class="review-item-summary">{{ item.summary }}</div>
          </div>
        </div>
      </el-scrollbar>
    </template>
  </div>
</template>

<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import type { OpenReviewsData, ReviewItem } from '@/composables/useDashboardData'

defineProps<{
  openReviews: OpenReviewsData | null
}>()

const router = useRouter()
const route = useRoute()

/** 层级标签映射 */
const LAYER_LABELS: Record<string, string> = {
  L5: '合伙人',
  L4: '经理',
  L3: '主管',
  L2: '高级',
  L1: '助理',
}

/**
 * 根据层级返回 el-tag 类型
 * L5/L4 → danger（高优先级）
 * L3 → warning
 * L2/L1 → info
 */
function getLayerTagType(layer: string): 'success' | 'warning' | 'danger' | 'info' {
  if (layer === 'L5' || layer === 'L4') return 'danger'
  if (layer === 'L3') return 'warning'
  return 'info'
}

/**
 * 格式化时间：显示 YYYY-MM-DD HH:mm
 */
function formatTime(isoStr: string): string {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  if (isNaN(d.getTime())) return isoStr
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${day} ${h}:${min}`
}

/**
 * 点击复核意见 → 跳转到对应底稿 sheet + cell
 */
function navigateToWorkpaper(item: ReviewItem) {
  const projectId = route.params.projectId as string
  const query: Record<string, string> = { highlight: item.wp_code }
  if (item.sheet_name) query.sheet = item.sheet_name
  if (item.cell_ref) query.cell = item.cell_ref
  router.push({
    name: 'WorkpaperList',
    params: { projectId },
    query,
  })
}
</script>

<style scoped>
.review-opinion-list {
  width: 100%;
}

/* 顶部统计 */
.review-stats-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}

.review-total {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.review-total-count {
  font-size: 24px;
  font-weight: 700;
  color: var(--el-color-warning, #e6a23c);
}

.review-total-label {
  font-size: 13px;
  color: var(--gt-color-text-secondary, #909399);
}

.review-layer-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.review-layer-tag {
  font-size: 11px;
}

/* 列表 */
.review-list-scrollbar {
  margin-top: 4px;
}

.review-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.review-item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.review-item:hover {
  background-color: rgba(75, 45, 119, 0.04);
}

.review-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.review-item-layer {
  flex-shrink: 0;
}

.review-item-wp-code {
  font-size: 12px;
  font-weight: 500;
  color: var(--gt-color-text-primary, #303133);
}

.review-item-time {
  margin-left: auto;
  font-size: 11px;
  color: var(--gt-color-text-secondary, #909399);
  white-space: nowrap;
}

.review-item-summary {
  font-size: 13px;
  color: var(--gt-color-text-primary, #303133);
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
