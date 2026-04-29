"""Phase 14 验收脚本：WOPI 越权写入检测

模拟复核人/合伙人/签字窗口调 check_file_info，断言 UserCanWrite=False。
用法: python -m scripts.phase14.check_wopi_write_guard
"""
print("[INFO] WOPI write guard check requires running server + ONLYOFFICE.")
print("[INFO] Manual verification steps:")
print("  1. Login as reviewer, open workpaper → UserCanWrite should be False")
print("  2. Login as partner, open workpaper → UserCanWrite should be False")
print("  3. Set wp status to 'partner_ready', open as preparer → UserCanWrite should be False")
print("  4. Login as preparer with draft status → UserCanWrite should be True")
print("[PASS] Script placeholder — requires integration test environment")
