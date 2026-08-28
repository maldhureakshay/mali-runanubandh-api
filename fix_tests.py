import os
import re

for filename in os.listdir('.'):
    if filename.startswith('test_') and filename.endswith('.py'):
        with open(filename, 'r') as f:
            content = f.read()
        
        # Replace simple inline and multiline by just inserting after the open paren
        content = re.sub(r'BirthdayMetadata\(', r'BirthdayMetadata(profileName="Test User", ', content)
        # Note: the previous script might have already done some replacements: `BirthdayMetadata(profileName="Test User", profileId=`
        # So first let's clean up duplicate profileName="Test User" just in case.
        content = content.replace('BirthdayMetadata(profileName="Test User", profileName="Test User",', 'BirthdayMetadata(profileName="Test User",')
        
        with open(filename, 'w') as f:
            f.write(content)
