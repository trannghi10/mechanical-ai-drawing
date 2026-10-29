"""Manufacturing stages carried by BOM descriptions, with source evidence."""
import re
from bom.reader import plain,normalized


def process_tags(description):
    """Only recognized operations in parentheses are stages; sizes are not."""
    aliases=[('cut_laser','Cắt laser',r'cat\s+la[sz]er'),
             ('welding','Hàn gò',r'han(?:\s+go|\s+laser)?'),
             ('bending','Chấn/uốn',r'(?:chan|uon)(?:\s+gap)?'),
             ('machining','Gia công',r'(?:gia cong|tien|phay|khoan(?:\s+la)?|la|chat)'),
             ('grinding','Nhám',r'(?:nham(?:\s+ban cat|\s+tay)?|bui nhui(?:\s+ban cat)?)'),
             ('painting','Sơn',r'(?:son(?:\s+[\w ."/-]+)?|std(?:\s+den|\s+tinh dien)?)'),
             ('plating','Xi/mạ',r'(?:xi|ma)(?:\s+den|\s+\d+\s+mau)?'),
             ('assembly','Lắp ráp',r'lap\s+rap'),
             ('purchasing','Mua hàng',r'mua\s+hang')]
    result=[]
    for match in re.finditer(r'\(([^()]*)\)',plain(description)):
        value=normalized(match.group(1))
        # These are explicit compound operations in source manufacturing
        # descriptions, not a new equivalence between their part codes.
        composite=re.fullmatch(r'cat\s+la[sz]er(?:\s+(nham|uon\s+cat))',value)
        if composite:
            stages=[('cut_laser','Cắt laser')]+([('grinding','Nhám')] if composite.group(1)=='nham'
                    else [('bending','Chấn/uốn')])
            for key,label in stages:
                if not any(t['id']==key for t in result):result.append(dict(id=key,label=label,source_text=match.group(0)))
            continue
        for key,label,pattern in aliases:
            if re.fullmatch(pattern,value):
                if not any(t['id']==key for t in result):result.append(dict(id=key,label=label,source_text=match.group(0)))
                break
    return result


def process_groups(tables,table_sheets):
    groups=[]
    for table in tables:
        if table.get('bom',{}).get('status')!='verified_template':continue
        stages={}
        for row in table['bom']['rows']:
            for tag in process_tags(row.get('description','')):
                stage=stages.setdefault(tag['id'],dict(id=f"{table['ref']}:{tag['id']}",stage_id=tag['id'],label=tag['label'],
                      table_ref=table['ref'],sheet_ids=table_sheets.get(table['ref'],[]),members=[]))
                cell=row.get('cells',{}).get('description',{})
                stage['members'].append(dict(part_code=row['part_code'].strip(),part_number=row['part_number'],
                       description=row.get('description',''),process_text=tag['source_text'],cell_index=cell.get('index'),
                       evidence_refs=[table['ref']]+([cell['mirror_ref']] if cell.get('mirror_ref') else [])))
        groups.extend(stages.values())
    return groups
