import urllib.request, json

doc_id = '5a1955b75d4345b69d19d38b7cfaf75c'
for rev_id in ['5f87b84ede6345c88ccf3596bfe75ac7', '840001c2e91448e299eca04d1f4add16']:
    url = f'http://127.0.0.1:8765/documents/{doc_id}/revisions/{rev_id}/exports'
    req = urllib.request.urlopen(url)
    data = json.loads(req.read().decode())
    print(f'=== Exports for {rev_id[:8]} ===')
    for item in data.get('items', []):
        print(f"  Job {item['id']}: scope={item['scope']}, status={item['status']}, file={item['file']}, url={item['download_url']}")
