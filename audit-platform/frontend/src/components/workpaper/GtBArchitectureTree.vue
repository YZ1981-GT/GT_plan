<!--
  GtBArchitectureTree.vue — B 类目录的底稿审计工作流图

  按 design §11.9 实现（2026-06-02 重构 v2）：
  - 按审计逻辑分 4 阶段泳道：① 程序计划 → ② 科目审定 → ③ 实质性程序 → ④ 披露与调整
  - 阶段间向下流程箭头串联（体现审计先后逻辑）
  - 阶段内 sheet 用多栏卡片 grid（紧凑 + 响应式）
  - 点击卡片 emit navigate(sheetName) → 父组件切换 sheet
  - 全 GT 紫令牌；当前激活 sheet 高亮

  数据源：B-Index sheet 的 navigation_rows（content / index_ref / component_type）
  锚定 spec workpaper-editor-slimdown Task 17.8 / US-16
-->

<template>
  <div class="gt-b-arch">
    <template v-if="stages.length > 0">
      <div
        v-for="(stage, sIdx) in stages"
        :key="stage.key"
        class="gt-b-arch__stage"
      >
        <!-- 阶段标题 -->
        <div class="gt-b-arch__stage-head">
          <span class="gt-b-arch__stage-badge">{{ sIdx + 1 }}</span>
          <span class="gt-b-arch__stage-title">{{ stage.title }}</span>
          <span class="gt-b-arch__stage-count">{{ stage.nodes.length }} 项</span>
        </div>

        <!-- 阶段内 sheet 卡片网格 -->
        <div class="gt-b-arch__grid">
          <div
            v-for="node in stage.nodes"
            :key="node.id"
            class="gt-b-arch__card"
            :class="{ 'is-active': node.sheetName === activeSheet }"
            @click="onNodeClick(node)"
          >
            <div class="gt-b-arch__card-top">
              <span class="gt-b-arch__card-icon">{{ node.icon }}</span>
              <GtIndexChip
                v-if="node.indexRef"
                :value="node.indexRef"
                :validate="false"
                class="gt-b-arch__chip"
              />
            </div>
            <span class="gt-b-arch__name" :title="node.name">{{ node.name }}</span>
            <el-tag
              v-if="node.status"
              :type="statusType(node.status)"
              size="small"
              effect="plain"
              class="gt-b-arch__status"
            >
              {{ statusLabel(node.status) }}
            </el-tag>
          </div>
        </div>

        <!-- 阶段间流程箭头 -->
        <div
          v-if="sIdx < stages.length - 1"
          class="gt-b-arch__flow-arrow"
        >
          <el-icon><Bottom /></el-icon>
        </div>
      </div>
    </template>

    <el-empty
      v-else
      description="暂无底稿架构数据"
      :image-size="60"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Bottom } from '@element-plus/icons-vue'
import GtIndexChip from './GtIndexChip.vue'

// ─── Props / Emits ───
const props = defineProps<{
  wpId?: string
  projectId?: string
  /** 当前激活的 sheet（高亮用） */
  activeSheet?: string
  /** B-Index sheet 的 html_data（含 navigation_rows） */
  htmlData?: Record<string, any>
}>()

const emit = defineEmits<{
  navigate: [sheetName: string]
}>()

// ─── Types ───
interface ArchNode {
  id: string
  sheetName: string
  indexRef: string
  name: string
  status?: string
  componentType: string
  icon: string
}

interface Stage {
  key: string
  title: string
  nodes: ArchNode[]
}

// ─── componentType → 图标 ───
const ICON_MAP: Record<string, string> = {
  'a-program-console': '📋',
  'b-index': '🗂️',
  'c-note-table': '📝',
  'd-form-table': '📑',
  'd-form-paragraph': '📄',
  'd-form-qa': '❓',
  'd-form-confirmation': '✉️',
  'd-form-review': '✍️',
  'e-control-test': '🧪',
  'h-static-doc': '📖',
  univer: '📊',
  skip: '⏭️',
}

// ─── 解析 navigation_rows → 节点 ───
const allNodes = computed<ArchNode[]>(() => {
  const rows = props.htmlData?.navigation_rows
  if (!Array.isArray(rows)) return []

  return rows
    .filter((row) => row && typeof row === 'object')
    .map((row, i) => {
      const ct = row.component_type || 'skip'
      const name = row.content || row.sheet_name || row.label || ''
      return {
        id: `arch-${i}`,
        sheetName: row.content || row.sheet_name || '',
        indexRef: row.index_ref || row.wp_code || '',
        name,
        status: row.status || '',
        componentType: ct,
        icon: ICON_MAP[ct] || '📄',
      }
    })
    .filter((n) => n.name)
})

// ─── 按审计阶段分组（4 泳道） ───
//   ① 程序计划：a-program-console
//   ② 科目审定：sheet 名含「审定表」
//   ③ 实质性程序：明细表/检查表/分析（univer + d-form-* 等，排除审定/调整）
//   ④ 披露与调整：c-note-table（附注）+ sheet 名含「调整分录」
function classifyStage(node: ArchNode): 'plan' | 'finalize' | 'substantive' | 'disclosure' {
  const name = node.name
  if (node.componentType === 'a-program-console') return 'plan'
  if (name.includes('审定表')) return 'finalize'
  if (node.componentType === 'c-note-table' || name.includes('附注') || name.includes('披露')) {
    return 'disclosure'
  }
  if (name.includes('调整分录') || name.includes('调整汇总')) return 'disclosure'
  return 'substantive'
}

const STAGE_META: { key: string; title: string }[] = [
  { key: 'plan', title: '审计计划' },
  { key: 'finalize', title: '科目审定' },
  { key: 'substantive', title: '实质性程序' },
  { key: 'disclosure', title: '披露与调整' },
]

const stages = computed<Stage[]>(() => {
  const buckets: Record<string, ArchNode[]> = {
    plan: [], finalize: [], substantive: [], disclosure: [],
  }
  for (const node of allNodes.value) {
    buckets[classifyStage(node)].push(node)
  }
  // 仅返回非空阶段，保持固定顺序
  return STAGE_META
    .map((m) => ({ key: m.key, title: m.title, nodes: buckets[m.key] }))
    .filter((s) => s.nodes.length > 0)
})

// ─── Methods ───
function statusType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  switch (status) {
    case 'completed': return 'success'
    case 'in_progress': return 'warning'
    case 'pending': return 'info'
    case 'not_applicable': return 'danger'
    default: return 'info'
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'completed': return '已完成'
    case 'in_progress': return '进行中'
    case 'pending': return '待执行'
    case 'not_applicable': return '已裁剪'
    default: return status
  }
}

function onNodeClick(node: ArchNode) {
  if (node.sheetName) {
    emit('navigate', node.sheetName)
  }
}
</script>

<style scoped>
.gt-b-arch {
  padding: 8px 4px;
}

/* ─── 阶段泳道 ─── */
.gt-b-arch__stage {
  position: relative;
}

.gt-b-arch__stage-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.gt-b-arch__stage-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--gt-color-primary, #4b2d77);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.gt-b-arch__stage-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.gt-b-arch__stage-count {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
  background: var(--gt-color-primary-bg, #f4f0fa);
  padding: 1px 8px;
  border-radius: 10px;
}

/* ─── 卡片网格（多栏响应式） ─── */
.gt-b-arch__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
  padding-left: 30px;
  position: relative;
}

/* 阶段左侧引导竖线 */
.gt-b-arch__grid::before {
  content: '';
  position: absolute;
  left: 10px;
  top: -4px;
  bottom: -4px;
  width: 2px;
  background: var(--gt-color-border-purple, #e8e4f0);
}

.gt-b-arch__card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 8px;
  background: var(--gt-color-bg-white, #fff);
  cursor: pointer;
  transition: all 0.2s;
}

.gt-b-arch__card:hover {
  border-color: var(--gt-color-primary, #4b2d77);
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.12);
  transform: translateY(-2px);
}

.gt-b-arch__card.is-active {
  border-color: var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary-bg, #f4f0fa);
  box-shadow: 0 0 0 1px var(--gt-color-primary, #4b2d77);
}

.gt-b-arch__card-top {
  display: flex;
  align-items: center;
  gap: 6px;
}

.gt-b-arch__card-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.gt-b-arch__chip {
  flex-shrink: 0;
}

/* 索引号 chip 强制 GT 紫（el-tag--primary 默认蓝，按致同规范覆盖） */
.gt-b-arch__card :deep(.el-tag),
.gt-b-arch__card :deep(.el-tag--primary) {
  --el-tag-bg-color: var(--gt-color-primary-bg, #f4f0fa);
  --el-tag-border-color: var(--gt-color-border-purple-light, #d8b8ee);
  --el-tag-text-color: var(--gt-color-primary, #4b2d77);
  background-color: var(--gt-color-primary-bg, #f4f0fa) !important;
  border-color: var(--gt-color-border-purple-light, #d8b8ee) !important;
  color: var(--gt-color-primary, #4b2d77) !important;
}

/* 状态标签保留语义色（不强制紫） */
.gt-b-arch__status {
  align-self: flex-start;
}
.gt-b-arch__card :deep(.gt-b-arch__status.el-tag) {
  --el-tag-bg-color: unset;
  background-color: unset !important;
}

.gt-b-arch__name {
  font-size: 13px;
  line-height: 1.4;
  color: var(--gt-color-text-primary, #303133);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ─── 阶段间流程箭头 ─── */
.gt-b-arch__flow-arrow {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding-left: 4px;
  margin: 6px 0 10px;
  color: var(--gt-color-primary-light, #a06dff);
  font-size: 18px;
}
</style>
