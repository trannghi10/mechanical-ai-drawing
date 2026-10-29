"""Audit the real expanded CAD scope and token count without generating edits."""
import json
from pathlib import Path
import sys
import httpx
sys.stdout.reconfigure(encoding='utf8')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.services import ai_provider
from backend.services.change_service import plan_change


def main():
    compound='--compound' in sys.argv
    root=Path(__file__).resolve().parents[1];folder=root/'storage/documents/34ee84f35e1a44fb81c56044397a0fff'
    target=next(t for t in json.loads((folder/'sheets-v3.json').read_text(encoding='utf8'))['items'] if t['id']=='3D3E83')
    ai_provider.settings=lambda:('native','qwen3-vl:4b-instruct')
    class Captured(Exception):pass
    result={}
    def capture(prompt,parts,schema):
        content=[dict(type='text',text=x['text']) if 'text' in x else
                 dict(type='image_url',image_url=dict(url='data:image/png;base64,'+x['inlineData']['data'])) for x in parts]
        if '--text-only-audit' in sys.argv:content=[x for x in content if x['type']=='text']
        body=dict(messages=[dict(role='system',content=prompt),dict(role='user',content=content)],temperature=0,stream=False,
                  chat_template_kwargs=dict(enable_thinking=False),response_format=dict(type='json_object',schema=schema.model_json_schema()))
        c=json.loads(parts[0]['text'])['cad_context']
        result.update(parsed_entities=c['full_parsed_entity_count'],supplied_entities=c['entity_count'],
                      deferred_entities=c['geometry_discovery']['deferred_count'],preview_images=sum('inlineData' in x for x in parts),
                      root_bom_refs=c['root_bom_refs'],related_scopes=len(c['targets']),body_bytes=len(json.dumps(body).encode()))
        if compound:
            choices=c.get('design_choices',{})
            assert choices.get('derived_values',{}).get('frame_height_target_mm')==697
            assert any(v.get('key')=='overall_height' and v.get('target_mm')==700 for v in choices.get('confirmed_choices',[]))
            result.update(request_requirements=c.get('request_requirements'),confirmed_design_choices=choices)
        (root/'storage/validation-fixtures/dauphine-focused-planning-wire.json').write_text(json.dumps(c,ensure_ascii=False),encoding='utf8')
        with httpx.Client(trust_env=False,timeout=30) as client:
            r=client.post('http://127.0.0.1:11436/v1/chat/completions/input_tokens',json=body);r.raise_for_status();result.update(r.json())
        result['available_output_tokens']=min(8192,32768-result['input_tokens']-256)
        result['fits_32k_with_4k_output']=result['available_output_tokens']>=4096
        raise Captured()
    ai_provider.generate_plan=capture
    request=('1. Chiều cao tổng thể sản phẩm từ 724 mm thành 700 mm; 2. Tất cả liệu sắt tấm cắt lazer đổi từ 1.5 mm thành 1 mm'
             if compound else 'Tất cả liệu sắt tấm cắt lazer đổi từ 1.5 mm thành 1mm')
    try:plan_change(folder.name,[target],request)
    except Captured:pass
    name='dauphine-compound-token-audit.json' if compound else 'dauphine-focused-token-audit.json'
    (root/'storage/validation-fixtures'/name).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    if not result['fits_32k_with_4k_output']:raise RuntimeError('Expanded source still exceeds the local model budget')


if __name__=='__main__':main()
