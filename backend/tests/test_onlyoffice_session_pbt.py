"""PBT（property-based testing）— 席位守恒性质

使用 Hypothesis 对 OnlyOffice 会话限制器的**模型**进行性质测试，
验证对任意随机 acquire/release 操作序列，以下性质恒成立：

1. 席位守恒：活跃席位 = acquire 成功数 - release 成功数
2. 席位上限：活跃席位恒 ≤ MAX_SESSIONS
3. 幂等续期：同一 (user_id, doc_key) 多次 acquire 不重复计数
4. Release 非负：活跃席位永远 ≥ 0

模型采用内存 dict 模拟 Redis 键值行为（与真实 session_limiter 语义对齐）：
- acquire: key 已存在 → 幂等(不新增)；不存在且未满 → 新增；不存在且满 → 拒绝
- release: key 存在 → 删除；不存在 → 无操作

Validates: Requirements R1, R2, R3
"""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Model: 模拟 session_limiter 的核心语义（不依赖 Redis）
# ---------------------------------------------------------------------------

MAX_SESSIONS = 5  # 小值增加约束触发概率


class SessionLimiterModel:
    """内存模型，模拟 onlyoffice_session_limiter 的 acquire/release 语义。

    与真实实现的关键语义对齐：
    - acquire(user_id, doc_key): 幂等（已存在 → 续期不新增）；未满 → 占位；满 → 拒绝
    - release(user_id, doc_key): 存在 → 删除；不存在 → 无操作
    """

    def __init__(self, max_sessions: int = MAX_SESSIONS):
        self.max_sessions = max_sessions
        self.sessions: dict[str, bool] = {}  # key → True
        self.acquire_success_count = 0
        self.release_success_count = 0

    def _make_key(self, user_id: int, doc_key: int) -> str:
        return f"{user_id}:{doc_key}"

    def acquire(self, user_id: int, doc_key: int) -> bool:
        """尝试获取席位。返回 True=成功（含幂等续期），False=满额拒绝。"""
        key = self._make_key(user_id, doc_key)

        # 幂等：已存在 → 续期（不新增计数）
        if key in self.sessions:
            return True

        # 满额 → 拒绝
        if len(self.sessions) >= self.max_sessions:
            return False

        # 占位
        self.sessions[key] = True
        self.acquire_success_count += 1
        return True

    def release(self, user_id: int, doc_key: int) -> bool:
        """释放席位。返回 True=确实释放了一个，False=无此席位（无操作）。"""
        key = self._make_key(user_id, doc_key)
        if key in self.sessions:
            del self.sessions[key]
            self.release_success_count += 1
            return True
        return False

    @property
    def active_count(self) -> int:
        return len(self.sessions)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# 操作类型
op_type_st = st.sampled_from(["acquire", "release"])

# 从小池生成 user_id 和 doc_key，增加碰撞概率
user_id_st = st.integers(min_value=1, max_value=5)
doc_key_st = st.integers(min_value=1, max_value=5)

# 单个操作：(op_type, user_id, doc_key)
operation_st = st.tuples(op_type_st, user_id_st, doc_key_st)

# 操作序列
operations_st = st.lists(operation_st, min_size=1, max_size=100)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(operations=operations_st)
@settings(max_examples=200)
def test_seat_conservation_property(operations):
    """席位守恒：活跃席位 = acquire 成功新增数 - release 成功数

    对任意 acquire/release 操作序列，模型内部状态始终满足：
    active_count == acquire_success_count - release_success_count

    **Validates: Requirements R1, R2, R3**
    """
    model = SessionLimiterModel(max_sessions=MAX_SESSIONS)

    for op, user_id, doc_key in operations:
        if op == "acquire":
            model.acquire(user_id, doc_key)
        else:
            model.release(user_id, doc_key)

        # 守恒性质：每步操作后都成立
        assert model.active_count == (
            model.acquire_success_count - model.release_success_count
        ), (
            f"Conservation violated: active={model.active_count}, "
            f"acquires={model.acquire_success_count}, "
            f"releases={model.release_success_count}"
        )


@given(operations=operations_st)
@settings(max_examples=200)
def test_seat_upper_bound_property(operations):
    """席位上限：活跃席位恒 ≤ MAX_SESSIONS

    无论操作序列如何，活跃席位数永远不超过上限。

    **Validates: Requirements R1, R2**
    """
    model = SessionLimiterModel(max_sessions=MAX_SESSIONS)

    for op, user_id, doc_key in operations:
        if op == "acquire":
            model.acquire(user_id, doc_key)
        else:
            model.release(user_id, doc_key)

        # 上限性质：每步操作后都成立
        assert model.active_count <= MAX_SESSIONS, (
            f"Upper bound violated: active={model.active_count}, max={MAX_SESSIONS}"
        )


@given(operations=operations_st)
@settings(max_examples=200)
def test_idempotent_acquire_property(operations):
    """幂等续期：同一 (user_id, doc_key) 多次 acquire 不增加计数

    对于已持有席位的 (user_id, doc_key)，再次 acquire 应成功但不增加
    active_count。这确保刷新页面/重连不会重复占席。

    **Validates: Requirements R1, R3**
    """
    model = SessionLimiterModel(max_sessions=MAX_SESSIONS)

    for op, user_id, doc_key in operations:
        if op == "acquire":
            count_before = model.active_count
            key = model._make_key(user_id, doc_key)
            already_exists = key in model.sessions

            result = model.acquire(user_id, doc_key)

            if already_exists:
                # 幂等：已存在的 key 再次 acquire → 成功且计数不变
                assert result is True
                assert model.active_count == count_before, (
                    f"Idempotent acquire changed count: "
                    f"before={count_before}, after={model.active_count}"
                )
        else:
            model.release(user_id, doc_key)


@given(operations=operations_st)
@settings(max_examples=200)
def test_release_never_negative_property(operations):
    """非负性质：活跃席位永远 ≥ 0

    release 一个不存在的席位不会导致负数（静默跳过）。

    **Validates: Requirements R3**
    """
    model = SessionLimiterModel(max_sessions=MAX_SESSIONS)

    for op, user_id, doc_key in operations:
        if op == "acquire":
            model.acquire(user_id, doc_key)
        else:
            model.release(user_id, doc_key)

        # 非负性质
        assert model.active_count >= 0, (
            f"Negative active count: {model.active_count}"
        )
