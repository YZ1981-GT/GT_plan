<!--
  TaxReturnPage — 纳税申报表（鉴证报告组）。

  表样来自《2025底稿-5.23-5.25补充高新-5.29（解密版）.xlsx》「申报表封面」~「行业数据报送明细表」
  共 38 张表（生成脚本 backend/scripts/gen/gen_tax_workpaper_grids.py → constants/taxReturnGrid.json），
  全部放进同一个电子表格，底部页签切换。
  - 申报表之间的公式（A100000 取 A101010 / A104000 等）保留，由表格计算；
  - 从底稿取数的公式（='2-01'!E8 之类）底稿不在本工作簿，置空，待取数规则接入后再补；
  - 可编辑但**不存盘**（离开页面即丢），导入 / 导出 / 保存保持禁用。
  🔴 本页不发请求、不读写任何业务数据。
-->
<template>
  <div class="gt-tax-return">
    <GtPageHeader title="申报表" :show-back="false">
      <template #prefix>
        <span class="gt-tax-return__badge">{{ SECTION_NO }}</span>
      </template>
      <span class="gt-tax-return__status">表样已就位，取数待接入</span>
    </GtPageHeader>

    <div class="gt-tax-return__toolbar">
      <el-tooltip
        v-for="btn in TOOLBAR"
        :key="btn.key"
        :content="DISABLED_REASON"
        placement="bottom"
      >
        <!-- el-button 禁用后不触发 hover ⇒ tooltip 必须挂在外层 span 上才显示得出来 -->
        <span>
          <el-button size="small" disabled :data-testid="`tax-return-${btn.key}`">{{ btn.label }}</el-button>
        </span>
      </el-tooltip>
    </div>

    <div class="gt-tax-return__card">
      <TaxWorkpaperGrid
        code="tax-return"
        name="企业所得税年度纳税申报表"
        :loader="loadTaxReturnGrid"
        test-id="tax-return-grid"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import TaxWorkpaperGrid from '@/components/workpaper/TaxWorkpaperGrid.vue'
import { loadTaxReturnGrid } from '@/constants/taxWorkpaperGrids'

defineOptions({ name: 'TaxReturnPage' })

/** 章节编号（截图口径「4.1.3」）。集中成常量，改编号只动这一处 */
const SECTION_NO = '4.1.3'

/** 工具栏按钮：全部禁用（不存盘，见文件头），顺序照截图 */
const TOOLBAR = [
  { key: 'import', label: '导入' },
  { key: 'export', label: '导出' },
  { key: 'save', label: '保存' },
] as const

const DISABLED_REASON = '本期暂未开放'
</script>

<style scoped>
.gt-tax-return {
  max-width: 1180px;
}

/* 标题前的章节编号徽标（半透明白底，落在紫色渐变横幅上） */
.gt-tax-return__badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.18);
  color: var(--gt-color-text-inverse, #fff);
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  flex-shrink: 0;
}

/* 横幅右侧状态文字：靠右、弱化 */
.gt-tax-return__status {
  margin-left: auto;
  font-size: var(--gt-font-size-xs);
  opacity: 0.85;
  white-space: nowrap;
}

.gt-tax-return__toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: var(--gt-space-3);
}

/* 表格面板不留内边距，让表格控件贴满 */
.gt-tax-return__card {
  background: var(--gt-color-bg-white, #fff);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: var(--gt-radius-lg, 10px);
  overflow: hidden;
}
</style>
