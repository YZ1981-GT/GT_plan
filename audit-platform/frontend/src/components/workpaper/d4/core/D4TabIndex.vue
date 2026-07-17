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
import { computed, inject, onMounted } from 'vue'
import { resolveD4SheetLabel } from '../../composables/d4SheetLabels'
import { useAcnrCatalogIndex } from '../../composables/useAcnrCatalogIndex'
import { parseIndexRef } from '@/utils/parseIndexRef'
import GtIndexChip from '../../GtIndexChip.vue'

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

onMounted(() => {
  loadCatalogIndex('D')
})

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
    <!-- 进度条 -->
    <div class="progress-bar-section">
      <div class="progress-info">
        <span>编制进度</span>
        <span class="progress-text">{{ completedCount }} / {{ applicableCount }} ({{ progressPercent }}%)</span>
      </div>
      <el-progress :percentage="progressPercent" :stroke-width="8" :show-text="false" />
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
</style>
