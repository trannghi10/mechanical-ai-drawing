/* Source-bound identity selection after an ambiguous whole-file request. */
(() => {
  const el=id=>document.getElementById(id);
  el('changeRequest').oninput=()=>el('documentTargetChoices').replaceChildren();
  el('wholeDocumentRequest').onchange=()=>{
    el('documentTargetChoices').replaceChildren();
    if(el('wholeDocumentRequest').checked){
      clearPartSelection();
      el('editTarget').textContent='Tìm chi tiết trên toàn file đang mở; khung hiện tại dùng để đối chiếu.';
    }else{
      el('editTarget').textContent=workItem?'Yêu cầu áp dụng cho bản vẽ #'+workItem.id+'. Các liên kết nguồn vẫn được kiểm tra.':'Chọn một khung hoặc bật lại tìm chi tiết trong toàn file.';
    }
  };
  window.renderDocumentTargets=(job,documentId)=>{
    const host=el('documentTargetChoices');host.replaceChildren();
    const resolution=job.target_resolution;
    if(doc!==documentId||!resolution)return;
    const note=document.createElement('p');note.textContent=resolution.message;host.append(note);
    if(job.status!=='needs_target')return;
    const filter=document.createElement('input');filter.type='search';filter.placeholder='Lọc mã, STT hoặc mô tả chi tiết';filter.setAttribute('aria-label','Lọc chi tiết cần sửa');
    const list=document.createElement('div');host.append(filter,list);
    const render=()=>{
      list.replaceChildren();const query=filter.value.trim().toLocaleLowerCase();
      for(const candidate of resolution.candidates.filter(c=>JSON.stringify(c).toLocaleLowerCase().includes(query))){
        const row=document.createElement('p'),text=document.createElement('span'),button=document.createElement('button');
        text.textContent=`${candidate.part_code} · STT ${candidate.part_numbers.join(', ')||'chưa có'} · ${candidate.descriptions.join(' / ')} · Khung ${candidate.frame_ids.join(', ')||'chưa xác định'} `;
        button.textContent='Dùng mã '+candidate.part_code;button.className='secondary';button.disabled=!!candidate.definition_conflict;
        button.onclick=async()=>{
          if(doc!==documentId||analyzing||creatingRevision)return;
          el('wholeDocumentRequest').checked=true;
          el('changeRequest').value=job.request;
          await submitDrawingRequest({atlas_id:resolution.atlas_id,source_hash:resolution.source_hash,part_code:candidate.part_code},job.request);
        };
        row.append(text,button);list.append(row);
      }
    };
    filter.oninput=render;render();
    if(resolution.candidate_count>resolution.candidates.length){const more=document.createElement('p');more.textContent=`Đang hiện ${resolution.candidates.length}/${resolution.candidate_count} mã. Tra mã trong hồ sơ toàn file rồi nhập mã cụ thể vào yêu cầu.`;host.append(more);}
  };
  window.addEventListener('cad-document-changed',()=>{
    el('documentTargetChoices').replaceChildren();el('workspace').classList.remove('request-mode');
    el('wholeDocumentRequest').checked=true;
  });
})();
