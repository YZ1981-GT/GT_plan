<script setup lang="ts">
/**
 * D4TabIndex — 统一底稿目录（合并8个源文件底稿目录为统一清单 42行）
 *
 * 每行 GtIndexChip 跳转对应二级 Tab
 * 不适用行灰色 + 进度条
 * 作为"核心"组第一个二级Tab
 *
 * Requirements: 31.1-31.5
 */
import { computed, inject, onMounted, ref, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { resolveD4SheetLabel } from '../../composables/d4SheetLabels'
import { useAcnrCatalogIndex } from '../../composables/useAcnrCatalogIndex'
import { parseIndexRef } from '@/utils/parseIndexRef'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { loadCycleWorkpaperCards, type CycleWpCard } from '@/services/cycleDirectory'

const D4PreparationHandbookDialog = defineAsyncComponent(() => import('../D4PreparationHandbookDialog.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  ipoGroupVisible: boolean
  hasExportBusiness: boolean
  availableSheets?: Array<{ sheet_name?: string }>
}>()

// ─── 底稿目录数据 ─────────────────────────────────────────────────────

interface IndexRow {
  seq: number
  name: string
  code: string
  group: string
  tabName: string
  /** 是否适用（不适用的灰色显示） */
  applicable: boolean
}

const indexRows = computed<IndexRow[]>(() => {
  const ipo = props.ipoGroupVisible
  const exp = props.hasExportBusiness

  return [
    // 核心组
    { seq: 1, name: '底稿目录', code: 'D4-目录', group: '核心', tabName: 'index', applicable: true },
    { seq: 2, name: '营业收入审计程序表', code: 'D4A', group: '核心', tabName: 'procedure', applicable: true },
    { seq: 3, name: '营业收入审定表', code: 'D4-1', group: '核心', tabName: 'adjudication', applicable: true },
    { seq: 4, name: '主营业务收入明细表', code: 'D4-2', group: '核心', tabName: 'revenue-detail', applicable: true },
    { seq: 5, name: '其他业务收入明细表', code: 'D4-3', group: '核心', tabName: 'other-revenue', applicable: true },
    { seq: 6, name: '营业收入调整分录汇总', code: 'D4-4', group: '核心', tabName: 'adjustment', applicable: true },
    { seq: 7, name: '附注披露信息（上市公司）', code: 'D4-附注上市', group: '核心', tabName: 'disclosure-listed', applicable: true },
    { seq: 8, name: '附注披露信息（国有企业）', code: 'D4-附注国企', group: '核心', tabName: 'disclosure-soe', applicable: true },
    // 政策组
    { seq: 9, name: '营业收入会计政策检查', code: 'D4-5', group: '政策', tabName: 'policy-check', applicable: true },
    // 分析程序组
    { seq: 10, name: '重要指标分析', code: 'D4-6', group: '分析程序', tabName: 'indicator', applicable: true },
    { seq: 11, name: '毛利率分析表', code: 'D4-7', group: '分析程序', tabName: 'margin-monthly', applicable: true },
    { seq: 12, name: '重要产品毛利分析', code: 'D4-8', group: '分析程序', tabName: 'product-margin', applicable: true },
    { seq: 13, name: '重要客户结构分析', code: 'D4-9', group: '分析程序', tabName: 'customer-structure', applicable: true },
    { seq: 14, name: '重要客户销售价格分析', code: 'D4-10', group: '分析程序', tabName: 'customer-price', applicable: true },
    { seq: 15, name: '产品销售价格分析', code: 'D4-11', group: '分析程序', tabName: 'product-price', applicable: true },
    // 检查程序组
    { seq: 16, name: '合同检查表', code: 'D4-12', group: '检查程序', tabName: 'contract', applicable: true },
    { seq: 17, name: 'ERP系统核对', code: 'D4-13', group: '检查程序', tabName: 'erp-check', applicable: true },
    { seq: 18, name: '营业收入发生检查表', code: 'D4-14', group: '检查程序', tabName: 'occurrence', applicable: true },
    { seq: 19, name: '营业收入完整性检查表', code: 'D4-15', group: '检查程序', tabName: 'completeness', applicable: true },
    { seq: 20, name: '出口收入电子口岸核对', code: 'D4-16', group: '检查程序', tabName: 'export-check', applicable: exp },
    { seq: 21, name: '截止测试（账到单据）', code: 'D4-17', group: '检查程序', tabName: 'cutoff-forward', applicable: true },
    { seq: 22, name: '截止测试（单据到账）', code: 'D4-18', group: '检查程序', tabName: 'cutoff-backward', applicable: true },
    { seq: 23, name: '销售折扣与折让检查', code: 'D4-19', group: '检查程序', tabName: 'discount', applicable: true },
    { seq: 24, name: '销售退货检查表', code: 'D4-20', group: '检查程序', tabName: 'return-check', applicable: true },
    // 关联方组
    { seq: 25, name: '关联方销售价格分析', code: 'D4-21', group: '关联方', tabName: 'related-price', applicable: true },
    // IPO/舞弊组
    { seq: 26, name: 'IPO审计程序表', code: 'D4-22A', group: 'IPO/舞弊', tabName: 'ipo-procedure', applicable: ipo },
    { seq: 27, name: '重要指标分析（IPO版）', code: 'D4-22', group: 'IPO/舞弊', tabName: 'ipo-indicator', applicable: ipo },
    { seq: 28, name: '收入与开具发票金额比较', code: 'D4-23', group: 'IPO/舞弊', tabName: 'invoice-compare', applicable: ipo },
    { seq: 29, name: '第三方回款检查', code: 'D4-24', group: 'IPO/舞弊', tabName: 'third-party', applicable: ipo },
    { seq: 30, name: '经销商检查', code: 'D4-25', group: 'IPO/舞弊', tabName: 'dealer', applicable: ipo },
    { seq: 31, name: '境外销售收入检查', code: 'D4-26', group: 'IPO/舞弊', tabName: 'overseas', applicable: ipo && exp },
    { seq: 32, name: '识别未披露的关联方', code: 'D4-27', group: 'IPO/舞弊', tabName: 'undisclosed-rp', applicable: ipo },
    { seq: 33, name: '客户信息核查清单', code: 'D4-28', group: 'IPO/舞弊', tabName: 'customer-checklist', applicable: ipo },
    { seq: 34, name: '客户信息检查表', code: 'D4-29', group: 'IPO/舞弊', tabName: 'customer-detail', applicable: ipo },
    { seq: 35, name: '客户访谈记录汇总表', code: 'D4-30', group: 'IPO/舞弊', tabName: 'interview-summary', applicable: ipo },
    { seq: 36, name: '客户访谈记录', code: 'D4-31', group: 'IPO/舞弊', tabName: 'interview-detail', applicable: ipo },
    { seq: 37, name: '客户/供应商资金流水检查', code: 'D4-32', group: 'IPO/舞弊', tabName: 'fund-flow', applicable: ipo },
    // 其他收入组
    { seq: 38, name: '其他业务毛利率分析表', code: 'D4-33', group: '其他收入', tabName: 'other-margin', applicable: true },
    { seq: 39, name: '其他业务收入合同测算表', code: 'D4-34', group: '其他收入', tabName: 'other-contract', applicable: true },
    { seq: 40, name: '其他业务收入检查表', code: 'D4-35', group: '其他收入', tabName: 'other-check', applicable: true },
    { seq: 41, name: '其他业务收入截止测试', code: 'D4-36', group: '其他收入', tabName: 'other-cutoff', applicable: true },
    // 访谈模板
    { seq: 42, name: '访谈记录与核对示例', code: 'D4-访谈模板', group: 'IPO/舞弊', tabName: 'interview-template', applicable: ipo },
  ]
})

// ─── ACNR catalog 名称合并（Req 18.1 / 18.2 / 18.7）───────────────────────────
// indexRows(上) 为本地配置，仅保留 catalog 不持有的 tabName(intra-bundle 跳转目标)/
// applicable(per-project 适用性)/group 等元数据，按 code(=sheet_code) keyed（Req 18.2 / 18.5）。
// 显示名称从 ACNR catalog 取（Req 18.1）；catalog 空/失败 → 回退硬编码 name（Req 18.7）。
const { catalogIndex, loadCatalogIndex } = useAcnrCatalogIndex()

const router = useRouter()
const cycleWorkpapers = ref<CycleWpCard[]>([])
async function loadCycleWorkpapers(): Promise<void> {
  cycleWorkpapers.value = await loadCycleWorkpaperCards(props.projectId, 'D', props.wpId)
}
function onCycleCardClick(wp: CycleWpCard): void {
  if (!wp.wp_id || wp.is_current || !props.projectId) return
  router.push({ name: 'WorkpaperEditor', params: { projectId: props.projectId, wpId: wp.wp_id } })
}

onMounted(() => {
  loadCatalogIndex('D')
  void loadCycleWorkpapers()
})

// ─── 编制/使用手册弹窗 ─────────────────────────────────────────────────
const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage') {
  handbookTab.value = tab
  handbookVisible.value = true
}

// ─── 跨表结论口径看板（审定/明细/检查类，排除程序表/附注/调整分录/不适用）───
const jumpToSectionFn = inject<((sheetName: string) => void) | null>('jumpToSection', null)
function isConclusionFilled(code: string): boolean {
  const map = props.allResponses instanceof Map ? props.allResponses : (props.allResponses as any)?.value ?? new Map()
  if (!map?.size) return false
  const token = `${code}-`
  for (const [key, val] of map.entries()) {
    if (!key.includes(token)) continue
    if (!/conclusion|audit-note|note/i.test(key)) continue
    const text = (val?.remark ?? val?.conclusion ?? '') as string
    if (typeof text === 'string' && text.trim().length > 0) return true
  }
  return false
}
const CONCLUSION_RE = /^D4-\d+$/
const conclusionSheets = computed(() =>
  displayRows.value
    .filter(r => r.applicable && CONCLUSION_RE.test(r.code) && !/调整分录/.test(r.name))
    .map(r => ({ code: r.code, sheetKey: resolveD4SheetLabel(r.code, props.availableSheets), filled: isConclusionFilled(r.code) })),
)
const conclusionFilledCount = computed(() => conclusionSheets.value.filter(c => c.filled).length)
const conclusionHasUnfilled = computed(() => conclusionSheets.value.some(c => !c.filled))
const conclusionWorstLabel = computed(() => {
  if (conclusionFilledCount.value === 0) return '结论未填'
  if (conclusionHasUnfilled.value) return `结论未齐 ${conclusionSheets.value.length - conclusionFilledCount.value} 项`
  return '总体已齐'
})
const conclusionWorstType = computed<'success' | 'warning' | 'info'>(() => {
  if (conclusionFilledCount.value === 0) return 'info'
  if (conclusionHasUnfilled.value) return 'warning'
  return 'success'
})
function jumpConclusion(sheetKey: string) {
  if (jumpToSectionFn && sheetKey) jumpToSectionFn(sheetKey)
}

interface DisplayRow extends IndexRow {
  addrId?: string
  order: number
}

const displayRows = computed<DisplayRow[]>(() =>
  indexRows.value.map((r) => {
    const cat = catalogIndex.value.get(r.code)
    return {
      ...r,
      name: cat?.sheet_name || r.name,
      addrId: cat?.addr_id,
      order: cat?.order ?? r.seq,
    }
  }),
)

/** code 是否可被索引文法解析为可跳转 chip（Chinese 合成码如 D4-目录/D4-附注上市 不可） */
function isParseableCode(code: string): boolean {
  return parseIndexRef(code) != null
}

// ─── 进度计算 ─────────────────────────────────────────────────────────

const applicableCount = computed(() => displayRows.value.filter(r => r.applicable).length)

/** 简易进度：有对应 allResponses 数据的视为已编制 */
const completedCount = computed(() => {
  let count = 0
  for (const row of displayRows.value) {
    if (!row.applicable) continue
    // 检查是否有对应的 checklist_responses 数据
    const hasData = props.allResponses.has(`${row.code}-rows`) ||
      props.allResponses.has(`${row.code}-note`) ||
      props.allResponses.has(`${row.code}-params`)
    if (hasData) count++
  }
  return count
})

const progressPercent = computed(() => {
  if (applicableCount.value === 0) return 0
  return Math.round((completedCount.value / applicableCount.value) * 100)
})

// ─── 跳转 ────────────────────────────────────────────────────────────

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

function navigateToSheet(row: IndexRow) {
  if (!row.applicable || !jumpToSection) return
  jumpToSection(resolveD4SheetLabel(row.code, props.availableSheets))
}

function indexRowClassName({ row }: { row: IndexRow }): string {
  return row.applicable ? '' : 'inapplicable-row'
}
</script>

<template>
  <div class="d4-tab-index">
    <!-- 目录卡头部（标题 + 复核 + 编制/使用手册） -->
    <div class="dir-header">
      <h3 class="dir-title">D4 底稿目录</h3>
      <GtReviewTrigger section-id="D4-index-directory" />
      <div class="handbook-btns">
        <el-button size="small" type="primary" plain @click="openHandbook('preparation')">📖 编制手册</el-button>
        <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
      </div>
    </div>

    <D4PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />

    <!-- 进度条 -->
    <div class="progress-bar-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ applicableCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
    </div>

    <!-- 跨表结论口径看板 -->
    <div class="conclusion-board">
      <div class="board-head">
        <strong>跨表结论口径</strong>
        <el-tag size="small" :type="conclusionWorstType">{{ conclusionWorstLabel }}</el-tag>
        <span class="board-meta">已填 {{ conclusionFilledCount }}/{{ conclusionSheets.length }}</span>
      </div>
      <div class="board-tags">
        <el-tag
          v-for="c in conclusionSheets"
          :key="c.code"
          size="small"
          class="concl-tag clickable"
          :type="c.filled ? 'success' : 'info'"
          effect="plain"
          @click="jumpConclusion(c.sheetKey)"
        >
          {{ c.code }} {{ c.filled ? '已填' : '未填' }}
        </el-tag>
      </div>
      <p v-if="conclusionHasUnfilled" class="board-hint">存在未填审计结论，请点击标签跳转补全审计说明与结论。</p>
    </div>

    <!-- 目录表 -->
    <el-table
      :data="displayRows"
      border
      size="small"
      :row-class-name="indexRowClassName"
      style="width: 100%"
    >
      <el-table-column prop="seq" label="序号" width="60" align="center" />
      <el-table-column prop="name" label="底稿名称" min-width="260">
        <template #default="{ row }">
          <span :class="{ 'text-gray': !row.applicable }">{{ row.name }}</span>
          <el-tag v-if="!row.applicable" size="small" type="info" style="margin-left: 8px">不适用</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="code" label="编码" width="100" align="center" />
      <el-table-column prop="group" label="所属分组" width="100" align="center" />
      <el-table-column label="跳转" width="80" align="center">
        <template #default="{ row }">
          <!-- 标准编码：用 GtIndexChip（Req 18.3），bundle 内 sheet 切换仍走 jumpToSection -->
          <GtIndexChip
            v-if="row.applicable && jumpToSection && isParseableCode(row.code)"
            :label="row.code"
            :prevent-navigate="true"
            :validate="false"
            @click="navigateToSheet(row)"
          />
          <!-- 合成码（D4-目录/D4-附注上市 等含中文，索引文法不可解析）保留 → 跳转，避免回归 -->
          <span
            v-else-if="row.applicable && jumpToSection"
            class="gt-index-chip"
            :title="`跳转到 ${row.name}`"
            @click="navigateToSheet(row)"
          >→</span>
          <span v-else class="text-gray">-</span>
        </template>
      </el-table-column>
    </el-table>

    <details class="methodology-hint">
      <summary>编制提示</summary>
      <p>推荐工作流：D4A 程序表 → D4-2/D4-3 明细（可从序时账取数）→ 发生/截止/完整性检查 + 分析程序 → D4-4 调整分录 → 确认回写 D4-1 → 勾稽 TB(6001/6051)/利润表 → 附注。IPO/舞弊组、出口核对按项目性质适用。</p>
    </details>

    <!-- 本循环底稿目录（D 循环其他科目，可跳转） -->
    <div v-if="cycleWorkpapers.length" class="cycle-section">
      <div class="cycle-header">
        <h4 class="cycle-title">本循环底稿目录</h4>
        <span class="cycle-hint">点击可跳转至同循环其他底稿（灰色表示尚未生成）</span>
      </div>
      <div class="cycle-grid">
        <div
          v-for="wp in cycleWorkpapers"
          :key="wp.wp_code"
          class="cycle-card"
          :class="{ 'is-current': wp.is_current, 'is-disabled': !wp.wp_id }"
          @click="onCycleCardClick(wp)"
        >
          <div class="cycle-card-top">
            <span class="cycle-code">{{ wp.wp_code }}</span>
            <el-tag v-if="wp.is_current" size="small" effect="plain" class="cycle-current-tag">当前</el-tag>
          </div>
          <span class="cycle-name" :title="wp.wp_name">{{ wp.wp_name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.d4-tab-index {
  padding: 12px;
}
.progress-bar-section {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}
.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.progress-text {
  font-weight: 600;
  color: #303133;
}
.gt-index-chip {
  display: inline-block;
  padding: 2px 8px;
  font-size: 12px;
  background: #e6f7ff;
  border: 1px solid #91d5ff;
  border-radius: 4px;
  color: #1890ff;
  cursor: pointer;
}
.gt-index-chip:hover {
  background: #bae7ff;
}
.text-gray {
  color: #c0c4cc;
}
:deep(.inapplicable-row) {
  background-color: #fafafa !important;
  color: #c0c4cc;
}
.dir-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.dir-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.handbook-btns { display: flex; gap: 6px; }
.conclusion-board { margin: 0 0 16px; padding: 10px 12px; background: #f5f7fa; border-radius: 6px; border-left: 3px solid #409eff; }
.board-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.board-head strong { font-size: 13px; color: #303133; }
.board-meta { font-size: 12px; color: #909399; }
.board-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.concl-tag.clickable { cursor: pointer; }
.board-hint { margin: 8px 0 0; font-size: 12px; color: #e6a23c; }
.methodology-hint { margin-top: 16px; padding: 10px 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 0 4px 4px 0; font-size: var(--wp-font-size, 13px); color: #606266; }
.methodology-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.cycle-section { margin-top: 24px; }
.cycle-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.cycle-title { margin: 0; font-size: 16px; font-weight: 600; color: #303133; }
.cycle-hint { font-size: 12px; color: #909399; }
.cycle-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
.cycle-card { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border: 1px solid var(--gt-color-border-purple, #e8e4f0); border-radius: 8px; background: #fff; cursor: pointer; transition: all 0.2s; }
.cycle-card:hover { border-color: var(--gt-color-primary, #4b2d77); box-shadow: 0 2px 8px rgba(75, 45, 119, 0.12); transform: translateY(-2px); }
.cycle-card.is-current { border-color: var(--gt-color-primary, #4b2d77); background: var(--gt-color-primary-bg, #f4f0fa); box-shadow: 0 0 0 1px var(--gt-color-primary, #4b2d77); cursor: default; }
.cycle-card.is-disabled { opacity: 0.5; cursor: not-allowed; }
.cycle-card.is-disabled:hover { border-color: var(--gt-color-border-purple, #e8e4f0); box-shadow: none; transform: none; }
.cycle-card-top { display: flex; align-items: center; gap: 6px; }
.cycle-code { font-size: var(--wp-font-size, 13px); font-weight: 700; color: var(--gt-color-primary, #4b2d77); }
.cycle-current-tag { margin-left: auto; }
.cycle-name { font-size: var(--wp-font-size, 13px); line-height: 1.4; color: #303133; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
</style>
