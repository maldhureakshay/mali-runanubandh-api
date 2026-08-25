import httpx
import subprocess
import re

output = subprocess.check_output(['node', '/Users/akshaykumarmaldhure/work/Text Extractor/mock_web_token.js'], text=True)
match = re.search(r'(eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)', output)
token = match.group(1)

url = "http://127.0.0.1:8000/api/v1/community/moderation/posts?limit=20"
headers = {"Authorization": f"Bearer {token}"}
response = httpx.get(url, headers=headers)
print(response.json())
