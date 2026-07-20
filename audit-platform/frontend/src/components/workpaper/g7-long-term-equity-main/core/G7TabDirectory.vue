<template>
  <div class="g7-directory" data-testid="g7-directory">
    <!-- Header -->
    <div class="dir-header">
      <h3 class="title">G7 底稿目录</h3>
      <GtReviewTrigger section-id="G7-index-directory" />
      <div class="progress-wrap">
        <span>编制进度 {{ completedCount }}/{{ totalCount }}</span>
        <el-progress :percentage="progressPct" :stroke-width="10" />
      </div>
    </div>

    <!-- 分组看板 -->
    <div
      v-for="group in groups"
      :key="group.id"
      class="group-board"
    >
      <div class="group-head">
        <strong>{{ group.title }}</strong>
        <el-tag size="small" effect="plain">{{ group.items.length }} 张</el-tag>
      </div>
      <div class="sheet-grid">
        <div
          v-for="item in group.items"
          :key="item.indexCode"
          class="sheet-card"
          :class="{ done: item.status === 'done' }"
          @click="handleJump(item.indexCode)"
        >
          <GtIndexChip v-if="item.indexCode" :value="item.indexCode" />
          <div class="card-code">{{ item.indexCode || '-' }}</div>
          <div class="card-name">{{ item.content }}</div>
          <span class="card-dot" :class="item.status" />
        </div>
      </div>
    </div>

    <!-- 编制提示 -->
    <details class="methodology-hint">
      <summary>编制提示</summary>
      <div class="hint-body">
        <p>本底稿目录涵盖 G7 长期股权投资全部底稿。索引号 G7A 为实质性程序表，G7-1 为审定表（按控制类型分层：子公司/合营/联营），G7-2 为明细表（54列5区段），G7-3 为调整分录汇总，G7-4 至 G7-6/G7-13 至 G7-17 为权益法组底稿，G7-7 至 G7-12/G7-18 为子公司组底稿，G0 为投资循环共享函证。各底稿通过索引号实现交叉引用与跳转。</p>
        <p>推荐工作流：G7A 程序表 → G7-1 审定表 → G7-2 明细表（带入TB未审数）→ G7-4~6 权益法基本信息与政策 → G7-14 权益法核算 → G7-13 成本法测试 → G7-15~17 内部交易/未确认损失/减值 → G7-7~12 子公司合并 → G7-18 凭证检查 → G0 函证 → G7-3 调整分录 → 附注披露。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabDirectory.vue — 底稿目录（卡片看板式，4分组24张）
 *
 * Spec: .kiro/specs/g7-long-term-equity-main/ Task 6.3
 * Requirements: 1.2
 *
 * G8风格卡片看板目录，替代旧el-table表格式。
 * 4个分组：主体Main组 / 权益法组 / 子公司组 / 函证&其他
 * 支持 GtIndexChip 索引跳转、编制进度统计
 */
import { computed } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ jump: [code: string] }>()

// ═══ 24行目录数据 ═══
interface DirectoryItem {
  seq: number
  content: string
  indexCode: string
  status: 'done' | 'pending'
}

const allItems = computed<DirectoryItem[]>(() => {
  const responses = props.htmlData?.responses_snapshot || props.htmlData?.allResponses || {}
  return [
    { seq: 1, content: '长期股权投资实质性程序表', indexCode: 'G7A', status: resolveStatus('G7A', responses) },
    { seq: 2, content: '长期股权投资审定表', indexCode: 'G7-1', status: resolveStatus('G7-1', responses) },
    { seq: 3, content: '长期股权投资明细表', indexCode: 'G7-2', status: resolveStatus('G7-2', responses) },
    { seq: 4, content: '调整分录汇总', indexCode: 'G7-3', status: resolveStatus('G7-3', responses) },
    { seq: 5, content: '附注披露信息（上市公司）', indexCode: 'G7-附注(上市)', status: resolveStatus('G7-附注(上市)', responses) },
    { seq: 6, content: '附注披露信息（国企）', indexCode: 'G7-附注(国企)', status: resolveStatus('G7-附注(国企)', responses) },
    { seq: 7, content: '被投资单位基本信息', indexCode: 'G7-4', status: resolveStatus('G7-4', responses) },
    { seq: 8, content: '被投资单位财务信息', indexCode: 'G7-5', status: resolveStatus('G7-5', responses) },
    { seq: 9, content: '会计政策一致性检查', indexCode: 'G7-6', status: resolveStatus('G7-6', responses) },
    { seq: 10, content: '成本法后续计量测试', indexCode: 'G7-13', status: resolveStatus('G7-13', responses) },
    { seq: 11, content: '权益法核算测算', indexCode: 'G7-14', status: resolveStatus('G7-14', responses) },
    { seq: 12, content: '内部交易未实现损益', indexCode: 'G7-15', status: resolveStatus('G7-15', responses) },
    { seq: 13, content: '未确认投资损失', indexCode: 'G7-16', status: resolveStatus('G7-16', responses) },
    { seq: 14, content: '长期股权投资减值', indexCode: 'G7-17', status: resolveStatus('G7-17', responses) },
    { seq: 15, content: '投资初始确认判断', indexCode: 'G7-7', status: resolveStatus('G7-7', responses) },
    { seq: 16, content: '同一控制下企业合并', indexCode: 'G7-8', status: resolveStatus('G7-8', responses) },
    { seq: 17, content: '非同一控制下企业合并', indexCode: 'G7-9', status: resolveStatus('G7-9', responses) },
    { seq: 18, content: '后续计量检查', indexCode: 'G7-10', status: resolveStatus('G7-10', responses) },
    { seq: 19, content: '处置检查（非一揽子交易）', indexCode: 'G7-11', status: resolveStatus('G7-11', responses) },
    { seq: 20, content: '处置检查（一揽子交易）', indexCode: 'G7-12', status: resolveStatus('G7-12', responses) },
    { seq: 21, content: '凭证检查表', indexCode: 'G7-18', status: resolveStatus('G7-18', responses) },
    { seq: 22, content: '投资循环函证', indexCode: 'G0', status: resolveStatus('G0', responses) },
    { seq: 23, content: '审计说明与结论', indexCode: 'G7-说明', status: resolveStatus('G7-说明', responses) },
    { seq: 24, content: '底稿目录', indexCode: 'G7-目录', status: 'done' },
  ]
})

// ═══ 4个分组 ═══
interface SheetGroup {
  id: string
  title: string
  items: DirectoryItem[]
}

const groups = computed<SheetGroup[]>(() => {
  const items = allItems.value
  const byCode = (code: string) => items.find(i => i.indexCode === code)

  return [
    {
      id: 'main',
      title: '主体 Main 组',
      items: [
        byCode('G7A'),
        byCode('G7-1'),
        byCode('G7-2'),
        byCode('G7-3'),
        byCode('G7-附注(上市)'),
        byCode('G7-附注(国企)'),
      ].filter(Boolean) as DirectoryItem[],
    },
    {
      id: 'equity-method',
      title: '权益法组',
      items: [
        byCode('G7-4'),
        byCode('G7-5'),
        byCode('G7-6'),
        byCode('G7-13'),
        byCode('G7-14'),
        byCode('G7-15'),
        byCode('G7-16'),
        byCode('G7-17'),
      ].filter(Boolean) as DirectoryItem[],
    },
    {
      id: 'subsidiary',
      title: '子公司组',
      items: [
        byCode('G7-7'),
        byCode('G7-8'),
        byCode('G7-9'),
        byCode('G7-10'),
        byCode('G7-11'),
        byCode('G7-12'),
        byCode('G7-18'),
      ].filter(Boolean) as DirectoryItem[],
    },
    {
      id: 'confirmation-other',
      title: '函证 & 其他',
      items: [
        byCode('G0'),
        byCode('G7-说明'),
        byCode('G7-目录'),
      ].filter(Boolean) as DirectoryItem[],
    },
  ]
})

// ═══ 编制进度 ═══
const totalCount = computed(() => allItems.value.length)
const completedCount = computed(() => allItems.value.filter(i => i.status === 'done').length)
const progressPct = computed(() => {
  return totalCount.value > 0
    ? Math.round((completedCount.value / totalCount.value) * 100)
    : 0
})

// ═══ 状态判断 ═══
function resolveStatus(code: string, responses: Record<string, any>): 'done' | 'pending' {
  // 从 responses 中检查是否有该 sheet 的完成标记
  if (!responses || typeof responses !== 'object') return 'pending'
  // 检查常见完成标记模式
  const keys = Object.keys(responses)
  const relatedKeys = keys.filter(k => k.startsWith(code) || k.includes(code))
  if (relatedKeys.length > 0) {
    // 有任何关联数据视为已编制
    const hasConclusion = relatedKeys.some(k =>
      responses[k]?.conclusion || responses[k]?.remark,
    )
    if (hasConclusion) return 'done'
  }
  return 'pending'
}

// ═══ 跳转 ═══
function handleJump(code: string) {
  if (code) {
    emit('jump', code)
  }
}
</script>

<style scoped>
.g7-directory {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* Header */
.dir-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.progress-wrap {
  flex: 1;
  min-width: 200px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.progress-wrap span {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

/* 分组看板 */
.group-board {
  margin-bottom: 16px;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
}
.group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.group-head strong {
  font-size: 14px;
}

/* Sheet Grid */
.sheet-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
@media (max-width: 768px) {
  .sheet-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 480px) {
  .sheet-grid {
    grid-template-columns: 1fr;
  }
}

/* Sheet Card */
.sheet-card {
  position: relative;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  cursor: pointer;
  transition: box-shadow 0.2s, border-color 0.2s;
  background: var(--el-fill-color-light);
}
.sheet-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  border-color: var(--el-color-primary-light-5);
}
.sheet-card.done {
  border-left: 3px solid var(--el-color-success);
}
.card-code {
  font-weight: 600;
  font-size: 13px;
  margin-top: 4px;
}
.card-name {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
  line-height: 1.4;
}
.card-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  position: absolute;
  top: 8px;
  right: 8px;
}
.card-dot.done {
  background: var(--el-color-success);
}
.card-dot.pending {
  background: var(--el-border-color-light);
}

/* 编制提示 */
.methodology-hint {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.methodology-hint summary {
  cursor: pointer;
  font-weight: 600;
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.hint-body {
  position: relative;
  margin-top: 8px;
  padding: 12px 12px 12px 16px;
  background: #fffbe6;
  border-radius: 4px;
  border-left: 4px solid #d48806;
  line-height: 1.7;
  color: #614700;
}
.hint-body p {
  margin: 0 0 8px;
}
.hint-body p:last-child {
  margin-bottom: 0;
}
</style>
