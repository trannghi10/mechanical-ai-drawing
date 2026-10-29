/* Explicit rectangle intent, bounded discovery and durable native job history. */
(() => {
  const panel=document.getElementById('apsPanel'),jobs=document.getElementById('apsJobs');
  const provider=document.getElementById('nativeProvider');
  if(!panel||!provider)return;
  const section=document.createElement('section');section.className='rectangle-editor';section.id='rectangleEditor';
  const title=document.createElement('h4');title.textContent='Đổi chiều rộng hình chữ nhật có DIM';
  const note=document.createElement('p'),status=document.createElement('p');status.setAttribute('role','status');
  const find=document.createElement('button');find.id='rectangleFind';find.textContent='Tìm nhóm chữ nhật trong file';
  const groups=document.createElement('div'),comparison=document.createElement('div');comparison.className='rectangle-comparison';
  section.append(title,note,find,status,groups,comparison);panel.insertBefore(section,jobs);
  let scopeDoc,scopeRoute,version=0;
  const current=(documentId,route,token)=>doc===documentId&&provider.value===route&&version===token;
  const imageUrl=(documentId,route,job,pair)=>`/documents/${documentId}/${route}/jobs/${job}/rectangle-preview?polyline_handle=${encodeURIComponent(pair.polyline_handle)}&dimension_handle=${encodeURIComponent(pair.dimension_handle)}`;
  function sync(){
    if(scopeDoc===doc&&scopeRoute===provider.value)return;
    scopeDoc=doc;scopeRoute=provider.value;++version;groups.replaceChildren();comparison.replaceChildren();status.textContent='';find.disabled=!doc;
    note.textContent='Tìm trên toàn file, rồi chọn đúng nhóm bằng hình xem trước. Chỉ đổi hình chữ nhật và DIM được chọn; giữ cạnh trái và chiều cao. Chưa đồng bộ BOM hoặc chi tiết xung quanh. '+(scopeRoute==='aps'?'Chế độ APS gửi bản sao CAD đến Autodesk khi đọc/sửa.':'AutoCAD xử lý trên máy.');
  }
  function figure(label,url){
    const box=document.createElement('figure'),caption=document.createElement('figcaption'),img=document.createElement('img');
    caption.textContent=label;img.alt=label;img.src=url;img.onerror=()=>{caption.textContent=label+' · Không tải được hình; cập nhật dữ liệu nếu file nguồn đã đổi.';};box.append(caption,img);return box;
  }
  function compare(documentId,route,inspection,job,pair){
    if(doc!==documentId||provider.value!==route)return;
    comparison.replaceChildren(figure('Trước sửa',imageUrl(documentId,route,inspection,pair)),figure('Sau sửa · đã kiểm sau mở lại',imageUrl(documentId,route,job,pair)));
  }
  async function waitJob(documentId,route,job,token){
    while(!['ready','failed'].includes(job.status)){
      if(!current(documentId,route,token))return null;
      await new Promise(resolve=>setTimeout(resolve,2000));
      if(!current(documentId,route,token))return null;
      job=await api(`/documents/${documentId}/${route}/jobs/${job.id}`);
    }
    if(job.status==='failed')throw Error(job.message||'Không hoàn tất chỉnh sửa. Xem lịch sử job.');
    return job;
  }
  find.onclick=async()=>{
    sync();const documentId=doc,route=provider.value,token=++version;
    if(!documentId)return;
    find.disabled=true;groups.replaceChildren();comparison.replaceChildren();status.textContent='Đang tìm dữ liệu CAD đã đọc…';
    try{
      const list=await api(`/documents/${documentId}/${route}/jobs`);
      if(!current(documentId,route,token))return;
      let inspection=list.items.find(job=>job.mode==='inspect'&&job.status==='ready');
      if(!inspection){
        status.textContent=route==='aps'?'Đang gửi bản sao file đến Autodesk để đọc nhóm…':'Đang đọc bản sao bằng AutoCAD…';
        inspection=await api(`/documents/${documentId}/${route}/jobs`,{method:'POST'});
        inspection=await waitJob(documentId,route,inspection,token);
      }
      if(!inspection||!current(documentId,route,token))return;
      const found=await api(`/documents/${documentId}/${route}/jobs/${inspection.id}/rectangle-candidates`);
      if(!current(documentId,route,token))return;
      status.textContent=found.items.length?`Có ${found.items.length} nhóm phù hợp${found.truncated?' trong phần đã quét':''}. Chọn nhóm và kiểm hình trước khi tạo bản sửa.`:'Chưa tìm thấy nhóm được hỗ trợ. Hiện cần chữ nhật bốn cạnh thẳng và một DIM ngang liên kết vertex 0/1.';
      if(!found.items.length)return;
      const select=document.createElement('select');select.id='rectangleGroup';select.setAttribute('aria-label','Nhóm chữ nhật trong file');
      for(const [index,pair] of found.items.entries()){
        const option=document.createElement('option');option.value=String(index);option.textContent=`${pair.layout} · ${pair.width_mm} × ${pair.height_mm} mm · nhóm #${pair.polyline_handle}`;select.append(option);
      }
      select.value='0';const form=document.createElement('div');groups.append(select,form);
      function render(){
        const pair=found.items[Number(select.value)],formToken=++version;form.replaceChildren();comparison.replaceChildren();
        const intent=document.createElement('p');intent.textContent=`Chiều rộng hiện tại ${pair.width_mm} mm; giữ cạnh trái và chiều cao ${pair.height_mm} mm.`;
        const label=document.createElement('label');label.textContent='Chiều rộng mới (mm)';
        const input=document.createElement('input');input.id='rectangleWidth';input.type='number';input.step='any';input.min='0';input.value=String(pair.width_mm);label.append(input);
        const apply=document.createElement('button');apply.id='rectangleApply';apply.textContent=route==='aps'?'Tạo DWG bằng APS · gửi Autodesk':'Tạo DWG sau đổi chiều rộng';
        form.append(intent,label,apply);comparison.append(figure('Hình nguồn · giữ cạnh trái',imageUrl(documentId,route,inspection.id,pair)));
        apply.onclick=async()=>{
          if(!current(documentId,route,formToken))return;
          const width=Number(input.value);
          if(!Number.isFinite(width)||width<=0||Math.abs(width-pair.width_mm)<=1e-7){status.textContent='Nhập chiều rộng dương và khác giá trị nguồn.';return;}
          apply.disabled=true;input.disabled=true;status.textContent='Đang giải và tạo bản DWG riêng…';
          try{
            let job=await api(`/documents/${documentId}/${route}/rectangle-stretch`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({inspection_id:found.inspection_id,source_hash:found.source_hash,polyline_handle:pair.polyline_handle,dimension_handle:pair.dimension_handle,target_width_mm:width})});
            if(!current(documentId,route,formToken))return;
            status.textContent=`Đang xử lý bản sửa #${job.id.slice(0,8)}. Job được giữ trong lịch sử khi đóng trang.`;
            await window.refreshApsJobs?.();job=await waitJob(documentId,route,job,formToken);
            if(!job||!current(documentId,route,formToken))return;
            status.textContent=`Đã tạo bản sửa ${pair.width_mm} → ${width} mm; hình và DIM đã kiểm sau mở lại. Tải DWG trong lịch sử job bên dưới.`;
            compare(documentId,route,inspection.id,job.id,pair);await window.refreshApsJobs?.();
          }catch(error){if(current(documentId,route,formToken))status.textContent=error.message;}
          finally{if(current(documentId,route,formToken)){apply.disabled=false;input.disabled=false;}}
        };
      }
      select.onchange=render;render();
    }catch(error){if(current(documentId,route,token))status.textContent=error.message;}
    finally{if(doc===documentId&&provider.value===route)find.disabled=false;}
  };
  provider.addEventListener('change',sync);
  window.syncRectangleEditor=sync;window.showRectangleComparison=compare;sync();
})();
