const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('frontend/index.html','utf8').split('<script>')[1].split('</script>')[0];
new vm.Script(source);
const links=[],status={},inlineStatus={};let queue=[],posts=[],downloadClicks=0,navigations=[];
const panel={isConnected:true,querySelector(selector){return selector==='.export-status'?inlineStatus:selector.startsWith('[data-download=')?links.find(link=>link.dataset.download===selector.slice(15,-1)):null},append(link){links.push(link)}};
const context={doc:'document',window:{location:{assign:url=>navigations.push(url)}},document:{createElement(){return {dataset:{},style:{},click(){downloadClicks++},remove(){const i=links.indexOf(this);if(i>=0)links.splice(i,1)}}}},
 $:()=>status,setTimeout:callback=>callback(),api:async(url,options)=>{posts.push({url,options});return queue.shift()}};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('function exportDownloadLink('),source.indexOf('function displayRevision(')),context);
(async()=>{
 const ready={id:'job',status:'ready',preview:true,format:'dwg',download_url:'/saved/download'};
 queue=[{...ready,status:'queued'},{...ready,status:'running'},ready];
 await context.exportRevisionFile({id:'revision'},panel,'dwg','selection',true);
 assert.equal(links[0].href,'/saved/download');assert.equal(links[0].dataset.download,'preview');
 assert.equal(JSON.parse(posts[0].options.body).scope,'selection');
 assert.equal(posts.length,3);assert(status.textContent.includes('chưa duyệt'));
 assert.deepEqual(navigations,['/saved/download']);assert.equal(downloadClicks,0); // direct navigation avoids browsers blocking an async synthetic click
 links.length=0;queue=[{items:[ready]}];
 await context.restoreRevisionDownloads({id:'revision'},panel);
 assert.equal(links[0].href,'/saved/download'); // recovered after a page reload
 assert(inlineStatus.textContent.includes('sẵn sàng'));
 assert.equal(navigations.length,1)&&assert.equal(downloadClicks,0); // reload restores links without an unsolicited download
 queue=[{status:'failed',message:'ODA failed'}];
 await assert.rejects(context.exportRevisionFile({id:'revision'},panel,'dwg','selection',true),/ODA failed/);
 links.length=0;context.doc='other';
 await context.waitExportJob('document','revision',panel,ready);assert.equal(links.length,0);
 console.log('Export queue, durable GET download, reload recovery, conversion errors and document isolation: passed');
})().catch(e=>{console.error(e);process.exitCode=1});

// Visible shortcuts must retain document/scope and reflect real export controls.
async function verifyWorkspaceShortcuts(){
 const nodes=new Map(),observers=[];let control=null,clicks=0,opened=[],release,dbReply;
 function element(){return {children:[],dataset:{},disabled:false,textContent:'',value:'',open:false,
  classList:{toggle(){},contains(){return true},add(){},remove(){}},addEventListener(){},scrollIntoView(){},focus(){},
  append(...values){this.children.push(...values)},replaceChildren(){this.children=[]},closest(){return this},
  click(){return this.onclick?.()},querySelector(){return control}}}
 const node=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
 const db={backend:'postgresql',ready:true,details_allowed:true,documents:92,revisions:111,message:'Connected',connection_info:{host:'127.0.0.1',port:5432,database:'project',username:'app'}};
 const scope={doc:'document',workItem:{id:'ROOT'},activeItem:null,analyzing:false,creatingRevision:false,
  revisionItems:[{id:'wrong',document_id:'other',target_ids:['ROOT']},{id:'unrelated',document_id:'document',target_ids:['FOREIGN']},{id:'right',document_id:'document',root_target_ids:['ROOT'],target_ids:['ROOT']}],
  cadCapabilities:{dwg_export:true},cadCapabilitiesReady:Promise.resolve({dwg_export:true}),focusItem(){},
  window:{addEventListener(){},documentReadingStatus:null},MutationObserver:class{constructor(fn){observers.push(fn)}observe(){}},
  document:{getElementById:node,querySelectorAll(){return []},createElement:element},
  api:async url=>url.startsWith('/database/')?(dbReply?await dbReply():db):{configured:true,read_backend:'autocad'}};
 node('revisionHistory').onchange=async()=>{opened.push(node('revisionHistory').value);if(release)await new Promise(r=>release=r);control={dataset:{cadAction:'export-dwg'},disabled:false,click(){clicks++}}};
 vm.createContext(scope);vm.runInContext(fs.readFileSync('frontend/workspace-ui.js','utf8'),scope);
 await new Promise(r=>setImmediate(r));const refresh=()=>observers[0]();
 assert.equal(node('databaseBadge').textContent,'PostgreSQL · đã kết nối');assert(node('databaseCounts').textContent.includes('111'));
 assert.equal(node('databaseConnection').children.length,8);node('databaseBadge').onclick({preventDefault(){}});assert(node('databasePanel').open);
 const modes=[];node('workspace').classList.add=mode=>modes.push(mode);
 scope.workItem=null;node('wholeDocumentRequest').checked=true;node('stepRequest').onclick();assert(modes.includes('request-mode'));
 assert(node('editTarget').textContent.includes('toàn file'));scope.workItem={id:'ROOT'};
 assert(!node('quickDwgCreate').disabled);assert(node('quickDwgCreate').textContent.includes('Tải DWG'));
 await node('quickDwgCreate').onclick();assert.deepEqual(opened,['right']);assert.equal(clicks,1);
 scope.workItem={id:'UNKNOWN'};control=null;refresh();assert(node('quickDwgCreate').disabled&&node('quickOpenRevision').disabled);
 scope.workItem={id:'ROOT'};control={dataset:{cadAction:'create-dwg'},disabled:false,click(){clicks++}};refresh();
 assert(node('quickDwgCreate').textContent.includes('Tạo và tải'));await node('quickDwgCreate').onclick();assert.equal(clicks,2);
 scope.analyzing=true;refresh();assert(node('quickDwgCreate').disabled);scope.analyzing=false;
 control.disabled=true;refresh();assert(node('quickDwgCreate').disabled);
 control=null;release=true;refresh();const pending=node('quickDwgCreate').onclick();await new Promise(r=>setImmediate(r));
 scope.doc='new-document';release();await pending;assert.equal(clicks,2);refresh();assert(node('quickOpenRevision').disabled);
 let oldResolve;dbReply=()=>new Promise(r=>oldResolve=r);const old=node('refreshDatabase').onclick();await new Promise(r=>setImmediate(r));
 dbReply=async()=>({...db,ready:false,message:'Unavailable',connection_info:{}});await node('refreshDatabase').onclick();oldResolve(db);await old;
 assert.equal(node('databaseBadge').textContent,'PostgreSQL · chưa kết nối');assert.equal(node('databaseConnection').children.length,0);
 dbReply=async()=>({...db,details_allowed:false,connection_info:undefined});await node('refreshDatabase').onclick();
 assert.equal(node('databaseBadge').textContent,'PostgreSQL · đã kết nối');assert.equal(node('databaseConnection').children.length,0);
 console.log('Visible DWG actions, scoped saved revision, busy/stale protection and PostgreSQL status: passed');
}
verifyWorkspaceShortcuts().catch(e=>{console.error(e);process.exitCode=1});
