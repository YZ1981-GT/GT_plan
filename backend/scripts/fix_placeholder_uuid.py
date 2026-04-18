"""批量修复占位 UUID → get_current_user 依赖注入"""
import re, os

router_dir = os.path.join(os.path.dirname(__file__), '..', 'app', 'routers')
PLACEHOLDER = '00000000-0000-0000-0000-000000000000'

files_to_fix = [
    'annotations.py', 'forum.py', 'process_record.py',
    'report_trace.py', 'review_conversations.py',
]

for fname in files_to_fix:
    fp = os.path.join(router_dir, fname)
    if not os.path.exists(fp):
        print(f'  SKIP: {fname} not found')
        continue
    
    with open(fp, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if PLACEHOLDER not in content:
        print(f'  SKIP: {fname} no placeholder')
        continue
    
    # Add import if not present
    if 'get_current_user' not in content:
        # Find the last import line
        content = content.replace(
            'from app.core.database import get_db',
            'from app.core.database import get_db\nfrom app.deps import get_current_user\nfrom app.models.core import User',
        )
    
    # Replace placeholder UUID patterns
    # Pattern: xxx_id = UUID("00000000-...")
    content = re.sub(
        r'(\w+_id)\s*=\s*UUID\(["\']' + PLACEHOLDER + r'["\']\)',
        r'# \1 now from JWT (see function signature)',
        content,
    )
    
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(content)
    
    count = content.count('# now from JWT')
    print(f'  FIXED: {fname} ({count} replacements)')

print('\nDone. Manual review needed to add current_user: User = Depends(get_current_user) to function signatures.')
