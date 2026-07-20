<template>
  <div class="g7-directory" data-testid="g7-directory">
    <!-- 标题 + 进度 -->
    <div class="dir-header">
      <h3 class="title">G7 底稿目录</h3>
      <GtReviewTrigger section-id="G7-index-directory" />
      <span class="progress-label">编制进度 {{ completedCount }}/{{ totalCount }}</span>
      <el-progress
        :percentage="progressPct"
        :stroke-width="14"
        color="#7c3aed"
        class="progress-bar"
      />
    </div>

    <!-- 编制提示（一行） -->
    <p class="workflow-hint">
      推荐工作流：G7A → G7-1 审定 → G7-2 明细 → G7-4~6 权益法 → G7-14 核算 → G7-13 成本法 → G7-7~12 子公司 → G7-18 凭证 → G0 函证 → G7-3 调整 → 附注
    </p>

    <!-- 底稿结构 -->
    <div class="structure-label">底稿结构 <span>共 {{ totalCount }} 张底稿分 {{ groups.length }} 组如下所示</span></div>

    <!-- 分组 -->
    <div
      v-for="(group, gi) in groups"
      :key="group.id"
      class="group-section"
    >
      <div class="group-head">
        <span class="group-num">{{ gi + 1 }}</span>
        <span class="group-title">{{ group.title }}</span>
        <span class="group-count">({{ group.items.length }} 张)</span>
      </div>
      <div class="sheet-grid">
        <div
          v-for="item in group.items"
          :key="item.indexCode"
          class="sheet-card"
          @click="handleJump(item.indexCode)"
        >
          <span class="card-check" :class="item.status">
            {{ item.status === 'done' ? '☑' : '☐' }}
          </span>
          <div class="card-body">
            <span class="card-code">{{ item.indexCode }}</span>
            <span class="card-name">{{ item.content }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabDirectory.vue — 底稿目录（G8风格：编号分组 + 白底卡片 + 紫色进度条）
 */
import { computed } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ jump: [code: string] }>()

interface DirectoryItem {
  content: string
  indexCode: string
  status: 'done' | 'pending'
}

const allItems = computed<DirectoryItem[]>(() => {
  const responses = props.htmlData?.responses_snapshot || props.htmlData?.allResponses || {}
  return [
    { content: '长期股权投资实质性程序表', indexCode: 'G7A', status: resolveStatus('G7A', responses) },
    { content: '长期股权投资审定表', indexCode: 'G7-1', status: resolveStatus('G7-1', responses) },
    { content: '长期股权投资明细表', indexCode: 'G7-2', status: resolveStatus('G7-2', responses) },
    { content: '调整分录汇总', indexCode: 'G7-3', status: resolveStatus('G7-3', responses) },
    { content: '附注披露信息（上市公司）', indexCode: 'G7-附注(上市)', status: resolveStatus('G7-附注(上市)', responses) },
    { content: '附注披露信息（国企）', indexCode: 'G7-附注(国企)', status: resolveStatus('G7-附注(国企)', responses) },
    { content: '被投资单位基本信息', indexCode: 'G7-4', status: resolveStatus('G7-4', responses) },
    { content: '被投资单位财务信息', indexCode: 'G7-5', status: resolveStatus('G7-5', responses) },
    { content: '会计政策一致性检查', indexCode: 'G7-6', status: resolveStatus('G7-6', responses) },
    { content: '成本法后续计量测试', indexCode: 'G7-13', status: resolveStatus('G7-13', responses) },
    { content: '权益法核算测算', indexCode: 'G7-14', status: resolveStatus('G7-14', responses) },
    { content: '内部交易未实现损益', indexCode: 'G7-15', status: resolveStatus('G7-15', responses) },
    { content: '未确认投资损失', indexCode: 'G7-16', status: resolveStatus('G7-16', responses) },
    { content: '长期股权投资减值', indexCode: 'G7-17', status: resolveStatus('G7-17', responses) },
    { content: '投资初始确认判断', indexCode: 'G7-7', status: resolveStatus('G7-7', responses) },
    { content: '同一控制下企业合并', indexCode: 'G7-8', status: resolveStatus('G7-8', responses) },
    { content: '非同一控制下企业合并', indexCode: 'G7-9', status: resolveStatus('G7-9', responses) },
    { content: '后续计量检查', indexCode: 'G7-10', status: resolveStatus('G7-10', responses) },
    { content: '处置检查（非一揽子交易）', indexCode: 'G7-11', status: resolveStatus('G7-11', responses) },
    { content: '处置检查（一揽子交易）', indexCode: 'G7-12', status: resolveStatus('G7-12', responses) },
    { content: '凭证检查表', indexCode: 'G7-18', status: resolveStatus('G7-18', responses) },
    { content: '投资循环函证', indexCode: 'G0', status: resolveStatus('G0', responses) },
    { content: '底稿目录', indexCode: 'G7-目录', status: 'done' as const },
  ]
})

interface SheetGroup { id: string; title: string; items: DirectoryItem[] }

const groups = computed<SheetGroup[]>(() => {
  const items = allItems.value
  const byCode = (code: string) => items.find(i => i.indexCode === code)!
  return [
    {
      id: 'main',
      title: '科目审定',
      items: ['G7A', 'G7-1', 'G7-2', 'G7-3'].map(byCode).filter(Boolean),
    },
    {
      id: 'equity-method',
      title: '实质性程序',
      items: ['G7-4', 'G7-5', 'G7-6', 'G7-13', 'G7-14', 'G7-15', 'G7-16', 'G7-17'].map(byCode).filter(Boolean),
    },
    {
      id: 'subsidiary',
      title: '子公司合并',
      items: ['G7-7', 'G7-8', 'G7-9', 'G7-10', 'G7-11', 'G7-12', 'G7-18'].map(byCode).filter(Boolean),
    },
    {
      id: 'disclosure',
      title: '披露与其他',
      items: ['G7-附注(上市)', 'G7-附注(国企)', 'G0', 'G7-目录'].map(byCode).filter(Boolean),
    },
  ]
})

const totalCount = computed(() => allItems.value.length)
const completedCount = computed(() => allItems.value.filter(i => i.status === 'done').length)
const progressPct = computed(() => totalCount.value > 0 ? Math.round((completedCount.value / totalCount.value) * 100) : 0)

function resolveStatus(code: string, responses: Record<string, any>): 'done' | 'pending' {
  if (!responses || typeof responses !== 'object') return 'pending'
  const keys = Object.keys(responses)
  const relatedKeys = keys.filter(k => k.startsWith(code) || k.includes(code))
  if (relatedKeys.length > 0) {
    const hasConclusion = relatedKeys.some(k => responses[k]?.conclusion || responses[k]?.remark)
    if (hasConclusion) return 'done'
  }
  return 'pending'
}

function handleJump(code: string) {
  if (code) emit('jump', code)
}
</script>

<style scoped>
.g7-directory {
  padding: 12px 16px;
  font-size: var(--wp-font-size, 13px);
}

/* ═══ Header ═══ */
.dir-header {
  margin-bottom: 12px;
}
.title {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 700;
}
.progress-label {
  display: inline-block;
  margin-right: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.progress-bar {
  margin-top: 4px;
}
.progress-bar :deep(.el-progress-bar__outer) {
  border-radius: 6px;
}
.progress-bar :deep(.el-progress-bar__inner) {
  border-radius: 6px;
}

/* ═══ Workflow hint ═══ */
.workflow-hint {
  margin: 0 0 16px;
  padding: 6px 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  line-height: 1.6;
}

/* ═══ Structure label ═══ */
.structure-label {
  margin-bottom: 12px;
  font-size: 13px;
  font-weight: 600;
}
.structure-label span {
  font-weight: 400;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-left: 8px;
}

/* ═══ Group ═══ */
.group-section {
  margin-bottom: 20px;
}
.group-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
}
.group-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}
.group-title {
  font-size: 14px;
  font-weight: 600;
}
.group-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* ═══ Sheet Grid ═══ */
.sheet-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
@media (max-width: 1100px) {
  .sheet-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 768px) {
  .sheet-grid { grid-template-columns: repeat(2, 1fr); }
}

/* ═══ Sheet Card ═══ */
.sheet-card {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  cursor: pointer;
  transition: box-shadow 0.15s, border-color 0.15s;
}
.sheet-card:hover {
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
  border-color: var(--el-color-primary-light-5);
}

/* Check icon */
.card-check {
  font-size: 14px;
  line-height: 1;
  flex-shrink: 0;
  margin-top: 1px;
}
.card-check.done {
  color: var(--el-color-success);
}
.card-check.pending {
  color: var(--el-border-color);
}

/* Card body */
.card-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}
.card-code {
  font-weight: 600;
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.card-name {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
