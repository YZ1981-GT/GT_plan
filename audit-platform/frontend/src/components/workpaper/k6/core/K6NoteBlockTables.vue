<template>
  <div class="k6-note-blocks">
    <!-- ═══ 附注表：持有待售资产减值准备（源模板「本期减少」下辖 转回/出售 两个子列） ═══ -->
    <el-card shadow="never" class="k6-block">
      <template #header>
        <div class="block-head">
          <span class="block-title">附注表·持有待售资产减值准备</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" @click="blocks.addRow('impairment')">
            + 项目
          </el-button>
        </div>
      </template>
      <div class="block-hint">
        勾稽：期末数 = {{ priorLabel }} + 本期增加 − 本期转回 − 本期出售（逐行）；本表期末合计应与
        主表「减值准备」列期末数核对一致。源模板「本期减少」下辖「本期转回」「本期出售」两个子列，
        不可合并成一列填列。
      </div>
      <el-table :data="blocks.impairment.value" border size="small" style="width:100%" show-summary :summary-method="impairmentSummary">
        <el-table-column prop="project" label="项目" min-width="160" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.project"
              size="small"
              placeholder="资产项目"
              @input="(v: string) => blocks.updateField('impairment', row.id, 'project', v)"
            />
            <span v-else>{{ row.project || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priorAmount" :label="priorLabel" width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.priorAmount" @change="(v?: number) => blocks.updateField('impairment', row.id, 'priorAmount', v ?? 0)" />
            <span v-else>{{ fmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" width="130" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.increase" @change="(v?: number) => blocks.updateField('impairment', row.id, 'increase', v ?? 0)" />
            <span v-else>{{ fmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少">
          <el-table-column prop="reverse" label="本期转回" width="130" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.reverse" @change="(v?: number) => blocks.updateField('impairment', row.id, 'reverse', v ?? 0)" />
              <span v-else>{{ fmt(row.reverse) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="disposal" label="本期出售" width="130" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.disposal" @change="(v?: number) => blocks.updateField('impairment', row.id, 'disposal', v ?? 0)" />
              <span v-else>{{ fmt(row.disposal) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末数" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :title="`期末 = ${priorLabel} + 本期增加 − 本期转回 − 本期出售`">
              {{ fmt(blocks.endOf(row)) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link :disabled="isReadonly" @click="blocks.removeRow('impairment', row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 附注表：持有待售非流动资产 / 处置组（公允价值 5 列） ═══ -->
    <K6FairValueBlock
      title="附注表·持有待售的非流动资产"
      :hint="`【提示：期末账面价值应小于等于（期末公允价值 − ${feeLabel}）—— 划分为持有待售后按二者较低者计量。】数据来源：初始确认检查表 K6-4。`"
      :rows="blocks.nonCurrent.value"
      :fee-label="feeLabel"
      :is-readonly="isReadonly"
      @add="blocks.addRow('nonCurrent')"
      @remove="(id: string) => blocks.removeRow('nonCurrent', id)"
      @update="(id: string, f: string, v: unknown) => blocks.updateField('nonCurrent', id, f, v)"
    />

    <K6FairValueBlock
      title="附注表·持有待售的处置组"
      hint="按处置组逐个披露：资产段与负债段分别列示明细。源模板的「① 子公司A」「② 分公司B」是示例处置组名，实际处置组名称由本表动态行提供。数据来源：初始确认检查表 K6-4 / 处置组减值测试表 K6-6。"
      :rows="blocks.disposalGroup.value"
      :fee-label="feeLabel"
      :is-readonly="isReadonly"
      @add="blocks.addRow('disposalGroup')"
      @remove="(id: string) => blocks.removeRow('disposalGroup', id)"
      @update="(id: string, f: string, v: unknown) => blocks.updateField('disposalGroup', id, f, v)"
    />

    <!-- ═══ 附注表：持有待售负债 ═══ -->
    <K6FairValueBlock
      v-if="variant === 'soe'"
      title="附注表·持有待售负债（独立章节 八、43）"
      hint="🔴 国企持有待售负债是**独立附注章节 八、43**（上市侧并入 五、11）→ 同步时单独发一次请求。注：应披露划分为持有待售的非流动负债或处置组的出售原因、方式和时间安排、分部信息，以及与其有关的其他综合收益累计金额。"
      :rows="blocks.liabilities.value"
      :fee-label="feeLabel"
      :is-readonly="isReadonly"
      @add="blocks.addRow('liabilities')"
      @remove="(id: string) => blocks.removeRow('liabilities', id)"
      @update="(id: string, f: string, v: unknown) => blocks.updateField('liabilities', id, f, v)"
    />

    <el-card v-else shadow="never" class="k6-block">
      <template #header>
        <div class="block-head">
          <span class="block-title">附注表·持有待售负债</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" @click="blocks.addRow('liabilities')">
            + 项目
          </el-button>
        </div>
      </template>
      <div class="block-hint">
        【提示：“持有待售负债”反映资产负债表日处置组中与划分为持有待售类别的资产直接相关的负债的
        期末账面价值。】上市侧该表并入 §五、11，列口径是「期末余额 / 上年年末余额」两列
        （与国企 §八、43 的 5 列公允价值口径不同，源模板即如此）。
      </div>
      <el-table :data="blocks.listedLiabilities.value" border size="small" style="width:100%" show-summary :summary-method="listedLiabSummary">
        <el-table-column prop="project" label="项目" min-width="180" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.project"
              size="small"
              placeholder="负债项目"
              @input="(v: string) => blocks.updateField('liabilities', row.id, 'project', v)"
            />
            <span v-else>{{ row.project || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="endAmount" label="期末余额" width="140" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.endAmount" @change="(v?: number) => blocks.updateField('liabilities', row.id, 'endAmount', v ?? 0)" />
            <span v-else>{{ fmt(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priorAmount" label="上年年末余额" width="140" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.priorAmount" @change="(v?: number) => blocks.updateField('liabilities', row.id, 'priorAmount', v ?? 0)" />
            <span v-else>{{ fmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link :disabled="isReadonly" @click="blocks.removeRow('liabilities', row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * K6NoteBlockTables.vue —— 附注要求的 4 张表录入区块（上市 / 国企共用）
 *
 * 改造前两个 K6 披露 Tab **只喂主表**，这 4 张表在底稿里完全没有录入位置
 * （模板补了 columns/guidance 也只有 seed 路径可见，同步路径永远推不出）。
 *
 * 变体差异（源 xlsx 实证，禁抽共享常量）：
 *   · 「预计出售费用」（上市）vs「预计处置费用」（国企）
 *   · 减值准备表首列「上年年末数」（上市）vs「期初数」（国企）
 *   · 持有待售负债：上市 2 列余额口径并入 §五、11；国企 5 列公允价值口径走 §八、43
 *
 * spec: .kiro/specs/k-cycle-disclosure-alignment/ 批 3 Task 13
 */
import { fmtAmount } from '@/utils/formatters'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import K6FairValueBlock from './K6FairValueBlock.vue'
import type { K6DisclosureVariant } from '../../composables/k6NoteSectionMap'
import type { K6NoteBlocks } from '../../composables/useK6NoteBlocks'

const props = defineProps<{
  variant: K6DisclosureVariant
  blocks: K6NoteBlocks
  isReadonly: boolean
}>()

const feeLabel = props.variant === 'listed' ? '预计出售费用' : '预计处置费用'
const priorLabel = props.variant === 'listed' ? '上年年末数' : '期初数'

/** 只读金额展示：委托平台单一真源，保留底稿「0 显示 -」语义 */
function fmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return fmtAmount(v)
}

function impairmentSummary({ columns }: { columns: any[] }): string[] {
  const rows = props.blocks.impairment.value
  const sum = (pick: (r: any) => number): number => rows.reduce((s, r) => s + (Number(pick(r)) || 0), 0)
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (prop && ['priorAmount', 'increase', 'reverse', 'disposal'].includes(prop)) {
      return fmt(sum(r => r[prop]))
    }
    // 期末数是公式列（无 prop）：标签 + 4 个录入列 = 索引 5
    if (idx === 5) return fmt(props.blocks.impairmentTotalEnd.value)
    return ''
  })
}

function listedLiabSummary({ columns }: { columns: any[] }): string[] {
  const rows = props.blocks.listedLiabilities.value
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    const prop = col.property
    if (prop && ['endAmount', 'priorAmount'].includes(prop)) {
      return fmt(rows.reduce((s, r) => s + (Number((r as any)[prop]) || 0), 0))
    }
    return ''
  })
}
</script>

<style scoped>
.k6-note-blocks :deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.k6-block { margin-bottom: 14px; }
.k6-block :deep(.el-card__header) { padding: 10px 16px; }
.block-head { display: flex; align-items: center; justify-content: space-between; }
.block-title { font-size: 14px; font-weight: 600; color: #303133; }
.block-hint {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 8px 12px;
  margin-bottom: 10px; border-radius: 4px; color: #78350f; line-height: 1.6;
}
.formula-cell { text-decoration: underline dashed; cursor: help; color: #409eff; }
:deep(.el-table__footer-wrapper td) { font-weight: 600; }
</style>
