# -*- coding: utf-8 -*-
with open(r'd:\mechanical-ai-drawing\frontend\index.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = None
end_idx = None

for i, line in enumerate(lines):
    if "release.textContent='Kiểm tra điều kiện phát hành'" in line:
        start_idx = i + 1  # line after release
    if "$('planHistory').onchange=async()=>{" in line:
        end_idx = i

if start_idx is None or end_idx is None:
    raise ValueError(f"Could not locate indices: start={start_idx}, end={end_idx}")

replacement = """ if(revision.part_selection){const part=document.createElement('p');part.textContent='Chi tiết được chọn bằng hình: '+revision.part_selection.part_code;panel.append(part)}
 if(revision.source_preservation?.status==='verified_unchanged'){const saved=document.createElement('p');saved.className='source-preserved';saved.textContent='Đã tạo bản mới riêng. Đã kiểm tra: bản vẽ nguồn giữ nguyên khi tạo bản này.';panel.append(saved)}
 const controls=(target,container)=>{const before=document.createElement('button');before.textContent='Trước sửa';before.onclick=()=>show(items.find(i=>i.id===target.id)||target,false);const after=document.createElement('button');after.textContent='Sau sửa';after.onclick=()=>{viewRevision(revision,target).catch(e=>$('changeStatus').textContent=e.message);loadRevisionMaterials(revision,target.id).catch(()=>{})};const compare=document.createElement('button');compare.textContent='Chồng nét';compare.onclick=()=>{openComparison(revision,target,null,'overlay').catch(e=>$('previewStatus').textContent=e.message);loadRevisionMaterials(revision,target.id).catch(()=>{})};const link=document.createElement('a');link.textContent=' Mở lớn';link.target='_blank';link.href=revisionPreviewUrl(revision,target);container.append(before,after,compare,link)};
 const geometryTarget=revision.targets.find(t=>t.id===revision.primary_geometry_target_id)||root;
 if(geometryTarget.id!==root.id){const changedView=document.createElement('p');changedView.textContent=`Hình học đã sửa nằm trong khung chi tiết #${geometryTarget.id}. Đang đối chiếu bản chi tiết; yêu cầu vẫn áp dụng cho bản vẽ đã chọn.`;panel.append(changedView)}
 const row=document.createElement('p');controls(geometryTarget,row);panel.append(row);
 displayProposalMaterials(revision,panel);
 displayChangedTargetsCard(revision.changed_targets,panel,revision,false,revision);
 displayImpactAndRelations(revision,panel);
 displayPlanOperations(revision,panel);
 const changedIds=new Set((revision.changed_targets||[]).map(t=>t.id));
 const unchanged=revision.targets.filter(t=>!changedIds.has(t.id));
 if(unchanged.length){const review=document.createElement('details');review.className='linked-review';const summary=document.createElement('summary');summary.textContent=`Xem các bản vẽ khác (${unchanged.length} khung giữ nguyên)`;review.append(summary);const info=document.createElement('p');info.textContent='Các khung này được giữ nguyên theo CAD gốc. Mở để đối chiếu trước khi duyệt.';review.append(info);const select=document.createElement('select');select.setAttribute('aria-label','Bản vẽ giữ nguyên để đối chiếu');for(const t of unchanged)select.add(new Option(`${t.name||t.kind} #${t.id}`,t.id));const open=document.createElement('button');open.textContent='Xem bản này';open.onclick=()=>viewRevision(revision,unchanged.find(t=>t.id===select.value)).catch(e=>$('changeStatus').textContent=e.message);const back=document.createElement('button');back.textContent='Về bản vẽ đang chọn';back.onclick=()=>viewRevision(revision,root).catch(e=>$('changeStatus').textContent=e.message);review.append(select,open,back);panel.append(review)}
 const count=document.createElement('p');count.id='revisionReviewStatus';count.textContent=`Đã xem ${revision.targets.filter(t=>(revision.previewed_targets||[]).includes(t.id)).length}/${revision.targets.length} bản vẽ trong bản sửa.`;panel.append(count);
 const solid=revision.solid_validation;if(solid?.checks?.length){const info=document.createElement('p');info.setAttribute('role','status');const planar=solid.checks.filter(c=>c.mode==='planar'),volumes=solid.checks.filter(c=>c.mode!=='planar');info.textContent=solid.status==='passed'?`FreeCAD đã kiểm tra ${[planar.length?`${planar.length} đường bao 2D và lỗ`:null,volumes.length?`${volumes.length} chi tiết dạng khối`:null].filter(Boolean).join('; ')}. ${solid.checks.filter(c=>c.scope==='centered_section_fit').map(c=>`Chi tiết ${c.part_code}: phần giao nhau với thành hộp ${Number(c.after.interference_volume_mm3).toFixed(6)} mm³.`).join(' ')} Kiểm tra này chưa bao gồm toàn bộ cụm lắp hoặc độ bền.`:'Chưa đạt kiểm tra hình học.';panel.append(info)}
 const solidFailed=['failed','error'].includes(solid?.status);if(solidFailed){const warning=document.createElement('p');warning.setAttribute('role','alert');warning.textContent='Bản sửa cũ có lỗi lắp ghép đã phát hiện. Hãy mở bản sửa mới nhất hoặc phân tích lại yêu cầu; bản này không được xuất.';panel.append(warning)}
 const dependencyChecks=(revision.pending_dependencies||[]).map(index=>{const dep=revision.dependencies[index];const label=document.createElement('label');label.style.display='block';const check=document.createElement('input');check.type='checkbox';label.append(check,document.createTextNode(`Kiểm tra liên kết ${dep.source_part} → ${dep.target_part}: ${dep.required_change}`));panel.append(label);return {index,check}});
 const exportFormat=cadCapabilities.dwg_export?'DWG':'DXF'; const extension=exportFormat.toLowerCase();
 const scopeLabel=document.createElement('label');scopeLabel.textContent='Phạm vi tệp tải: ';const exportScope=document.createElement('select');exportScope.setAttribute('aria-label','Phạm vi xuất backup');exportScope.add(new Option('Bản vẽ đã chọn và các khung liên quan được sửa','selection'));exportScope.add(new Option('Toàn bộ tài liệu gốc kèm thay đổi','document'));exportScope.value='selection';scopeLabel.append(exportScope);const scopeNote=document.createElement('p');scopeNote.textContent='Mặc định xuất phần đang sửa cùng bản chi tiết, bảng kê và công đoạn liên quan. Tài nguyên block được giữ để bảo toàn CAD.';
 const draft=document.createElement('button');draft.dataset.cadAction='export-dwg';draft.textContent=`Tải ${exportFormat} xem trước`;draft.disabled=solidFailed;
 const draftDxf=document.createElement('button');draftDxf.className='secondary';draftDxf.style.marginLeft='8px';draftDxf.textContent='Tải DXF xem trước (mọi CAD đều mở được)';draftDxf.disabled=solidFailed;draftDxf.onclick=async()=>{draftDxf.disabled=true;exportScope.disabled=true;try{await exportRevisionFile(revision,panel,'dxf',exportScope.value,true)}catch(e){if(panel.isConnected){downloadStatus.textContent=e.message;$('changeStatus').textContent=e.message}}finally{draftDxf.disabled=solidFailed;exportScope.disabled=false}};
 const downloadStatus=document.createElement('p');downloadStatus.className='export-status';downloadStatus.setAttribute('role','status');
 draft.onclick=async()=>{draft.disabled=true;exportScope.disabled=true;try{await exportRevisionFile(revision,panel,extension,exportScope.value,true)}catch(e){if(panel.isConnected){downloadStatus.textContent=e.message;$('changeStatus').textContent=e.message}}finally{draft.disabled=solidFailed;exportScope.disabled=false}};
 const downloads=document.createElement('details');downloads.className='technical-review advanced-downloads-accordion';downloads.id='revisionDownloads';
 const downloadsSummary=document.createElement('summary');downloadsSummary.textContent='⚙️ Tùy chọn xuất file nâng cao (DXF, phạm vi xuất khác)';
 downloads.append(downloadsSummary,scopeLabel,scopeNote,draft,draftDxf,downloadStatus);panel.append(downloads);restoreRevisionDownloads(revision,panel).catch(e=>{if(panel.isConnected)$('changeStatus').textContent=e.message});
 if(revision.complete_product_backup===false){const warning=document.createElement('p');warning.setAttribute('role','status');warning.textContent='BẢN SỬA MỘT PHẦN — chỉ dùng xem trước. '+(revision.preview_only_reason||'Còn liên kết chưa đồng bộ đầy đủ.');panel.prepend(warning)}
 const technicalStart=panel.children.length;const projectedViews=(revision.drawing_sync||[]).flatMap(r=>(r.verified_views||[]).map(v=>v.view));if(projectedViews.length){const info=document.createElement('p');info.setAttribute('role','status');info.textContent=`Hình đã đồng bộ và kiểm tra: ${projectedViews.join('; ')}.`;panel.append(info)}
 const incompleteAssembly=(revision.drawing_sync||[]).filter(r=>r.status==='unverified_projection_mapping');if(incompleteAssembly.length){const warning=document.createElement('p');warning.setAttribute('role','status');warning.textContent=`Đã sửa bản chi tiết, bảng kê và bản cắt. Còn ${incompleteAssembly.length} khung cụm lắp cần đồng bộ thêm hình chiếu/chi tiết phóng lớn; DWG hiện chỉ dùng xem trước. Chưa đủ điều kiện duyệt backup hoàn chỉnh.`;panel.append(warning)}const incompletePackaging=(revision.packaging_review||[]).some(r=>r.status==='unresolved_packaging');displayPackagingReview(revision,panel);displayFormingReview(revision,panel);displayRequestReview(revision,panel);const incompleteForming=(revision.forming_review||[]).some(r=>r.status==='unverified_developed_blank');const incompleteRequest=revision.request_review&&revision.request_review.status!=='complete';const finalBlocked=revision.complete_product_backup===false||solidFailed||revision.process_policy_version!==1||!Array.isArray(revision.drawing_sync)||incompleteAssembly.length>0||incompletePackaging||incompleteRequest||incompleteForming; const approve=document.createElement('button');approve.textContent=`Duyệt và tải ${exportFormat} backup hoàn chỉnh`;downloads.append(approve);if(revision.process_policy_version!==1){const warning=document.createElement('p');warning.textContent='Bản sửa này được tạo trước khi bổ sung kiểm tra toàn công đoạn. Phân tích lại yêu cầu để kiểm tra đủ liên kết trước khi duyệt và xuất backup hoàn chỉnh.';panel.append(warning);approve.disabled=true;}
 if(!Array.isArray(revision.drawing_sync)){const warning=document.createElement('p');warning.textContent='Bản sửa cũ chưa kiểm tra đồng bộ hình cụm lắp. Phân tích lại yêu cầu trước khi duyệt backup hoàn chỉnh.';panel.append(warning)}approve.disabled=finalBlocked;approve.title=finalBlocked?'Chưa đủ dữ liệu đồng bộ cụm lắp; dùng Tải DWG xem trước để đối chiếu.':'';approve.onclick=async()=>{if(finalBlocked)return;if(dependencyChecks.some(d=>!d.check.checked)){$('changeStatus').textContent=`Kiểm tra các liên kết kéo theo trước khi duyệt; có thể tải ${exportFormat} xem trước để đối chiếu.`;return}approve.disabled=true;try{
  await api(`/documents/${doc}/revisions/${revision.id}/approve`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmed_dependencies:dependencyChecks.map(d=>d.index)})});
  await exportRevisionFile(revision,panel,extension,exportScope.value,false);
 }catch(e){$('changeStatus').textContent=e.message}finally{approve.disabled=finalBlocked}};
 const technical=document.createElement('details');technical.className='technical-review';const technicalTitle=document.createElement('summary');technicalTitle.textContent='Chi tiết kiểm tra bản sửa';technical.append(technicalTitle);for(const child of Array.from(panel.children).slice(technicalStart))technical.append(child);panel.append(technical);
 if(geometryTarget&&autoView)viewRevision(revision,geometryTarget).catch(e=>$('changeStatus').textContent=e.message);
 return panel;
}
function addApply(result,ids,autoPreview=false,partial=false,autoDownloadDwg=false){
 const actions=$('planActions')||$('changeResult');const download=document.createElement('button');download.dataset.cadAction='create-dwg';
 download.textContent='Tạo và tải DWG xem trước';
 cadCapabilitiesReady.then(cap=>{download.textContent=`Tạo và tải ${cap.dwg_export?'DWG':'DXF'} xem trước`});
 const downloadDxf=document.createElement('button');downloadDxf.className='secondary';downloadDxf.textContent='Tải DXF xem trước (mọi CAD)';
 const view=document.createElement('button');view.textContent='Chỉ xem bản sửa';view.className='secondary-action';
 const status=document.createElement('p');status.className='export-status';status.setAttribute('role','status');
 if(!autoDownloadDwg)actions.append(download,downloadDxf,view,status);
 let created=null;
 const create=async(downloadFile=false,targetFormat=null)=>{if(creatingRevision)return;const documentId=doc;creatingRevision=true;download.disabled=true;downloadDxf.disabled=true;view.disabled=true;for(const id of ['chooseDrawing','analyze','planHistory','revisionHistory','docSelect'])$(id).disabled=true;
  try{
   renderProductStatusHero({status:'processing',step:2,message:'🛠️ Đang co giãn hình học, cập nhật DIM & bảng kê BOM...'});
   if(!created){$('changeStatus').className='status-editing';$('changeStatus').textContent='🛠️ AI đang chỉnh sửa bản vẽ DWG theo đúng yêu cầu... (1/2: Đang tạo bản sao an toàn & co giãn hình học/DIM)';status.textContent='1/2 · 🛠️ AI đang chỉnh sửa bản vẽ DWG: Đang tạo bản sao an toàn và co giãn hình học…';created=await api(`/documents/${documentId}/change-plans/${result.id}/${partial?'apply-checked-preview':'apply'}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmed_dependencies:[],preview_only:true})})}
   if(doc!==documentId)return;const panel=displayRevision(created,!downloadFile,false);if($('proposalMaterials'))$('proposalMaterials').open=false;await refreshRevisions(created.id);if(doc!==documentId)return;
   if(downloadFile){
    renderProductStatusHero({status:'processing',step:3,message:'📥 Đang đóng gói và xuất file AutoCAD DWG mới...'});
    $('changeStatus').className='status-editing';$('changeStatus').textContent='🛠️ AI đang hoàn tất chỉnh sửa: Đang kiểm tra tính toàn vẹn và đóng gói file DWG/DXF... (2/2)';status.textContent='2/2 · 🛠️ AI đang hoàn thiện bản vẽ: Kiểm tra toàn vẹn và chuẩn bị xuất file…';
    await cadCapabilitiesReady;const format=targetFormat||(cadCapabilities.dwg_export?'dwg':'dxf');
    const ready=await exportRevisionFile(created,panel,format,'selection',true);
    $('changeStatus').className='status-success';$('changeStatus').textContent=`✅ Đã chỉnh sửa xong bản vẽ DWG! File ${format.toUpperCase()} đã tải về máy thành công.`;status.textContent=`✅ Đã chỉnh sửa xong và tải thành công bản ${format.toUpperCase()}! Bấm đường dẫn tải màu xanh nếu trình duyệt chưa tự mở.`;
    renderProductStatusHero({status:'success',revision:created,planResult:result,downloadUrl:ready?.download_url,userRequest:$('changeRequest')?.value});
    window.showDownloadSuccessNotification?.({format,revisionId:created.id});
   }
   else{
    $('changeStatus').className='status-success';$('changeStatus').textContent=`✅ Đã chỉnh sửa xong bản vẽ DWG! Bản sửa #${created.id.slice(0,8)} đã sẵn sàng xem trước và tải về.`;status.textContent='✅ Đã chỉnh sửa xong bản sửa DWG! Bấm Sau sửa để xem hình hoặc Tải DWG xem trước để tải file.';
    renderProductStatusHero({status:'success',revision:created,planResult:result,userRequest:$('changeRequest')?.value});
   }
  }catch(e){
   if(doc===documentId){
     status.textContent=e.message;$('changeStatus').textContent=e.message;
     renderProductStatusHero({status:'failed',message:e.message,userRequest:$('changeRequest')?.value});
   }
  }
  finally{creatingRevision=false;download.disabled=false;downloadDxf.disabled=false;view.disabled=false;for(const id of ['chooseDrawing','planHistory','revisionHistory','docSelect'])$(id).disabled=analyzing;checkAI()}
 };
 download.onclick=()=>create(true,'dwg');downloadDxf.onclick=()=>create(true,'dxf');view.onclick=()=>create(false);
 if(autoDownloadDwg)create(true,'dwg');
 else if(autoPreview)create(false);
}
let historyGeneration=0;
async function refreshHistory(preferred){if(!doc)return;const documentId=doc,epoch=++historyGeneration,previous=preferred??$('planHistory').value;try{const history=await api(`/documents/${documentId}/change-plans?summary=true`);if(doc!==documentId||epoch!==historyGeneration)return;const current=preferred??($('planHistory').value||previous);$('planHistory').replaceChildren(new Option('Chọn kế hoạch trước',''));history.items.forEach(p=>$('planHistory').add(new Option(`#${p.id.slice(0,8)} · ${p.request.slice(0,100)}`,p.id)));if(history.items.some(p=>p.id===current))$('planHistory').value=current}catch(e){if(doc===documentId&&epoch===historyGeneration)$('changeStatus').textContent=e.message}}
let revisionItems=[];
async function refreshRevisions(preferred){if(!doc)return;const documentId=doc,previous=preferred??$('revisionHistory').value;const data=await api(`/documents/${documentId}/revisions?summary=true`);if(doc!==documentId)return;revisionItems=data.items;$('revisionHistory').replaceChildren(new Option('Chọn bản sửa trước',''));for(const r of revisionItems)$('revisionHistory').add(new Option(`#${r.id.slice(0,8)} · ${r.complete_product_backup===false?'Xem trước một phần':r.status==='validated'?'Đã kiểm tra CAD; chưa duyệt':r.status}`,r.id));if(revisionItems.some(r=>r.id===previous))$('revisionHistory').value=previous;window.updateQuickActions?.()}
$('revisionHistory').onchange=async()=>{
  if(analyzing||creatingRevision)return;
  const val=$('revisionHistory').value;
  if(!val){
    window.activeRevision=null;
    window.updateQuickActions?.();
    renderProductStatusHero({status:'baseline',historyCount:revisionItems.length});
    if(items&&items[0])show(items[0],false);
    return;
  }
  const r=revisionItems.find(i=>i.id===val);
  if(!r)return;
  const documentId=doc;
  $('changeResult').replaceChildren();
  $('changeStatus').textContent='Đang mở bản sửa lịch sử đã lưu…';
  try{
    const revision=await api(`/documents/${documentId}/revisions/${r.id}?summary=true`);
    if(doc===documentId&&$('revisionHistory').value===r.id){
      displayRevision(revision,true,true);
      $('changeStatus').textContent=`Đang xem bản sửa lịch sử #${r.id.slice(0,8)}. Bấm "Quay lại bản gốc" nếu muốn xem file gốc ban đầu.`;
    }
  }catch(e){if(doc===documentId)$('changeStatus').textContent=e.message}
};
"""

new_lines = lines[:start_idx] + [replacement] + lines[end_idx:]

with open(r'd:\mechanical-ai-drawing\frontend\index.html', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Replacement successful! Total new lines:", len(new_lines))
