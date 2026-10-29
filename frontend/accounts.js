'use strict';
const $=id=>document.getElementById(id);
const roleLabels={viewer:'Chỉ xem',operator:'Nhân viên chỉnh sửa',engineer:'Kỹ sư phê duyệt',admin:'Quản trị viên'};
let accountState=null;
function message(text){$('message').textContent=text;}
async function api(path,options={}){
  const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})},cache:'no-store'});
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Không hoàn tất yêu cầu. Kiểm tra dữ liệu và thử lại.');
  return data;
}
function nextPage(){try{const value=new URLSearchParams(location.search).get('next')||'/';const target=new URL(value,location.origin);return target.origin===location.origin?target.pathname+target.search+target.hash:'/';}catch{return '/';}}
function formBusy(form,busy){form.querySelectorAll('button,input,select').forEach(node=>node.disabled=busy);}
async function submit(form,operation){formBusy(form,true);try{await operation();}catch(error){message(error.message);}finally{formBusy(form,false);}}
function td(row,text){const node=document.createElement('td');node.textContent=text;row.append(node);return node;}
function table(headers){const element=document.createElement('table');element.className='account-table';const head=document.createElement('tr');headers.forEach(label=>{const cell=document.createElement('th');cell.textContent=label;head.append(cell);});element.append(head);return element;}
async function loadUsers(){
  const data=await api('/auth/users'),view=table(['Thành viên','Vai trò','Hoạt động','Đặt lại mật khẩu','']);
  for(const user of data.items){
    const row=document.createElement('tr');td(row,user.display_name+' ('+user.username+')');
    const role=document.createElement('select');for(const [value,label] of Object.entries(roleLabels)){const option=document.createElement('option');option.value=value;option.textContent=label;role.append(option);}role.value=user.role;td(row,'').append(role);
    const active=document.createElement('input');active.type='checkbox';active.checked=user.active;active.setAttribute('aria-label','Tài khoản '+user.username+' hoạt động');td(row,'').append(active);
    const password=document.createElement('input');password.type='password';password.autocomplete='new-password';password.minLength=12;password.maxLength=128;password.placeholder='Để trống nếu giữ nguyên';password.setAttribute('aria-label','Mật khẩu mới cho '+user.username);td(row,'').append(password);
    const save=document.createElement('button');save.textContent='Lưu';save.className='secondary';td(row,'').append(save);
    save.onclick=async()=>{save.disabled=true;try{const body={role:role.value,active:active.checked};if(password.value)body.password=password.value;await api('/auth/users/'+encodeURIComponent(user.id),{method:'PATCH',body:JSON.stringify(body)});password.value='';message('Đã cập nhật tài khoản.');await load();}catch(error){message(error.message);}finally{save.disabled=false;}};
    view.append(row);
  }
  $('users').replaceChildren(view);
}
async function loadAudit(){
  const data=await api('/auth/audit'),view=table(['Thời gian','Người thực hiện','Thao tác','Tài nguyên','Kết quả']);
  for(const event of data.items){const row=document.createElement('tr');[new Date(event.created_at*1000).toLocaleString('vi-VN'),event.username||'Chưa đăng nhập',event.action,event.resource,String(event.result)].forEach(value=>td(row,value));view.append(row);}
  $('audit').replaceChildren(view);
}
async function load(){
  accountState=await api('/auth/status');const user=accountState.user,setup=accountState.setup_needed;
  $('entry').hidden=!!user;$('profile').hidden=!user;$('admin').hidden=!user||user.role!=='admin';$('logout').hidden=!user;
  if(!user){$('entryTitle').textContent=setup?'Thiết lập quản trị viên':'Đăng nhập';$('entrySubmit').textContent=setup?'Tạo quản trị viên và bật đăng nhập':'Đăng nhập';$('entryNote').textContent=setup?'Thiết lập tại máy chủ. Sau khi tạo tài khoản đầu tiên, truy cập bản vẽ sẽ yêu cầu đăng nhập.':'Nhập tài khoản được quản trị viên công ty cấp.';$('displayField').hidden=!setup;$('displayName').required=setup;$('password').minLength=setup?12:1;$('password').autocomplete=setup?'new-password':'current-password';message(setup?'Chưa thiết lập tài khoản dùng chung.':'Đăng nhập để tiếp tục.');return;}
  $('profileTitle').textContent=user.display_name;$('roleCaption').textContent=roleLabels[user.role];message('Đã đăng nhập: '+user.username+'.');
  if(user.role==='admin')await Promise.all([loadUsers(),loadAudit()]);
}
$('entryForm').onsubmit=event=>{event.preventDefault();submit(event.target,async()=>{const body={username:$('username').value,password:$('password').value};if(accountState.setup_needed){body.display_name=$('displayName').value;body.role='admin';}await api(accountState.setup_needed?'/auth/setup':'/auth/login',{method:'POST',body:JSON.stringify(body)});$('password').value='';location.assign(nextPage());});};
$('createForm').onsubmit=event=>{event.preventDefault();submit(event.target,async()=>{await api('/auth/users',{method:'POST',body:JSON.stringify({username:$('newUsername').value,display_name:$('newDisplayName').value,password:$('initialPassword').value,role:$('newRole').value})});event.target.reset();message('Đã thêm thành viên.');await loadUsers();await loadAudit();});};
$('passwordForm').onsubmit=event=>{event.preventDefault();submit(event.target,async()=>{await api('/auth/password',{method:'POST',body:JSON.stringify({old_password:$('oldPassword').value,new_password:$('newPassword').value})});event.target.reset();message('Đã đổi mật khẩu và kết thúc các phiên cũ.');});};
$('logout').onclick=async()=>{try{await api('/auth/logout',{method:'POST'});location.assign('/login');}catch(error){message(error.message);}};
$('reloadAudit').onclick=()=>loadAudit().catch(error=>message(error.message));
load().catch(error=>message(error.message));
