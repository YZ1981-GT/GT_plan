<script setup lang="ts">
/**
 * ConsistencyPanel — 跨章节一致性校验结果展示面板
 *
 * 可折叠面板，按 severity 分组（error → warning → info）。
 * 章节引用渲染为可点击链接，导航到对应章节。
 * 无问题时显示成功指示器。
 *
 * Requirements: 3.4, 3.5, 3.6
 */
import { computed } from 'vue'

export interface ConsistencyResult {
  rule_id: string
  severity: 'error' | 'warning' | 'info'
  affected_chapters: string[]
  description: string
}

const props = defineProps<{
  results: ConsistencyResult[]
  loading?: boolean
  visible?: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-chapter', chapterId: string): void
  (e: 'close'): void
}>()

// ─── 按 severity 分组，error → warning → info ───
const groupedResults = computed(() => {
  const groups: { severity: string; label: string; type: string; items: ConsistencyResult[] }[] = []

  const errors = props.results.filter(r => r.severity === 'error')
  const warnings = props.results.filter(r => r.severity === 'warning')
  const infos = props.results.filter(r => r.severity === 'info')

  if (errors.length) groups.push({ severity: 'error', label: '错误', type: 'danger', items: errors })
  if (warnings.length) groups.push({ severity: 'warning', label: '警告', type: 'warning', items: warnings })
  if (infos.length) groups.push({ severity: 'info', label: '提示', type: 'info', items: infos })

  return groups
})

const hasResults = computed(() => props.results.length > 0)

// 章节 ID → 显示名称映射
const chapterLabels: Record<string, string> = {
  'A17-1-ch01': '第1章 项目概况',
  'A17-1-ch02': '第2章 审计范围',
  'A17-1-ch03': '第3章 重要性',
  'A17-1-ch04': '第4章 审计策略',
  'A17-1-ch05': '第5章 了解被审计单位',
  'A17-1-ch06': '第6章 重大错报风险',
  'A17-1-ch07': '第7章 集团审计',
  'A17-1-ch08': '第8章 财务报表分析',
  'A17-1-ch09': '第9章 会计政策',
  'A17-1-ch10': '第10章 持续经营',
  'A17-1-ch11': '第11章 关联方',
  'A17-1-ch12': '第12章 关键审计事项',
  'A17-1-ch13': '第13章 期后事项',
  'A17-1-ch14': '第14章 审计结论',
  'A17-1-ch15': '第15章 舞弊',
  'A17-1-ch16': '第16章 其他事项',
}

function getChapterLabel(chId: string): string {
  return chapterLabels[chId] || chId
}

function handleChapterClick(chapterId: string) {
  emit('navigate-chapter', chapterId)
}
</script>

<template>
  <div v-if="visible" class="consistency-panel">
    <!-- 加载中 -->
    <div v-if="loading" class="consistency-panel__loading">
      <el-icon class="is-loading"><i class="el-icon-loading" /></el-icon>
      <span>正在执行一致性校验...</span>
    </div>

    <!-- 无问题：成功指示器 -->
    <template v-else-if="!hasResults">
      <el-alert type="success" :closable="true" show-icon @close="emit('close')">
        <template #title>
          <span>一致性校验通过，未发现逻辑矛盾</span>
        </template>
      </el-alert>
    </template>

    <!-- 有问题：按 severity 分组展示 -->
    <template v-else>
      <el-collapse class="consistency-panel__results">
        <el-collapse-item
          v-for="group in groupedResults"
          :key="group.severity"
          :name="group.severity"
        >
          <template #title>
            <span class="consistency-panel__group-title">
              <el-tag :type="group.type as any" size="small" effect="dark">
                {{ group.label }}（{{ group.items.length }}）
              </el-tag>
            </span>
          </template>
          <div
            v-for="item in group.items"
            :key="item.rule_id"
            class="consistency-panel__item"
          >
            <div class="consistency-panel__item-desc">{{ item.description }}</div>
            <div class="consistency-panel__item-chapters">
              <span class="chapters-label">涉及章节：</span>
              <span
                v-for="ch in item.affected_chapters"
                :key="ch"
                class="chapter-link"
                @click="handleChapterClick(ch)"
              >{{ getChapterLabel(ch) }}</span>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
      <div class="consistency-panel__close">
        <el-button size="small" text @click="emit('close')">关闭面板</el-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.consistency-panel {
  margin-bottom: var(--gt-space-4, 16px);
  border: 1px solid var(--gt-color-border-light, #e4e7ed);
  border-radius: var(--gt-radius-sm, 4px);
  background: var(--gt-color-bg-elevated, #fafafa);
  padding: var(--gt-space-3, 12px);
}

.consistency-panel__loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  color: var(--gt-color-text-secondary, #909399);
  font-size: var(--gt-font-size-sm, 13px);
}

.consistency-panel__results :deep(.el-collapse-item__header) {
  font-size: var(--gt-font-size-sm, 13px);
  height: 36px;
  padding-left: 8px;
}

.consistency-panel__group-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.consistency-panel__item {
  padding: 8px 12px;
  border-bottom: 1px solid var(--gt-color-border-light, #f0f0f0);
}

.consistency-panel__item:last-child {
  border-bottom: none;
}

.consistency-panel__item-desc {
  font-size: var(--gt-font-size-sm, 13px);
  color: var(--gt-color-text, #303133);
  margin-bottom: 4px;
}

.consistency-panel__item-chapters {
  font-size: var(--gt-font-size-xs, 12px);
  color: var(--gt-color-text-secondary, #909399);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.chapters-label {
  color: var(--gt-color-text-tertiary, #c0c4cc);
}

.chapter-link {
  color: var(--gt-color-primary, #409eff);
  cursor: pointer;
  text-decoration: underline;
  text-decoration-style: dotted;
}

.chapter-link:hover {
  text-decoration-style: solid;
}

.consistency-panel__close {
  text-align: right;
  margin-top: 8px;
}
</style>
