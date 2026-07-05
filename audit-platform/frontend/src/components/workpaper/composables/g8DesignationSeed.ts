/** G8-5 指定适当性检查 — 36行4section种子数据（CAS22 FVOCI指定） */
export interface G8DesignationRowSeed {
  sectionNo: string
  sectionTitle: string
  checkItem: string
  auditRequirement: string
}

const SECTIONS: { no: string; title: string; items: string[] }[] = [
  {
    no: '(一)',
    title: '指定是否符合准则要求',
    items: [
      '被投资权益工具是否满足「非交易性」定义（非近期出售/回购目的）',
      '初始确认时是否作出不可撤销的 FVOCI 指定',
      '指定是否同时满足 CAS22 第19条四项条件',
      '是否获取管理层书面指定声明及董事会批准文件',
      '指定文件是否列明被投资单位清单及指定生效日期',
      '指定范围是否与财务报表附注披露一致',
      '是否存在应指定而未指定的非交易性权益工具',
      '指定会计处理是否与合同条款及业务实质一致',
      '与同行业披露惯例及监管要求是否一致',
    ],
  },
  {
    no: '(二)',
    title: '管理层持有目的验证',
    items: [
      '管理层是否声明持有目的为长期战略性投资而非交易',
      '报告期内是否存在频繁买卖或短期变现迹象',
      '投资决策流程是否支持非交易性持有目的',
      '风险管理政策是否与 FVOCI 指定一致',
      '关联方交易是否影响持有目的判断',
      '管理层访谈/声明与银行流水及交易记录是否一致',
      '持有目的变更是否及时评估并文档化',
      '新购入权益工具是否在初始确认时评估指定适当性',
      '处置计划是否表明原指定持有目的仍然成立',
    ],
  },
  {
    no: '(三)',
    title: '金融资产分类合规性',
    items: [
      '权益工具投资是否满足 CAS22 权益工具定义',
      '是否排除应分类为交易性金融资产的情形',
      '是否排除应适用权益法核算的长期股权投资',
      '公允价值是否能够可靠计量',
      'OCI 核算是否与指定声明一致（变动计入其他综合收益）',
      '股利收入是否按 CAS22 规定计入损益',
      '减值（如有）是否按准则要求处理',
      '与 G8-2 明细表指定 OCI 原因是否勾稽',
      '与 G8-4 公允价值层次及估值结论是否一致',
    ],
  },
  {
    no: '(四)',
    title: '指定的不可撤销性',
    items: [
      '管理层是否理解指定在初始确认后不可撤销',
      '是否存在试图通过处置重购规避不可撤销性的安排',
      '合并范围内主体间转移是否保持指定连续性',
      '指定变更（如适用）是否经恰当授权并充分披露',
      '比较期间指定政策是否一贯适用',
      '审计证据是否足以支持不可撤销性结论',
      '与治理层沟通记录是否涵盖指定适当性',
      '不合规指定是否识别并提出调整建议',
      '综合结论是否支持财务报表列报适当性',
    ],
  },
]

export function buildG8DesignationSeed(): G8DesignationRowSeed[] {
  const rows: G8DesignationRowSeed[] = []
  for (const sec of SECTIONS) {
    for (const item of sec.items) {
      rows.push({
        sectionNo: sec.no,
        sectionTitle: sec.title,
        checkItem: item,
        auditRequirement: `CAS22 FVOCI指定：${sec.title} — ${item}`,
      })
    }
  }
  return rows
}

export const G8_DESIGNATION_SEED = buildG8DesignationSeed()
