"""Task 29 变异检验：append-only timeline 投影、required scenario 推导、脱敏与告警。
spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 29
Requirements: 5.10, 5.11, 10.7, 12.10, 12.11, 12.12, 13.1, 13.2, 13.4, 13.5, 13.6,
              13.7, 13.8, 13.9, 13.10, 14.16
Properties: **P52 / P53 / P54 / P68 / P69 / P70 / P71**

用法（仓库根目录，`py -3` 不是 `python`）::

    py -3 backend/scripts/diagnose/mutate_task29_timeline_evidence_guards.py --list
    py -3 backend/scripts/diagnose/mutate_task29_timeline_evidence_guards.py --check-anchors
    py -3 backend/scripts/diagnose/mutate_task29_timeline_evidence_guards.py --run R01,R02

═══ 为什么用 `_mutation_kit.span` ═══

与 Tasks 26~28 同：`span.run_cli` 不落 `.mutbak`（内存持有变异前字节 + sha256 还原自证），
且本任务多条判据的本体是**相邻若干行的组合** —— 例如 `_matches_secret_key` 的「先看敏感词
再看末段角色词」两步、`check_projection` 的「先取 stateful 再建链」。拆成单行锚点就变成了
另一条判据；而 `line=` 绝对行号一改文件就失效。

═══ 六类落点 ═══

1. **脱敏三层**（R01~R10）—— 键名层/值形态层/容器层各自被绕开时是否有判据打红。
   最贵的一条是 R03：把「末段角色词」规则从「命中敏感词之后」提到前面，功能上
   `Authorization` 仍被屏蔽，只有 `authorization_result` 那条正向判据会红。
2. **allowlist 两侧锁**（R11~R14）—— 加宽（登记凭证键）、清空（空组/删组）、
   角色词名单被污染。四条各自独立异常。
3. **指标归因**（R21~R28）—— 六维必填、route 级禁 participant、封闭 result 域、
   禁止压平、`record_outcome` 的必填参数、有界缓冲。
4. **告警三向锁**（R31~R37）—— 规则↔目录↔13.9 条目、result_filter 拼错、
   去重键可归因、阈值/恢复窗口/runbook。
5. **timeline 投影**（R41~R48）—— 四条独立缺陷码、stateful 过滤、服务端时钟、
   `LOCATORS` 的 ClassVar 形态、recovery timeline 的结构性无 operation。
6. **evidence 推导与重算**（R51~R64）—— close 谓词的 `or`、替换只许两条、
   digest 输入完整性、`ScenarioKind` 与 V151 同域、kind 推导顺序、stale 逐条、
   跨 entry/跨 scenario 复用、schema 欠账登记表。

═══ 刻意避开的无效变异形态 ═══

* 改注释/docstring —— 判据全部走 AST 或行为，注释里逐字出现的被禁符号不会自伤；
* 锚定 `try:` / `except` 行 —— 会把整个异常块语义一起改掉，判定不可归因；
* 在正确实现下恒不触发的分支 —— 例如 `check_projection` 的 `empty_timeline`
  在真库上不可达（V151 禁 DELETE），所以它的判据只放在离线文件、变异也只指向离线用例。

═══ 判定四态与责任方 ═══

RED = 守卫有效；GREEN = **守卫缺陷**（该属性没被锁住）；WRONG-TEST = 污染残留或锚点落错
位置；ANCHOR-MISS = **脚本缺陷**。退出码不作判据 —— 只看失败名集合的差集，并逐条核对
`restored` / `restored_sha256`。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit.span import SpanMutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

RD = "backend/app/services/workpaper_sync/redaction.py"
MX = "backend/app/services/workpaper_sync/metrics.py"
AL = "backend/app/services/workpaper_sync/alerting.py"
TL = "backend/app/services/workpaper_sync/timeline.py"
EV = "backend/app/services/workpaper_sync/evidence.py"
R = "backend/app/routers/wp_sync_router.py"

OFF = "test_task29_timeline_evidence"
PG = "test_task29_timeline_evidence_pg"


def _off(node: str) -> str:
    return f"{OFF}.py::{node}"


def _pg(node: str) -> str:
    return f"{PG}.py::{node}"


MUTATIONS: list[SpanMutation] = [
    # ═══════════════════════════════════════════════════════════════════
    # R01~R14：RedactionPolicy 三层过滤 + allowlist 两侧锁
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="R01", path=RD,
        anchor="                if self._matches_secret_key(child_key):\n"
               "                    acc.secret.append(child_key)\n"
               "                    out[child_key] = self.secret_placeholder\n"
               "                    continue",
        new="                if False:\n"
            "                    acc.secret.append(child_key)\n"
            "                    out[child_key] = self.secret_placeholder\n"
            "                    continue",
        want=_off(
            "TestRedactionReverseLeak::test_no_credential_shape_survives_projection"
        ),
        why="键名层被短路 ⇒ `Authorization` 落到 allowlist 判定（未登记）而被**丢弃**而不是"
            "屏蔽。丢弃看起来也没泄露，但 `secret_keys` 报告为空 ⇒ 无法区分「屏蔽了」与"
            "「压根没查」；更要紧的是嵌套里的 `jwt` 会随父键 `detail` 一起被原样投影",
    ),
    SpanMutation(
        id="R02", path=RD,
        anchor="                if not self.is_allowed_key(child_key):\n"
               "                    acc.dropped.append(child_key)\n"
               "                    continue",
        new="                if False:\n"
            "                    acc.dropped.append(child_key)\n"
            "                    continue",
        want=_off(
            "TestRedactionReverseLeak::test_no_credential_shape_survives_projection"
        ),
        why="allowlist 层被短路 ⇒ 变成 blacklist：未登记的 `incoming_cell_values` 原样"
            "落库，审计底稿的真实金额进 timeline（Requirement 13.8 明确禁止）",
    ),
    SpanMutation(
        id="R03", path=RD,
        anchor="        segments = self._segments(key)\n"
               "        if segments and segments[-1] in self.non_credential_role_suffixes:\n"
               "            return False\n"
               "        return True",
        new="        segments = self._segments(key)\n"
            "        if any(seg in self.non_credential_role_suffixes for seg in segments):\n"
            "            return False\n"
            "        return True",
        want=_off("TestRedactionAllowlistIsTwoWayLocked::"
                  "test_role_suffix_list_is_closed_both_ways"),
        why="角色词豁免从**末段锚定**退化成「任一段命中即放行」⇒ `digest_token` / "
            "`state_authorization` / `sha256_secret` 因首段是角色词而被判非凭证，长期凭证"
            "原样落 timeline。这是本处唯一承载行为的不变量。"
            "﹙本条的前身是「两步顺序交换」，实测为**等价变异**：判据是合取，交换后 10 个"
            "探针键行为逐一相同 ⇒ 恒 GREEN。同时暴露出真实缺口 —— 原守卫只有放行侧"
            "（`token_digest`）断言、屏蔽侧一条都没有，故末段锚定实际无守卫。已改为对两个"
            "方向都断言，并把变异换到真实不变量上。﹚",
    ),
    SpanMutation(
        id="R04", path=RD,
        anchor='            if pattern.rule_id == "url_with_credentials_or_query":\n'
               "                text = pattern.regex.sub(lambda m: self.redact_url(m.group(0)), text)",
        new='            if pattern.rule_id == "url_with_credentials_or_query":\n'
            "                text = text",
        want=_off("TestRedactionReverseLeak::"
                  "test_no_credential_shape_survives_projection"),
        why="URL 分支不再降级 ⇒ `error_detail` 里的完整下载 URL（含 query 里的短期凭证与"
            "内网 host）原样保留。AC 10.7 明文禁止",
    ),
    SpanMutation(
        id="R05", path=RD,
        anchor="        suffix = f\"?{self.url_query_placeholder}\" if (parts.query or parts.fragment) else \"\"\n"
               "        return f\"{parts.scheme}://{shown_host}{path}{suffix}\"",
        new="        suffix = f\"?{parts.query}\" if (parts.query or parts.fragment) else \"\"\n"
            "        return f\"{parts.scheme}://{shown_host}{path}{suffix}\"",
        want=_off("TestRedactionReverseLeak::"
                  "test_no_credential_shape_survives_projection"),
        why="query 被原样拼回 —— 「只去了 host 没去 query」是最容易犯的半截脱敏，而"
            "「URL 变短了」的粗判据看不出来",
    ),
    SpanMutation(
        id="R06", path=RD,
        anchor="        host = (parts.hostname or \"\").lower()\n"
               "        shown_host = host if host in self.host_allowlist else self.unlisted_host_placeholder",
        new="        host = (parts.hostname or \"\").lower()\n"
            "        shown_host = host",
        want=_off("TestRedactionReverseLeak::"
                  "test_no_credential_shape_survives_projection"),
        why="未登记 host 不再降级 ⇒ 内网拓扑（DocServer 的真实地址）进日志/证据",
    ),
    SpanMutation(
        id="R07", path=RD,
        anchor="        if isinstance(value, (bytes, bytearray, memoryview)):\n"
               "            # 字节永远不进日志/证据：长度是唯一有用且非敏感的事实。\n"
               "            acc.secret.append(key)\n"
               "            return f\"{self.secret_placeholder}({len(bytes(value))}B)\"",
        new="        if isinstance(value, (bytes, bytearray, memoryview)):\n"
            "            return bytes(value).hex()",
        want=_off("TestRedactionReverseLeak::test_bytes_never_reach_the_record"),
        why="bytea 列（asyncpg 返回 memoryview）被 hex 化写进记录 ⇒ 整份载荷字节进 timeline",
    ),
    SpanMutation(
        id="R08", path=RD,
        anchor="        if depth > self.limits.max_depth:\n"
               "            acc.depth_exceeded = True\n"
               "            return self.truncated_placeholder",
        new="        if False:\n"
            "            acc.depth_exceeded = True\n"
            "            return self.truncated_placeholder",
        want=_off("TestRedactionReverseLeak::"
                  "test_depth_and_container_limits_bound_the_record"),
        why="深度门被短路 ⇒ 一条 event detail 能把任意深的嵌套结构整份写进库"
            "（Requirement 5.12 只要求记 identity 与 code）",
    ),
    SpanMutation(
        id="R09", path=RD,
        anchor="            kept = items[: self.limits.max_container_items]\n"
               "            if len(items) > len(kept):\n"
               "                acc.truncated.append(key)",
        new="            kept = items\n"
            "            if len(items) > len(kept):\n"
            "                acc.truncated.append(key)",
        want=_off("TestRedactionReverseLeak::"
                  "test_depth_and_container_limits_bound_the_record"),
        why="容器上限被摘掉 ⇒ 十万行的 projection 列表整份进记录",
    ),
    SpanMutation(
        id="R10", path=RD,
        anchor="        if len(scrubbed) > self.limits.max_exception_chars:\n"
               "            return scrubbed[: self.limits.max_exception_chars] + self.truncated_placeholder\n"
               "        return scrubbed",
        new="        return scrubbed",
        want=_off("TestRedactionReverseLeak::"
                  "test_exception_text_is_scrubbed_and_truncated"),
        why="异常文本不再截断 ⇒ 一条 SQL 参数超长的 asyncpg 异常能把整批业务值写进 "
            "`error_detail`（本 spec 里那类异常动辄几千字符）",
    ),
    SpanMutation(
        id="R11", path=RD,
        anchor="        conflicts = sorted(k for k in self.allowlist if self._matches_secret_key(k))\n"
               "        if conflicts:",
        new="        conflicts: list[str] = []\n"
            "        if conflicts:",
        want=_off("TestRedactionAllowlistIsTwoWayLocked::"
                  "test_no_allowlisted_key_is_a_credential_name"),
        why="加宽方向的门被摘掉 ⇒ 只要把 `authorization_header` 登记进 allowlist 就能"
            "合法泄露长期凭证。这是「allowlist 两侧锁」的加宽半边",
    ),
    SpanMutation(
        id="R12", path=RD,
        anchor="            if not isinstance(keys, Sequence) or isinstance(keys, (str, bytes)) or not keys:\n"
               "                raise RedactionConfigError(\n"
               "                    f\"allowlist.{group}.keys 必须是非空数组 —— 空组等于悄悄放弃该组判据\"\n"
               "                )",
        new="            if keys is None:\n"
            "                keys = []",
        want=_off("TestRedactionAllowlistIsTwoWayLocked::"
                  "test_emptying_a_group_is_refused"),
        why="清空方向的门被摘掉 ⇒ 把任一分组清空后该组字段全被丢弃，timeline 少一整段"
            "而没有任何报错。这是「allowlist 两侧锁」的清空半边",
    ),
    SpanMutation(
        id="R13", path=RD,
        anchor="        missing_groups = [g for g in ALLOWLIST_GROUPS if g not in allowlist]\n"
               "        if missing_groups:",
        new="        missing_groups: list[str] = []\n"
            "        if missing_groups:",
        want=_off("TestRedactionAllowlistIsTwoWayLocked::"
                  "test_dropping_a_group_entirely_is_refused"),
        why="整组缺失不再 fail closed ⇒ 删掉 `digest` 分组后所有 hash 被丢弃，"
            "而 hash 正是「服务端可重算」的唯一凭据（AC 14.14）",
    ),
    SpanMutation(
        id="R14", path=RD,
        anchor="        overlap = sorted(set(self.non_credential_role_suffixes) & set(self.secret_key_patterns))\n"
               "        if overlap:",
        new="        overlap: list[str] = []\n"
            "        if overlap:",
        want=_off("TestRedactionAllowlistIsTwoWayLocked::"
                  "test_role_suffix_may_not_overlap_a_credential_word"),
        why="角色词名单可以包含凭证词 ⇒ 把 `token` 加进角色词后，`access_token` 这类"
            "键立刻放行。末段规则就成了凭证放行通道",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # R21~R28：指标归因与禁止压平
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="R21", path=MX,
        anchor="        missing = sorted(\n"
               "            dim.value for dim in definition.required_dims if labels.get(dim.value) is None\n"
               "        )\n"
               "        if missing:",
        new="        missing: list[str] = []\n"
            "        if missing:",
        want=_off("TestMetricCatalog::"
                  "test_operation_scoped_metrics_require_all_six_dims"),
        why="必填归因维度不再校验 ⇒ 指标可以只带 room 就记数，「按 requested+canonical "
            "operation/application 归因」这条 AC 13.7 的要求彻底落空",
    ),
    SpanMutation(
        id="R22", path=MX,
        anchor="        forbidden = FORBIDDEN_DIMS.get(definition.attribution, frozenset())\n"
               "        present_forbidden = sorted(\n"
               "            dim.value for dim in forbidden if labels.get(dim.value) is not None\n"
               "        )\n"
               "        if present_forbidden:",
        new="        present_forbidden: list[str] = []\n"
            "        if present_forbidden:",
        want=_off("TestMetricCatalog::test_route_scoped_metrics_forbid_participant"),
        why="route 级指标可以带 participant ⇒ 聚合 callback 事件被归因到 route "
            "participant，即「route 当作者」（AC 5.1 / 10.9 明文禁止）",
    ),
    SpanMutation(
        id="R23", path=MX,
        anchor="        dedicated = FORBIDDEN_GENERIC_ERROR_OUTCOMES.get(outcome)\n"
               "        if dedicated is not None:",
        new="        dedicated = None\n"
            "        if dedicated is not None:",
        want=_off("TestMetricCatalog::"
                  "test_each_forbidden_outcome_refuses_the_generic_error_metric"),
        why="same-app fold / 跨 participant 409 / 无 successor 恢复态可以压成通用 error —— "
            "Task 29 正文明文禁止。压平的实际伤害：值班按重试 runbook 处理一个需要重新"
            "授权 + 新 generation 的状态",
    ),
    SpanMutation(
        id="R24", path=MX,
        anchor="        if result is None:\n"
               "            raise MetricAttributionError(\n"
               "                f\"{definition.name} 声明了 result_domain={list(definition.result_domain)}，\"",
        new="        if result is None:\n"
            "            return\n"
            "        if False:\n"
            "            raise MetricAttributionError(\n"
            "                f\"{definition.name} 声明了 result_domain={list(definition.result_domain)}，\"",
        want=_off("TestMetricCatalog::"
                  "test_result_is_mandatory_when_the_metric_has_a_closed_domain"),
        why="有封闭 result 域的指标允许不传 result ⇒ 「没抛异常就 +1」这种写法重新变得"
            "可行，而 Task 22/26 在 durable 之后**刻意不抛**",
    ),
    SpanMutation(
        id="R25", path=MX,
        anchor="        if result not in definition.result_domain:\n"
               "            raise MetricAttributionError(",
        new="        if False:\n"
            "            raise MetricAttributionError(",
        want=_off("TestMetricCatalog::"
                  "test_result_is_mandatory_when_the_metric_has_a_closed_domain"),
        why="result 不再限制在封闭域 ⇒ 拼错的结果值（`ok` / `success`）静默写入，"
            "告警规则的 result_filter 永不命中",
    ),
    SpanMutation(
        id="R26", path=MX,
        anchor="        result: str | None,\n"
               "        landed: bool,\n"
               "        value: float = 1.0,",
        new="        result: str | None = None,\n"
            "        landed: bool = True,\n"
            "        value: float = 1.0,",
        want=_off("TestMetricCatalog::"
                  "test_record_outcome_has_no_default_for_result_or_landed"),
        why="`result` / `landed` 变成可省参数。功能上什么都不变（现有调用方全都显式传），"
            "只有签名判据会红 —— 而它正是「失败不得被记成成功」的唯一结构性保障",
    ),
    SpanMutation(
        id="R27", path=MX,
        anchor="        self._samples: deque[MetricSample] = deque(maxlen=int(buffer_size))",
        new="        self._samples: deque[MetricSample] = deque()",
        want=_off("TestMetricCatalog::test_sample_buffer_is_bounded"),
        why="样本缓冲变无界 ⇒ 容量门（6000 会话 / 20 applications/s × 10 分钟）下长跑进程"
            "内存单调涨。功能测试全绿，只有上界判据会红",
    ),
    SpanMutation(
        id="R28", path=MX,
        anchor="        unknown = sorted(set(labels) - known)\n"
               "        if unknown:",
        new="        unknown: list[str] = []\n"
            "        if unknown:",
        want=_off("TestMetricCatalog::test_unknown_label_name_is_refused"),
        why="维度名不再受词汇表约束 ⇒ 同一件事在两处用 `room` 与 `room_id` 两个标签名，"
            "按 room 聚合时数据一分为二而看板照常出图",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # R31~R37：AlertRuleRegistry 三向双向锁
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="R31", path=AL,
        anchor="    for metric in sorted(required_metrics - covered_metrics):\n"
               "        problems.append(",
        new="    for metric in sorted(set()):\n"
            "        problems.append(",
        want=_off("TestAlertRegistry::"
                  "test_an_alert_required_metric_without_a_rule_is_reported"),
        why="「alert_required 指标必须有规则」这一侧被摘掉 ⇒ 加了指标忘加规则时"
            "「已覆盖」是假的（故障永远静默）。"
            "﹙原判据是 `test_registry_self_check_is_clean`（断言自检为空）与"
            "`test_every_alert_required_metric_has_exactly_one_rule`（断言注册表数据），"
            "实测恒 GREEN：前者在合规数据上无论删哪条分支都仍为空，后者根本不经过"
            "`validate_registry`。已换成注入型判据 —— 摘掉一条规则后断言本分支**独有**的"
            "措辞 + 指标名恰出现一次。﹚",
    ),
    SpanMutation(
        id="R32", path=AL,
        anchor="    for label, condition in sorted(REQUIREMENT_13_9_CONDITIONS.items()):\n"
               "        if condition not in registry.rules_by_condition:",
        new="    for label, condition in sorted({}.items()):\n"
            "        if condition not in registry.rules_by_condition:",
        want=_off("TestAlertRegistry::"
                  "test_a_missing_requirement_13_9_condition_is_reported_by_its_label"),
        why="Requirement 13.9 的逐条覆盖核对被摘掉 ⇒ 删掉任一类规则不再打红。"
            "13.9 列了十四类，漏一类就是那类故障永远无人知道。"
            "﹙原判据同 R31，恒 GREEN；且此处还叠了一层遮蔽 —— 紧随其后的 "
            "`for condition in AlertCondition` 兜底分支对同一个缺口也会报，"
            "所以判据不能只断言「有问题」，必须断言报的是 **13.9 的中文标签**"
            "而不是 enum 名，否则兜底分支会替它顶班。﹚",
    ),
    SpanMutation(
        id="R38", path=AL,
        anchor="    for metric in sorted(covered_metrics - required_metrics):\n"
               "        problems.append(",
        new="    for metric in sorted(set()):\n"
            "        problems.append(",
        want=_off("TestAlertRegistry::"
                  "test_a_rule_for_a_non_alert_required_metric_is_reported"),
        why="加宽方向被摘掉 ⇒ 规则引用了 `alert_required=False` 的指标不再报。"
            "与 R31 合起来才是两侧锁死：少规则报、多规则也报。单侧锁的实际后果是"
            "「把指标的 alert_required 翻成 False」可以在不动规则表的情况下悄悄"
            "解除一类告警的覆盖承诺",
    ),
    SpanMutation(
        id="R33", path=AL,
        anchor="        unknown_results = sorted(set(result_filter) - set(definition.result_domain))\n"
               "        if unknown_results:",
        new="        unknown_results: list[str] = []\n"
            "        if unknown_results:",
        want=_off("TestAlertRegistry::test_a_typo_in_result_filter_is_refused"),
        why="拼错的 result 过滤值不再被拒 ⇒ 规则**静默不触发**。这是告警系统最坏的失效"
            "形态：看板全绿、规则也在、只是永远不命中",
    ),
    SpanMutation(
        id="R34", path=AL,
        anchor="        illegal = sorted(d.value for d in dims if d not in allowed)\n"
               "        if illegal:",
        new="        illegal: list[str] = []\n"
            "        if illegal:",
        want=_off("TestAlertRegistry::test_an_ungroupable_dedupe_dim_is_refused"),
        why="去重键可以用该指标根本带不出的维度 ⇒ 取不到值时所有告警合成一条"
            "（`participant_id=-`），两个 room 的故障看起来是同一个",
    ),
    SpanMutation(
        id="R35", path=AL,
        anchor="        if threshold <= 0:\n"
               "            raise AlertConfigError(",
        new="        if False:\n"
            "            raise AlertConfigError(",
        want=_off("TestAlertRegistry::test_zero_threshold_is_refused"),
        why="阈值可以为 0 ⇒ 规则对空事件流也触发，告警立刻被噪音淹掉（等价于关掉告警）",
    ),
    SpanMutation(
        id="R36", path=AL,
        anchor="        if recovery.window_seconds < window_seconds:\n"
               "            raise AlertConfigError(",
        new="        if False:\n"
            "            raise AlertConfigError(",
        want=_off("TestAlertRegistry::"
                  "test_recovery_window_shorter_than_trigger_window_is_refused"),
        why="恢复窗口可以短于触发窗口 ⇒ 故障仍在发生时就宣布恢复",
    ),
    SpanMutation(
        id="R37", path=AL,
        anchor="        if len(runbook) < MIN_RUNBOOK_CHARS:\n"
               "            raise AlertConfigError(",
        new="        if False:\n"
            "            raise AlertConfigError(",
        want=_off("TestAlertRegistry::test_a_placeholder_runbook_is_refused"),
        why="`TODO` 也算 runbook ⇒ Requirement 13.9 的「每条规则须定义 runbook」变成形式",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # R41~R48：timeline 投影与 recovery 隔离
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="R41", path=TL,
        anchor="        expected = [index + 1 for index in range(len(ordered))]\n"
               "        if [e.sequence_no for e in ordered] != expected:\n"
               "            defects.append(ProjectionDefect.sequence_gap)",
        new="        expected = [index + 1 for index in range(len(ordered))]\n"
            "        if False:\n"
            "            defects.append(ProjectionDefect.sequence_gap)",
        want=_off("TestProjectionOracle::"
                  "test_a_deleted_middle_event_is_caught_as_a_sequence_gap"),
        why="号段连续性判据被短路。四条一致性判据各有独立缺陷码，共用一个码时靠后的会被"
            "靠前的遮蔽 —— 本 spec 已三次踩到，所以逐条变异",
    ),
    SpanMutation(
        id="R42", path=TL,
        anchor="        for previous, following in zip(stateful, stateful[1:]):\n"
               "            if following.from_state is not None and following.from_state != previous.to_state:\n"
               "                defects.append(ProjectionDefect.transition_chain_broken)",
        new="        for previous, following in zip(stateful, stateful[1:]):\n"
            "            if False:\n"
            "                defects.append(ProjectionDefect.transition_chain_broken)",
        want=_off("TestProjectionOracle::"
                  "test_a_forged_event_breaks_the_transition_chain"),
        why="转换链判据被短路 ⇒ 伪造一条 from_state 接不上的 event 不再被发现",
    ),
    SpanMutation(
        id="R43", path=TL,
        anchor="                and following.occurred_at < previous.occurred_at\n"
               "            ):\n"
               "                defects.append(ProjectionDefect.clock_regressed)",
        new="                and False\n"
            "            ):\n"
            "                defects.append(ProjectionDefect.clock_regressed)",
        want=_off("TestProjectionOracle::test_a_regressed_server_clock_is_caught"),
        why="服务端时钟单调判据被短路 ⇒ 乱序写入的 event 不再被发现（AC 13.10）",
    ),
    SpanMutation(
        id="R44", path=TL,
        anchor="        if current_state is not None and last_state is not None and last_state != current_state:\n"
               "            defects.append(ProjectionDefect.state_diverged)",
        new="        if False:\n"
            "            defects.append(ProjectionDefect.state_diverged)",
        want=_off("TestProjectionOracle::"
                  "test_current_state_diverging_from_the_last_event_is_caught"),
        wants=(_pg("TestAppendOnlyProjection::"
                   "test_editing_current_state_directly_is_caught"),),
        why="「current state 只是 timeline 的投影」这条 P68 的核心判据被短路 ⇒ 直接 "
            "`UPDATE` operation.state 后读侧毫无察觉。真库侧同名判据也应红",
    ),
    SpanMutation(
        id="R45", path=TL,
        anchor="        stateful = [e for e in ordered if e.to_state is not None]",
        new="        stateful = list(ordered)",
        want=_off("TestProjectionOracle::"
                  "test_a_stateless_sequence_fold_event_is_not_a_defect"),
        why="回归变异：不再过滤无状态事件 ⇒ 每次合法的 same-application sequence fold"
            "（`to_state` 为 NULL）都会误报断链与分叉。这是**真实缺陷**，而 fold 恰恰是"
            "协同下最常见的事件（Task 29 要求它「不 self-stale」）",
    ),
    SpanMutation(
        id="R46", path=TL,
        anchor="    illegal = [key for key in order_keys if key not in SERVER_ORDER_KEYS]\n"
               "    if illegal:",
        new="    illegal: list[str] = []\n"
            "    if illegal:",
        want=_off("TestTimelineQueryContract::"
                  "test_only_server_clock_columns_may_order_the_timeline"),
        why="排序键不再限制在服务端列 ⇒ 浏览器 trace 时间可以决定 timeline 顺序，"
            "AC 13.10 的「不得伪造服务端 callback 顺序」失效",
    ),
    SpanMutation(
        id="R47", path=TL,
        anchor="    LOCATORS: ClassVar[tuple[str, ...]] = (",
        new="    LOCATORS: tuple[str, ...] = (",
        want=_off("TestTimelineQueryContract::"
                  "test_locators_is_a_classvar_not_a_field"),
        why="回归变异：`ClassVar` 改回普通注解 ⇒ `@dataclass` 把 LOCATORS 收成实例字段，"
            "`TimelineQuery(LOCATORS=())` 就能让 `validate()` 恒通过。**真实踩过**："
            "写成 `Final[...]` 时同样会变成字段（PEP 591 只影响类型检查）",
    ),
    SpanMutation(
        id="R48", path=TL,
        anchor="        if not self.locators():\n"
               "            raise TimelineUsageError(",
        new="        if False:\n"
            "            raise TimelineUsageError(",
        want=_off("TestTimelineQueryContract::"
                  "test_a_query_without_any_locator_is_refused"),
        why="无条件 timeline 查询被放行 ⇒ 整库 event 可被一次拉出，且绕开 "
            "authorization-before-resource（AC 10.6）",
    ),
    SpanMutation(
        id="R49", path=TL,
        anchor="    claimed_operation_id: uuid.UUID | None\n"
               "    claimed_application_id: uuid.UUID | None\n"
               "    recovery_request_id: uuid.UUID | None\n"
               "    events: tuple[TimelineEvent, ...] = ()",
        new="    claimed_operation_id: uuid.UUID | None\n"
            "    claimed_application_id: uuid.UUID | None\n"
            "    recovery_request_id: uuid.UUID | None\n"
            "    operation_events: tuple[TimelineEvent, ...] = ()\n"
            "    events: tuple[TimelineEvent, ...] = ()",
        want=_off("TestRecoveryTimelineHasNoOperation::"
                  "test_the_recovery_timeline_type_has_no_operation_events_field"),
        wants=(_pg("TestRecoveryCaseHasNoOperationBeforeClaim::"
                   "test_the_pre_claim_payload_has_no_operation_events_key"),),
        why="recovery timeline 又能装 operation 事件 ⇒ AC 13.5 的「claim 前不得借 "
            "operation timeline 伪造 operation」重新只剩注释约定。结构判据比行为判据强："
            "字段不存在就不可能填",
    ),
    SpanMutation(
        id="R50", path=TL,
        anchor="        return (\n"
               "            self.claimed_operation_id is not None\n"
               "            and self.claimed_application_id is not None\n"
               "            and self.recovery_request_id is not None\n"
               "        )",
        new="        return (\n"
            "            self.claimed_operation_id is not None\n"
            "            or self.claimed_application_id is not None\n"
            "            or self.recovery_request_id is not None\n"
            "        )",
        want=_off("TestRecoveryTimelineHasNoOperation::"
                  "test_three_entities_flag_requires_all_three"),
        why="三实体判据的 `and` 改 `or` ⇒ 只要有一个就宣称齐备，download-only 的 case "
            "会被判成已 claim（AC 5.8 要求 download-only 三者恒为 0）",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # R51~R64：evidence 推导、DB 取值域、stale 与复用
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="R51", path=EV,
        anchor="    return profile.editable and (\n"
               "        capability is Capability.bidirectional or profile.room_model is RoomModel.shared\n"
               "    )",
        new="    return profile.editable and (\n"
            "        capability is Capability.bidirectional and profile.room_model is RoomModel.shared\n"
            "    )",
        want=_off("TestClosePredicate::"
                  "test_shared_room_alone_is_enough_even_without_bidirectional"),
        wants=(_off("TestDerivationOverTheRealManifest::"
                    "test_the_close_predicate_hits_every_shared_editable_entry"),),
        why="AC 12.12 的谓词 `or` 改 `and`。真 manifest 里当前**没有** bidirectional entry，"
            "所以 179 个 shared-room entry 会**全部**悄悄少八个 close 场景，而「场景都跑过了」"
            "的计数仍然满分。这是本任务最贵的一条落点",
    ),
    SpanMutation(
        id="R52", path=EV,
        anchor="    if close_required:\n"
               "        scenarios.extend(CLOSE_SCENARIOS)",
        new="    if False:\n"
            "        scenarios.extend(CLOSE_SCENARIOS)",
        want=_off("TestClosePredicate::"
                  "test_shared_room_alone_is_enough_even_without_bidirectional"),
        why="close 场景整组不再追加 ⇒ exactly-one close-capture 从此无人验收",
    ),
    SpanMutation(
        id="R53", path=EV,
        anchor="    if authority_model not in SUBSTITUTING_AUTHORITY_MODELS:\n"
               "        raise ScenarioSubstitutionError(",
        new="    if False:\n"
            "        raise ScenarioSubstitutionError(",
        want=_off("TestRequiredScenarioDerivation::"
                  "test_projection_contract_may_not_substitute"),
        why="替换不再限制在枚举 authority model ⇒ `projection_contract` 也能把字段级两"
            "场景换掉，AC 12.12「替换规则由服务端 registry 守卫，禁止自由文本豁免」失效",
    ),
    SpanMutation(
        id="R54", path=EV,
        anchor="    kept = [s for s in scenarios if s.scenario_id not in FIELD_LEVEL_SCENARIOS]\n"
               "    removed = len(scenarios) - len(kept)\n"
               "    if removed != len(FIELD_LEVEL_SCENARIOS):",
        new="    kept = [\n"
            "        s for s in scenarios\n"
            "        if s.scenario_id not in FIELD_LEVEL_SCENARIOS\n"
            "        and s.scenario_id != \"download_only_zero_three_entities\"\n"
            "    ]\n"
            "    removed = len(FIELD_LEVEL_SCENARIOS)\n"
            "    if removed != len(FIELD_LEVEL_SCENARIOS):",
        want=_off("TestRequiredScenarioDerivation::"
                  "test_only_the_two_field_level_scenarios_may_be_substituted"),
        why="替换时顺手多摘掉一条不可替换场景（download-only）。AC 12.12 明文只允许替换"
            "字段级两场景；多摘一条时「替换发生了」的粗判据仍然满足",
    ),
    SpanMutation(
        id="R55", path=EV,
        anchor="        if self.expects_zero_entities:\n"
               "            return ScenarioKind.download_only\n"
               "        if self.expects_recovery_case and not self.expects_application:\n"
               "            return ScenarioKind.recovery_reject",
        new="        if self.expects_recovery_case and not self.expects_application:\n"
            "            return ScenarioKind.recovery_reject\n"
            "        if self.expects_zero_entities:\n"
            "            return ScenarioKind.download_only",
        want=_off("TestScenarioKindIsLockedToV151::"
                  "test_kind_is_derived_from_the_entity_shape"),
        why="kind 推导的两步顺序交换 ⇒ download-only 场景（同时 `expects_recovery_case` "
            "且不 `expects_application`）被判成 `recovery_reject`，于是 V151 的"
            "`ck_wpees_download_only_zero_entities` 不再管辖它。顺序即 V151 的分支顺序，"
            "不可交换",
    ),
    SpanMutation(
        id="R56", path=EV,
        anchor="    standard = \"standard\"\n"
               "    download_only = \"download_only\"\n"
               "    recovery_reject = \"recovery_reject\"\n"
               "    recovery_claim = \"recovery_claim\"\n"
               "    close_capture = \"close_capture\"",
        new="    standard = \"standard\"\n"
            "    download_only = \"download_only\"\n"
            "    recovery_reject = \"recovery_reject\"\n"
            "    recovery_claim = \"recovery_claim\"\n"
            "    close_capture = \"close_capture\"\n"
            "    authorization_reject = \"authorization_reject\"",
        want=_off("TestScenarioKindIsLockedToV151::"
                  "test_the_enum_matches_the_v151_check_exactly"),
        why="回归变异：给 `ScenarioKind` 加一个 V151 CHECK 里没有的值。这正是**真实缺陷**的"
            "形态 —— 第一版枚举整套都不在 DDL 域里，真库插入全炸而离线守卫全绿。判据必须"
            "从迁移文本反向解析取值域做双向等值",
    ),
    SpanMutation(
        id="R57", path=EV,
        anchor="            \"scenario_profile_digest\": self.scenario_profile_digest,\n"
               "                \"scenario_ids\": list(self.scenario_ids),",
        new="            \"scenario_profile_digest\": self.scenario_profile_digest,\n"
            "                \"scenario_ids\": [],",
        want=_off("TestRequiredSetDigest::"
                  "test_the_scenario_list_itself_is_part_of_the_digest"),
        why="required set digest 不再包含场景清单 ⇒ 增删场景后 digest 不变，旧 evidence "
            "永不 stale（P71 的核心）。"
            "﹙原判据是 `test_changing_the_scenario_profile_payload_changes_the_digest`，"
            "实测恒 GREEN：它改的是 `scenario_profile` payload，而 "
            "`scenario_profile_digest` 是 digest 里**另一个仍在**的字段，所以摘掉 "
            "`scenario_ids` 它照样绿。同类问题存在于当时全部 5 条 digest 测试 —— 它们"
            "改的输入自己都在 digest 里。已补一条只改场景清单、其余 digest 输入逐项"
            "断言不变的判据。﹚",
    ),
    SpanMutation(
        id="R58", path=EV,
        anchor="                \"derivation_version\": DERIVATION_VERSION,\n"
               "                \"entry_id\": self.entry_id,",
        new="                \"entry_id\": self.entry_id,",
        want=_off("TestRequiredSetDigest::"
                  "test_the_derivation_version_is_part_of_the_digest"),
        why="推导版本号不再进 digest ⇒ 改了推导规则旧 run 仍算 verified（P71 明文要禁）",
    ),
    SpanMutation(
        id="R59", path=EV,
        anchor="                \"entry_id\": self.entry_id,\n"
               "                \"capability\": self.capability.value,",
        new="                \"capability\": self.capability.value,",
        want=_off("TestRequiredSetDigest::"
                  "test_entry_id_is_in_the_digest_so_evidence_cannot_be_copied_across_entries"),
        why="`entry_id` 不再进 digest ⇒ 两个 profile 相同的 entry 得到同一个 digest，"
            "证据可以跨 entry 直接复制（P70 的第一道门）",
    ),
    SpanMutation(
        id="R60", path=EV,
        anchor="    assert_profile_consistent_with_capability(profile, capability)",
        new="    pass",
        want=_off("TestRequiredScenarioDerivation::"
                  "test_a_contradictory_profile_is_refused_by_the_single_shared_rule"),
        wants=(_off("TestRequiredScenarioDerivation::"
                    "test_derivation_delegates_the_cross_rule_instead_of_reimplementing_it"),),
        why="交叉一致性校验被摘掉 ⇒ 真 manifest 里那 5 个 `single_html + exclusive` 的 docx "
            "entry 会被当成合法 single_html 处理（跳过全部 OO 场景），而它们实际上有"
            "exclusive room。P71 点名的「profile 降级保鲜」正是这条",
    ),
    SpanMutation(
        id="R61", path=EV,
        anchor="        if str(run.required_scenario_set_digest) != required.digest:\n"
               "            reasons.append(StaleReason.required_scenario_set_changed)",
        new="        if False:\n"
            "            reasons.append(StaleReason.required_scenario_set_changed)",
        want=_pg("TestEvidenceStaleness::"
                 "test_a_different_required_set_digest_makes_the_run_stale"),
        why="required set digest 变化不再 stale ⇒ 场景集合改了旧 run 照样 verified",
    ),
    SpanMutation(
        id="R62", path=EV,
        anchor="        if str(run.room_model) != required.room_model.value:\n"
               "            reasons.append(StaleReason.room_model_changed)",
        new="        if False:\n"
            "            reasons.append(StaleReason.room_model_changed)",
        want=_pg("TestEvidenceStaleness::"
                 "test_downgrading_the_profile_cannot_keep_old_evidence_fresh"),
        why="P71 明文点名的保鲜手法：把 profile 从 shared 改成 exclusive 来保住旧证据。"
            "这条判据一旦失效，179 个 entry 只要改一个字段就能规避重跑",
    ),
    SpanMutation(
        id="R63", path=EV,
        anchor="                    if value in bucket and bucket[value] != scenario_id:\n"
               "                        defects.append(EvidenceDefect.reused_within_run)",
        new="                    if False:\n"
            "                        defects.append(EvidenceDefect.reused_within_run)",
        want=_pg("TestEvidenceReuseIsRefused::"
                 "test_reusing_one_operation_for_two_scenarios_is_refused"),
        why="同 run 内复用不再被拒 ⇒ 一条 applied operation 可以冒充 24 个互不等价的场景，"
            "「逐 scenario 证据」变成一次 operation 的复制（P70）",
    ),
    SpanMutation(
        id="R64", path=EV,
        anchor="            if overlap:\n"
               "                defects.append(EvidenceDefect.reused_across_entry)",
        new="            if False:\n"
            "                defects.append(EvidenceDefect.reused_across_entry)",
        want=_pg("TestEvidenceReuseIsRefused::"
                 "test_the_same_entities_in_two_entries_runs_reddens_both"),
        why="跨 entry 复用不再被拒 ⇒ 把 pilot entry 的证据复制到另外 178 个 entry 就能"
            "让收口计数全绿（P70 的主要攻击面）",
    ),
    SpanMutation(
        id="R65", path=EV,
        anchor="            (unrepresentable if sid in SCHEMA_UNREPRESENTABLE_SCENARIOS else failed).append(sid)",
        new="            failed.append(sid)",
        want=_pg("TestEvidenceRecomputation::"
                 "test_a_clean_run_has_exactly_one_known_and_attributed_defect"),
        why="已登记的 schema 欠账与真实失败被合成一个码 ⇒ 每次重算都要重新排查那条已知"
            "欠账，而真实失败会被它淹掉。两类必须各有独立缺陷码",
    ),
    SpanMutation(
        id="R66", path=EV,
        anchor="        except EntryProfileError as exc:\n"
               "            # profile 与 capability 交叉矛盾 ⇒ required set 不可推导 ⇒ 恒 unverified。",
        new="        except EntryProfileError:\n"
            "            raise\n"
            "        except EntryProfileError as exc:\n"
            "            # profile 与 capability 交叉矛盾 ⇒ required set 不可推导 ⇒ 恒 unverified。",
        want=_pg("TestEvidenceRecomputation::"
                 "test_a_contradictory_profile_reports_drift_instead_of_crashing"),
        why="profile 漂移改成上抛 ⇒ 一个 entry 的 manifest 欠账让整批重算失败，那些 entry "
            "从 AC 12.13 的五类计数里**消失**（而不是计为未验收）。这是「跳过就等于抹掉」"
            "的典型形态",
    ),
    SpanMutation(
        id="R67", path=EV,
        anchor="        if self.defects:\n"
               "            return EvidenceResult.unverified\n"
               "        if self.stale_reasons:\n"
               "            return EvidenceResult.stale",
        new="        if self.stale_reasons:\n"
            "            return EvidenceResult.stale\n"
            "        if self.defects:\n"
            "            return EvidenceResult.unverified",
        want=_off("TestStaleAndDefectCodesAreDistinct::"
                  "test_verdict_result_is_derived_not_written"),
        why="缺陷与 stale 的优先级交换 ⇒ 一个既 stale 又有缺陷的 run 只报 stale，"
            "缺陷消失在「等环境刷新就好」里",
    ),
    # ═══════════════════════════════════════════════════════════════════
    # R71~R74：router 接线（避免 additive 注入即死代码）
    # ═══════════════════════════════════════════════════════════════════
    SpanMutation(
        id="R71", path=R,
        anchor="        timeline = await SyncTimelineService(svc.session).operation_timeline(",
        new="        timeline = await _legacy_timeline_projection(svc.session).operation_timeline(",
        want=_off("TestRouterWiring::"
                  "test_the_timeline_endpoint_goes_through_the_timeline_service"),
        why="timeline 端点改走别的实现 ⇒ 手写投影绕开 RedactionPolicy。Task 26 留下的"
            "「零生产调用方」欠账正是这种形态：模块存在但没人调",
    ),
    SpanMutation(
        id="R72", path=R,
        anchor="        timeline = await SyncTimelineService(svc.session).recovery_case_timeline(",
        new="        timeline = await SyncTimelineService(svc.session).operation_timeline(",
        want=_off("TestRouterWiring::"
                  "test_the_recovery_case_timeline_endpoint_exists_and_is_separate"),
        why="recovery case 端点改调 operation timeline ⇒ 为 recovery 事件编一个 operation，"
            "AC 13.5 后半句被违反",
    ),
    SpanMutation(
        id="R73", path=R,
        anchor="    landed = delivery.durable_at is not None",
        new="    landed = str(delivery.state) in (\"durable\", \"acknowledged\", \"unmatched\")",
        want=_off("TestRouterWiring::"
                  "test_the_callback_metric_reads_durable_at_not_a_state_name"),
        why="耐久判据从 `durable_at` 换成 state 名单 —— AC 5.4 明文「归属约束只以 immutable "
            "`durable_at`/durable fact 判定，不得把泛化 terminal 当 durable」。两者在正常"
            "路径上同值，只有形态判据会红",
    ),
    SpanMutation(
        id="R74", path=R,
        anchor="        if result.result is OoToHtmlResult.refresh_required:",
        new="        if False:",
        want=_off("TestRouterWiring::"
                  "test_the_apply_path_reads_the_result_instead_of_assuming_success"),
        why="apply 后的终态分型少一支 ⇒ `refresh_required` 被压进 post-durable 失败告警，"
            "而它是**合法结果**（AC 4.11），只需要让用户重开编辑器",
    ),
    SpanMutation(
        id="R75", path=R,
        anchor="            if outcome.shape is OperationShape.duplicate\n"
               "            else \"application_created\"",
        new="            if getattr(outcome, \"application_cache_hit\", False)\n"
            "            else \"application_created\"",
        want=_off("TestRouterWiring::"
                  "test_no_metric_emission_uses_a_defaulted_getattr"),
        why="回归变异：改回带默认值的 `getattr`。**真实踩过** —— 字段名写错时默认值让指标"
            "永远记成 `application_created`，而 Volar/vitest/get_diagnostics/HEAD-swap 四层"
            "全绿",
    ),
]

#: 覆盖面分母 —— 本任务全部守卫文件。少登记一个文件，那个文件里的判据就不参与覆盖核算。
GUARD_FILES: dict[str, str] = {
    "test_task29_timeline_evidence.py": (
        "Task 29 离线：脱敏三层/allowlist 两侧锁/指标归因/告警三向锁/"
        "投影四码/required scenario 推导/ScenarioKind ↔ V151 同域/router 接线"
    ),
    "test_task29_timeline_evidence_pg.py": (
        "Task 29 真库：append-only 存储层强制、recovery claim 前零 operation、"
        "evidence 逐项重算与 stale、跨 entry/跨 scenario 复用"
    ),
}

PYTEST_ARGS = [
    "backend/tests/workpaper_sync/test_task29_timeline_evidence.py",
    "backend/tests/workpaper_sync/test_task29_timeline_evidence_pg.py",
    "-q",
    "--tb=no",
    # 🔴 `-rE` 不可省：语法错误的替换体会让整文件**收集失败**，此时 `FAILED` 一行都不会
    # 打印 ⇒ 差集为空 ⇒ 判 GREEN（指纹是异常短的运行时长）。`ERROR` 行进失败集合后它会
    # 如实变成 RED。
    "-rfE",
    "-p",
    "no:randomly",
]

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            pytest_args=PYTEST_ARGS,
            description="Task 29 timeline / evidence / 脱敏 / 告警 变异检验",
            # 170 = 126 离线 + 44 真库（实测 2026-08-28）。
            baseline_passed=170,
        )
    )
