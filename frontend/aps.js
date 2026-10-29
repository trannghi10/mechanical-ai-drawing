/* Native CAD controls are separate from the AI provider and selection gallery. */
(() => {
  let settings, timer, epoch = 0, chooseInitialProvider = true;
  const panel = document.getElementById('apsPanel');
  const status = document.getElementById('apsStatus');
  const jobs = document.getElementById('apsJobs');
  const inspect = document.getElementById('apsInspect');
  const refresh = document.getElementById('apsRefresh');
  const providerSelect=document.createElement('select');providerSelect.id='nativeProvider';providerSelect.setAttribute?.('aria-label','Bộ xử lý CAD native');
  for(const [value,label] of [['aps','Autodesk APS · cloud'],['autocad','AutoCAD trên máy']]){
    const option=document.createElement('option');option.value=value;option.textContent=label;providerSelect.append(option);
  }
  providerSelect.value='aps';panel.insertBefore(providerSelect,jobs);
  const routing=document.createElement('p');routing.id='nativeRouting';routing.className='native-routing';panel.insertBefore(routing,jobs);
  const verification=document.createElement('p');verification.id='nativeVerification';panel.insertBefore(verification,jobs);
  const guide=document.createElement('a');guide.href='/help#aps';guide.textContent='Hướng dẫn dùng AutoCAD / APS từng bước ↗';guide.target='_blank';guide.rel='noopener';panel.insertBefore(guide,jobs);
  const connection=document.createElement('button');connection.textContent='Kiểm tra kết nối APS';connection.className='secondary';connection.hidden=true;panel.insertBefore(connection,jobs);
  const connectionStatus=document.createElement('p');connectionStatus.setAttribute?.('role','status');panel.insertBefore(connectionStatus,jobs);
  const sameScope=(documentId,route)=>doc===documentId&&providerSelect.value===route;
  const cloudCopy=document.createElement('button');cloudCopy.id='nativeImport';cloudCopy.textContent='Mở bản sao bằng APS (gửi Autodesk)';
  const readParameters=document.createElement('button');readParameters.textContent='Đọc tham số bản vẽ đang chọn';
  const recover=document.createElement('button');recover.textContent='Tạo bản DWG phục hồi';recover.hidden=true;
  recover.title='Chỉ tạo bản sao phục hồi nguồn lỗi. Tải và đối chiếu trước khi dùng làm đầu vào; đây chưa phải bản sửa thiết kế.';
  const parameters=document.createElement('div');
  panel.insertBefore(cloudCopy,jobs);panel.insertBefore(readParameters,jobs);panel.insertBefore(recover,jobs);panel.insertBefore(parameters,jobs);
  const readCenters=document.createElement('button');readCenters.id='nativeReadCenters';readCenters.textContent='Đọc dấu tâm của bản vẽ đang chọn';readCenters.hidden=true;
  const centers=document.createElement('div');centers.id='nativeCenters';panel.insertBefore(readCenters,jobs);panel.insertBefore(centers,jobs);
  let centerDocument,centerGeneration=0;
  let parameterDocument,parameterGeneration=0;
  const labels = {queued:'Đang chờ',uploading:'Đang tải lên',submitting:'Đang gửi tác vụ',processing:'AutoCAD đang xử lý',validating:'Đang kiểm tra',ready:'Đã có kết quả',failed:'Chưa hoàn tất'};
  async function load() {
    clearTimeout(timer);window.syncRectangleEditor?.();
    const documentId = doc, current = ++epoch,route=providerSelect.value;
    try {
      const received = await api(`/${route}/status`);
      if (current !== epoch || !sameScope(documentId,route)) return;
      settings=received;
      if(chooseInitialProvider){
        chooseInitialProvider=false;
        if(route==='aps'&&(settings.read_backend==='autocad'||settings.backend==='autocad')){
          providerSelect.value='autocad';return load();
        }
      }
      const names={aps:'APS cloud',autocad:'AutoCAD trên máy',oda:'ODA'};
      status.textContent = `${settings.message||'Chưa có trạng thái bộ xử lý.'} ${settings.cloud_disclosure||''}`;
      routing.textContent=`Tải file mới: ${names[settings.read_backend]||settings.read_backend}. Xuất bản sửa thông thường: ${names[settings.backend]||settings.backend}. Lựa chọn bên trên chỉ áp dụng cho các công cụ trong mục này. ${route==='aps'?'Bấm “Mở bản sao bằng APS” để nhập lại file đang mở bằng cloud.':'AutoCAD xử lý trên máy.'}`;
      const verifiedDate=new Date(settings.verified_at);
      verification.textContent=settings.live_verified?`Đã mở lại DWG kiểm chứng${settings.verified_at&&!Number.isNaN(verifiedDate.getTime())?' lúc '+verifiedDate.toLocaleString('vi-VN'):''}. Đây là kết quả kiểm chứng trước đó, không xác nhận mọi liên kết của file đang mở.`:'Chưa có bằng chứng chạy DWG khớp cấu hình hiện tại.';
      connection.hidden=route!=='aps';connection.disabled=!settings.configured;
      inspect.textContent=route==='autocad'?'Đọc CAD bằng AutoCAD trên máy':'Đọc toàn bộ DWG bằng APS (gửi Autodesk)';
      cloudCopy.textContent=route==='autocad'?'Mở bản sao bằng AutoCAD trên máy':'Mở bản sao bằng APS (gửi Autodesk)';
      if(settings.missing?.length)status.textContent+=' Thiếu: '+settings.missing.join(', ')+'. Điền trên server trong .env; không nhập secret vào trình duyệt.';
      inspect.disabled = !settings.configured || !documentId;
      cloudCopy.disabled=inspect.disabled;readParameters.disabled=inspect.disabled;
      recover.hidden=route!=='autocad';recover.disabled=inspect.disabled||route!=='autocad';
      readCenters.hidden=route!=='autocad';readCenters.disabled=inspect.disabled||route!=='autocad';
      const uploadButton=document.getElementById('upload').querySelector('button');
      uploadButton.textContent=settings.read_backend==='aps'?'Tải file lên APS':'Tải file mới';
      uploadButton.title=settings.read_backend==='aps'?settings.cloud_disclosure:'Đọc file trên máy';
      if(parameterDocument!==documentId){parameters.replaceChildren();parameterDocument=documentId;++parameterGeneration;}
      if(centerDocument!==documentId){centers.replaceChildren();centerDocument=documentId;++centerGeneration;}
      jobs.replaceChildren();
      if (!documentId) return;
      const result = await api(`/documents/${documentId}/${route}/jobs`);
      if (current !== epoch || documentId !== doc) return;
      let pending = false;
      for (const job of result.items) {
        const row = document.createElement('div');row.className='native-job';
        row.textContent = `${job.mode === 'inspect' ? 'Đọc CAD native' : job.mode === 'edit' ? 'Sửa native' : job.mode === 'recover' ? 'Phục hồi bản sao nguồn' : 'Xuất DWG'} #${job.id.slice(0,8)} · ${labels[job.status] || job.status}. ${job.message}`;
        const count = job.native_summary?.summary;
        if (count) row.append(document.createTextNode(` ${count.block_count} block definitions; ${count.entity_count} đối tượng.`));
        for(const effect of job.native_summary?.dynamic_effects||[]){
          const changes=effect.after.parameters.map((p,index)=>({...p,before:effect.before.parameters[index]?.name===p.name?effect.before.parameters[index].value:undefined})).filter(p=>p.value!==p.before);
          const detail=document.createElement('details'),caption=document.createElement('summary');caption.textContent=`Block #${effect.source_ref||effect.handle}: ${changes.length} tham số thay đổi sau khi mở lại DWG`;detail.append(caption);
          const list=document.createElement('ul');for(const property of changes){const li=document.createElement('li');li.textContent=`${property.name}: ${property.before??'chưa đối chiếu'} → ${property.value}`;list.append(li)}detail.append(list);row.append(detail);
        }
        for(const effect of job.native_summary?.centermark_effects||[]){
          const detail=document.createElement('p');detail.textContent=`Đường tròn #${effect.circle_handle} và dấu tâm: dịch [${effect.delta.join(', ')}] theo tọa độ CAD nguồn; đã đối chiếu sau khi mở lại DWG. Các chi tiết xung quanh cần kiểm tra riêng.`;row.append(detail);
        }
        const rectangle=job.native_summary?.rectangle_stretch_effects;
        if(rectangle){
          const detail=document.createElement('p');detail.textContent=`Hình chữ nhật: ${rectangle.source_width_mm} → ${rectangle.target_width_mm} mm; giữ cạnh trái và chiều cao, DIM đã kiểm sau mở lại.`;row.append(detail);
          const source=result.items.find(item=>item.mode==='inspect'&&item.status==='ready'&&item.source_hash===job.source_hash);
          if(source){const compare=document.createElement('button');compare.textContent='Đối chiếu chữ nhật';compare.onclick=()=>window.showRectangleComparison?.(documentId,route,source.id,job.id,rectangle);row.append(compare);}
        }
        for (const [url,label] of [[job.inventory_url,'Tải dữ liệu CAD native'],[job.download_url,job.mode==='recover'?'Tải DWG phục hồi · cần đối chiếu':'Tải DWG xem trước']]) {
          if (!url) continue;
          const link = document.createElement('a');
          link.href = url; link.textContent = label; link.className='native-download';
          row.append(link);
        }
        if(job.status==='ready'&&job.derivative_status){
          const metadata=document.createElement('button');metadata.textContent='Kiểm tra metadata Viewer';
          metadata.onclick=async()=>{metadata.disabled=true;try{const result=await api(`/documents/${documentId}/${route}/jobs/${job.id}/derivative`,{method:'POST'});if(sameScope(documentId,route))status.textContent=`Model Derivative: ${result.status}. ${result.views.length} khung nhìn. ${result.note}`;}catch(error){if(sameScope(documentId,route))status.textContent=error.message;}finally{metadata.disabled=false;}};
          row.append(metadata);
        }
        if(job.status==='ready'&&job.target_ids?.length){
          const view=document.createElement('button');view.textContent='Xem hình sau sửa';
          view.onclick=async()=>{
            const targetId=job.target_ids[0],version=++generation;view.disabled=true;
            try{
              const response=await fetch(`/documents/${documentId}/${route}/jobs/${job.id}/preview/${encodeURIComponent(targetId)}`);
              if(!response.ok)throw Error((await response.json()).detail);
              const blob=await response.blob();if(doc!==documentId||version!==generation)return;
              const img=document.getElementById('preview'),old=img.dataset.url;if(old)URL.revokeObjectURL(old);
              const url=URL.createObjectURL(blob);img.dataset.url=url;img.src=url;img.hidden=false;
              document.getElementById('comparisonBar').hidden=true;setZoom(1);
              document.getElementById('previewStatus').textContent=`Bản sửa ${route==='aps'?'APS':'AutoCAD local'} #${job.id.slice(0,8)} · phạm vi #${targetId}. Đây là bản xem trước tham số, chưa xác nhận đầy đủ liên kết lắp ghép.`;
              revealViewer(`CAD sau sửa #${job.id.slice(0,8)}`);
            }catch(error){if(sameScope(documentId,route))status.textContent=error.message;}finally{view.disabled=false;}
          };
          row.append(view);
        }
        jobs.append(row);
        if (!['ready','failed'].includes(job.status)) {
          pending = true;
          // Status requests resume already-authorized jobs after a restart.
          await api(`/documents/${documentId}/${route}/jobs/${job.id}`);
        }
      }
      if (pending && current === epoch && documentId === doc) timer = setTimeout(load, 5000);
    } catch (error) {
      if (current === epoch && documentId === doc) status.textContent = error.message;
    }
  }
  inspect.onclick = async () => {
    const documentId = doc,route=providerSelect.value;
    if (!documentId || !settings?.configured) return;
    inspect.disabled = true;
    try {
      await api(`/documents/${documentId}/${route}/jobs`, {method:'POST'});
      if (sameScope(documentId,route)) await load();
    } catch (error) {
      if (sameScope(documentId,route)) status.textContent = error.message;
    } finally { inspect.disabled = !settings?.configured || !doc; }
  };
  refresh.onclick = load;
  connection.onclick=async()=>{
    if(providerSelect.value!=='aps'||!settings?.configured)return;
    const documentId=doc,current=epoch;connection.disabled=true;
    connectionStatus.textContent='Đang kiểm tra tài khoản, Activity và bucket; không gửi bản vẽ…';
    try{
      const result=await api('/aps/connection',{method:'POST'});
      if(current===epoch&&sameScope(documentId,'aps'))connectionStatus.textContent=`Kết nối APS đạt: tài khoản, Activity và bucket. Không gửi CAD, không chạy tác vụ chỉnh sửa. ${result.note}`;
    }catch(error){if(current===epoch&&sameScope(documentId,'aps'))connectionStatus.textContent=error.message;}
    finally{if(current===epoch)connection.disabled=!settings?.configured;}
  };
  providerSelect.onchange=()=>{
    chooseInitialProvider=false;
    settings=null;inspect.disabled=cloudCopy.disabled=readParameters.disabled=recover.disabled=true;
    ++generation;++parameterGeneration;parameters.replaceChildren();connectionStatus.textContent='';parameterDocument=null;void load();
    ++centerGeneration;centers.replaceChildren();centerDocument=null;readCenters.disabled=true;
  };
  readCenters.onclick=async()=>{
    const documentId=doc,target=workItem||activeItem,version=++centerGeneration;
    centers.replaceChildren();centerDocument=documentId;
    if(!documentId||!target||providerSelect.value!=='autocad'){status.textContent='Chọn bản vẽ và AutoCAD trên máy trước khi đọc dấu tâm.';return;}
    const same=()=>sameScope(documentId,'autocad')&&(workItem||activeItem)?.id===target.id&&version===centerGeneration;
    readCenters.disabled=true;
    try{
      status.textContent='Đang kiểm tra dấu tâm trong bản vẽ đang chọn…';
      const context=await api(`/documents/${documentId}/autocad/context`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:[target.id]})});
      if(!same())return;
      let job=await api(`/documents/${documentId}/autocad/centermark-inspections`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:[target.id]})});
      const deadline=Date.now()+300000;
      while(same()&&!['ready','failed'].includes(job.status)){
        if(Date.now()>deadline)throw Error('Tác vụ đọc dấu tâm vẫn đang chạy; xem danh sách tác vụ và đọc lại sau.');
        await new Promise(resolve=>setTimeout(resolve,1000));if(!same())return;
        job=await api(`/documents/${documentId}/autocad/jobs/${job.id}`);
      }
      if(!same())return;if(job.status!=='ready')throw Error(job.message);
      const found=await api(`/documents/${documentId}/autocad/jobs/${job.id}/centermark-candidates`);
      if(!same())return;
      if(found.source_hash!==context.original_source_hash)throw Error('Nguồn đã đổi; đọc lại dấu tâm trước khi sửa.');
      if(!found.items.length){status.textContent='Chưa tìm được cặp dấu tâm có liên kết native được hỗ trợ trong phạm vi chọn.';return;}
      const select=document.createElement('select');select.id='nativeCenterPair';select.multiple=true;select.size=Math.min(found.items.length,6);select.style.maxWidth='100%';select.setAttribute?.('aria-label','Các cặp đường tròn và dấu tâm');
      for(const [index,pair] of found.items.entries()){
        const option=document.createElement('option');option.value=String(index);option.selected=index===0;option.textContent=`Đường tròn #${pair.circle_handle} · dấu tâm #${pair.mark_handle} · X ${pair.source_center[0].toFixed(3)}, Y ${pair.source_center[1].toFixed(3)}`;select.append(option);
      }select.value='0';centers.append(select);
      const inputs=[];
      for(const name of ['Dịch ngang X','Dịch dọc Y']){
        const label=document.createElement('label'),input=document.createElement('input');input.id=inputs.length?'nativeCenterY':'nativeCenterX';input.type='number';input.step='any';input.value='0';input.setAttribute?.('aria-label',name);label.style.display='block';label.style.margin='10px 0';label.textContent=name+' (đơn vị CAD nguồn): ';label.append(input);centers.append(label);inputs.push(input);
      }
      const note=document.createElement('p');note.textContent=`Chọn từ 1 đến 16 cặp; giữ Ctrl hoặc Shift để chọn nhiều. Các cặp được chọn dùng cùng độ dịch X/Y. Đơn vị bản vẽ: ${context.drawing_units||'chưa xác định'}. Hình có tỷ lệ cần quy đổi theo tọa độ CAD gốc. Các chi tiết xung quanh cần đối chiếu riêng.`;centers.append(note);
      const apply=document.createElement('button');apply.id='nativeCenterApply';apply.textContent='Dịch các cặp đã chọn và tạo DWG xem trước';centers.append(apply);
      apply.onclick=async()=>{
        if(!same()){status.textContent='Phạm vi đã đổi; đọc lại dấu tâm trước khi sửa.';return;}
        const values=inputs.map(input=>Number(input.value));
        if(inputs.some(input=>input.value.trim()==='')||values.some(value=>!Number.isFinite(value))||values.every(value=>Math.abs(value)<=1e-10)){status.textContent='Nhập độ dịch X/Y hữu hạn và khác 0.';return;}
        const selected=Array.from(select.selectedOptions||[{value:select.value}]).map(option=>found.items[Number(option.value)]);
        if(!selected.length||selected.length>16||selected.some(pair=>!pair)){status.textContent='Chọn từ 1 đến 16 cặp dấu tâm hợp lệ.';return;}
        const operations=selected.map(pair=>({action:'translate_centermark',handle:pair.circle_handle,mark_handle:pair.mark_handle,action_handle:pair.action_handle,owner_handle:pair.owner_handle,expected_type:'CIRCLE',before:JSON.stringify(pair.source_center),after:JSON.stringify([pair.source_center[0]+values[0],pair.source_center[1]+values[1],pair.source_center[2]])}));
        if(selected.some(pair=>!Number.isFinite(pair.source_center[0]+values[0])||!Number.isFinite(pair.source_center[1]+values[1]))){status.textContent='Độ dịch vượt giới hạn tọa độ.';return;}
        apply.disabled=true;
        try{
          await api(`/documents/${documentId}/autocad/native-edits`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({inspection_id:context.inspection_id,dependency_inspection_id:job.id,source_hash:found.source_hash,ids:[target.id],operations})});
          if(same())await load();
        }catch(error){if(same())status.textContent=error.message;}finally{apply.disabled=false;}
      };
      status.textContent=`Đã đọc ${found.items.length} cặp dấu tâm. Chọn đúng cặp và nhập độ dịch để tạo bản xem trước.`;
    }catch(error){if(same())status.textContent=error.message;}
    finally{readCenters.disabled=!settings?.configured||!doc||providerSelect.value!=='autocad';}
  };
  recover.onclick=async()=>{
    const documentId=doc;if(!documentId||providerSelect.value!=='autocad'||!settings?.configured)return;
    recover.disabled=true;
    try{
      await api(`/documents/${documentId}/autocad/recover`,{method:'POST'});
      if(doc===documentId&&providerSelect.value==='autocad')await load();
    }catch(error){if(doc===documentId)status.textContent=error.message;}
    finally{recover.disabled=!settings?.configured||!doc||providerSelect.value!=='autocad';}
  };
  cloudCopy.onclick=async()=>{
    const documentId=doc,route=providerSelect.value;if(!documentId||!settings?.configured)return;cloudCopy.disabled=true;
    try{
      const result=await api(`/documents/${documentId}/${route}/import`,{method:'POST'});
      if(doc!==documentId||providerSelect.value!==route)return;
      if(result.id!==doc)setDocument(result.id);
      await loadDocumentsList();await window.refreshApsJobs();
      // The existing upload reader resumes polling/discovery without replacing
      // frame detection or overwriting old document/revision identities.
      await window.loadApsImportedDocument();
    }catch(error){if(sameScope(documentId,route))status.textContent=error.message;}finally{cloudCopy.disabled=!settings?.configured||!doc;}
  };
  readParameters.onclick=async()=>{
    const documentId=doc,target=workItem||activeItem,route=providerSelect.value;
    if(!documentId||!target){status.textContent='Chọn bản vẽ hoặc block trước khi đọc tham số.';return;}
    readParameters.disabled=true;parameters.replaceChildren();const formVersion=++parameterGeneration;
    const sameForm=()=>sameScope(documentId,route)&&(workItem||activeItem)?.id===target.id&&formVersion===parameterGeneration;
    try{
      const context=await api(`/documents/${documentId}/${route}/context`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:[target.id],parameter_offset:0})});
      if(!sameForm())return;
      parameterDocument=documentId;const controls=[],seen=new Set();
      const fields=document.createElement('div');parameters.append(fields);
      function appendRecords(records){
      for(const record of records){
        if(seen.has(record.ref))continue;seen.add(record.ref);
        if(record.type!=='INSERT'||record.nested_editable===false)continue;
        for(const property of record.parameters||[]){
          const isString=property.value_type==='String',before=isString?property.value:Number(property.value),allowed=property.allowed||[];
          if(property.read_only||!['Double','Int16','Int32','String',undefined].includes(property.value_type)||property.value==null||(!isString&&!Number.isFinite(before))||(isString&&!allowed.length))continue;
          const label=document.createElement('label'),input=document.createElement(allowed.length?'select':'input');
          let initial=String(before);
          if(allowed.length){
            const matching=allowed.find(value=>isString?String(value)===before:Math.abs(Number(value)-before)<1e-8);
            const choices=matching===undefined?[before,...allowed]:allowed;initial=String(matching===undefined?before:matching);
            for(const value of choices){const option=document.createElement('option');option.value=String(value);option.textContent=String(value);input.append(option)}
          }else{input.type='number';input.step=property.value_type==='Double'?'any':'1';}input.value=initial;
          label.style.display='block';label.style.margin='10px 0';label.append(document.createTextNode(`#${record.ref} · ${property.name} (${property.units}): `),input);fields.append(label);
          controls.push({record,property,input,before,isString});
        }
      }
      const blocked=records.filter(record=>record.type==='INSERT'&&record.nested_editable===false&&record.parameters?.length);
      if(blocked.length){const warning=document.createElement('p');warning.textContent=`Có ${blocked.length} block con chưa thể cô lập nhánh cha an toàn: ${blocked.map(record=>'#'+record.ref).join(', ')}. Các tham số này chưa được đưa vào lệnh sửa.`;fields.append(warning);}
      }
      appendRecords(context.records);
      const note=document.createElement('p');parameters.append(note);
      const more=document.createElement('button');more.textContent='Đọc thêm block có tham số';more.className='secondary';parameters.append(more);
      const apply=document.createElement('button');apply.textContent='Áp dụng tham số và tạo DWG xem trước';parameters.append(apply);
      let next=context.next_parameter_offset,invalid=false;
      function updateForm(){
        more.hidden=next==null;
        apply.disabled=!controls.length;
        note.textContent=`Đã đọc ${seen.size}${context.parameter_record_count!=null?'/'+context.parameter_record_count:''} block có tham số. ${controls.length?'Giá trị là tham số cục bộ của block; block có tỷ lệ có thể cho số đo thành phẩm khác. AutoCAD cập nhật quan hệ nguồn và mở lại DWG để đối chiếu. BOM/lắp ghép ngoài block cần kiểm tra riêng.':'Chưa có tham số có thể sửa ở phần đã đọc.'}`;
      }
      updateForm();
      more.onclick=async()=>{
        if(!sameForm()||next==null)return;
        const offset=next;more.disabled=apply.disabled=true;
        try{
          const page=await api(`/documents/${documentId}/${route}/context`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:[target.id],parameter_offset:offset})});
          if(!sameForm())return;
          if(page.inspection_id!==context.inspection_id||page.original_source_hash!==context.original_source_hash||JSON.stringify(page.scope_ids)!==JSON.stringify(context.scope_ids)){invalid=true;throw Error('Nguồn/phạm vi CAD đã đổi; đọc lại tham số trước khi sửa.');}
          appendRecords(page.records);next=page.next_parameter_offset;updateForm();
        }catch(error){if(sameForm())status.textContent=error.message;}
        finally{more.disabled=invalid;apply.disabled=invalid||!sameForm()||!controls.length;}
      };
        apply.onclick=async()=>{
          if(!sameForm()){status.textContent='Phạm vi/bộ xử lý đã đổi; đọc lại tham số.';return;}
          if(invalid){status.textContent='Nguồn CAD đã đổi; đọc lại tham số trước khi sửa.';return;}
          if(controls.some(c=>c.input.value.trim()===''||(!c.isString&&!Number.isFinite(Number(c.input.value))))){status.textContent='Nhập giá trị tham số hợp lệ.';return;}
          const changed=controls.filter(c=>c.isString?c.input.value!==c.before:Math.abs(Number(c.input.value)-c.before)>=1e-8);
          if(!changed.length){status.textContent='Chưa thay đổi tham số.';return;}
          if(changed.length>200){status.textContent='Mỗi lần sửa tối đa 200 tham số; chia thành phạm vi nhỏ hơn.';return;}
          apply.disabled=true;
          try{
            const operations=changed.map(c=>({action:'set_dynamic_property',handle:c.record.handle,owner_handle:c.record.owner_handle,expected_type:c.record.type,before:c.before,after:c.isString?c.input.value:Number(c.input.value),property:c.property.name,instance_path:c.record.ref.includes('/')?c.record.ref.split('/'):[]}));
            await api(`/documents/${documentId}/${route}/native-edits`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({inspection_id:context.inspection_id,source_hash:context.original_source_hash,ids:context.scope_ids,operations})});
            if(sameScope(documentId,route))await load();
          }catch(error){if(sameScope(documentId,route))status.textContent=error.message;}finally{apply.disabled=false;}
        };
    }catch(error){if(sameForm())status.textContent=error.message;}finally{readParameters.disabled=!settings?.configured||!doc;}
  };
  window.displayNativeChangePlan=result=>{
    const documentId=doc,route=result.provider,host=document.getElementById('changeResult');host.replaceChildren();
    const title=document.createElement('h4');title.textContent='Thay đổi tham số CAD';host.append(title);
    const list=document.createElement('ul');for(const operation of result.native_edit.operations){const li=document.createElement('li');li.textContent=`Block #${operation.instance_path?.length?operation.instance_path.join('/'):operation.handle} · ${operation.property}: ${operation.before} → ${operation.after}`;list.append(li)}host.append(list);
    for(const text of result.plan.questions){const p=document.createElement('p');p.textContent=text;host.append(p)}
    const note=document.createElement('p');note.textContent=(route==='aps'?'APS gửi CAD đến Autodesk để chạy AutoCAD. ':'AutoCAD chạy trên máy. ')+'Thực thi quan hệ có sẵn trong block, lưu và mở lại DWG để kiểm tra. Phần BOM/lắp ghép bên ngoài block cần kiểm tra riêng.';host.append(note);
    document.getElementById('changeStatus').textContent=result.native_execution_available?'Đã xác định tham số và giá trị nguồn. Có thể tạo DWG xem trước.':'Chưa sửa: cần xác định tham số theo hướng dẫn bên dưới.';
    if(!result.native_execution_available)return;
    const create=document.createElement('button');create.dataset.cadAction='create-dwg';create.textContent='Tạo DWG sau sửa tham số';host.append(create);
    create.onclick=async()=>{
      if(doc!==documentId||!(workItem||activeItem)||!result.native_edit.ids.includes((workItem||activeItem).id)){document.getElementById('changeStatus').textContent='Phạm vi đã đổi; phân tích lại yêu cầu.';return}
      create.disabled=true;
      try{
        const job=await api(`/documents/${documentId}/${route}/native-edits`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(result.native_edit)});
        if(doc!==documentId)return;
        document.getElementById('changeStatus').textContent=`Đang tạo bản sửa #${job.id.slice(0,8)}. Hình sau sửa và liên kết tải DWG sẽ hiện trong mục AutoCAD bên dưới.`;
        providerSelect.value=route;panel.open=true;await load();
      }catch(error){if(doc===documentId)document.getElementById('changeStatus').textContent=error.message}finally{create.disabled=false}
    };
  };
  panel.addEventListener('toggle', () => { if (panel.open) void load(); });
  window.refreshApsJobs = load;
  window.beginLocalNativeImport=async()=>{
    chooseInitialProvider=false;providerSelect.value='autocad';await load();
    if(!settings?.configured)throw Error('AutoCAD chưa sẵn sàng. Kiểm tra cấu hình trong phần công cụ CAD.');
    await cloudCopy.onclick();
  };
  void load();
})();
