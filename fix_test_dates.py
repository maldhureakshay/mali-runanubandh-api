import os

for filename in os.listdir('.'):
    if filename.startswith('test_') and filename.endswith('.py'):
        with open(filename, 'r') as f:
            content = f.read()
        
        content = content.replace('datetime(2026, 8, 8, tzinfo=timezone.utc)', 'datetime.now(timezone.utc)')
        content = content.replace('datetime.datetime(2026, 8, 8, tzinfo=timezone.utc)', 'datetime.now(timezone.utc)')
        
        with open(filename, 'w') as f:
            f.write(content)
