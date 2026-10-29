with open('frontend/index.html', 'rb') as f:
    content = f.read()

target = b"const seen=new Set();for(const job of result.items){"
replacement = b"const items=[...(result.items||[])].sort((a,b)=>(b.scope==='document'?1:0)-(a.scope==='document'?1:0));const seen=new Set();for(const job of items){"

if target in content:
    content = content.replace(target, replacement)
    with open('frontend/index.html', 'wb') as f:
        f.write(content)
    print('SUCCESS')
else:
    print('NOT FOUND')
