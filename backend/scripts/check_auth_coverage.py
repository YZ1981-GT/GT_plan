"""检查五根主梁的代码硬度"""
import re, os

router_dir = os.path.join(os.path.dirname(__file__), '..', 'app', 'routers')

# 主梁相关路由文件
PILLAR_FILES = {
    "底稿": ["working_paper.py", "wp_download.py", "wp_template.py", "wp_review.py", "wp_storage.py", "wp_ai.py", "wp_chat.py", "wp_progress.py"],
    "复核": ["working_paper.py", "wp_review.py", "qc.py", "review_conversations.py", "annotations.py"],
    "附件": ["attachments.py"],
    "权限": ["project_wizard.py", "adjustments.py", "trial_balance.py", "misstatements.py"],
    "留痕": ["process_record.py", "report_trace.py"],
}

print("=== 五根主梁认证覆盖检查 ===\n")

for pillar, files in PILLAR_FILES.items():
    print(f"【{pillar}】")
    for fname in files:
        fp = os.path.join(router_dir, fname)
        if not os.path.exists(fp):
            print(f"  {fname}: 文件不存在!")
            continue
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Count endpoints
        endpoints = re.findall(r'@router\.(get|post|put|delete|patch)\(', content)
        # Count endpoints with auth
        auth_endpoints = len(re.findall(r'Depends\(get_current_user\)', content))
        # Count endpoints with consol_lock
        lock_endpoints = len(re.findall(r'Depends\(check_consol_lock\)', content))
        
        total = len(endpoints)
        unprotected = total - auth_endpoints
        status = "✅" if unprotected == 0 else f"⚠️ {unprotected}/{total} 无认证"
        lock_info = f" 🔒{lock_endpoints}" if lock_endpoints > 0 else ""
        print(f"  {fname:30s} {total:2d} 端点, {auth_endpoints:2d} 有认证 {status}{lock_info}")
    print()
