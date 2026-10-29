/* Presentation helpers; CAD selection, plans and rendering remain in the existing engine. */
(() => {
  const byId=id=>document.getElementById(id);
  const scroll=id=>byId(id)?.scrollIntoView({block:'start',behavior:'smooth'});
  let host;
  const activate=id=>{
    for(const button of document.querySelectorAll('.step'))button.classList.toggle('active',button.id===id);
  };
  byId('stepUpload').onclick=()=>{activate('stepUpload');scroll('fileLibrary')};
  byId('stepSelect').onclick=()=>{
    if(analyzing||creatingRevision)return;
    byId('workspace').classList.remove('request-mode');
    if(workItem)byId('chooseDrawing').click();
    activate('stepSelect');scroll('catalogTools');
  };
  byId('stepRequest').onclick=()=>{
    if(!doc){byId('status').textContent='Mở file trước khi nhập yêu cầu chỉnh sửa.';scroll('fileLibrary');return}
    if(!workItem&&!byId('wholeDocumentRequest').checked){byId('status').textContent='Chọn hình hoặc bật tìm chi tiết trong toàn file.';scroll('catalogTools');return}
    if(workItem&&!byId('workspace').classList.contains('focused'))focusItem(workItem);
    byId('workspace').classList.add('request-mode');
    if(!workItem)byId('editTarget').textContent='Tìm chi tiết trên toàn file đang mở; tự mở rộng các khung có liên kết nguồn.';
    activate('stepRequest');scroll('editorPanel');byId('changeRequest').focus();
  };
  byId('stepResult').onclick=()=>{
    if(!workItem){byId('status').textContent='Mở file và chọn bản vẽ để xem kết quả.';scroll('fileLibrary');return}
    if(!byId('workspace').classList.contains('focused'))focusItem(workItem);
    activate('stepResult');scroll('changeResult');
    if(!byId('changeResult').children.length){byId('changeStatus').textContent='Chưa có kết quả trong phiên này. Phân tích yêu cầu hoặc mở bản sửa trong lịch sử.';byId('planHistory').closest('details').open=true}
  };
  function latestScopedRevision(){
    if(window.activeRevision&&(!doc||window.activeRevision.document_id===doc||!window.activeRevision.document_id))return window.activeRevision;
    if(!doc)return revisionItems[0]||null;
    const target=workItem||activeItem;
    if(target&&revisionItems.length){
      const scoped=revisionItems.find(r=>(!r.document_id||r.document_id===doc)&&[...(r.root_target_ids||[]),...(r.target_ids||[])].includes(target.id));
      if(scoped)return scoped;
    }
    return revisionItems.find(r=>!r.document_id||r.document_id===doc)||revisionItems[0]||null;
  }
  function showDownloadSuccessNotification(info={}){
    const format=(info.format||'DWG').toUpperCase();
    const revisionId=info.revisionId||'';
    const oldToast=document.getElementById('downloadSuccessToast');
    if(oldToast)oldToast.remove();

    const toast=document.createElement('div');
    toast.id='downloadSuccessToast';
    toast.className='download-success-toast';
    toast.setAttribute('role','alert');
    const revText=revisionId?` (Bản sửa #${revisionId.slice(0,8)})`:'';
    toast.innerHTML=`
      <span class="toast-icon">✅</span>
      <div class="toast-content">
        <div class="toast-title">Đã tải thành công bản ${format} đã chỉnh sửa!</div>
        <div class="toast-desc">File ${format}${revText} đã được tải về máy của bạn. Vui lòng kiểm tra thư mục Downloads.</div>
      </div>
      <button type="button" class="toast-close" aria-label="Đóng" onclick="this.parentElement.remove()">✕</button>
    `;
    document.body.appendChild(toast);
    setTimeout(()=>{
      if(toast.isConnected){
        toast.classList.add('toast-hide');
        setTimeout(()=>toast.remove(),400);
      }
    },6000);
  }
  window.showDownloadSuccessNotification=showDownloadSuccessNotification;

  function triggerDownload(url,format='dwg',revisionId=''){
    const filename=`PREVIEW-backup-${(revisionId||'rev').slice(0,8)}.${format}`;
    const directLink=byId('quickBannerDirectLink');
    if(directLink){
      directLink.href=url;
      directLink.download=filename;
      directLink.hidden=false;
      directLink.style.display='inline-flex';
      directLink.textContent=`📥 Bấm vào đây để tải trực tiếp file ${format.toUpperCase()} (${filename})`;
    }
    const a=document.createElement('a');
    a.style.display='none';
    a.href=url;
    a.setAttribute('download',filename);
    document.body.appendChild(a);
    a.click();
    setTimeout(()=>{a.remove()},2000);
    showDownloadSuccessNotification({format,revisionId});
  }
  function downloadControl(){return byId('changeResult').querySelector('[data-cad-action="export-dwg"]')||byId('changeResult').querySelector('[data-cad-action="create-dwg"]')}
  async function downloadRevisionDirect(format='dwg'){
    const revision=latestScopedRevision();
    if(!revision||!doc)return;
    const bannerStatus=byId('quickBannerStatus');
    const dwgBtn=byId('btnQuickDwgDownload'),dxfBtn=byId('btnQuickDxfDownload');
    dwgBtn.disabled=true;dxfBtn.disabled=true;
    if(bannerStatus)bannerStatus.textContent=`Đang kiểm tra và chuẩn bị file ${format.toUpperCase()} xem trước…`;
    try{
      const exportsList=await api(`/documents/${doc}/revisions/${revision.id}/exports`).catch(()=>({items:[]}));
      const readyJob=exportsList.items?.find(j=>j.status==='ready'&&j.format===format&&j.preview&&j.scope==='document') || exportsList.items?.find(j=>j.status==='ready'&&j.format===format&&j.preview);
      if(readyJob&&readyJob.download_url){
        triggerDownload(readyJob.download_url,format,revision.id);
        if(bannerStatus)bannerStatus.textContent=`✅ Đã tải file ${format.toUpperCase()} toàn bộ tài liệu gốc kèm thay đổi (bản sửa #${revision.id.slice(0,8)}). Bấm nút màu xanh nếu trình duyệt chưa tự mở file.`;
        return;
      }
      if(bannerStatus)bannerStatus.textContent=`1/2 · Đang tạo file ${format.toUpperCase()} toàn bộ tài liệu gốc kèm thay đổi…`;
      const job=await api(`/documents/${doc}/revisions/${revision.id}/exports`,{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({format,scope:'document',preview:true})
      });
      let currentJob=job;
      while(currentJob.status==='queued'||currentJob.status==='running'){
        if(bannerStatus)bannerStatus.textContent=currentJob.message||`Đang xuất file ${format.toUpperCase()}…`;
        await new Promise(r=>setTimeout(r,1500));
        currentJob=await api(`/documents/${doc}/revisions/${revision.id}/exports/${currentJob.id}`);
      }
      if(currentJob.status==='ready'&&currentJob.download_url){
        triggerDownload(currentJob.download_url,format,revision.id);
        if(bannerStatus)bannerStatus.textContent=`✅ Đã tạo file ${format.toUpperCase()} toàn bộ tài liệu gốc kèm thay đổi thành công! Bấm nút màu xanh nếu trình duyệt chưa tự mở file.`;
      }else{
        throw Error(currentJob.message||'Không thể tạo file');
      }
    }catch(err){
      if(bannerStatus)bannerStatus.textContent='Lỗi tải file: '+err.message;
      byId('changeStatus').textContent=err.message;
    }finally{
      dwgBtn.disabled=false;dxfBtn.disabled=false;
    }
  }
  byId('btnQuickDwgDownload').onclick=()=>downloadRevisionDirect('dwg');
  byId('btnQuickDxfDownload').onclick=()=>downloadRevisionDirect('dxf');
  function updateQuickActions(){
    const button=byId('quickDwgCreate'),open=byId('quickOpenRevision'),history=byId('quickOpenHistory'),hint=byId('quickDwgHint'),banner=byId('quickDownloadBanner'),bannerRev=byId('quickBannerRevisionLabel');
    const busy=analyzing||creatingRevision,control=downloadControl(),revision=latestScopedRevision(),target=workItem||activeItem;
    const format=cadCapabilities.dwg_export?'DWG':'DXF';
    const activeRev=doc&&window.activeRevision&&(!doc||window.activeRevision.document_id===doc||!window.activeRevision.document_id)?window.activeRevision:null;
    
    // Only show quick download banner if an active revision was actually created or explicitly opened in this session
    if(activeRev&&doc){
      if(banner)banner.hidden=false;
      if(bannerRev)bannerRev.textContent=`Bản sửa #${activeRev.id.slice(0,8)}${activeRev.complete_product_backup===false?' (Xem trước)':''}`;
      api(`/documents/${doc}/revisions/${activeRev.id}/exports`).then(res=>{
        const readyJob=res.items?.find(j=>j.status==='ready'&&j.format==='dwg'&&j.preview&&j.scope==='document') || res.items?.find(j=>j.status==='ready'&&j.format==='dwg'&&j.preview);
        const directLink=byId('quickBannerDirectLink');
        if(readyJob&&readyJob.download_url&&directLink){
          directLink.href=readyJob.download_url;
          directLink.download=`PREVIEW-backup-${activeRev.id.slice(0,8)}.dwg`;
          directLink.hidden=false;
          directLink.style.display='inline-flex';
          directLink.textContent=`📥 Bấm vào đây để tải ngay file DWG toàn bộ bản vẽ (#${activeRev.id.slice(0,8)})`;
        }
      }).catch(()=>{});
    }else{
      if(banner)banner.hidden=true;
    }
    button.disabled=busy||!doc||Boolean(control?.disabled);
    open.disabled=busy||!doc||!revision;
    history.disabled=busy||!doc;

    if(control?.dataset.cadAction==='create-dwg'){
      button.textContent=`Tạo và tải ${format} từ yêu cầu`;
    }else if(activeRev){
      button.textContent=`Tải ${format} bản sửa (xem trước)`;
    }else{
      button.textContent=`Tạo và tải ${format} từ yêu cầu`;
    }

    hint.textContent=!doc?'Chưa chọn file bản vẽ. Chọn một file từ danh sách hoặc tải lên file DWG/DXF để bắt đầu.':busy?'Đang xử lý. Vui lòng đợi trong giây lát…':control?'Bấm nút trên để tạo/tải bản đã thay đổi.':activeRev?`Bản sửa #${activeRev.id.slice(0,8)} đã sẵn sàng. Bấm để tải file ${format}.`:`Nhập yêu cầu rồi bấm nút trên để AI tự động phân tích và tải file ${format}.`;
    button.title=button.disabled?hint.textContent:'';
  }
  window.updateQuickActions=updateQuickActions;
  async function openLatestRevision(){
    const revision=latestScopedRevision();if(!revision||analyzing||creatingRevision)return;
    const rootId=revision.root_target_ids?.[0]||revision.target_ids?.[0];
    if(rootId&&(!workItem||!revision.target_ids?.includes(workItem.id))){
      const targetObj=sourceTarget(rootId);
      if(targetObj)await show(targetObj,true);
    }
    byId('revisionHistory').value=revision.id;await byId('revisionHistory').onchange();
  }
  byId('quickOpenHistory').onclick=()=>{byId('revisionHistory').closest('details').open=true;scroll('revisionHistory')};
  byId('quickOpenRevision').onclick=async()=>{try{await openLatestRevision();scroll('changeResult')}catch(error){byId('changeStatus').textContent=error.message}};
  byId('quickDwgCreate').onclick=async()=>{
    if(analyzing||creatingRevision)return;
    if(!doc){
      byId('changeStatus').textContent='Vui lòng chọn một file bản vẽ để bắt đầu.';
      return;
    }
    const hasRequestText=Boolean(byId('changeRequest')?.value?.trim());
    const control=downloadControl();
    const activeRev=doc&&window.activeRevision&&(!doc||window.activeRevision.document_id===doc||!window.activeRevision.document_id)?window.activeRevision:null;

    // 1. If active revision was already created and loaded, download DWG
    if(activeRev){
      await downloadRevisionDirect('dwg');
      return;
    }

    // 2. If a plan has been generated with create-dwg button ready
    if(control&&!control.disabled){
      control.click();
      scroll('changeResult');
      return;
    }

    // 3. If user typed a request, run automated pipeline
    if(hasRequestText){
      if(typeof window.submitDrawingRequest==='function'){
        window.submitDrawingRequest(null,null,true);
      }else if(byId('analyze')){
        byId('analyze').click();
      }
      return;
    }

    // 4. If no request: prompt user clearly, DO NOT default to old revisions!
    byId('changeRequest')?.focus();
    byId('changeStatus').textContent='Vui lòng nhập yêu cầu chỉnh sửa (ví dụ: Chi tiết 1 hạ từ 463 xuống 400), sau đó bấm Tự động sửa & Xuất file DWG.';
    window.renderProductStatusHero?.({
      status:'failed',
      message:'Vui lòng nhập yêu cầu chỉnh sửa vào ô bên dưới trước khi thực hiện.',
      reason:'Chưa nhập nội dung yêu cầu chỉnh sửa.'
    });
  };
  const actionsObserver=new MutationObserver(updateQuickActions);
  for(const id of ['changeResult','revisionHistory','changeStatus','workspaceBar','analyze'])actionsObserver.observe(byId(id),{childList:true,subtree:true,attributes:true,attributeFilter:['disabled']});
  byId('docSelect').addEventListener('change',updateQuickActions);
  window.addEventListener('cad-document-ready',updateQuickActions);
  window.addEventListener('cad-document-changed',updateQuickActions);
  cadCapabilitiesReady.then(updateQuickActions);
  updateQuickActions();
  let databaseLoad=0;
  async function loadDatabase(){
    const epoch=++databaseLoad,button=byId('refreshDatabase'),badge=byId('databaseBadge');if(button)button.disabled=true;
    try{
      let result=await api('/database/health');if(epoch!==databaseLoad)return;
      if(result.details_allowed){result=await api('/database/status');if(epoch!==databaseLoad)return;}
      if(badge){badge.dataset.ready=String(Boolean(result.ready));badge.textContent=result.backend==='postgresql'?(result.ready?'PostgreSQL · đã kết nối':'PostgreSQL · chưa kết nối'):(result.ready?'SQLite · đang dùng':'Database · chưa kết nối');}
      if(byId('databaseStatus'))byId('databaseStatus').textContent=result.message;if(byId('databaseCounts'))byId('databaseCounts').textContent=result.ready?`${result.documents} tài liệu · ${result.revisions} phiên bản sửa trong chỉ mục (gồm lịch sử và file thử).`:'';
      const list=byId('databaseConnection');if(list){list.replaceChildren();
      for(const [key,label] of [['host','Host'],['port','Cổng'],['database','Database'],['username','Tài khoản ứng dụng']]){
        if(result.connection_info?.[key]==null)continue;const term=document.createElement('dt'),value=document.createElement('dd');term.textContent=label;value.textContent=String(result.connection_info[key]);list.append(term,value)
      }}
    }catch(error){if(epoch===databaseLoad&&badge){badge.dataset.ready='false';badge.textContent='Database · không kiểm tra được';if(byId('databaseStatus'))byId('databaseStatus').textContent='Không đọc được trạng thái database. Kiểm tra server rồi bấm thử lại.';byId('databaseConnection')?.replaceChildren();if(byId('databaseCounts'))byId('databaseCounts').textContent=''}}
    finally{if(epoch===databaseLoad&&button)button.disabled=false}
  }
  if(byId('refreshDatabase'))byId('refreshDatabase').onclick=loadDatabase;
  if(byId('databaseBadge'))byId('databaseBadge').onclick=event=>{event.preventDefault();byId('databasePanel').open=true;scroll('databasePanel')};
  void loadDatabase();
  function documentReady(){
    const current=window.documentReadingStatus,notice=byId('nativeDocumentNotice');
    notice.hidden=!(host?.configured&&host.read_backend==='autocad'&&current?.status==='ready'&&current.read_backend!=='autocad');
    if(!notice.hidden)byId('nativeDocumentText').textContent='File này được nhập bằng bộ đọc cũ. Mở bản sao bằng AutoCAD để đọc tham số và dữ liệu native; lịch sử hiện tại được giữ.';
  }
  window.addEventListener('cad-document-ready',documentReady);
  byId('apsPanel').addEventListener('toggle',()=>{if(byId('apsPanel').open)byId('advancedTools').open=true});
  byId('nativeImportShortcut').onclick=async()=>{
    if(analyzing||creatingRevision)return;
    const button=byId('nativeImportShortcut');button.disabled=true;
    try{
      byId('advancedTools').open=byId('apsPanel').open=true;
      await window.beginLocalNativeImport();
    }catch(error){byId('nativeDocumentText').textContent=error.message}
    finally{button.disabled=false}
  };
  api('/aps/status').then(aps=>{
    const badge=byId('engineBadge');
    if(aps.configured){
      badge.dataset.ready='true';
      badge.textContent='⚡ Động cơ: Autodesk APS Cloud (Tự động)';
      if(!aps.live_verified){
        api('/aps/connection',{method:'POST'}).catch(()=>{});
      }
    }else{
      api('/autocad/status').then(status=>{
        host=status;badge.dataset.ready=String(Boolean(status.configured));
        badge.textContent=status.configured?'⚡ AutoCAD trên máy · Sẵn sàng':'⚡ Bộ xử lý CAD ODA (Tự động)';
        documentReady();
      }).catch(()=>{badge.textContent='⚡ Bộ xử lý CAD (Tự động)'});
    }
  }).catch(()=>{
    api('/autocad/status').then(status=>{
      host=status;const badge=byId('engineBadge');badge.dataset.ready=String(Boolean(status.configured));
      badge.textContent=status.configured?'⚡ AutoCAD trên máy · Sẵn sàng':'⚡ Bộ xử lý CAD ODA (Tự động)';
    }).catch(()=>{byId('engineBadge').textContent='⚡ Bộ xử lý CAD (Tự động)'});
  });
})();
