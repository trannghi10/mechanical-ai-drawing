import sys, traceback
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

from backend.services.planning_jobs import submit, Control, run, CURRENT, POOL, ACTIVE, LOCK

doc_id = 'fdb1918fbce7401aa33c7738c4096b8f'
req = 'đổi chiều dài từ 705mm thành 700mm'

def my_update(phase, message, **kwargs):
    print(f'PROGRESS: {phase} - {message}')

control = Control(my_update)
jid = 'a' * 32

try:
    from backend.services.change_service import storage
    path = storage.folder(doc_id) / 'planning-jobs' / (jid + '.json')
    stat = (storage.folder(doc_id) / storage.read_status(doc_id)['dxf']).stat()
    data = dict(id=jid, document_id=doc_id, status='running', phase='cad', message='Testing',
                created_at=1.0, request=req, target_ids=[], targets=[], key='test',
                source_signature=[stat.st_mtime_ns, stat.st_size], whole_document=True, target_choice=None)
    storage.write_json(path, data)
    print('Starting run...')
    run(doc_id, jid, control)
    print('Finished run successfully!')
    final_data = storage.read_json(path)
    print('Final status:', final_data.get('status'), final_data.get('message'))
except Exception as e:
    print('EXCEPTION CAUGHT:')
    traceback.print_exc()
