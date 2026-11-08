/* Development-only client portal: OIDC PKCE and in-memory tokens; never store documents or tokens in localStorage. */
'use strict';
const S={config:null,token:null,refresh:null,expires:0};
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notice(message){$('notice').textContent=message}
const enc=b=>btoa(String.fromCharCode(...new Uint8Array(b))).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');
async function login(){const verifier=enc(crypto.getRandomValues(new Uint8Array(32)));
 const challenge=enc(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier)));
 const state=enc(crypto.getRandomValues(new Uint8Array(20)));
 sessionStorage.setItem('ios_client_pkce',JSON.stringify({state,verifier}));
 const url=new URL(S.config.issuer+'/protocol/openid-connect/auth');
 url.search=new URLSearchParams({client_id:S.config.client_id,response_type:'code',redirect_uri:location.origin+'/client',scope:'openid profile email',state,code_challenge:challenge,code_challenge_method:'S256'}).toString();
 location.assign(url.toString());}
function setTokens(t){S.token=t.access_token;S.refresh=t.refresh_token;S.expires=Date.now()+t.expires_in*1000}
async function callback(){let qp=new URLSearchParams(location.search);let code=qp.get('code');if(!code)return false;
 const saved=JSON.parse(sessionStorage.getItem('ios_client_pkce')||'null');sessionStorage.removeItem('ios_client_pkce');
 if(!saved||qp.get('state')!==saved.state)throw Error('Invalid sign-in state');
 const r=await fetch(S.config.issuer+'/protocol/openid-connect/token',{method:'POST',body:new URLSearchParams({client_id:S.config.client_id,grant_type:'authorization_code',redirect_uri:location.origin+'/client',code,code_verifier:saved.verifier})});
 if(!r.ok)throw Error('Identity-provider sign-in failed');setTokens(await r.json());history.replaceState({},'',location.pathname);return true}
async function api(path,options={}){if(!S.token)throw Error('Sign in first');if(Date.now()>S.expires-35000){
 const r=await fetch(S.config.issuer+'/protocol/openid-connect/token',{method:'POST',body:new URLSearchParams({client_id:S.config.client_id,grant_type:'refresh_token',refresh_token:S.refresh})});
 if(!r.ok)throw Error('Session expired. Sign in again.');setTokens(await r.json())}
 const headers={Authorization:'Bearer '+S.token,...options.headers};
 if(options.body&&!(options.body instanceof FormData)){headers['Content-Type']='application/json';options.body=JSON.stringify(options.body)}
 const res=await fetch(path,{...options,headers,cache:'no-store'});
 if(!res.ok){const payload=await res.json().catch(()=>({}));throw Error(payload.detail||`Request failed (${res.status})`)}
 return res.json()}

async function renderStudyIntake(caseId){
 const schema=await api('/api/v1/client/cases/'+encodeURIComponent(caseId)+'/study-intake');
 const controls=schema.fields.map(q=>{
  const required=q.required?' required':'';
  const field=q.kind==='choice'
   ? '<select data-question-path name="'+esc(q.path)+'"'+required+'><option value="">Select…</option>'+
     q.choices.map(o=>'<option value="'+esc(o)+'">'+esc(o.replaceAll('_',' '))+'</option>').join('')+'</select>'
   : '<input data-question-path name="'+esc(q.path)+'" type="'+(q.kind==='date'?'date':q.kind==='money'?'number':'text')+'"'+
     (q.kind==='money'?' min="0" step="0.01"':'')+' maxlength="300"'+required+'>';
  const conditional=q.condition_path?' data-condition-path="'+esc(q.condition_path)+'" data-condition-value="'+esc(q.condition_value)+'" hidden':'';
  return '<div class="intake-field"'+conditional+'><label>'+esc(q.label)+(q.required?' *':'')+'</label>'+field+'</div>';
 }).join('');
 return '<section class="card"><h2>Study-permit preliminary intake</h2>'+
   '<p>Answer from your original documents. Your consultant must independently review each answer; this is not an official IRCC form.</p>'+
   (schema.last_submitted_at?'<p class="status">Previous submission received '+esc(new Date(schema.last_submitted_at).toLocaleString())+'. A new submission creates a new revision.</p>':'')+
   '<form data-intake="'+esc(caseId)+'" data-template="'+esc(schema.template_version)+'">'+
   '<div class="intake-grid">'+controls+'</div>'+
   '<p class="meta">'+esc(schema.notice)+'</p>'+
   '<label class="intake-ack"><input type="checkbox" name="acknowledged_notice" required> I acknowledge the development data-use notice above (not consent to external AI processing).</label>'+
   '<p><button class="primary" type="submit">Submit preliminary intake</button></p>'+
   '</form></section>';
}

function updateIntakeConditions(form){
 for(const row of form.querySelectorAll('[data-condition-path]')){
  const controller=Array.from(form.querySelectorAll('[data-question-path]'))
   .find(node=>node.name===row.dataset.conditionPath);
  const visible=!!controller&&controller.value===row.dataset.conditionValue;
  row.hidden=!visible;
  for(const input of row.querySelectorAll('[data-question-path]')){
   input.disabled=!visible;
   input.required=visible;
   if(!visible)input.value='';
  }
 }
}
const repeatableFields={
 family:[['relationship','Relationship','select','spouse,common_law_partner,child,parent,sibling,other'],['given_name','Given name'],['family_name','Family name'],['date_of_birth','Date of birth','date'],['citizenship','Citizenship']],
 address:[['start_date','From','date'],['end_date','To (leave blank if current)','date'],['line1','Address line'],['city','City'],['region','Province / region'],['country','Country']],
 education:[['start_date','From','date'],['end_date','To','date'],['institution','Institution'],['program','Program'],['country','Country']],
 employment:[['start_date','From','date'],['end_date','To','date'],['employer','Employer'],['position','Position'],['country','Country'],['employment_status','Status','select','employed,self_employed,unemployed,student,other']],
 travel:[['start_date','Departure','date'],['end_date','Return','date'],['destination_country','Country visited'],['purpose','Purpose']]
};
async function renderRepeatables(caseId){
 const url='/api/v1/client/cases/'+encodeURIComponent(caseId)+'/repeatables';
 const data=await api(url);
 const formBlocks=Object.entries(repeatableFields).map(([kind,fields])=>{
  const controls=fields.map(([key,label,type,values])=>{
   const required=['given_name','family_name','relationship','start_date','line1','city','country','institution','program','employer','position','employment_status','destination_country','purpose'].includes(key);
   const input=type==='select'
    ?'<select name="'+esc(key)+'"'+(required?' required':'')+'><option value="">Select…</option>'+values.split(',').map(v=>'<option value="'+esc(v)+'">'+esc(v.replaceAll('_',' '))+'</option>').join('')+'</select>'
    :'<input type="'+(type==='date'?'date':'text')+'" name="'+esc(key)+'" maxlength="160"'+(required?' required':'')+'>';
   return '<div class="intake-field"><label>'+esc(label)+'</label>'+input+'</div>';
  }).join('');
  return '<details><summary>Add '+esc(kind)+' record</summary><form data-repeatable="'+esc(caseId)+'" data-kind="'+esc(kind)+'" data-version="'+esc(data.template_version)+'">'+
    '<div class="intake-grid">'+controls+'</div>'+
    '<label><input type="checkbox" name="acknowledged_notice" required> I acknowledge that this is a development intake for fictional data and requires consultant review.</label>'+
    '<p><button type="submit" class="primary">Send '+esc(kind)+' record to consultant</button></p></form></details>';
 }).join('');
 const received=data.proposals.map(p=>'<div class="meta">'+esc(p.kind)+' · '+esc(p.review_status)+' · '+esc(new Date(p.created_at).toLocaleString())+'</div>').join('');
 return '<section class="card"><h2>Family and personal history</h2>'+
  '<p>Add each family member, address period, educational record, job or trip separately. Entries remain unverified until consultant review and supporting evidence checks.</p>'+
  '<p class="meta">'+esc(data.notice)+'</p>'+formBlocks+
  '<h3>Previously sent entries</h3>'+(received||'<p>No entries sent yet.</p>')+'</section>';
}

async function load(){const cases=await api('/api/v1/client/cases');if(!cases.length){$('cases').innerHTML='<div class="empty">No linked cases yet. Accept an invitation from your consultant to begin.</div>';return}
 const blocks=[];for(const c of cases){const requests=await api(`/api/v1/client/cases/${encodeURIComponent(c.id)}/requests`);
 const intake=c.application_type==='study_permit'?(await renderStudyIntake(c.id))+(await renderRepeatables(c.id)):'';
 blocks.push(`<section class="card"><h2>${esc(c.title)} <span class="status">${esc(c.status)}</span></h2><p>${esc(c.application_type.replaceAll('_',' '))}</p><h3>Requested documents</h3>${requests.length?requests.map(r=>`<div class="request"><div><strong>${esc(r.title)}</strong><div class="meta">${esc(r.instructions)}${r.due_at?' · Due '+esc(new Date(r.due_at).toLocaleDateString()):''}</div></div>${r.status==='open'&&c.status!=='closed'?`<form data-request="${esc(r.id)}" data-case="${esc(c.id)}"><input type="file" name="file" accept=".pdf,.png,.jpg,.jpeg,.txt" required aria-label="Upload ${esc(r.title)}"><button class="primary" type="submit">Upload</button></form>`:`<span class="status">${esc(r.status)}</span>`}</div>`).join(''):'<p>No outstanding document requests.</p>'}</section>${intake}`)}$('cases').innerHTML=blocks.join('');
 for(const form of $('cases').querySelectorAll('form[data-intake]'))updateIntakeConditions(form);}
async function init(){try{S.config=await fetch('/app/config',{cache:'no-store'}).then(r=>r.json());$('signin').onclick=login;
 $('signout').onclick=()=>{S.token=null;S.refresh=null;$('portal').classList.add('hidden');$('welcome').classList.remove('hidden');$('signout').classList.add('hidden');notice('Signed out of this browser session.')};
 $('refresh').onclick=()=>load().catch(e=>notice(e.message));
 $('claim').onsubmit=async e=>{e.preventDefault();try{await api('/api/v1/client/invitations/accept',{method:'POST',body:{token:$('token').value.trim()}});$('token').value='';notice('Invitation accepted.');await load()}catch(error){notice(error.message)}};
 document.addEventListener('change',e=>{const form=e.target.closest('form[data-intake]');if(form)updateIntakeConditions(form)});
 document.addEventListener('submit',async e=>{
  const form=e.target.closest('form[data-repeatable]');
  if(!form)return;
  e.preventDefault();
  const button=form.querySelector('button[type=submit]');button.disabled=true;
  try{
   const details={};
   for(const input of form.querySelectorAll('input[name],select[name]')){
    if(input.name==='acknowledged_notice')continue;
    if(input.value.trim())details[input.name]=input.value.trim();
   }
   await api('/api/v1/client/cases/'+encodeURIComponent(form.dataset.repeatable)+'/repeatables',{
    method:'POST',body:{kind:form.dataset.kind,details,
      template_version:form.dataset.version,
      acknowledged_notice:form.querySelector('[name=acknowledged_notice]').checked}
   });
   notice('Entry sent to your consultant for review. It has not been marked verified.');
   await load();
  }catch(error){notice(error.message)}finally{button.disabled=false}
 });
 document.addEventListener('submit',async e=>{
  const form=e.target.closest('form[data-intake]');
  if(!form)return;
  e.preventDefault();
  const button=form.querySelector('button[type=submit]');button.disabled=true;
  try{
   const answers={};
   for(const element of form.querySelectorAll('[data-question-path]')){
    if(element.disabled)continue;
    const value=(element.value||'').trim();
    if(value)answers[element.name]=value;
   }
   const noticeConfirmed=form.querySelector('[name=acknowledged_notice]').checked;
   const response=await api('/api/v1/client/cases/'+encodeURIComponent(form.dataset.intake)+'/study-intake/submissions',{
    method:'POST',body:{template_version:form.dataset.template,acknowledged_notice:noticeConfirmed,answers}
   });
   notice('Intake revision received. '+response.answer_count+' answers are awaiting your consultant’s review; none is a verified application answer.');
   await load();
  }catch(error){notice(error.message)}finally{button.disabled=false}
 });
 document.addEventListener('submit',async e=>{const form=e.target.closest('form[data-request]');if(!form)return;e.preventDefault();let b=form.querySelector('button');b.disabled=true;
 try{const file=form.querySelector('input[type=file]').files[0];if(!file||file.size>8*1024*1024)throw Error('Maximum file size is 8 MB');
 const payload=new FormData();payload.append('file',file);
 const result=await api(`/api/v1/client/cases/${encodeURIComponent(form.dataset.case)}/requests/${encodeURIComponent(form.dataset.request)}/upload`,{method:'POST',body:payload});
 notice('Upload received in quarantine for security screening. Your consultant will review it after scanning.');await load();}catch(error){notice(error.message)}finally{b.disabled=false}});
 if(await callback()){$('welcome').classList.add('hidden');$('portal').classList.remove('hidden');$('signout').classList.remove('hidden');await load()}
 }catch(error){notice(error.message)}}
window.addEventListener('DOMContentLoaded',init);
