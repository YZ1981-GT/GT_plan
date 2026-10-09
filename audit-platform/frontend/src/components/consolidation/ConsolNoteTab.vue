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
            <el-tooltip content="按合并附注公式把合并数填入本章节；手工单元格保留原值" placement="bottom">
              <el-button size="small" type="primary" data-testid="consol-note-fill" @click="fillCurrentByFormula" :loading="formulaFilling">ƒx 按公式填入</el-button>
            </el-tooltip>
            <el-tooltip content="查看本章节有公式单元格的个别数汇总、调整、抵销、合并数及各下级贡献" placement="bottom">
              <el-button size="small" data-testid="consol-note-breakdown" @click="openNoteBreakdown()">📊 查看差额</el-button>
            </el-tooltip>
            <!-- B.1.13: 重新汇总按钮 -->
            <el-tooltip content="从子公司单体附注重新汇总" placement="bottom">
              <el-button size="small" @click="handleReaggregate" :loading="reaggregating">🔄 重新汇总</el-button>
            </el-tooltip>
            <el-tooltip content="审核当前表格公式一致性" placement="bottom">
              <el-button size="small" @click="auditCurrentNote" :loading="noteSingleAuditLoading">✅</el-button>
            </el-tooltip>
            <el-tooltip content="公式管理（编辑取数规则）" placement="bottom">
              <el-button size="small" @click="openNoteFormula">ƒx</el-button>
            </el-tooltip>
          </div>
        </div>

        <!-- 跨表勾稽校验结果 -->
        <div v-if="checkRulesResults.length" style="margin-bottom:8px">
          <el-alert
            v-for="cr in checkRulesResults"
            :key="cr.check_id"
            :type="cr.status === 'pass' ? 'success' : cr.status === 'fail' ? 'error' : 'warning'"
            :closable="false"
            show-icon
            style="margin-bottom:4px"
          >
            <template #title>
              <span>{{ cr.check_id }}：{{ cr.description }}</span>
              <span v-if="cr.status === 'fail'" style="margin-left:8px;color:#f56c6c">
                差异 {{ cr.diff }}（期望 {{ cr.expected }}，实际 {{ cr.actual }}）
              </span>
              <span v-else-if="cr.status === 'skipped'" style="margin-left:8px;color:#e6a23c">
                {{ cr.reason }}
              </span>
            </template>
          </el-alert>
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
            :row-class-name="noteRowClassName"
            @selection-change="onNoteSelectionChange"
            @cell-click="onNoteCellClick"
            @cell-contextmenu="onNoteCellContextMenu">
            <el-table-column v-if="noteEditMode" type="selection" width="36" />
            <!-- 多行合并表头：有 parsedMultiHeader 时用嵌套 el-table-column -->
            <template v-if="parsedMultiHeader">
              <template v-for="(col, ci) in parsedMultiHeader" :key="'mh-' + ci">
                <!-- 叶子列（独立列，无 children） -->
                <el-table-column v-if="!col.children" :label="col.label" :min-width="col.colIndex === 0 ? 200 : 130">
                  <template #default="{ row, $index }">
                    <el-input v-if="noteEditMode && lazyEdit.isEditing($index, col.colIndex)" v-model="row[col.colIndex]" size="small" :placeholder="col.label"
                      :class="{ 'gt-note-cell-manual': isManual(row, col.colIndex) }"
                      :style="{ textAlign: col.colIndex === 0 ? 'left' : 'right' }"
                      @blur="lazyEdit.stopEdit()" @input="onNoteCellInput(row, col.colIndex)" autofocus />
                    <CommentTooltip v-else-if="col.colIndex > 0" :comment="cellComments.getComment(selectedNoteSection?.section_id || 'default', $index, col.colIndex)">
                    <span class="gt-note-cell-text"
                      :class="{ 'gt-note-cell-editable': noteEditMode, 'gt-note-cell-manual': isManual(row, col.colIndex) }"
                      :title="isManual(row, col.colIndex) ? '手工单元格：按公式填入时保留' : ''"
                      :style="{ textAlign: 'right' }"
                      @click="noteEditMode && lazyEdit.startEdit($index, col.colIndex)">{{ row[col.colIndex] || '-' }}</span>
                    </CommentTooltip>
                    <span v-else class="gt-note-cell-text"
                      :class="{ 'gt-note-cell-editable': noteEditMode }"
                      :style="{ textAlign: 'left' }"
                      @click="noteEditMode && lazyEdit.startEdit($index, col.colIndex)">{{ row[col.colIndex] || '-' }}</span>
                  </template>
                </el-table-column>
                <!-- 分组列（有 children，el-table-column 嵌套自动生成合并表头） -->
                <el-table-column v-else :label="col.label" align="center">
                  <template v-for="(child, chi) in col.children" :key="'mhc-' + ci + '-' + chi">
                    <!-- 二级叶子 -->
                    <el-table-column v-if="!child.children" :label="child.label" :min-width="130">
                      <template #default="{ row, $index }">
                        <el-input v-if="noteEditMode && lazyEdit.isEditing($index, child.colIndex)" v-model="row[child.colIndex]" size="small" :placeholder="child.label"
                          :class="{ 'gt-note-cell-manual': isManual(row, child.colIndex) }"
                          style="text-align:right"
                          @blur="lazyEdit.stopEdit()" @input="onNoteCellInput(row, child.colIndex)" autofocus />
                        <CommentTooltip v-else :comment="cellComments.getComment(selectedNoteSection?.section_id || 'default', $index, child.colIndex)">
                        <span class="gt-note-cell-text"
                          :class="{ 'gt-note-cell-editable': noteEditMode, 'gt-note-cell-manual': isManual(row, child.colIndex) }"
                          :title="isManual(row, child.colIndex) ? '手工单元格：按公式填入时保留' : ''"
                          style="text-align:right"
                          @click="noteEditMode && lazyEdit.startEdit($index, child.colIndex)">{{ row[child.colIndex] || '-' }}</span>
                        </CommentTooltip>
                      </template>
                    </el-table-column>
                    <!-- 三级嵌套（3 行表头场景） -->
                    <el-table-column v-else :label="child.label" align="center">
                      <el-table-column v-for="(leaf, li) in child.children" :key="'mhl-' + ci + '-' + chi + '-' + li"
                        :label="leaf.label" :min-width="130">
                        <template #default="{ row, $index }">
                          <el-input v-if="noteEditMode && lazyEdit.isEditing($index, leaf.colIndex)" v-model="row[leaf.colIndex]" size="small" :placeholder="leaf.label"
                            :class="{ 'gt-note-cell-manual': isManual(row, leaf.colIndex) }"
                            style="text-align:right"
                            @blur="lazyEdit.stopEdit()" @input="onNoteCellInput(row, leaf.colIndex)" autofocus />
                          <CommentTooltip v-else :comment="cellComments.getComment(selectedNoteSection?.section_id || 'default', $index, leaf.colIndex)">
                          <span class="gt-note-cell-text"
                            :class="{ 'gt-note-cell-editable': noteEditMode, 'gt-note-cell-manual': isManual(row, leaf.colIndex) }"
                            :title="isManual(row, leaf.colIndex) ? '手工单元格：按公式填入时保留' : ''"
                            style="text-align:right"
                            @click="noteEditMode && lazyEdit.startEdit($index, leaf.colIndex)">{{ row[leaf.colIndex] || '-' }}</span>
                          </CommentTooltip>
                        </template>
                      </el-table-column>
                    </el-table-column>
                  </template>
                </el-table-column>
              </template>
            </template>
            <!-- 扁平表头（无 multi_header 的章节，走原逻辑） -->
            <template v-else>
            <el-table-column v-for="(h, hi) in selectedNoteSection.headers" :key="hi" :label="h" :min-width="hi === 0 ? 200 : 130">
              <template #default="{ row, $index }">
                <el-input v-if="noteEditMode && lazyEdit.isEditing($index, hi)" v-model="row[hi]" size="small" :placeholder="h"
                  :class="{ 'gt-note-cell-manual': isManual(row, hi) }"
                  :style="{ textAlign: hi === 0 ? 'left' : 'right' }"
                  @blur="lazyEdit.stopEdit()" @input="onNoteCellInput(row, hi)" autofocus />
                <CommentTooltip v-else-if="hi > 0" :comment="cellComments.getComment(selectedNoteSection?.section_id || 'default', $index, hi)">
                <span class="gt-note-cell-text"
                  :class="{ 'gt-note-cell-editable': noteEditMode, 'gt-note-cell-manual': isManual(row, hi) }"
                  :title="isManual(row, hi) ? '手工单元格：按公式填入时保留' : ''"
                  :style="{ textAlign: 'right' }"
                  @click="noteEditMode && lazyEdit.startEdit($index, hi)">{{ row[hi] || '-' }}</span>
                </CommentTooltip>
                <span v-else class="gt-note-cell-text"
                  :class="{ 'gt-note-cell-editable': noteEditMode }"
                  :style="{ textAlign: 'left' }"
                  @click="noteEditMode && lazyEdit.startEdit($index, hi)">{{ row[hi] || '-' }}</span>
              </template>
            </el-table-column>
            </template>
          </el-table>

          <div class="gt-note-table-footer">
            <template v-if="noteEditMode">
              <el-button size="small" @click="addNoteRow">+ 新增行</el-button>
              <el-button size="small" type="danger" :disabled="!noteSelectedRows.length" @click="deleteNoteRows">
                删除{{ noteSelectedRows.length ? `(${noteSelectedRows.length})` : '' }}
              </el-button>
            </template>
            <span v-else style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary)">💡 查看模式下可选中复制，粘贴到 Word/Excel 保持格式</span>
            <span style="flex:1" />
            <span style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary)">共 {{ selectedNoteSection.editRows?.length || 0 }} 行</span>
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
            <el-button size="small" type="warning" class="gt-four-col-pulse" @click="switchToFourCol">
              👉 点击此处切换四栏视图显示附注树 👈
            </el-button>
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
            <el-tooltip content="按公式填入" placement="bottom">
              <el-button size="small" type="primary" @click="fillCurrentByFormula" :loading="formulaFilling">ƒx 按公式填入</el-button>
            </el-tooltip>
            <el-tooltip content="查看差额" placement="bottom">
              <el-button size="small" @click="openNoteBreakdown()">📊 查看差额</el-button>
            </el-tooltip>
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
            @selection-change="onNoteSelectionChange"
            :row-class-name="noteRowClassName">
            <el-table-column v-if="noteEditMode" type="selection" width="36" />
            <!-- 全屏模式：多行合并表头 -->
            <template v-if="parsedMultiHeader">
              <template v-for="(col, ci) in parsedMultiHeader" :key="'fs-mh-' + ci">
                <el-table-column v-if="!col.children" :label="col.label" :min-width="col.colIndex === 0 ? 200 : 130">
                  <template #default="{ row, $index }">
                    <el-input v-if="noteEditMode && lazyEdit.isEditing($index + 10000, col.colIndex)" v-model="row[col.colIndex]" size="small" :placeholder="col.label"
                      :class="{ 'gt-note-cell-manual': isManual(row, col.colIndex) }"
                      :style="{ textAlign: col.colIndex === 0 ? 'left' : 'right' }"
                      @blur="lazyEdit.stopEdit()" @input="onNoteCellInput(row, col.colIndex)" autofocus />
                    <span v-else class="gt-note-cell-text"
                      :class="{ 'gt-note-cell-editable': noteEditMode, 'gt-note-cell-manual': isManual(row, col.colIndex) }"
                      :title="isManual(row, col.colIndex) ? '手工单元格：按公式填入时保留' : ''"
                      :style="{ textAlign: col.colIndex === 0 ? 'left' : 'right' }"
                      @click="noteEditMode && lazyEdit.startEdit($index + 10000, col.colIndex)">{{ row[col.colIndex] || '-' }}</span>
                  </template>
                </el-table-column>
                <el-table-column v-else :label="col.label" align="center">
                  <template v-for="(child, chi) in col.children" :key="'fs-mhc-' + ci + '-' + chi">
                    <el-table-column v-if="!child.children" :label="child.label" :min-width="130">
                      <template #default="{ row, $index }">
                        <el-input v-if="noteEditMode && lazyEdit.isEditing($index + 10000, child.colIndex)" v-model="row[child.colIndex]" size="small" :placeholder="child.label"
                          :class="{ 'gt-note-cell-manual': isManual(row, child.colIndex) }"
                          style="text-align:right"
                          @blur="lazyEdit.stopEdit()" @input="onNoteCellInput(row, child.colIndex)" autofocus />
                        <span v-else class="gt-note-cell-text"
                          :class="{ 'gt-note-cell-editable': noteEditMode, 'gt-note-cell-manual': isManual(row, child.colIndex) }"
                          :title="isManual(row, child.colIndex) ? '手工单元格：按公式填入时保留' : ''"
                          style="text-align:right"
                          @click="noteEditMode && lazyEdit.startEdit($index + 10000, child.colIndex)">{{ row[child.colIndex] || '-' }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column v-else :label="child.label" align="center">
                      <el-table-column v-for="(leaf, li) in child.children" :key="'fs-mhl-' + ci + '-' + chi + '-' + li"
                        :label="leaf.label" :min-width="130">
                        <template #default="{ row, $index }">
                          <el-input v-if="noteEditMode && lazyEdit.isEditing($index + 10000, leaf.colIndex)" v-model="row[leaf.colIndex]" size="small" :placeholder="leaf.label"
                            :class="{ 'gt-note-cell-manual': isManual(row, leaf.colIndex) }"
                            style="text-align:right"
                            @blur="lazyEdit.stopEdit()" @input="onNoteCellInput(row, leaf.colIndex)" autofocus />
                          <span v-else class="gt-note-cell-text"
                            :class="{ 'gt-note-cell-editable': noteEditMode, 'gt-note-cell-manual': isManual(row, leaf.colIndex) }"
                            :title="isManual(row, leaf.colIndex) ? '手工单元格：按公式填入时保留' : ''"
                            style="text-align:right"
                            @click="noteEditMode && lazyEdit.startEdit($index + 10000, leaf.colIndex)">{{ row[leaf.colIndex] || '-' }}</span>
                        </template>
                      </el-table-column>
                    </el-table-column>
                  </template>
                </el-table-column>
              </template>
            </template>
            <!-- 全屏模式：扁平表头 -->
            <template v-else>
            <el-table-column v-for="(h, hi) in selectedNoteSection.headers" :key="hi" :label="h" :min-width="hi === 0 ? 200 : 130">
              <template #default="{ row, $index }">
                <el-input v-if="noteEditMode && lazyEdit.isEditing($index + 10000, hi)" v-model="row[hi]" size="small" :placeholder="h"
                  :class="{ 'gt-note-cell-manual': isManual(row, hi) }"
                  :style="{ textAlign: hi === 0 ? 'left' : 'right' }"
                  @blur="lazyEdit.stopEdit()" @input="onNoteCellInput(row, hi)" autofocus />
                <span v-else class="gt-note-cell-text"
                  :class="{ 'gt-note-cell-editable': noteEditMode, 'gt-note-cell-manual': isManual(row, hi) }"
                  :title="isManual(row, hi) ? '手工单元格：按公式填入时保留' : ''"
                  :style="{ textAlign: hi === 0 ? 'left' : 'right' }"
                  @click="noteEditMode && lazyEdit.startEdit($index + 10000, hi)">{{ row[hi] || '-' }}</span>
              </template>
            </el-table-column>
            </template>
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
          <span style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary)">共 {{ selectedNoteSection.editRows?.length || 0 }} 行 · ESC 退出全屏</span>
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
    <div class="gt-ucell-ctx-item" @click="openNoteBreakdownForSelection"><span class="gt-ucell-ctx-icon">📊</span> 查看该格差额</div>
    <div v-if="selectedCellIsManual" class="gt-ucell-ctx-item" @click="restoreSelectedFormula"><span class="gt-ucell-ctx-icon">↩</span> 恢复按公式填入</div>
    <div class="gt-ucell-ctx-item" @click="addCellComment"><span class="gt-ucell-ctx-icon">💬</span> 添加批注</div>
    <div class="gt-ucell-ctx-item" @click="markCellReviewed"><span class="gt-ucell-ctx-icon">✅</span> 标记已复核</div>
    <div class="gt-ucell-ctx-divider" />
    <div class="gt-ucell-ctx-item" @click="openAggregateDialog"><span class="gt-ucell-ctx-icon">Σ</span> 汇总</div>
  </CellContextMenu>

  <!-- 批量导入导出弹窗 -->
  <el-dialog v-model="showNoteBatchDialog" title="附注导入导出与批量操作" width="520px" append-to-body>
    <div style="display:flex;flex-direction:column;gap:10px">
      <p style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-secondary);margin:0 0 4px;font-weight:600">当前表格操作</p>
      <div style="display:flex;gap:8px">
        <el-button size="small" @click="exportNoteTemplate" :disabled="!selectedNoteSection">📥 导出当前模板</el-button>
        <el-button size="small" @click="exportNoteData" :disabled="!selectedNoteSection">📤 导出当前数据</el-button>
        <el-button size="small" @click="noteFileRef?.click()" :disabled="!selectedNoteSection">📤 导入当前表格</el-button>
      </div>
      <el-divider style="margin:6px 0" />
      <p style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-secondary);margin:0 0 4px;font-weight:600">全部附注批量操作</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <el-button size="small" @click="batchExportAllTemplates" :loading="noteBatchLoading">📥 一键导出全部模板</el-button>
        <el-button size="small" @click="batchExportAllData" :loading="noteBatchLoading">📤 一键导出全部数据</el-button>
        <el-button size="small" type="primary" @click="noteBatchFileRef?.click()" :loading="noteBatchLoading">📤 一键导入全部数据</el-button>
      </div>
      <el-divider style="margin:6px 0" />
      <p style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-secondary);margin:0 0 4px;font-weight:600">公式审核</p>
      <div style="display:flex;gap:8px">
        <el-button size="small" @click="() => { auditCurrentNote(); showNoteBatchDialog = false }" :disabled="!selectedNoteSection" :loading="noteSingleAuditLoading">✅ 审核当前表格</el-button>
        <el-button size="small" @click="() => { onNoteAuditAll(); showNoteBatchDialog = false }">✅ 全部附注审核</el-button>
      </div>
      <el-divider style="margin:6px 0" />
      <p style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-secondary);margin:0 0 4px;font-weight:600">公式管理</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <el-button size="small" @click="() => { openNoteFormula(); showNoteBatchDialog = false }">ƒx 打开公式管理</el-button>
        <el-button size="small" @click="exportNoteFormulas" :loading="noteBatchLoading">📥 导出公式模板</el-button>
        <el-button size="small" @click="noteFormulaFileRef?.click()" :loading="noteBatchLoading">📤 导入公式</el-button>
        <el-button size="small" type="primary" @click="fillAllByFormula" :loading="noteBatchLoading">ƒx 全部按公式填入</el-button>
      </div>
      <p style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary);margin:4px 0 0">
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
      <span class="is-loading" style="font-size: 24px /* allow-px: special */;display:inline-block">⏳</span>
      <p style="color: var(--gt-color-text-tertiary);margin-top:8px">正在审核所有附注表格...</p>
    </div>
    <div v-else>
      <div style="display:flex;gap:12px;margin-bottom:12px;align-items:center">
        <el-tag :type="noteAuditSummary.errorCount ? 'danger' : 'success'" size="large">
          {{ noteAuditSummary.errorCount ? `${noteAuditSummary.errorCount} 项异常` : '全部通过' }}
        </el-tag>
        <span style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary)">
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
        <span class="gt-comment-info-value" style="font-size: var(--gt-font-size-sm)">{{ aggTarget.itemName }} / {{ aggTarget.colName }}</span>
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
          <p style="margin:2px 0 0;font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary)">汇总当前合并节点的直接下级企业，取同表同行同列数据求和</p>
        </div>
      </el-radio>
      <el-radio value="custom" style="display:flex;align-items:flex-start;width:100%">
        <div>
          <b>自定义汇总</b>
          <p style="margin:2px 0 0;font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary)">自由选择单位、数据表、坐标位置</p>
        </div>
      </el-radio>
    </el-radio-group>

    <!-- 自定义汇总详细设置 -->
    <div v-if="aggTarget.mode === 'custom'" style="border:1px solid var(--gt-color-border-purple);border-radius:8px;padding:14px;background: var(--gt-color-primary-bg)">
      <div style="display:flex;gap:16px">
        <!-- 左侧：选择单位 -->
        <div style="flex:1;min-width:0">
          <p style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-secondary);margin:0 0 6px;font-weight:600">① 选择汇总单位</p>
          <div style="border:1px solid var(--gt-color-border-purple);border-radius:6px;padding:6px;max-height:200px;overflow-y:auto;background: var(--gt-color-bg-white)">
            <el-tree :data="aggTreeData" :props="{ label: 'label', children: 'children', disabled: 'disabled' }"
              show-checkbox node-key="key" ref="aggTreeRef"
              default-expand-all>
              <template #default="{ data }">
                <span style="font-size: var(--gt-font-size-xs)">{{ data.icon }} {{ data.label }}
                  <el-tag v-if="data.ratio" size="small" type="info" style="margin-left:4px;font-size: var(--gt-font-size-xs)">{{ data.ratio }}%</el-tag>
                </span>
              </template>
            </el-tree>
          </div>
        </div>
        <!-- 右侧：选择数据来源和坐标 -->
        <div style="width:280px;flex-shrink:0">
          <p style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-secondary);margin:0 0 6px;font-weight:600">② 数据来源</p>
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

          <p style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-secondary);margin:10px 0 6px;font-weight:600">③ 坐标位置（可选）</p>
          <div style="display:flex;gap:8px">
            <div style="flex:1">
              <div style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary);margin-bottom:2px">行（项目名）</div>
              <el-input v-model="aggTarget.rowName" size="small" placeholder="留空=整表" clearable />
            </div>
            <div style="flex:1">
              <div style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-tertiary);margin-bottom:2px">列（表头名）</div>
              <el-input v-model="aggTarget.colHeader" size="small" placeholder="留空=整表" clearable />
            </div>
          </div>
          <p style="font-size: var(--gt-font-size-xs);color: var(--gt-color-text-placeholder);margin:4px 0 0">留空则汇总整张表格所有数据，填写则只汇总指定行列交叉位置</p>
        </div>
      </div>
    </div>

    <!-- 操作提示 -->
    <div style="margin-top:14px;padding:10px 14px;background: var(--gt-color-primary-bg);border-radius:6px;font-size: var(--gt-font-size-sm);color: var(--gt-color-text-secondary);line-height:1.6">
      <b style="color: var(--gt-color-primary)">💡 操作提示：</b>
      <span v-if="aggTarget.mode === 'direct'">点击"执行汇总"后，系统将自动获取直接下级企业的数据并求和，结果填充到当前选中的单元格。执行前会弹出确认框。</span>
      <span v-else>选择企业和数据来源后点击"执行汇总"，系统会弹出确认框显示汇总范围。坐标留空=汇总整表数据，填写=只汇总指定位置。</span>
    </div>

    <template #footer>
      <el-button @click="showAggregateDialog = false">取消</el-button>
      <el-button type="primary" @click="confirmAndExecuteAggregate" :loading="aggLoading">执行汇总</el-button>
    </template>
  </el-dialog>

  <!--
    Sprint 1.5.3：附注公式管理 dialog 已收敛到全局 FormulaManagerDialog（ThreeColumnLayout 顶层挂载）。
    `openNoteFormula()` 改为发出 EventBus `open-formula-manager` 事件，nodeKey='consol_note'。
  -->

  <!-- 「按公式填入」结果：手工保留与取不到数必须显式列出，不静默 -->
  <el-dialog v-model="showFillResultDialog" title="按公式填入结果" width="720px" append-to-body destroy-on-close
    data-testid="consol-note-fill-result">
    <el-alert :title="fillResultSummary" :type="fillDetails.some((r) => r.kind === 'blank') ? 'warning' : 'success'"
      :closable="false" show-icon style="margin-bottom:10px" />
    <el-table :data="fillDetails" border size="small" max-height="400" empty-text="全部公式单元格已填入">
      <el-table-column label="结果" width="90">
        <template #default="{ row }">
          <el-tag :type="row.kind === 'kept' ? 'info' : 'warning'" size="small">{{ row.kind === 'kept' ? '保留手工' : '未填入' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="position" label="单元格" min-width="190" show-overflow-tooltip />
      <el-table-column label="当前手工值" width="130" align="right">
        <template #default="{ row }"><GtAmountCell v-if="row.current !== null" :value="row.current" /></template>
      </el-table-column>
      <el-table-column label="公式值" width="130" align="right">
        <template #default="{ row }"><GtAmountCell v-if="row.formula_value !== null" :value="row.formula_value" /></template>
      </el-table-column>
      <el-table-column prop="reason" label="说明" min-width="190" show-overflow-tooltip />
    </el-table>
    <template #footer><el-button @click="showFillResultDialog = false">关闭</el-button></template>
  </el-dialog>

  <!-- 合并附注差额：四度量 + 所选汇总节点的直接子节点贡献（与报表差额表同一节点金额内核） -->
  <el-dialog v-model="showNoteBreakdownDialog" :title="`附注差额 — ${noteBreakdown?.title || selectedNoteSection?.title || ''}`"
    width="92%" top="3vh" append-to-body destroy-on-close data-testid="consol-note-breakdown-dialog">
    <div class="gt-note-breakdown-toolbar">
      <span>汇总节点</span>
      <el-select v-model="noteBreakdownNodeKey" size="small" style="width:240px" placeholder="根合并节点"
        data-testid="consol-note-breakdown-node" @change="loadNoteBreakdown">
        <el-option v-for="n in noteAggregateNodes" :key="n.node_key" :label="n.label" :value="n.node_key" />
      </el-select>
      <span v-if="noteBreakdown" :class="{ 'gt-note-breakdown-check--bad': noteBreakdownAudit.mismatched.length }"
        data-testid="consol-note-breakdown-check">{{ noteBreakdownAuditText }}</span>
      <span style="flex:1" />
      <el-button size="small" :loading="noteBreakdownLoading" @click="loadNoteBreakdown">🔄 刷新</el-button>
    </div>
    <el-alert v-if="noteBreakdownError" type="error" :closable="false" show-icon :title="noteBreakdownError" />
    <el-table v-loading="noteBreakdownLoading" :data="noteBreakdownTableRows" border size="small" max-height="62vh"
      empty-text="本章节还没有取数公式" :row-class-name="noteBreakdownRowClass" data-testid="consol-note-breakdown-table">
      <el-table-column type="expand" width="44">
        <template #default="{ row }">
          <div class="gt-note-breakdown-children">
            <p>所选汇总节点的直接子节点贡献（各列均按本单元格公式求值）</p>
            <el-table :data="noteBreakdownChildren(row)" border size="small" empty-text="所选节点没有下级贡献">
              <el-table-column prop="label" label="下级节点" min-width="180" />
              <el-table-column prop="kind_label" label="节点类型" width="100" />
              <el-table-column label="贡献" width="150" align="right">
                <template #default="{ row: child }"><GtAmountCell :value="child.value" /></template>
              </el-table-column>
            </el-table>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="position" label="单元格" fixed="left" min-width="200" show-overflow-tooltip />
      <el-table-column label="个别数汇总" min-width="130" align="right">
        <template #default="{ row }"><GtAmountCell :value="row.individual" /></template>
      </el-table-column>
      <el-table-column label="调整" min-width="120" align="right">
        <template #default="{ row }"><GtAmountCell :value="row.adjustment" /></template>
      </el-table-column>
      <el-table-column label="抵销" min-width="120" align="right" class-name="gt-note-elim-col" label-class-name="gt-note-elim-col">
        <template #default="{ row }"><GtAmountCell :value="row.elimination" /></template>
      </el-table-column>
      <el-table-column label="合并数" min-width="130" align="right">
        <template #default="{ row }"><strong><GtAmountCell :value="row.consolidated" /></strong></template>
      </el-table-column>
      <el-table-column label="公式" min-width="260" show-overflow-tooltip>
        <template #default="{ row }"><code>{{ row.formula }}</code></template>
      </el-table-column>
      <el-table-column label="来源" width="90">
        <template #default="{ row }">{{ formulaSourceLabel(row.source) }}</template>
      </el-table-column>
      <el-table-column prop="note" label="说明" min-width="180" show-overflow-tooltip />
    </el-table>
    <template #footer><el-button @click="showNoteBreakdownDialog = false">关闭</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { consolNoteSections as P_cn, consolidation as P_consol } from '@/services/apiPaths'
import {
  fillConsolNoteByFormula,
  getConsolNoteBreakdown,
  listConsolNoteFormulas,
  type ConsolNoteBreakdown,
  type ConsolNoteFillResult,
  type ConsolTreeNode,
  type CurrentConsolEntity,
} from '@/services/consolidationApi'
import { nodeLabel as treeNodeLabel, walkTree } from '@/components/consolidation/composables/consolTreeView'
import { createConsolRequestGuard, isAborted } from '@/components/consolidation/composables/consolRequestGuard'
import {
  clearManual,
  emptyEditRow,
  fillDetailRows,
  fillSummaryText,
  findBreakdownCell,
  fromEditRows,
  isManual,
  markManual,
  noteBreakdownCheck,
  noteBreakdownCheckText,
  noteBreakdownRows,
  notePayload,
  sectionIdsWithFormulas,
  toEditRows,
  type FillDetailRow,
  type NoteEditRow,
} from '@/components/consolidation/composables/consolNoteView'
import { useAcnr } from '@/services/acnr/useAcnr'
import { useCellSelection } from '@/composables/useCellSelection'
import CellContextMenu from '@/components/common/CellContextMenu.vue'
import CommentTooltip from '@/components/common/CommentTooltip.vue'
import SelectionBar from '@/components/common/SelectionBar.vue'
import { useCellComments } from '@/composables/useCellComments'
import { useLazyEdit } from '@/composables/useLazyEdit'
import { useEditMode } from '@/composables/useEditMode'
import { useFullscreen } from '@/composables/useFullscreen'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useTableToolbar } from '@/composables/useTableToolbar'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import { useAutoSave, buildDisclosureDraftKey, type DraftContext } from '@/composables/useAutoSave'
import { eventBus } from '@/utils/eventBus'
import type { ConsolCatalogSelectPayload, ConsolTreeAggregatePayload, ConsolNoteAuditAllPayload } from '@/utils/eventBus'
import { handleApiError } from '@/utils/errorHandler'
import { exportMultiSheetData, readSheetAoa, readWorkbookAoa } from '@/composables/useExcelIO'

const props = defineProps<{
  projectId: string
  year: number
  standard: string
  currentEntity: CurrentConsolEntity
  groupTree: ConsolTreeNode[]
  consolNoteTree: any[]
}>()

const emit = defineEmits<{
  (e: 'note-node-click', data: { section_id: string; title?: string }): void
  (e: 'audit-all'): void
  (e: 'load-note-tree', forceRefresh?: boolean): void
  (e: 'revert-standard', standard: string): void
}>()

// ─── ACNR NOTE 域索引解析（Req 20.3/20.4/20.7/20.9） ──────────────────────────
// 合并附注 note section 引用经 useAcnr().resolveIndex('note:'+sectionId) 解析/跳转，
// NOTE 域走 full_resolve V1 delegation，无需预登记 L1 catalog（Req 17.4）。
const router = useRouter()
const acnr = useAcnr()

/**
 * 源单体附注 section 的稳定 NOTE 地址标识（Req 20.4 reaggregate 溯源）。
 * 合并附注按同一 section 汇总各单体附注，故源 section 以 `note:{section}` 标识，
 * 与整个寻址体系一致，可追溯。仅为标识用途，不参与 reaggregate 计算。
 */
function sourceNoteAddr(sectionId?: string): string {
  return sectionId ? `note:${sectionId}` : ''
}

/**
 * 跳转到某合并附注 section（Req 20.3）。
 * 先经 ACNR resolveIndex('note:'+sectionId) 解析：
 *   - found=true 且有 jump_route → 直接按 ACNR 返回路由跳转（不自拼路由，R7.3 铁律）；
 *   - found=false / 无 jump_route / 异常 / 空 → 回退现有 note 导航 onNoteNodeClick（Req 20.7/20.9，无回归）。
 */
async function jumpToNoteSection(sectionId?: string, title?: string) {
  if (!sectionId) return
  try {
    const res = await acnr.resolveIndex(sourceNoteAddr(sectionId))
    if (res.found && res.jump_route) {
      router.push(res.jump_route)
      return
    }
  } catch { /* ACNR 不可用 → 回退现有导航 */ }
  // miss / 无 jump_route / 异常 → 回退现有 note 导航（行为不变）
  onNoteNodeClick({ section_id: sectionId, title })
}

// 当前请求目标章节独立于已渲染章节；切换章节后旧响应不得写入新章节。
const requestedSectionId = ref('')
const selectedNoteSection = ref<any>(null)

// ─── 跨表勾稽校验结果 ──────────────────────────────────────────────────────
const checkRulesResults = ref<Array<{ check_id: string; status: string; description: string; expected?: string; actual?: string; diff?: string; reason?: string }>>([])
const checkRulesLoading = ref(false)

async function loadCheckRules(sectionId: string) {
  if (!props.projectId || !props.year || !sectionId) {
    checkRulesResults.value = []
    return
  }
  checkRulesLoading.value = true
  try {
    const res: any = await api.get(
      `/api/consol-note-sections/check-rules/${props.projectId}/${props.year}/${sectionId}`,
      { params: { template_type: props.standard || 'soe' } },
    )
    checkRulesResults.value = res?.results || []
  } catch {
    checkRulesResults.value = []
  } finally {
    checkRulesLoading.value = false
  }
}

/**
 * 解析 multi_header（多行合并表头）为 Element Plus 嵌套 el-table-column 结构。
 *
 * multi_header 是二维数组 [row][col]：
 *   - 非空字符串 = 表头文本
 *   - 空字符串且同行左侧有非空 = 被左侧横向合并（colspan）
 *   - 空字符串且同列上方有非空 = 被上方纵向合并（rowspan）
 *
 * 返回 null 表示无分组（走旧扁平列逻辑），非 null 时返回嵌套列定义数组。
 *
 * 每个列定义：
 *   { label: string, colIndex: number, children?: [...] }
 *   - colIndex 对应 headers 数组下标（叶子列才有，非叶子为 -1）
 *   - children 存在时为分组列（el-table-column 嵌套渲染）
 */
interface MultiHeaderCol {
  label: string
  colIndex: number
  children?: MultiHeaderCol[]
}

const parsedMultiHeader = computed<MultiHeaderCol[] | null>(() => {
  const sec = selectedNoteSection.value
  if (!sec) return null

  // ── 路径 A：按 _column_groups 构建分组表头（与单体附注 DisclosureEditor 同结构） ──
  // CP-04：当 multi_header 有 3+ 行时跳过 Path A（只能建两层），让 Path B 递归处理三层
  const cg: Array<{ group: string; start: number; span: number }> | null = sec.columnGroups
  const mhRows: string[][] | null = sec?.multiHeader
  const hasThreeOrMoreHeaderRows = mhRows && Array.isArray(mhRows) && mhRows.length >= 3
  if (cg && Array.isArray(cg) && cg.length > 0 && !hasThreeOrMoreHeaderRows) {
    const headers: string[] = sec.headers || []
    const mhForLabels: string[][] | null = sec.multiHeader
    // 子列标签优先从 multi_header 末行取（最底层真实标签），降级到 headers 拆分最后一段
    const leafRow: string[] | null = (mhForLabels && Array.isArray(mhForLabels) && mhForLabels.length >= 2)
      ? mhForLabels[mhForLabels.length - 1]
      : null
    const result: MultiHeaderCol[] = []
    let pos = 0
    for (const g of cg) {
      // 分组前的独立列
      while (pos < g.start && pos < headers.length) {
        result.push({ label: headers[pos] || '', colIndex: pos })
        pos++
      }
      // 分组列
      const children: MultiHeaderCol[] = []
      for (let i = g.start; i < g.start + g.span && i < headers.length; i++) {
        // 优先：multi_header 末行的真实标签
        let label = (leafRow && i < leafRow.length) ? (leafRow[i] || '').trim() : ''
        if (!label) {
          // 降级：从合并 headers（/连接的）取最后一段
          const parts = (headers[i] || '').split('/')
          label = parts[parts.length - 1] || headers[i] || ''
        }
        children.push({ label, colIndex: i })
      }
      if (children.length > 0) {
        result.push({ label: g.group, colIndex: -1, children })
      }
      pos = g.start + g.span
    }
    // 分组后的剩余独立列
    while (pos < headers.length) {
      result.push({ label: headers[pos] || '', colIndex: pos })
      pos++
    }
    return result.length > 0 ? result : null
  }

  // ── 路径 B（降级）：按 multi_header 二维数组解析（P0 实现，保留作为降级路径） ──
  const mh: string[][] | null = sec?.multiHeader
  if (!mh || !Array.isArray(mh) || mh.length < 2) return null

  const rowCount = mh.length
  const colCount = mh[0]?.length || 0
  if (colCount === 0) return null

  // 构建 grid：计算每个单元格的 colspan 和 rowspan
  const grid: Array<Array<{ text: string; colspan: number; rowspan: number; occupied: boolean }>> = []
  for (let r = 0; r < rowCount; r++) {
    grid[r] = []
    for (let c = 0; c < colCount; c++) {
      grid[r][c] = { text: (mh[r]?.[c] || '').trim(), colspan: 1, rowspan: 1, occupied: false }
    }
  }

  // 标记被合并的单元格：横向（同行左边非空→右边空=colspan）
  for (let r = 0; r < rowCount; r++) {
    for (let c = colCount - 1; c >= 1; c--) {
      if (grid[r][c].text === '') {
        // 向左找最近的非空
        let anchor = c - 1
        while (anchor >= 0 && grid[r][anchor].text === '' && grid[r][anchor].occupied) anchor--
        if (anchor >= 0 && grid[r][anchor].text !== '') {
          grid[r][anchor].colspan++
          grid[r][c].occupied = true
        }
      }
    }
  }

  // 纵向合并（上方非空→下方空=rowspan）
  for (let c = 0; c < colCount; c++) {
    for (let r = rowCount - 1; r >= 1; r--) {
      if (grid[r][c].text === '' && !grid[r][c].occupied) {
        let anchor = r - 1
        while (anchor >= 0 && grid[anchor][c].text === '' && grid[anchor][c].occupied) anchor--
        if (anchor >= 0 && grid[anchor][c].text !== '') {
          grid[anchor][c].rowspan++
          grid[r][c].occupied = true
        }
      }
    }
  }

  // 只处理 2~3 行表头的常见场景：转为嵌套 el-table-column 结构
  // 策略：第一行的每个非 occupied 单元格是顶层列。
  // 如果它的 rowspan == rowCount，它是叶子列（独立列跨全部行）。
  // 如果它的 rowspan < rowCount，它是分组列，其 children 由下一行对应 colspan 范围内的列构成。
  const result: MultiHeaderCol[] = []
  for (let c = 0; c < colCount; c++) {
    const cell = grid[0][c]
    if (cell.occupied) continue

    if (cell.rowspan >= rowCount) {
      // 独立列，跨全部行
      result.push({ label: cell.text, colIndex: c })
    } else {
      // 分组列：收集 children 从下一行开始
      const children = collectChildren(grid, 1, c, c + cell.colspan, rowCount, colCount)
      if (children.length > 0) {
        result.push({ label: cell.text, colIndex: -1, children })
      } else {
        // 无法解析子列时降级为扁平列
        for (let cc = c; cc < c + cell.colspan && cc < colCount; cc++) {
          result.push({ label: sec.headers[cc] || '', colIndex: cc })
        }
      }
    }
  }

  return result.length > 0 ? result : null
})

/** 递归收集子列（支持 3 行表头的二级嵌套） */
function collectChildren(
  grid: Array<Array<{ text: string; colspan: number; rowspan: number; occupied: boolean }>>,
  startRow: number, startCol: number, endCol: number,
  totalRows: number, totalCols: number,
): MultiHeaderCol[] {
  const children: MultiHeaderCol[] = []
  for (let c = startCol; c < endCol && c < totalCols; c++) {
    const cell = grid[startRow][c]
    if (cell.occupied) continue

    if (cell.rowspan + startRow >= totalRows) {
      // 叶子
      children.push({ label: cell.text, colIndex: c })
    } else {
      // 继续嵌套
      const sub = collectChildren(grid, startRow + 1, c, c + cell.colspan, totalRows, totalCols)
      if (sub.length > 0) {
        children.push({ label: cell.text, colIndex: -1, children: sub })
      } else {
        children.push({ label: cell.text, colIndex: c })
      }
    }
  }
  return children
}

const { isEditing: noteEditMode, isDirty: noteDirty, enterEdit: enterNoteEdit, exitEdit: exitNoteEdit, markDirty: markNoteDirty, clearDirty: clearNoteDirty } = useEditMode({ guardRoute: false })
const { isFullscreen: noteFullscreen, toggleFullscreen: toggleNoteFullscreen } = useFullscreen()
const formulaFilling = ref(false)
const reaggregating = ref(false)
const noteSingleAuditLoading = ref(false)
const noteFileRef = ref<HTMLInputElement | null>(null)
const noteTableRef = ref<any>(null)

/**
 * 当前节点身份键。所有附注节点级请求统一经此取 nodeKey，
 * 确保读写、公式、审核、汇总共享同一个节点上下文。
 * 设计：consol-node-key-isolation-and-shared-context §七
 */
function currentNodeKey(): string | undefined {
  return props.currentEntity.nodeKey || undefined
}

interface NotePageSnapshot {
  projectId: string
  year: number
  nodeKey: string
}

interface NoteContextSnapshot extends NotePageSnapshot {
  sectionId: string
}

type NoteRefreshStatus = 'done' | 'failed' | 'stale' | 'skipped'

type NoteRefreshContext = NoteContextSnapshot

interface NoteRefreshResult {
  status: NoteRefreshStatus
  context: NoteRefreshContext | null
  persisted: boolean
  updatedAt: string | null
  reason?: string
}

// NoteRefreshResult 已覆盖持久化载荷需求；PersistedNotePayload 不再使用

interface AggregateSnapshot {
  context: NoteContextSnapshot
  section: any
  row: number
  col: number
  mode: 'direct' | 'custom'
  source: 'same' | 'report' | 'note'
  reportTypes: string[]
  noteSections: string[]
  companyCodes: string[]
  entityCode: string
}

function capturePageSnapshot(): NotePageSnapshot | null {
  const projectId = String(props.projectId || '').trim()
  const year = Number(props.year) || 0
  if (!projectId || !year) return null
  return { projectId, year, nodeKey: currentNodeKey() || '' }
}

function captureNoteSnapshot(section: any = selectedNoteSection.value): NoteContextSnapshot | null {
  const page = capturePageSnapshot()
  const sectionId = String(section?.section_id || '').trim()
  if (!page || !sectionId) return null
  return { ...page, sectionId }
}

function isPageSnapshotCurrent(snapshot: NotePageSnapshot): boolean {
  const current = capturePageSnapshot()
  return !!current
    && current.projectId === snapshot.projectId
    && current.year === snapshot.year
    && current.nodeKey === snapshot.nodeKey
}

function isNoteSnapshotCurrent(snapshot: NoteContextSnapshot, section?: any): boolean {
  return isPageSnapshotCurrent(snapshot)
    && String(selectedNoteSection.value?.section_id || '') === snapshot.sectionId
    && (!section || selectedNoteSection.value === section)
}

// ─── 请求上下文保护：切节点后旧响应不得提交（设计 §七、P9）──────────────────
const noteRequestGuard = createConsolRequestGuard(() => ({
  projectId: props.projectId,
  year: props.year,
  nodeKey: currentNodeKey() || '',
  sectionId: requestedSectionId.value,
}))

function noteDataUrl(context: NoteContextSnapshot): string {
  const base = P_cn.data(context.projectId, context.year, context.sectionId)
  return context.nodeKey
    ? `${base}?node_key=${encodeURIComponent(context.nodeKey)}`
    : base
}

function currentRequestedNoteContext(): NoteContextSnapshot | null {
  const page = capturePageSnapshot()
  const sectionId = String(requestedSectionId.value || selectedNoteSection.value?.section_id || '').trim()
  if (!page || !sectionId) return null
  return { ...page, sectionId }
}

function sameNoteContext(left: NoteContextSnapshot, right: NoteContextSnapshot): boolean {
  return left.projectId === right.projectId
    && left.year === right.year
    && left.nodeKey === right.nodeKey
    && left.sectionId === right.sectionId
}

function noteRefreshResult(
  status: NoteRefreshStatus,
  context: NoteContextSnapshot | null,
  options: Partial<Omit<NoteRefreshResult, 'status' | 'context'>> = {},
): NoteRefreshResult {
  return {
    status,
    context,
    persisted: options.persisted ?? false,
    updatedAt: options.updatedAt ?? null,
    reason: options.reason,
  }
}

function noteErrorMessage(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
    || err?.response?.data?.message
    || err?.data?.detail
    || err?.data?.message
    || err?.message
  return typeof detail === 'string' && detail.trim() ? detail : fallback
}

function hasPersistedNoteContent(content: Record<string, unknown>): boolean {
  return Object.keys(content).length > 0
}

function applyPersistedNoteContent(section: any, content: Record<string, unknown>) {
  const headers = Array.isArray(content.headers) && content.headers.length
    ? content.headers
    : section.headers
  const rows = Array.isArray(content.rows) ? content.rows : []
  section.headers = headers
  section.savedData = { ...content }
  section.editRows = toEditRows(headers, rows, content.manual_cells)
  clearNoteDirty()
  clearAutoSaveDraft()
}

/**
 * 重新读取当前章节的持久化数据。
 *
 * note_done 的唯一证据是本次 GET 返回的持久化 content，并且响应提交前必须
 * 仍处于调用方冻结的 project/year/node/section 上下文；公式接口响应本身不能替代这次重读。
 */
async function reloadCurrentSectionAfterRefresh(
  expectedContext?: NoteContextSnapshot | null,
): Promise<NoteRefreshResult> {
  const context = expectedContext || currentRequestedNoteContext()
  if (!context) return noteRefreshResult('skipped', null, { reason: '当前没有可重读的附注章节' })
  const current = currentRequestedNoteContext()
  if (!current || !sameNoteContext(context, current)) {
    return noteRefreshResult('stale', context, { reason: '附注节点或章节已切换' })
  }
  const ticket = noteRequestGuard.startRequest()
  try {
    const saved: any = await api.get(noteDataUrl(context), {
      validateStatus: (s: number) => s < 600,
      signal: ticket.signal,
    })
    if (noteRequestGuard.isStale(ticket)) {
      return noteRefreshResult('stale', context, { reason: '附注重读响应已过期' })
    }
    const latest = currentRequestedNoteContext()
    const section = selectedNoteSection.value
    if (!latest || !sameNoteContext(context, latest) || section?.section_id !== context.sectionId) {
      return noteRefreshResult('stale', context, { reason: '附注节点或章节已切换' })
    }
    if (!saved || saved.error) {
      throw new Error(saved?.error || '附注持久化数据读取失败')
    }
    // 错误响应（4xx/5xx）不能被当作空 content 返回 skipped（需求 6.4）
    if (hasApiFailure(saved)) {
      throw new Error(noteErrorMessage(saved, '附注持久化数据读取失败'))
    }
    const content = saved.content && typeof saved.content === 'object'
      ? { ...saved.content }
      : {}
    if (!hasPersistedNoteContent(content)) {
      return noteRefreshResult('skipped', context, {
        updatedAt: saved.updated_at || null,
        reason: '当前章节暂无持久化数据',
      })
    }
    applyPersistedNoteContent(section, content)
    return noteRefreshResult('done', context, {
      persisted: true,
      updatedAt: saved.updated_at || null,
    })
  } catch (err: any) {
    if (noteRequestGuard.isStale(ticket)) {
      return noteRefreshResult('stale', context, { reason: '附注重读响应已过期' })
    }
    const reason = noteErrorMessage(err, '附注持久化数据读取失败')
    ElMessage.error(`读取附注持久化数据失败：${reason}`)
    return noteRefreshResult('failed', context, { reason })
  }
}

// ─── 合并附注公式填入与差额（同报表差额表的节点金额内核） ─────────────────────
const showFillResultDialog = ref(false)
const fillResultSummary = ref('')
const fillDetails = ref<FillDetailRow[]>([])
const showNoteBreakdownDialog = ref(false)
const noteBreakdownLoading = ref(false)
const noteBreakdownError = ref('')
const noteBreakdown = ref<ConsolNoteBreakdown | null>(null)
const noteBreakdownNodeKey = ref<string | null>(null)
const noteBreakdownTarget = reactive({ row: -1, col: -1 })

/** 企业树中的汇总节点（树序）；与报表差额表 / 合并试算平衡表的节点选择同一判定 */
const noteAggregateNodes = computed(() => {
  const out: Array<{ node_key: string; label: string }> = []
  for (const root of props.groupTree) {
    for (const node of walkTree(root)) {
      if (node.kind === 'aggregate') out.push({ node_key: node.node_key, label: treeNodeLabel(node) })
    }
  }
  return out
})
const noteBreakdownTableRows = computed(() => noteBreakdownRows(noteBreakdown.value))
const noteBreakdownAudit = computed(() => noteBreakdownCheck(noteBreakdown.value))
const noteBreakdownAuditText = computed(() => noteBreakdownCheckText(noteBreakdownAudit.value))

// useTableToolbar 管理选中行状态（editRows 是动态嵌套属性，用 computed 桥接）
const noteEditRows = computed({
  get: () => selectedNoteSection.value?.editRows ?? [],
  set: (v) => { if (selectedNoteSection.value) selectedNoteSection.value.editRows = v },
})
const {
  selectedRows: noteSelectedRows,
  onSelectionChange: onNoteSelectionChange,
  deleteSelectedRows,
} = useTableToolbar(noteEditRows)
const noteBatchFileRef = ref<HTMLInputElement | null>(null)
const noteFormulaFileRef = ref<HTMLInputElement | null>(null)
const showNoteBatchDialog = ref(false)
const noteBatchLoading = ref(false)

// ─── 批注与复核持久化 ────────────────────────────────────────────────────────
const cellComments = useCellComments(() => props.projectId, () => props.year, 'consol_note')

// ─── 按需渲染编辑控件（大表格性能优化） ──────────────────────────────────────
const lazyEdit = useLazyEdit()

// ─── 自动保存/草稿恢复 [R3.8] ──────────────────────────────────────────────
const noteDraftContext = computed<DraftContext | null>(() => {
  const sectionId = String(selectedNoteSection.value?.section_id || '').trim()
  const nodeKey = String(currentNodeKey() || '').trim()
  const projectId = String(props.projectId || '').trim()
  const year = Number(props.year) || 0
  if (!projectId || !year || !sectionId || !nodeKey) return null
  // DraftContext 的 section 同时编码节点与章节，确保同一章节在不同合并节点间隔离。
  return { project_id: projectId, year, section: `${nodeKey}:${sectionId}` }
})
const noteDraftKey = computed(() => {
  const context = noteDraftContext.value
  return context ? buildDisclosureDraftKey(context) : 'global'
})
const { clearDraft: clearAutoSaveDraft } = useAutoSave(
  noteDraftKey,
  () => {
    const sec = selectedNoteSection.value
    const context = noteDraftContext.value
    if (!sec || !context) return null
    return {
      section_id: sec.section_id,
      node_key: currentNodeKey(),
      title: sec.title,
      headers: sec.headers,
      editRows: sec.editRows,
    }
  },
  (data) => {
    const sec = selectedNoteSection.value
    if (!sec || !data) return
    if (data.section_id !== sec.section_id || data.node_key !== currentNodeKey()) return
    if (data.headers) sec.headers = data.headers
    if (data.editRows) sec.editRows = data.editRows
  },
  { enabled: noteEditMode, context: noteDraftContext },
)

// ─── 附注全审 ────────────────────────────────────────────────────────────────
const showNoteAuditDialog = ref(false)
const noteAuditLoading = ref(false)
const noteAuditResults = ref<any[]>([])
const noteAuditSummary = reactive({ totalSections: 0, totalChecks: 0, passCount: 0, errorCount: 0, warnCount: 0 })

// ─── 公式编辑（已收敛到全局 FormulaManagerDialog，详见 openNoteFormula） ────

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

// 兼容别名
const selectedCells = noteCtx.selectedCells
const selectedCellIsManual = computed(() => {
  const sec = selectedNoteSection.value
  const cell = selectedCells.value[0]
  return !!sec && selectedCells.value.length === 1 && !!cell && isManual(sec.editRows?.[cell.row], cell.col)
})
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

// 汇总选择树：键用 node_key（同一企业的合并户与母公司户是两个节点，按企业代码会撞键）；
// 差额节点没有企业数据，不可勾选；提交时按勾选节点的企业代码去重（后端按企业取数）
const aggTreeData = computed(() => {
  function buildAggNode(node: any): any {
    return {
      key: node.node_key || node.company_code || 'root',
      companyCode: node.company_code || '',
      label: node.display_name || node.company_name || node.name,
      icon: node.kind === 'elim' ? '📝' : node.children?.length ? '🏢' : '🏠',
      ratio: node.shareholding,
      disabled: node.kind === 'elim',
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

// onNoteSelectionChange 已由 useTableToolbar 提供

/** 编辑值即成为手工单元格；第 0 列是项目名，不参与取数公式 */
function onNoteCellInput(row: NoteEditRow, col: number) {
  markManual(row, col)
  markNoteDirty()
  // 自动刷新合计行
  recalcTotalRows()
}

/** 重算合计行：遍历 editRows，对 total/subtotal 行的空值列自动求和 */
function recalcTotalRows() {
  const sec = selectedNoteSection.value
  if (!sec?.editRows?.length) return
  const rows = sec.editRows as NoteEditRow[]
  const types: string[] | null = sec.rowTypes
  const width = sec.headers?.length || 0

  for (let ri = 0; ri < rows.length; ri++) {
    const rtype = types && ri < types.length
      ? types[ri]
      : _inferRowType(rows[ri])
    if (rtype !== 'total' && rtype !== 'subtotal') continue

    // 向上找数据行范围
    let dataStart = ri
    for (let j = ri - 1; j >= 0; j--) {
      const jtype = types && j < types.length
        ? types[j]
        : _inferRowType(rows[j])
      if (jtype === 'total' || jtype === 'subtotal') break
      dataStart = j
    }

    // 对每个数值列求和回填
    for (let ci = 1; ci < width; ci++) {
      let sum = 0
      let hasData = false
      for (let j = dataStart; j < ri; j++) {
        const v = _parseNum(rows[j]?.[ci])
        if (v !== null) { sum += v; hasData = true }
      }
      if (hasData) {
        rows[ri][ci] = sum === Math.floor(sum) ? String(sum) : String(sum)
      }
    }
  }
}

function _inferRowType(row: NoteEditRow): string {
  const label = String(row?.[0] || '').trim().replace(/\s+/g, '')
  if (label === '合计') return 'total'
  if (label === '小计') return 'subtotal'
  return 'data'
}

function _parseNum(val: any): number | null {
  if (val == null || val === '') return null
  const s = String(val).trim().replace(/,/g, '').replace(/，/g, '')
  if (!s) return null
  const n = Number(s)
  return isNaN(n) ? null : n
}

/** 删除行后手工标记随行对象一起移动；保存时重新按当前行号序列化 */
async function deleteNoteRows() {
  if (await deleteSelectedRows()) markNoteDirty()
}

/** 取消手工保护；下一次「按公式填入」会重新写入该格 */
function restoreSelectedFormula() {
  noteCtx.closeContextMenu()
  const sec = selectedNoteSection.value
  const cell = selectedCells.value[0]
  if (!sec || !cell) return
  clearManual(sec.editRows[cell.row], cell.col)
  markNoteDirty()
  ElMessage.success('已恢复为公式单元格；点击“按公式填入”即可取最新合并数')
}

// ─── 单元格选中与右键菜单 ──────────────────────────────────────────────────
/** 合计行/小计行 CSS class（基于后端 _row_types 推导，或行首列文本匹配） */
function noteRowClassName({ rowIndex }: { row: any; rowIndex: number }): string {
  const sec = selectedNoteSection.value
  if (!sec) return ''
  // 优先使用后端推导的 _row_types
  const types: string[] | null = sec.rowTypes
  if (types && rowIndex < types.length) {
    if (types[rowIndex] === 'total') return 'gt-note-total-row'
    if (types[rowIndex] === 'subtotal') return 'gt-note-subtotal-row'
    return ''
  }
  // 降级：从行首列文本判断
  const rows = sec.editRows
  if (!rows || rowIndex >= rows.length) return ''
  const label = String(rows[rowIndex]?.[0] || '').trim().replace(/\s+/g, '')
  if (label === '合计') return 'gt-note-total-row'
  if (label === '小计') return 'gt-note-subtotal-row'
  return ''
}

function noteCellClassName({ rowIndex, columnIndex }: any) {
  const sec = selectedNoteSection.value
  const sheetKey = sec?.section_id || ''
  const classes: string[] = []
  const selClass = noteCtx.cellClassName({ rowIndex, columnIndex })
  if (selClass) classes.push(selClass)
  // 批注/复核标记
  const ccClass = cellComments.commentCellClass(sheetKey, rowIndex, columnIndex)
  if (ccClass) classes.push(ccClass)
  if (isManual(sec?.editRows?.[rowIndex], columnIndex)) classes.push('gt-note-manual-cell')
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
  // eslint-disable-next-line gt-audit/no-amount-toFixed -- 这里格式化的是百分比，不是金额
  const pct = vals[1] !== 0 ? ((diff / Math.abs(vals[1])) * 100).toFixed(2) : '—'
  ElMessage.info(`差异：${fmtAmt(diff)}（${pct}%）| 值1=${fmtAmt(vals[0])} 值2=${fmtAmt(vals[1])}`)
}

const FORMULA_SOURCE_LABEL: Record<string, string> = { seed: '自动种子', manual: '人工' }
const NODE_KIND_LABEL: Record<string, string> = { data: '单户', elim: '差额', aggregate: '下级汇总' }

function formulaSourceLabel(source: string | null | undefined): string {
  return FORMULA_SOURCE_LABEL[source || ''] || source || ''
}

/** 打开章节差额；传 row/col 时，按模板行标签定位并高亮该单元格对应公式 */
async function openNoteBreakdown(target?: { row: number; col: number }) {
  const sec = selectedNoteSection.value
  if (!sec?.section_id) {
    ElMessage.info('请先选择附注章节')
    return
  }
  noteCtx.closeContextMenu()
  noteBreakdownTarget.row = target?.row ?? -1
  noteBreakdownTarget.col = target?.col ?? -1
  showNoteBreakdownDialog.value = true
  await loadNoteBreakdown()
}

async function openNoteBreakdownForSelection() {
  const cell = selectedCells.value[0]
  if (!cell) {
    ElMessage.info('请先选择附注单元格')
    return
  }
  await openNoteBreakdown({ row: cell.row, col: cell.col })
}

async function loadNoteBreakdown() {
  const sec = selectedNoteSection.value
  if (!sec?.section_id || noteBreakdownLoading.value) return
  noteBreakdownLoading.value = true
  noteBreakdownError.value = ''
  try {
    const result = await getConsolNoteBreakdown(props.projectId, props.year, sec.section_id, {
      nodeKey: noteBreakdownNodeKey.value,
      standard: props.standard,
    })
    noteBreakdown.value = result
    if (!noteBreakdownNodeKey.value && result.node_key) noteBreakdownNodeKey.value = result.node_key
    // 已保存数据插删过行时，用行标签把编辑格映射回模板公式行（与后端填入同口径）
    if (noteBreakdownTarget.row >= 0 && noteBreakdownTarget.col >= 1) {
      const rowLabel = String(sec.editRows?.[noteBreakdownTarget.row]?.[0] || '')
      const found = findBreakdownCell(result.cells, rowLabel, noteBreakdownTarget.row, noteBreakdownTarget.col)
      if (found) {
        noteBreakdownTarget.row = found.row_index
        noteBreakdownTarget.col = found.col_index
      }
    }
  } catch (err: any) {
    noteBreakdown.value = null
    const detail = err?.response?.data?.detail
    noteBreakdownError.value = typeof detail === 'string' && detail ? detail : '加载附注差额失败'
  } finally {
    noteBreakdownLoading.value = false
  }
}

function noteBreakdownChildren(row: ReturnType<typeof noteBreakdownRows>[number]) {
  return (noteBreakdown.value?.children || []).map((child) => ({
    node_key: child.node_key,
    label: child.label || child.node_key,
    kind_label: NODE_KIND_LABEL[child.kind] || child.kind,
    value: row.children?.[child.node_key] ?? null,
  }))
}

function noteBreakdownRowClass({ row }: { row: ReturnType<typeof noteBreakdownRows>[number] }): string {
  if (row.row_index === noteBreakdownTarget.row && row.col_index === noteBreakdownTarget.col) return 'gt-note-breakdown-target'
  return ''
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
    const { confirmDangerous } = await import('@/utils/confirm')
    await confirmDangerous(confirmMsg, '确认执行汇总')
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
      const data = await api.post(P_cn.aggregate(props.projectId, props.year), {
        section_id: sec.section_id,
        row_idx: c.row,
        col_idx: c.col,
        company_code: entityCode,
        mode: 'direct',
        standard: props.standard,
        node_key: currentNodeKey(),
      }, { validateStatus: (s: number) => s < 600 })
      const result = data
      if (result?.value != null) {
        sec.editRows[c.row][c.col] = String(result.value)
        ElMessage.success(`已汇总 ${result.count || 0} 家直接下级，合计：${fmtAmt(result.value)}`)
      } else {
        ElMessage.info('暂无下级数据可汇总')
      }
    } else {
      const checkedNodes = aggTreeRef.value?.getCheckedNodes() || []
      if (!checkedNodes.length) { ElMessage.warning('请选择要汇总的单位'); aggLoading.value = false; return }
      const companyCodes: string[] = [...new Set<string>(
        checkedNodes.map((n: any) => String(n.companyCode || '')).filter((c: string) => !!c),
      )]
      const data = await api.post(P_cn.aggregate(props.projectId, props.year), {
        section_id: aggTarget.source === 'same' ? sec.section_id : (aggTarget.source === 'note' ? (aggTarget as any).noteSection : sec.section_id),
        row_idx: c.row,
        col_idx: c.col,
        company_codes: companyCodes,
        mode: 'custom',
        source: aggTarget.source,
        report_types: aggTarget.reportTypes,
        note_sections: aggTarget.noteSections,
        standard: props.standard,
        node_key: currentNodeKey(),
      }, { validateStatus: (s: number) => s < 600 })
      const result = data
      if (result?.value != null) {
        sec.editRows[c.row][c.col] = String(result.value)
        ElMessage.success(`已汇总 ${companyCodes.length} 家企业，合计：${fmtAmt(result.value)}`)
      } else {
        ElMessage.info('暂无数据可汇总')
      }
    }
    showAggregateDialog.value = false
  } catch (err: any) {
    handleApiError(err, '汇总')
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

function noteFormulaError(err: any, action: string) {
  const status = err?.response?.status || err?.status || 0
  const detail = err?.response?.data?.detail || err?.data?.detail
  if ((status === 400 || status === 423) && typeof detail === 'string' && detail) {
    ElMessage.warning(`${action}：${detail}`)
    return
  }
  handleApiError(err, action)
}

/** 把该章节有公式单元格的合并数写入已保存数据；手工单元格保留，取不到数逐格提示 */
async function fillCurrentByFormula(): Promise<NoteRefreshResult> {
  const sec = selectedNoteSection.value
  const context = captureNoteSnapshot(sec)
  if (!sec || !context || !props.projectId) {
    ElMessage.warning('请先选择章节')
    return noteRefreshResult('skipped', context, { reason: '请先选择附注章节' })
  }
  // 未保存的编辑必须先落库并带 manual_cells；否则后端读到旧数据会覆盖用户刚输入的值
  if (noteDirty.value && !(await saveNoteData())) {
    return noteRefreshResult('failed', context, { reason: '当前附注数据保存失败' })
  }
  const latestBeforeFill = currentRequestedNoteContext()
  if (!latestBeforeFill || !sameNoteContext(context, latestBeforeFill)) {
    return noteRefreshResult('stale', context, { reason: '附注节点或章节已切换' })
  }
  formulaFilling.value = true
  try {
    const result = await fillConsolNoteByFormula(
      context.projectId,
      context.year,
      context.sectionId,
      props.standard,
      context.nodeKey || null,
    )
    const latestAfterFill = currentRequestedNoteContext()
    if (!latestAfterFill || !sameNoteContext(context, latestAfterFill)) {
      return noteRefreshResult('stale', context, { reason: '公式填入响应已过期' })
    }
    fillResultSummary.value = fillSummaryText(result)
    fillDetails.value = fillDetailRows(result)
    if (fillDetails.value.length) showFillResultDialog.value = true
    if (result.blank?.length) ElMessage.warning(fillResultSummary.value)
    // 公式接口响应只用于展示填入明细；必须再 GET 当前章节的持久化内容，
    // 以保留后端实际保存的 manual_cells 和其他元数据。
    const reloadResult = await reloadCurrentSectionAfterRefresh(context)
    if (reloadResult.status === 'done') {
      ElMessage.success(fillResultSummary.value)
    } else if (reloadResult.status === 'failed') {
      ElMessage.error(`按公式填入完成，但持久化重读失败：${reloadResult.reason || '未知原因'}`)
    } else if (reloadResult.status === 'stale') {
      ElMessage.warning(`按公式填入结果已过期：${reloadResult.reason || '附注节点或章节已切换'}`)
    } else {
      ElMessage.warning(`按公式填入未完成：${reloadResult.reason || '暂无持久化数据'}`)
    }
    return reloadResult
  } catch (err: any) {
    noteFormulaError(err, '按公式填入')
    return noteRefreshResult('failed', context, { reason: noteErrorMessage(err, '按公式填入失败') })
  } finally {
    formulaFilling.value = false
  }
}

// B.1.13: 重新汇总（从子公司单体附注汇总到合并附注）
// Req 20.4/20.9：溯源以 NOTE addr（note:{section}）标识源单体附注 section，
// 与统一寻址体系一致；reaggregate 计算逻辑本身完全不变（仅后端聚合，前端只负责触发+重载）。
async function handleReaggregate(): Promise<NoteRefreshResult> {
  if (!props.projectId) return noteRefreshResult('skipped', null, { reason: '当前项目无效' })
  const sec = selectedNoteSection.value
  const context = captureNoteSnapshot(sec)
  if (!context) return noteRefreshResult('skipped', null, { reason: '请先选择附注章节' })
  reaggregating.value = true
  try {
    const body: Record<string, unknown> = {
      section_ids: [context.sectionId],
      node_key: context.nodeKey || null,
      standard: props.standard,
      template_type: props.standard,
    }
    const result: any = await api.post(
      P_consol.notes.reaggregate(context.projectId, context.year),
      body,
    )
    const updated = result?.sections_updated ?? 0
    const processed = result?.sections_processed ?? 0
    const errors = Array.isArray(result?.errors) ? result.errors : []
    const failures = Array.isArray(result?.failures) ? result.failures : []
    if (errors.length || failures.length) {
      ElMessage.warning(`重新汇总完成：处理 ${processed} 个章节，更新 ${updated} 个，${errors.length || failures.length} 个有告警`)
    }
    // reaggregate 成功只说明服务端编排完成；当前章节仍必须通过独立 GET 证明已持久化。
    const reloadResult = await reloadCurrentSectionAfterRefresh(context)
    if (reloadResult.status === 'done') {
      if (!errors.length && !failures.length) ElMessage.success(`重新汇总完成：更新 ${updated} 个章节`)
    } else if (reloadResult.status === 'failed') {
      ElMessage.error(`重新汇总完成，但章节重读失败：${reloadResult.reason || '未知原因'}`)
    } else if (reloadResult.status === 'stale') {
      ElMessage.warning(`重新汇总结果已过期：${reloadResult.reason || '附注节点或章节已切换'}`)
    } else {
      ElMessage.warning(`重新汇总未完成：${reloadResult.reason || '暂无持久化数据'}`)
    }
    return reloadResult
  } catch (err: any) {
    const reason = noteErrorMessage(err, '重新汇总失败')
    handleApiError(err, '重新汇总')
    return noteRefreshResult('failed', context, { reason })
  } finally {
    reaggregating.value = false
  }
}

function addNoteRow() {
  const sec = selectedNoteSection.value
  if (!sec?.headers) return
  sec.editRows.push(emptyEditRow(sec.headers.length))
  markNoteDirty()
}

// deleteNoteRows 封装 useTableToolbar.deleteSelectedRows：删除后同步 dirty，手工标记随行移动

async function saveNoteData(): Promise<boolean> {
  const sec = selectedNoteSection.value
  if (!sec || !props.projectId) return false
  const data = notePayload(sec.savedData, sec.headers, sec.editRows)
  try {
    const nk = currentNodeKey()
    const url = nk
      ? `${P_cn.data(props.projectId, props.year, sec.section_id)}?node_key=${encodeURIComponent(nk)}`
      : P_cn.data(props.projectId, props.year, sec.section_id)
    const result: any = await api.put(
      url,
      { data },
      { validateStatus: (s: number) => s < 600 },
    )
    if (result?.ok === false) throw Object.assign(new Error(result.error || '保存失败'), { status: 500 })
    sec.savedData = data
    ElMessage.success('附注数据已保存')
    clearNoteDirty()
    clearAutoSaveDraft()
    return true
  } catch (err) {
    handleApiError(err, '保存')
    return false
  }
}

async function exportNoteTemplate() {
  const sec = selectedNoteSection.value
  if (!sec?.headers) return
  // 走 useExcelIO 单一入口（B4 批）。三个显式关闭保持产物不变。
  await exportMultiSheetData({
    sheets: [{
      sheetName: '模板',
      rows: [sec.headers, ...(sec.editRows || []).map(() => sec.headers.map(() => ''))],
      colWidths: sec.headers.map(() => ({ wch: 18 })),
    }],
    fileName: `${sec.title || '附注'}_模板.xlsx`,
    applyStyles: false,
    successMessage: false,
  })
  ElMessage.success('模板已导出')
}

async function exportNoteData() {
  const sec = selectedNoteSection.value
  if (!sec?.headers) return
  const dataRows = sec.editRows.map((r: any) => sec.headers.map((_: string, j: number) => r[j] || ''))
  await exportMultiSheetData({
    sheets: [{
      sheetName: '数据',
      rows: [sec.headers, ...dataRows],
      colWidths: sec.headers.map(() => ({ wch: 18 })),
    }],
    fileName: `${sec.title || '附注'}_数据.xlsx`,
    applyStyles: false,
    successMessage: false,
  })
  ElMessage.success('数据已导出')
}

async function onNoteFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const sec = selectedNoteSection.value
  if (!sec?.headers) return
  try {
    // 走 useExcelIO 单一入口（B4 批）。原先取第一个 sheet + sheet_to_json(header:1)，
    // readSheetAoa 不传 sheetName 时同样取第一个，选项逐项透传保持等价。
    const { rows: json } = await readSheetAoa(file)
    let startRow = 0
    if (json.length > 0) {
      const firstRow = json[0].map((c: any) => String(c || '').trim())
      if (firstRow.some((c: string) => sec.headers.includes(c))) startRow = 1
    }
    const imported: any[] = []
    for (let i = startRow; i < json.length; i++) {
      const r = json[i]
      if (!r || !r.length) continue
      const obj: NoteEditRow = {}
      const manual: number[] = []
      for (let j = 0; j < sec.headers.length; j++) {
        obj[j] = r[j] != null ? String(r[j]) : ''
        if (j > 0 && obj[j] !== '') manual.push(j)
      }
      if (manual.length) obj.__manual = manual
      imported.push(obj)
    }
    if (imported.length) {
      sec.editRows.push(...imported)
      markNoteDirty()
      ElMessage.success(`已导入 ${imported.length} 行`)
    } else {
      ElMessage.warning('未解析到有效数据')
    }
  } catch (err: any) { handleApiError(err, '导入') }
  finally { if (noteFileRef.value) noteFileRef.value.value = '' }
}

// ─── 批量导入导出 ─────────────────────────────────────────────────────────────
/**
 * 生成不重复的 sheet 名（章节号前缀 + 标题，截断到 Excel 上限 31 字符）
 *
 * 🔴 改造前这个函数**名不副实**：它把名字 `add` 进 `usedNames` 但**从不检查**是否
 * 已存在 —— `usedNames` 是死参数，去重完全没实现。一旦两个名字截断后相同，
 * `book_append_sheet` 会抛错，导致**整批导出失败**（不是少一个 sheet）。
 *
 * 当前数据下撞不上：实测 282 个 section（18 个被截断）**零重复**，因为 `prefix`
 * 由唯一的 `section_id` 派生且位于名字最前，不同章节前几个字符就不同。
 * 但这个「不会撞」依赖章节编号体系的形态 —— 编号变长（如 `五-10-11-12-13`）或
 * 改成非唯一前缀就会失效。既然函数名已经承诺去重，就把它实现掉。
 */
function uniqueSheetName(usedNames: Set<string>, rawName: string, sectionId: string): string {
  const prefix = sectionId.replace(/^五-/, '').replace(/-/g, '.')
  const base = `${prefix} ${rawName}`.substring(0, 31)
  if (!usedNames.has(base)) {
    usedNames.add(base)
    return base
  }
  // 撞名时加 `~n` 后缀，并**为后缀预留位置**后再截断 —— 否则拼完又超 31，
  // Excel 侧仍会拒绝（这是加后缀去重最容易漏的一步）。
  for (let n = 2; n < 1000; n += 1) {
    const suffix = `~${n}`
    const candidate = base.substring(0, 31 - suffix.length) + suffix
    if (!usedNames.has(candidate)) {
      usedNames.add(candidate)
      return candidate
    }
  }
  // 兜底：极端情况下用时间戳，保证不抛错（宁可名字难看也不让整批导出失败）
  const fallback = base.substring(0, 24) + `~${Date.now() % 1000000}`
  usedNames.add(fallback)
  return fallback
}

async function batchExportAllData() {
  noteBatchLoading.value = true
  try {
    const usedNames = new Set<string>()
    const data = await api.get(P_cn.list(props.standard), {
      validateStatus: (s: number) => s < 600,
    })
    const groups = Array.isArray(data) ? data : (data ?? [])
    // 走 useExcelIO 单一入口（B4 批）：循环内累积 sheet 定义，循环后一次性导出。
    // uniqueSheetName 已把名字截到 31 字符内，故内部的 slice(0,31) 是无操作。
    const sheetDefs: { sheetName: string; rows: any[][]; colWidths: { wch: number }[] }[] = []
    let sheetCount = 0
    for (const g of groups) {
      for (const c of (g.children || [])) {
        const detail = await api.get(P_cn.detail(props.standard, c.section_id), {
          validateStatus: (s: number) => s < 600,
        })
        const sec = detail?.data ?? detail
        if (!sec?.headers?.length) continue
        const rows = sec.rows || []
        const name = uniqueSheetName(usedNames, sec.title || c.title || `表${sheetCount + 1}`, c.section_id)
        sheetDefs.push({
          sheetName: name,
          rows: [sec.headers, ...rows],
          colWidths: sec.headers.map(() => ({ wch: 16 })),
        })
        sheetCount++
      }
    }
    await exportMultiSheetData({
      sheets: sheetDefs,
      fileName: `合并附注_全部数据_${props.standard}.xlsx`,
      applyStyles: false,
      successMessage: false,
    })
    ElMessage.success(`已导出 ${sheetCount} 个附注表格`)
  } catch (e: any) { handleApiError(e, '导出') }
  finally { noteBatchLoading.value = false; showNoteBatchDialog.value = false }
}

async function batchExportAllTemplates() {
  noteBatchLoading.value = true
  try {
    const usedNames = new Set<string>()
    const data = await api.get(P_cn.list(props.standard), {
      validateStatus: (s: number) => s < 600,
    })
    const groups = Array.isArray(data) ? data : (data ?? [])
    // 同 batchExportAllData，仅差「只写表头行、不写数据行」（B4 批）。
    const sheetDefs: { sheetName: string; rows: any[][]; colWidths: { wch: number }[] }[] = []
    let sheetCount = 0
    for (const g of groups) {
      for (const c of (g.children || [])) {
        const detail = await api.get(P_cn.detail(props.standard, c.section_id), {
          validateStatus: (s: number) => s < 600,
        })
        const sec = detail?.data ?? detail
        if (!sec?.headers?.length) continue
        const name = uniqueSheetName(usedNames, sec.title || c.title || `表${sheetCount + 1}`, c.section_id)
        sheetDefs.push({
          sheetName: name,
          rows: [sec.headers],
          colWidths: sec.headers.map(() => ({ wch: 16 })),
        })
        sheetCount++
      }
    }
    await exportMultiSheetData({
      sheets: sheetDefs,
      fileName: `合并附注_模板_${props.standard}.xlsx`,
      applyStyles: false,
      successMessage: false,
    })
    ElMessage.success(`已导出 ${sheetCount} 个附注模板`)
  } catch (e: any) { handleApiError(e, '导出') }
  finally { noteBatchLoading.value = false; showNoteBatchDialog.value = false }
}

async function onNoteBatchImport(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file || !props.projectId) return
  noteBatchLoading.value = true
  try {
    // 走 useExcelIO 单一入口（B4 批）。本函数需遍历**全部** sheet 按标题匹配章节，
    // 故用整簿读取：一次解析拿到所有 sheet 的 AOA，与原实现等价。
    const { sheetNames, sheets } = await readWorkbookAoa(file)
    let matched = 0
    const data = await api.get(P_cn.list(props.standard), {
      validateStatus: (s: number) => s < 600,
    })
    const groups = Array.isArray(data) ? data : (data ?? [])
    const sectionMap: Record<string, string> = {}
    for (const g of groups) {
      for (const c of (g.children || [])) {
        sectionMap[c.title] = c.section_id
      }
    }
    for (const sheetName of sheetNames) {
      const sectionId = sectionMap[sheetName]
      if (!sectionId) continue
      const json: any[][] = sheets[sheetName]
      if (json.length < 2) continue
      const headers = json[0].map((c: any) => String(c || ''))
      const rows = json.slice(1).filter((r: any[]) => r.some(c => c != null && c !== '')).map((r: any[]) => r.map(c => String(c ?? '')))
      // Excel 导入属于人工录入：所有非空数值格都标为手工，后续「按公式填入」不得静默覆盖
      const editRows: NoteEditRow[] = rows.map((r: string[]) => {
        const item: NoteEditRow = {}
        const manual: number[] = []
        for (let col = 0; col < headers.length; col++) {
          item[col] = r[col] || ''
          if (col > 0 && item[col] !== '') manual.push(col)
        }
        if (manual.length) item.__manual = manual
        return item
      })
      const serialised = fromEditRows(headers, editRows)
      const nk = currentNodeKey()
      const importUrl = nk
        ? `${P_cn.data(props.projectId, props.year, sectionId)}?node_key=${encodeURIComponent(nk)}`
        : P_cn.data(props.projectId, props.year, sectionId)
      await api.put(
        importUrl,
        { data: { headers, ...serialised } },
        { validateStatus: (s: number) => s < 600 },
      )
      matched++
    }
    ElMessage.success(`已导入 ${matched} 个附注表格（共 ${sheetNames.length} 个 Sheet）`)
  } catch (e: any) { handleApiError(e, '导入') }
  finally {
    noteBatchLoading.value = false
    showNoteBatchDialog.value = false
    if (noteBatchFileRef.value) noteBatchFileRef.value.value = ''
  }
}

// ─── 公式管理（Sprint 1.5.3 收敛） ───────────────────────────────────────────
// ConsolNoteTab 不再自维护公式 dialog，统一走全局 FormulaManagerDialog
// （由 ThreeColumnLayout 顶层挂载，scope='consol_note'）。
function openNoteFormula() {
  const sec = selectedNoteSection.value
  if (!sec) { ElMessage.warning('请先选择章节'); return }
  // 项目级合并模块无 wpId，显式传完整上下文，避免全局挂载层退成普通报表域
  eventBus.emit('open-formula-manager', {
    nodeKey: 'consol_note',
    scope: 'consol_note',
    projectId: props.projectId,
    year: props.year,
    templateType: props.standard,
    noteSection: sec.section_id,
    noteSectionTitle: sec.title,
  })
}

async function exportNoteFormulas() {
  noteBatchLoading.value = true
  try {
    const headers = ['章节ID', '章节标题', '行号', '列号', '公式类型', '公式表达式', '数据来源', '说明']
    const data = await api.get(P_cn.list(props.standard), {
      validateStatus: (s: number) => s < 600,
    })
    const groups = Array.isArray(data) ? data : (data ?? [])
    const rows: string[][] = []
    for (const g of groups) {
      for (const c of (g.children || [])) {
        rows.push([c.section_id, c.title, '合计行', '所有数值列', 'SUM', '=SUM(明细行)', '自动计算', '合计行自动求和'])
        rows.push([c.section_id, c.title, '所有行', '期末列', 'TB_REF', `=TB(科目名,期末余额)`, '试算表', '从试算表提取期末余额'])
        rows.push([c.section_id, c.title, '所有行', '期初列', 'TB_REF', `=TB(科目名,期初余额)`, '试算表', '从试算表提取期初余额'])
      }
    }
    await exportMultiSheetData({
      sheets: [{
        sheetName: '公式规则',
        rows: [headers, ...rows],
        colWidths: headers.map((_, i) => ({ wch: i < 2 ? 20 : 14 })),
      }],
      fileName: `合并附注_公式模板_${props.standard}.xlsx`,
      applyStyles: false,
      successMessage: false,
    })
    ElMessage.success(`已导出公式模板`)
  } catch (e: any) { handleApiError(e, '导出') }
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
      const { rows: json } = await readSheetAoa(file)
      const ruleCount = Math.max(0, json.length - 1)
      ElMessage.success(`已解析 ${ruleCount} 条公式规则（需后端配合存储）`)
    }
  } catch (e: any) { handleApiError(e, '导入') }
  finally {
    noteBatchLoading.value = false
    if (noteFormulaFileRef.value) noteFormulaFileRef.value.value = ''
  }
}

async function fillAllByFormula() {
  if (noteBatchLoading.value) return
  if (noteDirty.value && !(await saveNoteData())) return
  noteBatchLoading.value = true
  try {
    const templateType = props.standard.includes('listed') ? 'listed' : 'soe'
    const formulaList = await listConsolNoteFormulas(templateType)
    const sectionIds = sectionIdsWithFormulas(formulaList)
    if (!sectionIds.length) {
      ElMessage.info('当前模板还没有合并附注公式')
      return
    }
    let filled = 0
    let kept = 0
    let blank = 0
    const failed: string[] = []
    let currentResult: ConsolNoteFillResult | null = null
    for (const sectionId of sectionIds) {
      try {
        const result = await fillConsolNoteByFormula(props.projectId, props.year, sectionId, templateType, currentNodeKey())
        filled += result.filled?.length || 0
        kept += result.kept_manual?.length || 0
        blank += result.blank?.length || 0
        if (sectionId === selectedNoteSection.value?.section_id) currentResult = result
      } catch (err: any) {
        const detail = err?.response?.data?.detail
        failed.push(`${sectionId}${typeof detail === 'string' && detail ? `：${detail}` : ''}`)
        if (err?.response?.status === 400 || err?.response?.status === 423) {
          noteFormulaError(err, '全部按公式填入')
          break
        }
      }
    }
    if (currentResult && selectedNoteSection.value) {
      const sec = selectedNoteSection.value
      sec.headers = currentResult.data?.headers || sec.headers
      sec.savedData = { ...(currentResult.data || {}) }
      sec.editRows = toEditRows(sec.headers, currentResult.data?.rows || [], currentResult.data?.manual_cells)
      clearNoteDirty()
      clearAutoSaveDraft()
    }
    const summary = `已处理 ${sectionIds.length - failed.length}/${sectionIds.length} 个有公式章节：填入 ${filled} 格，保留手工 ${kept} 格，取不到数 ${blank} 格`
    if (failed.length || blank) ElMessage.warning(`${summary}${failed.length ? `；失败 ${failed.length} 个章节` : ''}`)
    else ElMessage.success(summary)
  } catch (err: any) {
    noteFormulaError(err, '全部按公式填入')
  } finally {
    noteBatchLoading.value = false
    showNoteBatchDialog.value = false
  }
}

// ─── 审核 ────────────────────────────────────────────────────────────────────
async function onNoteAuditAll(_e?: Event) {
  showNoteAuditDialog.value = true
  noteAuditLoading.value = true
  noteAuditResults.value = []
  try {
    const entityCode = props.currentEntity.code || ''
    const data = await api.post(P_cn.auditAll(props.projectId, props.year), {
      standard: props.standard,
      company_code: entityCode,
      node_key: currentNodeKey(),
    }, { validateStatus: (s: number) => s < 600 })
    const result = data
    noteAuditResults.value = Array.isArray(result?.results) ? result.results : []
    noteAuditSummary.totalSections = result?.total_sections || 0
    noteAuditSummary.totalChecks = noteAuditResults.value.length
    noteAuditSummary.passCount = noteAuditResults.value.filter((r: any) => r.level === 'pass').length
    noteAuditSummary.errorCount = noteAuditResults.value.filter((r: any) => r.level === 'error').length
    noteAuditSummary.warnCount = noteAuditResults.value.filter((r: any) => r.level === 'warn').length
  } catch (err: any) {
    handleApiError(err, '全审')
  } finally { noteAuditLoading.value = false }
}

function auditRowClass({ row }: { row: any }) {
  if (row.level === 'error') return 'gt-audit-row-error'
  if (row.level === 'warn') return 'gt-audit-row-warn'
  return ''
}

async function exportAuditResults() {
  if (!noteAuditResults.value.length) return
  const headers = ['章节', '审核规则', '级别', '预期值', '实际值', '差异', '说明']
  const rows = noteAuditResults.value.map((r: any) => [
    r.section_title, r.rule_name,
    r.level === 'error' ? '异常' : r.level === 'warn' ? '警告' : '通过',
    r.expected, r.actual, r.difference, r.message,
  ])
  await exportMultiSheetData({
    sheets: [{
      sheetName: '审核结果',
      rows: [headers, ...rows],
      colWidths: [{ wch: 20 }, { wch: 30 }, { wch: 8 }, { wch: 14 }, { wch: 14 }, { wch: 14 }, { wch: 30 }],
    }],
    fileName: `合并附注_审核报告_${props.standard}.xlsx`,
    applyStyles: false,
    successMessage: false,
  })
  ElMessage.success('审核报告已导出')
}

async function auditCurrentNote() {
  const sec = selectedNoteSection.value
  if (!sec || !props.projectId) { ElMessage.warning('请先选择章节'); return }
  noteSingleAuditLoading.value = true
  try {
    const entityCode = props.currentEntity.code || ''
    const currentRows = sec.editRows.map((r: any) => sec.headers.map((_: string, j: number) => r[j] || ''))
    const data = await api.post(P_cn.audit(props.projectId, props.year, sec.section_id), {
      standard: props.standard,
      company_code: entityCode,
      node_key: currentNodeKey(),
      headers: sec.headers,
      rows: currentRows,
    }, { validateStatus: (s: number) => s < 600 })
    const result = data
    noteAuditResults.value = Array.isArray(result?.results) ? result.results : []
    noteAuditSummary.totalSections = 1
    noteAuditSummary.totalChecks = noteAuditResults.value.length
    noteAuditSummary.passCount = noteAuditResults.value.filter((r: any) => r.level === 'pass').length
    noteAuditSummary.errorCount = noteAuditResults.value.filter((r: any) => r.level === 'error').length
    noteAuditSummary.warnCount = noteAuditResults.value.filter((r: any) => r.level === 'warn').length
    showNoteAuditDialog.value = true
  } catch (err: any) {
    handleApiError(err, '单表审核')
  } finally { noteSingleAuditLoading.value = false }
}

function hasApiFailure(payload: any): boolean {
  return !!payload && (
    payload.error
    || (typeof payload.code === 'number' && payload.code >= 400)
    || (typeof payload.status === 'number' && payload.status >= 400)
  )
}

/**
 * 读取一个章节的模板和持久化数据。
 * 初次选择时没有持久化记录属于正常的模板空状态；已有记录读取失败则必须显式失败，
 * 不能悄悄用模板覆盖用户当前节点的数据。
 */
async function onNoteNodeClick(
  data: { section_id: string; title?: string },
): Promise<NoteRefreshResult> {
  const sectionId = String(data.section_id || '').trim()
  if (!sectionId) return noteRefreshResult('skipped', null, { reason: '未指定附注章节' })
  requestedSectionId.value = sectionId
  noteSelectedRows.value = []
  selectedCells.value = []
  noteBreakdown.value = null
  // 差额穿透初始节点 = 当前树节点（设计 §七）；用户显式另选只影响穿透视图，不改页面 nodeKey
  noteBreakdownNodeKey.value = currentNodeKey() || null
  noteBreakdownTarget.row = -1
  noteBreakdownTarget.col = -1
  const context = captureNoteSnapshot({ section_id: sectionId })
  if (!context) return noteRefreshResult('skipped', null, { reason: '当前项目或年度无效' })
  const ticket = noteRequestGuard.startRequest()
  try {
    const detail: any = await api.get(P_cn.detail(props.standard, sectionId), {
      validateStatus: (s: number) => s < 600,
      signal: ticket.signal,
    })
    if (noteRequestGuard.isStale(ticket)) {
      return noteRefreshResult('stale', context, { reason: '附注章节响应已过期' })
    }
    if (hasApiFailure(detail)) {
      throw new Error(noteErrorMessage(detail, '附注模板读取失败'))
    }
    const sec = detail?.data ?? detail
    if (!sec || sec.error) throw new Error(sec?.error || '附注模板读取失败')
    const headers = Array.isArray(sec.headers) ? sec.headers : []
    let rows = Array.isArray(sec.rows) ? sec.rows : []
    let savedContent: Record<string, unknown> = {}
    let updatedAt: string | null = null
    const saved: any = await api.get(noteDataUrl(context), {
      validateStatus: (s: number) => s < 600,
      signal: ticket.signal,
    })
    if (noteRequestGuard.isStale(ticket)) {
      return noteRefreshResult('stale', context, { reason: '附注持久化响应已过期' })
    }
    if (hasApiFailure(saved)) {
      throw new Error(noteErrorMessage(saved, '附注持久化数据读取失败'))
    }
    if (saved?.content && typeof saved.content === 'object') savedContent = { ...saved.content }
    updatedAt = saved?.updated_at || null
    if (Array.isArray(savedContent.rows)) rows = savedContent.rows

    const latest = currentRequestedNoteContext()
    if (!latest || !sameNoteContext(context, latest)) {
      return noteRefreshResult('stale', context, { reason: '附注节点或章节已切换' })
    }
    const editRows = toEditRows(headers, rows, savedContent.manual_cells)
    selectedNoteSection.value = {
      section_id: sec.section_id,
      title: sec.title,
      parent_section: sec.parent_section,
      headers,
      multiHeader: sec.multi_header || null,
      columnGroups: sec._column_groups || null,
      editRows,
      savedData: savedContent,
      // Req 20.4：以 ACNR NOTE 地址标识源单体附注 section（reaggregate 溯源），
      // 与统一寻址体系一致，可追溯；仅为标识，不参与计算。
      noteAddr: sourceNoteAddr(sec.section_id),
      // P3-a 补齐的行类型（total/subtotal/data），供合计行加粗渲染
      rowTypes: Array.isArray(sec._row_types) ? sec._row_types : null,
    }
    cellComments.loadComments(sec.section_id)
    // 异步加载跨表勾稽结果（不阻塞章节展示）
    loadCheckRules(sec.section_id)
    return noteRefreshResult(
      hasPersistedNoteContent(savedContent) ? 'done' : 'skipped',
      context,
      {
        persisted: hasPersistedNoteContent(savedContent),
        updatedAt,
        reason: hasPersistedNoteContent(savedContent) ? undefined : '当前章节暂无持久化数据',
      },
    )
  } catch (err: any) {
    if (noteRequestGuard.isStale(ticket)) {
      return noteRefreshResult('stale', context, { reason: '附注响应已过期' })
    }
    const reason = noteErrorMessage(err, '附注章节读取失败')
    ElMessage.error(`加载附注章节失败：${reason}`)
    return noteRefreshResult('failed', context, { reason })
  }
}

function switchToFourCol() {
  eventBus.emit('four-col-switch', { tab: 'notes' })
}

// CP-05：模板切换（国企↔上市）时重新加载当前已选章节，不保留旧配置
// R4.3：如有未保存内容须先确认
watch(() => props.standard, async (newStd, oldStd) => {
  if (newStd && oldStd && newStd !== oldStd && selectedNoteSection.value) {
    // 有未保存编辑时先确认
    if (noteDirty.value) {
      try {
        await ElMessageBox.confirm(
          '当前附注章节有未保存的编辑内容，切换模板后将丢失。是否继续？',
          '未保存提醒',
          { confirmButtonText: '继续切换', cancelButtonText: '取消', type: 'warning' },
        )
      } catch {
        // 用户取消 → emit 让父组件回退 standard
        emit('revert-standard', oldStd)
        return
      }
    }
    const currentSection = selectedNoteSection.value
    // 清除旧配置
    selectedNoteSection.value = null
    clearNoteDirty()
    clearAutoSaveDraft()
    // 用新模板重新加载同一章节
    onNoteNodeClick({ section_id: currentSection.section_id, title: currentSection.title })
  }
})

// ─── 生命周期 ────────────────────────────────────────────────────────────────
function onDocClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.closest('.gt-ucell-context-menu')) return
  noteCtx.closeContextMenu()
}

// Listen for catalog select events to load note sections
function onConsolCatalogSelect(data: ConsolCatalogSelectPayload) {
  if (!data) return
  if (data.type === 'note' && data.sectionId) {
    // Req 20.3：note section 引用经 ACNR resolveIndex('note:'+sectionId) 解析/跳转，
    // miss/异常回退现有 note 导航（jumpToNoteSection 内部处理）。
    jumpToNoteSection(data.sectionId, data.title)
  }
}

// Listen for tree aggregate events
function onTreeAggregate(detail: ConsolTreeAggregatePayload) {
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
function onNoteAuditAllEvent(_payload: ConsolNoteAuditAllPayload) {
  onNoteAuditAll()
}

/** 快捷键保存：保存当前附注数据 */
function onShortcutSave() {
  if (selectedNoteSection.value) {
    saveNoteData()
  }
}

onMounted(() => {
  document.addEventListener('click', onDocClick)
  eventBus.on('consol-catalog-select', onConsolCatalogSelect)
  eventBus.on('consol-tree-aggregate', onTreeAggregate)
  eventBus.on('consol-note-audit-all', onNoteAuditAllEvent)
  eventBus.on('shortcut:save', onShortcutSave)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
  eventBus.off('consol-catalog-select', onConsolCatalogSelect)
  eventBus.off('consol-tree-aggregate', onTreeAggregate)
  eventBus.off('consol-note-audit-all', onNoteAuditAllEvent)
  eventBus.off('shortcut:save', onShortcutSave)
  // 取消飞行中的附注请求
  noteRequestGuard.abort()
  autoSync.cancelPending()
})

// Expose for parent to call
defineExpose({
  onNoteNodeClick,
  reloadCurrentSectionAfterRefresh,
  handleReaggregate,
  selectedNoteSection,
  noteSelectedRows,
  selectedCells,
  drillDownCell,
  onNoteAuditAll,
  fillCurrentByFormula,
  openNoteBreakdown,
  openNoteBreakdownForSelection,
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
.gt-note-section-title { margin: 0; font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-text-primary); white-space: nowrap; }
.gt-note-actions { display: flex; gap: 4px; flex-wrap: wrap; }
.gt-note-table-wrap { flex: 1; min-height: 0; }
.gt-note-table-footer {
  display: flex; align-items: center; gap: 8px; padding: 6px 0; border-top: 1px solid var(--gt-color-border-purple); margin-top: 4px;
}

/* 附注空状态引导 */
.gt-note-empty-guide {
  display: flex; flex-direction: column; align-items: center;
  padding: 24px 20px 16px; gap: 16px;
}
.gt-note-empty-hero { text-align: center; }
.gt-note-empty-hero p { margin: 0 0 12px; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-tertiary); }
.gt-note-empty-actions { display: flex; gap: 8px; justify-content: center; align-items: center; }
.gt-four-col-pulse {
  animation: gt-four-col-glow 1.5s ease-in-out infinite, gt-four-col-bounce 1.5s ease-in-out infinite;
  font-weight: 700 !important;
  position: relative;
}
.gt-four-col-pulse::before {
  content: '⬇';
  position: absolute;
  top: -24px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 16px;
  animation: gt-arrow-bounce 1s ease-in-out infinite;
}
@keyframes gt-four-col-glow {
  0%, 100% { box-shadow: 0 0 0 0 rgba(230, 162, 60, 0.6); }
  50% { box-shadow: 0 0 0 10px rgba(230, 162, 60, 0); }
}
@keyframes gt-four-col-bounce {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.08); }
}
@keyframes gt-arrow-bounce {
  0%, 100% { transform: translateX(-50%) translateY(0); opacity: 1; }
  50% { transform: translateX(-50%) translateY(4px); opacity: 0.5; }
}
.gt-note-empty-steps {
  display: flex; gap: 12px; width: 100%;
}
.gt-note-step {
  flex: 1; min-width: 0;
  display: flex; gap: 8px; align-items: flex-start;
  padding: 12px; background: var(--gt-color-primary-bg); border-radius: 8px; border: 1px solid var(--gt-color-border-purple);
}
.gt-note-step-icon {
  font-size: var(--gt-font-size-md); font-weight: 700; color: var(--gt-color-primary); flex-shrink: 0; line-height: 1;
}
.gt-note-step-text { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); line-height: 1.6; }
.gt-note-step-text b { color: var(--gt-color-text-primary); font-size: var(--gt-font-size-xs); display: block; margin-bottom: 2px; }
.gt-note-step-text p { margin: 0; }
.gt-note-empty-info {
  font-size: var(--gt-font-size-xs); color: var(--gt-color-text-placeholder); text-align: center;
}

/* 审核结果行样式 */
:deep(.gt-audit-row-error td) { background: var(--gt-bg-danger) !important; }
:deep(.gt-audit-row-warn td) { background: var(--gt-bg-warning) !important; }

.gt-note-cell-text {
  display: block; padding: 2px 2px; font-size: var(--gt-font-size-sm); min-height: 20px;
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
:deep(.gt-comment-dialog .el-dialog__title) { color: var(--gt-color-text-inverse); font-size: var(--gt-font-size-base); }
:deep(.gt-comment-dialog .el-dialog__headerbtn .el-dialog__close) { color: rgba(255,255,255,0.8); }
:deep(.gt-comment-dialog .el-dialog__body) { padding: 16px 20px; }
.gt-comment-info {
  display: flex; gap: 0; margin-bottom: 14px;
  background: var(--gt-color-primary-bg); border-radius: 6px; overflow: hidden;
}
.gt-comment-info-item {
  flex: 1; padding: 10px 14px; border-right: 1px solid var(--gt-color-border-purple);
  display: flex; flex-direction: column; gap: 2px;
}
.gt-comment-info-item:last-child { border-right: none; }
.gt-comment-info-label { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); text-transform: uppercase; letter-spacing: 0.5px; }
.gt-comment-info-value { font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-text-primary); }
.gt-comment-info-value--primary { color: var(--gt-color-primary); }
:deep(.gt-comment-textarea .el-textarea__inner) {
  border: none; border-bottom: 1.5px solid var(--gt-color-border-purple); border-radius: 0;
  font-size: var(--gt-font-size-sm); line-height: 1.6; padding: 10px 4px; resize: none;
}
:deep(.gt-comment-textarea .el-textarea__inner:focus) {
  border-color: var(--gt-color-primary); box-shadow: none;
}

/* 紧凑行高 */
.gt-note-compact-table :deep(.el-table__row td) { height: 32px; }
.gt-note-compact-table :deep(.el-table__header th) { height: 34px; }
.gt-note-compact-table :deep(.el-input__inner) { height: 28px; font-size: var(--gt-font-size-sm); }

/* 合计行加粗 + 浅色底 */
.gt-note-compact-table :deep(.gt-note-total-row td) { font-weight: 700; background: #f5f3fa !important; }
.gt-note-compact-table :deep(.gt-note-subtotal-row td) { font-weight: 600; }

/* 手工单元格：按公式填入时后端保留；视觉上用麦田黄提示保护状态 */
.gt-note-cell-manual { background: var(--gt-color-wheat-light) !important; }
.gt-note-compact-table :deep(td.gt-note-manual-cell) { background: var(--gt-color-wheat-light) !important; }
.gt-note-breakdown-toolbar {
  display: flex; align-items: center; gap: 8px; margin-bottom: 10px;
  font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary);
}
.gt-note-breakdown-check--bad { color: var(--gt-color-coral); }
.gt-note-breakdown-children { padding: 8px 28px 12px; }
.gt-note-breakdown-children p { margin: 0 0 6px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
:deep(td.gt-note-elim-col), :deep(th.gt-note-elim-col) { background: var(--gt-color-wheat-light) !important; }
:deep(.gt-note-breakdown-target td) { box-shadow: inset 0 0 0 1px var(--gt-color-primary); }
</style>
