'use strict';
const byId=id=>document.getElementById(id);
const idPattern=/^[a-f0-9]{32}$/;
let reviewDoc=null,reviewProposal=null,historyVersion=null,activeRevision=null,proposalData=null,historyRequest=0,pendingTimer=null;
async function loadHistory(){
  const request=++historyRequest,doc=reviewDoc,proposal=reviewProposal;
  const current=()=>request===historyRequest&&doc===reviewDoc&&proposal===reviewProposal;
  if(pendingTimer){clearTimeout(pendingTimer);pendingTimer=null;}
  const h=await responseJson(await fetch(`/documents/${doc}/autocad/relationship-history`));if(!current())return;historyVersion=h.version;
  activeRevision=h.active_revision_id;byId('propose-native').hidden=true;
  const pending=Boolean(h.pending_revision);
  const wrongBase=proposalData?.adapter==='native_pointrefs'&&proposalData.base?.revision_id!==h.active_revision_id;
  const oldNative=proposalData?.adapter==='native_pointrefs'&&proposalData.schema_version!==3;
  byId('apply-repair').disabled=pending||wrongBase||oldNative;byId('undo-repair').disabled=pending||h.cursor<0;byId('redo-repair').disabled=pending||h.cursor+1>=h.entries.length;
  byId('apply-repair').title=oldNative?'Lập lại đề xuất native để kiểm phạm vi mới.':wrongBase?'Chọn revision nền của đề xuất trước khi tạo bản sửa.':'';
  byId('revision-state').textContent=pending?`Đang kiểm bản sửa ${h.pending_revision.id}; giữ nguyên bản đang chọn cho đến khi kiểm xong.`:h.active_revision_id?`Đang chọn bản sửa ${h.active_revision_id}`:'Đang chọn nguồn gốc; các bản sửa đã lưu vẫn được giữ.';
  byId('revision-download').hidden=!h.active_revision_id;
  byId('native-review').textContent='';
  byId('preview').src=h.active_revision_id?`/documents/${reviewDoc}/autocad/relationship-revisions/${h.active_revision_id}/preview`:`/documents/${reviewDoc}/autocad/relationship-proposals/${reviewProposal}/preview`;
  byId('preview-caption').textContent=h.active_revision_id?'Hình từ DXF của revision đang chọn; bản sửa liên kết giữ nguyên tọa độ.':'Hình nguồn; đề xuất gắn liên kết giữ nguyên tọa độ.';
  if(h.active_revision_id){
    byId('revision-download').href=`/documents/${reviewDoc}/autocad/relationship-revisions/${h.active_revision_id}/files/modified.dwg`;
    byId('revision-download').onclick=()=>{byId('revision-state').textContent='✅ Đã tải thành công bản DWG đã chỉnh sửa! Kiểm tra thư mục Downloads.';};
    const r=await responseJson(await fetch(`/documents/${reviewDoc}/autocad/relationship-revisions/${h.active_revision_id}`));
    if(!current())return;
    if(r.plan_id===reviewProposal&&r.status==='ready')byId('state').textContent='Đề xuất này đã tạo bản sửa được kiểm chứng. DWG nguồn được giữ nguyên; chưa phát hành bản sản xuất.';
    const heads=(r.native_endpoint_review?.endpoints||[]).filter(e=>!e.source_bound);
    byId('native-review').textContent=heads.length?'Đầu DIM native chưa đủ bằng chứng: '+heads.map(e=>`${e.dimension_handle} / ${e.field}, ứng viên đỉnh ${e.candidate_vertex_indices.join(', ')}`).join('; ')+'. Chưa tự gắn lại các đầu này.':'';
    byId('propose-native').hidden=pending||!(heads.length===2 && r.adapter!=='native_pointrefs');
    if(r.adapter==='native_pointrefs' && r.status==='ready')byId('native-review').textContent='Hai đầu DIM đã được kiểm liên kết; native B giữ nguyên, qua 8 phép kéo A/B và 4 phép kiểm riêng native B sau lưu/mở DWG. Ý đồ cơ khí chưa được xác nhận.';
  }
  if(pending&&current())pendingTimer=setTimeout(()=>{pendingTimer=null;loadHistory().catch(error=>{byId('revision-state').textContent=error.message;});},3000);
}
const params=new URLSearchParams(location.search);
for(const [key,field] of [['document','document'],['inspection','inspection'],['polyline','polyline'],['source_hash','source-hash']]){
  if(params.has(key))byId(field).value=params.get(key);
}
function showProposal(result,doc){
  proposalData=result;
  if(!idPattern.test(result.id)||!idPattern.test(doc))throw new Error('Mã hồ sơ không hợp lệ.');
  if(result.edit_authorization!==false||result.release_gate?.allowed!==false)throw new Error('Trạng thái đề xuất không hợp lệ.');
  byId('document').value=doc;byId('inspection').value=result.inspection_id||'';byId('polyline').value=result.plan.polyline_handle||'';byId('source-hash').value=result.source_sha256||'';
  const rows=byId('rows');rows.replaceChildren();
  for(const item of result.plan.repairs){
    const row=document.createElement('tr');
    for(const text of [item.dimension_handle,`Đỉnh ${item.a_vertex}`,`Đỉnh ${item.b_vertex}`,'Chưa xác nhận']){
      const cell=document.createElement('td');cell.textContent=text;row.append(cell);
    }rows.append(row);
  }
  const url=`/documents/${doc}/autocad/relationship-proposals/${result.id}`;
  byId('json-link').href=url;byId('preview').src=url+'/preview';
  byId('scope').textContent=result.scope_sha256;
  byId('state').textContent='Đã lưu đề xuất. Chưa thực thi hoặc phát hành bản sửa DWG.';
  byId('reasons').textContent=result.release_gate.reasons.join(' ');
  byId('result').hidden=false;
  reviewDoc=doc;reviewProposal=result.id;byId('revision-controls').hidden=false;
  loadHistory().catch(error=>{historyVersion=null;byId('revision-state').textContent=error.message;});
  history.replaceState(null,'',`?document=${doc}&proposal=${result.id}`);
}
async function responseJson(response){
  const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Không đọc được đề xuất.');return data;
}
byId('preview').addEventListener('error',()=>{byId('message').textContent='Không tải được hình; nguồn hoặc dữ liệu kiểm tra có thể đã đổi. Hãy đọc lại hồ sơ.';});
byId('proposal-form').addEventListener('submit',async event=>{
  event.preventDefault();byId('submit').disabled=true;byId('result').hidden=true;byId('revision-controls').hidden=true;reviewDoc=null;reviewProposal=null;historyVersion=null;byId('message').textContent='Đang kiểm tra nguồn và liên kết…';
  try{
    const doc=byId('document').value.trim();
    const response=await fetch(`/documents/${doc}/autocad/relationship-proposals`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({inspection_id:byId('inspection').value.trim(),polyline_handle:byId('polyline').value.trim(),source_hash:byId('source-hash').value.trim()})});
    showProposal(await responseJson(response),doc);byId('message').textContent='Đã kiểm nguồn và lưu đề xuất để xem xét.';
  }catch(error){byId('message').textContent=error.message;}finally{byId('submit').disabled=false;}
});
async function restore(){
  const doc=params.get('document'),proposal=params.get('proposal');if(!proposal)return;
  if(!idPattern.test(doc||'')||!idPattern.test(proposal)){byId('message').textContent='Mã hồ sơ không hợp lệ.';return;}
  byId('message').textContent='Đang tải đề xuất và kiểm tra bằng chứng nguồn…';
  try{showProposal(await responseJson(await fetch(`/documents/${doc}/autocad/relationship-proposals/${proposal}`)),doc);byId('message').textContent='Đã mở đề xuất đã lưu.';}
  catch(error){byId('result').hidden=true;byId('message').textContent=error.message;}
}
restore();
byId('propose-native').addEventListener('click',async()=>{
  if(!reviewDoc||!activeRevision||!proposalData)return;
  byId('propose-native').disabled=true;
  try{
    const result=await responseJson(await fetch(`/documents/${reviewDoc}/autocad/relationship-proposals`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({inspection_id:proposalData.inspection_id,polyline_handle:proposalData.plan.polyline_handle,source_hash:proposalData.source_sha256,adapter:'native_pointrefs',base_revision_id:activeRevision})}));
    showProposal(result,reviewDoc);
  }catch(error){byId('revision-state').textContent=error.message;}
  finally{byId('propose-native').disabled=false;}
});
for(const direction of ['undo','redo'])byId(direction+'-repair').addEventListener('click',async()=>{
  try{
    await responseJson(await fetch(`/documents/${reviewDoc}/autocad/relationship-history/${direction}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_version:historyVersion})}));await loadHistory();
  }catch(error){byId('revision-state').textContent=error.message;}
});
byId('apply-repair').addEventListener('click',async()=>{
  if(!reviewDoc||historyVersion===null)return;
  byId('apply-repair').disabled=true;byId('undo-repair').disabled=true;byId('redo-repair').disabled=true;
  let failure=null;
  try{
    let r=await responseJson(await fetch(`/documents/${reviewDoc}/autocad/relationship-proposals/${reviewProposal}/apply`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_version:historyVersion})}));
    while(r.status==='queued'||r.status==='running'){
      byId('revision-state').textContent='Đang chạy đối chứng và sửa thử trên bản sao…';
      await new Promise(resolve=>setTimeout(resolve,2000));
      r=await responseJson(await fetch(`/documents/${reviewDoc}/autocad/relationship-revisions/${r.id}`));
    }
    if(r.status!=='ready')throw new Error(r.error||'Bản sửa chưa đạt kiểm chứng.');
  }catch(error){failure=error;}
  finally{
    try{await loadHistory();}catch(error){failure=failure||error;byId('apply-repair').disabled=true;}
    if(failure)byId('revision-state').textContent=failure.message;
  }
});
