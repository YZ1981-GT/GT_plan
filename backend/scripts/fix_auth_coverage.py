"""批量给主梁路由添加 get_current_user 认证依赖"""
import re, os

router_dir = os.path.join(os.path.dirname(__file__), '..', 'app', 'routers')

# 需要加认证的路由文件
FILES_TO_FIX = [
    "working_paper.py", "wp_download.py", "wp_template.py", "wp_review.py",
    "wp_storage.py", "wp_ai.py", "wp_chat.py", "wp_progress.py",
    "qc.py", "attachments.py", "trial_balance.py", "misstatements.py",
    "sampling.py", "sampling_enhanced.py",
]

for fname in FILES_TO_FIX:
    fp = os.path.join(router_dir, fname)
    if not os.path.exists(fp):
        print(f"  SKIP: {fname}")
        continue
    
    with open(fp, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'get_current_user' in content:
        # Already has some auth, count unprotected
        endpoints = len(re.findall(r'@router\.(get|post|put|delete|patch)\(', content))
        auth = len(re.findall(r'Depends\(get_current_user\)', content))
        if auth >= endpoints:
            print(f"  OK: {fname} ({auth}/{endpoints})")
            continue
    
    # Add import if missing
    if 'get_current_user' not in content:
        if 'from app.core.database import get_db' in content:
            content = content.replace(
                'from app.core.database import get_db',
                'from app.core.database import get_db\nfrom app.deps import get_current_user\nfrom app.models.core import User',
            )
        elif 'from app.deps import' in content and 'get_current_user' not in content:
            content = re.sub(
                r'(from app\.deps import [^\n]+)',
                r'\1, get_current_user',
                content, count=1,
            )
    
    # Find all async def endpoints that don't have get_current_user
    # Pattern: async def xxx(..., db: AsyncSession = Depends(get_db),\n):
    # Add current_user parameter
    
    # Simple approach: find "db: AsyncSession = Depends(get_db),\n):" without get_current_user nearby
    pattern = r'(    db: AsyncSession = Depends\(get_db\),\n)(    (?:_lock_check[^\n]*)?\n)?(\):\n)'
    
    def add_auth(match):
        line1 = match.group(1)
        line2 = match.group(2) or ''
        closing = match.group(3)
        # Check if get_current_user already in nearby context
        if 'get_current_user' in line2:
            return match.group(0)
        if line2:
            return f"{line1}{line2}    current_user: User = Depends(get_current_user),\n{closing}"
        return f"{line1}    current_user: User = Depends(get_current_user),\n{closing}"
    
    new_content = re.sub(pattern, add_auth, content)
    
    if new_content != content:
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        old_auth = len(re.findall(r'Depends\(get_current_user\)', content))
        new_auth = len(re.findall(r'Depends\(get_current_user\)', new_content))
        print(f"  FIXED: {fname} ({old_auth} → {new_auth} auth)")
    else:
        print(f"  UNCHANGED: {fname} (pattern not matched, may need manual fix)")

print("\nDone. Run check_auth_coverage.py to verify.")
