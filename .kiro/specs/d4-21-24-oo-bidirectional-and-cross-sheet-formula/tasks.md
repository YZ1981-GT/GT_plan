# D4-21~24 任务

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":[1,2],"description":"模板裁决与descriptor"},{"wave":2,"tasks":[3,4],"description":"ContentMutationService与行身份"},{"wave":3,"tasks":[5,6],"description":"各表映射与动态store"},{"wave":4,"tasks":[7,8],"description":"F-SHELL公式与溯源"},{"wave":5,"tasks":[9,10,11],"description":"导入导出、A13和验证"}]}
```

## Wave 1
- [ ] 1.1 用运行时 finder/index 及权威模板逐表记录 D4-21、D4-22A、D4-22、D4-23、D4-24 的几何、公式、身份、O列保留值和 digest，形成裁决证据。
- [ ] 1.2 对每表判 full_bidirectional、limited_bidirectional 或 single_html；D4-22A 无金额/公式/身份时记录不适用，不扩代码。

## Wave 2
- [ ] 2.1 为裁决允许的表实现 descriptor、行身份和 mask；D4-21 避开 O 列，D4-23 保护 D/I/J，D4-21 保护 I/K。
- [ ] 2.2 将 HTML/OO 同步接入 ContentMutationService，带版本、三方合并、durable callback；冲突/身份失败 fail-closed。

## Wave 3
- [ ] 3.1 D4-21/22/23/24 对齐各自 store；D4-22 分槽保留 peers/transportExpense；同业列使用 `{slot}_{seq}`。
- [ ] 3.2 D4-21/24 专用 parser/export 按列头处理；D4-21 模板-only 列显式登记，派生列不采信。

## Wave 4
- [ ] 4.1 通过 F-SHELL 建立 preset/custom/effective definition、refs、params、version/hash 和失败状态；物理 OO 公式不重复入库。
- [ ] 4.2 用 four_table scope/叶子聚合取数；D4-21 读取 D4-1 canonical snapshot；导航 refs 与公式 refs 分离但可追溯。

## Wave 5
- [ ] 5.1 溯源从 cross_wp_references 读取，补条目只增不删；D4-24 D2 引用先完成语义裁决。
- [ ] 5.2 A13 只消费 logic_check IssueItem，复用共享件并锁定 6001/营业收入。
- [ ] 5.3 运行 projection/OOXML/DB formula/stale/round-trip 守卫及 Playwright 四表实测；校验 AC 引用、唯一 waves JSON、任务为数字且未勾选。
