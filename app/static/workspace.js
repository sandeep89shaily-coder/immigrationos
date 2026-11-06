/* ImmigrationOS consultant workspace. No frontend build chain, no stored access token.
   For fictitious development data ONLY. Auth: OIDC authorization code with PKCE. */
'use strict';
const S={config:null,token:null,refresh:null,expires:0,orgs:[],org:null,view:'dashboard',caseId:null,prospectId:null,tab:'overview',filingContext:null,data:{}};
const $=id=>document.getElementById(id);
const h=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const d=x=>x?new Date(x).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'}):'—';
const chip=x=>`<span class="chip ${h(x)}">${h(String(x).replaceAll('_',' '))}</span>`;
const empty=(name,description)=>`<div class="empty"><div class="empty-icon">◇</div><strong>${h(name)}</strong>${h(description)}</div>`;
const btn=(label,action,extra='')=>`<button class="btn ${extra}" data-action="${h(action)}">${h(label)}</button>`;
const badgeCase=c=>c.status==='closed'?'closed':c.status;
const q=()=>`/api/v1/orgs/${encodeURIComponent(S.org)}`;
function toast(msg){$('toast').textContent=msg;$('toast').classList.remove('hidden');setTimeout(()=>$('toast').classList.add('hidden'),4500)}
async function authRefresh(){if(!S.token)return; if(Date.now()<S.expires-40000)return;
  const form=new URLSearchParams({grant_type:'refresh_token',client_id:S.config.client_id,refresh_token:S.refresh});
  let resp=await fetch(`${S.config.issuer}/protocol/openid-connect/token`,{method:'POST',body:form});
  if(!resp.ok){S.token=null;throw new Error('Session expired, please sign in again.');}
  const token=await resp.json();setTokens(token);
}
function setTokens(t){S.token=t.access_token;S.refresh=t.refresh_token||S.refresh;S.expires=Date.now()+t.expires_in*1000}
async function api(path,opts={}){await authRefresh();if(!S.token)throw Error('Not signed in');
 const headers={Authorization:`Bearer ${S.token}`,...opts.headers};
 if(opts.body&&typeof opts.body==='object'&&!(opts.body instanceof FormData)){headers['Content-Type']='application/json';opts.body=JSON.stringify(opts.body)}
 const response=await fetch(path,{...opts,headers,cache:'no-store'});
 if(!response.ok){let reason;try{let data=await response.json();reason=typeof data.detail==='string'?data.detail:JSON.stringify(data.detail)}catch{}throw new Error(reason||`HTTP ${response.status}`)}
 if(opts.raw)return response;
 return response.status===204?null:response.json();
}
const enc=b=>btoa(String.fromCharCode(...new Uint8Array(b))).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');
async function login(){const verifier=enc(crypto.getRandomValues(new Uint8Array(32)));
 const challenge=enc(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier)));
 const state=enc(crypto.getRandomValues(new Uint8Array(20)));
 sessionStorage.setItem('ios_oauth',JSON.stringify({verifier,state}));
 const url=new URL(`${S.config.issuer}/protocol/openid-connect/auth`);
 url.search=new URLSearchParams({client_id:S.config.client_id,redirect_uri:location.origin+'/app',response_type:'code',scope:'openid profile',code_challenge:challenge,code_challenge_method:'S256',state}).toString();
 location.assign(url.toString());
}
async function oauthCallback(){const params=new URLSearchParams(location.search);const code=params.get('code');if(!code)return false;
 const saved=JSON.parse(sessionStorage.getItem('ios_oauth')||'null');sessionStorage.removeItem('ios_oauth');
 if(!saved||params.get('state')!==saved.state)throw Error('Invalid OAuth state');
 const response=await fetch(`${S.config.issuer}/protocol/openid-connect/token`,{method:'POST',body:new URLSearchParams({
 grant_type:'authorization_code',client_id:S.config.client_id,redirect_uri:location.origin+'/app',code,code_verifier:saved.verifier})});
 if(!response.ok)throw Error('Unable to complete sign-in with Keycloak');
 setTokens(await response.json());history.replaceState({},'',location.pathname);return true;
}
function showLogin(message=''){ $('shell').classList.add('hidden');$('login').classList.remove('hidden');$('loginError').textContent=message; }
function showShell(){ $('login').classList.add('hidden');$('shell').classList.remove('hidden'); }
function logout(){S.token=null;S.refresh=null;S.org=null;showLogin('Signed out of this browser session.');}
async function firms(){S.orgs=await api('/api/v1/me/orgs');const selected=sessionStorage.getItem('ios_org');S.org=S.orgs.some(o=>o.id===selected)?selected:(S.orgs[0]?.id||null);
 $('firmSelect').innerHTML=`<option value="">${S.orgs.length?'Select firm':'No firm created'}</option>`+S.orgs.map(o=>`<option value="${h(o.id)}">${h(o.name)}</option>`).join('');$('firmSelect').value=S.org||'';}
async function init(){try{
 S.config=await fetch('/app/config',{cache:'no-store'}).then(r=>r.json());
 $('loginBtn').addEventListener('click',login);
 $('signoutBtn').addEventListener('click',logout);
 $('refreshBtn').addEventListener('click',()=>render().catch(fail));
 $('firmSelect').addEventListener('change',async e=>{S.org=e.target.value||null;sessionStorage.setItem('ios_org',S.org||'');S.caseId=null;S.prospectId=null;await render()});
 $('closeModal').addEventListener('click',closeModal);$('modalBackdrop').addEventListener('click',e=>{if(e.target.id==='modalBackdrop')closeModal()});
 document.querySelectorAll('.nav-item').forEach(x=>x.addEventListener('click',()=>{S.view=x.dataset.view;S.caseId=null;S.prospectId=null;render().catch(fail)}));
 document.addEventListener('click',eventHandler);
 if(!await oauthCallback()){showLogin();return}
 showShell();await firms();await render();
 }catch(e){showLogin(e.message||String(e))}}
function fail(e){console.error(e);toast(e.message||'Unexpected error');}
function nav(){document.querySelectorAll('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.view===S.view));
 const labels={dashboard:'Practice overview',crm:'Prospects',cases:'Matters',clients:'Client directory',review:'Evidence review queue',tasks:'Task management',audit:'Audit history'};
 $('breadcrumb').textContent=S.caseId?'Case workspace':(labels[S.view]||'ImmigrationOS');}
function page(title,desc,tools=''){return `<div class="page-head"><div><div class="eyebrow">IMMIGRATIONOS / ${h(S.view).toUpperCase()}</div><h1>${h(title)}</h1><p>${h(desc)}</p></div><div>${tools}</div></div>`}
function panel(title,inner,tools=''){return `<section class="panel"><div class="panel-head"><h2>${h(title)}</h2>${tools}</div>${inner}</section>`}
function table(headers,rows){if(!rows.length)return empty('Nothing here yet','Create an entry to get started.');return `<div class="table-wrap"><table><thead><tr>${headers.map(x=>`<th>${h(x)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`}
async function render(){nav();if(!S.org){$('mainContent').innerHTML=`${page('Set up your first firm','Create a fictional development firm to start working with sample matters.',btn('+ Create practice','newOrg','primary'))}<div class="callout">This is not an approved production product. Use fictional names and test documents only.</div>`;return}
 $('mainContent').innerHTML='<div class="loading">Loading workspace…</div>';
 try{if(S.caseId)return await renderCase();
 if(S.view==='dashboard')await renderDashboard();
 if(S.view==='crm')await renderCRM();
 if(S.view==='cases')await renderCases();
 if(S.view==='clients')await renderClients();
 if(S.view==='review')await renderReviews();
 if(S.view==='tasks')await renderTasks();
 if(S.view==='audit')await renderAudit();
 }catch(e){$('mainContent').innerHTML=`${page('Something went wrong',e.message||'Request failed')}`;throw e}
}
function caseRows(cases){return cases.map(c=>`<tr class="clickable" data-case="${h(c.id)}"><td><strong>${h(c.title)}</strong></td><td>${h(c.application_type.replaceAll('_',' '))}</td><td>${chip(badgeCase(c))}</td><td>${d(c.created_at)}</td><td>→</td></tr>`)}
async function renderDashboard(){const [data,cases,tasks,issues]=await Promise.all([api(q()+'/dashboard'),api(q()+'/cases?limit=75'),api(q()+'/tasks'),api(q()+'/issues')]);$('issueBadge').textContent=data.open_issues;
 const metrics=[['Active matters',data.cases,'▣'],['Client records',data.clients,'♙'],['Open review issues',data.open_issues,'◇'],['Outstanding tasks',data.open_tasks,'☑']];
 $('mainContent').innerHTML=`${page('Practice overview','Your cases, quality checks and priorities in one place.',btn('+ New matter','newCase','primary'))}
 <div class="welcome"><div><h2>One connected view of every case.</h2><p>Trace each material fact to its source, resolve exceptions, and keep professional review decisions auditable.</p></div>${data.cases?btn('Open review queue →','goReview'):btn('Load synthetic sample →','seedDemo')}</div>
 <div class="grid stats-grid">${metrics.map(([l,v,i])=>`<div class="stat-card"><div class="label">${h(l)}<span class="stat-icon">${i}</span></div><div class="number">${v}</div><div class="footer">Current practice snapshot</div></div>`).join('')}</div>
 <div class="two-col">${panel('Recent matters',table(['Matter','Application','Status','Opened',''],caseRows([...cases].reverse().slice(0,7))),btn('View all →','goCases','smallbtn'))}
 ${panel('Needs attention',`<div class="panel-body">${issues.length?issues.slice(0,4).map(i=>issueItem(i)).join(''):empty('No open evidence issues','New evidence contradictions will appear here.')}${tasks.slice(0,3).map(t=>taskItem(t)).join('')}</div>`,btn('Tasks →','goTasks','smallbtn'))}</div>`;
}
async function renderCases(){const cases=await api(q()+'/cases?limit=100');$('mainContent').innerHTML=`${page('Matters',`${cases.length} matters in this practice.`,btn('+ New matter','newCase','primary'))}${panel('All matters',table(['Matter','Application','Status','Created',''],caseRows([...cases].reverse())))}`}
async function renderClients(){const clients=await api(q()+'/clients?limit=100');const rows=clients.map(c=>`<tr><td><strong>${h(c.first_name)} ${h(c.last_name)}</strong></td><td>${h(c.email||'—')}</td><td>${h(c.phone||'—')}</td><td>${d(c.created_at)}</td></tr>`);$('mainContent').innerHTML=`${page('Clients',`${clients.length} records`,btn('+ Add client','newClient','primary'))}${panel('Client directory',table(['Client','Email','Phone','Added'],rows))}`}
function issueItem(i){return `<div class="item-row"><div class="bullet">!</div><div><div class="item-title">${h(i.field_path.replaceAll('_',' '))} — ${h(i.issue_type.replaceAll('_',' '))}</div><div class="meta">${h(i.description)}</div></div><div class="push">${chip(i.status)}<button class="btn smallbtn" data-case="${h(i.case_id)}">View</button></div></div>`}
function taskItem(t){return `<div class="item-row"><div class="bullet">☑</div><div><div class="item-title">${h(t.title)}</div><div class="meta">Due ${d(t.due_at)} · ${h(t.case_id.slice(0,8))}</div></div><div class="push"><button class="btn smallbtn" data-case="${h(t.case_id)}">Open</button></div></div>`}
async function renderReviews(){const issues=await api(q()+'/issues?status=all');$('mainContent').innerHTML=`${page('Evidence review queue','Material discrepancies require a documented human decision.')}${panel('Case issues',`<div class="panel-body">${issues.length?issues.map(issueItem).join(''):empty('No issues recorded','Create conflicting facts in a case to see the detection engine at work.')}</div>`)}`}
async function renderTasks(){const tasks=await api(q()+'/tasks?status=all');const rows=tasks.map(t=>`<tr class="clickable" data-case="${h(t.case_id)}"><td><strong>${h(t.title)}</strong></td><td>${chip(t.status)}</td><td>${d(t.due_at)}</td><td>${h(t.case_id.slice(0,8))}</td><td>→</td></tr>`);$('mainContent').innerHTML=`${page('Tasks','Operational to-dos and critical case milestones.')}${panel('All tasks',table(['Task','Status','Due','Case',''],rows))}`}
async function renderAudit(){const events=await api(q()+'/audit');const rows=events.map(e=>`<tr><td>${d(e.occurred_at)}</td><td><strong>${h(e.action.replaceAll('.',' · '))}</strong></td><td>${h(e.resource_type)}</td><td>${h(e.actor_sub.slice(0,22))}</td></tr>`);$('mainContent').innerHTML=`${page('Audit history','Metadata-only actions, timestamped and attributed.')}${panel('Latest activity',table(['Date','Action','Resource','Actor'],rows))}`}
function keyValue(label,value){return `<div class="item-row"><div style="flex:1"><div class="meta">${h(label)}</div><div class="item-title">${h(value||'—')}</div></div></div>`}
function gateWidget(r){return `<div class="gate ${r.review_gate==='operational_checks_clear'?'clear':''}"><strong>${r.review_gate==='operational_checks_clear'?'✓ Operational checks clear':'⚠ Professional review required'}</strong><div class="small" style="margin-top:6px">This is NOT an eligibility or government submission decision.</div>${r.reasons.length?`<ul>${r.reasons.map(x=>`<li>${h(x)}</li>`).join('')}</ul>`:''}</div>`}
function factItem(f){return `<div class="item-row"><div class="bullet">◇</div><div style="flex:1;min-width:0"><div class="meta">${h(f.field_path)}</div><div class="item-title">${h(f.value)}</div>${f.source_excerpt?`<div class="evidence-preview">${h(f.source_excerpt)}</div>`:''}<div class="meta">${f.document_id?'Source document linked':'Client-reported / source not linked'} ${f.source_page?' · page '+f.source_page:''}</div></div><div class="push">${chip(f.review_status)}${f.review_status==='pending'?`<div style="margin-top:8px">${btn('Verify','verifyFact:'+f.id,'smallbtn')} ${btn('Reject','rejectFact:'+f.id,'smallbtn')}</div>`:''}</div></div>`}
function docItem(doc){return `<div class="item-row"><div class="bullet">▤</div><div style="flex:1"><div class="item-title">${h(doc.filename)}</div><div class="meta">${h(doc.document_type)} · ${(doc.size_bytes/1024).toFixed(0)} KB · SHA-256 ${h(doc.sha256.slice(0,12))}…</div></div><div class="push">${btn('Extract','extractDoc:'+doc.id,'smallbtn')} ${S.config.ai_enabled?btn('AI review','aiDoc:'+doc.id,'smallbtn'):''} ${btn('Download','downloadDoc:'+doc.id,'smallbtn')}</div></div>`}
async function renderCase(){const [cases,clients,tasks,issues,facts,docs,readiness,suggestions]=await Promise.all([
 api(q()+'/cases?limit=100'),api(q()+'/clients?limit=100'),api(q()+`/cases/${S.caseId}/tasks`),api(q()+`/cases/${S.caseId}/issues`),
 api(q()+`/cases/${S.caseId}/facts`),api(q()+`/cases/${S.caseId}/documents`),api(q()+`/cases/${S.caseId}/readiness`),api(q()+`/cases/${S.caseId}/suggestions`)]);
 const c=cases.find(c=>c.id===S.caseId);if(!c){S.caseId=null;return render()};const client=clients.find(x=>x.id===c.client_id);
 const worksheet=await api(q()+`/cases/${S.caseId}/worksheets/${c.application_type==='work_permit'?'work_permit_demo':'study_permit_demo'}`);
 S.data={cases,clients,tasks,issues,facts,docs,readiness,suggestions,worksheet};
 const tabs=['overview','evidence','planning','intake','documents','suggestions','worksheet','preflight','representative','tasks','issues','portal'];
 let content='';
 if(S.tab==='overview') content=`${gateWidget(readiness)}<div class="two-col">${panel('Matter details',`<div class="panel-body">${keyValue('Application type',c.application_type.replaceAll('_',' '))}${keyValue('Client',client?client.first_name+' '+client.last_name:'Unknown')}${keyValue('Opened',d(c.created_at))}${keyValue('Status',c.status)}</div>`)}${panel('Evidence summary',`<div class="panel-body">${keyValue('Verified facts',String(readiness.verified_facts))}${keyValue('Pending verification',String(readiness.pending_facts))}${keyValue('Open exceptions',String(readiness.open_issues))}${keyValue('Documents uploaded',String(readiness.documents))}</div>`)}</div>`;
 if(S.tab==='evidence')content=panel('Case facts and human verification',`<div class="panel-body">${facts.length?facts.map(factItem).join(''):empty('No evidence facts','Add a manually documented fact to begin the evidence record.')}</div>`,btn('+ Add fact','newFact','primary smallbtn'));
 if(S.tab==='planning'){
 let html='<div class=callout>Select the filing context. This operational checklist is non-exhaustive and always requires RCIC review.</div><p>'+btn('Outside Canada','filingContext:outside_canada','smallbtn')+' '+btn('Inside Canada','filingContext:inside_canada','smallbtn')+'</p>';
 let actions='';
 if(S.filingContext){
  const matrix=await api(q()+`/cases/${S.caseId}/evidence/matrix?filing_context=${encodeURIComponent(S.filingContext)}`);
  html+=`<p class=meta>Filing context: ${h(matrix.filing_context)} · Open evidence issues: ${matrix.open_evidence_issue_count}</p><div class=warning-text>${h(matrix.warning)}</div>`;
  if(matrix.source_recheck_required)html+='<div class=warning-text>Official sources require rechecking before use.</div>';
  html+=matrix.requirements.map(r=>`<div class=item-row><div class=bullet>▤</div><div style='flex:1'><div class=item-title>${h(r.title)}</div><div class=meta>${h(r.guidance)}</div><div class=meta><a href='${h(r.source_url)}' target='_blank' rel='noopener noreferrer'>Official IRCC source ↗</a>${r.requires_professional_applicability_review?' · Conditional applicability requires RCIC assessment':''}</div></div><div class=push>${chip(r.status)}</div></div>`).join('');
  const reviewInfo=await api(q()+`/cases/${S.caseId}/reviews/history?filing_context=${encodeURIComponent(S.filingContext)}`);
  S.latestReviewHash=reviewInfo.current.case_sha256;
  const recent=reviewInfo.history[0];
  if(recent)html+=`<div class=callout>Last staff review: ${h(recent.reviewer_sub)} · ${d(recent.created_at)} · ${recent.is_current?'Current evidence fingerprint':'STALE — evidence changed, review again'}. This is not IRCC approval.</div>`;
  else html+='<div class=callout>No recorded staff review yet. Document sufficiency and legal applicability still require professional assessment.</div>';
  actions=btn('Create draft document requests','requestEvidence','primary smallbtn')+' '+btn('Record staff evidence review','recordEvidenceReview','smallbtn');
 }else html+=empty('Select filing context','Choose inside or outside Canada to view case evidence coverage.');
 content=panel('RCIC study-permit evidence planning',`<div class=panel-body>${html}</div>`,actions);
}

 if(S.tab==='intake'){
  if(c.application_type!=='study_permit'){
   content=panel('Client intake','<div class="panel-body"><div class="callout">The preliminary questionnaire currently supports study permit matters only.</div></div>');
  }else{
   const result=await api(q()+'/cases/'+S.caseId+'/study-intake');
   const versions=result.submissions;
   let body='<div class="callout">Client questionnaire answers are self-reported. Accepting an answer adds a PENDING fact. Review against the original document before professional verification. This is not an official IRCC form.</div>';
   if(!versions.length)body+=empty('No questionnaires received','Invite the fictional client through the Portal tab. The questionnaire appears automatically on their study-permit case.');
   else{
    const current=versions[0];
    const reviewed=new Map(current.decisions.map(d=>[d.field_path,d]));
    body+='<div class="meta">Current version: '+h(current.template_version)+' · Submitted '+d(current.submitted_at)+' · '+versions.length+' revision(s)</div>';
    body+=Object.entries(current.answers).map(([path,value])=>{
     const decision=reviewed.get(path);
     const controls=decision?chip(decision.decision):
       btn('Accept to pending facts','intakeDecision:'+current.id+':'+path+':accept','smallbtn')+' '+
       btn('Dismiss','intakeDecision:'+current.id+':'+path+':dismiss','smallbtn');
     return '<div class="item-row"><div style="flex:1;min-width:0"><div class="meta">'+h(path)+'</div>'+
       '<div class="item-title">'+h(value)+'</div></div><div class="push">'+controls+'</div></div>';
    }).join('');
    if(versions.length>1)body+='<p class="warning-text">Earlier submissions are retained for history but cannot be accepted after a newer revision. Previously accepted facts are not silently overwritten.</p>';
   }
   content=panel('Client study-permit intake review','<div class="panel-body">'+body+'</div>');
  }
 }
if(S.tab==='documents')content=panel('Encrypted development documents',`<div class="panel-body"><div class="warning-text">Development only — synthetic documents. Production uploads are disabled until malware scanning and privacy approval.</div>${docs.length?docs.map(docItem).join(''):empty('No documents uploaded','Upload a synthetic test document to test the secure storage workflow.')}</div>`,btn('+ Upload','newDocument','primary smallbtn'));
 if(S.tab==='suggestions')content=panel('Document extraction proposals',`<div class="panel-body"><div class="callout">Proposals come from a deterministic labelled-field parser, not an AI model. Every proposal needs human acceptance, then separate fact verification.</div>${suggestions.length?suggestions.map(s=>`<div class="item-row"><div class="bullet">◇</div><div style="flex:1"><div class="meta">${h(s.field_path)} · Page ${s.source_page} · ${h(s.extraction_method)}</div><div class="item-title">${h(s.value)}</div><div class="evidence-preview">${h(s.source_excerpt)}</div></div><div class="push">${chip(s.status)} ${s.status==='proposed'?`<div style="margin-top:8px">${btn('Accept','acceptSuggestion:'+s.id,'smallbtn')} ${btn('Dismiss','dismissSuggestion:'+s.id,'smallbtn')}</div>`:''}</div></div>`).join(''):empty('No extraction suggestions','Upload a synthetic labelled PDF/text document and select Extract on the Documents tab.')}</div>`);
 if(S.tab==='worksheet')content=panel('Internal preparation worksheet',`<div class="panel-body"><div class="warning-text">This is an INTERNAL DEMONSTRATION worksheet — not an official IRCC form and not an eligibility decision.</div>${gateWidget(readiness)}<div class="callout">${h(worksheet.title)} · ${h(worksheet.template_version)} · ${h(worksheet.status.replaceAll('_',' '))}</div>${table(['Field','Mapped verified value','Status'],worksheet.fields.map(f=>`<tr><td><strong>${h(f.label)}</strong><div class="meta">${h(f.field_path)}</div></td><td>${h(f.value||'—')}</td><td>${chip(f.status)}</td></tr>`))}</div>`);
 if(S.tab==='preflight'){
  if(c.application_type!=='study_permit'){
   content=panel('Internal form preflight','<div class="panel-body"><div class="callout">The mapped preflight is only available for synthetic study permit cases. Other forms remain unsupported.</div></div>');
  }else{
   let html='<div class="warning-text">INTERNAL preparation check only. This does not produce a validated IRCC PDF or authorize government submission.</div>';
   html+='<p>'+btn('Outside Canada · IMM1294','filingContext:outside_canada','smallbtn')+' '+btn('Inside Canada · IMM5709','filingContext:inside_canada','smallbtn')+'</p>';
   let actionButton='';
   S.preflight=null;
   if(S.filingContext){
    const code=S.filingContext==='inside_canada'?'IMM5709':'IMM1294';
    const root=q()+'/ircc/cases/'+S.caseId+'/forms/'+code+'/preflight?filing_context='+encodeURIComponent(S.filingContext);
    const pre=await api(root);
    S.preflight=pre;
    html+='<div class="callout"><strong>'+h(pre.code)+'</strong> · '+h(pre.internal_preflight_status.replaceAll('_',' '))+' · Acknowledgement: '+h(pre.acknowledgement)+'</div>';
    html+='<div class="meta">Official source observed '+h(pre.observed_on)+' · '+h(pre.observed_revision)+'</div>';
    if(pre.blockers.length)html+='<h3>Blocking review items</h3><ul>'+pre.blockers.map(x=>'<li>'+h(x)+'</li>').join('')+'</ul>';
    else html+='<div class="callout">The limited internal preflight has no blocking items. Official PDF preparation and IRCC submission remain unavailable.</div>';
    html+=table(['Mapped field','Verified value','Evidence status'],pre.fields.map(x=>'<tr><td>'+h(x.label)+'<div class="meta">'+h(x.canonical_path)+'</div></td><td>'+h(x.value||'—')+'</td><td>'+h(x.status)+'</td></tr>'));
    html+='<p class="meta">Snapshot SHA-256: '+h(pre.snapshot_sha256.slice(0,20))+'…</p>';
    if(pre.acknowledgement==='stale')html+='<div class="warning-text">The last acknowledgement is stale. Re-review the case after resolving all blockers.</div>';
    if(pre.internal_preflight_status==='reviewable' && pre.acknowledgement!=='current')
     actionButton=btn('Acknowledge internal review','acknowledgePreflight','primary smallbtn');
   }else html+=empty('Select filing context','The filing route cannot be inferred from citizenship or an address.');
   content=panel('Evidence-bound form preflight','<div class="panel-body">'+html+'</div>',actionButton);
  }
 }
if(S.tab==='representative'){
 S.repOperation=S.repOperation||'appoint'; S.repChannel=S.repChannel||'portal_or_secure_account';
 const source=q()+'/ircc/forms/IMM5476/workflow?operation='+encodeURIComponent(S.repOperation)+'&submission_channel='+encodeURIComponent(S.repChannel);
 const profile=await api(source);
 let body='<div class=warning-text>IMM 5476 (11-2025) — preparation and PDF technical inspection only. No official form is generated, validated or submitted.</div>';
 body+='<p>'+[['appoint','Appoint'],['update_contact','Update contact'],['cancel','Cancel'],['replace','Replace'],['withdraw','Withdraw']].map(pair=>btn(pair[1],'repOperation:'+pair[0],'smallbtn')).join(' ')+'</p>';
 body+='<p>'+btn('Portal / secure account','repChannel:portal_or_secure_account','smallbtn')+' '+btn('Outside a portal','repChannel:outside_portal','smallbtn')+'</p>';
 body+='<div class=callout><strong>'+h(profile.operation_title)+'</strong> · Required sections: '+profile.sections.map(x=>h(x.code)).join(', ')+'</div>';
 body+='<p><a href="'+h(profile.source_url)+'" target="_blank" rel="noopener noreferrer">Official IRCC instructions ↗</a> · <a href="'+h(profile.official_pdf_url)+'" target="_blank" rel="noopener noreferrer">Current PDF ↗</a></p>';
 body+='<ul>'+profile.notes.map(x=>'<li>'+h(x)+'</li>').join('')+'</ul>';
 body+='<div class=callout>Inspect a blank PDF downloaded from IRCC to learn its technical structure. The application does not store this file or certify its official provenance. Never upload completed client documents.</div>';
 if(S.templateInspection){const r=S.templateInspection;body+='<div class=callout>Last inspection: '+h(r.classification)+' · '+r.pages+' pages · '+r.field_count+' fields · SHA-256 '+h(r.file_sha256.slice(0,18))+'…</div>';body+='<p class=meta>Indicators: '+h(r.indicators.join(', ')||'none')+'</p>';body+='<p class=meta>Sample technical fields: '+h(r.field_names.slice(0,12).join(', ')||'none')+'</p>';}
 content=panel('IMM 5476 · RCIC representative workflow','<div class=panel-body>'+body+'</div>',btn('Inspect blank PDF','inspectRepresentativePDF','primary smallbtn'));
}
if(S.tab==='portal'){
   const root=q()+`/cases/${S.caseId}/portal`;
   const [requests,submissions]=await Promise.all([api(root+'/requests'),api(root+'/submissions')]);
   content=panel('Client access and document intake',`<div class="panel-body"><div class="callout">Clients authenticate using a verified identity-provider email and a one-time invitation. A client sees only their linked case and its document requests. Uploaded files remain in quarantine until a malware scanner clears them.</div><p><a href="/client" target="_blank" rel="noopener noreferrer">Open the development client portal ↗</a></p><h3>Document requests</h3>${requests.length?requests.map(r=>`<div class="item-row"><div class="bullet">▤</div><div style="flex:1"><div class="item-title">${h(r.title)}</div><div class="meta">${h(r.document_type)} · ${h(r.instructions)} · Due ${d(r.due_at)}</div></div>${chip(r.status)}</div>`).join(''):empty('No document requests','Ask the client for a document.')}<h3>Client submissions</h3>${submissions.length?submissions.map(s=>`<div class="item-row"><div class="bullet">↥</div><div style="flex:1"><div class="item-title">Received submission ${h(s.id.slice(0,8))}</div><div class="meta">${d(s.created_at)} · ${h(s.document_id.slice(0,8))}</div></div>${chip(s.scan_status)} ${s.scan_status==='quarantined'?btn('Scan','scanSubmission:'+s.id,'smallbtn'):''}</div>`).join(''):empty('No client submissions','Client uploads will appear here after receipt.')}</div>`,btn('Create invitation','newPortalInvite','smallbtn')+' '+btn('+ Request document','newPortalRequest','primary smallbtn'));
 }
 if(S.tab==='tasks')content=panel('Case tasks',`<div class="panel-body">${tasks.length?tasks.map(t=>`<div class="item-row"><div class="bullet">☑</div><div style="flex:1"><div class="item-title">${h(t.title)}</div><div class="meta">Due ${d(t.due_at)}</div></div><div class="push">${chip(t.status)} ${t.status==='open'?btn('Complete','completeTask:'+t.id,'smallbtn'):''}</div></div>`).join(''):empty('No tasks','Add milestones or follow-up work.')}</div>`,btn('+ Add task','newTask','primary smallbtn'));
 if(S.tab==='issues')content=panel('Contradictions and resolutions',`<div class="panel-body">${issues.length?issues.map(i=>`<div class="item-row"><div class="bullet">!</div><div style="flex:1"><div class="item-title">${h(i.field_path)}</div><div class="meta">${h(i.description)}</div>${i.resolution?`<div class="evidence-preview">Resolution: ${h(i.resolution)}</div>`:''}</div><div class="push">${chip(i.status)} ${i.status==='open'?btn('Resolve','resolveIssue:'+i.id,'smallbtn'):''}</div></div>`).join(''):empty('No conflicts detected','Adding different values for the same fact will create a review issue.')}</div>`);
 $('mainContent').innerHTML=`<div class="page-head"><div><div class="eyebrow"><button class="btn smallbtn" data-action="backCases">← All matters</button> &nbsp; / CASE WORKSPACE</div><h1 class="case-title">${h(c.title)}</h1><div class="detail-meta"><span>${h(c.application_type.replaceAll('_',' '))}</span><span>${h(client?client.first_name+' '+client.last_name:'Client')}</span>${chip(c.status)}</div></div><div>${c.status!=='closed'?btn('Change status','changeStatus','primary'):''}</div></div><div class="pillbar">${tabs.map(t=>`<button class="pilltab ${S.tab===t?'active':''}" data-tab="${t}">${h(t.charAt(0).toUpperCase()+t.slice(1))}${t==='issues'&&issues.filter(i=>i.status==='open').length?' · '+issues.filter(i=>i.status==='open').length:''}</button>`).join('')}</div>${content}`;
}
function modal(inner,handler){$('modalBody').innerHTML=inner;$('modalBackdrop').classList.remove('hidden');const form=$('modalBody').querySelector('form');if(form)form.addEventListener('submit',async e=>{e.preventDefault();let submit=form.querySelector('[type="submit"]');submit.disabled=true;try{await handler(form);closeModal();await firms();await render();toast('Saved successfully')}catch(err){toast(err.message||'Save failed')}finally{submit.disabled=false}})}
function closeModal(){S.inviteToken=null;$('modalBackdrop').classList.add('hidden');$('modalBody').innerHTML=''}
function values(f){return Object.fromEntries(new FormData(f).entries())}
const fld=(name,label,type='text',attr='')=>`<div class="form-field"><label for="f_${h(name)}">${h(label)}</label><input id="f_${h(name)}" name="${h(name)}" type="${h(type)}" ${attr}></div>`;
const selectField=(name,label,options)=>`<div class="form-field"><label>${h(label)}</label><select name="${h(name)}">${options.map(([value,label])=>`<option value="${h(value)}">${h(label)}</option>`).join('')}</select></div>`;
const actions=label=>`<div class="actions"><button type="button" class="btn" data-action="closeModal">Cancel</button><button type="submit" class="btn primary">${h(label)}</button></div>`;
function newOrg(){modal(`<h2>Create a practice</h2><p>Start with a fictional organization in your local development environment.</p><form>${fld('name','Firm name','text','required minlength="2" placeholder="e.g. Northstar Demo Immigration"')}${fld('slug','Short unique ID','text','required minlength="3" pattern="[a-z][a-z0-9-]*" placeholder="northstar-demo"')}${actions('Create practice')}</form>`,async f=>{const o=await api('/api/v1/orgs',{method:'POST',body:values(f)});S.org=o.id;sessionStorage.setItem('ios_org',S.org)})}
function newClient(){modal(`<h2>Add a client</h2><p>Fictional test data only — do not enter real client information.</p><form><div class="form-grid">${fld('first_name','First name','text','required')}${fld('last_name','Last name','text','required')}</div>${fld('email','Email','email')}${fld('phone','Phone')}${actions('Add client')}</form>`,async f=>{let v=values(f);v.email=v.email||null;v.phone=v.phone||null;await api(q()+'/clients',{method:'POST',body:v})})}
async function newCase(){const clients=await api(q()+'/clients?limit=100');if(!clients.length){toast('Add a fictional client first');return newClient()}
 modal(`<h2>Open a matter</h2><p>Associate a new application with an existing client.</p><form>${selectField('client_id','Client',clients.map(c=>[c.id,c.first_name+' '+c.last_name]))}${selectField('application_type','Application category',[['study_permit','Study permit'],['work_permit','Work permit'],['visitor_visa','Visitor visa'],['express_entry','Express Entry'],['sponsorship','Family sponsorship'],['other','Other']])}${fld('title','Matter title','text','required minlength="2" placeholder="e.g. Study permit · September intake"')}${actions('Create matter')}</form>`,async f=>{const c=await api(q()+'/cases',{method:'POST',body:values(f)});S.caseId=c.id;S.tab='overview'})}
function newPortalRequest(){modal(`<h2>Request a client document</h2><p>Only linked client identities can see this request. Synthetic data only.</p><form>${fld('title','Document request title','text','required minlength="3"')}${selectField('document_type','Type',[['passport','Passport'],['employment_letter','Employment letter'],['education','Education'],['finance','Financial evidence'],['other','Other']])}${fld('instructions','Instructions','text','maxlength="1200"')}${fld('due_at','Due date','date')}${actions('Create document request')}</form>`,async f=>{const data=values(f);data.due_at=data.due_at?new Date(data.due_at+'T12:00:00Z').toISOString():null;await api(q()+`/cases/${S.caseId}/portal/requests`,{method:'POST',body:data})})}
async function newPortalInvite(){if(!confirm('Create a single-use invitation valid for 48 hours? The client must sign in with the matching verified email.'))return;
 const invitation=await api(q()+`/cases/${S.caseId}/portal/invitations`,{method:'POST'});
 S.inviteToken=invitation.invite_token;
 $('modalBody').innerHTML=`<h2>Invitation created</h2><p>The link token is shown once. Deliver it through an approved secure channel to the intended client. The token is not sent automatically.</p><div class="form-field"><label>One-time token</label><textarea readonly id="newInviteToken" rows="4">${h(invitation.invite_token)}</textarea></div><p>Client portal: <a href="/client" target="_blank" rel="noopener noreferrer">Open client portal</a></p><div class="actions">${btn('Copy token','copyPortalToken','primary')} ${btn('Close','closeModal')}</div>`;
 $('modalBackdrop').classList.remove('hidden');}
function newTask(){modal(`<h2>Create a task</h2><p>Tasks are operational. They do not represent a complete legal document checklist.</p><form>${fld('title','Task description','text','required minlength="3"')}${fld('due_at','Due date','date')}${actions('Save task')}</form>`,async f=>{let v=values(f);v.due_at=v.due_at?new Date(v.due_at+'T12:00:00Z').toISOString():null;await api(q()+`/cases/${S.caseId}/tasks`,{method:'POST',body:v})})}
function newFact(){const docs=S.data.docs||[];modal(`<h2>Add an evidence fact</h2><p>Facts remain unverified until a professional manually reviews them. Different values for the same field automatically create a review issue.</p><form>${fld('field_path','Canonical field path','text','required pattern="[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*){1,5}" placeholder="employment.end_date"')}${fld('value','Reported value','text','required maxlength="1200"')}${selectField('document_id','Source document',[['','Client-reported / no document'],...docs.map(x=>[x.id,x.filename])])}${fld('source_page','Source page number','number','min="1"')}${fld('source_excerpt','Evidence excerpt','text','maxlength="500"')}${actions('Record fact')}</form>`,async f=>{let v=values(f);v.document_id=v.document_id||null;v.source_page=v.source_page?Number(v.source_page):null;v.source_excerpt=v.source_excerpt||null;await api(q()+`/cases/${S.caseId}/facts`,{method:'POST',body:v})})}
function newDocument(){modal(`<h2>Upload a synthetic document</h2><p>Encrypted at rest in this local development environment. Only PDF, PNG, JPEG and UTF-8 text are supported (8 MB maximum).</p><div class="warning-text">Never use real passports, bank statements, immigration applications or other actual client data in this preview.</div><form>${selectField('document_type','Document type',[['passport','Passport'],['employment_letter','Employment letter'],['education','Education'],['finance','Financial evidence'],['other','Other']])}${fld('file','Test file','file','required accept=".pdf,.png,.jpg,.jpeg,.txt"')}${actions('Upload test document')}</form>`,async f=>{const data=new FormData(f);await api(q()+`/cases/${S.caseId}/documents`,{method:'POST',body:data})})}
function resolveIssue(id){modal(`<h2>Resolve evidence issue</h2><p>Record a professional rationale. This is retained in the case record, not in the metadata audit log.</p><form>${selectField('status','Decision',[['resolved','Resolved'],['dismissed','Dismissed with explanation']])}<div class="form-field"><label>Rationale</label><textarea name="resolution" required minlength="10" maxlength="1200" placeholder="Explain how the conflicting evidence was reconciled..."></textarea></div>${actions('Save decision')}</form>`,async f=>{await api(q()+`/cases/${S.caseId}/issues/${id}/resolve`,{method:'POST',body:values(f)})})}
function changeStatus(){const caseObj=S.data.cases.find(x=>x.id===S.caseId);const map={draft:['intake','closed'],intake:['review','on_hold','closed'],review:['intake','on_hold','closed'],on_hold:['intake','review','closed'],closed:[]};const options=map[caseObj.status]||[];
 modal(`<h2>Update case status</h2><p>Status changes are recorded in the audit trail. This does not submit anything to IRCC.</p><form>${selectField('status','Next status',options.map(v=>[v,v.replaceAll('_',' ')]))}${fld('reason','Reason (required)','text','required minlength="10" maxlength="250"')}${actions('Update status')}</form>`,async f=>{await api(q()+`/cases/${S.caseId}/status`,{method:'PATCH',body:values(f)})})}
async function downloadDoc(id){const doc=S.data.docs.find(x=>x.id===id);const res=await api(q()+`/cases/${S.caseId}/documents/${id}/download`,{raw:true});const blob=await res.blob();const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=doc?.filename||'document';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),2000)}
async function eventHandler(e){const tab=e.target.closest('[data-tab]');if(tab){S.tab=tab.dataset.tab;return render().catch(fail)}const prow=e.target.closest('[data-prospect]');if(prow){S.prospectId=prow.dataset.prospect;S.caseId=null;S.view='crm';return render().catch(fail)}const row=e.target.closest('[data-case]');if(row){S.caseId=row.dataset.case;S.view='cases';S.tab='overview';S.filingContext=null;S.prospectId=null;return render().catch(fail)}const act=e.target.closest('[data-action]');if(!act)return;const action=act.dataset.action;
 try{
 if(action.startsWith('crm:'))return await crmAction(action);
 if(action.startsWith('repOperation:')){S.repOperation=action.split(':')[1];return await render()}
if(action.startsWith('repChannel:')){S.repChannel=action.split(':')[1];return await render()}
if(action==='inspectRepresentativePDF'){
 return modal('<h2>Inspect blank official form</h2><p>Development only. Select an uncompleted IMM 5476 PDF downloaded from IRCC. No client records, and no government validation.</p><form><input type="hidden" name="form_code" value="IMM5476"><label>Blank PDF template <input type="file" name="file" accept=".pdf" required></label><p><button type="submit" class="btn primary">Inspect technical fields</button></p></form>',async form=>{S.templateInspection=await api(q()+'/ircc/inspect-template',{method:'POST',body:new FormData(form)})});
}
if(action==='acknowledgePreflight'){
  const pre=S.preflight;
  if(!pre || pre.internal_preflight_status!=='reviewable')return toast('Resolve all internal review blockers first');
  if(!confirm('Acknowledge only this INTERNAL field subset? This is not an IRCC form, professional eligibility decision, or permission to submit.'))return;
  const url=q()+'/ircc/cases/'+S.caseId+'/forms/'+pre.code+'/preflight/acknowledge?filing_context='+encodeURIComponent(S.filingContext);
  await api(url,{method:'POST',body:{snapshot_sha256:pre.snapshot_sha256}});
  await render();
  return toast('Internal evidence snapshot acknowledged; IRCC submission remains blocked');
 }
 if(action.startsWith('filingContext:')){S.filingContext=action.split(':')[1];return await render()}
if(action==='requestEvidence'){
 if(!S.filingContext)return toast('Select filing context first');
 if(!confirm('Create draft document requests? No client message is sent. Review requests before sharing.'))return;
 const result=await api(q()+`/cases/${S.caseId}/evidence/request-missing`,{method:'POST',body:{filing_context:S.filingContext}});
 await render();return toast(`${result.created.length} draft document requests created`);
}
if(action==='recordEvidenceReview'){
 if(!S.filingContext||!S.latestReviewHash)return toast('Select filing context and refresh evidence first');
 return modal(`<h2>Record staff evidence review</h2><p>This is an operational review record, NOT eligibility, verified RCIC licensing, or IRCC submission approval. Any later evidence changes will make the review stale.</p><form><label>Review note (at least 20 characters)<textarea name='review_note' required minlength='20' maxlength='1200' rows='4' style='display:block;width:100%'></textarea></label><p><label><input type='checkbox' name='sources_checked' required> I independently checked the current official IRCC instructions.</label></p><button type='submit' class='btn primary'>Record reviewed snapshot</button></form>`,async form=>{
  await api(q()+`/cases/${S.caseId}/reviews/record`,{method:'POST',body:{filing_context:S.filingContext,expected_sha256:S.latestReviewHash,review_note:form.querySelector('[name=review_note]').value,reviewed_current_ircc_sources:form.querySelector('[name=sources_checked]').checked}});
 });
}
if(action==='seedDemo'){if(!confirm('Create fictional demonstration clients, cases and evidence?'))return;await api(q()+'/demo-seed',{method:'POST'});await render();return toast('Sample cases created')}
 if(action==='newPortalInvite')return await newPortalInvite();if(action==='newPortalRequest')return newPortalRequest();if(action==='copyPortalToken'){if(S.inviteToken)await navigator.clipboard.writeText(S.inviteToken);return toast('Token copied to clipboard')}if(action==='newOrg')return newOrg();if(action==='newClient')return newClient();if(action==='newCase')return await newCase();if(action==='newTask')return newTask();if(action==='newFact')return newFact();if(action==='newDocument')return newDocument();if(action==='changeStatus')return changeStatus();if(action==='closeModal')return closeModal();
 if(action==='backCases'||action==='goCases'){S.caseId=null;S.view='cases';return await render()}
 if(action==='goTasks'){S.caseId=null;S.view='tasks';return await render()}
 if(action==='goReview'){S.caseId=null;S.view='review';return await render()}
 if(action.startsWith('intakeDecision:')){
  const [,submissionId,path,decision]=action.split(':');
  if(!confirm((decision==='accept'?'Accept as an UNVERIFIED pending fact?':'Dismiss this client-reported answer?')+
     ' No IRCC field will be approved automatically.'))return;
  await api(q()+'/cases/'+S.caseId+'/study-intake/'+submissionId+
    '/answers/'+encodeURIComponent(path)+'/decide',{method:'POST',body:{decision}});
  await render();return toast(decision==='accept'?'Answer added as pending fact':'Answer dismissed');
 }
 const [command,id]=action.split(':');if(command==='resolveIssue')return resolveIssue(id);
 if(command==='downloadDoc')return await downloadDoc(id);
 if(command==='aiDoc'){
   if(!confirm('External AI processing sends this synthetic document to a model provider. Do NOT use real client data. Continue?'))return;
   const result=await api(q()+`/cases/${S.caseId}/documents/${id}/analyze-ai`,{method:'POST'});
   S.tab='suggestions';await render();return toast(`${result.length} new source-anchored AI suggestions`);
 }
 if(command==='extractDoc'){const result=await api(q()+`/cases/${S.caseId}/documents/${id}/extract`,{method:'POST'});S.tab='suggestions';await render();return toast(`${result.length} fact suggestions found`)}
 if(command==='acceptSuggestion'||command==='dismissSuggestion'){
   const decision=command==='acceptSuggestion'?'accept':'dismiss';
   await api(q()+`/cases/${S.caseId}/suggestions/${id}/decide`,{method:'POST',body:{decision}});
   await render();return toast(`Suggestion ${decision==='accept'?'accepted into pending facts':'dismissed'}`);
 }
 if(command==='scanSubmission'){const result=await api(q()+`/cases/${S.caseId}/portal/submissions/${id}/scan`,{method:'POST'});await render();return toast('Scan result: '+result.scan_status)}
 if(command==='completeTask'){await api(q()+`/cases/${S.caseId}/tasks/${id}/complete`,{method:'POST'});await render();return toast('Task marked complete')}
 if(command==='verifyFact'||command==='rejectFact'){
 const decision=command==='verifyFact'?'verified':'rejected';
 if(!confirm(`Record this fact as ${decision}? This is an audited human decision.`))return;
 await api(q()+`/cases/${S.caseId}/facts/${id}/review`,{method:'POST',body:{status:decision}});await render();return toast(`Fact marked ${decision}`);
 }
 }catch(err){fail(err)}}
window.addEventListener('DOMContentLoaded',init);
