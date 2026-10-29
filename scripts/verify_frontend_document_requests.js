const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Node {
 constructor(){this.children=[];this.value='';this.textContent='';this.checked=false;this.disabled=false;this.classList={remove(){}};}
 append(...children){this.children.push(...children)} replaceChildren(...children){this.children=children} setAttribute(){}
}
const nodes=new Map(),el=id=>{if(!nodes.has(id))nodes.set(id,new Node());return nodes.get(id)},events={},calls=[];
const context={doc:'DOC',workItem:null,clearPartSelection(){},analyzing:false,creatingRevision:false,window:{addEventListener:(n,f)=>events[n]=f},
 document:{getElementById:el,createElement:()=>new Node()},submitDrawingRequest:async(...args)=>calls.push(args)};
vm.createContext(context);vm.runInContext(fs.readFileSync('frontend/document-request.js','utf8'),context);
const job={status:'needs_target',request:'Chi tiết số 7 dài 100 thành 120',target_resolution:{atlas_id:'ATLAS',source_hash:'HASH',message:'Chọn mã nguồn',candidate_count:2,
 candidates:[{part_code:'A',part_numbers:['7'],descriptions:['<script>alert(1)</script>'],frame_ids:['S1']},{part_code:'B',part_numbers:['7'],descriptions:['Shaft'],frame_ids:['S2']}]}};
(async()=>{
 context.window.renderDocumentTargets(job,'DOC');let host=el('documentTargetChoices');
 assert.equal(host.children[2].children.length,2);
 let filter=host.children[1];filter.value='Shaft';filter.oninput();assert.equal(host.children[2].children.length,1);
 let button=host.children[2].children[0].children[1];context.analyzing=true;await button.onclick();assert.equal(calls.length,0);
 context.analyzing=false;await button.onclick();assert.equal(calls.length,1);assert.equal(calls[0][0].part_code,'B');assert.equal(calls[0][0].source_hash,'HASH');assert.equal(calls[0][1],job.request);assert(el('wholeDocumentRequest').checked);
 context.doc='OTHER';await button.onclick();assert.equal(calls.length,1);events['cad-document-changed']();assert.equal(host.children.length,0);
 context.doc='DOC';context.window.renderDocumentTargets({...job,status:'blocked'},'DOC');assert.equal(host.children.length,1);
 context.window.renderDocumentTargets(job,'DOC');el('changeRequest').oninput();assert.equal(host.children.length,0);
 assert(!fs.readFileSync('frontend/document-request.js','utf8').includes('innerHTML'));
 el('wholeDocumentRequest').checked=true;el('wholeDocumentRequest').onchange();assert(el('editTarget').textContent.includes('toàn file'));
 el('wholeDocumentRequest').checked=false;el('wholeDocumentRequest').onchange();assert(el('editTarget').textContent.includes('Chọn một khung'));
 const html=fs.readFileSync('frontend/index.html','utf8');new vm.Script(html.split('<script>')[1].split('</script>')[0]);
 console.log('Whole-file source choices, repeated STT, source hash binding, filter, busy/stale guards and CAD text escaping: passed');
})().catch(e=>{console.error(e);process.exitCode=1});
