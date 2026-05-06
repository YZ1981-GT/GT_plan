<template>
  <el-dialog
    v-model="visible"
    :title="`编辑公式 — ${row?.row_code} ${row?.row_name}`"
    width="95%"
    top="2vh"
    append-to-body
    destroy-on-close
    :close-on-click-modal="false"
  >
    <div class="gt-fe-container">
      <!-- 公式列表 -->
      <div class="gt-fe-formulas">
        <div class="gt-fe-section-title">
          <span>公式配置</span>
          <div style="display: flex; gap: 6px;">
            <el-button size="small" @click="copyFormula">📋 复制{{ checkedCount ? `(${checkedCount})` : '' }}</el-button>
            <el-button size="small" @click="addFormula">+ 添加公式</el-button>
          </div>
        </div>
        <div v-for="(f, idx) in formulas" :key="idx" class="gt-fe-formula-item"
          :class="{ 'gt-fe-formula-active': activeFormulaIdx === idx }"
          @click="activeFormulaIdx = idx"
          draggable="true"
          @dragstart="onDragStart(idx)"
          @dragover.prevent
          @drop="onDrop(idx)">
          <div class="gt-fe-formula-header">
            <el-checkbox v-model="f._checked" size="small" @click.stop style="margin-right: 2px;" />
            <span class="gt-fe-drag-handle" title="拖拽排序">⠿</span>
            <span style="font-size: 11px; color: #bbb; min-width: 20px;">{{ idx + 1 }}.</span>
            <el-select v-model="f.category" size="small" style="width: 120px;">
              <el-option label="⚡ 自动运算" value="auto_calc" />
              <el-option label="🔍 逻辑审核" value="logic_check" />
              <el-option label="💡 合理性" value="reasonability" />
            </el-select>
            <el-input v-model="f.description" size="small" placeholder="公式说明（如：流动资产合计）" style="flex: 1;" />
            <el-button size="small" link style="color: #999;" @click="removeFormula(idx)" v-if="formulas.length > 1">删除</el-button>
          </div>
          <!-- 目标定位 -->
          <div class="gt-fe-target-bar">
            <span style="font-size: 11px; color: #999; white-space: nowrap;">📍 写入目标：</span>
            <el-button size="small" @click="openTargetPicker(idx)">🎯 点击定位</el-button>
            <el-input
              v-model="f.target_cell"
              size="small"
              :placeholder="row?.row_code ? `${row.row_code} ${row.row_name}` : '目标地址（如 BS-002·期末）'"
              style="flex: 1; margin-left: 4px;"
              clearable
            />
          </div>
          <div class="gt-fe-formula-input">
            <el-input
              v-model="f.expression"
              type="textarea"
              :rows="1"
              :autosize="{ minRows: 2, maxRows: 6 }"
              placeholder="输入公式，如 TB('1001','期末余额') 或 ROW('BS-001')+ROW('BS-002')"
              resize="none"
              :input-style="{ fontSize: '11px', fontFamily: 'Cascadia Code, Fira Code, Consolas, monospace', lineHeight: '1.5' }"
            />
            <div class="gt-fe-quick-btns">
              <span class="gt-fe-btn-label">取数:</span>
              <el-button size="small" title="从试算表取某科目金额，如 TB('1001','期末余额')" @click="insertRef(idx, 'TB')">TB</el-button>
              <el-button size="small" title="引用同报表某一行金额，如 ROW('BS-002')" @click="insertRef(idx, 'ROW')">ROW</el-button>
              <el-button size="small" title="连续行范围求和，如 SUM_ROW('BS-002','BS-010')" @click="insertRef(idx, 'SUM_ROW')">SUM_ROW</el-button>
              <el-button size="small" title="按科目前缀汇总，如 SUM_TB('10','审定数') 汇总10开头科目" @click="insertRef(idx, 'SUM_TB')">SUM_TB</el-button>
              <el-button size="small" title="引用附注表格数据，如 NOTE('货币资金','合计','期末')" @click="insertRef(idx, 'NOTE')">NOTE</el-button>
              <el-button size="small" title="引用底稿审定表数据，如 WP('E1-1','审定数')" @click="insertRef(idx, 'WP')">WP</el-button>
              <el-button size="small" title="跨表引用其他报表行金额，如 REPORT('BS-002','期末')" @click="insertRef(idx, 'REPORT')">REPORT</el-button>
              <el-button size="small" title="从辅助余额表按维度取数，如 AUX('1122','客户A','期末')" @click="insertRef(idx, 'AUX')">AUX</el-button>
              <el-button size="small" title="取上年同期数据，如 PREV('BS-002','期末') 取上年期末" @click="insertRef(idx, 'PREV')">PREV</el-button>
            </div>
            <div class="gt-fe-quick-btns">
              <span class="gt-fe-btn-label">比较:</span>
              <el-button size="small" title="等于：左侧值应等于右侧值" @click="insertRef(idx, 'EQ')">=</el-button>
              <el-button size="small" title="不等于：左侧值不应等于右侧值" @click="insertRef(idx, 'NEQ')">≠</el-button>
              <el-button size="small" title="大于" @click="insertRef(idx, 'GT')">&gt;</el-button>
              <el-button size="small" title="大于等于" @click="insertRef(idx, 'GTE')">≥</el-button>
              <el-button size="small" title="小于" @click="insertRef(idx, 'LT')">&lt;</el-button>
              <el-button size="small" title="小于等于" @click="insertRef(idx, 'LTE')">≤</el-button>
            </div>
            <div class="gt-fe-quick-btns">
              <span class="gt-fe-btn-label">函数:</span>
              <el-button size="small" title="条件判断：IF(条件, 真值, 假值)，条件成立返回真值否则假值" @click="insertRef(idx, 'IF')">IF</el-button>
              <el-button size="small" title="取绝对值：ABS(值)，用于差异金额取绝对值比较" @click="insertRef(idx, 'ABS')">ABS</el-button>
              <el-button size="small" title="四舍五入：ROUND(值, 小数位)，允许尾差场景" @click="insertRef(idx, 'ROUND')">ROUND</el-button>
              <el-button size="small" title="最大值：MAX(值1, 值2)，取两个值中较大的" @click="insertRef(idx, 'MAX')">MAX</el-button>
              <el-button size="small" title="最小值：MIN(值1, 值2)，取两个值中较小的" @click="insertRef(idx, 'MIN')">MIN</el-button>
            </div>
            <div class="gt-fe-quick-btns">
              <span class="gt-fe-btn-label">审计:</span>
              <el-button size="small" title="非空检查：该行不能为空值" @click="insertRef(idx, 'NOT_EMPTY')">非空</el-button>
              <el-button size="small" title="非零检查：该行金额不能为零" @click="insertRef(idx, 'NOT_ZERO')">非零</el-button>
              <el-button size="small" title="变动率检查：CHANGE_RATE('行次') < 阈值，超过阈值需说明" @click="insertRef(idx, 'CHANGE_RATE')">变动率</el-button>
              <el-button size="small" title="区间判断：BETWEEN(值, 下限, 上限)，值应在区间内" @click="insertRef(idx, 'BETWEEN')">区间</el-button>
              <el-button size="small" title="变动超阈值必须填写原因：REQUIRE_REASON('行次', 0.3)" @click="insertRef(idx, 'REQUIRE_REASON')">必填原因</el-button>
              <el-button size="small" title="差异容差：TOLERANCE(值1, 值2, 容差)，差异在容差内视为一致（如允许1元尾差）" @click="insertRef(idx, 'TOLERANCE')">容差</el-button>
              <el-button size="small" title="同比增长率：YOY_RATE('行次')，(本期-上期)/上期" @click="insertRef(idx, 'YOY_RATE')">同比</el-button>
              <el-button size="small" title="占比计算：RATIO(分子行, 分母行)，计算某项占总额比例" @click="insertRef(idx, 'RATIO')">占比</el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 中栏：数据源一览 -->
      <div class="gt-fe-sources">
        <div class="gt-fe-section-title">📋 数据源一览</div>
        <div class="gt-fe-ref-panel">
          <div class="gt-fe-ref-group">
            <div class="gt-fe-ref-group-title" @click="toggleRefGroup('report')">
              <span>{{ refGroupOpen.report ? '▼' : '▶' }} 📊 报表</span>
              <span class="gt-fe-ref-count">6</span>
            </div>
            <div v-show="refGroupOpen.report" class="gt-fe-ref-list">
              <div class="gt-fe-ref-row" @click="jumpToSource('report', 'balance_sheet')"><span class="gt-fe-ref-code">BS</span>资产负债表</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('report', 'income_statement')"><span class="gt-fe-ref-code">IS</span>利润表</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('report', 'cash_flow_statement')"><span class="gt-fe-ref-code">CFS</span>现金流量表</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('report', 'equity_statement')"><span class="gt-fe-ref-code">EQ</span>权益变动表</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('report', 'cash_flow_supplement')"><span class="gt-fe-ref-code">CFSS</span>现金流附表</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('report', 'impairment_provision')"><span class="gt-fe-ref-code">IMP</span>资产减值准备表</div>
            </div>
          </div>
          <div class="gt-fe-ref-group">
            <div class="gt-fe-ref-group-title" @click="toggleRefGroup('note')">
              <span>{{ refGroupOpen.note ? '▼' : '▶' }} 📝 附注</span>
              <span class="gt-fe-ref-count">22</span>
            </div>
            <div v-show="refGroupOpen.note" class="gt-fe-ref-list">
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '货币资金')"><span class="gt-fe-ref-code">E</span>货币资金</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '应收票据')"><span class="gt-fe-ref-code">D</span>应收票据</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '应收账款')"><span class="gt-fe-ref-code">D</span>应收账款</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '预付款项')"><span class="gt-fe-ref-code">F</span>预付款项</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '其他应收款')"><span class="gt-fe-ref-code">D</span>其他应收款</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '存货')"><span class="gt-fe-ref-code">G</span>存货</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '合同资产')"><span class="gt-fe-ref-code">D</span>合同资产</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '固定资产')"><span class="gt-fe-ref-code">H</span>固定资产</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '在建工程')"><span class="gt-fe-ref-code">H</span>在建工程</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '无形资产')"><span class="gt-fe-ref-code">I</span>无形资产</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '长期股权投资')"><span class="gt-fe-ref-code">J</span>长期股权投资</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '短期借款')"><span class="gt-fe-ref-code">K</span>短期借款</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '应付账款')"><span class="gt-fe-ref-code">F</span>应付账款</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '合同负债')"><span class="gt-fe-ref-code">D</span>合同负债</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '应付职工薪酬')"><span class="gt-fe-ref-code">L</span>应付职工薪酬</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '应交税费')"><span class="gt-fe-ref-code">N</span>应交税费</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '长期借款')"><span class="gt-fe-ref-code">K</span>长期借款</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '营业收入')"><span class="gt-fe-ref-code">D</span>营业收入</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '营业成本')"><span class="gt-fe-ref-code">D</span>营业成本</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '管理费用')"><span class="gt-fe-ref-code">N</span>管理费用</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '财务费用')"><span class="gt-fe-ref-code">N</span>财务费用</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('note', '所得税费用')"><span class="gt-fe-ref-code">N</span>所得税费用</div>
            </div>
          </div>
          <div class="gt-fe-ref-group">
            <div class="gt-fe-ref-group-title" @click="toggleRefGroup('wp')">
              <span>{{ refGroupOpen.wp ? '▼' : '▶' }} 📋 底稿</span>
              <span class="gt-fe-ref-count">14</span>
            </div>
            <div v-show="refGroupOpen.wp" class="gt-fe-ref-list">
              <div class="gt-fe-ref-row" @click="jumpToSource('wp', 'E1')"><span class="gt-fe-ref-code">E1</span>货币资金（E1-1审定/E1-2现金/E1-3银行）</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('wp', 'D2')"><span class="gt-fe-ref-code">D2</span>应收账款（D2-1审定/D2-2明细/D2-3坏账）</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('wp', 'D1')"><span class="gt-fe-ref-code">D1</span>营业收入（D1-1审定/D1-2明细）</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('wp', 'F1')"><span class="gt-fe-ref-code">F1</span>应付账款（F1-1审定）</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('wp', 'F2')"><span class="gt-fe-ref-code">F2</span>预付款项（F2-1审定）</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('wp', 'G1')"><span class="gt-fe-ref-code">G1</span>存货（G1-1审定）</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('wp', 'H1')"><span class="gt-fe-ref-code">H1</span>固定资产（H1-1审定/H1-12折旧）</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('wp', 'H2')"><span class="gt-fe-ref-code">H2</span>在建工程（H2-1审定）</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('wp', 'I1')"><span class="gt-fe-ref-code">I1</span>无形资产（I1-1审定）</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('wp', 'J1')"><span class="gt-fe-ref-code">J1</span>长期股权投资（J1-1审定/J1-2明细）</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('wp', 'K1')"><span class="gt-fe-ref-code">K1</span>短期借款（K1-1审定）</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('wp', 'K2')"><span class="gt-fe-ref-code">K2</span>长期借款（K2-1审定）</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('wp', 'L1')"><span class="gt-fe-ref-code">L1</span>应付职工薪酬（L1-1审定）</div>
              <div class="gt-fe-ref-row" @click="jumpToSource('wp', 'M1')"><span class="gt-fe-ref-code">M1</span>所有者权益（M1-1审定）</div>
            </div>
          </div>
          <div class="gt-fe-ref-group">
            <div class="gt-fe-ref-group-title" @click="toggleRefGroup('tb')">
              <span>{{ refGroupOpen.tb ? '▼' : '▶' }} 📈 试算表</span>
              <span class="gt-fe-ref-count">1</span>
            </div>
            <div v-show="refGroupOpen.tb" class="gt-fe-ref-list">
              <div class="gt-fe-ref-row" @click="jumpToSource('tb', '')"><span class="gt-fe-ref-code">TB</span>打开试算表选择科目</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右栏：语法说明 -->
      <div class="gt-fe-help">
        <div class="gt-fe-section-title">语法说明</div>
        <div class="gt-fe-help-content">
          <div class="gt-fe-help-group">📐 取数函数（点击左侧按钮弹窗选择）</div>
          <div class="gt-fe-help-tip">
            💡 公式结果自动写入<b>当前行</b>。例如在 BS-027（资产总计）行配置公式，计算结果就填入该行。
          </div>
          <div class="gt-fe-help-item">
            <code>TB('1001','期末余额')</code>
            <span>从试算表取某科目的期末余额</span>
          </div>
          <div class="gt-fe-help-item">
            <code>SUM_TB('10','审定数')</code>
            <span>按科目前缀汇总（如10开头的所有科目）</span>
          </div>
          <div class="gt-fe-help-item">
            <code>ROW('BS-001')</code>
            <span>引用同报表某一行的金额</span>
          </div>
          <div class="gt-fe-help-item">
            <code>REPORT('BS-002','期末')</code>
            <span>跨表引用其他报表行的金额</span>
          </div>
          <div class="gt-fe-help-item">
            <code>NOTE('货币资金','合计','期末')</code>
            <span>引用附注表格的合计值</span>
          </div>
          <div class="gt-fe-help-item">
            <code>WP('E1-1','审定数')</code>
            <span>引用底稿审定表数据</span>
          </div>

          <div class="gt-fe-help-group">➕ 求和公式（当前行 = 公式结果）</div>
          <div class="gt-fe-help-item">
            <code>SUM_ROW('BS-002','BS-010')</code>
            <span>连续行求和：BS-002 到 BS-010 之间所有行</span>
          </div>
          <div class="gt-fe-help-item">
            <code>ROW('BS-002') + ROW('BS-011')</code>
            <span>指定行相加：逐个选择不连续的行</span>
          </div>
          <div class="gt-fe-help-item">
            <code>SUM_ROW('BS-002','BS-010') + ROW('BS-015')</code>
            <span>混合：连续段 + 单独行</span>
          </div>
          <div class="gt-fe-help-item">
            <code>SUM_ROW('BS-002','BS-010') + SUM_ROW('BS-020','BS-026')</code>
            <span>多段连续求和：两段连续行分别求和再相加</span>
          </div>
          <div class="gt-fe-help-item">
            <code>SUM_ROW('BS-002','BS-026') - ROW('BS-015')</code>
            <span>连续求和后减去某行（如扣除某项）</span>
          </div>

          <div class="gt-fe-help-group">🔍 逻辑校验</div>
          <div class="gt-fe-help-item">
            <code>ROW('BS-053') = ROW('BS-129')</code>
            <span>资产总计 应等于 负债和权益总计</span>
          </div>
          <div class="gt-fe-help-item">
            <code>ROW('BS-002') > 0</code>
            <span>货币资金 应大于 0</span>
          </div>
          <div class="gt-fe-help-item">
            <code>ROW('IS-040') >= ROW('IS-044')</code>
            <span>营业利润 应 ≥ 利润总额（含营业外）</span>
          </div>
          <div class="gt-fe-help-item">
            <code>IF(ROW('BS-002') > 0, '正常', '异常')</code>
            <span>条件判断：货币资金>0则正常，否则异常</span>
          </div>
          <div class="gt-fe-help-item">
            <code>IF(CHANGE_RATE('BS-008') > 0.3, '需说明', '正常')</code>
            <span>应收账款变动超30%需说明原因</span>
          </div>

          <div class="gt-fe-help-group">💡 合理性检查</div>
          <div class="gt-fe-help-item">
            <code>NOT_EMPTY('IS-002')</code>
            <span>营业收入 不能为空</span>
          </div>
          <div class="gt-fe-help-item">
            <code>NOT_ZERO('BS-002')</code>
            <span>货币资金 不能为零</span>
          </div>
          <div class="gt-fe-help-item">
            <code>CHANGE_RATE('BS-002') &lt; 0.5</code>
            <span>货币资金变动率 &lt; 50%（大额变动需说明）</span>
          </div>
          <div class="gt-fe-help-item">
            <code>REQUIRE_REASON('BS-002', 0.3)</code>
            <span>变动超30%时必须填写原因</span>
          </div>

          <div class="gt-fe-help-group">🔢 运算符</div>
          <div class="gt-fe-help-item">
            <code>+ - * /</code>
            <span>加减乘除四则运算</span>
          </div>
          <div class="gt-fe-help-item">
            <code>= != > &lt; >= &lt;=</code>
            <span>等于、不等于、大于、小于、大于等于、小于等于</span>
          </div>
          <div class="gt-fe-help-item">
            <code>IF(条件, 真值, 假值)</code>
            <span>条件判断：条件成立返回真值，否则返回假值</span>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="onSave">保存公式</el-button>
    </template>
  </el-dialog>

  <!-- 源表浏览弹窗 -->
  <el-dialog
    v-model="showSourceBrowser"
    :title="`选择 — ${sourceBrowserTitle}`"
    width="70%"
    top="5vh"
    append-to-body
    destroy-on-close
  >
    <div style="margin-bottom: 10px;">
      <el-input v-model="sourceBrowserSearch" size="small" placeholder="搜索编码或名称..." clearable style="width: 300px;" />
    </div>
    <el-table
      :data="filteredBrowserRows"
      v-loading="sourceBrowserLoading"
      max-height="60vh"
      border
      highlight-current-row
      size="small"
      style="width: 100%;"
      @row-click="onBrowserRowClick"
    >
      <el-table-column prop="row_code" label="编码" width="120" />
      <el-table-column prop="row_name" label="项目名称" min-width="260">
        <template #default="{ row }">
          <span :style="{ paddingLeft: (row.indent_level || 0) * 16 + 'px' }">{{ row.row_name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="formula" label="公式" min-width="200" show-overflow-tooltip />
      <el-table-column label="将插入引用" width="240">
        <template #default="{ row }">
          <code style="font-size: 11px; color: #4b2d77; background: #f0ecf5; padding: 1px 6px; border-radius: 4px;">{{ row._ref }}</code>
        </template>
      </el-table-column>
    </el-table>
    <div style="margin-top: 8px; font-size: 11px; color: #999;">
      💡 点击任意行即可将引用插入到当前公式中
    </div>
  </el-dialog>

  <!-- 报表类型选择弹窗（ROW/REPORT 先选哪张表） -->
  <el-dialog
    v-model="showReportTypePicker"
    title="选择报表"
    width="400px"
    append-to-body
    destroy-on-close
  >
    <div style="display: flex; flex-direction: column; gap: 8px;">
      <div
        v-for="opt in reportTypeOptions"
        :key="opt.type"
        class="gt-fe-report-type-item"
        @click="onPickReportType(opt)"
      >
        📊 {{ opt.label }}
      </div>
    </div>
  </el-dialog>

  <!-- 目标单元格定位弹窗 -->
  <el-dialog
    v-model="showTargetPicker"
    :title="`定位写入目标 — ${targetPickerTitle}`"
    width="80%"
    top="3vh"
    append-to-body
    destroy-on-close
  >
    <div v-if="targetPickerLoading" style="text-align: center; padding: 40px;">
      <el-icon class="is-loading" :size="24"><Loading /></el-icon>
      <div style="margin-top: 8px; color: #999; font-size: 12px;">加载表格数据...</div>
    </div>
    <div v-else>
      <div style="margin-bottom: 8px; font-size: 12px; color: #666;">
        💡 点击表格中的单元格，将其设为公式的写入目标位置
      </div>
      <div class="gt-fe-target-table-wrap">
        <table class="gt-fe-target-table" border="1">
          <thead>
            <tr>
              <th style="width: 40px; background: #f5f3f8;">#</th>
              <th style="background: #f5f3f8; padding: 6px 10px; font-size: 12px; width: 100px;">行次</th>
              <th style="background: #f5f3f8; padding: 6px 10px; font-size: 12px;">项目名称</th>
              <th style="background: #f5f3f8; padding: 6px 10px; font-size: 12px; width: 100px; text-align: center;">期末金额</th>
              <th style="background: #f5f3f8; padding: 6px 10px; font-size: 12px; width: 100px; text-align: center;">期初金额</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, ri) in targetPickerRows" :key="ri">
              <td style="color: #bbb; font-size: 10px; text-align: center; background: #faf8fd;">{{ ri + 1 }}</td>
              <td style="font-size: 11px; color: #999; white-space: nowrap;">{{ row[0] }}</td>
              <td style="font-size: 12px;">{{ row[1] }}</td>
              <td
                class="gt-fe-target-cell"
                :class="{ 'gt-fe-target-cell-selected': targetSelectedCell === `R${ri}C2` }"
                @click="onTargetCellClick(ri, 2, row[2])"
                style="text-align: center; min-width: 80px;"
              >
                <span v-if="targetSelectedCell === `R${ri}C2`" style="color: #4b2d77;">✓ 期末</span>
                <span v-else style="color: #ccc; font-size: 11px;">点击选择</span>
              </td>
              <td
                class="gt-fe-target-cell"
                :class="{ 'gt-fe-target-cell-selected': targetSelectedCell === `R${ri}C3` }"
                @click="onTargetCellClick(ri, 3, row[3])"
                style="text-align: center; min-width: 80px;"
              >
                <span v-if="targetSelectedCell === `R${ri}C3`" style="color: #4b2d77;">✓ 期初</span>
                <span v-else style="color: #ccc; font-size: 11px;">点击选择</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="targetSelectedCell" style="margin-top: 8px; font-size: 12px;">
        已选中：<code style="color: #4b2d77; background: #f0ecf5; padding: 2px 8px; border-radius: 4px;">{{ targetSelectedLabel }}</code>
      </div>
    </div>
    <template #footer>
      <el-button @click="showTargetPicker = false">取消</el-button>
      <el-button type="primary" :disabled="!targetSelectedCell" @click="confirmTargetCell">确认定位</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'

interface FormulaItem {
  expression: string
  category: string
  description: string
  target_cell?: string
  _checked?: boolean
}

const props = defineProps<{
  modelValue: boolean
  row: any
  sourceRows?: any[]
  applicableStandard?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'save': [data: { formula: string; category: string; description: string }]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const formulas = ref<FormulaItem[]>([])

watch(visible, (v) => {
  if (v && props.row) {
    if (props.row.formula) {
      // 多条公式用换行分隔存储，加载时拆分
      const lines = props.row.formula.split('\n').filter((l: string) => l.trim())
      const descs = (props.row.formula_description || '').split('；')
      if (lines.length > 1) {
        formulas.value = lines.map((expr: string, i: number) => ({
          expression: expr.trim(),
          category: props.row.formula_category || 'auto_calc',
          description: descs[i]?.trim() || '',
          _checked: false,
        }))
      } else {
        formulas.value = [{
          expression: props.row.formula,
          category: props.row.formula_category || 'auto_calc',
          description: props.row.formula_description || '',
          _checked: false,
        }]
      }
    } else {
      formulas.value = [{
        expression: '',
        category: 'auto_calc',
        description: '',
        _checked: false,
      }]
    }
  }
})

function addFormula() {
  formulas.value.push({ expression: '', category: 'logic_check', description: '', _checked: false })
}

const checkedCount = computed(() => formulas.value.filter((f: any) => f._checked).length)

function copyFormula() {
  // 优先复制勾选的公式，无勾选则复制当前选中的
  const checked = formulas.value.filter((f: any) => f._checked)
  if (checked.length > 0) {
    const insertAt = formulas.value.length
    checked.forEach((src: any) => {
      formulas.value.push({
        expression: src.expression,
        category: src.category,
        description: src.description ? src.description + '（副本）' : '',
        target_cell: '',
        _checked: false,
      })
    })
    // 取消原来的勾选
    formulas.value.forEach((f: any) => { f._checked = false })
    activeFormulaIdx.value = insertAt
    return
  }
  const idx = activeFormulaIdx.value
  if (idx < 0 || idx >= formulas.value.length) return
  const src = formulas.value[idx]
  formulas.value.splice(idx + 1, 0, {
    expression: src.expression,
    category: src.category,
    description: src.description ? src.description + '（副本）' : '',
    target_cell: '',
    _checked: false,
  })
  activeFormulaIdx.value = idx + 1
}

function removeFormula(idx: number) {
  formulas.value.splice(idx, 1)
}

// 拖拽排序
const dragIdx = ref(-1)
function onDragStart(idx: number) { dragIdx.value = idx }
function onDrop(idx: number) {
  if (dragIdx.value < 0 || dragIdx.value === idx) return
  const item = formulas.value.splice(dragIdx.value, 1)[0]
  formulas.value.splice(idx, 0, item)
  dragIdx.value = -1
}

// 需要弹窗选择的函数类型
const PICKER_FUNCTIONS = ['TB', 'SUM_TB', 'ROW', 'SUM_ROW', 'NOTE', 'WP', 'REPORT', 'AUX', 'PREV']

function insertRef(idx: number, fn: string) {
  activeFormulaIdx.value = idx

  // 取数类函数 → 弹出选择器让用户鼠标选
  if (PICKER_FUNCTIONS.includes(fn)) {
    openPickerForFunction(fn)
    return
  }

  const templates: Record<string, string> = {
    'EQ': " = ",
    'NEQ': " != ",
    'GT': " > ",
    'GTE': " >= ",
    'LT': " < ",
    'LTE': " <= ",
    'IF': "IF(条件, 真值, 假值)",
    'ABS': "ABS()",
    'ROUND': "ROUND(, 2)",
    'MAX': "MAX(, )",
    'MIN': "MIN(, )",
    'BETWEEN': "BETWEEN(, 下限, 上限)",
    'NOT_EMPTY': "NOT_EMPTY('')",
    'NOT_ZERO': "NOT_ZERO('')",
    'CHANGE_RATE': "CHANGE_RATE('') < 0.5",
    'REQUIRE_REASON': "REQUIRE_REASON('', 0.3)",
    'TOLERANCE': "TOLERANCE(, , 1)",
    'YOY_RATE': "YOY_RATE('')",
    'RATIO': "RATIO('', '')",
  }
  const tpl = templates[fn] || fn + '()'
  const f = formulas.value[idx]
  if (['EQ', 'NEQ', 'GT', 'GTE', 'LT', 'LTE'].includes(fn)) {
    f.expression += tpl
  } else {
    f.expression += (f.expression ? ' + ' : '') + tpl
  }
}

// 根据函数类型打开对应的数据源选择弹窗
const pickerFnType = ref('')  // 当前选择器对应的函数类型

function openPickerForFunction(fn: string) {
  pickerFnType.value = fn
  if (fn === 'ROW' || fn === 'REPORT' || fn === 'SUM_ROW') {
    showReportTypePicker.value = true
  } else if (fn === 'TB' || fn === 'SUM_TB') {
    openSourceBrowserForTB(fn)
  } else if (fn === 'NOTE') {
    openSourceBrowserForNote()
  } else if (fn === 'WP') {
    openSourceBrowserForWP()
  } else if (fn === 'AUX') {
    openSourceBrowserForTB('AUX')  // 复用试算表选择，生成 AUX 引用
  } else if (fn === 'PREV') {
    openSourceBrowserForTB('PREV')  // 复用试算表选择，生成 PREV 引用
  }
}

// ── 数据源一览跳转 ──
function jumpToSource(type: string, key: string) {
  if (type === 'report') {
    const labelMap: Record<string, string> = {
      balance_sheet: '资产负债表', income_statement: '利润表',
      cash_flow_statement: '现金流量表', equity_statement: '所有者权益变动表',
      cash_flow_supplement: '现金流附表', impairment_provision: '资产减值准备表',
    }
    pickerFnType.value = 'ROW'
    openSourceBrowserForReport(key, labelMap[key] || key)
  } else if (type === 'note') {
    pickerFnType.value = 'NOTE'
    // 直接插入带科目名的引用模板
    const idx = activeFormulaIdx.value
    if (idx >= 0 && idx < formulas.value.length) {
      const f = formulas.value[idx]
      f.expression += (f.expression ? ' + ' : '') + `NOTE('${key}','合计','期末')`
    }
  } else if (type === 'wp') {
    pickerFnType.value = 'WP'
    const idx = activeFormulaIdx.value
    if (idx >= 0 && idx < formulas.value.length) {
      const f = formulas.value[idx]
      f.expression += (f.expression ? ' + ' : '') + `WP('${key}-1','审定数')`
    }
  } else if (type === 'tb') {
    pickerFnType.value = 'TB'
    openSourceBrowserForTB('TB')
  }
}

// ── 报表类型选择弹窗（ROW/REPORT 先选哪张表） ──
const showReportTypePicker = ref(false)
const reportTypeOptions = [
  { type: 'balance_sheet', label: '资产负债表' },
  { type: 'income_statement', label: '利润表' },
  { type: 'cash_flow_statement', label: '现金流量表' },
  { type: 'equity_statement', label: '所有者权益变动表' },
  { type: 'cash_flow_supplement', label: '现金流附表' },
  { type: 'impairment_provision', label: '资产减值准备表' },
]

function onPickReportType(opt: { type: string; label: string }) {
  showReportTypePicker.value = false
  openSourceBrowserForReport(opt.type, opt.label)
}

// ── 报表行次浏览 ──
const sumRowStart = ref('')  // SUM_ROW 起始行

async function openSourceBrowserForReport(reportType: string, label: string) {
  const fn = pickerFnType.value
  sourceBrowserTitle.value = fn === 'SUM_ROW' ? `${label} — 选择起始行` : label
  sourceBrowserSearch.value = ''
  showSourceBrowser.value = true
  sourceBrowserLoading.value = true
  sumRowStart.value = ''
  sourceBrowserRefBuilder.value = (r: any) => {
    if (fn === 'REPORT') return `REPORT('${r.row_code}','期末')`
    if (fn === 'SUM_ROW') return `（点击选择起始行）`
    return `ROW('${r.row_code}')`
  }
  try {
    const standard = props.applicableStandard || 'soe_consolidated'
    const resp = await api.get('/api/report-config', {
      params: { report_type: reportType, applicable_standard: standard },
      validateStatus: (s: number) => s < 600,
    })
    const rows = resp?.data ?? resp ?? []
    sourceBrowserRows.value = rows.map((r: any) => ({
      ...r,
      _ref: sourceBrowserRefBuilder.value(r),
    }))
  } catch {
    sourceBrowserRows.value = []
  } finally {
    sourceBrowserLoading.value = false
  }
}

// ── 试算表科目浏览 ──
async function openSourceBrowserForTB(fn: string) {
  sourceBrowserTitle.value = '试算表科目'
  sourceBrowserSearch.value = ''
  showSourceBrowser.value = true
  sourceBrowserLoading.value = true
  sourceBrowserRefBuilder.value = (r: any) => {
    const code = r.standard_account_code || r.account_code || r.row_code || ''
    if (fn === 'SUM_TB') return `SUM_TB('${code.substring(0, 2)}','审定数')`
    if (fn === 'AUX') return `AUX('${code}','','期末')`
    if (fn === 'PREV') return `PREV('${code}','期末')`
    return `TB('${code}','期末余额')`
  }
  try {
    const resp = await api.get('/api/trial-balance', {
      validateStatus: (s: number) => s < 600,
    })
    const rows = resp?.data ?? resp ?? []
    sourceBrowserRows.value = rows.map((r: any) => ({
      row_code: r.standard_account_code || r.account_code || '',
      row_name: r.account_name || r.standard_account_name || '',
      indent_level: (r.level || 1) - 1,
      formula: '',
      _ref: sourceBrowserRefBuilder.value(r),
    }))
  } catch {
    sourceBrowserRows.value = []
  } finally {
    sourceBrowserLoading.value = false
  }
}

// ── 附注章节浏览 ──
async function openSourceBrowserForNote() {
  sourceBrowserTitle.value = '附注章节'
  sourceBrowserSearch.value = ''
  showSourceBrowser.value = true
  sourceBrowserLoading.value = true
  sourceBrowserRefBuilder.value = (r: any) => {
    const name = r.row_name || r.title || ''
    return `NOTE('${name}','合计','期末')`
  }
  try {
    const resp = await api.get('/api/disclosure-notes/tree', {
      validateStatus: (s: number) => s < 600,
    })
    const items = resp?.data ?? resp ?? []
    sourceBrowserRows.value = items.map((r: any) => ({
      row_code: r.note_number || r.section_number || '',
      row_name: r.title || r.section_title || '',
      indent_level: (r.level || 1) - 1,
      formula: '',
      _ref: sourceBrowserRefBuilder.value(r),
    }))
  } catch {
    sourceBrowserRows.value = []
  } finally {
    sourceBrowserLoading.value = false
  }
}

// ── 底稿浏览 ──
async function openSourceBrowserForWP() {
  sourceBrowserTitle.value = '底稿列表'
  sourceBrowserSearch.value = ''
  showSourceBrowser.value = true
  sourceBrowserLoading.value = true
  sourceBrowserRefBuilder.value = (r: any) => {
    const code = r.wp_code || r.row_code || ''
    return `WP('${code}','审定数')`
  }
  try {
    const resp = await api.get('/api/working-papers', {
      validateStatus: (s: number) => s < 600,
    })
    const items = resp?.data ?? resp ?? []
    sourceBrowserRows.value = items.map((r: any) => ({
      row_code: r.wp_code || '',
      row_name: r.wp_name || r.name || '',
      indent_level: 0,
      formula: '',
      _ref: sourceBrowserRefBuilder.value(r),
    }))
  } catch {
    sourceBrowserRows.value = []
  } finally {
    sourceBrowserLoading.value = false
  }
}

function onSave() {
  const validFormulas = formulas.value.filter(f => f.expression.trim())
  if (!validFormulas.length) {
    const first = formulas.value[0]
    emit('save', { formula: '', category: first?.category || 'auto_calc', description: first?.description || '' })
  } else if (validFormulas.length === 1) {
    emit('save', {
      formula: validFormulas[0].expression,
      category: validFormulas[0].category,
      description: validFormulas[0].description,
    })
  } else {
    // 多条公式用换行拼接，分类取第一条的
    emit('save', {
      formula: validFormulas.map(f => f.expression).join('\n'),
      category: validFormulas[0].category,
      description: validFormulas.map(f => f.description || f.expression.substring(0, 30)).join('；'),
    })
  }
  visible.value = false
}

// ── 数据源一览折叠状态 ──
const refGroupOpen = ref<Record<string, boolean>>({ report: false, note: false, wp: false, tb: false })
function toggleRefGroup(key: string) {
  refGroupOpen.value[key] = !refGroupOpen.value[key]
}

// ── 源表浏览弹窗 ──
const activeFormulaIdx = ref(0)
const showSourceBrowser = ref(false)
const sourceBrowserTitle = ref('')
const sourceBrowserRows = ref<any[]>([])
const sourceBrowserLoading = ref(false)
const sourceBrowserSearch = ref('')
const sourceBrowserRefBuilder = ref<(r: any) => string>(() => '')

const filteredBrowserRows = computed(() => {
  const kw = sourceBrowserSearch.value.toLowerCase()
  if (!kw) return sourceBrowserRows.value
  return sourceBrowserRows.value.filter((r: any) =>
    (r.row_code || '').toLowerCase().includes(kw) || (r.row_name || '').toLowerCase().includes(kw)
  )
})

function onBrowserRowClick(row: any) {
  const idx = activeFormulaIdx.value
  if (idx < 0 || idx >= formulas.value.length) return
  const f = formulas.value[idx]

  // SUM_ROW 需要选两次（起始行 + 结束行）
  if (pickerFnType.value === 'SUM_ROW') {
    if (!sumRowStart.value) {
      // 第一次点击：记录起始行，提示选结束行
      sumRowStart.value = row.row_code
      sourceBrowserTitle.value = sourceBrowserTitle.value.replace('选择起始行', `起始 ${row.row_code}，再选结束行`)
      // 更新引用列显示
      sourceBrowserRows.value = sourceBrowserRows.value.map((r: any) => ({
        ...r,
        _ref: `SUM_ROW('${sumRowStart.value}','${r.row_code}')`,
      }))
      return
    } else {
      // 第二次点击：生成完整公式
      const ref = `SUM_ROW('${sumRowStart.value}','${row.row_code}')`
      f.expression += (f.expression ? ' + ' : '') + ref
      sumRowStart.value = ''
      showSourceBrowser.value = false
      return
    }
  }

  f.expression += (f.expression ? ' + ' : '') + row._ref
  showSourceBrowser.value = false
}

// ── 目标单元格定位弹窗 ──
const showTargetPicker = ref(false)
const targetPickerTitle = ref('')
const targetPickerHeaders = ref<string[]>([])
const targetPickerRows = ref<any[][]>([])
const targetPickerLoading = ref(false)
const targetSelectedCell = ref('')
const targetSelectedLabel = ref('')
const targetFormulaIdx = ref(0)
const targetPickerRawRows = ref<any[]>([])

function openTargetPicker(idx: number) {
  targetFormulaIdx.value = idx
  const r = props.row
  if (r?.row_code && !r.row_code.startsWith('CUSTOM')) {
    // 报表行——目标就是当前行本身
    const f = formulas.value[idx]
    f.target_cell = `${r.row_code} ${r.row_name}`
    return
  }
  // 自定义公式——弹出表格让用户选择目标行
  targetPickerTitle.value = '选择公式写入的目标行'
  targetSelectedCell.value = ''
  targetSelectedLabel.value = ''
  loadTargetRows()
}

async function loadTargetRows() {
  showTargetPicker.value = true
  targetPickerLoading.value = true
  try {
    const standard = props.applicableStandard || 'soe_consolidated'
    const resp = await api.get('/api/report-config', {
      params: { report_type: 'balance_sheet', applicable_standard: standard },
      validateStatus: (s: number) => s < 600,
    })
    const rows = resp?.data ?? resp ?? []
    targetPickerHeaders.value = ['行次', '项目名称', '期末金额', '期初金额']
    targetPickerRows.value = rows.map((r: any) => [
      r.row_code || '',
      r.row_name || '',
      '',  // 期末金额列（可点击选择）
      '',  // 期初金额列（可点击选择）
    ])
    targetPickerRawRows.value = rows
  } catch {
    targetPickerHeaders.value = []
    targetPickerRows.value = []
  } finally {
    targetPickerLoading.value = false
  }
}

const periodLabels: Record<number, string> = { 2: '期末', 3: '期初' }

function onTargetCellClick(ri: number, ci: number, _cell: any) {
  // 只允许点击期末(ci=2)或期初(ci=3)列
  if (ci < 2) return
  targetSelectedCell.value = `R${ri}C${ci}`
  const raw = targetPickerRawRows.value[ri]
  const period = periodLabels[ci] || '期末'
  if (raw) {
    targetSelectedLabel.value = `${raw.row_code || ''} ${raw.row_name || ''} · ${period}`
  } else {
    targetSelectedLabel.value = `第${ri + 1}行 · ${period}`
  }
}

function confirmTargetCell() {
  const idx = targetFormulaIdx.value
  if (idx >= 0 && idx < formulas.value.length && targetSelectedLabel.value) {
    formulas.value[idx].target_cell = targetSelectedLabel.value
  }
  showTargetPicker.value = false
}

</script>

<style scoped>
.gt-fe-container {
  display: flex;
  gap: 12px;
  height: calc(100vh - 200px);
  min-height: 400px;
}
.gt-fe-formulas {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
}
.gt-fe-sources {
  width: 280px;
  flex-shrink: 0;
  border-left: 1px solid #e8e4f0;
  border-right: 1px solid #e8e4f0;
  padding: 0 12px;
  overflow-y: auto;
}
.gt-fe-help {
  width: 280px;
  flex-shrink: 0;
  padding-left: 4px;
  overflow-y: auto;
  max-height: 100%;
}
.gt-fe-ref-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.gt-fe-ref-group-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
  color: #555;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  user-select: none;
  transition: background 0.12s;
}
.gt-fe-ref-group-title:hover {
  background: #f0ecf5;
}
.gt-fe-ref-count {
  font-size: 10px;
  color: #999;
  background: #f0ecf5;
  padding: 1px 6px;
  border-radius: 8px;
}
.gt-fe-ref-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.gt-fe-ref-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  color: #444;
  transition: all 0.12s;
}
.gt-fe-ref-row:hover {
  background: #f0ecf5;
  color: #4b2d77;
}
.gt-fe-ref-code {
  display: inline-block;
  min-width: 32px;
  font-size: 10px;
  font-weight: 700;
  color: #4b2d77;
  background: #f0ecf5;
  padding: 1px 5px;
  border-radius: 3px;
  text-align: center;
  font-family: 'Cascadia Code', 'Fira Code', monospace;
}
.gt-fe-section-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  color: #333;
  margin-bottom: 10px;
}
.gt-fe-formula-item {
  border: 1px solid #e8e4f0;
  border-radius: 6px;
  padding: 6px 8px;
  margin-bottom: 6px;
  background: #faf8fd;
  cursor: pointer;
  transition: border-color 0.15s;
}
.gt-fe-formula-active {
  border-color: var(--gt-color-primary);
  box-shadow: 0 0 0 1px rgba(75, 45, 119, 0.1);
}
.gt-fe-drag-handle {
  cursor: grab;
  color: #ccc;
  font-size: 14px;
  user-select: none;
  padding: 0 2px;
}
.gt-fe-drag-handle:hover { color: #999; }
.gt-fe-formula-header {
  display: flex;
  gap: 4px;
  align-items: center;
  margin-bottom: 4px;
  font-size: 11px;
}
.gt-fe-formula-input {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gt-fe-quick-btns {
  display: flex;
  gap: 3px;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 3px;
}
.gt-fe-quick-btns .el-button {
  font-size: 10px;
  padding: 2px 6px;
  font-family: 'Cascadia Code', 'Fira Code', monospace;
  height: 22px;
  line-height: 1;
}
.gt-fe-btn-label {
  font-size: 9px;
  color: #999;
  margin-right: 2px;
  white-space: nowrap;
  min-width: 28px;
}
.gt-fe-help-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.gt-fe-help-item {
  font-size: 11px;
  line-height: 1.5;
}
.gt-fe-help-item code {
  display: inline-block;
  background: #f0ecf5;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  color: #4b2d77;
  margin-bottom: 2px;
}
.gt-fe-help-item span {
  display: block;
  color: #888;
  font-size: 11px;
}
.gt-fe-help-group {
  font-size: 11px;
  font-weight: 600;
  color: #555;
  margin-top: 8px;
  margin-bottom: 4px;
  padding-bottom: 2px;
  border-bottom: 1px solid #f0ecf5;
}
.gt-fe-help-tip {
  font-size: 11px;
  color: #4b2d77;
  background: #f8f5fd;
  border: 1px solid #e8e0f5;
  border-radius: 6px;
  padding: 6px 10px;
  margin-bottom: 8px;
  line-height: 1.6;
}
.gt-fe-help-link {
  cursor: pointer;
}
.gt-fe-help-link:hover {
  background: #e0d8f0 !important;
}
.gt-fe-link {
  color: var(--gt-color-primary);
  cursor: pointer;
  text-decoration: none;
  font-size: 10px;
}
.gt-fe-link:hover {
  text-decoration: underline;
}
.gt-fe-report-type-item {
  padding: 10px 16px;
  border: 1px solid #e8e4f0;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}
.gt-fe-report-type-item:hover {
  background: #f0ecf5;
  border-color: var(--gt-color-primary);
  transform: translateX(4px);
}
.gt-fe-target-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 0;
  margin-bottom: 4px;
}
.gt-fe-target-table-wrap {
  max-height: 55vh;
  overflow: auto;
  border: 1px solid #e8e4f0;
  border-radius: 6px;
}
.gt-fe-target-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.gt-fe-target-table th,
.gt-fe-target-table td {
  padding: 5px 8px;
  border: 1px solid #e8e4f0;
}
.gt-fe-target-cell {
  cursor: pointer;
  transition: background 0.1s;
}
.gt-fe-target-cell:hover {
  background: #f0ecf5;
}
.gt-fe-target-cell-selected {
  background: var(--gt-color-primary-bg, #f4f0fa) !important;
  outline: 1.5px solid var(--gt-color-primary, #4b2d77);
  outline-offset: -1.5px;
}
</style>
