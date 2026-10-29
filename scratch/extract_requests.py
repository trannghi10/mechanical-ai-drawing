import json

log_path = r'C:\Users\nghi.tran\.gemini\antigravity-ide\brain\9e608566-52d7-4d85-964a-291509e972a9\.system_generated\logs\transcript.jsonl'
with open(log_path, 'r', encoding='utf-8') as f:
    for idx, line in enumerate(f):
        if idx >= 280:
            try:
                data = json.loads(line)
                if data.get('type') == 'USER_INPUT':
                    c = data.get('content', '')
                    if '<USER_REQUEST>' in c:
                        c = c.split('<USER_REQUEST>')[1].split('</USER_REQUEST>')[0].strip()
                    print(f"[{idx} / step {data.get('step_index')}] {c}\n")
            except Exception:
                pass




