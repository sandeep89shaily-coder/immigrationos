'use strict';
/* Consultant CRM vertical slice. Development/synthetic records only. Uses existing OIDC API. */
const crmBase=()=>q()+'/crm/prospects';
const crmPath=()=>crmBase()+'/'+encodeURIComponent(S.prospectId);

async function renderCRM(){
 if(!S.prospectId){
   const leads=await api(crmBase());
   const rows=leads.map(p=>`<tr class=clickable data-prospect='${h(p.id)}'><td><strong>${h(p.first_name)} ${h(p.last_name)}</strong></td><td>${h(p.email||p.phone||'—')}</td><td>${chip(p.stage)}</td><td>${h(p.source)}</td><td>${d(p.created_at)}</td><td>→</td></tr>`);
   $('mainContent').innerHTML=page('Prospects & consultations','From fictional first enquiry to a governed consultation and client record.',btn('+ New prospect','crm:new','primary'))+panel('Prospect pipeline',table(['Prospect','Contact','Stage','Source','Created',''],rows));
   return;
 }
 const [p,activities,consultations]=await Promise.all([api(crmPath()),api(crmPath()+'/activities'),api(crmPath()+'/consultations')]);
 const consultation=consultations.find(x=>x.status==='scheduled')||consultations[0]||null;
 const agreements=consultation?await api(crmPath()+'/consultations/'+consultation.id+'/agreements'):[];
 const current=agreements[0]||null,proof=current?.signed_copy||null;
 S.crmConsultation=consultation; S.crmAgreement=current; S.crmProof=proof;
 let actions=btn('← Prospects','crm:back','smallbtn');
 if(['new','contacted'].includes(p.stage))actions+=' '+btn('Record activity','crm:activity','smallbtn');
 if(!consultations.some(c=>c.status==='scheduled')&&!['converted','closed'].includes(p.stage))actions+=' '+btn('Schedule consultation','crm:schedule','primary smallbtn');
 if(!consultations.some(c=>c.status==='scheduled')&&!['converted','closed'].includes(p.stage))actions+=' '+btn('Close prospect','crm:close','smallbtn');
 const summary=panel('Prospect record',`<div class=panel-body>${keyValue('Name',p.first_name+' '+p.last_name)}${keyValue('Contact',p.email||p.phone)}${keyValue('Source',p.source)}${keyValue('Stage',p.stage)}${keyValue('Marketing/outreach consent',p.outreach_consent?'Recorded ('+(p.consent_source||'')+')':'Not recorded')}</div>`);
 const history=panel('Recorded interactions',`<div class=panel-body><div class=callout>These are internal records only. No email, SMS or WhatsApp is sent by this module.</div>${activities.length?activities.map(a=>`<div class=item-row><div class=bullet>≡</div><div><div class=item-title>${h(a.kind)} · ${d(a.created_at)}</div><div class=meta>${h(a.content)}</div></div></div>`).join(''):empty('No activity yet','Record an initial contact or note.')}</div>`);
 let appointment=empty('No consultation booked','Schedule a consultation before drafting its written agreement.');
 if(consultation){
   let body=`<div class=panel-body>${keyValue('Date',d(consultation.starts_at))}${keyValue('Professional',consultation.professional_sub)}${keyValue('Status',consultation.status)}`;
   if(consultation.status==='scheduled'){
     body+=btn('Cancel appointment','crm:cancel','smallbtn');
     body+='<div class=callout>The CICC Code generally requires a signed written consultation agreement before an initial regulated consultation. This system does not verify RCIC credentials or electronic signatures.</div>';
     if(!current)body+=btn('Prepare consultation agreement','crm:agreement','primary smallbtn');
     else{
       body+=`<p><strong>Written terms version ${current.version}</strong> · SHA-256 ${h(current.terms_sha256.slice(0,16))}…</p>`;
       body+=btn('Download printable terms','crm:draft','smallbtn');
       if(!proof)body+=' '+btn('Upload signed PDF and delivery evidence','crm:upload','primary smallbtn');
       else {
         body+=`<p>Signed PDF: ${chip(proof.scan_status)} · Review: ${chip(proof.review_status)}</p>`;
         if(proof.scan_status==='quarantined')body+=btn('Rescan signed PDF','crm:scan','smallbtn');
         if(proof.scan_status==='cleared'){
           body+=btn('Download signed copy for review','crm:signed','smallbtn');
           if(proof.review_status==='pending')body+=' '+btn('Review signed copy','crm:review','primary smallbtn');
           if(proof.review_status==='accepted')body+=' '+btn('Complete consultation','crm:complete','primary smallbtn');
         }
         if(proof.review_status==='rejected')body+='<div class=warning-text>Rejected signed proof. A new consultation/terms process is required.</div>';
       }
     }
   }
   body+='</div>';
   appointment=panel('Consultation · '+d(consultation.starts_at),body);
 }
 if(p.stage==='consulted')appointment+=panel('Client conversion','<div class=panel-body><p>Consultation terms have been manually reviewed. Further immigration advice requires a separate written service agreement and related checks.</p>'+btn('Convert to client record','crm:convert','primary smallbtn')+'</div>');
 if(p.stage==='converted')appointment+=panel('Client conversion',`<div class=panel-body>${keyValue('Client ID',p.converted_client_id)}<div class=callout>Conversion does not authorize further consulting or IRCC submission. A separate service agreement remains outstanding.</div></div>`);
 $('mainContent').innerHTML=page('Prospect · '+p.first_name+' '+p.last_name,'Controlled consultation and signed-copy review, using fictional records only.',actions)+`<div class=two-col>${summary}${history}</div>`+appointment;
}

function crmNewProspect(){
 const inner=`<h2>New prospect</h2><p>Development-only; do not add real client information.</p><form>${fld('first_name','Given name','text','required maxlength="100"')}${fld('last_name','Family name','text','required maxlength="100"')}${fld('email','Email','email','maxlength="254"')}${fld('phone','Telephone','text','maxlength="40"')}${selectField('source','Lead source',[['referral','Referral'],['web','Website'],['phone','Phone'],['email','Email'],['other','Other']])}<label><input type=checkbox name=outreach_consent> Outreach consent recorded</label>${fld('consent_source','Consent source (if recorded)','text','maxlength="200"')}${actions('Create prospect')}</form>`;
 modal(inner,async form=>{const payload=values(form);payload.outreach_consent=form.querySelector('[name=outreach_consent]').checked;const created=await api(crmBase(),{method:'POST',body:payload});S.prospectId=created.id;S.view='crm'});
}

function crmActivity(){
 modal(`<h2>Record prospect interaction</h2><p>Manual record only; no actual message will be sent.</p><form>${selectField('kind','Type',[['call','Call'],['email','Email (record only)'],['meeting','Meeting'],['note','Internal note']])}<div class=form-field><label>Details</label><textarea name=content rows=4 minlength=5 maxlength=1200 required></textarea></div>${actions('Record interaction')}</form>`,async f=>{await api(crmPath()+'/activities',{method:'POST',body:values(f)})});
}

function crmSchedule(){
 modal(`<h2>Schedule consultation</h2><p>Dates are stored with explicit timezone; consultation agreements must be signed before regulated consultation.</p><form>${fld('starts_at','Start (your local time)','datetime-local','required')}${fld('ends_at','End (your local time)','datetime-local','required')}${actions('Schedule consultation')}</form>`,async f=>{const v=values(f);await api(crmPath()+'/consultations',{method:'POST',body:{starts_at:new Date(v.starts_at).toISOString(),ends_at:new Date(v.ends_at).toISOString()}})});
}

function crmAgreement(){
 const c=S.crmConsultation; if(!c)return toast('Schedule consultation first');
 const inner=`<h2>Draft written consultation agreement</h2><p>Verify all statutory content and RCIC details independently. This generates printable DRAFT terms, not a signature or regulatory approval.</p><form>${fld('licensee_name','RCIC full name','text','required minlength="3"')}${fld('licensee_registration_number','Registration number','text','required minlength="3"')}${fld('licensee_address','RCIC mailing address','text','required minlength="10"')}${fld('licensee_phone','RCIC telephone','text','required minlength="7"')}${fld('licensee_email','RCIC email','email','required')}${fld('client_address','Potential client mailing address','text','required minlength="10"')}<div class=form-field><label>Purpose and scope</label><textarea name=purpose_scope rows=3 required minlength=20 maxlength=900></textarea></div><div class=form-field><label>College regulator description</label><textarea name=regulator_description rows=2 required minlength=25 maxlength=500>The College of Immigration and Citizenship Consultants is the statutory regulator responsible for oversight of its licensees.</textarea></div>${selectField('pro_bono','Fee arrangement',[['true','Pro bono (no consultation fee)'],['false','Paid consultation']])}${fld('fee_cents_cad','Consultation fee (CAD cents, enter 0 if pro bono)','number','required min="0" value="0"')}${actions('Save immutable draft')}</form>`;
 modal(inner,async f=>{const v=values(f);v.pro_bono=v.pro_bono==='true';v.fee_cents_cad=Number(v.fee_cents_cad);await api(crmPath()+'/consultations/'+c.id+'/agreements',{method:'POST',body:v})});
}

function crmUpload(){
 const c=S.crmConsultation,a=S.crmAgreement;if(!c||!a)return toast('Create written terms first');
 const inner=`<h2>Record signed PDF and client-copy delivery</h2><div class=warning-text>Fictional data only. Keep a copy of the signed document and verify client delivery. Uploads remain quarantined until the malware scanner clears them.</div><form>${fld('signed_at','Date and time signed','datetime-local','required')}${fld('client_copy_provided_at','Date and time copy sent to client','datetime-local','required')}${fld('file','Signed PDF test document','file','required accept=".pdf"')}${actions('Upload signed copy')}</form>`;
 modal(inner,async f=>{const form=new FormData(f);form.set('signed_at',new Date(form.get('signed_at')).toISOString());form.set('client_copy_provided_at',new Date(form.get('client_copy_provided_at')).toISOString());await api(crmPath()+'/consultations/'+c.id+'/agreements/'+a.id+'/signed-copy',{method:'POST',body:form})});
}

function crmReview(){
 const c=S.crmConsultation,a=S.crmAgreement;
 modal(`<h2>Review signed consultation agreement</h2><p>Download the scan-cleared PDF first. Check the signature, contents, client-copy delivery and professional obligations independently.</p><form>${selectField('decision','Decision',[['accept','Accept after manual inspection'],['reject','Reject signed evidence']])}<div class=form-field><label>Review rationale</label><textarea name=review_note minlength=20 maxlength=800 required rows=3></textarea></div><label><input name=attested type=checkbox required> I personally reviewed the signed content and verified that the client received a copy.</label>${actions('Record decision')}</form>`,async f=>{const v=values(f);await api(crmPath()+'/consultations/'+c.id+'/agreements/'+a.id+'/review',{method:'POST',body:{decision:v.decision,review_note:v.review_note,reviewer_attests_signed_agreement_and_client_copy:f.querySelector('[name=attested]').checked}})});
}

async function crmDownload(which){
 const c=S.crmConsultation,a=S.crmAgreement;if(!c||!a)return;
 const suffix=which==='draft'?'/draft':'/signed-copy';
 const res=await api(crmPath()+'/consultations/'+c.id+'/agreements/'+a.id+suffix,{raw:true});
 const blob=await res.blob();const u=URL.createObjectURL(blob);const link=document.createElement('a');link.href=u;link.download=which==='draft'?'consultation-agreement-DRAFT.html':'signed-consultation-copy.pdf';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(u),2000);
}

async function crmAction(action){
 if(action==='crm:back'){S.prospectId=null;return render()}
 if(action==='crm:new')return crmNewProspect();
 if(action==='crm:activity')return crmActivity();
 if(action==='crm:close')return modal('<h2>Close prospect</h2><p>Keep the historical contact record. This does not delete prospect information.</p><form><div class=form-field><label>Reason</label><textarea name=reason rows=3 required minlength=5 maxlength=500></textarea></div>'+actions('Close prospect')+'</form>',async f=>{await api(crmPath()+'/close',{method:'POST',body:values(f)})});

 if(action==='crm:schedule')return crmSchedule();
 if(action==='crm:agreement')return crmAgreement();
 if(action==='crm:upload')return crmUpload();
 if(action==='crm:review')return crmReview();
 if(action==='crm:draft')return crmDownload('draft');
 if(action==='crm:signed')return crmDownload('signed');
 const c=S.crmConsultation,a=S.crmAgreement;
 if(action==='crm:cancel'){if(!confirm('Cancel the scheduled consultation?'))return;await api(crmPath()+'/consultations/'+c.id+'/cancel',{method:'POST'});await render();return toast('Consultation cancelled')}
 if(action==='crm:scan'){const r=await api(crmPath()+'/consultations/'+c.id+'/agreements/'+a.id+'/scan',{method:'POST'});await render();return toast('Scan status: '+r.scan_status)}
 if(action==='crm:complete'){if(!confirm('Record consultation as complete after reviewing the signed agreement?'))return;await api(crmPath()+'/consultations/'+c.id+'/complete',{method:'POST'});await render();return toast('Consultation recorded as completed')}
 if(action==='crm:convert'){if(!confirm('Convert this fictional prospect to a client? Further consulting needs a separate service agreement.'))return;const r=await api(crmPath()+'/convert',{method:'POST'});await render();return toast('Client record linked: '+r.client_id.slice(0,8))}
}
