<template>
<div class="f1-four-table-source">
  <div class="src-bar">
    <span class="src-title">四表库取数溯源</span>
    <el-tag size="small" type="info">报表行 {{ source.rowCode }}</el-tag>
    <el-tag size="small" :type="grossTag.type">原值：{{ grossTag.text }}</el-tag>
    <el-tag size="small" :type="provisionTag.type">备抵：{{ provisionTag.text }}</el-tag>
    <el-tag v-if="source.useProvisionNameFilter" size="small" type="warning">
      备抵按「预付」过滤
    </el-tag>
    <el-tag v-if="divergence.hasDivergence" size="small" type="danger">
      两口径差异 {{ fmtAmount(divergence.diff) }}
    </el-tag>
    <el-button size="small" text type="primary" @click="expanded = !expanded">
      {{ expanded ? '收起明细' : '展开明细' }}
    </el-button>
  </div>

  <div v-if="expanded" class="src-detail">
    <el-descriptions :column="1" size="small" border>
      <el-descriptions-item label="报表映射公式">
        <code v-if="source.formula">{{ source.formula }}</code>
        <span v-else class="muted">未取到（已回退兜底科目 1123）</span>
      </el-descriptions-item>
      <el-descriptions-item label="原值科目（标准码 → 原始码）">
        <span class="code-list">{{ joinCodes(source.grossStandard) }}</span>
        <span class="arrow">→</span>
        <span class="code-list">{{ joinCodes(source.gross) }}</span>
        <el-tag size="small" :type="grossTag.type" class="inline-tag">{{ grossTag.text }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="备抵科目（坏账准备-预付账款）">
        <span class="code-list">{{ joinCodes(source.provisionStandard) }}</span>
        <span class="arrow">→</span>
        <span class="code-list">{{ joinCodes(source.provision) }}</span>
        <el-tag size="small" :type="provisionTag.type" class="inline-tag">
          {{ provisionTag.text }}
        </el-tag>
        <span v-if="source.useProvisionNameFilter" class="muted filter-hint">
          反解退化为宽前缀，已叠加科目名含「预付」过滤（防混入应收票据/应收账款/其他应收款的坏账）
        </span>
      </el-descriptions-item>
      <el-descriptions-item v-if="crossCycle" label="F1-4 跨循环锚点">
        存货 {{ crossCycle.inventory.rowCode }}：{{ joinCodes(crossCycle.inventory.codes) }}；
        应付账款 {{ crossCycle.payable.rowCode }}：{{ joinCodes(crossCycle.payable.codes) }}
      </el-descriptions-item>
      <el-descriptions-item label="试算平衡表数 / 科目余额表叶子合计">
        <span>{{ fmtAmount(trialBalanceAmount) }}</span>
        <span class="arrow">vs</span>
        <span>{{ fmtAmount(leafAmount) }}</span>
        <el-tag v-if="divergence.hasDivergence" size="small" type="danger" class="inline-tag">
          差异 {{ fmtAmount(divergence.diff) }}
        </el-tag>
        <el-tag v-else size="small" type="success" class="inline-tag">两口径一致</el-tag>
        <div v-if="divergence.hasDivergence" class="muted filter-hint">
          试算平衡表是重算产物，与科目余额表叶子合计不等时须核实数据集范围
          （历史无数据集标识的行可能被重复计入）。
        </div>
      </el-descriptions-item>
    </el-descriptions>
  </div>
</div>
</template>

<script setup lang="ts">
/**
 * F1FourTableSourcePanel — F1 四表库取数溯源面板
 *
 * 消费 render 下发的 `project_context.tb_source_codes` / `tb_cross_cycle_codes`
 * （改造前这两个字段前端 0 消费 = dead output）。
 *
 * spec: .kiro/specs/f1-four-table-extraction-and-disclosure-alignment/ R1.7, R4.3
 */
import { computed, ref } from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import {
  describeResolvedFrom,
  normalizeF1CrossCycleSources,
  normalizeF1TbSource,
  tbAmountDivergence,
} from '../composables/f1FourTableSource'

const props = withDefaults(defineProps<{
  /** render 下发的 project_context.tb_source_codes（新 dict / 旧 string[] 均可） */
  tbSourceCodes?: unknown
  /** render 下发的 project_context.tb_cross_cycle_codes（可选） */
  tbCrossCycleCodes?: unknown
  /** 试算平衡表口径金额（project_context.prepaid_tb_amount） */
  trialBalanceAmount?: number
  /** 科目余额表叶子合计（project_context.prepaid_tb_leaf_amount） */
  leafAmount?: number
  /** 是否显示 F1-4 跨循环锚点行（披露 Tab 不需要） */
  showCrossCycle?: boolean
}>(), {
  trialBalanceAmount: 0,
  leafAmount: 0,
  showCrossCycle: true,
})

const displayPrefs = useDisplayPrefsStore()
const expanded = ref(false)

const source = computed(() => normalizeF1TbSource(props.tbSourceCodes))
const crossCycle = computed(() =>
  props.showCrossCycle ? normalizeF1CrossCycleSources(props.tbCrossCycleCodes) : null,
)
const grossTag = computed(() => describeResolvedFrom(source.value.resolvedFrom))
const provisionTag = computed(() => describeResolvedFrom(source.value.provisionResolvedFrom))
const divergence = computed(() =>
  tbAmountDivergence(props.trialBalanceAmount, props.leafAmount),
)

function joinCodes(codes: string[]): string {
  return codes.length ? codes.join('、') : '—'
}

function fmtAmount(v: number | null | undefined): string {
  return displayPrefs.fmtAmount(v)
}
</script>

<style scoped>
.f1-four-table-source { margin-bottom: 10px; }
.src-bar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 6px 12px; background: #f5f7fa; border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
}
.src-title { font-weight: 600; color: #303133; }
.src-detail { margin-top: 6px; }
.src-detail :deep(.el-descriptions__label) { width: 200px; }
.code-list { font-family: var(--el-font-family-monospace, monospace); }
.arrow { margin: 0 6px; color: #909399; }
.inline-tag { margin-left: 8px; }
.muted { color: #909399; }
.filter-hint { display: block; margin-top: 4px; font-size: 12px; line-height: 1.5; }
code { background: #f0f2f5; padding: 1px 4px; border-radius: 2px; }
</style>
