<script setup lang="ts">
/**
 * B23ControlPointDialog — B23 控制点引导式录入弹窗
 *
 * Spec: .kiro/specs/b23-business-control-rework/（增强：点选式录入 + 实时逻辑联动）
 *
 * 将 21 列宽表矩阵的横向填格改为分组卡片式引导录入：
 *   ① 控制识别 ② WCGW与认定 ③ 控制属性 ④ 设计评价 ⑤ 测试决策
 * 右侧实时联动面板：设计无效→缺陷提示；关键控制∧穿行按设计执行→建议控制测试。
 * 保存时全字段一次性批量提交（父组件 setControlPointFields），避免逐字段多次 PUT。
 */
import { ref, computed, watch } from 'vue'
import {
  ASSERTION_OPTIONS, FREQUENCY_OPTIONS, PREVENT_DETECT_OPTIONS, CTRL_TYPE_L1_OPTIONS, YES_NO_OPTIONS,
  suggestControlTest, deficiencyHints,
  type B23ControlPoint, type B23WalkthroughTest,
} from './composables/useB23ProcessControl'

interface Props {
  modelValue: boolean
  cycleName: string
  controlPoint: B23ControlPoint | null
  walkthrough?: B23WalkthroughTest | null
  wcgwOptions: string[]
  readonly?: boolean
}
const props = withDefaults(defineProps<Props>(), { walkthrough: null, readonly: false })
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'save', patch: Partial<B23ControlPoint>): void
}>()

const CTRL_TYPE_L2_HINTS = ['有权人员批准', '安全访问控制', '复核其他控制的执行情况', '账实核对', '系统自动校验']

// 本地表单克隆（不直接改 prop）
const form = ref<B23ControlPoint | null>(null)
watch(
  () => [props.modelValue, props.controlPoint] as const,
  ([open]) => { if (open && props.controlPoint) form.value = { ...props.controlPoint, assertion: [...props.controlPoint.assertion] } },
  { immediate: true },
)

function set<K extends keyof B23ControlPoint>(field: K, v: B23ControlPoint[K]) {
  if (form.value) (form.value as any)[field] = v
}

// ─── 实时逻辑联动 ──────────────────────────────────────────────────────────
const designInvalid = computed(() => form.value?.designEffective === '否')
const suggestTest = computed(() =>
  form.value ? suggestControlTest(form.value, props.walkthrough || undefined) : false,
)
const isKeyNotTested = computed(() => form.value?.isKeyControl === '是' && form.value?.doControlTest !== '是')
const defHints = computed(() =>
  form.value ? deficiencyHints(form.value, props.walkthrough || undefined) : [],
)
const missingAssertion = computed(() => form.value?.isKeyControl === '是' && (form.value?.assertion.length ?? 0) === 0)

function onClose() { emit('update:modelValue', false) }
function onSave() {
  if (!form.value) return
  emit('save', { ...form.value })
  emit('update:modelValue', false)
}
</script>

<template>
  <el-dialog :model-value="modelValue" :title="`${cycleName} · 控制点录入`" width="920px" top="5vh"
    @update:model-value="onClose" append-to-body>
    <div v-if="form" class="b23-cp-dialog">
      <div class="cp-main">
        <!-- ① 控制识别 -->
        <el-card shadow="never" class="grp">
          <template #header><span class="grp-t">① 控制识别</span></template>
          <div class="grid2">
            <div class="fld"><label>子流程</label><el-input v-model="form.subProcess" :disabled="readonly" size="small" /></div>
            <div class="fld"><label>控制编号</label><el-input v-model="form.ctrlNo" :disabled="readonly" size="small" /></div>
          </div>
          <div class="fld"><label>控制名称</label><el-input v-model="form.ctrlName" :disabled="readonly" size="small" /></div>
          <div class="fld"><label>详细控制描述</label><el-input v-model="form.ctrlDesc" :disabled="readonly" type="textarea" :autosize="{ minRows: 2 }" /></div>
          <div class="fld"><label>受影响的交易/账户/披露</label><el-input v-model="form.affectedItems" :disabled="readonly" size="small" /></div>
        </el-card>

        <!-- ② WCGW 与认定 -->
        <el-card shadow="never" class="grp">
          <template #header><span class="grp-t">② WCGW 与认定</span></template>
          <div class="grid2">
            <div class="fld"><label>WCGW 引用（容易出错领域）</label>
              <el-select v-model="form.wcgwRef" :disabled="readonly" clearable filterable allow-create size="small" placeholder="引用 WCGW 识别表编号" style="width:100%">
                <el-option v-for="w in wcgwOptions" :key="w" :label="w" :value="w" />
              </el-select>
            </div>
            <div class="fld"><label>认定<span v-if="missingAssertion" class="warn-inline">（关键控制建议至少 1 项认定）</span></label>
              <el-select v-model="form.assertion" :disabled="readonly" multiple collapse-tags size="small" placeholder="多选" style="width:100%">
                <el-option v-for="o in ASSERTION_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
            </div>
          </div>
          <div class="fld"><label>WCGW 详细记录</label><el-input v-model="form.wcgwDetail" :disabled="readonly" type="textarea" :autosize="{ minRows: 2 }" /></div>
          <div class="fld"><label>控制属性</label><el-input v-model="form.ctrlAttr" :disabled="readonly" size="small" placeholder="如：审批/复核/账实核对" /></div>
        </el-card>

        <!-- ③ 控制属性 -->
        <el-card shadow="never" class="grp">
          <template #header><span class="grp-t">③ 控制属性登记</span></template>
          <div class="grid3">
            <div class="fld"><label>控制频率</label>
              <el-select v-model="form.frequency" :disabled="readonly" clearable size="small" style="width:100%">
                <el-option v-for="o in FREQUENCY_OPTIONS" :key="o" :label="o" :value="o" /></el-select></div>
            <div class="fld"><label>预防性/检查性</label>
              <el-select v-model="form.preventDetect" :disabled="readonly" clearable size="small" style="width:100%">
                <el-option v-for="o in PREVENT_DETECT_OPTIONS" :key="o" :label="o" :value="o" /></el-select></div>
            <div class="fld"><label>控制类型（一级）</label>
              <el-select v-model="form.ctrlTypeL1" :disabled="readonly" clearable size="small" style="width:100%">
                <el-option v-for="o in CTRL_TYPE_L1_OPTIONS" :key="o" :label="o" :value="o" /></el-select></div>
            <div class="fld"><label>控制类型（二级）</label>
              <el-select v-model="form.ctrlTypeL2" :disabled="readonly" clearable filterable allow-create size="small" style="width:100%">
                <el-option v-for="o in CTRL_TYPE_L2_HINTS" :key="o" :label="o" :value="o" /></el-select></div>
            <div class="fld"><label>IT 应用名称</label><el-input v-model="form.itApp" :disabled="readonly" size="small" /></div>
            <div class="fld"><label>执行人</label><el-input v-model="form.executor" :disabled="readonly" size="small" /></div>
            <div class="fld"><label>执行人名称/服务机构</label><el-input v-model="form.executorOrg" :disabled="readonly" size="small" /></div>
            <div class="fld"><label>是否有文件记录</label>
              <el-select v-model="form.hasDoc" :disabled="readonly" clearable size="small" style="width:100%">
                <el-option v-for="o in YES_NO_OPTIONS" :key="o" :label="o" :value="o" /></el-select></div>
          </div>
        </el-card>

        <!-- ④ 设计评价 -->
        <el-card shadow="never" class="grp">
          <template #header><span class="grp-t">④ 控制设计有效性评价</span></template>
          <div class="fld"><label>控制设计是否有效</label>
            <el-radio-group v-model="form.designEffective" :disabled="readonly">
              <el-radio v-for="o in YES_NO_OPTIONS" :key="o" :value="o">{{ o }}</el-radio>
            </el-radio-group>
          </div>
          <el-alert v-if="designInvalid" type="error" :closable="false" show-icon
            title="控制设计无效——需在缺陷汇总识别缺陷并评估对实质性程序范围的影响" />
        </el-card>

        <!-- ⑤ 测试决策 -->
        <el-card shadow="never" class="grp">
          <template #header><span class="grp-t">⑤ 关键控制与测试决策</span></template>
          <div class="grid2">
            <div class="fld"><label>是否为关键控制点</label>
              <el-radio-group v-model="form.isKeyControl" :disabled="readonly">
                <el-radio v-for="o in YES_NO_OPTIONS" :key="o" :value="o">{{ o }}</el-radio></el-radio-group></div>
            <div class="fld"><label>是否执行控制测试</label>
              <el-radio-group v-model="form.doControlTest" :disabled="readonly">
                <el-radio v-for="o in YES_NO_OPTIONS" :key="o" :value="o">{{ o }}</el-radio></el-radio-group></div>
          </div>
        </el-card>
      </div>

      <!-- 实时逻辑联动面板 -->
      <aside class="cp-side">
        <div class="side-t">逻辑联动提示</div>
        <el-alert v-if="suggestTest" type="success" :closable="false" show-icon
          title="关键控制 ∧ 穿行按设计执行 → 通常应执行控制测试（关联 C 类底稿）" />
        <el-alert v-if="isKeyNotTested" type="warning" :closable="false" show-icon
          title="该关键控制点尚未安排控制测试，请确认是否仅依赖实质性程序" />
        <el-alert v-for="(h, i) in defHints" :key="i" type="error" :closable="false" show-icon :title="h" />
        <el-alert v-if="!suggestTest && !isKeyNotTested && !defHints.length" type="info" :closable="false"
          title="按 WCGW → 关键控制 → 穿行验设计 → 控制测试验运行 顺序录入，本面板会实时提示。" />
      </aside>
    </div>

    <template #footer>
      <el-button @click="onClose">取消</el-button>
      <el-button type="primary" :disabled="readonly" @click="onSave">保存控制点</el-button>
    </template>
  </el-dialog>
</template>

<style scoped lang="scss">
.b23-cp-dialog {
  display: flex; gap: 12px; font-size: 13px;
  .cp-main { flex: 1; min-width: 0; }
  .cp-side { width: 240px; flex-shrink: 0;
    .side-t { font-weight: 600; color: #531dab; margin-bottom: 8px; }
    .el-alert { margin-bottom: 8px; } }
  .grp { margin-bottom: 10px;
    :deep(.el-card__header) { padding: 6px 12px; border-left: 3px solid #722ed1; background: linear-gradient(90deg,#f9f0ff,#fff); }
    :deep(.el-card__body) { padding: 10px 12px; }
    .grp-t { font-weight: 600; color: #333; } }
  .fld { margin-bottom: 8px; label { display: block; font-size: 12px; color: #666; margin-bottom: 3px; } }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .warn-inline { color: #faad14; font-size: 11px; }
}
</style>
