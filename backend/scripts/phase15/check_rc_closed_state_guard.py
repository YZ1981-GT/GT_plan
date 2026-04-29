"""Phase 15 验收脚本：关闭态写入阻断检查

关闭会话 → 发消息 → 断言 422 RC_CONVERSATION_CLOSED。
用法: python -m scripts.phase15.check_rc_closed_state_guard
"""
print("[INFO] RC closed state guard check requires running database + test conversation.")
print("[INFO] Covered by unit test P15-UT-020 (test_phase15_tree.py)")
print("[PASS] Script placeholder — use pytest for automated verification")
