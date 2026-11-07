'use strict';
/* First usable application worklist: study permits only; NO IRCC PDF autofill. */
const pkgRoot=()=>q()+'/cases/'+encodeURIComponent(S.caseId)+'/package';
const reqRoot=()=>q()+'/cases/'+encodeURIComponent(S.caseId)+'/requirements';

async function renderPackage(){
 const pkg=await api(pkgRoot());
 S.activePackage=pkg;
 const requirements=pkg.initialized?await api(reqRoot()):null;
 S.activeRequirements=requirements;
 const prep=pkg.initialized?await api(q()+'/cases/'+encodeURIComponent(S.caseId)+'/form-preparation/preview'):null;
 S.activeFormPreparation=prep;
 const hasRepresentativeForm=pkg.initialized&&pkg.forms.some(form=>form.code==='IMM5476');
 const repPreview=hasRepresentativeForm?await api(
   q()+'/cases/'+encodeURIComponent(S.caseId)+'/ircc/IMM5476/preparation'):null;
 S.activeImm5476Preview=repPreview;
 if(!pkg.initialized){
  let intro='<div class="panel-body"><p>Start an application package by choosing the actual filing location. This selects the study permit form and connects the existing document checklist.</p><div class="warning-text">IMM 1294 and IMM 5709 are NOT auto-filled. Do not file an internal worksheet as an official IRCC document.</div>';
  intro+=btn('Start application package','pkg:create','primary')+'</div>';
  return panel('Application forms and required documents',intro);
 }
 let body='<div class="panel-body"><div class="callout"><strong>Filing route: '+h(pkg.filing_context.replaceAll('_',' '))+'</strong> · '+h(pkg.profile_version)+'</div>';
 body+='<div class="warning-text">This is the actual file-preparation checklist; it is not a completed IRCC application. A reviewed PDF copy is NOT proof of official form validation. Government submission is disabled.</div>';
 if(pkg.sources_need_recheck)body+='<p class="warning-text">One or more official sources need rechecking before continuing.</p>';
 body+='<h3>Forms to prepare and review</h3>';
 for(const form of pkg.forms){
   const copy=form.latest_copy;
   body+='<div class="item-row"><div class="bullet">▤</div><div style="flex:1;min-width:0">'+
     '<div class="item-title">'+h(form.code)+' — '+h(form.title)+'</div>'+
     '<div class="meta">Official revision: '+h(form.source_revision)+' · '+h(form.status.replaceAll('_',' '))+'</div>'+
     '<div class="meta"><a href="'+h(form.source_url)+'" rel="noopener noreferrer" target="_blank">IRCC instructions ↗</a> · '+form.copy_count+' retained copy/copies</div>'+
     (copy?'<div class="meta">Latest linked document: '+h(copy.document_id.slice(0,8))+' · Scan '+h(copy.scan_status)+' · Review '+h(copy.review_status)+'</div>':'')+
     '</div><div class="push">'+
     btn('Attach PDF copy','pkg:link:'+form.code,'smallbtn')+
     (copy&&copy.scan_status==='quarantined'?' '+btn('Rescan','pkg:scan:'+copy.id,'smallbtn'):'')+
     (copy&&copy.scan_status==='cleared'&&copy.review_status==='pending'?
       ' '+btn('Review copy','pkg:review:'+copy.id,'primary smallbtn'):'')+
     '</div></div>';
 }
 if(repPreview){
   body+='<h3>IMM 5476 · Representative appointment preparation</h3>';
   body+='<div class="callout"><strong>'+repPreview.verified_text_fields+' / '+repPreview.observed_text_fields+
     ' mapped text fields backed by verified evidence</strong> · Observed version '+h(repPreview.revision)+
     '. This covers only the paid-CICC appointment scenario; no government PDF is generated.</div>';
   body+='<details><summary>Inspect IMM 5476 mapped field evidence and gaps</summary>';
   for(const item of repPreview.fields){
     body+='<div class="item-row"><div style="flex:1;min-width:0"><strong>'+h(item.key.replaceAll('_',' '))+'</strong>'+
       '<div class="meta">'+h(item.status.replaceAll('_',' '))+
       (item.value?' · '+h(item.value):'')+'</div>'+
       '<div class="meta">'+h(item.canonical_path)+'</div></div>'+
       chip(item.status)+'</div>';
   }
   body+='</details>';
   body+='<p class="warning-text">Official autofill remains disabled. '+h(repPreview.blockers.length)+
     ' preparation or release blockers remain, including form-completeness, licence and signature review requirements.</p>';
 }
 body+='<h3>Verified form preparation · Internal fields only</h3>';
 body+='<div class="callout">'+h(prep.form_code)+' · '+h(prep.source_revision)+' · Source-linked internal preview. This is NOT a filled government PDF.</div>';
 for(const item of prep.fields){
   body+='<div class="item-row"><div style="flex:1"><strong>'+h(item.label)+'</strong> · '+h(item.canonical_path)+
     '<div class="meta">'+h(item.status.replaceAll('_',' '))+
     (item.value?' · '+h(item.value):'')+'</div></div>'+chip(item.status)+'</div>';
 }
 if(prep.blockers.length)body+='<p class="warning-text">Blocked: '+prep.blockers.map(x=>h(x.replaceAll('_',' '))).join(', ')+'</p>';
 body+=btn('Capture verified internal preparation packet','pkg:capture-preparation','smallbtn'+(prep.verified_subset_complete?'':' muted'));
 body+='<h3>Supporting evidence worklist</h3>';
 body+='<div class="callout">These are the existing, non-exhaustive document requirements for this study-permit route. Conditional items still require an RCIC applicability decision.</div>';
 for(const req of requirements.requirements){
   body+='<div class="item-row"><div style="flex:1"><div class="item-title">'+h(req.title)+'</div>'+
     '<div class="meta">'+h(req.guidance)+'</div>'+
     '<div class="meta"><a href="'+h(req.source_url)+'" target="_blank" rel="noopener noreferrer">Official IRCC guidance ↗</a></div></div>'+
     '<div class="push">'+chip(req.status)+
     (req.kind==='conditional_document'?btn('Applicability','pkg:applicability:'+req.key,'smallbtn'):'')+
     (req.kind!=='verified_facts'?btn('Review document','pkg:docreview:'+req.key,'smallbtn'):'')+
     '</div></div>';
 }
 body+='<p class="meta">Unresolved document requirements: '+requirements.unresolved_requirements.length+' · Open evidence issues: '+pkg.open_evidence_issue_count+'</p>';
 body+='<p class="meta">Applicability decisions and document reviews are recorded with source versions and reviewer audit history. Staff-reviewed does not mean IRCC-approved.</p>';
 body+='<div class="callout">Forms are staff-reviewed copies only: '+(pkg.all_selected_form_copies_staff_reviewed?'all selected copies reviewed.':'more form copies/reviews are needed.')+
   ' Official autofill, Adobe/barcode validity and submission are still NOT implemented.</div>';
 body+='</div>';
 return panel('Application package · '+pkg.filing_context.replaceAll('_',' '),body);
}

function pkgCreate(){
 modal('<h2>Start application package</h2><p>Study permits only. Confirm the route with current IRCC guidance. This filing context will be locked until a versioned change workflow is added.</p><form>'+
   selectField('filing_context','Filing route',[
     ['outside_canada','Outside Canada — IMM 1294'],
     ['inside_canada','Inside Canada — IMM 5709']])+
   '<label><input type="checkbox" name="representative" checked> Include IMM 5476 representative form in this case package</label>'+
   '<p class="meta">A representative form may apply differently by case and submission channel; verify with an RCIC.</p>'+
   actions('Create worklist')+'</form>',async f=>{
     const v=values(f);
     const include=f.querySelector('[name=representative]').checked;
     await api(pkgRoot(),{method:'POST',body:{
       filing_context:v.filing_context,include_representative_form:include}});
 });
}

function pkgLink(code){
 const pdfs=(S.data.docs||[]).filter(d=>d.mime_type==='application/pdf'&&d.filename.toLowerCase().endsWith('.pdf'));
 if(!pdfs.length){
  toast('Upload a fictional PDF from the Documents tab first.');
  S.tab='documents';return render();
 }
 const options=pdfs.map(d=>[d.id,d.filename+' ('+d.document_type+')']);
 modal('<h2>Attach a manually completed '+h(code)+' PDF copy</h2>'+
   '<p>Only select a PDF already uploaded to this same case. The system will scan it and create an immutable evidence record; it does NOT autofill or officially validate the PDF.</p><form>'+
   selectField('document_id','Existing PDF document',options)+
   actions('Link and scan document')+'</form>',async f=>{
     await api(pkgRoot()+'/forms/'+encodeURIComponent(code)+'/copies',{
       method:'POST',body:values(f)});
 });
}

function pkgReview(copyId){
 modal('<h2>Professional review of manual IRCC PDF copy</h2>'+
   '<p>First download the file from the Documents tab and personally verify the correct official revision, fields, signatures and any required Adobe/barcode validation. A staff attestation does not guarantee IRCC acceptance.</p><form>'+
   selectField('decision','Decision',[
     ['accept','Record as staff-reviewed copy'],['reject','Reject this document copy']])+
   '<div class="form-field"><label>Review findings</label><textarea rows="4" name="note" required minlength="25" maxlength="900"></textarea></div>'+
   '<label><input type="checkbox" name="source_checked" required> I checked the latest official IRCC source and applicable instructions.</label>'+
   '<label><input type="checkbox" name="pdf_checked" required> I inspected the PDF in the appropriate reader and reviewed its fields and signature requirements.</label>'+
   actions('Record human review')+'</form>',async f=>{
     const v=values(f);
     await api(pkgRoot()+'/copies/'+encodeURIComponent(copyId)+'/review',{
       method:'POST',body:{
         decision:v.decision,note:v.note,
         current_ircc_source_checked:f.querySelector('[name=source_checked]').checked,
         reviewed_pdf_in_appropriate_software:f.querySelector('[name=pdf_checked]').checked}});
 });
}

async function pkgAction(action){
 if(action==='pkg:create')return pkgCreate();
 if(action==='pkg:capture-preparation')return pkgCapturePreparation();
 const [,cmd,id]=action.split(':');
 if(cmd==='link')return pkgLink(id);
 if(cmd==='applicability')return pkgApplicability(id);
 if(cmd==='docreview')return pkgDocumentReview(id);
 if(cmd==='review')return pkgReview(id);
 if(cmd==='scan'){
   const r=await api(pkgRoot()+'/copies/'+encodeURIComponent(id)+'/scan',{method:'POST'});
   await render();return toast('Malware scan status: '+r.scan_status);
 }
}

function pkgApplicability(key){
 const requirement=S.activeRequirements?.requirements.find(x=>x.key===key);
 if(!requirement)return toast('Refresh the package');
 modal('<h2>Professional applicability review</h2><p>'+h(requirement.title)+'</p>'+
   '<p><a href="'+h(requirement.source_url)+'" target="_blank" rel="noopener noreferrer">Official source</a></p>'+
   '<p class="warning-text">An exemption requires individual circumstances and current IRCC instructions. This record is not legal eligibility approval.</p><form>'+
   selectField('decision','Applicability',[['required','Required for this case'],['not_applicable','Not applicable — reason required']])+
   '<div class="form-field"><label>Substantive reasoning</label><textarea name="reason" rows="4" required minlength="25" maxlength="900"></textarea></div>'+
   '<label><input type="checkbox" name="source_checked" required> I independently checked the current official source and the circumstances of this case.</label>'+
   actions('Record applicability review')+'</form>',async form=>{
     const v=values(form);
     await api(reqRoot()+'/'+encodeURIComponent(key)+'/applicability',{
       method:'POST',body:{decision:v.decision,reason:v.reason,
         confirmed_current_source:form.querySelector('[name=source_checked]').checked,
         expected_revision:requirement.applicability_revision}});
   });
}
function pkgDocumentReview(key){
 const req=S.activeRequirements?.requirements.find(x=>x.key===key);
 if(!req)return toast('Refresh the worklist');
 const allowed=new Set(req.document_types||[]);
 const docs=(S.data.docs||[]).filter(doc=>allowed.has(doc.document_type)&&
   !req.reviewed_document_ids.includes(doc.id)&&!req.rejected_document_ids.includes(doc.id));
 if(!docs.length)return toast('Upload an unreviewed document of the matching type in the Documents tab first.');
 modal('<h2>Document review · '+h(req.title)+'</h2>'+
   '<p>Check the original file, its identity, completeness, expiry and applicability. An accepted document is NOT proof of IRCC acceptance.</p><form>'+
   selectField('document_id','Existing document',docs.map(doc=>[doc.id,doc.filename+' ('+doc.document_type+')']))+
   selectField('decision','Decision',[['accepted','Accept for staff case worklist'],['rejected','Reject document']])+
   '<div class="form-field"><label>Review notes</label><textarea name="reason" rows="4" required minlength="25" maxlength="900"></textarea></div>'+
   '<label><input type="checkbox" name="inspected" required> I inspected the source document personally.</label>'+
   actions('Record document review')+'</form>',async form=>{
     const v=values(form);
     await api(reqRoot()+'/'+encodeURIComponent(key)+'/documents/review',{
       method:'POST',body:{document_id:v.document_id,decision:v.decision,
         reason:v.reason,inspected_original_document:form.querySelector('[name=inspected]').checked}});
   });
}

async function pkgCapturePreparation(){
 const preview=S.activeFormPreparation;
 if(!preview?.verified_subset_complete)return toast('Resolve case evidence and form-preview blockers first.');
 modal('<h2>Capture an internal preparation snapshot</h2><p>This captures only a small set of source-linked canonical fields. It does NOT generate, validate, sign, barcode or submit an IRCC form.</p><form>'+
   '<label><input type="checkbox" name="acknowledge" required> I understand this is not an official IRCC form.</label>'+
   actions('Capture internal packet')+'</form>',async form=>{
     const response=await api(q()+'/cases/'+encodeURIComponent(S.caseId)+'/form-preparation/packets',{
       method:'POST',body:{expected_sha256:preview.snapshot_sha256,
          acknowledge_internal_subset_only:form.querySelector('[name=acknowledge]').checked}});
     toast('Internal packet captured: '+response.id.slice(0,8));
   });
}
