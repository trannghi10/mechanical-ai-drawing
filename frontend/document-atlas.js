/* Whole-file reading is independent of the selected editing frame. */
(() => {
  const el=id=>document.getElementById(id);
  let epoch=0, report=null, job=null, documentId=null, page=0, next=null, queryEpoch=0;
  const busy=()=>analyzing||creatingRevision;
  const current=ticket=>ticket===epoch&&doc===documentId;
  const note=text=>{el('atlasStatus').textContent=text;};
  const labels={record_budget:'Vượt ngân sách đọc',depth_budget:'Block lồng quá sâu',recursive_block:'Block tham chiếu vòng',missing_block:'Thiếu định nghĩa block',external_reference:'XREF cần đọc riêng',multiple_insert_array:'Mảng block cần mở từng vị trí',invalid_transform:'Phép biến đổi không hợp lệ'};
  function reset(){
    epoch++;queryEpoch++;report=job=null;documentId=doc;next=null;
    el('atlasPanel').hidden=!doc;
    for(const id of ['atlasSummary','atlasParts','atlasEntities'])el(id).replaceChildren();
    el('atlasSearch').value='';el('atlasEntityCount').textContent='';el('atlasNext').disabled=true;
    el('atlasRead').disabled=!doc;el('atlasEntityRead').disabled=true;note('Đang chuẩn bị hồ sơ toàn file…');
  }
  function renderParts(){
    const box=el('atlasParts');box.replaceChildren();if(!report)return;
    const text=el('atlasSearch').value.trim().toLocaleLowerCase();
    const parts=report.parts.filter(p=>JSON.stringify([p.part_code,p.descriptions,p.materials,p.bom_occurrences.map(o=>o.part_number)]).toLocaleLowerCase().includes(text));
    const p=document.createElement('p');p.textContent=`${parts.length}/${report.parts.length} mã trong danh mục toàn file. STT được giữ theo từng bảng kê.`;box.append(p);
    const table=document.createElement('table');table.className='material-table';
    const header=table.createTHead().insertRow();for(const label of ['Mã / mô tả','Bản chi tiết và khung liên quan','Bằng chứng']){const th=document.createElement('th');th.textContent=label;header.append(th);}
    const body=table.createTBody(),ticket=epoch,did=documentId;
    // Search the entire directory, then page the displayed results.
    for(const part of parts.slice(page*20,(page+1)*20)){
      const row=body.insertRow();row.insertCell().textContent=[part.part_code,...part.descriptions].join(' · ');
      const frames=row.insertCell();
      for(const frame of part.frames){
        const button=document.createElement('button');button.className='secondary';
        button.textContent=`${part.detail_sheet_ids.includes(frame.id)?'Chi tiết':'Khung'} ${frame.name||''} · #${frame.id} · ${frame.layout}`;
        button.onclick=async()=>{
          if(!current(ticket)||doc!==did||busy())return;
          try{
            const checked=await api(`/documents/${did}/atlas/${job.id}/report`);
            if(!current(ticket)||busy())return;
            if(checked.source_hash!==report.source_hash)throw Error('Nguồn CAD đã đổi; cần đọc lại hồ sơ toàn file.');
            await show(items.find(i=>i.id===frame.id)||frame,true);
          }catch(error){if(current(ticket))note(error.message);}
        };frames.append(button);
      }
      if(!part.frames.length)frames.textContent='Chưa định vị được khung; chưa tự chọn hình để sửa.';
      row.insertCell().textContent=part.definition_conflict?'Mô tả BOM mâu thuẫn; cần đối chiếu':`${part.bom_occurrences.length} dòng BOM · ${part.native_instances.length} instance có mã. Liên kết cơ khí được kiểm tra khi lập kế hoạch.`;
    }
    box.append(table);
    if(parts.length>20){const previous=document.createElement('button'),more=document.createElement('button');previous.textContent='Trang trước';more.textContent='Trang sau';previous.disabled=page===0;more.disabled=(page+1)*20>=parts.length;previous.onclick=()=>{page--;renderParts()};more.onclick=()=>{page++;renderParts()};box.append(previous,more);}
    if(!report.parts.length){const p=document.createElement('p');p.textContent='Chưa có mã BOM đủ bằng chứng. Các thực thể vẫn có thể tra cứu bên dưới; không tự suy mã từ hình giống nhau.';box.append(p);}
  }
  function renderSummary(){
    const box=el('atlasSummary');box.replaceChildren();
    const add=text=>{const p=document.createElement('p');p.textContent=text;box.append(p);};
    add(`${report.placed_record_count.toLocaleString('vi-VN')} thực thể theo vị trí đặt · ${report.layouts.length} layout · ${report.frames.length} khung · ${report.parts.length} mã vật tư · ${report.unused_definition_count} định nghĩa block chưa được đặt.`);
    add(report.traversal_complete?'Đã duyệt hết các nhánh được đặt trong file DXF đã đọc từ DWG, kể cả phần ngoài khung.':'Chưa duyệt đủ toàn file; còn nhánh bị giới hạn hoặc tham chiếu cần đọc riêng.');
    const metadata=Object.values(report.metadata_only_types).reduce((a,b)=>a+b,0),partial=Object.values(report.partial_types).reduce((a,b)=>a+b,0);
    add(`${metadata} thực thể chỉ có metadata · ${partial} thực thể đọc một phần · ${report.gap_count} nhánh chưa mở đủ. Việc duyệt hết file chưa chứng minh đã hiểu đủ quan hệ lắp ghép hoặc sửa được mọi chi tiết.`);
    if(report.graph_error)add('Chưa lập được cấu trúc cụm/BOM: '+report.graph_error);
    for(const gap of report.gaps)add(`#${gap.ref}: ${labels[gap.reason]||gap.reason}${gap.block?' · '+gap.block:''}`);
    if(report.gaps_omitted)add(`Còn ${report.gaps_omitted} nhánh lỗi; cần đọc lại sau khi xử lý giới hạn.`);
    const select=el('atlasLayout');select.replaceChildren(new Option('Mọi layout',''));for(const layout of report.layouts)select.add(new Option(layout.name,layout.name));
    el('atlasEntityRead').disabled=false;page=0;renderParts();
  }
  async function start(){
    if(!doc)return;reset();const ticket=epoch,did=documentId;el('atlasRead').disabled=true;
    try{
      const submitted=await api(`/documents/${did}/atlas`,{method:'POST'});if(!current(ticket))return;job=submitted;
      while(job.status==='queued'||job.status==='running'){
        note(`${job.message} · ${job.visited_count||0} thực thể đã đọc`);
        await new Promise(resolve=>setTimeout(resolve,1500));if(!current(ticket))return;
        const result=await api(`/documents/${did}/atlas/${job.id}`);if(!current(ticket))return;job=result;
      }
      if(job.status!=='ready')throw Error(job.message);
      const result=await api(`/documents/${did}/atlas/${job.id}/report`);if(!current(ticket))return;
      report=result;renderSummary();note('Hồ sơ toàn file đã sẵn sàng. Tra mã để mở đúng bản chi tiết; kế hoạch sửa vẫn kiểm chứng hình học và các liên kết.');
    }catch(error){if(current(ticket))note(error.message);}
    finally{if(current(ticket))el('atlasRead').disabled=false;}
  }
  async function readEntities(append=false){
    if(!report||!job)return;const ticket=epoch,request=++queryEpoch,did=documentId;
    const params=new URLSearchParams({offset:String(append?next||0:0),limit:'50',layout:el('atlasLayout').value,kind:el('atlasKind').value,query:el('atlasEntityQuery').value});
    el('atlasEntityRead').disabled=true;el('atlasNext').disabled=true;
    try{
      const result=await api(`/documents/${did}/atlas/${job.id}/entities?${params}`);if(!current(ticket)||request!==queryEpoch)return;
      const box=el('atlasEntities');if(!append)box.replaceChildren();
      for(const record of result.items){const detail=document.createElement('details'),title=document.createElement('summary'),pre=document.createElement('pre');title.textContent=`${record.type} #${record.ref} · ${record.layout} · ${record.read_status}${record.role==='annotation_graphics'?' · nét hiển thị chú thích':''}`;pre.textContent=JSON.stringify(record,null,2);detail.append(title,pre);box.append(detail);}
      next=result.next_offset;el('atlasEntityCount').textContent=`${result.match_count} thực thể khớp · dữ liệu có hệ tọa độ và đường dẫn instance nguồn.`;
    }catch(error){if(current(ticket)&&request===queryEpoch)note(error.message);}
    finally{if(current(ticket)&&request===queryEpoch){el('atlasEntityRead').disabled=false;el('atlasNext').disabled=next===null;}}
  }
  el('atlasRead').onclick=start;el('atlasSearch').oninput=()=>{page=0;renderParts()};
  el('atlasEntityRead').onclick=()=>{next=null;return readEntities(false)};el('atlasNext').onclick=()=>readEntities(true);
  for(const id of ['atlasLayout','atlasKind','atlasEntityQuery'])el(id).addEventListener('input',()=>{queryEpoch++;next=null;el('atlasNext').disabled=true;el('atlasEntityRead').disabled=!report;});
  window.addEventListener('cad-document-ready',start);window.addEventListener('cad-document-changed',reset);
  if(window.documentReadingStatus?.status==='ready'&&doc)void start();
})();
