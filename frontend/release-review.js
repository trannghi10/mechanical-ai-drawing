'use strict';
(()=>{
  const $=id=>document.getElementById(id),params=new URLSearchParams(location.search);
  const documentId=params.get('document'),revisionId=params.get('revision');let generation=0;
  const valid=value=>/^[0-9a-f]{32}$/.test(value||'');
  function renderGate(gate){
    const host=$('gate');host.replaceChildren();if(!gate)return;
    const section=document.createElement('section');section.className='gate-summary';section.dataset.mode=gate.mode;
    const heading=document.createElement('h3');heading.textContent='DWG Edit Confidence & Safety Gate · '+gate.mode;
    const detail=document.createElement('p');
    detail.textContent=gate.mode==='AUTO'?'Đủ điều kiện tự phát hành theo chứng nhận hiện tại.':gate.mode==='REVIEW'?'Có thể xem xét theo bằng chứng hiện tại; chưa tự phát hành.':'Chặn sửa/phát hành cho đến khi khắc phục bằng chứng không đạt.';
    section.append(heading,detail);
    for(const check of gate.checks||[]){
      const line=document.createElement('p');line.textContent=(check.status==='passed'?'Đạt: ':check.status==='review'?'Cần xem xét: ':'Chặn: ')+check.detail;section.append(line);
    }
    host.append(section);
  }
  async function load(){
    const epoch=++generation;$('checks').replaceChildren();$('gate').replaceChildren();
    if(!valid(documentId)||!valid(revisionId)){$('status').textContent='Chọn một bản sửa đã lưu để kiểm tra điều kiện phát hành.';$('refresh').disabled=true;return;}
    $('title').textContent='Bản sửa #'+revisionId.slice(0,8);
    $('back').href='/?doc='+documentId+'&revision='+revisionId;
    $('refresh').disabled=true;$('status').textContent='Đang đối chiếu nguồn, hình học, phạm vi và bằng chứng lưu/mở lại DWG…';
    try{
      const response=await fetch(`/documents/${documentId}/revisions/${revisionId}/release-review`,{cache:'no-store'});
      const result=await response.json();if(epoch!==generation)return;
      if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'Chưa kiểm được điều kiện phát hành.');
      // Fail closed in the UI as well: this page has no publish operation.
      $('status').textContent=`${result.passed_count}/${result.checks.length} điều kiện đạt. Chưa bật tự phát hành.`;
      renderGate(result.edit_gate);
      for(const check of result.checks){
        const section=document.createElement('section');section.className='release-check';section.dataset.status=check.status;
        const heading=document.createElement('h3');heading.textContent=(check.status==='passed'?'Đạt · ':'Cần hoàn thiện · ')+check.label;
        const detail=document.createElement('p');detail.textContent=check.detail;section.append(heading,detail);$('checks').append(section);
      }
    }catch(error){if(epoch===generation)$('status').textContent=error.message;}
    finally{if(epoch===generation)$('refresh').disabled=false;}
  }
  $('refresh').onclick=load;load();
})();
