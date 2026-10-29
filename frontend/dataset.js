(() => {
  const el=id=>document.getElementById(id);let epoch=0,queryEpoch=0,next=null;
  const request=async url=>{const result=await fetch(url,{cache:'no-store'});if(!result.ok)throw Error((await result.json()).detail||'Không đọc được dữ liệu');return result.json()};
  function table(headers,rows){
    const result=document.createElement('table');result.className='material-table';const head=result.createTHead().insertRow();
    for(const label of headers){const cell=document.createElement('th');cell.textContent=label;head.append(cell)}
    const body=result.createTBody();for(const values of rows){const row=body.insertRow();for(const value of values)row.insertCell().textContent=String(value)}return result;
  }
  async function records(append=false){
    const ticket=++queryEpoch;el('searchDataset').disabled=true;el('moreDataset').disabled=true;
    try{
      const query=new URLSearchParams({offset:String(append?next||0:0),limit:'50',query:el('datasetQuery').value});
      const value=await request('/dataset/records?'+query);if(ticket!==queryEpoch)return;
      const view=el('datasetRecords');if(!append)view.replaceChildren();
      view.append(table(['Hồ sơ / nguồn','CAD / nhóm đề xuất','Trạng thái','Quyền sử dụng'],value.items.map(r=>[
        `${r.title} · ${r.source_id} · ${r.origin}`,
        `${r.cad_formats.join(', ')} · ${r.group}${r.group_review==='pending'?' (chưa duyệt)':''}`,
        `${r.native_opened?'Đã mở native':'Chưa mở native'} · ${r.label_count} nhãn đề xuất · ${r.relationship_count} quan hệ · ${r.edit_case_count} ca sửa · kỹ sư: ${r.dossier_review} · split: ${r.split}`,
        `${r.rights.license_id||r.rights.status} · đọc: ${r.rights.evaluation?'có':'chưa rõ'} · huấn luyện: ${r.rights.training?'nguồn cho phép, chưa sẵn sàng':'chưa cho phép'} · chia sẻ: ${r.rights.redistribution?'có theo giấy phép':'không'}`
      ])));next=value.next_offset;el('moreDataset').hidden=next===null;
    }catch(error){if(ticket===queryEpoch)el('datasetStatus').textContent=error.message}
    finally{if(ticket===queryEpoch){el('searchDataset').disabled=false;el('moreDataset').disabled=false}}
  }
  async function refresh(){
    const ticket=++epoch;el('refreshDataset').disabled=true;
    try{
      const value=await request('/dataset/status');if(ticket!==epoch)return;
      const summary=el('datasetSummary');summary.replaceChildren();
      for(const text of [
        `${value.accepted_dwg_dossiers}/500 hồ sơ DWG đã nghiệm thu · ${value.record_count} hồ sơ đăng ký · ${value.unique_dwg_files} file DWG gốc khác nhau.`,
        `${value.label_count} nhãn trong registry · ${value.relationship_count} quan hệ · ${value.engineer_approved_edit_cases} ca có đáp án kỹ sư · ${value.dwg_roundtrip_cases} ca sửa qua lưu/mở DWG.`,
        `${value.training_ready} hồ sơ sẵn sàng huấn luyện. Split train/validation/test chưa được tự gán. ${value.note}`
      ]){const p=document.createElement('p');p.textContent=text;summary.append(p)}
      el('datasetStatus').textContent=value.integrity_checked&&!Object.keys(value.integrity_errors).length&&!value.split_errors.length?'Đã kiểm hash file và phân tách dữ liệu. Chưa hoàn tất bộ dữ liệu nghiệm thu.':'Có lỗi dữ liệu: '+JSON.stringify([value.integrity_errors,value.split_errors]);
      el('datasetGroups').replaceChildren(table(['Nhóm sản phẩm','Mục tiêu','Đã đăng ký (chưa duyệt nhóm)','Đã nghiệm thu'],value.groups.map(g=>[g.name,g.target,g.records,g.accepted])));
      el('datasetSources').replaceChildren(table(['Nguồn','Truy cập đã kiểm','Quyền / giới hạn'],value.sources.public_sources.map(s=>[s.name,s.access,s.rights+' · '+s.notes])));
      await records();
    }catch(error){if(ticket===epoch)el('datasetStatus').textContent=error.message}
    finally{if(ticket===epoch)el('refreshDataset').disabled=false}
  }
  el('refreshDataset').onclick=refresh;el('searchDataset').onclick=()=>{next=null;return records()};el('moreDataset').onclick=()=>records(true);
  el('datasetQuery').addEventListener('input',()=>{queryEpoch++;next=null;el('moreDataset').hidden=true;el('searchDataset').disabled=false});
  void refresh();
})();
