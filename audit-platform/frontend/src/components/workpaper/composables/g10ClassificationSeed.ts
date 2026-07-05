/** G10-4 分类适当性检查 — 28行4section种子数据 */
export interface G10ClassificationRowSeed {
  sectionNo: string
  sectionTitle: string
  checkItem: string
  auditRequirement: string
}

const SECTIONS: { no: string; title: string; items: string[] }[] = [
  {
    no: '(一)',
    title: '初始分类依据检查',
    items: [
      '管理层是否明确承担该金融负债的近期出售或回购目的',
      '是否属于集中管理的可辨认金融工具组合的一部分',
      '是否属于衍生金融负债且不符合套期会计要求',
      '初始确认时分类依据是否文档化',
      '分类决策是否经适当管理层批准',
      '分类依据是否与合同条款及业务实质一致',
      '是否存在应重分类而未重分类的情形',
    ],
  },
  {
    no: '(二)',
    title: '持有目的验证',
    items: [
      '近期出售/回购意图是否在报告期持续存在',
      '交易频率与持有期限是否支持交易性分类',
      '风险管理政策是否与交易性分类一致',
      '是否存在长期持有迹象与分类矛盾',
      '关联方交易是否影响持有目的判断',
      '管理层声明与实际操作是否一致',
      '持有目的变更是否及时评估并记录',
    ],
  },
  {
    no: '(三)',
    title: '公允价值计量适当性',
    items: [
      '公允价值层次划分是否合理',
      'Level3估值技术是否适当且可复核',
      '估值输入值来源是否可靠',
      '与上期估值方法是否一致或有合理变更',
      '公允价值变动是否计入当期损益',
      '估值结果与市场价格/第三方报价是否勾稽',
      '重大估值假设是否充分披露',
    ],
  },
  {
    no: '(四)',
    title: '重分类可能性评估',
    items: [
      '是否存在业务模式变更导致重分类',
      '重分类条件触发是否识别并评估',
      '重分类会计处理是否符合CAS22规定',
      '重分类日前后计量基础是否正确切换',
      '重分类是否影响比较信息列报',
      '重分类披露是否完整',
      '与G10-2明细表分类是否一致',
    ],
  },
]

export function buildG10ClassificationSeed(): G10ClassificationRowSeed[] {
  const rows: G10ClassificationRowSeed[] = []
  for (const sec of SECTIONS) {
    for (const item of sec.items) {
      rows.push({
        sectionNo: sec.no,
        sectionTitle: sec.title,
        checkItem: item,
        auditRequirement: `CAS22/37交易性金融负债分类：${sec.title} — ${item}`,
      })
    }
  }
  return rows
}

export const G10_CLASSIFICATION_SEED = buildG10ClassificationSeed()
