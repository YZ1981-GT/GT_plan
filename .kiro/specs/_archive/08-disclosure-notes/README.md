# 08 · 附注模块系列（2 个）

财务报表附注（披露）模块的全栈开发，从单体附注生成到合并附注、动态表格、模板继承、离线分发。

| Spec | 成果 |
|------|------|
| `disclosure-note-full-revamp` | 附注模块重写：173 章节生成 + 自动裁剪 + Word 导出 + 公式 DSL；46/47 tasks（剩外部 UAT/文档）；note_formula_generator.py 1331 行 + 50 note 测试 |
| `note-dynamic-tables-and-template-inheritance` | 全维度增强 v0.6.2（D1~D15 共 15 维度）：动态行列 / wp_data / Jinja 段落 / 章节序号 / 国企↔上市切换 / 合并附注 / 离线分发；实测 166/182≈90%（剩 16 项纯外部依赖：审计师标注 + 真合并项目 UAT）；10 核心 service + 50 note 测试实跑全绿 |

> 代码实证（2026-05-30）：两 spec 声称的核心 service 文件全部真实存在，note 测试 50 文件实跑通过，非空壳。剩余未完成项均为外部依赖（审计师数据 / 真实项目 UAT），代码侧已闭环。
