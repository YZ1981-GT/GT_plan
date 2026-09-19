<script setup lang="ts">
const props = defineProps<{ modelValue: boolean; variant?: 'listed' | 'soe' }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
function close(): void { emit('update:modelValue', false) }
const isListed = () => (props.variant || 'listed') === 'listed'
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="isListed() ? 'F1 附注（上市）· 使用手册' : 'F1 附注（国企）· 使用手册'"
    width="760px"
    top="6vh"
    destroy-on-close
    append-to-body
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="guide-body">
      <el-alert
        type="success"
        :closable="false"
        show-icon
        :title="isListed()
          ? '一句话：按账龄披露（5 列 + 小计/减：减值准备/合计）+ 超1年重要预付（含减值准备）+ 前五名；数字与 F1-1 按账龄审定勾稽。'
          : '一句话：按账龄列示（期末/期初各含账面余额金额+比例与减值准备）+ 超1年大额（五列齐备）+ 前五名；口径与 F1-1/F1-5 一致。'"
        class="mb12"
      />

      <section class="guide-section">
        <h3>1. 表结构（源模板口径，不可增删列）</h3>
        <template v-if="isListed()">
          <ul>
            <li>(1) 预付款项按账龄披露：<b>账龄 | 期末余额{金额, 比例%} | 上年年末余额{金额, 比例%}</b>，
              行序 = 各账龄段 → 小计 → 减：减值准备 → 合计。</li>
            <li>(2) 账龄超过1年的重要预付款项：<b>债务人名称 | 账面余额 | 占预付款项合计的比例（%）| 减值准备</b>。
              上市列报格式<b>没有</b>「账龄」「未结算的原因」两列 —— 原因写在下方说明段落。</li>
            <li>(3) 前五名：汇总披露格式（一段话）与分别披露格式（<b>3 列</b>，无减值准备列）择一披露。</li>
          </ul>
        </template>
        <template v-else>
          <ul>
            <li>(1) 预付款项按账龄列示：<b>账龄 | 期末数{账面余额（金额, 比例（%））, 减值准备} | 期初数{同上}</b>，
              表内另有小计与合计行。</li>
            <li>(2) 账龄超过1年的大额预付款项：<b>债权单位 | 债务单位 | 期末余额 | 账龄 | 未结算的原因</b>，五列齐备。</li>
            <li>(3) 按欠款方归集的期末余额前五名的预付款项：
              <b>债务人名称 | 账面余额 | 占预付款项合计的比例（%）| 减值准备</b>。</li>
          </ul>
        </template>
      </section>

      <section class="guide-section">
        <h3>2. 推荐编制顺序</h3>
        <ol>
          <li>先在 F1-2 明细表录入/导入明细并确认账龄枚举口径（3年段 / 5年段 / 自定义）。</li>
          <li>完成 F1-1 审定表「按账龄分类」，本表 (1) 的金额随之自动带入（浅蓝底格为跨 sheet 取数，不可直接改）。</li>
          <li v-if="isListed()">在 (1) 手工录入「减：减值准备」的期末与上年年末两格 —— 合计行自动等于小计减去它。</li>
          <li v-else>在 (1) 逐账龄段录入「减值准备」—— 小计行自动求和，合计行 = 小计 − 减：减值准备。</li>
          <li>(2) 的行由 F1-5 长期挂款检查表带入，也可「+ 添加」手工行；补齐
            <span v-if="isListed()">减值准备，并展开行填「未及时结算的原因」后点「据此生成说明」</span>
            <span v-else>债权单位、账龄与未结算的原因</span>。</li>
          <li>(3) 按期末余额降序自动取前五名；核对附注表述勿与关联方、减值披露冲突。</li>
          <li>点「同步到附注」推送到附注模块（保存时也会自动同步一次）。</li>
        </ol>
      </section>

      <section class="guide-section">
        <h3>3. 勾稽（与附注校验预设 F7-1~F7-14 同口径）</h3>
        <ul>
          <li>各账龄段之和 = 小计行（期末 / 上年年末（期初）各独立校验）。</li>
          <li>合计行 = 小计行 − 减：减值准备行；合计行期末金额 = 资产负债表「预付款项」期末数。</li>
          <li>比例 = 该行金额 ÷ 小计行金额 × 100；减值准备行与合计行不参与比例校验（显示「——」）。</li>
          <li>(2) 合计行余额 ≤ (1) 表 1 年以上各段期末金额之和；(3) 合计行余额 ≤ (1) 小计行期末金额。</li>
          <li v-if="!isListed()">(3) 合计行减值准备 ≤ (1) 减：减值准备行期末金额。</li>
        </ul>
      </section>

      <section class="guide-section">
        <h3>4. 账龄枚举（3年段 / 5年段 / 自定义）</h3>
        <ul>
          <li>口径单一真源在 F1-2 明细表：<b>表级覆盖 &gt; 项目级账龄配置 &gt; 科目默认（预付账款为 3 年段）</b>。</li>
          <li>切到 5 年段后，(1) 自动变成 6 档（1年以内 / 1至2年 / 2至3年 / 3至4年 / 4至5年 / 5年以上），
            <b>不再折入「3年以上」</b>；自定义段直接用自定义标签。</li>
          <li v-if="!isListed()">(2) 的「账龄」下拉选项同步排除首档（1年以内），随生效段联动。</li>
          <li>附注侧行集合由同步整表覆盖，因此附注 TAB 的档数与底稿始终一致。</li>
        </ul>
      </section>

      <section class="guide-section">
        <h3>5. 常见问题</h3>
        <ul>
          <li>附注 TAB 数量没变？<b>附注表格是生成时快照</b> —— 模板改名/加表只对新建项目或重新生成附注生效；
            「🔄 恢复模板结构」只重置当前单张表。</li>
          <li>比例列显示「——」？该行（减值准备 / 合计）按校验预设不参与比例计算，属正常。</li>
          <li>浅蓝底格改不了？那是跨 sheet 取数格，请回 F1-1 / F1-2 / F1-5 修改源头。</li>
        </ul>
      </section>
    </div>
    <template #footer>
      <el-button type="primary" @click="close">知道了</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.guide-body { max-height: min(68vh, 640px); overflow-y: auto; font-size: 13px; line-height: 1.65; color: #303133; }
.mb12 { margin-bottom: 12px; }
.guide-section { margin-bottom: 16px; }
.guide-section h3 { margin: 0 0 8px; font-size: 14px; font-weight: 600; color: #1d39c4; border-left: 3px solid #409eff; padding-left: 8px; }
.guide-section ol, .guide-section ul { margin: 0; padding-left: 1.35em; }
.guide-section li { margin: 4px 0; }
</style>
