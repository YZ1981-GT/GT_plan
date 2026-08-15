<template>
  <div v-if="visible" class="wp-four-table-source">
    <div class="src-bar">
      <span class="src-title">四表库取数口径</span>
      <el-tag size="small" type="info">报表行 {{ src.row_code || fallbackRowCode }}</el-tag>
      <!-- 🔴 absent 态不渲染「原值 兜底科目」这类标签：一个码都没取到时说「兜底科目」
           会让审计师以为已按兜底码取了数（实测 I5-1 的 `1911` 全库不存在） -->
      <el-tag v-if="isAbsent" size="small" type="info" effect="plain">
        本项目无此科目
      </el-tag>
      <template v-else>
        <el-tag size="small" :type="grossTagType">
          {{ grossLabel }} {{ resolvedFromLabel(src.resolved_from) }}
        </el-tag>
        <el-tag v-if="showProvision" size="small" :type="provTagType">
          {{ provisionLabel }} {{ resolvedFromLabel(src.provision_resolved_from) }}
        </el-tag>
        <el-tag v-if="showProvision && src.use_provision_name_filter" size="small" type="warning">
          已叠加「{{ provisionFilterLabel }}」名称过滤
        </el-tag>
        <el-tag v-if="absentSlotLabels.length" size="small" type="info">
          本项目无「{{ absentSlotLabels.join('、') }}」科目
        </el-tag>
      </template>
      <el-button v-if="!isAbsent" size="small" link type="primary" @click="expanded = !expanded">
        {{ expanded ? '收起明细' : '展开明细' }}
      </el-button>
    </div>

    <!--
      🔴 「本项目无此科目」必须显式说明，不能整块隐藏（旧行为）。
      三条信息都要给，否则审计师无从判断该不该手工填：
      ① 本该从哪个报表行取（`row_code` 已在上方标签）
      ② 报表公式引用了哪些科目码
      ③ 结论是「本项目没有」而非「取数失败」，且下一步该做什么
    -->
    <el-alert
      v-if="isAbsent"
      type="info"
      show-icon
      :closable="false"
      class="src-alert"
    >
      <template #title>
        本项目科目表中没有{{ grossLabel }}对应科目 —— 未取数（不是余额为 0）
      </template>
      <p class="src-alert-note">
        报表行 <code>{{ src.row_code || fallbackRowCode }}</code>
        <template v-if="src.row_name">（{{ src.row_name }}）</template>
        <template v-if="absentCodesText">
          的公式引用 <code>{{ absentCodesText }}</code>，但本项目科目表里不存在该科目
        </template>
        <template v-else>在本项目科目表里没有可定位的科目</template>。
        属业务事实时无需处理（审定表相关行留空即可，<strong>请勿填 0</strong>）；
        若本项目确有该科目，请检查科目表导入与科目映射。
      </p>
      <p v-if="src.formula" class="src-alert-note">
        报表公式：<code>{{ src.formula }}</code>
      </p>
    </el-alert>

    <!-- 🔴 报表公式与本项目科目表冲突：以科目表为准，但必须让审计师看见 -->
    <el-alert
      v-if="conflictTexts.length"
      type="warning"
      show-icon
      :closable="false"
      class="src-alert"
    >
      <template #title>报表公式引用的科目与本项目科目表不一致（已按科目表取数）</template>
      <ul class="src-alert-list">
        <li v-for="(t, i) in conflictTexts" :key="i">{{ t }}</li>
      </ul>
    </el-alert>

    <!-- 客户仍在用旧准则科目 → 需人工按业务模式与合同现金流量特征（SPPI）判断归属 -->
    <el-alert
      v-if="unmappedTexts.length"
      type="info"
      show-icon
      :closable="false"
      class="src-alert"
    >
      <template #title>本项目存在旧准则同族科目，需人工确认归属后再取数</template>
      <ul class="src-alert-list">
        <li v-for="(t, i) in unmappedTexts" :key="i">{{ t }}</li>
      </ul>
      <p class="src-alert-note">
        新准则下这类科目按业务模式与合同现金流量特征拆分到不同报表项目，属会计判断，
        系统不做自动推断 —— 请在科目映射界面处理。
      </p>
    </el-alert>

    <el-alert
      v-if="chartUnavailable"
      type="warning"
      show-icon
      :closable="false"
      class="src-alert"
      title="本项目科目表未导入或读取失败 —— 当前口径为兜底科目码，取数结果仅供参考"
    />

    <el-collapse-transition>
      <div v-show="expanded" class="src-detail">
        <el-table :data="rows" size="small" :show-header="true" class="src-table">
          <el-table-column prop="role" label="口径" width="150" />
          <el-table-column prop="standard" label="标准科目码（试算平衡表）" min-width="200" />
          <el-table-column prop="original" label="客户原始科目码（余额表）" min-width="220" />
        </el-table>
        <p v-if="formulaText" class="src-formula">
          报表公式：<code>{{ src.formula }}</code>
          <span class="src-sign">（符号：{{ formulaText }}）</span>
        </p>
        <ul v-if="hints.length" class="src-hint">
          <!-- eslint-disable-next-line vue/no-v-html -- 提示文案来自各循环的编译期常量（无用户输入） -->
          <li v-for="(h, i) in hints" :key="i" v-html="h" />
        </ul>
      </div>
    </el-collapse-transition>
  </div>
</template>

<script setup lang="ts">
/**
 * WpFourTableSourcePanel — 四表库取数溯源面板（跨循环共用）
 *
 * 消费各循环 render 下发的 `tb_source_codes`（不得成为 dead output）：
 * 让审计师看到「报表行 → 标准码 → 客户原始码」这条链路究竟落在哪些科目上，
 * 以及是走了报表规则映射还是兜底 —— 审计 UI 必须有逻辑追溯能力。
 *
 * 循环差异全部由 props 声明（原值/备抵中文名、附加科目名、提示文案、兜底报表行），
 * 组件内**不含任何循环专属常量**。首个消费者 = K1（`K1FourTableSourcePanel` 薄壳）、
 * K2（`K2FourTableSourcePanel` 薄壳）。
 *
 * spec: .kiro/specs/k2-four-table-extraction-and-dynamic-rows/ Task 2.1
 */
import { computed, ref } from 'vue'
import {
  hasTbSourceCodes,
  isTbSourceAbsent,
  tbAbsentCodesText,
  tbCodeListText,
  tbConflictTexts,
  tbExtraEntries,
  tbResolvedFromLabel,
  tbResolvedFromTagType,
  tbSemanticSlots,
  tbSignedFormulaText,
  tbUnmappedTexts,
  type TbSourceCodes,
} from '../composables/shared/tbSourceCodes'

const props = withDefaults(
  defineProps<{
    sourceCodes?: TbSourceCodes | null
    /** 原值口径中文名（如「其他应收款原值」/「其他流动资产原值」） */
    grossLabel: string
    /** 备抵口径中文名；不传（或该循环无备抵科目）则不显示备抵行与 tag */
    provisionLabel?: string
    /** 名称过滤 tag 里的科目名（默认取 `grossLabel`） */
    provisionFilterLabel?: string
    /** 附加科目标准码 → 中文名 */
    extraLabels?: Readonly<Record<string, string>>
    /**
     * 除主槽（`gross` / `provision`）外还要在明细表里展示的**语义槽键**。
     *
     * 🔴 多槽循环必需：`SemanticAccountResult.as_dict()` 的扁平投影只由
     * `gross` / `provision` 两个槽派生，而 H3 的四槽是
     * `gross` / `accum_dep` / `accum_amort` / `impairment`（**没有** `provision` 槽）
     * ⇒ 不声明这三个槽键，累计折旧/累计摊销/减值准备的来源科目码在面板里
     * 完全看不到（审计 UI 失去逻辑追溯能力）。
     *
     * 默认 `[]` ⇒ 既有单槽消费者（K1/K2/F1/E1…）逐字节零回归。
     */
    extraSlotKeys?: readonly string[]
    /** 口径说明（允许内嵌 `<code>`/`<strong>`，均为编译期常量） */
    hints?: readonly string[]
    /** 溯源未下发 row_code 时的展示兜底 */
    fallbackRowCode?: string
  }>(),
  {
    sourceCodes: null,
    provisionLabel: '',
    provisionFilterLabel: '',
    extraLabels: () => ({}),
    extraSlotKeys: () => [],
    hints: () => [],
    fallbackRowCode: '',
  },
)

const expanded = ref(false)

const src = computed<TbSourceCodes>(() => props.sourceCodes || {})

/** 声明的附加槽里是否有真实命中（多槽循环下主槽可能为空而备抵槽有值） */
const hasExtraSlotCodes = computed(() =>
  (props.extraSlotKeys || []).some((k) => {
    const slot = src.value.slots?.[k]
    return !!(slot && ((slot.codes?.length ?? 0) || (slot.standard_codes?.length ?? 0)))
  }),
)

/**
 * 「本项目无此科目」态 —— 后端算过但该项目科目表里确实没有对应科目。
 *
 * 🔴 旧实现只有 `hasTbSourceCodes || hasExtraSlotCodes` 两项，
 *    absent 态四个码列表全空 ⇒ 整块 `v-if` 隐藏 ⇒ 审计师看到**一片空白**，
 *    既不知道该从哪个报表行取数、也不知道为何没取到（I5-1「其他非流动资产」
 *    的 `1911` 在本项目科目表里不存在，实测面板整块未渲染）。
 *    这与平台口径「本项目无此科目须显式说明、不得静默」相悖。
 */
const isAbsent = computed(() => isTbSourceAbsent(props.sourceCodes))
const absentCodesText = computed(() => tbAbsentCodesText(props.sourceCodes))

const visible = computed(
  () => hasTbSourceCodes(props.sourceCodes) || hasExtraSlotCodes.value || isAbsent.value,
)

/** 无备抵科目的循环（如 K2 其他流动资产）不显示备抵行 */
const showProvision = computed(() => !!props.provisionLabel)
const provisionFilterLabel = computed(() => props.provisionFilterLabel || props.grossLabel)

const grossTagType = computed(() => tbResolvedFromTagType(src.value.resolved_from))
const provTagType = computed(() => tbResolvedFromTagType(src.value.provision_resolved_from))
const formulaText = computed(() => tbSignedFormulaText(src.value))
const hints = computed(() => props.hints || [])

const resolvedFromLabel = tbResolvedFromLabel

// ── 语义解析新增的审计追溯信号（`semantic_account_resolver` 起可用）──────────
// 旧的报表映射路径（`report_line_accounts`）不发这些字段 → 全部为空、界面无变化，
// 故本节改动对 K1/K2/F1 等既有消费者是**零回归**的纯增量。

/** 报表公式与本项目科目表冲突（实证 `report_config` 有 4 行错码） */
const conflictTexts = computed(() => tbConflictTexts(src.value))

/** 客户仍在用的旧准则同族科目（需人工按 SPPI 判断归属） */
const unmappedTexts = computed(() => tbUnmappedTexts(src.value))

/**
 * 本项目科目表不可用。
 *
 * 🔴 只在**显式为 false** 时告警 —— 旧路径不发该字段（`undefined`），
 * 不能把「字段缺失」当成「科目表坏了」。
 */
const chartUnavailable = computed(() => src.value.chart_available === false)

/**
 * 本项目确实没有的槽（`found === false`）。
 *
 * 这是**正确行为**（宁缺勿造），用 info tag 提示而非报错 —— 让审计师知道
 * 「这里是空的，因为本项目没有这个科目」，而不是误以为余额为 0 或取数失败。
 */
const absentSlotLabels = computed(() =>
  tbSemanticSlots(src.value)
    .filter((s) => s.found === false)
    .map((s) => s.label || s.key),
)

interface SrcRow {
  role: string
  standard: string
  original: string
}

const rows = computed<SrcRow[]>(() => {
  const out: SrcRow[] = [
    {
      role: props.grossLabel,
      standard: tbCodeListText(src.value.gross_standard),
      original: tbCodeListText(src.value.gross),
    },
  ]
  if (showProvision.value) {
    out.push({
      role: props.provisionLabel,
      standard: tbCodeListText(src.value.provision_standard),
      original: tbCodeListText(src.value.provision),
    })
  }
  for (const e of tbExtraEntries(src.value, props.extraLabels)) {
    out.push({
      role: e.label,
      standard: e.standard,
      original: tbCodeListText(e.originals),
    })
  }
  // 多槽循环的其余语义槽（H3 的累计折旧 / 累计摊销 / 减值准备）
  // 解析来源写进「口径」列而不新增表列 —— 新增列会改动全部既有消费者的表格布局
  for (const key of props.extraSlotKeys || []) {
    const slot = src.value.slots?.[key]
    if (!slot) continue
    out.push({
      role: `${slot.label || key}（${resolvedFromLabel(slot.resolved_from)}）`,
      standard: tbCodeListText(slot.standard_codes),
      original: tbCodeListText(slot.codes),
    })
  }
  return out
})
</script>

<style scoped>
.wp-four-table-source {
  margin: 8px 0;
  font-size: 13px;
}

.src-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 6px 10px;
  background: #f5f7fa;
  border-left: 3px solid var(--el-color-primary);
  border-radius: 2px;
}

.src-title {
  font-weight: 600;
  color: #303133;
}

.src-detail {
  padding: 8px 10px 4px;
  background: #fafcff;
  border: 1px solid #ebeef5;
  border-top: none;
}

.src-table {
  font-size: 13px;
}

.src-formula {
  margin: 8px 0 4px;
  color: #606266;
}

.src-formula code {
  background: #f0f2f5;
  padding: 1px 4px;
  border-radius: 2px;
}

.src-sign {
  margin-left: 6px;
  color: #909399;
}

.src-hint {
  margin: 4px 0 0;
  padding-left: 18px;
  color: #8a6d3b;
  background: #fffbe6;
  border-left: 3px solid #faad14;
  padding: 6px 6px 6px 22px;
  line-height: 1.7;
}

.src-hint :deep(code) {
  background: #fff3cd;
  padding: 0 3px;
}

.src-alert {
  margin-top: 6px;
}

.src-alert-list {
  margin: 4px 0 0;
  padding-left: 18px;
  line-height: 1.7;
}

.src-alert-note {
  margin: 6px 0 0;
  color: #606266;
  line-height: 1.6;
}
</style>
