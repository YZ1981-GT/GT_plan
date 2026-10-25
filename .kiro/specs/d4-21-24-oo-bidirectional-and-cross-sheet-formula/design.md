# D4-21~24 设计

## 总体架构
先做模板裁决，再按裁决登记可管理 sheet。所有内容变更进入 ContentMutationService；phase5 仅提供 sheet descriptor、行身份和字段映射，bridge 负责 transport。任何失败 fail-closed。D4-22A 可因程序表属性保持 single_html。

## 决策
- DEC1：finder/index 核定模板后才决定 workbook、sheet、UUID、范围与档位。
- DEC2：D4-21 O 列保留枚举，UUID 只能使用裁决确定的其他空列；D4-21 I/K、D4-23 D/I/J mask 保护 OO 公式。
- DEC3：D4-22 复合 remark 分槽，同业列稳定键 `{slot}_{seq}`。
- DEC4：公式统一 F-SHELL/wp_formula effective definition；preset/custom/revert/Excel edit 均版本化；不写 field_overrides/remark。
- DEC5：表内 OO 算术留在 OOXML；跨表业务公式进入 wp_formula，不复制物理公式。
- DEC6：导航 refs 与公式 refs 分工不同，分别从 cross_wp_references 和 wp_formula 读取。
- DEC7：四表取数走 four_table scope/leaf aggregation，缺码拒绝或人工。

## 数据流
模板 descriptor → phase5 adapter → store projection。HTML flush 或 OO callback 均携带基线版本，ContentMutationService 三方合并后持久化；mask 列不被普通 projection 写入。公式预设经 F-SHELL upsert effective definition，后端执行并输出 IssueItem/HintItem，失败保留 failed/blocked。导入导出使用专用列头映射，派生列重算。A13 只消费 logic_check IssueItem。

## 各表
- D4-21：11 个受管字段；priceDiffRate 等模板 I/K 公式列非受管；O 列原值守卫。
- D4-22：rows/peers/transportExpense 分槽，同业列动态。
- D4-23：月份天然键；D/I/J 公式 mask。
- D4-24：布尔/枚举按列头映射；UUID 与是否扩双向由模板裁决。
- D4-22A：程序表无金额/公式/身份时不扩代码。

## Properties
### Property 1
**Validates: Requirements 1.1, 1.3, 2.1**
descriptor、行身份、mask 和三方合并共同决定可管理内容，普通投影不能覆盖公式。
### Property 2
**Validates: Requirements 2.2, 2.3, 4.1**
各表受管字段、复合槽和动态列经同步及 round-trip 不丢失。
### Property 3
**Validates: Requirements 3.1, 3.2, 3.3**
公式定义统一版本化，失败隔离，D4-21 从 canonical D4-1 snapshot 取数。
### Property 4
**Validates: Requirements 4.2, 5.1, 5.2**
派生列重算，导航与 A13 均来自各自唯一真源。
