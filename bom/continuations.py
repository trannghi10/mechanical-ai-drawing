"""Associate BOM continuation pages using exact source title and product.

This provides row identities for reading. It does not assign geometry or
infer mechanical constraints, and conflicting balloon maps remain unresolved.
"""
import re
from bom.reader import normalized,plain,part_number_key


def numbered_series(sheet):
    """Explicit title-block page series, never adjacency or product alone."""
    texts=[plain(t) for t in sheet.get('texts',[])]
    products={t for t in texts if re.fullmatch(r'9\.\d+\.\d+',t)}
    if sheet.get('product_code'):products.add(str(sheet['product_code']).strip())
    titles={normalized(t) for t in texts if len(t)>25 and re.search(r'\d+(?:[.,]\d+)?\s*[x×]\s*\d+',t)}
    purposes={normalized(t) for t in texts if re.fullmatch(r'ban ve [\w ]+',normalized(t))}
    pages={tuple(map(int,m.groups())) for t in texts for m in [re.fullmatch(r'(?:so to|sheet(?: no\.?)?)\s*:\s*(\d+)\s*/\s*(\d+)',normalized(t))] if m}
    if not all(len(v)==1 for v in (products,titles,purposes,pages)):return None
    page,total=next(iter(pages))
    if not 1<=page<=total or not 2<=total<=100:return None
    return (next(iter(products)),next(iter(titles)),next(iter(purposes)),total),page


def continuation_links(tables,sheets,table_sheets):
    verified={t['ref']:t for t in tables if t.get('bom',{}).get('status')=='verified_template'}
    def signature(sheet):
        texts=[plain(t) for t in sheet.get('texts',[])]
        if not any(normalized(t)=='ban ve bang ke' for t in texts):return None
        products={t for t in texts if re.fullmatch(r'9\.\d+\.\d+',t)}
        titles={normalized(t) for t in texts if len(t)>25 and re.search(r'\d+(?:\.\d+)?\s*[x×]\s*\d+',t)}
        return (next(iter(products)),next(iter(titles))) if len(products)==len(titles)==1 else None
    groups={}
    for sheet in sheets:
        sig=signature(sheet)
        if sig:groups.setdefault(sig,[]).append(sheet['id'])
    links={}
    for (product,title),ids in groups.items():
        refs=[r for r in verified if set(table_sheets[r]).intersection(ids)]
        numbered={}
        for ref in refs:
            for row in verified[ref]['bom']['rows']:
                numbered.setdefault(row['part_number'],set()).add((row['part_code'],normalized(row['description']),normalized(row.get('material',''))))
        if not refs or any(len(values)!=1 for values in numbered.values()):continue
        for sid in ids:
            if any(sid in table_sheets[r] for r in refs):continue
            links[sid]=dict(table_refs=sorted(refs),product_code=product,title=title,
                           evidence_sheet_ids=sorted({s for r in refs for s in table_sheets[r]}),
                           status='exact_bom_continuation_title',geometry_ownership='unverified')
    series={}
    for sheet in sheets:
        found=numbered_series(sheet)
        if found:
            sig,page=found;series.setdefault(sig,[]).append((sheet['id'],page))
    for (product,title,purpose,total),members in series.items():
        # A duplicate/missing page may belong to another revision. Do not
        # borrow the first BOM just because the product/title is familiar.
        if len(members)!=total or {page for _,page in members}!=set(range(1,total+1)):continue
        ids={sid for sid,_ in members};refs=[r for r in verified if set(table_sheets.get(r,[])).intersection(ids)]
        numbers={};valid=bool(refs)
        for ref in refs:
            seen=set()
            for row in verified[ref]['bom']['rows']:
                key=part_number_key(row['part_number'])
                if key in seen:valid=False;break
                seen.add(key)
                numbers.setdefault(key,set()).add((row['part_code'],normalized(row['description']),normalized(row.get('material','')),plain(row.get('quantity_text',''))))
        if not valid or any(len(values)!=1 for values in numbers.values()):continue
        for sid,page in members:
            if any(sid in table_sheets.get(r,[]) for r in refs):continue
            links[sid]=dict(table_refs=sorted(refs),product_code=product,title=title,purpose=purpose,
                page=page,total_pages=total,page_sheet_ids={str(n):s for s,n in members},
                evidence_sheet_ids=sorted({s for r in refs for s in table_sheets[r]}),
                status='explicit_numbered_drawing_series',geometry_ownership='unverified')
    return links


def scoped_table_sheets(context):
    """Re-read source page metadata/BOMs before using a remote row identity."""
    tables=[e for e in context.get('entities',[]) if e.get('ref') and e.get('bom',{}).get('status')=='verified_template']
    scopes={e['ref']:set(e.get('source_sheet_ids',[])) for e in tables}
    links=continuation_links(tables,context.get('targets',[]),scopes)
    for sid,link in links.items():
        if link['status']=='explicit_numbered_drawing_series':
            for ref in link['table_refs']:scopes[ref].add(sid)
    return scopes
