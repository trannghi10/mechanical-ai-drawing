"""Link existing detected sheets using exact BOM codes and fit notes."""
import re
from bom.reader import normalized,plain


def related_scope(targets,context,sheets,request,part_graph=None,derived_codes=()):
    if part_graph is not None:
        from graph.part_graph import seed_codes,impact_graph
        from backend.services.compound_planner import request_seeds
        impact=impact_graph(part_graph,request_seeds(context,request,part_graph)|set(derived_codes))
        wanted={sheet_id for node in impact["nodes"] for sheet_id in node["detail_sheets"]}
        wanted.update(s for link in impact.get('confirmed_representation_links',[]) if not link.get('unavailable_scope_ids') for s in link['sheet_ids'])
        selected_rows=[g for g in part_graph.get('drawing_rows',{}).get('groups',[]) if g['status']=='source_row_group' and
                       ({t['id'] for t in targets}.intersection(g['sheet_ids']) or set(impact['seed_codes']).intersection(g.get('part_codes',[])))]
        row_sources={sid for g in selected_rows for sid in g['sheet_ids']}
        wanted.update(row_sources)
        wanted.update(s for node in impact['nodes'] for instance in node.get('native_instances',[]) for s in instance['sheet_ids'])
        wanted.update(s for node in impact['nodes'] for occurrence in node['bom_occurrences'] for s in occurrence['sheet_ids'])
        wanted.update(e['sheet_id'] for edge in impact['edges'] for e in edge['evidence'])
        assembly_sources={s for g in impact.get('assembly_structure',{}).get('assemblies',[]) for s in g['scope_ids']}
        wanted.update(assembly_sources)
        review_sources={r['sheet_id'] for group in impact.get('process_groups',[]) for r in group.get('assembly_references',[])}
        wanted.update(review_sources)
        packaging_sources={sid for group in impact.get('packaging_groups',[]) for sid in group['sheet_ids']}
        wanted.update(packaging_sources)
        from bom.stage_links import physical_spec
        seed_specs={physical_spec(o.get('description','')) for node in impact['nodes'] for o in node.get('bom_occurrences',[])}
        seed_specs={s for s in seed_specs if s}
        stage_sources=set()
        if seed_specs:
            for sheet in sheets:
                if any(physical_spec(t) in seed_specs for t in sheet.get('texts',[])):
                    stage_sources.add(sheet['id'])
        wanted.update(stage_sources)
        selected={t["id"] for t in targets};expanded=list(targets);links=[]
        for sheet in sheets:
            if sheet["id"] not in wanted or sheet["id"] in selected:continue
            codes=[node["code"] for node in impact["nodes"] if sheet["id"] in node["detail_sheets"] or
                   any(sheet['id'] in o['sheet_ids'] for o in node['bom_occurrences']) or
                   any(sheet['id'] in i['sheet_ids'] for i in node.get('native_instances',[]))]
            reason="Liên kết mã chi tiết/chuỗi ghi chú lắp ghép: "+", ".join(codes)
            if sheet['id'] in row_sources:reason='Cùng hàng có nhãn nguồn '+', '.join(g['label'] for g in selected_rows if sheet['id'] in g['sheet_ids'])+'; đối chiếu hình chiếu/công đoạn trước khi sửa.'
            if sheet['id'] in packaging_sources:reason='Khung đóng gói cùng mã sản phẩm; kiểm tra thùng, lớp đệm, lót góc và pallet theo kích thước sau sửa.'
            if sheet['id'] in stage_sources and not codes:reason='Khung cắt phôi/công đoạn cùng quy cách chi tiết; đối chiếu quy cách trước và sau sửa.'
            if sheet['id'] in review_sources and not codes and sheet['id'] not in stage_sources:reason='Khung lắp ráp cùng mã sản phẩm; đối chiếu ghi chú công đoạn, chưa xác nhận số chi tiết với BOM.'
            if sheet['id'] in assembly_sources:reason='Cùng cây cụm từ bảng kê/STT; kiểm tra các chi tiết liên quan trước khi tính mặt lắp và mốc giữ.'
            expanded.append(dict(sheet,scope_reason=reason));selected.add(sheet["id"])
            links.append({"sheet_id":sheet["id"],"part_codes":codes,"reason":reason})
        # context_for enforces the actual parsed-entity/byte budget. Counting
        # sheets alone rejected small but well-linked assemblies unnecessarily.
        return expanded,links
    match=re.search(r'chi tiet\s*(?:so\s*)?(\d+)\b',normalized(request))
    if not match:return targets,[]
    rows=[row for e in context['entities'] for row in e.get('bom',{}).get('rows',[])
          if row['part_number']==match.group(1)]
    codes={row['part_code'].strip() for row in rows}
    if len(codes)!=1:return targets,[]
    code=codes.pop();base=code.rsplit('.',1)[0]
    pattern=re.compile(r'(?<![\d.])'+re.escape(base)+r'(?:\.\d+)?(?![\d.])')
    selected={t['id'] for t in targets};expanded=list(targets);links=[]
    dependent_codes=set()
    for sheet in sheets:
        texts=[plain(t) for t in sheet.get('texts',[])]
        if any(pattern.search(t) and 'vua khit' in normalized(t) for t in texts):
            dependent_codes.update(t for t in texts if re.fullmatch(r'\d+(?:\.\d+){3}',t))
    for sheet in sheets:
        if sheet['id'] in selected:continue
        texts=[plain(t) for t in sheet.get('texts',[])]
        direct=code in texts
        linked=any(c in texts for c in dependent_codes)
        if not direct and not linked:continue
        reason=('Mã chi tiết trùng dòng BOM '+code) if direct else ('Ghi chú lắp vừa với chi tiết '+base)
        item=dict(sheet,scope_reason=reason)
        expanded.append(item);selected.add(sheet['id'])
        links.append({'sheet_id':sheet['id'],'part_code':code,'reason':reason})
    if len(expanded)>8:
        raise ValueError('Có hơn 8 khung liên quan; cần chọn nhóm công đoạn cụ thể trước khi tạo bản sửa')
    return expanded,links
