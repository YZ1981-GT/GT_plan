<template>
  <div class="e1-dir" data-testid="e1-directory">
    <div class="index-header">
      <h3 class="title">E1 底稿目录</h3>
      <GtReviewTrigger section-id="E1-index-directory" />
      <div class="handbook-btns">
        <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
        <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
      </div>
      <div class="progress-wrap">
        <span>编制进度 {{ completedCount }}/{{ E1_SHEETS.length }}</span>
        <el-progress :percentage="progressPct" :stroke-width="10" />
      </div>
    </div>

    <E1PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

    <!-- 跨表结论口径看板 -->
    <div class="conclusion-board" data-testid="e1-conclusion-board">
      <div class="board-head">
        <strong>跨表结论口径</strong>
        <el-tag size="small" :type="worstTagType">{{ worstLabel }}</el-tag>
        <span class="board-meta">已填 {{ filledCount }}/{{ E1_SHEETS.length }}</span>
      </div>
      <div class="board-tags">
        <el-tag
          v-for="c in conclusionSheets"
          :key="c.code"
          size="small"
          class="concl-tag clickable"
          :type="c.filled ? 'success' : 'info'"
          effect="plain"
          @click="goSheet(c.code)"
        >
          {{ c.code }} {{ c.filled ? '已填' : '未填' }}
        </el-tag>
      </div>
      <p v-if="hasUnfilled" class="board-hint">存在未填审计结论，请点击标签跳转补全审计说明与结论。</p>
    </div>

    <details class="methodology-hint">
      <summary>编制提示</summary>
      <p>
        推荐工作流：E1A 程序表 → E1-1 审定表 → E1-2/E1-3/E1-4 明细（现金/银行/数字货币）→
        E1-6 余额调节 → E1-7/E1-8 现金盘点 → E1-9 存单盘点 → E1-10 账户核对 → E1-11 承诺书 →
        E1-15/E1-20 利息与应计利息 → E1-21/E1-22 截止测试 → E1-23 收支检查 → E1-18/E1-19 信用报告 →
        E1-14 分析表 → E1-5 调整分录 → 附注披露。各表填妥"审计结论"后目录标签转为"已填"。
      </p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * E1TabDirectory.vue — E1 货币资金底稿目录「跨表结论口径」卡片（G4TabDirectory 红框范式）
 *
 * 设计为自包含卡片，嵌入 GtBIndex 目录页「底稿架构」上方（仅追加，不改动 GtBIndex 既有架构树/循环网格）：
 * - 编制进度条 + 跨表结论口径看板（各表审计结论已填/未填 + 跳转）+ 编制提示 details
 * - 自行拉取本底稿 checklist-responses（GtBIndex 不持有 allResponses），也支持外部传入 allResponses
 * - 跳转经 emit('navigate', sheetName)（由 GtBIndex 的 handleNavigate → jump-to-section 转发）
 *
 * 注：E1 各表审计结论为自由文本（非 A/B/C 枚举），故看板按"已填/未填"分类。
 */
import { computed, onMounted, ref, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import GtReviewTrigger from '../GtReviewTrigger.vue'

const E1PreparationHandbookDialog = defineAsyncComponent(() => import('./E1PreparationHandbookDialog.vue'))

// ═══ 编制/使用手册弹窗 ═══
const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage') {
  handbookTab.value = tab
  handbookVisible.value = true
}

const props = defineProps<{
  wpId?: string
  /** 外部可直接传入已加载的响应 Map；缺省时组件自行拉取 */
  allResponses?: Map<string, any>
  /** sheet 全名列表（如 b-index navigation_rows），供 jumpToSection 精确匹配 */
  availableSheets?: Array<{ sheet_name?: string; content?: string }>
}>()

const emit = defineEmits<{ (e: 'navigate', sheetName: string): void }>()

// ═══ 响应数据：优先外部传入，否则自行拉取 ═══
const fetchedResponses = ref<Map<string, any>>(new Map())
const responses = computed<Map<string, any>>(() => props.allResponses ?? fetchedResponses.value)

onMounted(async () => {
  if (props.allResponses || !props.wpId) return
  try {
    const res: any = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
    const list = res?.data?.items ?? res?.items ?? res?.data ?? res
    const map = new Map<string, any>()
    if (Array.isArray(list)) {
      for (const it of list) {
        if (it?.item_id) map.set(it.item_id, it)
      }
    }
    fetchedResponses.value = map
  } catch {
    /* silent：拉取失败则看板全显未填，不影响 GtBIndex 架构树 */
  }
})

// ═══ E1 各表审计结论/说明键（源自各子组件 CONCLUSION_KEY / NOTE_KEY） ═══
interface SheetDef {
  code: string
  name: string
  noteKey: string
  conclusionKey: string
}

const E1_SHEETS: SheetDef[] = [
  { code: 'E1-1', name: '审定表', noteKey: 'E1-adj-audit-note', conclusionKey: 'E1-adj-audit-conclusion' },
  { code: 'E1-2', name: '现金明细表', noteKey: 'E1-cash-audit-note', conclusionKey: 'E1-cash-audit-conclusion' },
  { code: 'E1-3', name: '银行存款明细表', noteKey: 'E1-bank-audit-note', conclusionKey: 'E1-bank-audit-conclusion' },
  { code: 'E1-4', name: '数字货币明细表', noteKey: 'E1-digital-audit-note', conclusionKey: 'E1-digital-audit-conclusion' },
  { code: 'E1-5', name: '调整分录', noteKey: 'E1-adjustment-audit-note', conclusionKey: 'E1-adjustment-audit-conclusion' },
  { code: 'E1-6', name: '余额调节表', noteKey: 'E1-recon-audit-note', conclusionKey: 'E1-recon-audit-conclusion' },
  { code: 'E1-7', name: '库存现金盘点(人民币)', noteKey: 'E1-cashcount-audit-note-rmb', conclusionKey: 'E1-cashcount-audit-conclusion-rmb' },
  { code: 'E1-8', name: '库存现金盘点(外币)', noteKey: 'E1-cashcount-audit-note-fx', conclusionKey: 'E1-cashcount-audit-conclusion-fx' },
  { code: 'E1-9', name: '银行存单盘点表', noteKey: 'E1-cert-audit-note', conclusionKey: 'E1-cert-audit-conclusion' },
  { code: 'E1-10', name: '银行账户核对表', noteKey: 'E1-acctlist-audit-note', conclusionKey: 'E1-acctlist-audit-conclusion' },
  { code: 'E1-11', name: '银行账户完整性承诺书', noteKey: 'E1-commit-audit-note', conclusionKey: 'E1-commit-audit-conclusion' },
  { code: 'E1-14', name: '分析表', noteKey: 'E1-analysis-audit-note', conclusionKey: 'E1-analysis-audit-conclusion' },
  { code: 'E1-15', name: '利息收入月度分析', noteKey: 'E1-interest-audit-note', conclusionKey: 'E1-interest-audit-conclusion' },
  { code: 'E1-18', name: '企业信用报告查询', noteKey: 'E1-credit-audit-note-query', conclusionKey: 'E1-credit-audit-conclusion-query' },
  { code: 'E1-19', name: '企业信用报告核对', noteKey: 'E1-credit-audit-note-check', conclusionKey: 'E1-credit-audit-conclusion-check' },
  { code: 'E1-20', name: '应计利息测算', noteKey: 'E1-accrued-audit-note', conclusionKey: 'E1-accrued-audit-conclusion' },
  { code: 'E1-21', name: '银行存款截止测试', noteKey: 'E1-cutoff-audit-note-bank', conclusionKey: 'E1-cutoff-audit-conclusion-bank' },
  { code: 'E1-22', name: '其他货币资金截止测试', noteKey: 'E1-cutoff-audit-note-other', conclusionKey: 'E1-cutoff-audit-conclusion-other' },
  { code: 'E1-23', name: '收支检查情况表', noteKey: 'E1-largecheck-audit-note', conclusionKey: 'E1-largecheck-audit-conclusion' },
]

// ═══ 完成判定 ═══
function isFilled(key: string): boolean {
  const raw = responses.value?.get?.(key)
  const text = (raw?.remark ?? raw?.conclusion ?? '') as string
  return typeof text === 'string' && text.trim().length > 0
}

/** 编制进度：审计说明或审计结论任一填写即视为该表已编制 */
const completedCount = computed(() =>
  E1_SHEETS.filter(s => isFilled(s.noteKey) || isFilled(s.conclusionKey)).length,
)
const progressPct = computed(() => {
  const total = E1_SHEETS.length
  return total > 0 ? Math.round((completedCount.value / total) * 100) : 0
})

// ═══ 跨表结论口径看板 ═══
interface ConclusionSheet {
  code: string
  filled: boolean
}

const conclusionSheets = computed<ConclusionSheet[]>(() =>
  E1_SHEETS.map(s => ({ code: s.code, filled: isFilled(s.conclusionKey) })),
)

const filledCount = computed(() => conclusionSheets.value.filter(c => c.filled).length)
const hasUnfilled = computed(() => conclusionSheets.value.some(c => !c.filled))

const worstLabel = computed(() => {
  if (filledCount.value === 0) return '结论未填'
  if (hasUnfilled.value) return `结论未齐 ${E1_SHEETS.length - filledCount.value} 项`
  return '总体已齐'
})

const worstTagType = computed<'success' | 'warning' | 'info'>(() => {
  if (filledCount.value === 0) return 'info'
  if (hasUnfilled.value) return 'warning'
  return 'success'
})

// ═══ 跳转（emit navigate → GtBIndex handleNavigate → jump-to-section） ═══
/** 按编码精确匹配 sheet 全名（避免 E1-1 误配 E1-10/E1-11 等）。 */
function resolveSheetLabel(code: string): string {
  if (props.availableSheets?.length) {
    const boundary = new RegExp(`${code.replace(/[-]/g, '\\-')}(?!\\d)`)
    const hit = props.availableSheets.find(s => {
      const name = s.sheet_name || s.content || ''
      return name && boundary.test(name)
    })
    if (hit) return hit.sheet_name || hit.content || code
  }
  return code
}

function goSheet(code: string) {
  emit('navigate', resolveSheetLabel(code))
}
</script>

<style scoped>
.e1-dir { font-size: var(--wp-font-size, 13px); margin-bottom: 20px; }
.index-header { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.title { margin: 0; }
.handbook-btns { display: flex; gap: 6px; }
.progress-wrap { flex: 1; min-width: 200px; }
.conclusion-board {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  border-left: 3px solid #409eff;
}
.board-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.board-meta { font-size: 12px; color: #909399; }
.board-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.concl-tag.clickable { cursor: pointer; }
.board-hint { margin: 8px 0 0; font-size: 12px; color: #e6a23c; }
.methodology-hint { margin-top: 12px; font-size: 12px; color: #606266; }
</style>
