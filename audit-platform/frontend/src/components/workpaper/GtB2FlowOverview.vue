<script setup lang="ts">
/**
 * GtB2FlowOverview — B2 前任沟通流程总览 + 函件往来状态台账
 *
 * 按三个互斥场景分泳道（委托前沟通 / 委托后底稿查阅 / 重新审计·IPO），每卡片显示
 * 底稿编码 + 名称 + 函件状态（未发/已发函/已回函 + 发函日/回函日；B2-3 含第一封+催函日）。
 * 点击 emit open(wpCode)；未生成底稿点击提示。适用性 applicability 控制泳道显隐。
 */
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from './GtIndexChip.vue'

interface Applicability {
  firstEngagement: boolean
  reviewPredecessorWp: boolean
  ipoReaudit: boolean
}
interface LetterStatus {
  status?: string
  sentDate?: string
  replyDate?: string
  followUpDate?: string
}

const props = defineProps<{
  wpIdMap: Record<string, string>
  applicability: Applicability
  letterStatus: Record<string, LetterStatus>
  readonly?: boolean
}>()

const emit = defineEmits<{
  open: [wpCode: string]
  updateStatus: [wpCode: string, patch: LetterStatus]
}>()

interface FlowNode {
  wpCode: string
  name: string
  inBundle: boolean
  isLetter?: boolean
  hasFollowUp?: boolean
}
interface Lane { key: keyof Applicability; title: string; hint: string; nodes: FlowNode[] }

const LANES: Lane[] = [
  {
    key: 'firstEngagement',
    title: '① 接受委托前沟通（业务承接决策）',
    hint: '准则 1153 号 · 首次承接适用',
    nodes: [
      { wpCode: 'B2-1', name: '向被审计单位发出的沟通函（就业务承接事项）', inBundle: false, isLetter: true },
      { wpCode: 'B2-3', name: '与前任的沟通函（就业务承接事项，两封含催函）', inBundle: false, isLetter: true, hasFollowUp: true },
      { wpCode: 'B2-5', name: '与前任沟通后的评价（接受/不接受委托）', inBundle: true },
    ],
  },
  {
    key: 'reviewPredecessorWp',
    title: '② 接受委托后底稿查阅沟通',
    hint: '准则 1331 号 · 期初余额首次审计适用',
    nodes: [
      { wpCode: 'B2-6', name: '向被审计单位发出的沟通函（就底稿使用事项）', inBundle: false, isLetter: true },
      { wpCode: 'B2-8', name: '与前任的沟通函（就底稿查阅事项）', inBundle: false, isLetter: true },
    ],
  },
  {
    key: 'ipoReaudit',
    title: '③ 重新审计 / IPO 前任评价',
    hint: '准则 1153 号 §5.2 · 重新审计·IPO 复核适用',
    nodes: [
      { wpCode: 'B2-11', name: '与前任的沟通函（就沪深交易所复核重要事项）', inBundle: false, isLetter: true },
      { wpCode: 'B2-12', name: '对前任注册会计师的评价底稿（9 步了解 + 7 点判断）', inBundle: false },
    ],
  },
]

const STATUS_OPTIONS = ['未发', '已发函', '已回函']

const visibleLanes = computed(() =>
  LANES.filter((l) => props.applicability[l.key] !== false)
)

function nodeReady(n: FlowNode): boolean {
  return n.inBundle || !!props.wpIdMap[n.wpCode]
}

function statusOf(wpCode: string): LetterStatus {
  return props.letterStatus?.[wpCode] || {}
}

function patchStatus(wpCode: string, patch: LetterStatus) {
  if (props.readonly) return
  emit('updateStatus', wpCode, { ...statusOf(wpCode), ...patch })
}

// 催函提示：B2-3 已发函(第一封)、有发函日、超 14 天无回函且未发催函 → 建议催函
function followUpHint(n: FlowNode): string {
  if (!n.hasFollowUp) return ''
  const s = statusOf(n.wpCode)
  if (s.status === '已回函') return ''
  if (!s.sentDate || s.followUpDate) return ''
  const days = Math.floor((Date.now() - new Date(s.sentDate).getTime()) / 86400000)
  return days >= 14 ? `第一封已发出 ${days} 天未获回函，建议发第二封催函` : ''
}

function statusTagType(wpCode: string): 'success' | 'warning' | 'info' {
  const s = statusOf(wpCode).status
  if (s === '已回函') return 'success'
  if (s === '已发函') return 'warning'
  return 'info'
}

function onClick(n: FlowNode) {
  if (!nodeReady(n)) {
    ElMessage.info(`底稿 ${n.wpCode} 尚未生成，请先在底稿列表 / 项目底稿生成该函件后再打开`)
    return
  }
  emit('open', n.wpCode)
}
</script>

<template>
  <div class="gt-b2-flow">
    <el-alert type="info" :closable="false" show-icon class="gt-b2-flow__tip">
      <template #title>
        前任-后任注册会计师沟通全流程总览与函件往来台账。三个场景互斥，可在「基础信息」页勾选适用性以裁剪不适用场景。
        点击卡片标题打开对应底稿；在卡片内维护发函/回函状态。
      </template>
    </el-alert>

    <div v-for="lane in visibleLanes" :key="lane.key" class="gt-b2-flow__lane">
      <div class="gt-b2-flow__lane-head">
        <span class="gt-b2-flow__lane-title">{{ lane.title }}</span>
        <span class="gt-b2-flow__lane-hint">{{ lane.hint }}</span>
      </div>
      <div class="gt-b2-flow__grid">
        <div
          v-for="n in lane.nodes"
          :key="n.wpCode"
          class="gt-b2-flow__card"
        >
          <div class="gt-b2-flow__card-top">
            <span class="gt-b2-flow__code" :class="{ 'is-disabled': !nodeReady(n) }" @click="onClick(n)">
              <GtIndexChip :value="n.wpCode" :validate="false" />
            </span>
            <el-tag
              v-if="n.isLetter"
              :type="statusTagType(n.wpCode)"
              size="small"
              effect="plain"
            >{{ statusOf(n.wpCode).status || '未发' }}</el-tag>
            <el-tag
              v-else
              :type="nodeReady(n) ? 'success' : 'info'"
              size="small"
              effect="plain"
            >{{ n.inBundle ? '本页可编辑' : (props.wpIdMap[n.wpCode] ? '可打开' : '未生成') }}</el-tag>
          </div>
          <span class="gt-b2-flow__name" :title="n.name" @click="onClick(n)">{{ n.name }}</span>

          <!-- 函件状态台账 -->
          <div v-if="n.isLetter" class="gt-b2-flow__status">
            <div class="gt-b2-flow__status-row">
              <el-select
                :model-value="statusOf(n.wpCode).status || '未发'"
                size="small"
                :disabled="readonly"
                class="gt-b2-flow__status-sel"
                @update:model-value="(v: string) => patchStatus(n.wpCode, { status: v })"
              >
                <el-option v-for="o in STATUS_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
            </div>
            <div class="gt-b2-flow__status-row">
              <span class="gt-b2-flow__status-lbl">{{ n.hasFollowUp ? '第一封发函日' : '发函日' }}</span>
              <el-date-picker
                :model-value="statusOf(n.wpCode).sentDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="readonly"
                placeholder="选择日期"
                @update:model-value="(v: string) => patchStatus(n.wpCode, { sentDate: v })"
              />
            </div>
            <div v-if="n.hasFollowUp" class="gt-b2-flow__status-row">
              <span class="gt-b2-flow__status-lbl">催函发函日</span>
              <el-date-picker
                :model-value="statusOf(n.wpCode).followUpDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="readonly"
                placeholder="选择日期"
                @update:model-value="(v: string) => patchStatus(n.wpCode, { followUpDate: v })"
              />
            </div>
            <div class="gt-b2-flow__status-row">
              <span class="gt-b2-flow__status-lbl">回函日</span>
              <el-date-picker
                :model-value="statusOf(n.wpCode).replyDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                :disabled="readonly"
                placeholder="选择日期"
                @update:model-value="(v: string) => patchStatus(n.wpCode, { replyDate: v })"
              />
            </div>
            <el-alert
              v-if="followUpHint(n)"
              type="warning"
              :closable="false"
              size="small"
              class="gt-b2-flow__followup"
            >
              <template #title>{{ followUpHint(n) }}</template>
            </el-alert>
          </div>
        </div>
      </div>
    </div>

    <el-empty v-if="visibleLanes.length === 0" description="当前适用性下无适用场景" :image-size="60" />
  </div>
</template>

<style scoped>
.gt-b2-flow { padding: 4px; }
.gt-b2-flow__tip { margin-bottom: 14px; }
.gt-b2-flow__lane { margin-bottom: 18px; }
.gt-b2-flow__lane-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 10px; }
.gt-b2-flow__lane-title { font-size: 14px; font-weight: 600; color: var(--gt-color-primary, #4b2d77); }
.gt-b2-flow__lane-hint { font-size: 12px; color: var(--gt-color-text-tertiary, #909399); }
.gt-b2-flow__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
  padding-left: 14px;
}
.gt-b2-flow__card {
  display: flex; flex-direction: column; gap: 8px;
  padding: 12px;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 8px;
  background: #fff;
  transition: all 0.2s;
}
.gt-b2-flow__card:hover {
  border-color: var(--gt-color-primary, #4b2d77);
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.12);
}
.gt-b2-flow__card-top { display: flex; align-items: center; justify-content: space-between; }
.gt-b2-flow__code { cursor: pointer; }
.gt-b2-flow__code.is-disabled { opacity: 0.55; cursor: not-allowed; }
.gt-b2-flow__name {
  font-size: var(--wp-font-size, 13px); line-height: 1.4; cursor: pointer;
  color: var(--gt-color-text-primary, #303133);
}
.gt-b2-flow__name:hover { color: var(--gt-color-primary, #4b2d77); }
.gt-b2-flow__status {
  display: flex; flex-direction: column; gap: 6px;
  padding-top: 8px; border-top: 1px dashed var(--gt-color-border-purple, #e8e4f0);
}
.gt-b2-flow__status-row { display: flex; align-items: center; gap: 8px; }
.gt-b2-flow__status-lbl { font-size: 12px; color: var(--gt-color-text-tertiary, #909399); width: 74px; flex-shrink: 0; }
.gt-b2-flow__status-sel { width: 120px; }
.gt-b2-flow__followup { margin-top: 4px; }
</style>
