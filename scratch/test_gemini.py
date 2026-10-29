import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(r'd:\mechanical-ai-drawing\.env'), override=True, encoding='utf-8-sig')
api_key = os.getenv('GEMINI_API_KEY')
print("API KEY:", api_key[:10] + '...' if api_key else 'None')

import httpx
try:
    r = httpx.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}", timeout=10)
    print("Status:", r.status_code)
    if r.status_code == 200:
        models = [m['name'] for m in r.json().get('models', []) if 'gemini' in m['name']]
        print("Available models:", models[:5])
    else:
        print("Response:", r.text[:200])
except Exception as e:
    print("Error:", e)
