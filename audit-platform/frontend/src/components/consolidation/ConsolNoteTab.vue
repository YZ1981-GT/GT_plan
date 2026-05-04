<template>
  <div class="gt-tab-content gt-note-layout">
    <!-- 右侧：章节内容（左侧树已移到第3栏 ConsolCatalog） -->
    <div class="gt-note-content" style="flex:1">
      <div v-if="selectedNoteSection" class="gt-note-detail">
        <!-- 工具栏 -->
        <div class="gt-note-toolbar">
          <h4 class="gt-note-section-title">{{ selectedNoteSection.title }}</h4>
          <div class="gt-note-actions">
            <el-tooltip content="复制整表（可粘贴到 Word/Excel）" placement="bottom">
              <el-button size="small" @click="copyEntireNoteTable">📋 整表</el-button>
            </el-tooltip>
            <el-button-group size="small">
              <el-button :type="noteEditMode ? '' : 'primary'" @click="exitNoteEdit(true)">📋 查看</el-button>
              <el-button :type="noteEditMode ? 'primary' : ''" @click="enterNoteEdit()">✏️ 编辑</el-button>
            </el-button-group>
            <el-tooltip content="全屏编辑（ESC 退出）" placement="bottom">
              <el-button size="small" @click="toggleNoteFullscreen">{{ noteFullscreen ? '退出' : '全屏' }}</el-button>
            </el-tooltip>
            <el-tooltip content="保存当前表格数据" placement="bottom">
              <el-button size="small" @click="saveNoteData">💾</el-button>
            </el-tooltip>
            <el-tooltip content="导入导出与批量操作" placement="bottom">
              <el-button size="small" @click="showNoteBatchDialog = true">📦</el-button>
            </el-tooltip>
            <el-tooltip content="根据公式从项目数据重新计算" placement="bottom">
              <el-button size="small" @click="refreshNoteByFormula" :loading="noteRefreshing">🔄</el-button>
            </el-tooltip>
            <el-tooltip content="审核当前表格公式一致性" placement="bottom">
              <el-button size="small" @click="auditCurrentNote" :loading="noteSingleAuditLoading">✅</el-button>
            </el-tooltip>
            <el-tooltip content="公式管理（编辑取数规则）" placement="bottom">
              <el-button size="small" @click="openNoteFormula">ƒx</el-button>
            </el-tooltip>
          </div>
        </div>

        <!-- 当前表格 -->
        <div v-if="selectedNoteSection.headers?.length" class="gt-note-table-wrap">
          <el-table ref="noteTableRef" :data="selectedNoteSection.editRows" border size="small"
            :max-height="noteFullscreen ? 'calc(100vh - 100px)' : 'calc(100vh - 260px)'"
            style="width:100%" class="gt-note-compact-table"
            :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
            :header-cell-style="{ background: '#f0edf5', fontSize: '13px', padding: '4px 0' }"
            :cell-style="{ padding: '2px 6px', fontSize: '13px', lineHeight: '1.4' }"
            :cell-class-name="noteCellClassName"
            @selection-change="onNoteSelectionChange"
            @cell-click="onNoteCellClick"
            @cell-contextmenu="onNoteCellContextMenu">
            <el-table-column v-if="noteEditMode" type="selection" width="36" />
            <el-table-column v-for="(h, hi) in selectedNoteSection.headers" :key="hi" :label="h" :min-width="hi === 0 ? 200 : 130">
              <template #default="{ row, $index }">
                <el-input v-if="noteEditMode && lazyEdit.isEditing($index, hi)" v-model="row[hi]" size="small" :placeholder="h"
                  :style="{ textAlign: hi === 0 ? 'left' : 'right' }"
                  @blur="lazyEdit.stopEdit()" @input="markNoteDirty()" autofocus />
                <CommentTooltip v-else-if="hi > 0" :comment="cellComments.getComment(selectedNoteSection?.section_id || 'default', $index, hi)">
                <span class="gt-note-cell-text"
                  :class="{ 'gt-note-cell-editable': noteEditMode }"
                  :style="{ textAlign: 'right' }"
                  @click="noteEditMode && lazyEdit.startEdit($index, hi)">{{ row[hi] || '-' }}</span>
                </CommentTooltip>
                <span v-else class="gt-note-cell-text"
                  :class="{ 'gt-note-cell-editable': noteEditMode }"
                  :style="{ textAlign: 'left' }"
                  @click="noteEditMode && lazyEdit.startEdit($index, hi)">{{ row[hi] || '-' }}</span>
              </template>
            </el-table-column>
          </el-table>

          <div class="gt-note-table-footer">
            <template v-if="noteEditMode">
              <el-button size="small" @click="addNoteRow">+ 新增行</el-button>
              <el-button size="small" type="danger" :disabled="!noteSelectedRows.length" @click="deleteNoteRows">
                删除{{ noteSelectedRows.length ? `(${noteSelectedRows.length})` : '' }}
              </el-button>
            </template>
            <span v-else style="font-size:11px;color:#999">💡 查看模式下可选中复制，粘贴到 Word/Excel 保持格式</span>
            <span style="flex:1" />
            <span style="font-size:11px;color:#999">共 {{ selectedNoteSection.editRows?.length || 0 }} 行</span>
          </div>

          <!-- 选中区域状态栏 -->
          <SelectionBar :stats="noteCtx.selectionStats()" />
        </div>
        <el-empty v-else description="该章节暂无表格" :image-size="60" />
      </div>
      <div v-else class="gt-note-empty-guide">
        <div class="gt-note-empty-hero">
          <p>在左侧附注栏选择章节开始编辑，或使用批量功能一键导入全部数据</p>
          <div class="gt-note-empty-actions">
            <el-button size="small" @click="showNoteBatchDialog = true">📦 批量导入导出</el-button>
            <el-button size="small" @click="switchToFourCol">🔲 切换四栏视图显示附注树</el-button>
          </div>
        </div>
        <div class="gt-note-empty-steps">
          <div class="gt-note-step">
            <div class="gt-note-step-icon">①</div>
            <div class="gt-note-step-text">
              <b>切换四栏视图</b>
              <p>点击顶部栏 🔲 按钮或上方快捷按钮，左侧出现附注树形导航，按科目章节分组展示所有表格</p>
            </div>
          </div>
          <div class="gt-note-step">
            <div class="gt-note-step-icon">②</div>
            <div class="gt-note-step-text">
              <b>选择章节编辑</b>
              <p>点击树形中的具体表格名称加载到右侧，切换"查看/编辑"模式，编辑模式支持逐单元格修改、增删行、多选删除</p>
            </div>
          </div>
          <div class="gt-note-step">
            <div class="gt-note-step-icon">③</div>
            <div class="gt-note-step-text">
              <b>批量导入导出</b>
              <p>点击"📦 批量"弹窗：一键导出全部模板（空表）或数据（已填），一键导入 Excel（按 Sheet 名自动匹配章节）</p>
            </div>
          </div>
          <div class="gt-note-step">
            <div class="gt-note-step-icon">④</div>
            <div class="gt-note-step-text">
              <b>保存与复制</b>
              <p>编辑后点"💾 保存"入库，查看模式下可直接框选表格复制，粘贴到 Word/Excel 自动保持表格格式</p>
            </div>
          </div>
        </div>
        <div class="gt-note-empty-info">
          国企版 91 章节 · 221 表格 &nbsp;|&nbsp; 上市版 80 章节 · 282 表格 &nbsp;|&nbsp; 顶部栏切换准则自动更新 &nbsp;|&nbsp; 每表独立保存不丢失 &nbsp;|&nbsp; 全屏编辑按 ESC 退出
        </div>
      </div>
    </div>
    <input ref="noteFileRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onNoteFileSelected" />
    <input ref="noteBatchFileRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onNoteBatchImport" />
    <input ref="noteFormulaFileRef" type="file" accept=".xlsx,.xls,.json" style="display:none" @change="onNoteFormulaImport" />
  </div>

  <!-- 附注全屏覆盖层（Teleport 到 body 避免被裁剪） -->
  <Teleport to="body">
    <div v-if="noteFullscreen" class="gt-fullscreen">
      <div v-if="selectedNoteSection" class="gt-note-detail">
        <div class="gt-note-toolbar">
          <h4 class="gt-note-section-title">{{ selectedNoteSection.title }}</h4>
          <div class="gt-note-actions">
            <el-button-group size="small">
              <el-button :type="noteEditMode ? '' : 'primary'" @click="exitNoteEdit(true)">📋 查看</el-button>
              <el-button :type="noteEditMode ? 'primary' : ''" @click="enterNoteEdit()">✏️ 编辑</el-button>
            </el-button-group>
            <el-tooltip content="公式管理" placement="bottom">
              <el-button size="small" @click="openNoteFormula">ƒx</el-button>
            </el-tooltip>
            <el-button size="small" type="danger" @click="toggleNoteFullscreen">✕ 退出全屏</el-button>
          </div>
        </div>
        <div v-if="selectedNoteSection.headers?.length" style="flex:1;min-height:0">
          <el-table :data="selectedNoteSection.editRows" border size="small"
            max-height="calc(100vh - 100px)" style="width:100%" class="gt-note-compact-table"
            :style="{ fontSize: displayPrefs.fontConfig.tableFont }"
            :header-cell-style="{ background: '#f0edf5', fontSize: '11px', padding: '2px 0' }"
            :cell-style="{ padding: '0 4px', fontSize: '11px', lineHeight: '1.2' }"
            @selection-change="onNoteSelectionChange">
            <el-table-column v-if="noteEditMode" type="selection" width="36" />
            <el-table-column v-for="(h, hi) in selectedNoteSection.headers" :key="hi" :label="h" :min-width="hi === 0 ? 200 : 130">
              <template #default="{ row, $index }">
                <el-input v-if="noteEditMode && lazyEdit.isEditing($index + 10000, hi)" v-model="row[hi]" size="small" :placeholder="h"
                  :style="{ textAlign: hi === 0 ? 'left' : 'right' }"
                  @blur="lazyEdit.stopEdit()" @input="markNoteDirty()" autofocus />
                <span v-else class="gt-note-cell-text"
                  :class="{ 'gt-note-cell-editable': noteEditMode }"
                  :style="{ textAlign: hi === 0 ? 'left' : 'right' }"
                  @click="noteEditMode && lazyEdit.startEdit($index + 10000, hi)">{{ row[hi] || '-' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div class="gt-note-table-footer" style="margin-top:6px">
          <template v-if="noteEditMode">
            <el-button size="small" @click="addNoteRow">+ 新增行</el-button>
            <el-button size="small" type="danger" :disabled="!noteSelectedRows.length" @click="deleteNoteRows">
              删除{{ noteSelectedRows.length ? `(${noteSelectedRows.length})` : '' }}
            </el-button>
          </template>
          <span style="flex:1" />
          <span style="font-size:11px;color:#999">共 {{ selectedNoteSection.editRows?.length || 0 }} 行 · ESC 退出全屏</span>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- 右键菜单（统一组件 + 模块特有项） -->
  <CellContextMenu
    :visible="noteCtx.contextMenu.visible"
    :x="noteCtx.contextMenu.x"
    :y="noteCtx.contextMenu.y"
    :item-name="drillDownCell.itemName"
    :value="drillDownCell.totalValue"
    :multi-count="noteCtx.selectedCells.value.length"
    @copy="onNoteCtxCopy"
    @formula="onNoteCtxFormula"
    @sum="onNoteCtxSum"
    @compare="onNoteCtxCompare"
  >
    <div class="gt-ucell-ctx-item" @click="drillDownFromCell"><span class="gt-ucell-ctx-icon">📊</span> 查看汇总穿透</div>
    <div class="gt-ucell-ctx-item" @click="addCellComment"><span class="gt-ucell-ctx-icon">💬</span> 添加批注</div>
    <div class="gt-ucell-ctx-item" @click="markCellReviewed"><span class="gt-ucell-ctx-icon">✅</span> 标记已复核</div>
    <div class="gt-ucell-ctx-divider" />
    <div class="gt-ucell-ctx-item" @click="openAggregateDialog"><span class="gt-ucell-ctx-icon">Σ</span> 汇总</div>
  </CellContextMenu>

  <!-- 批量导入导出弹窗 -->
  <el-dialog v-model="showNoteBatchDialog" title="附注导入导出与批量操作" width="520px" append-to-body>
    <div style="display:flex;flex-direction:column;gap:10px">
      <p style="font-size:12px;color:#666;margin:0 0 4px;font-weight:600">当前表格操作</p>
      <div style="display:flex;gap:8px">
        <el-button size="small" @click="exportNoteTemplate" :disabled="!selectedNoteSection">📥 导出当前模板</el-button>
        <el-button size="small" @click="exportNoteData" :disabled="!selectedNoteSection">📤 导出当前数据</el-button>
        <el-button size="small" @click="noteFileRef?.click()" :disabled="!selectedNoteSection">📤 导入当前表格</el-button>
      </div>
      <el-divider style="margin:6px 0" />
      <p style="font-size:12px;color:#666;margin:0 0 4px;font-weight:600">全部附注批量操作</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <el-button size="small" @click="batchExportAllTemplates" :loading="noteBatchLoading">📥 一键导出全部模板</el-button>
        <el-button size="small" @click="batchExportAllData" :loading="noteBatchLoading">📤 一键导出全部数据</el-button>
        <el-button size="small" type="primary" @click="noteBatchFileRef?.click()" :loading="noteBatchLoading">📤 一键导入全部数据</el-button>
      </div>
      <el-divider style="margin:6px 0" />
      <p style="font-size:12px;color:#666;margin:0 0 4px;font-weight:600">公式审核</p>
      <div style="display:flex;gap:8px">
        <el-button size="small" @click="() => { auditCurrentNote(); showNoteBatchDialog = false }" :disabled="!selectedNoteSection" :loading="noteSingleAuditLoading">✅ 审核当前表格</el-button>
        <el-button size="small" @click="() => { onNoteAuditAll(); showNoteBatchDialog = false }">✅ 全部附注审核</el-button>
      </div>
      <el-divider style="margin:6px 0" />
      <p style="font-size:12px;color:#666;margin:0 0 4px;font-weight:600">公式管理</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <el-button size="small" @click="() => { openNoteFormula(); showNoteBatchDialog = false }">ƒx 打开公式管理</el-button>
        <el-button size="small" @click="exportNoteFormulas" :loading="noteBatchLoading">📥 导出公式模板</el-button>
        <el-button size="small" @click="noteFormulaFileRef?.click()" :loading="noteBatchLoading">📤 导入公式</el-button>
        <el-button size="small" type="primary" @click="applyAllNoteFormulas" :loading="noteBatchLoading">▶ 一键取数计算</el-button>
      </div>
      <p style="font-size:11px;color:#999;margin:4px 0 0">
        导出 Excel 每个表格一个 Sheet（编号+标题），导入按 Sheet 名自动匹配。
      </p>
    </div>
    <template #footer>
      <el-button @click="showNoteBatchDialog = false">关闭</el-button>
    </template>
  </el-dialog>

  <!-- 附注全审结果弹窗 -->
  <el-dialog v-model="showNoteAuditDialog" title="附注公式审核结果" width="80%" top="4vh" append-to-body destroy-on-close :z-index="10000">
    <div v-if="noteAuditLoading" style="text-align:center;padding:40px">
      <span class="is-loading" style="font-size:24px;display:inline-block">⏳</span>
      <p style="color:#999;margin-top:8px">正在审核所有附注表格...</p>
    </div>
    <div v-else>
      <div style="display:flex;gap:12px;margin-bottom:12px;align-items:center">
        <el-tag :type="noteAuditSummary.errorCount ? 'danger' : 'success'" size="large">
          {{ noteAuditSummary.errorCount ? `${noteAuditSummary.errorCount} 项异常` : '全部通过' }}
        </el-tag>
        <span style="font-size:12px;color:#999">
          共审核 {{ noteAuditSummary.totalSections }} 个章节 · {{ noteAuditSummary.totalChecks }} 条规则 ·
          通过 {{ noteAuditSummary.passCount }} · 异常 {{ noteAuditSummary.errorCount }} · 警告 {{ noteAuditSummary.warnCount }}
        </span>
      </div>
      <el-table :data="noteAuditResults" border size="small" max-height="60vh" style="width:100%"
        :header-cell-style="{ background: '#f8f6fb', fontSize: '12px' }"
        :row-class-name="auditRowClass">
        <el-table-column prop="section_title" label="章节" min-width="160" show-overflow-tooltip />
        <el-table-column prop="rule_name" label="审核规则" min-width="200" show-overflow-tooltip />
        <el-table-column prop="level" label="级别" width="70" align="center">
          <template #default="{ row }">
            <el-tag :type="row.level === 'error' ? 'danger' : row.level === 'warn' ? 'warning' : 'success'" size="small">
              {{ row.level === 'error' ? '异常' : row.level === 'warn' ? '警告' : '通过' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="expected" label="预期值" width="120" align="right" />
        <el-table-column prop="actual" label="实际值" width="120" align="right" />
        <el-table-column prop="difference" label="差异" width="120" align="right">
          <template #default="{ row }">
            <span :style="{ color: row.difference ? '#f56c6c' : '#67c23a' }">{{ row.difference || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="说明" min-width="200" show-overflow-tooltip />
      </el-table>
    </div>
    <template #footer>
      <el-button @click="showNoteAuditDialog = false">关闭</el-button>
      <el-button type="primary" @click="exportAuditResults">📤 导出审核报告</el-button>
    </template>
  </el-dialog>

  <!-- 批注弹窗 -->
  <el-dialog v-model="showCommentDialog" :title="editingCommentId ? '编辑审计批注' : '添加审计批注'" width="650px" append-to-body :z-index="10000" class="gt-comment-dialog">
    <div class="gt-comment-info">
      <div class="gt-comment-info-item">
        <span class="gt-comment-info-label">项目</span>
        <span class="gt-comment-info-value">{{ commentTarget.itemName }}</span>
      </div>
      <div class="gt-comment-info-item">
        <span class="gt-comment-info-label">列</span>
        <span class="gt-comment-info-value">{{ commentTarget.colName }}</span>
      </div>
      <div class="gt-comment-info-item">
        <span class="gt-comment-info-label">当前值</span>
        <span class="gt-comment-info-value gt-comment-info-value--primary">{{ commentTarget.value || '-' }}</span>
      </div>
    </div>
    <el-input v-model="commentTarget.text" type="textarea" :rows="8"
      placeholder="输入审计批注、发现的问题或需要跟进的事项..."
      maxlength="500" show-word-limit
      class="gt-comment-textarea" />
    <template #footer>
      <el-button v-if="editingCommentId" type="danger" plain @click="deleteCurrentComment" style="float:left">删除批注</el-button>
      <el-button @click="showCommentDialog = false">取消</el-button>
      <el-button type="primary" @click="saveComment">保存批注</el-button>
    </template>
  </el-dialog>

  <!-- 汇总弹窗 -->
  <el-dialog v-model="showAggregateDialog" title="数据汇总" width="800px" append-to-body :z-index="10000" class="gt-comment-dialog">
    <div class="gt-comment-info" style="margin-bottom:16px">
      <div class="gt-comment-info-item" style="flex:2">
        <span class="gt-comment-info-label">目标单元格</span>
        <span class="gt-comment-info-value" style="font-size:14px">{{ aggTarget.itemName }} / {{ aggTarget.colName }}</span>
      </div>
      <div class="gt-comment-info-item">
        <span class="gt-comment-info-label">当前值</span>
        <span class="gt-comment-info-value gt-comment-info-value--primary">{{ aggTarget.currentValue || '-' }}</span>
      </div>
      <div class="gt-comment-info-item">
        <span class="gt-comment-info-label">当前单位</span>
        <span class="gt-comment-info-value">{{ currentEntity.name || '集团' }}</span>
      </div>
    </div>

    <el-radio-group v-model="aggTarget.mode" style="margin-bottom:14px;width:100%">
      <el-radio value="direct" style="display:flex;align-items:flex-start;margin-bottom:12px;width:100%">
        <div>
          <b>直接下级汇总</b>
          <p style="margin:2px 0 0;font-size:12px;color:#999">汇总当前合并节点的直接下级企业，取同表同行同列数据求和</p>
        </div>
      </el-radio>
      <el-radio value="custom" style="display:flex;align-items:flex-start;width:100%">
        <div>
          <b>自定义汇总</b>
          <p style="margin:2px 0 0;font-size:12px;color:#999">自由选择单位、数据表、坐标位置</p>
        </div>
      </el-radio>
    </el-radio-group>

    <!-- 自定义汇总详细设置 -->
    <div v-if="aggTarget.mode === 'custom'" style="border:1px solid #e8e4f0;border-radius:8px;padding:14px;background:#faf9fc">
      <div style="display:flex;gap:16px">
        <!-- 左侧：选择单位 -->
        <div style="flex:1;min-width:0">
          <p style="font-size:12px;color:#666;margin:0 0 6px;font-weight:600">① 选择汇总单位</p>
          <div style="border:1px solid #e8e4f0;border-radius:6px;padding:6px;max-height:200px;overflow-y:auto;background:#fff">
            <el-tree :data="aggTreeData" :props="{ label: 'label', children: 'children' }"
              show-checkbox node-key="key" ref="aggTreeRef"
              default-expand-all>
              <template #default="{ data }">
                <span style="font-size:12px">{{ data.icon }} {{ data.label }}
                  <el-tag v-if="data.ratio" size="small" type="info" style="margin-left:4px;font-size:10px">{{ data.ratio }}%</el-tag>
                </span>
              </template>
            </el-tree>
          </div>
        </div>
        <!-- 右侧：选择数据来源和坐标 -->
        <div style="width:280px;flex-shrink:0">
          <p style="font-size:12px;color:#666;margin:0 0 6px;font-weight:600">② 数据来源</p>
          <el-radio-group v-model="aggTarget.source" size="small" style="margin-bottom:10px">
            <el-radio-button value="same">当前表格</el-radio-button>
            <el-radio-button value="report">报表</el-radio-button>
            <el-radio-button value="note">附注</el-radio-button>
          </el-radio-group>

          <div v-if="aggTarget.source === 'report'" style="margin-bottom:8px">
            <el-select v-model="aggTarget.reportTypes" size="small" style="width:100%" placeholder="选择报表（可多选）" multiple collapse-tags>
              <el-option label="全部报表" value="_all" />
              <el-option label="资产负债表" value="balance_sheet" />
              <el-option label="利润表" value="income_statement" />
              <el-option label="现金流量表" value="cash_flow_statement" />
              <el-option label="权益变动表" value="equity_statement" />
              <el-option label="现金流附表" value="cash_flow_supplement" />
              <el-option label="资产减值准备表" value="impairment_provision" />
            </el-select>
          </div>
          <div v-if="aggTarget.source === 'note'" style="margin-bottom:8px">
            <el-select v-model="aggTarget.noteSections" size="small" style="width:100%" placeholder="选择附注章节（可多选）" multiple collapse-tags filterable>
              <el-option label="全部附注" value="_all" />
              <el-option v-for="sec in aggNoteSections" :key="sec.section_id" :label="sec.title" :value="sec.section_id" />
            </el-select>
          </div>

          <p style="font-size:12px;color:#666;margin:10px 0 6px;font-weight:600">③ 坐标位置（可选）</p>
          <div style="display:flex;gap:8px">
            <div style="flex:1">
              <div style="font-size:10px;color:#999;margin-bottom:2px">行（项目名）</div>
              <el-input v-model="aggTarget.rowName" size="small" placeholder="留空=整表" clearable />
            </div>
            <div style="flex:1">
              <div style="font-size:10px;color:#999;margin-bottom:2px">列（表头名）</div>
              <el-input v-model="aggTarget.colHeader" size="small" placeholder="留空=整表" clearable />
            </div>
          </div>
          <p style="font-size:10px;color:#bbb;margin:4px 0 0">留空则汇总整张表格所有数据，填写则只汇总指定行列交叉位置</p>
        </div>
      </div>
    </div>

    <!-- 操作提示 -->
    <div style="margin-top:14px;padding:10px 14px;background:#f8f6fb;border-radius:6px;font-size:13px;color:#666;line-height:1.6">
      <b style="color:#4b2d77">💡 操作提示：</b>
      <span v-if="aggTarget.mode === 'direct'">点击"执行汇总"后，系统将自动获取直接下级企业的数据并求和，结果填充到当前选中的单元格。执行前会弹出确认框。</span>
      <span v-else>选择企业和数据来源后点击"执行汇总"，系统会弹出确认框显示汇总范围。坐标留空=汇总整表数据，填写=只汇总指定位置。</span>
    </div>

    <template #footer>
      <el-button @click="showAggregateDialog = false">取消</el-button>
      <el-button type="primary" @click="confirmAndExecuteAggregate" :loading="aggLoading">执行汇总</el-button>
    </template>
  </el-dialog>

  <!-- 附注公式管理弹窗 -->
  <el-dialog v-model="showNoteFormulaDialog" :title="`公式管理 — ${selectedNoteSection?.title || ''}`" width="85%" top="4vh" append-to-body destroy-on-close :z-index="10000">
    <div style="margin-bottom:10px;display:flex;gap:8px;align-items:center">
      <span style="font-size:12px;color:#999">共 {{ noteFormulaRules.length }} 条公式规则，点击"执行取数"从试算表自动填充数据</span>
      <span style="flex:1" />
      <el-button size="small" @click="addNoteFormulaRule">+ 新增规则</el-button>
      <el-button size="small" type="primary" @click="applyNoteFormulaRules" :loading="noteRefreshing">▶ 执行取数</el-button>
    </div>
    <el-table :data="noteFormulaRules" border size="small" max-height="55vh" style="width:100%"
      :header-cell-style="{ background: '#f0edf5', fontSize: '11px' }"
      :cell-style="{ padding: '2px 6px', fontSize: '11px' }">
      <el-table-column label="行" width="50" align="center">
        <template #default="{ row }">{{ row.row + 1 }}</template>
      </el-table-column>
      <el-table-column prop="itemName" label="项目名称" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.itemName" size="small" placeholder="科目/项目名" />
        </template>
      </el-table-column>
      <el-table-column prop="colName" label="目标列" width="120">
        <template #default="{ row }">
          <el-input v-model="row.colName" size="small" placeholder="列名" />
        </template>
      </el-table-column>
      <el-table-column prop="type" label="类型" width="100" align="center">
        <template #default="{ row }">
          <el-select v-model="row.type" size="small" style="width:100%">
            <el-option label="试算表取数" value="TB_REF" />
            <el-option label="自动求和" value="SUM" />
            <el-option label="跨表引用" value="CROSS_REF" />
            <el-option label="手动输入" value="manual" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="formula" label="公式表达式" min-width="220">
        <template #default="{ row }">
          <el-input v-model="row.formula" size="small" placeholder='如 =TB("货币资金","期末余额")' />
        </template>
      </el-table-column>
      <el-table-column prop="source" label="数据来源" width="90">
        <template #default="{ row }">
          <span style="font-size:11px;color:#999">{{ row.source }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="currentValue" label="当前值" width="100" align="right">
        <template #default="{ row }">
          <span style="font-size:11px">{{ row.currentValue || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="50" align="center">
        <template #default="{ $index }">
          <el-button size="small" link type="danger" @click="removeNoteFormulaRule($index)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div style="margin-top:10px;padding:8px;background:#f8f6fb;border-radius:6px;font-size:11px;color:#666;line-height:1.6">
      <b>公式类型说明：</b><br/>
      · <b>TB_REF</b>（试算表取数）：从项目试算表按科目名匹配，提取期末/期初余额。格式：=TB("科目名","期末余额")<br/>
      · <b>SUM</b>（自动求和）：合计行自动汇总上方明细行数据<br/>
      · <b>CROSS_REF</b>（跨表引用）：从其他附注表格或报表引用数据。格式：=REF("章节ID","行名","列名")<br/>
      · <b>manual</b>（手动输入）：不自动计算，由用户手动填写
    </div>
    <template #footer>
      <el-button @click="showNoteFormulaDialog = false">关闭</el-button>
      <el-button @click="openGlobalFormulaManager">
        打开全局公式管理器
      </el-button>
      <el-button type="primary" @click="applyNoteFormulaRules" :loading="noteRefreshing">▶ 执行取数</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useCellSelection } from '@/composables/useCellSelection'
import CellContextMenu from '@/components/common/CellContextMenu.vue'
import CommentTooltip from '@/components/common/CommentTooltip.vue'
import SelectionBar from '@/components/common/SelectionBar.vue'
import TableSearchBar from '@/components/common/TableSearchBar.vue'
import { useCellComments } from '@/composables/useCellComments'
import { useLazyEdit } from '@/composables/useLazyEdit'
import { useEditMode } from '@/composables/useEditMode'
import { useFullscreen } from '@/composables/useFullscreen'
import { useTableSearch } from '@/composables/useTableSearch'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  projectId: string
  year: number
  standard: string
  currentEntity: { code: string; name: string }
  groupTree: any[]
  consolNoteTree: any[]
}>()

const emit = defineEmits<{
  (e: 'note-node-click', data: { section_id: string; title?: string }): void
  (e: 'audit-all'): void
  (e: 'load-note-tree', forceRefresh?: boolean): void
}>()

// ─── 附注状态 ─────────────────────────────────────────────────────────────────
const selectedNoteSection = ref<any>(null)
const { isEditing: noteEditMode, isDirty: noteDirty, enterEdit: enterNoteEdit, exitEdit: exitNoteEdit, markDirty: markNoteDirty, clearDirty: clearNoteDirty } = useEditMode()
const { isFullscreen: noteFullscreen, toggleFullscreen: toggleNoteFullscreen } = useFullscreen()
const noteRefreshing = ref(false)
const noteSingleAuditLoading = ref(false)
const noteFileRef = ref<HTMLInputElement | null>(null)
const noteTableRef = ref<any>(null)
const noteSelectedRows = ref<any[]>([])
const noteBatchFileRef = ref<HTMLInputElement | null>(null)
const noteFormulaFileRef = ref<HTMLInputElement | null>(null)
const showNoteBatchDialog = ref(false)
const noteBatchLoading = ref(false)

// ─── 批注与复核持久化 ────────────────────────────────────────────────────────
const cellComments = useCellComments(() => props.projectId, () => props.year, 'consol_note')

// ─── 按需渲染编辑控件（大表格性能优化） ──────────────────────────────────────
const lazyEdit = useLazyEdit()

// ─── 附注全审 ────────────────────────────────────────────────────────────────
const showNoteAuditDialog = ref(false)
const noteAuditLoading = ref(false)
const noteAuditResults = ref<any[]>([])
const noteAuditSummary = reactive({ totalSections: 0, totalChecks: 0, passCount: 0, errorCount: 0, warnCount: 0 })

// ─── 公式编辑弹窗 ────────────────────────────────────────────────────────────
const showNoteFormulaDialog = ref(false)
const noteFormulaRules = ref<any[]>([])

// ─── 单元格选中与右键菜单（统一 composable） ──────────────────────────────
const noteCtx = useCellSelection()
noteCtx.setupTableDrag(noteTableRef, (rowIdx: number, colIdx: number) => {
  const sec = selectedNoteSection.value
  if (!sec?.editRows) return null
  const row = sec.editRows[rowIdx]
  if (!row) return null
  return row[colIdx] ?? null
})

// ─── 显示偏好（全局单位/字号） ──────────────────────────────────────────────
const displayPrefs = useDisplayPrefsStore()
/** 格式化金额（跟随全局单位设置） */
const fmt = (v: any) => displayPrefs.fmt(v)

// ─── 表格内搜索（Ctrl+F） ──────────────────────────────────────────────────
const noteSearch = useTableSearch(computed(() => []), ['row_name'])
// 兼容别名
const selectedCells = noteCtx.selectedCells
const drillDownCell = reactive({ itemName: '', colName: '', totalValue: 0 as number | null, sectionId: '', rowIdx: -1, colIdx: -1 })

// ─── 批注 ────────────────────────────────────────────────────────────────────
const showCommentDialog = ref(false)
const commentTarget = reactive({ itemName: '', colName: '', value: '', text: '' })
const editingCommentId = ref('')

// ─── 汇总 ────────────────────────────────────────────────────────────────────
const showAggregateDialog = ref(false)
const aggLoading = ref(false)
const aggTreeRef = ref<any>(null)
const aggTarget = reactive({
  itemName: '', colName: '', currentValue: '',
  mode: 'direct' as 'direct' | 'custom',
  source: 'same' as 'same' | 'report' | 'note',
  reportTypes: [] as string[],
  noteSections: [] as string[],
  rowName: '',
  colHeader: '',
})

const aggTreeData = computed(() => {
  function buildAggNode(node: any): any {
    return {
      key: node.company_code || 'root',
      label: node.company_name || node.name,
      icon: node.children?.length ? '🏢' : '🏠',
      ratio: node.shareholding,
      children: (node.children || []).map(buildAggNode),
    }
  }
  return props.groupTree.map(buildAggNode)
})

const aggNoteSections = computed(() => {
  const sections: { section_id: string; title: string }[] = []
  for (const group of props.consolNoteTree) {
    for (const child of (group.children || [])) {
      sections.push({ section_id: child.section_id || child.key, title: child.title || child.label })
    }
  }
  return sections
})

// ─── 工具函数 ────────────────────────────────────────────────────────────────
function fmtAmt(v: any): string {
  return fmt(v)
}

function onNoteSelectionChange(rows: any[]) { noteSelectedRows.value = rows }

// ─── 单元格选中与右键菜单 ──────────────────────────────────────────────────
function noteCellClassName({ rowIndex, columnIndex }: any) {
  const sec = selectedNoteSection.value
  const sheetKey = sec?.section_id || ''
  const classes: string[] = []
  const selClass = noteCtx.cellClassName({ rowIndex, columnIndex })
  if (selClass) classes.push(selClass)
  // 批注/复核标记
  const ccClass = cellComments.commentCellClass(sheetKey, rowIndex, columnIndex)
  if (ccClass) classes.push(ccClass)
  return classes.join(' ')
}

function onNoteCellClick(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  noteCtx.closeContextMenu()
  const sec = selectedNoteSection.value
  if (!sec || noteEditMode.value) return
  const colIdx = sec.headers.indexOf(column.label)
  if (colIdx < 0) return
  const rowIdx = sec.editRows.indexOf(row)
  if (rowIdx < 0) return

  noteCtx.selectCell(rowIdx, colIdx, row[colIdx], event.ctrlKey || event.metaKey, event.shiftKey)

  if (noteCtx.selectedCells.value.length === 1) {
    const c = noteCtx.selectedCells.value[0]
    drillDownCell.itemName = sec.editRows[c.row]?.[0] || ''
    drillDownCell.colName = sec.headers[c.col] || ''
    drillDownCell.totalValue = Number(c.value) || null
    drillDownCell.rowIdx = c.row
    drillDownCell.colIdx = c.col
  }
}

function onNoteCellContextMenu(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  const sec = selectedNoteSection.value
  if (!sec || noteEditMode.value) return
  const colIdx = sec.headers.indexOf(column.label)
  if (colIdx < 0) return
  const rowIdx = sec.editRows.indexOf(row)
  if (rowIdx < 0) return
  if (!noteCtx.selectedCells.value.some(c => c.row === rowIdx && c.col === colIdx)) {
    noteCtx.selectedCells.value = [{ row: rowIdx, col: colIdx, value: row[colIdx] }]
    drillDownCell.itemName = row[0] || ''
    drillDownCell.colName = sec.headers[colIdx] || ''
    drillDownCell.totalValue = Number(row[colIdx]) || null
    drillDownCell.rowIdx = rowIdx
    drillDownCell.colIdx = colIdx
  }
  noteCtx.openContextMenu(event, drillDownCell.itemName)
}

// ─── 右键菜单操作 ────────────────────────────────────────────────────────────
function onNoteCtxCopy() {
  noteCtx.closeContextMenu()
  noteCtx.copySelectedValues()
  ElMessage.success('已复制到剪贴板')
}

function onNoteCtxFormula() {
  noteCtx.closeContextMenu()
  openNoteFormula()
}

function onNoteCtxSum() {
  noteCtx.closeContextMenu()
  const sum = noteCtx.sumSelectedValues()
  ElMessage.info(`选中 ${noteCtx.selectedCells.value.length} 格，合计：${fmtAmt(sum)}`)
}

function onNoteCtxCompare() {
  noteCtx.closeContextMenu()
  if (noteCtx.selectedCells.value.length < 2) return
  const vals = noteCtx.selectedCells.value.map(c => Number(c.value) || 0)
  const diff = vals[0] - vals[1]
  const pct = vals[1] !== 0 ? ((diff / Math.abs(vals[1])) * 100).toFixed(2) : '—'
  ElMessage.info(`差异：${fmtAmt(diff)}（${pct}%）| 值1=${fmtAmt(vals[0])} 值2=${fmtAmt(vals[1])}`)
}

function drillDownFromCell() {
  noteCtx.closeContextMenu()
  if (noteCtx.selectedCells.value.length) {
    emit('note-node-click', { section_id: '__drill_down__' })
  }
}

function addCellComment() {
  noteCtx.closeContextMenu()
  if (!noteCtx.selectedCells.value.length) return
  const c = noteCtx.selectedCells.value[0]
  const sec = selectedNoteSection.value
  commentTarget.itemName = sec?.editRows?.[c.row]?.[0] || ''
  commentTarget.colName = sec?.headers?.[c.col] || ''
  commentTarget.value = c.value || ''
  // 预填已有批注
  const existing = cellComments.getComment(sec?.section_id || '', c.row, c.col)
  commentTarget.text = existing?.comment || ''
  editingCommentId.value = existing?.id || ''
  showCommentDialog.value = true
}

async function saveComment() {
  if (!commentTarget.text.trim()) { ElMessage.warning('请输入批注内容'); return }
  const c = noteCtx.selectedCells.value[0]
  const sec = selectedNoteSection.value
  if (!c || !sec) return
  const result = await cellComments.saveComment({
    sheetKey: sec.section_id,
    rowIdx: c.row,
    colIdx: c.col,
    comment: commentTarget.text.trim(),
    rowName: commentTarget.itemName,
    colName: commentTarget.colName,
  })
  if (result) {
    ElMessage.success('批注已保存')
    showCommentDialog.value = false
  } else {
    ElMessage.error('批注保存失败')
  }
}

async function deleteCurrentComment() {
  if (!editingCommentId.value) return
  const ok = await cellComments.deleteComment(editingCommentId.value)
  if (ok) {
    ElMessage.success('批注已删除')
    editingCommentId.value = ''
    showCommentDialog.value = false
  } else {
    ElMessage.error('删除失败')
  }
}

async function markCellReviewed() {
  noteCtx.closeContextMenu()
  const cells = noteCtx.selectedCells.value
  if (!cells.length) return
  const sec = selectedNoteSection.value
  if (!sec) return
  let successCount = 0
  for (const c of cells) {
    const alreadyReviewed = cellComments.isReviewed(sec.section_id, c.row, c.col)
    const result = await cellComments.toggleReview({
      sheetKey: sec.section_id,
      rowIdx: c.row,
      colIdx: c.col,
      status: alreadyReviewed ? 'pending' : 'reviewed',
      rowName: sec.editRows?.[c.row]?.[0] || '',
      colName: sec.headers?.[c.col] || '',
    })
    if (result) successCount++
  }
  if (successCount > 0) {
    const action = cellComments.isReviewed(sec.section_id, cells[0].row, cells[0].col) ? '标记' : '取消标记'
    ElMessage.success(`已${action} ${successCount} 个单元格复核状态`)
  }
}

// ─── 汇总功能 ────────────────────────────────────────────────────────────────
function openAggregateDialog() {
  noteCtx.closeContextMenu()
  if (!noteCtx.selectedCells.value.length) { ElMessage.warning('请先选中单元格'); return }
  const c = noteCtx.selectedCells.value[0]
  const sec = selectedNoteSection.value
  aggTarget.itemName = sec?.editRows?.[c.row]?.[0] || ''
  aggTarget.colName = sec?.headers?.[c.col] || ''
  aggTarget.currentValue = c.value || ''
  aggTarget.mode = 'direct'
  aggTarget.source = 'same'
  aggTarget.rowName = ''
  aggTarget.colHeader = ''
  showAggregateDialog.value = true
}

async function confirmAndExecuteAggregate() {
  let confirmMsg = ''
  if (aggTarget.mode === 'direct') {
    confirmMsg = `将汇总 "${props.currentEntity.name || '集团'}" 的直接下级企业数据，结果填充到 "${aggTarget.itemName} / ${aggTarget.colName}"。`
  } else {
    const checkedNodes = aggTreeRef.value?.getCheckedNodes() || []
    const names = checkedNodes.map((n: any) => n.label).filter((l: string) => l).join('、')
    const sourceLabel = aggTarget.source === 'same' ? '当前表格' : aggTarget.source === 'report' ? '报表' : '附注'
    confirmMsg = `将汇总以下 ${checkedNodes.length} 家企业的${sourceLabel}数据：\n${names || '未选择'}\n\n结果填充到 "${aggTarget.itemName} / ${aggTarget.colName}"。`
  }

  try {
    const { ElMessageBox } = await import('element-plus')
    await ElMessageBox.confirm(confirmMsg, '确认执行汇总', {
      type: 'info',
      confirmButtonText: '确认汇总',
      cancelButtonText: '返回修改',
    })
    await executeAggregate()
  } catch { /* cancelled */ }
}

async function executeAggregate() {
  aggLoading.value = true
  try {
    const sec = selectedNoteSection.value
    if (!sec) return
    const c = selectedCells.value[0]
    if (!c) return

    if (aggTarget.mode === 'direct') {
      const entityCode = props.currentEntity.code || ''
      const { data } = await http.post(`/api/consol-note-sections/aggregate/${props.projectId}/${props.year}`, {
        section_id: sec.section_id,
        row_idx: c.row,
        col_idx: c.col,
        company_code: entityCode,
        mode: 'direct',
        standard: props.standard,
      }, { validateStatus: (s: number) => s < 600 })
      const result = data?.data ?? data
      if (result?.value != null) {
        sec.editRows[c.row][c.col] = String(result.value)
        ElMessage.success(`已汇总 ${result.count || 0} 家直接下级，合计：${fmtAmt(result.value)}`)
      } else {
        ElMessage.info('暂无下级数据可汇总')
      }
    } else {
      const checkedNodes = aggTreeRef.value?.getCheckedNodes() || []
      if (!checkedNodes.length) { ElMessage.warning('请选择要汇总的单位'); aggLoading.value = false; return }
      const companyCodes = checkedNodes.map((n: any) => n.key).filter((k: string) => k !== 'root')
      const { data } = await http.post(`/api/consol-note-sections/aggregate/${props.projectId}/${props.year}`, {
        section_id: aggTarget.source === 'same' ? sec.section_id : (aggTarget.source === 'note' ? (aggTarget as any).noteSection : sec.section_id),
        row_idx: c.row,
        col_idx: c.col,
        company_codes: companyCodes,
        mode: 'custom',
        source: aggTarget.source,
        report_types: aggTarget.reportTypes,
        note_sections: aggTarget.noteSections,
        standard: props.standard,
      }, { validateStatus: (s: number) => s < 600 })
      const result = data?.data ?? data
      if (result?.value != null) {
        sec.editRows[c.row][c.col] = String(result.value)
        ElMessage.success(`已汇总 ${companyCodes.length} 家企业，合计：${fmtAmt(result.value)}`)
      } else {
        ElMessage.info('暂无数据可汇总')
      }
    }
    showAggregateDialog.value = false
  } catch (err: any) {
    ElMessage.error(`汇总失败：${err?.response?.data?.detail || err?.message || '未知错误'}`)
  } finally { aggLoading.value = false }
}

// ─── 附注数据操作 ────────────────────────────────────────────────────────────
function copyEntireNoteTable() {
  const sec = selectedNoteSection.value
  if (!sec?.headers?.length) { ElMessage.warning('无表格数据'); return }
  const headers = sec.headers
  const rows = (sec.editRows || []).map((r: any) => headers.map((_: string, j: number) => r[j] || ''))
  const lines = [headers.join('\t'), ...rows.map((r: string[]) => r.join('\t'))]
  const text = lines.join('\n')
  const html = `<table border="1"><tr>${headers.map((h: string) => `<th>${h}</th>`).join('')}</tr>${rows.map((r: string[]) => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</table>`
  try {
    const blob = new Blob([html], { type: 'text/html' })
    const textBlob = new Blob([text], { type: 'text/plain' })
    navigator.clipboard.write([new ClipboardItem({ 'text/html': blob, 'text/plain': textBlob })])
    ElMessage.success(`已复制 ${rows.length} 行 × ${headers.length} 列，可粘贴到 Word/Excel`)
  } catch {
    navigator.clipboard?.writeText(text)
    ElMessage.success('已复制为文本格式')
  }
}

async function refreshNoteByFormula() {
  const sec = selectedNoteSection.value
  if (!sec || !props.projectId) { ElMessage.warning('请先选择章节'); return }
  noteRefreshing.value = true
  try {
    const entityCode = props.currentEntity.code || ''
    const { data } = await http.post(`/api/consol-note-sections/refresh/${props.projectId}/${props.year}/${sec.section_id}`, {
      standard: props.standard,
      company_code: entityCode,
    }, { validateStatus: (s: number) => s < 600 })
    const result = data?.data ?? data
    if (result?.rows?.length) {
      const headers = sec.headers
      sec.editRows = result.rows.map((r: string[]) => {
        const obj: any = {}
        for (let j = 0; j < headers.length; j++) obj[j] = r[j] || ''
        return obj
      })
      ElMessage.success(`已刷新 ${result.rows.length} 行数据`)
    } else {
      ElMessage.info('暂无可计算的公式数据，请确认项目中已有对应科目的试算表数据')
    }
  } catch (err: any) {
    ElMessage.error(`公式刷新失败：${err?.response?.data?.detail || err?.message || '未知错误'}`)
  } finally { noteRefreshing.value = false }
}

function addNoteRow() {
  const sec = selectedNoteSection.value
  if (!sec?.headers) return
  const obj: any = {}
  for (let j = 0; j < sec.headers.length; j++) obj[j] = ''
  sec.editRows.push(obj)
}

async function deleteNoteRows() {
  if (!noteSelectedRows.value.length) return
  const { ElMessageBox } = await import('element-plus')
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${noteSelectedRows.value.length} 行？`, '删除确认', { type: 'warning' })
    const sec = selectedNoteSection.value
    if (!sec) return
    const toDelete = new Set(noteSelectedRows.value)
    sec.editRows = sec.editRows.filter((r: any) => !toDelete.has(r))
    noteSelectedRows.value = []
  } catch { /* cancelled */ }
}

async function saveNoteData() {
  const sec = selectedNoteSection.value
  if (!sec || !props.projectId) return
  const rows = sec.editRows.map((r: any) => sec.headers.map((_: string, j: number) => r[j] || ''))
  try {
    await http.put(
      `/api/consol-note-sections/data/${props.projectId}/${props.year}/${sec.section_id}`,
      { data: { headers: sec.headers, rows } },
      { validateStatus: (s: number) => s < 600 },
    )
    ElMessage.success('附注数据已保存')
    clearNoteDirty()
  } catch { ElMessage.error('保存失败') }
}

async function exportNoteTemplate() {
  const sec = selectedNoteSection.value
  if (!sec?.headers) return
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const ws = XLSX.utils.aoa_to_sheet([sec.headers, ...(sec.editRows || []).map(() => sec.headers.map(() => ''))])
  ws['!cols'] = sec.headers.map(() => ({ wch: 18 }))
  XLSX.utils.book_append_sheet(wb, ws, '模板')
  XLSX.writeFile(wb, `${sec.title || '附注'}_模板.xlsx`)
  ElMessage.success('模板已导出')
}

async function exportNoteData() {
  const sec = selectedNoteSection.value
  if (!sec?.headers) return
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const dataRows = sec.editRows.map((r: any) => sec.headers.map((_: string, j: number) => r[j] || ''))
  const ws = XLSX.utils.aoa_to_sheet([sec.headers, ...dataRows])
  ws['!cols'] = sec.headers.map(() => ({ wch: 18 }))
  XLSX.utils.book_append_sheet(wb, ws, '数据')
  XLSX.writeFile(wb, `${sec.title || '附注'}_数据.xlsx`)
  ElMessage.success('数据已导出')
}

async function onNoteFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const sec = selectedNoteSection.value
  if (!sec?.headers) return
  try {
    const XLSX = await import('xlsx')
    const wb = XLSX.read(await file.arrayBuffer(), { type: 'array' })
    const ws = wb.Sheets[wb.SheetNames[0]]
    const json: any[][] = XLSX.utils.sheet_to_json(ws, { header: 1 })
    let startRow = 0
    if (json.length > 0) {
      const firstRow = json[0].map((c: any) => String(c || '').trim())
      if (firstRow.some((c: string) => sec.headers.includes(c))) startRow = 1
    }
    const imported: any[] = []
    for (let i = startRow; i < json.length; i++) {
      const r = json[i]
      if (!r || !r.length) continue
      const obj: any = {}
      for (let j = 0; j < sec.headers.length; j++) obj[j] = r[j] != null ? String(r[j]) : ''
      imported.push(obj)
    }
    if (imported.length) {
      sec.editRows.push(...imported)
      ElMessage.success(`已导入 ${imported.length} 行`)
    } else {
      ElMessage.warning('未解析到有效数据')
    }
  } catch (err: any) { ElMessage.error('导入失败：' + (err.message || '')) }
  finally { if (noteFileRef.value) noteFileRef.value.value = '' }
}

// ─── 批量导入导出 ─────────────────────────────────────────────────────────────
function uniqueSheetName(usedNames: Set<string>, rawName: string, sectionId: string): string {
  const prefix = sectionId.replace(/^五-/, '').replace(/-/g, '.')
  const name = `${prefix} ${rawName}`.substring(0, 31)
  usedNames.add(name)
  return name
}

async function batchExportAllData() {
  noteBatchLoading.value = true
  try {
    const XLSX = await import('xlsx')
    const wb = XLSX.utils.book_new()
    const usedNames = new Set<string>()
    const { data } = await http.get(`/api/consol-note-sections/${props.standard}`, {
      validateStatus: (s: number) => s < 600,
    })
    const groups = Array.isArray(data) ? data : (data?.data ?? [])
    let sheetCount = 0
    for (const g of groups) {
      for (const c of (g.children || [])) {
        const { data: detail } = await http.get(`/api/consol-note-sections/${props.standard}/${c.section_id}`, {
          validateStatus: (s: number) => s < 600,
        })
        const sec = detail?.data ?? detail
        if (!sec?.headers?.length) continue
        const rows = sec.rows || []
        const ws = XLSX.utils.aoa_to_sheet([sec.headers, ...rows])
        ws['!cols'] = sec.headers.map(() => ({ wch: 16 }))
        const name = uniqueSheetName(usedNames, sec.title || c.title || `表${sheetCount + 1}`, c.section_id)
        XLSX.utils.book_append_sheet(wb, ws, name)
        sheetCount++
      }
    }
    XLSX.writeFile(wb, `合并附注_全部数据_${props.standard}.xlsx`)
    ElMessage.success(`已导出 ${sheetCount} 个附注表格`)
  } catch (e: any) { ElMessage.error('导出失败：' + (e?.message || '')) }
  finally { noteBatchLoading.value = false; showNoteBatchDialog.value = false }
}

async function batchExportAllTemplates() {
  noteBatchLoading.value = true
  try {
    const XLSX = await import('xlsx')
    const wb = XLSX.utils.book_new()
    const usedNames = new Set<string>()
    const { data } = await http.get(`/api/consol-note-sections/${props.standard}`, {
      validateStatus: (s: number) => s < 600,
    })
    const groups = Array.isArray(data) ? data : (data?.data ?? [])
    let sheetCount = 0
    for (const g of groups) {
      for (const c of (g.children || [])) {
        const { data: detail } = await http.get(`/api/consol-note-sections/${props.standard}/${c.section_id}`, {
          validateStatus: (s: number) => s < 600,
        })
        const sec = detail?.data ?? detail
        if (!sec?.headers?.length) continue
        const ws = XLSX.utils.aoa_to_sheet([sec.headers])
        ws['!cols'] = sec.headers.map(() => ({ wch: 16 }))
        const name = uniqueSheetName(usedNames, sec.title || c.title || `表${sheetCount + 1}`, c.section_id)
        XLSX.utils.book_append_sheet(wb, ws, name)
        sheetCount++
      }
    }
    XLSX.writeFile(wb, `合并附注_模板_${props.standard}.xlsx`)
    ElMessage.success(`已导出 ${sheetCount} 个附注模板`)
  } catch (e: any) { ElMessage.error('导出失败：' + (e?.message || '')) }
  finally { noteBatchLoading.value = false; showNoteBatchDialog.value = false }
}

async function onNoteBatchImport(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file || !props.projectId) return
  noteBatchLoading.value = true
  try {
    const XLSX = await import('xlsx')
    const wb = XLSX.read(await file.arrayBuffer(), { type: 'array' })
    let matched = 0
    const { data } = await http.get(`/api/consol-note-sections/${props.standard}`, {
      validateStatus: (s: number) => s < 600,
    })
    const groups = Array.isArray(data) ? data : (data?.data ?? [])
    const sectionMap: Record<string, string> = {}
    for (const g of groups) {
      for (const c of (g.children || [])) {
        sectionMap[c.title] = c.section_id
      }
    }
    for (const sheetName of wb.SheetNames) {
      const sectionId = sectionMap[sheetName]
      if (!sectionId) continue
      const ws = wb.Sheets[sheetName]
      const json: any[][] = XLSX.utils.sheet_to_json(ws, { header: 1 })
      if (json.length < 2) continue
      const headers = json[0].map((c: any) => String(c || ''))
      const rows = json.slice(1).filter((r: any[]) => r.some(c => c != null && c !== '')).map((r: any[]) => r.map(c => String(c ?? '')))
      await http.put(
        `/api/consol-note-sections/data/${props.projectId}/${props.year}/${sectionId}`,
        { data: { headers, rows } },
        { validateStatus: (s: number) => s < 600 },
      )
      matched++
    }
    ElMessage.success(`已导入 ${matched} 个附注表格（共 ${wb.SheetNames.length} 个 Sheet）`)
  } catch (e: any) { ElMessage.error('导入失败：' + (e?.message || '')) }
  finally {
    noteBatchLoading.value = false
    showNoteBatchDialog.value = false
    if (noteBatchFileRef.value) noteBatchFileRef.value.value = ''
  }
}

// ─── 公式管理 ────────────────────────────────────────────────────────────────
function openGlobalFormulaManager() {
  window.dispatchEvent(new CustomEvent('gt-open-formula-manager', { detail: { nodeKey: 'consol_note' } }))
  showNoteFormulaDialog.value = false
}

function openNoteFormula() {
  const sec = selectedNoteSection.value
  if (!sec) { ElMessage.warning('请先选择章节'); return }
  const rules: any[] = []
  const headers = sec.headers || []
  for (let ri = 0; ri < (sec.editRows || []).length; ri++) {
    const row = sec.editRows[ri]
    const itemName = row[0] || `行${ri + 1}`
    const isTotal = String(itemName).includes('合计') || String(itemName).includes('小计')
    for (let ci = 1; ci < headers.length; ci++) {
      const h = headers[ci]
      const hClean = h.replace(/\s/g, '')
      let formulaType = 'manual'
      let formula = ''
      let source = ''
      if (isTotal) {
        formulaType = 'SUM'
        formula = `=SUM(${headers[ci]}列明细行)`
        source = '自动求和'
      } else if (hClean.includes('期末') || hClean.includes('本期') || hClean.includes('账面余额')) {
        formulaType = 'TB_REF'
        formula = `=TB("${itemName}","期末余额")`
        source = '试算表'
      } else if (hClean.includes('期初') || hClean.includes('年初')) {
        formulaType = 'TB_REF'
        formula = `=TB("${itemName}","期初余额")`
        source = '试算表'
      }
      if (formulaType !== 'manual') {
        rules.push({
          row: ri, col: ci, itemName, colName: h,
          type: formulaType, formula, source,
          currentValue: row[ci] || '',
        })
      }
    }
  }
  noteFormulaRules.value = rules
  showNoteFormulaDialog.value = true
}

async function applyNoteFormulaRules() {
  const sec = selectedNoteSection.value
  if (!sec || !props.projectId) return
  await refreshNoteByFormula()
  showNoteFormulaDialog.value = false
}

function addNoteFormulaRule() {
  noteFormulaRules.value.push({
    row: 0, col: 1, itemName: '', colName: '',
    type: 'TB_REF', formula: '=TB("科目名","期末余额")', source: '试算表',
    currentValue: '',
  })
}

function removeNoteFormulaRule(idx: number) {
  noteFormulaRules.value.splice(idx, 1)
}

async function exportNoteFormulas() {
  noteBatchLoading.value = true
  try {
    const XLSX = await import('xlsx')
    const wb = XLSX.utils.book_new()
    const headers = ['章节ID', '章节标题', '行号', '列号', '公式类型', '公式表达式', '数据来源', '说明']
    const { data } = await http.get(`/api/consol-note-sections/${props.standard}`, {
      validateStatus: (s: number) => s < 600,
    })
    const groups = Array.isArray(data) ? data : (data?.data ?? [])
    const rows: string[][] = []
    for (const g of groups) {
      for (const c of (g.children || [])) {
        rows.push([c.section_id, c.title, '合计行', '所有数值列', 'SUM', '=SUM(明细行)', '自动计算', '合计行自动求和'])
        rows.push([c.section_id, c.title, '所有行', '期末列', 'TB_REF', `=TB(科目名,期末余额)`, '试算表', '从试算表提取期末余额'])
        rows.push([c.section_id, c.title, '所有行', '期初列', 'TB_REF', `=TB(科目名,期初余额)`, '试算表', '从试算表提取期初余额'])
      }
    }
    const ws = XLSX.utils.aoa_to_sheet([headers, ...rows])
    ws['!cols'] = headers.map((_, i) => ({ wch: i < 2 ? 20 : 14 }))
    XLSX.utils.book_append_sheet(wb, ws, '公式规则')
    XLSX.writeFile(wb, `合并附注_公式模板_${props.standard}.xlsx`)
    ElMessage.success(`已导出公式模板`)
  } catch (e: any) { ElMessage.error('导出失败：' + (e?.message || '')) }
  finally { noteBatchLoading.value = false }
}

async function onNoteFormulaImport(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  noteBatchLoading.value = true
  try {
    if (file.name.endsWith('.json')) {
      const text = await file.text()
      const formulas = JSON.parse(text)
      ElMessage.success(`已导入 ${Array.isArray(formulas) ? formulas.length : 0} 条公式规则（需后端配合存储）`)
    } else {
      const XLSX = await import('xlsx')
      const wb = XLSX.read(await file.arrayBuffer(), { type: 'array' })
      const ws = wb.Sheets[wb.SheetNames[0]]
      const json: any[][] = XLSX.utils.sheet_to_json(ws, { header: 1 })
      const ruleCount = Math.max(0, json.length - 1)
      ElMessage.success(`已解析 ${ruleCount} 条公式规则（需后端配合存储）`)
    }
  } catch (e: any) { ElMessage.error('导入失败：' + (e?.message || '')) }
  finally {
    noteBatchLoading.value = false
    if (noteFormulaFileRef.value) noteFormulaFileRef.value.value = ''
  }
}

async function applyAllNoteFormulas() {
  noteBatchLoading.value = true
  try {
    const entityCode = props.currentEntity.code || ''
    const { data } = await http.post(`/api/consol-note-sections/apply-formulas/${props.projectId}/${props.year}`, {
      standard: props.standard,
      company_code: entityCode,
    }, { validateStatus: (s: number) => s < 600 })
    const result = data?.data ?? data
    const updated = result?.updated_sections || 0
    ElMessage.success(`已对 ${updated} 个附注表格执行公式取数计算`)
    if (selectedNoteSection.value) {
      onNoteNodeClick({ section_id: selectedNoteSection.value.section_id })
    }
  } catch (err: any) {
    ElMessage.error(`一键取数计算失败：${err?.response?.data?.detail || err?.message || '未知错误'}`)
  } finally { noteBatchLoading.value = false; showNoteBatchDialog.value = false }
}

// ─── 审核 ────────────────────────────────────────────────────────────────────
async function onNoteAuditAll(_e?: Event) {
  showNoteAuditDialog.value = true
  noteAuditLoading.value = true
  noteAuditResults.value = []
  try {
    const entityCode = props.currentEntity.code || ''
    const { data } = await http.post(`/api/consol-note-sections/audit-all/${props.projectId}/${props.year}`, {
      standard: props.standard,
      company_code: entityCode,
    }, { validateStatus: (s: number) => s < 600 })
    const result = data?.data ?? data
    noteAuditResults.value = Array.isArray(result?.results) ? result.results : []
    noteAuditSummary.totalSections = result?.total_sections || 0
    noteAuditSummary.totalChecks = noteAuditResults.value.length
    noteAuditSummary.passCount = noteAuditResults.value.filter((r: any) => r.level === 'pass').length
    noteAuditSummary.errorCount = noteAuditResults.value.filter((r: any) => r.level === 'error').length
    noteAuditSummary.warnCount = noteAuditResults.value.filter((r: any) => r.level === 'warn').length
  } catch (err: any) {
    ElMessage.error(`全审失败：${err?.response?.data?.detail || err?.message || '未知错误'}`)
  } finally { noteAuditLoading.value = false }
}

function auditRowClass({ row }: { row: any }) {
  if (row.level === 'error') return 'gt-audit-row-error'
  if (row.level === 'warn') return 'gt-audit-row-warn'
  return ''
}

async function exportAuditResults() {
  if (!noteAuditResults.value.length) return
  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const headers = ['章节', '审核规则', '级别', '预期值', '实际值', '差异', '说明']
  const rows = noteAuditResults.value.map((r: any) => [
    r.section_title, r.rule_name,
    r.level === 'error' ? '异常' : r.level === 'warn' ? '警告' : '通过',
    r.expected, r.actual, r.difference, r.message,
  ])
  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows])
  ws['!cols'] = [{ wch: 20 }, { wch: 30 }, { wch: 8 }, { wch: 14 }, { wch: 14 }, { wch: 14 }, { wch: 30 }]
  XLSX.utils.book_append_sheet(wb, ws, '审核结果')
  XLSX.writeFile(wb, `合并附注_审核报告_${props.standard}.xlsx`)
  ElMessage.success('审核报告已导出')
}

async function auditCurrentNote() {
  const sec = selectedNoteSection.value
  if (!sec || !props.projectId) { ElMessage.warning('请先选择章节'); return }
  noteSingleAuditLoading.value = true
  try {
    const entityCode = props.currentEntity.code || ''
    const currentRows = sec.editRows.map((r: any) => sec.headers.map((_: string, j: number) => r[j] || ''))
    const { data } = await http.post(`/api/consol-note-sections/audit/${props.projectId}/${props.year}/${sec.section_id}`, {
      standard: props.standard,
      company_code: entityCode,
      headers: sec.headers,
      rows: currentRows,
    }, { validateStatus: (s: number) => s < 600 })
    const result = data?.data ?? data
    noteAuditResults.value = Array.isArray(result?.results) ? result.results : []
    noteAuditSummary.totalSections = 1
    noteAuditSummary.totalChecks = noteAuditResults.value.length
    noteAuditSummary.passCount = noteAuditResults.value.filter((r: any) => r.level === 'pass').length
    noteAuditSummary.errorCount = noteAuditResults.value.filter((r: any) => r.level === 'error').length
    noteAuditSummary.warnCount = noteAuditResults.value.filter((r: any) => r.level === 'warn').length
    showNoteAuditDialog.value = true
  } catch (err: any) {
    ElMessage.error(`单表审核失败：${err?.response?.data?.detail || err?.message || '未知错误'}`)
  } finally { noteSingleAuditLoading.value = false }
}

// ─── 章节加载 ────────────────────────────────────────────────────────────────
function onNoteNodeClick(data: { section_id: string; title?: string }) {
  if (!data.section_id) return
  noteSelectedRows.value = []
  selectedCells.value = []
  http.get(`/api/consol-note-sections/${props.standard}/${data.section_id}`, {
    validateStatus: (s: number) => s < 600,
  }).then(async ({ data: detail }) => {
    const sec = detail?.data ?? detail
    if (sec && !sec.error) {
      const headers = sec.headers || []
      let rows = sec.rows || []

      // 尝试加载用户已保存的数据覆盖模板
      try {
        const { data: saved } = await http.get(
          `/api/consol-note-sections/data/${props.projectId}/${props.year}/${data.section_id}`,
          { validateStatus: (s: number) => s < 600 }
        )
        const savedData = saved?.data ?? saved
        if (savedData?.data?.rows?.length) {
          rows = savedData.data.rows
        }
      } catch { /* 无已保存数据，用模板默认 */ }

      const editRows = rows.map((r: string[]) => {
        const obj: any = {}
        for (let j = 0; j < headers.length; j++) obj[j] = (Array.isArray(r) ? r[j] : '') || ''
        return obj
      })
      while (editRows.length < 5) {
        const obj: any = {}
        for (let j = 0; j < headers.length; j++) obj[j] = ''
        editRows.push(obj)
      }
      selectedNoteSection.value = {
        section_id: sec.section_id,
        title: sec.title,
        parent_section: sec.parent_section,
        headers,
        editRows,
      }
      // 加载该章节的批注和复核标记
      cellComments.loadComments(sec.section_id)
    }
  }).catch(() => {})
}

function switchToFourCol() {
  window.dispatchEvent(new CustomEvent('gt-switch-four-col', { detail: { tab: 'notes' } }))
}

// ─── 生命周期 ────────────────────────────────────────────────────────────────
function onDocClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.closest('.gt-ucell-context-menu')) return
  noteCtx.closeContextMenu()
}

// Listen for catalog select events to load note sections
function onConsolCatalogSelect(e: Event) {
  const data = (e as CustomEvent).detail
  if (!data) return
  if (data.type === 'note' && data.sectionId) {
    onNoteNodeClick({ section_id: data.sectionId, title: data.title })
  }
}

// Listen for tree aggregate events
function onTreeAggregate(e: Event) {
  const detail = (e as CustomEvent).detail
  if (!detail) return
  const sec = selectedNoteSection.value
  if (sec) {
    aggTarget.itemName = sec.editRows?.[0]?.[0] || ''
    aggTarget.colName = sec.headers?.[1] || ''
    aggTarget.currentValue = ''
  } else {
    aggTarget.itemName = '（请先选择附注表格）'
    aggTarget.colName = ''
    aggTarget.currentValue = ''
  }
  aggTarget.mode = detail.mode || 'direct'
  aggTarget.source = 'same'
  aggTarget.rowName = ''
  aggTarget.colHeader = ''
  aggTarget.reportTypes = []
  aggTarget.noteSections = []
  showAggregateDialog.value = true
}

// Listen for audit-all events
function onNoteAuditAllEvent(e: Event) {
  onNoteAuditAll(e)
}

onMounted(() => {
  document.addEventListener('click', onDocClick)
  window.addEventListener('consol-catalog-select', onConsolCatalogSelect)
  window.addEventListener('consol-tree-aggregate', onTreeAggregate)
  window.addEventListener('consol-note-audit-all', onNoteAuditAllEvent)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
  window.removeEventListener('consol-catalog-select', onConsolCatalogSelect)
  window.removeEventListener('consol-tree-aggregate', onTreeAggregate)
  window.removeEventListener('consol-note-audit-all', onNoteAuditAllEvent)
})

// Expose for parent to call
defineExpose({
  onNoteNodeClick,
  selectedNoteSection,
  noteSelectedRows,
  selectedCells,
  drillDownCell,
  onNoteAuditAll,
})
</script>

<style>
/* 全局：确保 MessageBox 和 Select 下拉在所有弹窗之上 */
.el-overlay.is-message-box { z-index: 10010 !important; }
.el-select__popper { z-index: 10005 !important; }
</style>

<style scoped>
/* ── 合并附注布局 ── */
.gt-note-layout { display: flex; gap: 0; min-height: 400px; }
.gt-note-content { flex: 1; min-width: 0; overflow: auto; padding: 0; }
.gt-note-detail { height: 100%; display: flex; flex-direction: column; }
.gt-note-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.gt-note-section-title { margin: 0; font-size: 14px; font-weight: 600; color: #333; white-space: nowrap; }
.gt-note-actions { display: flex; gap: 4px; flex-wrap: wrap; }
.gt-note-table-wrap { flex: 1; min-height: 0; }
.gt-note-table-footer {
  display: flex; align-items: center; gap: 8px; padding: 6px 0; border-top: 1px solid #e8e4f0; margin-top: 4px;
}

/* 附注空状态引导 */
.gt-note-empty-guide {
  display: flex; flex-direction: column; align-items: center;
  padding: 24px 20px 16px; gap: 16px;
}
.gt-note-empty-hero { text-align: center; }
.gt-note-empty-hero p { margin: 0 0 12px; font-size: 13px; color: #999; }
.gt-note-empty-actions { display: flex; gap: 8px; justify-content: center; }
.gt-note-empty-steps {
  display: flex; gap: 12px; width: 100%;
}
.gt-note-step {
  flex: 1; min-width: 0;
  display: flex; gap: 8px; align-items: flex-start;
  padding: 12px; background: #f8f6fb; border-radius: 8px; border: 1px solid #ebe7f2;
}
.gt-note-step-icon {
  font-size: 16px; font-weight: 700; color: #4b2d77; flex-shrink: 0; line-height: 1;
}
.gt-note-step-text { font-size: 12px; color: #666; line-height: 1.6; }
.gt-note-step-text b { color: #333; font-size: 12px; display: block; margin-bottom: 2px; }
.gt-note-step-text p { margin: 0; }
.gt-note-empty-info {
  font-size: 11px; color: #bbb; text-align: center;
}

/* 审核结果行样式 */
:deep(.gt-audit-row-error td) { background: #fef0f0 !important; }
:deep(.gt-audit-row-warn td) { background: #fdf6ec !important; }

.gt-note-cell-text {
  display: block; padding: 2px 2px; font-size: 13px; min-height: 20px;
  user-select: text; cursor: pointer; white-space: nowrap;
}
.gt-note-cell-editable {
  cursor: text; border-bottom: 1px dashed var(--gt-color-border, #e5e5ea);
  border-radius: 2px; transition: background 0.1s;
}
.gt-note-cell-editable:hover {
  background: var(--gt-color-primary-bg, #f4f0fa);
}

/* 批注弹窗 */
:deep(.gt-comment-dialog .el-dialog__header) {
  background: linear-gradient(135deg, #4b2d77, #7c5caa); padding: 14px 20px;
  border-radius: 8px 8px 0 0;
}
:deep(.gt-comment-dialog .el-dialog__title) { color: #fff; font-size: 15px; }
:deep(.gt-comment-dialog .el-dialog__headerbtn .el-dialog__close) { color: rgba(255,255,255,0.8); }
:deep(.gt-comment-dialog .el-dialog__body) { padding: 16px 20px; }
.gt-comment-info {
  display: flex; gap: 0; margin-bottom: 14px;
  background: #f8f6fb; border-radius: 6px; overflow: hidden;
}
.gt-comment-info-item {
  flex: 1; padding: 10px 14px; border-right: 1px solid #ebe7f2;
  display: flex; flex-direction: column; gap: 2px;
}
.gt-comment-info-item:last-child { border-right: none; }
.gt-comment-info-label { font-size: 10px; color: #999; text-transform: uppercase; letter-spacing: 0.5px; }
.gt-comment-info-value { font-size: 13px; font-weight: 600; color: #333; }
.gt-comment-info-value--primary { color: #4b2d77; }
:deep(.gt-comment-textarea .el-textarea__inner) {
  border: none; border-bottom: 1.5px solid #e8e4f0; border-radius: 0;
  font-size: 13px; line-height: 1.6; padding: 10px 4px; resize: none;
}
:deep(.gt-comment-textarea .el-textarea__inner:focus) {
  border-color: #4b2d77; box-shadow: none;
}

/* 紧凑行高 */
.gt-note-compact-table :deep(.el-table__row td) { height: 32px; }
.gt-note-compact-table :deep(.el-table__header th) { height: 34px; }
.gt-note-compact-table :deep(.el-input__inner) { height: 28px; font-size: 13px; }
</style>
