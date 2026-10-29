with open('frontend/index.html', 'rb') as f:
    content = f.read()

target = b"const ready=await exportRevisionFile(created,panel,format,'selection',true);"
replacement = b"const ready=await exportRevisionFile(created,panel,format,'document',true);"

if target in content:
    content = content.replace(target, replacement)
    with open('frontend/index.html', 'wb') as f:
        f.write(content)
    print('SUCCESS')
else:
    print('NOT FOUND')
