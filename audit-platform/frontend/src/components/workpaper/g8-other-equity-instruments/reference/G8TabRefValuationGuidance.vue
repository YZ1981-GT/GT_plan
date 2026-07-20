<template>
  <div class="g8-tab-ref-valuation" data-testid="g8-ref-valuation">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="本 sheet 为参考材料（中证协《非上市公司股权估值指引》要点），仅供查阅，不支持编辑"
      class="ref-info-bar"
    />

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="ref-info-bar"
      title="Level3 编制提示：选择市场法/收益法/资产基础法后，须在 G8-4 填写估值技术、不可观察输入值及估值文件索引；本表不可替代具体估值工作底稿。"
    />

    <div class="ref-toolbar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索章节/要点…"
        size="small"
        clearable
        style="width: 280px"
      />
      <el-tag v-if="searchKeyword && filteredRows.length !== tableRows.length" size="small" type="info">
        匹配 {{ filteredRows.length }} / {{ tableRows.length }} 行
      </el-tag>
      <el-tag size="small" type="danger">适用于 G8-4 Level3</el-tag>
    </div>

    <el-table
      :data="filteredRows"
      border
      stripe
      size="small"
      :max-height="560"
      style="width:100%;font-size:13px"
      empty-text="暂无参考行。若模板已导入 Excel 指引表，将优先显示模板数据。"
    >
      <el-table-column prop="seq" label="#" width="48" align="center" />
      <el-table-column prop="chapter" label="章节" width="120" />
      <el-table-column prop="topic" label="主题" width="140" />
      <el-table-column prop="method" label="常用方法" width="120" />
      <el-table-column label="要点" min-width="280">
        <template #default="{ row }">
          <span v-if="searchKeyword" v-html="highlightText(row.point, searchKeyword)" />
          <span v-else>{{ row.point }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="auditFocus" label="审计关注" min-width="200" />
    </el-table>

    <details class="guidance-details" open>
      <summary>编制提示</summary>
      <ul>
        <li>内容摘录自中证协《非上市公司股权估值指引》的审计常用要点，非全文替代。</li>
        <li>G8-4 判定为 Level3 时，应结合本表选择估值路径，并在估值详情区留痕。</li>
        <li>若项目模板 Excel 含完整指引表，系统优先展示模板行数据。</li>
        <li>所有内容只读，不可在本页编辑保存。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G8TabRefValuationGuidance — 参考中证协《非上市公司股权估值指引》
 * 对齐 G4 参考 sheet：只读 + 搜索；无 htmlData 时使用内置要点表。
 */
import { ref, computed } from 'vue'

const props = defineProps<{
  htmlData?: Record<string, any> | null
  wpId?: string
  projectId?: string
  isReadonly?: boolean
}>()

interface RefRow {
  seq: number
  chapter: string
  topic: string
  method: string
  point: string
  auditFocus: string
}

/** 内置审计常用要点（非全文复制） */
const SEED_ROWS: RefRow[] = [
  { seq: 1, chapter: '总则', topic: '适用范围', method: '—', point: '适用于非上市公司股权公允价值计量与估值，尤其缺乏活跃市场报价时。', auditFocus: '确认被投资单位是否确属非上市、无可靠 Level1 报价' },
  { seq: 2, chapter: '基本原则', topic: '公允价值定义', method: '—', point: '估值应反映市场参与者在计量日有序交易中出售资产可收取的价格。', auditFocus: '持有目的、交易限制是否已在估值中考虑' },
  { seq: 3, chapter: '基本原则', topic: '方法选择', method: '市场/收益/资产', point: '应选择与投资性质、可获数据质量相匹配的估值方法，必要时交叉验证。', auditFocus: 'G8-4 估值方法与上期一致性；变更须说明' },
  { seq: 4, chapter: '市场法', topic: '可比公司法', method: '市场法', point: '选取经营与财务特征可比的公司，运用市盈率、市净率等乘数并作必要调整。', auditFocus: '可比样本代表性、乘数口径、流动性折价' },
  { seq: 5, chapter: '市场法', topic: '可比交易法', method: '市场法', point: '参考近期类似股权交易价格，考虑交易背景、控制权溢价与时间差异。', auditFocus: '交易是否公允、是否关联方、时效性' },
  { seq: 6, chapter: '收益法', topic: '现金流折现', method: '收益法', point: '基于合理预测的未来现金流与折现率，估计股权价值。', auditFocus: '预测假设、折现率构成、终值与永续增长率' },
  { seq: 7, chapter: '收益法', topic: '输入值', method: '收益法', point: '关键输入值包括收入增速、利润率、资本结构、WACC/股权成本等。', auditFocus: 'Level3 不可观察输入值须在 G8-4 描述并索引底稿' },
  { seq: 8, chapter: '资产基础法', topic: '净资产调整', method: '资产基础法', point: '以资产负债表为基础，对资产负债按公允价值调整后确定股权价值。', auditFocus: '重大资产评估依据、或有负债、表外事项' },
  { seq: 9, chapter: '特殊事项', topic: '流动性与控制权', method: '调整', point: '非上市股权通常需考虑缺乏流动性折价；控制权/少数股权溢折价应有依据。', auditFocus: '折价率来源、是否与持股比例一致' },
  { seq: 10, chapter: '特殊事项', topic: '近期融资', method: '校准', point: '若存在近期外部融资轮次，可作为校准公允价值的重要证据。', auditFocus: '融资是否独立第三方、条款是否影响可比性' },
  { seq: 11, chapter: '质量控制', topic: '复核与文档', method: '—', point: '估值过程、关键假设、计算过程与结论应形成可复核文档。', auditFocus: 'G8-4 估值文件索引号；外部估值报告复核' },
  { seq: 12, chapter: '质量控制', topic: '敏感性', method: '—', point: '对重大不可观察输入值应进行敏感性分析并评估结论稳健性。', auditFocus: '重大假设变动对审定金额的影响是否披露/说明' },
]

const searchKeyword = ref('')

function extractRows(data: Record<string, any> | null | undefined): RefRow[] {
  if (!data) return []
  const raw = data.rows || data.data || data.tableData
  if (!Array.isArray(raw) || !raw.length) return []
  return raw.map((r: any, i: number) => ({
    seq: Number(r.seq ?? r.col0 ?? i + 1),
    chapter: String(r.chapter ?? r.col1 ?? r['章节'] ?? ''),
    topic: String(r.topic ?? r.col2 ?? r['主题'] ?? ''),
    method: String(r.method ?? r.col3 ?? r['方法'] ?? ''),
    point: String(r.point ?? r.col4 ?? r['要点'] ?? r['条款内容'] ?? JSON.stringify(r)),
    auditFocus: String(r.auditFocus ?? r.col5 ?? r['审计关注'] ?? ''),
  }))
}

const tableRows = computed(() => {
  const fromHtml = extractRows(props.htmlData)
  return fromHtml.length ? fromHtml : SEED_ROWS
})

const filteredRows = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return tableRows.value
  return tableRows.value.filter((row) =>
    [row.chapter, row.topic, row.method, row.point, row.auditFocus]
      .some((v) => String(v).toLowerCase().includes(kw)),
  )
})

function highlightText(text: string, keyword: string): string {
  if (!keyword) return text
  const escaped = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return String(text ?? '').replace(new RegExp(`(${escaped})`, 'gi'), '<mark class="search-highlight">$1</mark>')
}
</script>

<style scoped>
.g8-tab-ref-valuation { font-size: var(--wp-font-size, 13px); }
.ref-info-bar { margin-bottom: 10px; }
.ref-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
.guidance-details {
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #303133; }
.guidance-details ul { margin: 8px 0 0 16px; padding: 0; }
.guidance-details li { margin-bottom: 4px; }
:deep(.search-highlight) {
  background-color: #ffd54f;
  padding: 0 2px;
  border-radius: 2px;
}
</style>
