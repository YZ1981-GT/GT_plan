"""公式全局设置 / 本项目适配 / 公式模板（spec formula-global-settings-sync）。

模块分工：

* ``definitions`` —— 六个域的公式位字段口径、规范化、哈希、相等判定；
* ``sync`` —— 纯函数同步内核：上游（全局 / 模板）变化时对每个项目分类并给出效果；
* ``stores`` —— 各域的存储适配（报表走 ``report_config``，其余走 ``formula_setting``）；
* ``effective`` —— 有效定义解析（本项目适配 → 订阅模板 → 全局 → 系统预设）；
* ``publish`` / ``project_ops`` —— 全局发布与项目侧操作；
* ``templates`` —— 公式模板的保存、共享、订阅、发布；
* ``propagation`` —— 有效定义变化后的过期标记与重算。

服务层只 flush，路由统一 commit。
"""
