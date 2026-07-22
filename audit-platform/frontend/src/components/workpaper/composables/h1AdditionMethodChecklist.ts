/**
 * H1-7 按增加方式的专项检查清单定义
 * 对齐致同模板编制提示第 2–10 条
 */

export interface MethodChecklistItem {
  key: string
  label: string
}

/** 增加方式 → 专项勾选清单 */
export const METHOD_CHECKLISTS: Record<string, MethodChecklistItem[]> = {
  外购: [
    { key: 'contract', label: '合同/订单齐全' },
    { key: 'invoice', label: '发票与账面金额勾稽' },
    { key: 'delivery', label: '发运/到货凭证' },
    { key: 'insurance', label: '保险单（如适用）' },
    { key: 'financing', label: '已关注延期付款融资成分' },
    { key: 'cutoff', label: '入账期间恰当' },
  ],
  在建工程转入: [
    { key: 'completion', label: '竣工决算或暂估依据齐全' },
    { key: 'acceptance', label: '验收/移交报告' },
    { key: 'cipMatch', label: '与在建工程记录勾稽' },
    { key: 'borrowing', label: '借款费用资本化金额核实' },
    { key: 'provisional', label: '暂估入账已标注且可后续调整' },
    { key: 'depStart', label: '达到预定可使用状态日起算折旧' },
  ],
  更新改造: [
    { key: 'valueReal', label: '增加价值真实（与费用化区分）' },
    { key: 'capCondition', label: '符合资本化条件（CAS4）' },
    { key: 'lifeReset', label: '已重新确定残值/折旧年限' },
    { key: 'docs', label: '改造合同、结算及验收齐全' },
  ],
  盘盈: [
    { key: 'valuation', label: '盘盈计价符合会计准则' },
    { key: 'pnl', label: '确认损益处理正确' },
    { key: 'stocktake', label: '与盘点记录勾稽（H1-10）' },
  ],
  融资租赁: [
    { key: 'leaseLink', label: '已参见租赁循环相关程序（H1-20等）' },
    { key: 'pv', label: '入账价值（最低租赁付款额现值等）正确' },
    { key: 'dep', label: '折旧政策与租赁期/使用寿命匹配' },
  ],
  投资者投入: [
    { key: 'agreement', label: '投资协议/章程约定齐全' },
    { key: 'appraisal', label: '评估报告或约定价值合理' },
    { key: 'transfer', label: '产权移交手续完备' },
    { key: 'accounting', label: '会计处理符合准则' },
  ],
  非货币交换: [
    { key: 'agreement', label: '交换协议齐全' },
    { key: 'fairValue', label: '公允价值计量恰当' },
    { key: 'transfer', label: '移交手续完备' },
    { key: 'accounting', label: '会计处理符合准则' },
  ],
  债务重组: [
    { key: 'agreement', label: '重组协议齐全' },
    { key: 'fairValue', label: '受让资产公允价值恰当' },
    { key: 'accounting', label: '债务重组损益处理正确' },
  ],
  企业合并: [
    { key: 'agreement', label: '合并协议/决议齐全' },
    { key: 'appraisal', label: '评估/购买日公允价值' },
    { key: 'transfer', label: '移交与权属变更手续' },
    { key: 'accounting', label: '合并会计处理正确' },
  ],
  其他: [
    { key: 'docs', label: '取得依据（合同/决议/报告）齐全' },
    { key: 'valuation', label: '入账价值合理' },
    { key: 'accounting', label: '会计处理正确' },
    { key: 'cutoff', label: '入账期间恰当' },
  ],
}

/** 解析增加方式对应清单（未知方式回退「其他」） */
export function getMethodChecklist(method: string): MethodChecklistItem[] {
  const m = (method || '').trim()
  if (!m) return []
  if (METHOD_CHECKLISTS[m]) return METHOD_CHECKLISTS[m]
  if (m.includes('在建')) return METHOD_CHECKLISTS['在建工程转入']
  return METHOD_CHECKLISTS['其他']
}

/** 清单完成度：已勾选(Y/N/NA) / 总项 */
export function calcChecklistProgress(
  checks: Record<string, string> | null | undefined,
  items: MethodChecklistItem[],
): { done: number; total: number; incomplete: boolean } {
  const total = items.length
  if (!total) return { done: 0, total: 0, incomplete: false }
  const map = checks || {}
  let done = 0
  for (const it of items) {
    const v = map[it.key]
    if (v === 'Y' || v === 'N' || v === 'NA') done++
  }
  return { done, total, incomplete: done < total }
}
