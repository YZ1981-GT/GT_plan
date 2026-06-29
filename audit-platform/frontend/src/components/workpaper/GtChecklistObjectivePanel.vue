<script setup lang="ts">
/**
 * GtChecklistObjectivePanel — 审计目标追溯面板
 *
 * A17-5 专用：6个审计目标卡片，每个目标显示：
 * - 目标描述 + 达成状态（绿/黄/灰）
 * - 完成进度环
 * - 关联程序编号 chip 列表（可点击跳转定位到对应核对程序项）
 *
 * 纯展示型子组件，数据通过 props 下行，交互通过 emit 上行。
 */
import { computed } from 'vue'
import type { ResponseData } from './checklistTypes'

/** 目标→程序映射（与 GtChecklistTable 中 OBJECTIVE_PROGRAM_MAP 保持一致） */
const OBJECTIVES: Record<number, { label: string; description: string; programs: number[] }> = {
  1: {
    label: '错报评价与处理',
    description: '确定审计过程中发现的所有错报均已得到恰当的评价与处理。',
    programs: [33, 34, 35, 36, 37],
  },
  2: {
    label: '获取管理层声明书',
    description: '确定已获取管理层签署的声明书，声明其已履行编制财务报表的责任并向注册会计师提供了所有相关信息。',
    programs: [44],
  },
  3: {
    label: '内控缺陷及重大事项沟通',
    description: '确定识别出的内部控制缺陷及其他重大事项（例如舞弊迹象或疑似违反法律法规事项）均与管理层或/和治理层进行了沟通。',
    programs: [7, 25, 32],
  },
  4: {
    label: '财务报表合规性',
    description: '确定财务报表及附注符合企业会计准则及有关法规的要求。',
    programs: [16, 17, 18, 19, 20, 21, 22, 23, 24, 45],
  },
  5: {
    label: '审计意见恰当性',
    description: '确定审计报告意见类型恰当。',
    programs: [28, 29, 30, 31, 38],
  },
  6: {
    label: '充分证据与复核',
    description: '确定已获取充分适当的审计证据，对审计工作底稿已按照执业准则和本所质量管理政策与程序完成复核。',
    programs: [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 26, 27, 39, 40, 41, 42, 43, 46, 47, 48, 49],
  },
}

const props = defineProps<{
  /** 所有 responses 数据（用于计算完成进度） */
  responses: Record<string, ResponseData>
  /** 当前所有 sections 的 items（扁平化 id 用于匹配程序编号） */
  allItemIds: string[]
}>()

const emit = defineEmits<{
  (e: 'locate-program', programNum: number): void
}>()

/** 从 item id 中提取尾部数字（程序编号） */
function extractProgramNum(itemId: string): number | null {
  const m = itemId.match(/(\d+)$/)
  return m ? parseInt(m[1]) : null
}

/** 每个目标的进度统计 */
interface ObjectiveStats {
  idx: number
  label: string
  description: string
  programs: number[]
  filled: number
  total: number
  percent: number
  status: 'completed' | 'partial' | 'not_started'
}

const objectiveStats = computed<ObjectiveStats[]>(() => {
  return Object.entries(OBJECTIVES).map(([key, obj]) => {
    const idx = Number(key)
    let filled = 0
    let total = 0

    for (const progNum of obj.programs) {
      // 找到匹配该程序编号的 item id
      const matchedId = props.allItemIds.find(id => {
        const num = extractProgramNum(id)
        return num === progNum
      })
      if (matchedId) {
        total++
        const resp = props.responses[matchedId]
        if (resp?.conclusion) filled++
      } else {
        // 程序存在于映射中但实际 items 中未找到（可能不适用）
        total++
      }
    }

    const percent = total > 0 ? Math.round((filled / total) * 100) : 0
    let status: 'completed' | 'partial' | 'not_started' = 'not_started'
    if (filled > 0 && filled >= total) status = 'completed'
    else if (filled > 0) status = 'partial'

    return { idx, label: obj.label, description: obj.description, programs: obj.programs, filled, total, percent, status }
  })
})

function statusColor(status: string): string {
  switch (status) {
    case 'completed': return '#67c23a'
    case 'partial': return '#e6a23c'
    default: return '#c0c4cc'
  }
}

function statusIcon(status: string): string {
  switch (status) {
    case 'completed': return '✓'
    case 'partial': return '◐'
    default: return '○'
  }
}

function statusText(status: string): string {
  switch (status) {
    case 'completed': return '已达成'
    case 'partial': return '进行中'
    default: return '未开始'
  }
}
</script>

<template>
  <div class="gt-objective-panel">
    <div class="gt-objective-panel__header">
      <span class="gt-objective-panel__icon">🎯</span>
      <span class="gt-objective-panel__title">审计目标追溯面板</span>
      <span class="gt-objective-panel__subtitle">6 项审计目标 × 47 项核对程序 多对多追溯</span>
    </div>

    <div class="gt-objective-panel__cards">
      <div
        v-for="obj in objectiveStats"
        :key="obj.idx"
        class="objective-card"
        :class="`objective-card--${obj.status}`"
      >
        <!-- 卡片头部：编号 + 标签 + 状态 -->
        <div class="objective-card__head">
          <span class="objective-card__num">{{ obj.idx }}</span>
          <span class="objective-card__label">{{ obj.label }}</span>
          <span class="objective-card__status" :style="{ color: statusColor(obj.status) }">
            {{ statusIcon(obj.status) }} {{ statusText(obj.status) }}
          </span>
        </div>

        <!-- 描述 -->
        <p class="objective-card__desc">{{ obj.description }}</p>

        <!-- 进度条 -->
        <div class="objective-card__progress">
          <el-progress
            :percentage="obj.percent"
            :stroke-width="10"
            :color="statusColor(obj.status)"
            :text-inside="false"
            :format="() => `${obj.filled}/${obj.total}`"
          />
        </div>

        <!-- 关联程序 chip 列表 -->
        <div class="objective-card__programs">
          <span class="objective-card__programs-label">关联程序：</span>
          <span
            v-for="prog in obj.programs"
            :key="prog"
            class="program-chip"
            :class="{ 'program-chip--done': (() => {
              const mid = allItemIds.find(id => extractProgramNum(id) === prog)
              return mid ? !!responses[mid]?.conclusion : false
            })() }"
            @click="emit('locate-program', prog)"
          >
            #{{ prog }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gt-objective-panel {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.gt-objective-panel__header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--gt-color-primary, #409eff);
}

.gt-objective-panel__icon {
  font-size: 20px;
}

.gt-objective-panel__title {
  font-size: 16px;
  font-weight: 600;
  color: var(--gt-color-primary, #409eff);
}

.gt-objective-panel__subtitle {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #999);
  margin-left: auto;
}

.gt-objective-panel__cards {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ─── Objective Card ─── */
.objective-card {
  border: 1px solid var(--gt-color-border-light, #e4e7ed);
  border-radius: 8px;
  padding: 16px;
  background: #fff;
  transition: box-shadow 0.2s, border-color 0.2s;
}

.objective-card:hover {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.objective-card--completed {
  border-left: 4px solid #67c23a;
}

.objective-card--partial {
  border-left: 4px solid #e6a23c;
}

.objective-card--not_started {
  border-left: 4px solid #c0c4cc;
}

.objective-card__head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.objective-card__num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--gt-color-primary, #409eff);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}

.objective-card__label {
  font-size: 15px;
  font-weight: 600;
  color: var(--gt-color-text, #303133);
}

.objective-card__status {
  margin-left: auto;
  font-size: 13px;
  font-weight: 500;
}

.objective-card__desc {
  font-size: 13px;
  line-height: 1.6;
  color: var(--gt-color-text-secondary, #606266);
  margin: 0 0 12px;
}

.objective-card__progress {
  margin-bottom: 12px;
}

.objective-card__progress :deep(.el-progress__text) {
  font-size: 12px !important;
  min-width: 44px;
}

.objective-card__programs {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.objective-card__programs-label {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #999);
  flex-shrink: 0;
}

/* ─── Program Chip ─── */
.program-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  background: #f0f2f5;
  color: var(--gt-color-text-secondary, #606266);
  cursor: pointer;
  transition: all 0.15s;
  user-select: none;
}

.program-chip:hover {
  background: var(--gt-color-primary-bg, #ecf5ff);
  color: var(--gt-color-primary, #409eff);
}

.program-chip--done {
  background: #e6f7e6;
  color: #67c23a;
}

.program-chip--done:hover {
  background: #d4edda;
  color: #5aaf33;
}
</style>
