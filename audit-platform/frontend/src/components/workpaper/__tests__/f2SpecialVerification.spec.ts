/**
 * F2 存货特殊组 — 性能优化验证 (Task 13.2) + UI规范验证 (Task 13.3)
 *
 * 通过静态源码分析验证关键实现模式：
 * - 13.2: 虚拟滚动/分组折叠/区段Tab/固定列滚动列/defineAsyncComponent/公式纯函数
 * - 13.3: 13px字体/AI+复核按钮右对齐/公式列虚线tooltip/min-width/el-card/details折叠
 *
 * Validates: Requirements 22.1~22.8
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

const COMP_BASE = path.resolve(__dirname, '..')

function readSource(relativePath: string): string {
  return fs.readFileSync(path.join(COMP_BASE, relativePath), 'utf-8')
}

describe('Task 13.2: 性能优化验证', () => {
  describe('F2-72 供应商访谈记录正式问卷（对齐源模板）', () => {
    const src = readSource('f2-special/ipo/F2TabInterviewDetail.vue')

    it('呈现左侧卡片列表与右侧十一项问卷详情', () => {
      expect(src).toContain('list-card')
      expect(src).toContain('detail-panel')
      expect(src).toContain('qa-card')
      expect(src).toContain('questionSection')
      expect(src).toContain('isEditablePrompt')
      expect(src).toContain('访谈基本信息')
      expect(src).toContain('本份访谈结论')
    })

    it('支持弹窗新建、附件、签字与真实性声明', () => {
      expect(src).toContain('openCreateDialog')
      expect(src).toContain('el-dialog')
      expect(src).toContain('ItemAttachment')
      expect(src).toContain('参与访谈各方签字')
      expect(src).toContain('declarationAck')
      expect(src).toContain('真实性声明')
    })

    it('提供访谈编制示例弹窗（访谈记录与核对示例）', () => {
      expect(src).toContain('F2InterviewCheckExample')
      expect(src).toContain('查看编制示例')
      expect(src).toContain('exampleVisible')
      const summarySrc = readSource('f2-special/ipo/F2TabInterviewSummary.vue')
      expect(summarySrc).toContain('F2InterviewCheckExample')
      expect(summarySrc).toContain('查看编制示例')
      const hostSrc = readSource('GtF2InventorySpecial.vue')
      expect(hostSrc).toContain('isInterviewCheckExampleSheet')
      expect(hostSrc).toContain('F2InterviewCheckExample')
    })

    it('支持 F2-71/70/68 联动及说明/结论 AI', () => {
      expect(src).toContain('applyLinkage')
      expect(src).toContain('F2-71')
      expect(src).toContain('knownSuppliers')
      expect(src).toContain('interview-detail-note')
      expect(src).toContain('interview-detail-conclusion')
      expect(src).toContain('F2SheetToolbar')
    })
  })

  describe('F2-71 供应商访谈记录汇总（对齐源模板）', () => {
    const src = readSource('f2-special/ipo/F2TabInterviewSummary.vue')

    it('完整呈现源表访谈项目', () => {
      expect(src).toContain('访谈时间')
      expect(src).toContain('访谈原因')
      expect(src).toContain('被访谈公司注册地址')
      expect(src).toContain('实地走访公司地址')
      expect(src).toContain('接受访谈人员及身份')
      expect(src).toContain('访谈人员行程信息')
      expect(src).toContain('是否现场函证')
      expect(src).toContain('合同执行核对情况')
      expect(src).toContain('交易金额核对是否一致')
      expect(src).toContain('往来金额核对是否一致')
      expect(src).toContain('访谈记录索引')
    })

    it('支持卡片/矩阵切换及弹窗录入', () => {
      expect(src).toContain('卡片模式')
      expect(src).toContain('矩阵模式')
      expect(src).toContain("viewMode === 'card'")
      expect(src).toContain('el-dialog')
      expect(src).toContain('openCreateDialog')
      expect(src).toContain('saveDraft')
    })

    it('支持附件上传及 F2-68/70/72 底稿联动', () => {
      expect(src).toContain('ItemAttachment')
      expect(src).toContain('attSlot')
      expect(src).toContain('fillRegisteredAddress')
      expect(src).toContain('purchaseAmountOf')
      expect(src).toContain('F2-72:')
      expect(src).toContain('knownSuppliers')
    })

    it('提供地址不一致预警、完整度及说明/结论 AI', () => {
      expect(src).toContain('isAddressMismatch')
      expect(src).toContain('completionPct')
      expect(src).toContain('riskFlags')
      expect(src).toContain('interview-summary-note')
      expect(src).toContain('interview-summary-conclusion')
      expect(src).toContain('F2SheetToolbar')
    })
  })

  describe('F2-70 供应商信息核查转置矩阵（对齐源模板）', () => {
    const src = readSource('f2-special/ipo/F2TabSupplierInfoCheck.vue')

    it('按核查项目×供应商转置布局并冻结项目列', () => {
      expect(src).toContain('info-matrix')
      expect(src).toContain('table-scroll')
      expect(src).toContain('item-col')
      expect(src).toContain('新增供应商')
    })

    it('支持卡片/矩阵切换及弹窗录入（在线编辑走双模式页签）', () => {
      expect(src).toContain('卡片模式')
      expect(src).toContain('矩阵模式')
      expect(src).toContain("viewMode === 'card'")
      expect(src).toContain('el-dialog')
      expect(src).toContain('openCreateDialog')
      expect(src).toContain('openEditDialog')
      expect(src).toContain('saveDraft')
      expect(src).toContain('在线编辑')
    })

    it('完整呈现工商、股东、关键人员及穿透核查项目', () => {
      expect(src).toContain('统一社会信用代码')
      expect(src).toContain('网站IP地址')
      expect(src).toContain('注册资本/实缴资本')
      expect(src).toContain('股东1及持股比例')
      expect(src).toContain('股东5及持股比例')
      expect(src).toContain('董事长')
      expect(src).toContain('实际控制人')
      expect(src).toContain('是否为关联方')
      expect(src).toContain('是否列入失信名单')
      expect(src).toContain('信息来源')
    })

    it('提供完整度、风险提示及第18号舞弊特征提示', () => {
      expect(src).toContain('completionPct')
      expect(src).toContain('riskFlags')
      expect(src).toContain('第三方配合舞弊特征')
      expect(src).toContain('formula')
    })

    it('提供导入导出及审计说明/结论 AI', () => {
      expect(src).toContain('F2SheetToolbar')
      expect(src).toContain('supplier-info-note')
      expect(src).toContain('supplier-info-conclusion')
      expect(src).toContain('AI 填写审计说明')
      expect(src).toContain('AI 生成结论')
    })
  })

  describe('F2-69 供应商核查分组宽表（对齐源模板）', () => {
    const src = readSource('f2-special/ipo/F2TabSupplierChecklist.vue')

    it('呈现反向核查、函证资料及五种核查方式', () => {
      expect(src).toContain('反向核查')
      expect(src).toContain('函证资料')
      expect(src).toContain('工商资料查询')
      expect(src).toContain('互联网信息查询')
      expect(src).toContain('访谈/电话访谈')
      expect(src).toContain('实地走访')
    })

    it('提供金额差异、完成度及证据索引', () => {
      expect(src).toContain('row.isAmountMismatch')
      expect(src).toContain('row.completionPct')
      expect(src).toContain('最终索引号')
      expect(src).toContain('formula')
    })

    it('提供横向滚动、导入导出及说明/结论 AI', () => {
      expect(src).toContain('table-scroll')
      expect(src).toContain('overflow-x: auto')
      expect(src).toContain('F2SheetToolbar')
      expect(src).toContain('supplier-checklist-note')
      expect(src).toContain('supplier-checklist-conclusion')
    })
  })

  describe('F2-67 未披露关联方人员身份交叉核对（对齐源模板）', () => {
    const src = readSource('f2-special/ipo/F2TabUndisclosedParty.vue')

    it('使用宽矩阵和两列冻结布局', () => {
      expect(src).toContain('match-table')
      expect(src).toContain('table-scroll')
      expect(src).toContain('class="sticky seq"')
      expect(src).toContain('class="sticky name"')
    })

    it('完整呈现源表人员匹配维度及自动合计', () => {
      expect(src).toContain('个人供应商')
      expect(src).toContain('供应商法人')
      expect(src).toContain('合同签订人')
      expect(src).toContain('财务部门')
      expect(src).toContain('营销部门')
      expect(src).toContain('供应商与公司员工或者其家属存在关系（Y/N）')
      expect(src).toContain('row.total')
    })

    it('提供导入导出及审计说明/结论 AI', () => {
      expect(src).toContain('F2SheetToolbar')
      expect(src).toContain('undisclosed-party-note')
      expect(src).toContain('undisclosed-party-conclusion')
      expect(src).toContain('AI 填写审计说明')
      expect(src).toContain('AI 生成结论')
    })
  })

  describe('F2-66 关联方市场价分组月度矩阵（对齐源模板）', () => {
    const src = readSource('f2-special/ipo/F2TabRelatedPartyMarket.vue')

    it('使用分组卡片与市场价宽表', () => {
      expect(src).toContain('group-card')
      expect(src).toContain('market-table')
      expect(src).toContain('table-scroll')
    })

    it('呈现采购均价、月初月末市场价与区间判断', () => {
      expect(src).toContain('采购均价')
      expect(src).toContain('市场价格（挂牌价）均价')
      expect(src).toContain('月初')
      expect(src).toContain('月末')
      expect(src).toContain('采购价格是否处于市场价区间')
    })

    it('提供审计说明/结论 AI 与导入导出工具条', () => {
      expect(src).toContain('related-market-note')
      expect(src).toContain('related-market-conclusion')
      expect(src).toContain('F2SheetToolbar')
      expect(src).toContain('AI 填写审计说明')
      expect(src).toContain('AI 生成结论')
    })
  })

  describe('F2-64 四区块月度矩阵（对齐源模板）', () => {
    const src = readSource('f2-special/ipo/F2TabUnitConsumption.vue')

    it('使用 matrix-table 宽表与横向滚动', () => {
      expect(src).toContain('matrix-table')
      expect(src).toContain('table-scroll')
    })

    it('完整呈现成本构成、成本衔接、单位成本和材料耗用', () => {
      expect(src).toContain('一、生产成本构成')
      expect(src).toContain('二、生产成本本期')
      expect(src).toContain('三、产品单位成本分析')
      expect(src).toContain('四、产品主要原材料耗用分析')
    })

    it('按本年/上年固定12个月并生成合计', () => {
      expect(src).toContain('structureByPeriod')
      expect(src).toContain('flowByPeriod')
      expect(src).toContain('unitByPeriod')
      expect(src).toContain('materialByPeriod')
      expect(src).toContain('row-total')
    })

    it('包含同行业单位成本比较', () => {
      expect(src).toContain('peerCompanies')
      expect(src).toContain('同行业公司比较')
    })

    it('四段说明及结论均有AI能力', () => {
      expect(src.match(/@ai="runAi/g)?.length).toBe(4)
      expect(src).toContain('unit-consumption-conclusion')
    })
  })

  describe('F2-61 采购价格 四区块矩阵（对齐源模板）', () => {
    const src = readSource('f2-special/ipo/F2TabPurchasePrice.vue')

    it('使用 matrix-table 宽表 + 横向滚动', () => {
      expect(src).toContain('matrix-table')
      expect(src).toContain('table-scroll')
      expect(src).toContain('overflow-x: auto')
    })

    it('包含入库金额/数量/单价/市场单价四区块', () => {
      expect(src).toContain('入库金额（单位：元）')
      expect(src).toContain('入库数量')
      expect(src).toContain('入库单价（单位：元）')
      expect(src).toContain('市场单价（单位：元）')
    })

    it('材料列 sticky 固定', () => {
      expect(src).toContain('sticky')
      expect(src).toContain('col-name')
    })

    it('包含问题解答第18号第三方舞弊提示', () => {
      expect(src).toContain('fraudTip')
    })
  })

  describe('F2-65 询价函附件 OCR 确认回写', () => {
    const src = readSource('f2-special/ipo/F2TabRelatedPartyInquiry.vue')

    it('底部双栏含附件面板与OCR上传', () => {
      expect(src).toContain('evidence-panel')
      expect(src).toContain('ItemAttachment')
      expect(src).toContain('上传并 OCR')
      expect(src).toContain('inquiry-letter')
    })

    it('OCR结果先预览二次编辑再确认回写', () => {
      expect(src).toContain('ocrPreviewVisible')
      expect(src).toContain('confirmOcrWriteback')
      expect(src).toContain('overwriteExisting')
      expect(src).toContain('applyOcrFields')
    })
  })

  describe('F2-66 市场价附件 OCR 确认回写', () => {
    const src = readSource('f2-special/ipo/F2TabRelatedPartyMarket.vue')

    it('底部双栏含行情附件面板与OCR', () => {
      expect(src).toContain('evidence-panel')
      expect(src).toContain('market-quote')
      expect(src).toContain('ItemAttachment')
      expect(src).toContain('f2-ipo-soft')
    })

    it('OCR确认回写主表', () => {
      expect(src).toContain('confirmOcrWriteback')
      expect(src).toContain('applyOcrFields')
    })
  })

  describe('F2-61 采购价格浅色分区导航', () => {
    const src = readSource('f2-special/ipo/F2TabPurchasePrice.vue')
    it('使用浅色卡片与区块导航', () => {
      expect(src).toContain('f2-ipo-soft')
      expect(src).toContain('uc-nav')
      expect(src).toContain('f2IpoSoftStyles.css')
    })
  })

  describe('F2-62 原材料单价分析 AI 文本框', () => {
    const src = readSource('f2-special/ipo/F2TabUnitPrice.vue')

    it('审计说明和分析结论均提供 AI 功能', () => {
      expect(src).toContain("runAi('unit-price-note')")
      expect(src).toContain("runAi('unit-price-conclusion')")
      expect(src).toContain('AI 填写审计说明')
      expect(src).toContain('AI 生成分析结论')
      expect(src).toContain('useF2SpecialAiGenerate')
    })

    it('AI 生成内容分别回填并保存两个文本框', () => {
      expect(src).toContain('up.auditNote.value = text')
      expect(src).toContain('saveAuditConclusion(text)')
      expect(src).toContain('aiContext()')
    })
  })

  describe('F2-55(37列) 宽表横向滚动 + 固定列', () => {
    const src = readSource('f2-special/contract/F2TabContractCostDetail.vue')

    it('使用 matrix-table 宽表布局', () => {
      expect(src).toContain('matrix-table')
      expect(src).toContain('table-scroll')
    })

    it('包含期初/增加/减少/期末/审计调整/审定列组', () => {
      expect(src).toContain('账面期初余额')
      expect(src).toContain('账面本期增加')
      expect(src).toContain('账面本期减少')
      expect(src).toContain('账面期末余额')
      expect(src).toContain('审计调整')
      expect(src).toContain('期末审定余额')
    })

    it('项目信息列 sticky 固定', () => {
      expect(src).toContain('sticky')
      expect(src).toContain('col-name')
    })

    it('配置横向滚动最小宽度', () => {
      expect(src).toContain('min-width: 3400px')
      expect(src).toContain('overflow-x: auto')
    })
  })

  describe('F2-68 本年/上年重要供应商双区宽矩阵', () => {
    const src = readSource('f2-special/ipo/F2TabSupplierStructure.vue')

    it('本年、上年分别呈现并冻结序号和供应商', () => {
      expect(src).toContain('本年重要供应商')
      expect(src).toContain('上年重要供应商')
      expect(src).toContain('class="sticky seq"')
      expect(src).toContain('class="sticky supplier"')
    })

    it('完整呈现采购业务条件及合理性核查列', () => {
      expect(src).toContain('主要采购产品')
      expect(src).toContain('采购业务情况')
      expect(src).toContain('信用期')
      expect(src).toContain('支付方式')
      expect(src).toContain('运输方式')
      expect(src).toContain('采购额与供应商规模是否匹配')
      expect(src).toContain('采购产品与经营范围是否匹配')
    })

    it('有横向滚动、导入导出及说明/结论 AI', () => {
      expect(src).toContain('table-scroll-wrap')
      expect(src).toContain('overflow-x: auto')
      expect(src).toContain('F2SheetToolbar')
      expect(src).toContain('supplier-structure-note')
      expect(src).toContain('supplier-structure-conclusion')
    })
  })

  describe('defineAsyncComponent lazy加载', () => {
    const src = readSource('GtF2InventorySpecial.vue')

    it('使用 defineAsyncComponent 延迟加载非首屏组件', () => {
      expect(src).toContain('defineAsyncComponent')
    })

    it('GtOnlyOfficeSheet 通过 defineAsyncComponent 懒加载', () => {
      expect(src).toMatch(/defineAsyncComponent\(\(\)\s*=>\s*import\(['"]\.\/GtOnlyOfficeSheet\.vue['"]\)\)/)
    })

    it('复核对话与版本链 Host 由 Runtime Boundary 统一挂载（不在本组件内联）', () => {
      // 历史上 GtWpVersionTrail/GtWpReviewDialogHost 在本组件懒加载，
      // 现已上移到 GtWorkpaperRuntimeHosts（经 GtWpRenderer 挂载）
      const hosts = readSource('GtWorkpaperRuntimeHosts.vue')
      expect(hosts).toContain('GtWpVersionTrail')
      expect(hosts).toContain('GtWpReviewDialogHost')
    })
  })

  describe('公式引擎纯函数（无副作用/无recomputation）', () => {
    const src = readSource('composables/useF2SpecialFormulaEngine.ts')

    it('所有导出函数均为纯函数（export function）', () => {
      const exportFns = src.match(/^export function \w+/gm) || []
      expect(exportFns.length).toBeGreaterThanOrEqual(10)
    })

    it('不包含 ref/reactive/computed（无Vue响应式副作用）', () => {
      expect(src).not.toContain("from 'vue'")
      expect(src).not.toMatch(/\bref\s*\(/)
      expect(src).not.toMatch(/\breactive\s*\(/)
      expect(src).not.toMatch(/\bcomputed\s*\(/)
    })

    it('不包含异步操作（无fetch/axios/await）', () => {
      expect(src).not.toContain('async ')
      expect(src).not.toContain('await ')
      expect(src).not.toContain('fetch(')
      expect(src).not.toContain('axios')
    })

    it('不包含console/localStorage等副作用', () => {
      expect(src).not.toContain('console.')
      expect(src).not.toContain('localStorage')
      expect(src).not.toContain('sessionStorage')
    })
  })
})

describe('Task 13.3: UI规范验证', () => {
  // 收集所有特殊组组件源码
  const componentFiles = [
    'f2-special/contract/F2TabContractCostDetail.vue',
    'f2-special/ipo/F2TabPurchasePrice.vue',
    'f2-special/ipo/F2TabUnitConsumption.vue',
    'f2-special/ipo/F2TabRelatedPartyMarket.vue',
    'f2-special/ipo/F2TabUndisclosedParty.vue',
    'f2-special/ipo/F2TabSupplierStructure.vue',
    'f2-special/ipo/F2TabSupplierChecklist.vue',
    'f2-special/ipo/F2TabSupplierInfoCheck.vue',
    'f2-special/ipo/F2TabInterviewSummary.vue',
    'f2-special/ipo/F2TabInterviewDetail.vue',
  ]
  const sources = componentFiles.map(readSource)

  describe('13px 字体全局验证', () => {
    it.each(componentFiles)('%s 使用 13px 字体（直接或 --wp-font-size 变量兜底）', (file) => {
      const src = readSource(file)
      const has13px = src.includes('font-size: 13px')
        || src.includes('var(--wp-font-size, 13px)')
      expect(has13px).toBe(true)
    })
  })

  describe('AI + 复核按钮右对齐 (F2SheetToolbar)', () => {
    it.each(componentFiles)('%s 包含 F2SheetToolbar 组件', (file) => {
      const src = readSource(file)
      expect(src).toContain('F2SheetToolbar')
    })

    it.each(componentFiles)('%s toolbar 使用 flex 布局实现右对齐', (file) => {
      const src = readSource(file)
      expect(src).toContain('display: flex')
      expect(src).toContain('gap:')
    })
  })

  describe('公式列虚线下划线 + cursor:help + tooltip', () => {
    it.each(componentFiles)('%s 有公式列视觉标识（.formula 或 .calc 灰底列）', (file) => {
      const src = readSource(file)
      expect(src.includes('.formula') || src.includes('.calc ') || src.includes('.calc-cell')).toBe(true)
    })

    it('公式样式包含 underline dotted 虚线效果', () => {
      // 至少一个组件有完整的公式虚线样式定义
      const hasUnderlineDotted = sources.some(
        (s) => s.includes('underline dotted') || s.includes('text-decoration: underline dotted'),
      )
      expect(hasUnderlineDotted).toBe(true)
    })

    it('公式元素使用 span.formula 包裹计算值', () => {
      const hasFormulaSpan = sources.some((s) => s.includes('class="formula"'))
      expect(hasFormulaSpan).toBe(true)
    })
  })

  describe('min-width 自适应列宽', () => {
    it('F2TabContractCostDetail 使用 min-width 保证宽表列宽', () => {
      const src = readSource('f2-special/contract/F2TabContractCostDetail.vue')
      expect(src).toContain('min-width')
    })

    it('F2TabUnitConsumption 使用 min-width 自适应列', () => {
      const src = readSource('f2-special/ipo/F2TabUnitConsumption.vue')
      expect(src).toContain('min-width')
    })
  })

  describe('审计结论区域验证', () => {
    it.each(componentFiles)('%s 包含审计说明/结论textarea', (file) => {
      const src = readSource(file)
      // 每个组件都应有 textarea 用于审计说明
      expect(src).toContain('type="textarea"')
    })
  })

  describe('编制提示 / 引导区域', () => {
    it('F2TabUnitConsumption 有提示信息区域', () => {
      const src = readSource('f2-special/ipo/F2TabUnitConsumption.vue')
      expect(src).toContain('guidance-details')
      expect(src).toContain('编制提示')
    })
  })
})
