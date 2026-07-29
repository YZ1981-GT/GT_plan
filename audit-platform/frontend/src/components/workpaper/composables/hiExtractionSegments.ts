/**
 * H/I 循环四表取数分段配置注册表（per-wpCode）。
 * 各主入口用 `getHiExtractionSegments(wpCode)` 获取分段配置，
 * 传给 HiFourTableSourcePanel 作参数化渲染。
 *
 * Spec: .kiro/specs/hi-cycle-four-table-extraction/ Task 4.2
 */

export interface HiExtractionSegment {
  label: string
  accountCode: string
  expression: string
  anchorKey: string
}

const _REGISTRY: Record<string, HiExtractionSegment[]> = {
  H5: [
    { label: '油气资产原值(1631)', accountCode: '1631', expression: "TB('1631','期末余额')", anchorKey: 'H5-1-tb-amount' },
    { label: '累计折耗(1632)', accountCode: '1632', expression: "TB('1632','期末余额')", anchorKey: 'H5-1-tb-depletion' },
  ],
  H6: [
    { label: '固定资产清理(1606)', accountCode: '1606', expression: "TB('1606','期末余额')", anchorKey: 'H6-1-tb-amount' },
  ],
  H7: [
    { label: '生产性生物资产(1621)', accountCode: '1621', expression: "TB('1621','期末余额')", anchorKey: 'H7-1-tb-amount' },
  ],
  H8: [
    { label: '使用权资产原值(1901)', accountCode: '1901', expression: "TB('1901','期末余额')", anchorKey: 'H8-1-tb-amount' },
    { label: '累计折旧(190101)', accountCode: '190101', expression: "TB('190101','期末余额')", anchorKey: 'H8-1-tb-dep' },
  ],
  H9: [
    { label: '租赁负债(2205)', accountCode: '2205', expression: "TB('2205','期末余额')", anchorKey: 'H9-1-tb-amount' },
    { label: '未确认融资费用', accountCode: '220501', expression: "TB('220501','期末余额')", anchorKey: 'H9-1-tb-unearned' },
  ],
  H10: [
    { label: '资产处置损益(6115)', accountCode: '6115', expression: "TB('6115','审定数')", anchorKey: 'H10-1-tb-amount' },
  ],
  I1: [
    { label: '无形资产原值(1701)', accountCode: '1701', expression: "TB('1701','期末余额')", anchorKey: 'I1-1-tb-cost' },
    { label: '累计摊销(1702)', accountCode: '1702', expression: "TB('1702','期末余额')", anchorKey: 'I1-1-tb-amort' },
    { label: '减值准备(1703)', accountCode: '1703', expression: "TB('1703','期末余额')", anchorKey: 'I1-1-tb-impair' },
  ],
  I2: [
    { label: '开发支出(1717)', accountCode: '1717', expression: "TB('1717','期末余额')", anchorKey: 'I2-1-tb-amount' },
  ],
  I3: [
    { label: '商誉(1711)', accountCode: '1711', expression: "TB('1711','期末余额')", anchorKey: 'I3-1-tb-amount' },
  ],
  I4: [
    { label: '长期待摊费用(1801)', accountCode: '1801', expression: "TB('1801','期末余额')", anchorKey: 'I4-1-tb-amount' },
  ],
  I5: [
    { label: '其他非流动资产(1911)', accountCode: '1911', expression: "TB('1911','期末余额')", anchorKey: 'I5-1-tb-amount' },
  ],
  I6: [
    { label: '研发费用(6602)', accountCode: '6602', expression: "TB('6602','审定数')", anchorKey: 'I6-1-tb-amount' },
  ],
}

export function getHiExtractionSegments(wpCode: string): HiExtractionSegment[] {
  return _REGISTRY[wpCode] ?? []
}
