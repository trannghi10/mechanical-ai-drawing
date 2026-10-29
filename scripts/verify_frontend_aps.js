// Cloud submission controls, native parameter contract and stale scope protection.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{
  constructor(tag='div'){this.tagName=tag;this.children=[];this.style={};this.dataset={};this.textContent='';this.value='';}
  append(...children){this.children.push(...children);}
  insertBefore(child){this.children.push(child);}
  replaceChildren(...children){this.children=[...children];}
  addEventListener(){}
  querySelector(){return this.children[0];}
}
const nodes=new Map();for(const id of ['apsPanel','apsStatus','apsJobs','apsInspect','apsRefresh','upload','changeResult','changeStatus'])nodes.set(id,new Element());
nodes.get('upload').append(new Element('button'));
const context={console,doc:'document',workItem:{id:'AA'},activeItem:null,generation:0,
  document:{getElementById:id=>nodes.get(id),createElement:tag=>new Element(tag),createTextNode:text=>text},
  setTimeout:()=>1,clearTimeout(){},URL,loadDocumentsList:async()=>{},setDocument(id){context.doc=id;},
  loadApsImportedDocument:async()=>{},setZoom(){},revealViewer(){}};
context.window=context;
let posted=[],listedJobs=[],extraProperties=[];
context.api=async(url,options={})=>{
  if(url==='/aps/status')return {configured:true,backend:'aps',read_backend:'aps',message:'configured',cloud_disclosure:'sent to Autodesk'};
  if(url==='/autocad/status')return {configured:true,backend:'autocad',read_backend:'autocad',message:'local configured',cloud_disclosure:'runs on this computer'};
  if((url.endsWith('/aps/jobs')||url.endsWith('/autocad/jobs'))&&!options.method)return {items:listedJobs};
  if(url.endsWith('/aps/context')||url.endsWith('/autocad/context'))return {inspection_id:'inspection',original_source_hash:'source',scope_ids:['AA'],records:[{
    ref:'AB',handle:'AB',owner_handle:'1F',type:'INSERT',parameters:[{name:'Length',value:'20',value_type:'Double',units:'Distance',read_only:false},...extraProperties]}]};
  if(options.method==='POST'){posted.push({url,body:options.body&&JSON.parse(options.body)});return {id:'native',status:'processing'};}
  return {status:'processing'};
};
vm.createContext(context);vm.runInContext(fs.readFileSync('frontend/aps.js','utf8'),context);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const descendants=(node,tag)=>node.children.flatMap(child=>typeof child==='object'?[...(child.tagName===tag?[child]:[]),...descendants(child,tag)]:[]);
(async()=>{
  await flush();
  assert.equal(nodes.get('upload').children[0].textContent,'Tải file lên APS');
  const routing=nodes.get('apsPanel').children.find(n=>n.id==='nativeRouting');
  assert.ok(routing.textContent.includes('chỉ áp dụng cho các công cụ'));
  const connection=descendants(nodes.get('apsPanel'),'button').find(n=>n.textContent==='Kiểm tra kết nối APS');
  assert.equal(connection.hidden,false);await connection.onclick();
  assert.equal(posted[0].url,'/aps/connection');assert.equal(posted[0].body,undefined);posted=[];
  const read=nodes.get('apsPanel').children.find(n=>n.textContent==='Đọc tham số bản vẽ đang chọn');
  await read.onclick();
  const input=descendants(nodes.get('apsPanel'),'input')[0];assert.equal(input.value,'20');input.value='30';
  const apply=descendants(nodes.get('apsPanel'),'button').find(n=>n.textContent==='Áp dụng tham số và tạo DWG xem trước');
  await apply.onclick();
  assert.equal(posted.length,1);const request=posted[0];assert.ok(request.url.endsWith('/aps/native-edits'));
  assert.equal(request.body.operations[0].action,'set_dynamic_property');
  assert.equal(request.body.operations[0].before,20);assert.equal(request.body.operations[0].after,30);
  assert.deepEqual(request.body.ids,['AA']);assert.equal(request.body.source_hash,'source');
  context.workItem={id:'OTHER'};await apply.onclick();assert.equal(posted.length,1);
  context.doc='another-document';await apply.onclick();assert.equal(posted.length,1);
  listedJobs=[{id:'ready-job',mode:'edit',status:'ready',message:'ready',download_url:'/checked/file.dwg',target_ids:['AA']}];
  await context.refreshApsJobs();
  const links=descendants(nodes.get('apsJobs'),'a');assert.equal(links[0].href,'/checked/file.dwg');
  assert.ok(descendants(nodes.get('apsJobs'),'button').some(n=>n.textContent==='Xem hình sau sửa'));
  const provider=nodes.get('apsPanel').children.find(n=>n.id==='nativeProvider');provider.value='autocad';provider.onchange();await flush();
  assert.equal(nodes.get('apsInspect').textContent,'Đọc CAD bằng AutoCAD trên máy');
  context.workItem={id:'AA'};listedJobs=[];
  await apply.onclick();assert.equal(posted.length,1,'Old cloud controls cannot submit to the local provider');
  await read.onclick();
  const localInput=descendants(nodes.get('apsPanel'),'input')[0];localInput.value='35';
  const localApply=descendants(nodes.get('apsPanel'),'button').find(n=>n.textContent==='Áp dụng tham số và tạo DWG xem trước');
  await localApply.onclick();assert.equal(posted.length,2);assert.ok(posted[1].url.endsWith('/autocad/native-edits'));
  assert.equal(posted[1].body.operations[0].after,35);
  extraProperties=[{name:'Part Number',value:'626',value_type:'String',allowed:['626','627']},{name:'Side',value:'0',value_type:'Int16',allowed:['0','1']},
    {name:'Ball Size',value:'3.1749999999999994',value_type:'Double',allowed:['3.175','3.9688']}];
  await read.onclick();
  const selectors=descendants(nodes.get('apsPanel'),'select');
  const choice=selectors.find(n=>n.children.some(c=>c.value==='627'));choice.value='627';
  const flip=selectors.find(n=>n.children.some(c=>c.value==='1'));flip.value='1';
  const typedApply=descendants(nodes.get('apsPanel'),'button').find(n=>n.textContent==='Áp dụng tham số và tạo DWG xem trước');
  await typedApply.onclick();
  assert.equal(posted[2].body.operations[0].before,'626');assert.equal(posted[2].body.operations[0].after,'627');
  assert.equal(posted[2].body.operations[1].after,1);
  assert.equal(posted[2].body.operations.length,2,'Rounding at the native allowed value must not create a spurious edit');
  const nativePlan={provider:'autocad',native_execution_available:true,plan:{questions:[]},native_edit:posted[2].body};
  context.displayNativeChangePlan(nativePlan);
  const create=descendants(nodes.get('changeResult'),'button')[0];await create.onclick();
  assert.ok(posted[3].url.endsWith('/autocad/native-edits'));
  context.workItem={id:'OTHER'};await create.onclick();assert.equal(posted.length,4);context.workItem={id:'AA'};
  const recover=descendants(nodes.get('apsPanel'),'button').find(n=>n.textContent==='Tạo bản DWG phục hồi');
  assert.equal(recover.hidden,false);await recover.onclick();
  assert.ok(posted[4].url.endsWith('/autocad/recover'));
  assert.equal(connection.hidden,true,'Cloud connection action is hidden for local AutoCAD');
  // A late response from APS must not replace local settings or enable cloud
  // actions after the user has selected the local provider.
  const raceApi=context.api;let releaseStatus,releaseRead;
  provider.value='aps';provider.onchange();await flush();
  context.api=(url,options)=>url.endsWith('/aps/context')?new Promise((_,reject)=>{releaseRead=reject;}):raceApi(url,options);
  const waitingRead=read.onclick();
  provider.value='autocad';provider.onchange();await flush();
  const localStatus=nodes.get('apsStatus').textContent;
  releaseRead(Error('stale cloud error'));await waitingRead;
  assert.equal(nodes.get('apsStatus').textContent,localStatus);
  context.api=(url,options)=>url==='/aps/status'?new Promise(resolve=>{releaseStatus=resolve;}):raceApi(url,options);
  provider.value='aps';provider.onchange();await flush();
  provider.value='autocad';provider.onchange();await flush();
  releaseStatus({configured:false,backend:'aps',read_backend:'aps',message:'old APS unavailable'});await flush();
  assert.equal(nodes.get('apsInspect').disabled,false,'Late cloud status must not clear local readiness');
  assert.equal(nodes.get('apsStatus').textContent,localStatus);
  const beforeInspect=posted.length;await nodes.get('apsInspect').onclick();
  assert.equal(posted.length,beforeInspect+1);assert.ok(posted.at(-1).url.endsWith('/autocad/jobs'));
  context.api=raceApi;
  // Nested native controls submit an occurrence path, never just the shared
  // definition handle (which can be reused under another parent instance).
  context.api=async(url,options)=>url.endsWith('/autocad/context')?{inspection_id:'nested-inspection',original_source_hash:'nested-hash',scope_ids:['AA'],records:[{
    ref:'AA/CC/AB',handle:'AB',owner_handle:'1F',type:'INSERT',nested_editable:true,
    parameters:[{name:'Length',value:'20',value_type:'Double',units:'Distance',read_only:false}]}]}:raceApi(url,options);
  await read.onclick();
  descendants(nodes.get('apsPanel'),'input')[0].value='40';
  await descendants(nodes.get('apsPanel'),'button').find(n=>n.textContent==='Áp dụng tham số và tạo DWG xem trước').onclick();
  assert.deepEqual(posted.at(-1).body.operations[0].instance_path,['AA','CC','AB']);
  context.api=raceApi;
  // Reading a later parameter page must preserve edited values from earlier
  // pages and bind the whole submission to one inspection/source hash.
  let changedPageHash=false;
  const parameterRecord=(ref)=>({ref,handle:ref.split('/').at(-1),owner_handle:'1F',type:'INSERT',nested_editable:true,
    parameters:[{name:'Length',value:'20',value_type:'Double',units:'Distance',read_only:false}]});
  context.api=async(url,options)=>{
    if(url.endsWith('/autocad/context')){
      const offset=JSON.parse(options.body).parameter_offset||0;
      return {inspection_id:'paged',original_source_hash:offset&&changedPageHash?'changed':'paged-hash',scope_ids:['AA'],
        parameter_record_count:2,next_parameter_offset:offset?null:25,records:[parameterRecord(offset?'AA/DD':'AA/CC')]};
    }
    return raceApi(url,options);
  };
  await read.onclick();descendants(nodes.get('apsPanel'),'input')[0].value='40';
  const more=descendants(nodes.get('apsPanel'),'button').find(n=>n.textContent==='Đọc thêm block có tham số');
  await more.onclick();
  const pagedInputs=descendants(nodes.get('apsPanel'),'input');assert.equal(pagedInputs.length,2);assert.equal(pagedInputs[0].value,'40');pagedInputs[1].value='60';
  await descendants(nodes.get('apsPanel'),'button').find(n=>n.textContent==='Áp dụng tham số và tạo DWG xem trước').onclick();
  assert.deepEqual(posted.at(-1).body.operations.map(op=>op.after),[40,60]);
  assert.deepEqual(posted.at(-1).body.operations.map(op=>op.instance_path),[['AA','CC'],['AA','DD']]);
  await read.onclick();changedPageHash=true;
  descendants(nodes.get('apsPanel'),'input')[0].value='45';
  await descendants(nodes.get('apsPanel'),'button').find(n=>n.textContent==='Đọc thêm block có tham số').onclick();
  const invalidApply=descendants(nodes.get('apsPanel'),'button').find(n=>n.textContent==='Áp dụng tham số và tạo DWG xem trước');
  const previousPosted=posted.length;assert.equal(invalidApply.disabled,true);await invalidApply.onclick();assert.equal(posted.length,previousPosted);
  context.api=raceApi;
  // CenterMark edits bind selection, original inspection and scoped dependencies.
  let mismatchedCenterHash=false;
  context.api=async(url,options)=>{
    if(url.endsWith('/centermark-inspections'))return {id:'center-inspection',status:'ready'};
    if(url.endsWith('/centermark-candidates'))return {source_hash:mismatchedCenterHash?'changed':'source',items:[{circle_handle:'12',mark_handle:'13',action_handle:'14',owner_handle:'1F',source_center:[1,2,0]},{circle_handle:'22',mark_handle:'23',action_handle:'24',owner_handle:'1F',source_center:[10,20,0]}]};
    return raceApi(url,options);
  };
  const centerRead=descendants(nodes.get('apsPanel'),'button').find(n=>n.id==='nativeReadCenters');
  assert.equal(centerRead.hidden,false);await centerRead.onclick();
  const centerBox=nodes.get('apsPanel').children.find(n=>n.id==='nativeCenters');
  const centerInputs=descendants(centerBox,'input');const centerApply=descendants(centerBox,'button')[0];
  let beforeCenter=posted.length;await centerApply.onclick();assert.equal(posted.length,beforeCenter,'Zero translation cannot submit');
  centerInputs[0].value='3';centerInputs[1].value='-2';await centerApply.onclick();
  const centerRequest=posted.at(-1).body;
  assert.equal(centerRequest.inspection_id,'inspection');assert.equal(centerRequest.dependency_inspection_id,'center-inspection');
  assert.equal(centerRequest.operations[0].action,'translate_centermark');
  assert.deepEqual(JSON.parse(centerRequest.operations[0].before),[1,2,0]);
  assert.deepEqual(JSON.parse(centerRequest.operations[0].after),[4,0,0]);
  assert.equal(centerRequest.operations[0].mark_handle,'13');assert.deepEqual(centerRequest.ids,['AA']);
  const centerSelect=descendants(centerBox,'select')[0];assert.equal(centerSelect.multiple,true);
  centerSelect.selectedOptions=[{value:'0'},{value:'1'}];await centerApply.onclick();
  assert.equal(posted.at(-1).body.operations.length,2);
  assert.deepEqual(JSON.parse(posted.at(-1).body.operations[1].after),[13,18,0]);
  beforeCenter=posted.length;centerSelect.selectedOptions=[];await centerApply.onclick();assert.equal(posted.length,beforeCenter,'Empty batch cannot submit');
  centerSelect.selectedOptions=Array.from({length:17},()=>({value:'0'}));await centerApply.onclick();assert.equal(posted.length,beforeCenter,'Oversized batch cannot submit');
  centerSelect.selectedOptions=[{value:'0'}];
  beforeCenter=posted.length;context.workItem={id:'OTHER'};await centerApply.onclick();assert.equal(posted.length,beforeCenter);context.workItem={id:'AA'};
  mismatchedCenterHash=true;await centerRead.onclick();assert.equal(descendants(centerBox,'button').length,0,'Changed source cannot create a center edit form');
  let releaseCenters;
  const centerApi=context.api;
  context.api=(url,options)=>url.endsWith('/centermark-candidates')?new Promise(resolve=>{releaseCenters=resolve;}):centerApi(url,options);
  const pendingCenters=centerRead.onclick();await flush();
  provider.value='aps';provider.onchange();await flush();
  releaseCenters({source_hash:'source',items:[{circle_handle:'12',mark_handle:'13',action_handle:'14',owner_handle:'1F',source_center:[1,2,0]}]});await pendingCenters;
  assert.equal(descendants(centerBox,'button').length,0,'Late CenterMark results cannot restore controls after provider changes');
  assert.equal(centerRead.hidden,true);
  context.api=raceApi;provider.value='autocad';provider.onchange();await flush();
  context.api=raceApi;
  // A server activated for local AutoCAD must not start by requesting APS keys.
  const originalApi=context.api;
  context.api=async(url,options)=>url==='/aps/status'?{configured:false,backend:'autocad',read_backend:'autocad'}:originalApi(url,options);
  nodes.get('apsPanel').replaceChildren();
  vm.runInContext(fs.readFileSync('frontend/aps.js','utf8'),context);await flush();
  assert.equal(nodes.get('apsPanel').children.find(n=>n.id==='nativeProvider').value,'autocad');
  assert.equal(nodes.get('apsInspect').textContent,'Đọc CAD bằng AutoCAD trên máy');
  console.log('APS/local routing, cloud disclosure, native parameter preconditions, stale scope and ready DWG links: passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
