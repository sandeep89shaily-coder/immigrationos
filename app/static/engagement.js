'use strict';
/* RCIC s24 agreement workflow; fictional data, not a legally verified contract. */
const egRoot=()=>q()+'/engagements';
const egPath=()=>egRoot()+'/clients/'+encodeURIComponent(S.engagementClientId);

async function renderEngagement(){
 const [client,status,headings,matters]=await Promise.all([
   api(q()+'/clients/'+encodeURIComponent(S.engagementClientId)),
   api(egPath()),api(egRoot()+'/s24/clauses'),api(egPath()+'/matters')
 ]);
 S.egStatus=status;S.egHeadings=headings;
 const screen=status.screen,draft=status.draft,proof=status.signed_copy;
 let buttons=btn('← Client directory','eg:back','smallbtn')+' '+btn('New conflict screen','eg:screen','primary smallbtn');
 buttons+=' '+btn('Review agreement history','eg:history','smallbtn');
 if(screen&&screen.clear_for_drafting)buttons+=' '+btn('Draft service agreement','eg:draft','smallbtn');
 let profile='<div class="panel-body">'+keyValue('Client',client.first_name+' '+client.last_name)+
   keyValue('Contact',client.email||client.phone||'Not provided')+
   keyValue('Prior representative',screen?screen.prior_rep:'Not screened')+
   keyValue('Conflict review',screen?screen.conflict_status:'Not screened')+
   keyValue('Reviewer',screen?screen.reviewer_sub:'—')+
   '<div class="callout">'+(screen&&screen.clear_for_drafting?
   'Staff screen recorded as clear. This is not an independent legal determination.':
   'HOLD: identity, previous representation and professional conflict review are required.')+
   '</div></div>';
 let draftBody='<div class="panel-body"><div class="callout">All 26 Code s24 headings need professional, client-specific terms. This is not an approved legal contract.</div>';
 if(draft){
   draftBody+='<p>Draft version '+draft.version+' · SHA-256 '+h(draft.sha256.slice(0,18))+'…'+
     (draft.uses_current_screen?'':' · STALE CONFLICT SCREEN')+'</p>';
   draftBody+=btn('Download printable unsigned terms','eg:print','smallbtn');
   if(!proof)draftBody+=' '+btn('Upload signed PDF','eg:upload','smallbtn');
   else{
     draftBody+='<p>Malware scan: '+h(proof.scan_status)+' · Staff review: '+h(proof.review_status)+'</p>';
     if(proof.scan_status==='quarantined')draftBody+=btn('Rescan','eg:scan','smallbtn');
     if(proof.scan_status==='cleared'){
       draftBody+=btn('Download scanned copy','eg:download','smallbtn');
       if(proof.review_status==='pending')draftBody+=' '+btn('Review signed copy','eg:review','primary smallbtn');
     }
   }
 }else draftBody+='<p>No unsigned service agreement draft yet.</p>';
 draftBody+='</div>';
 let caseBody='<div class="panel-body"><div class="callout">Engagement-gated matters link one client, signed agreement revision and active staff professional. Other legacy draft-case creation remains outside this gate.</div>';
 if(status.eligible_for_engagement_gated_case_creation)caseBody+=btn('Open assigned matter','eg:open','primary smallbtn');
 else caseBody+='<p>Blocked until the current conflict screen, latest agreement, scan and professional review are cleared.</p>';
 for(const matter of matters){
   caseBody+='<div class="item-row"><div><strong>Case '+h(matter.case_id.slice(0,8))+'</strong>'+
     '<div class="meta">Assigned to '+h(matter.professional_sub)+'</div></div>'+
     btn('Open case','eg:case:'+matter.case_id,'smallbtn')+'</div>';
 }
 caseBody+='</div>';
 $('mainContent').innerHTML=page('Engagement · '+client.first_name+' '+client.last_name,
   'CICC service agreement and supervised case assignment; synthetic data only.',buttons)+
   '<div class="two-col">'+panel('Identity and conflict screen',profile)+
   panel('Written service agreement',draftBody)+'</div>'+
   panel('Supervised matters',caseBody);
}

function egScreen(){
 modal('<h2>New professional conflict review</h2><p>Do not assume that a conflict can be resolved by client consent. Concurrent representation and unresolved conflicts block the release gate.</p><form>'+
   selectField('prior_rep','Prior representation',[
     ['unknown','Unknown / unchecked'],['none','No prior representative'],
     ['ended_in_writing','Ended in writing with supporting review'],
     ['concurrent','Current concurrent representation']])+
   selectField('conflict_status','Conflict status',[
     ['unresolved','Not resolved'],['none_identified','No conflict identified after review'],
     ['potential','Potential conflict'],['prohibited','Prohibited conflict']])+
   '<label><input type="checkbox" name="client_identity_verified" required> I verified client identity and contact information.</label>'+
   '<label><input type="checkbox" name="previous_rep_checked" required> I checked the previous-representative arrangements.</label>'+
   '<div class="form-field"><label>Screening findings and evidence</label><textarea name="details" rows="4" minlength="25" maxlength="1200" required></textarea></div>'+
   '<label><input type="checkbox" name="independently_reviewed_conflicts" required> I personally reviewed the current conflict requirements.</label>'+
   actions('Record immutable screen')+'</form>',async f=>{
     const body=values(f);
     for(const k of ['client_identity_verified','previous_rep_checked','independently_reviewed_conflicts'])body[k]=f.querySelector('[name="'+k+'"]').checked;
     await api(egPath()+'/screens',{method:'POST',body});
 });
}

function egDraft(){
 const headings=S.egHeadings.items;
 const fields=headings.map(c=>'<div class="form-field"><label>'+h(c.key.slice(0,1).toUpperCase())+
   '. '+h(c.label)+'</label><textarea name="'+h(c.key)+'" rows="3" minlength="3" maxlength="1500" required></textarea></div>').join('');
 modal('<h2>Code s24 — client-specific service agreement</h2><p>Fill all 26 required headings. Do not use these fields as an automatically approved legal template.</p><form>'+
   fields+'<label><input name="reviewed" type="checkbox" required> I independently checked the current Code, scope and contract requirements.</label>'+
   actions('Save unsigned revision')+'</form>',async f=>{
     const data=new FormData(f);
     const clauses=Object.fromEntries(headings.map(c=>[c.key,data.get(c.key)]));
     await api(egPath()+'/drafts',{method:'POST',body:{
       clauses,professional_checked_current_code:f.querySelector('[name="reviewed"]').checked}});
 });
}

function egUpload(){
 const d=S.egStatus.draft;
 modal('<h2>Record signed service agreement</h2><p>Fictional PDF only. Client must first receive the draft and later the signed copy; timestamps are staff-entered evidence, not proof of electronic delivery.</p><form>'+
   fld('draft_provided_at','Draft provided to client','datetime-local','required')+
   fld('signed_at','Agreement signed','datetime-local','required')+
   fld('client_copy_provided_at','Signed copy provided to client','datetime-local','required')+
   fld('file','Signed PDF','file','required accept=".pdf"')+
   actions('Upload signed PDF')+'</form>',async f=>{
     const data=new FormData(f);
     for(const name of ['draft_provided_at','signed_at','client_copy_provided_at'])
       data.set(name,new Date(data.get(name)).toISOString());
     await api(egPath()+'/drafts/'+d.id+'/signed-copy',{method:'POST',body:data});
 });
}

function egReview(){
 const d=S.egStatus.draft;
 modal('<h2>Staff signed-copy review</h2><p>Download the cleared signed copy before reviewing. Check actual signatures, matching clauses and client delivery. Licence and signature authenticity are NOT independently validated.</p><form>'+
   selectField('decision','Review outcome',[['accept','Accept after manual review'],['reject','Reject']])+
   '<div class="form-field"><label>Substantive review note</label><textarea name="note" rows="4" minlength="25" maxlength="1000" required></textarea></div>'+
   '<label><input type="checkbox" name="confirmed" required> I personally checked signed terms and client-copy delivery.</label>'+
   actions('Record staff signoff')+'</form>',async f=>{
     const v=values(f);
     await api(egPath()+'/drafts/'+d.id+'/review',{method:'POST',body:{
       decision:v.decision,note:v.note,
       reviewer_confirmed_signed_terms_and_delivery:f.querySelector('[name="confirmed"]').checked}});
 });
}

function egOpen(){
 const sub=S.egStatus.screen?S.egStatus.screen.reviewer_sub:'';
 modal('<h2>Open supervised matter</h2><p>The assignee must have an active firm role. This does not verify the person is currently CICC licensed.</p><form>'+
   selectField('application_type','Application program',[
     ['work_permit','Work permit'],['study_permit','Study permit'],['visitor','Visitor'],
     ['permanent_residence','Permanent residence'],['sponsorship','Sponsorship'],['citizenship','Citizenship']])+
   fld('title','Matter description','text','required minlength="4" maxlength="160"')+
   fld('professional_sub','Assigned professional identity subject','text',
       'required minlength="3" value="'+h(sub)+'"')+
   '<label><input name="confirmed" type="checkbox" required> I reviewed engagement status and the professional assignment.</label>'+
   actions('Create supervised draft case')+'</form>',async f=>{
     const body=values(f);
     body.confirm_engagement_and_professional_assignment=f.querySelector('[name="confirmed"]').checked;
     const opened=await api(egPath()+'/open-matter',{method:'POST',body});
     S.caseId=opened.case_id;S.engagementClientId=null;S.tab='overview';S.view='cases';
 });
}

async function egDownload(which){
 const d=S.egStatus.draft;
 const res=await api(egPath()+'/drafts/'+d.id+
   (which==='print'?'/print':'/signed-copy'),{raw:true});
 const blob=await res.blob(), url=URL.createObjectURL(blob);
 const a=document.createElement('a');a.href=url;
 a.download=which==='print'?'UNSIGNED-service-agreement-draft.html':'signed-service-agreement.pdf';
 document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),2000);
}

async function egAction(action){
 if(action==='eg:back'){S.engagementClientId=null;S.view='clients';return render()}
 if(action==='eg:screen')return egScreen();
 if(action==='eg:history'){const history=await api(egPath()+'/history');let body='<h2>Immutable service agreement history</h2><p>Prior agreement versions are preserved. A newer revision or conflict screen requires independent professional reconciliation; this view does not decide legal validity.</p>';body+='<h3>Contract versions</h3><div class=panel-body>'+history.drafts.map(x=>'<div class=item-row><div><strong>Version '+x.version+'</strong> '+(x.currently_latest?'CURRENT DRAFT':'HISTORICAL')+'<div class=meta>SHA-256 '+h(x.sha256.slice(0,20))+'… · '+h(x.screen_still_latest?'Current screening':'OLD SCREEN')+'</div><div class=meta>Signed-copy: '+h(x.signed_copy.review_status||'Not received')+' · '+h(x.signed_copy.scan_status||'Not scanned')+'</div></div></div>').join('')+'</div>';body+='<h3>Conflict screen history</h3><div class=panel-body>'+history.screens.map(x=>'<div class=item-row><div><strong>'+h(x.conflict_status)+'</strong> · '+h(x.prior_rep)+'<div class=meta>'+h(x.reviewer_sub)+' · '+d(x.created_at)+' · '+h(x.currently_latest?'Current':'Superseded')+'</div></div></div>').join('')+'</div>';return modal(body,()=>{})}
 if(action==='eg:draft')return egDraft();
 if(action==='eg:upload')return egUpload();
 if(action==='eg:review')return egReview();
 if(action==='eg:open')return egOpen();
 if(action==='eg:print')return egDownload('print');
 if(action==='eg:download')return egDownload('signed');
 if(action==='eg:scan'){
   const d=S.egStatus.draft;
   const res=await api(egPath()+'/drafts/'+d.id+'/scan',{method:'POST'});
   await render();return toast('Scan: '+res.scan_status);
 }
 if(action.startsWith('eg:case:')){
   S.caseId=action.split(':')[2];S.engagementClientId=null;S.view='cases';S.tab='overview';
   return render();
 }
}
