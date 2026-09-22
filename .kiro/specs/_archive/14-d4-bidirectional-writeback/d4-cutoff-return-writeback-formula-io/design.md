# Design Document

## Preserved structure
D4-17/18 保留截止行字段及方向语义；D4-19 保留 16 字段；D4-20 保留 policy/summary/assessment/provision/current-returns/post-returns/note/conclusion 六区和原 item_id。源 xlsx 逐 sheet 核定，是列头和结构唯一权威。

## Architecture
`_d4_import_export.py` 负责专用 parser/exporter 与两侧 item_id 映射；D4-20 主 sheet 无存储时清除死配置。公式使用 F-SHELL effective definition，`useD4FormulaEngine` 为同一定义适配，后端执行、前端预览、Excel 投影三者一致。统一平台 mutation/sync/三方合并/contract/representation/durable ack。发现先进入风险记录，人工确认方向、金额、证据后才能通过 `useD4InspectionWriteback` 生成 A13 请求；A13 与 D4-1 说明各自持久 ack、幂等与重试。

## Boundaries
不以 A13 代替双模式同步，不以 Excel 覆盖 HTML；不把 reason/“否”非空自动视为异常；未知分类/科目/分组不猜；动态 id 不重分配；解析失败不覆盖原数据。日期缺失/非法/零/未知分开处理。D4-17/18 仅跨期条件互斥，非跨期不得恒相反。

## Acceptance implementation
先源核定与共享 gate，再实现 IO、公式、发现/人工认定、持久联动，最后做行为守卫、变异和真实浏览器双向验收。
