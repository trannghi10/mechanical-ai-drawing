const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('frontend/index.html','utf8');
const source=html.slice(html.indexOf('let activePlanning=null;'),html.indexOf('function revisionPreviewUrl'));
const elements=new Map(),saved=new Map(),calls=[],plans=[];
const context={doc:'DOC',items:[{id:'S'}],creatingRevision:false,analyzing:false,workItem:{id:'S'},activeItem:null,
 $:id=>{if(!elements.has(id))elements.set(id,{hidden:false,disabled:false,value:'resize',textContent:'',replaceChildren(){}});return elements.get(id)},
 localStorage:{setItem:(k,v)=>saved.set(k,v),getItem:k=>saved.get(k),removeItem:k=>saved.delete(k)},
 setTimeout:fn=>{fn()},checkAI(){},async show(){},focusItem(){},selectedPart:{part_code:'OLD'},clearPartSelection(){context.selectedPart=null},
 displayPlan:(plan,ids,auto)=>plans.push({plan,ids,auto}),
 async api(url,options){calls.push({url,method:options?.method||'GET'});
  if(url.includes('/change-plans/'))return {id:'PLAN',root_target_ids:['S']};
  return {id:'JOB',status:'ready',plan_id:'PLAN',target_ids:['S'],request:'resize',message:'Ready',elapsed_seconds:1};}
};
vm.createContext(context);vm.runInContext(source,context);
(async()=>{
 await context.watchPlanning('DOC',{id:'JOB',status:'running',target_ids:['S'],message:'CAD',elapsed_seconds:0});
 assert.equal(plans.length,1);assert.deepEqual(Array.from(plans[0].ids),['S']);assert.equal(saved.size,0);
 assert.equal(elements.get('cancelAnalysis').hidden,true);assert.equal(context.analyzing,false);
 assert(calls.some(c=>c.url.includes('/planning-jobs/')));
 saved.set('cad-planning:DOC','JOB');await context.restorePlanning();
 for(let i=0;i<5;i++)await Promise.resolve();
 assert.equal(plans.length,2);assert.equal(saved.size,0);
 assert.equal(context.selectedPart,null);
 await context.watchPlanning('DOC',{id:'CANCEL',status:'cancelled',target_ids:['S'],message:'Cancelled'});
 assert.equal(plans.length,2);assert.equal(elements.get('changeStatus').textContent,'Cancelled');
 assert(!source.includes('readProcessVision('));
 console.log('Planning progress, saved-job reload, cancellation state, source selection and explicit vision follow-up: passed');
})().catch(error=>{console.error(error);process.exitCode=1});
