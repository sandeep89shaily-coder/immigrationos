'use strict';
// Client master record and case-specific INTERNAL answer drafts, never official PDF output.
const applicantRoot=id=>q()+'/clients/'+encodeURIComponent(id)+'/applicant';

async function renderApplicantCase(clientId){
 const [master,drafts,histories,evidence]=await Promise.all([
   api(applicantRoot(clientId)),api(q()+'/cases/'+encodeURIComponent(S.caseId)+'/answer-drafts'),
   api(q()+'/clients/'+encodeURIComponent(clientId)+'/histories'),
   api(q()+'/cases/'+encodeURIComponent(S.caseId)+'/history-evidence-review')]);
 S.applicantClientId=clientId;
 S.applicantMaster=master;
 S.applicantHistories=histories.records;
 let html='<div class="panel-body"><div class="warning-text">Development-only fictional data. Profile entries are not evidence verified and cannot be used as official IRCC form PDFs.</div>';
 const identity=master.profile?.identity||{};
 html+='<h3>Reusable applicant identity</h3>';
 for(const [name,key] of [['Given name','given_name'],['Family name','family_name'],
  ['Date of birth','date_of_birth'],['Citizenship','citizenship'],
  ['Passport number','passport_number'],['Passport expiry','passport_expiry'],
  ['Country of birth','country_of_birth']]){
   html+=keyValue(name,identity[key]);
 }
 html+='<p class="meta">Profile version: '+(master.profile?.version||'Not created')+'</p>';
 html+=btn('Edit identity profile','applicant:edit','primary smallbtn');
 html+='<h3>Family members</h3>';
 for(const person of master.family){
  html+='<div class="item-row"><div style="flex:1"><strong>'+h(person.given_name)+' '+h(person.family_name)+'</strong><div class="meta">'+h(person.relationship)+' · '+h(person.date_of_birth||'No DOB')+'</div></div>'+
    btn('Edit','applicant:family-edit:'+person.id,'smallbtn')+'</div>';
 }
 html+=btn('Add family member','applicant:family-add','smallbtn');
 html+='<h3>Address, education, employment and travel history</h3>';
 html+='<div class="callout">History entries are self-reported. Evidence checks do not verify a complete travel or residence timeline.</div>';
 for(const kind of ['address','education','employment','travel']){
  const entries=histories.records.filter(row=>row.kind===kind);
  html+='<h4>'+h(kind.charAt(0).toUpperCase()+kind.slice(1))+' ('+entries.length+')</h4>';
  for(const entry of entries){
   const summary=Object.entries(entry.details).filter(([key])=>!['start_date','end_date'].includes(key)).map(([key,val])=>h(key.replaceAll('_',' '))+': '+h(val)).join(' · ');
   const review=evidence.records.find(row=>row.record_id===entry.id);
   const discrepancies=(review?.fields||[]).filter(field=>field.status==='conflict_requires_review').length;
   html+='<div class="item-row"><div style="flex:1"><div class="item-title">'+h(entry.details.start_date)+' – '+h(entry.details.end_date||'present / not recorded')+'</div><div class="meta">'+summary+'</div><div class="meta">'+(discrepancies?discrepancies+' evidence discrepancy/discrepancies':'Not independently evidence-verified')+'</div></div>'+btn('Edit','applicant:history-edit:'+entry.id,'smallbtn')+'</div>';
  }
  html+=btn('Add '+kind,'applicant:history-add:'+kind,'smallbtn');
 }
 html+='<h3>Case-specific answer snapshots</h3><p class="meta">These snapshots preserve the source profile version. Every answer remains unverified until separately supported by source evidence and checked by staff.</p>';
 html+=btn('Create internal form-answer draft','applicant:draft','smallbtn');
 for(const draft of drafts){
   html+='<div class="item-row"><div style="flex:1"><strong>'+h(draft.form_code)+'</strong> · Profile version '+draft.profile_version+
   '<div class="meta">'+d(draft.created_at)+' · '+h(draft.status)+' · Missing fields: '+draft.unresolved_fields.length+'</div>'+
   '<div class="meta">'+Object.entries(draft.answers).map(([key,val])=>h(key)+': '+h(val)).join(' · ')+'</div></div></div>';
 }
 html+='</div>';
 return panel('Applicant and family · Internal answer drafts',html);
}

function applicantEdit(){
 const master=S.applicantMaster, current=master.profile?.identity||{};
 const fields=[['given_name','Given name','text'],['family_name','Family name','text'],
  ['date_of_birth','Date of birth','date'],['citizenship','Citizenship','text'],
  ['passport_number','Passport number','text'],['passport_expiry','Passport expiry','date'],
  ['country_of_birth','Country of birth','text']];
 const controls=fields.map(([key,label,type])=>fld(key,label,type,
  'value="'+h(current[key]||'')+'"')).join('');
 modal('<h2>Edit reusable applicant identity</h2><p>Only fictional records. Saving this profile does not verify evidence or update prior case snapshots.</p><form>'+
   controls+actions('Save profile')+'</form>',async form=>{
     const identity={};
     for(const [key] of fields){
       const value=form.elements.namedItem(key).value.trim();
       if(value)identity[key]=value;
     }
     const body={identity};
     if(master.profile)body.expected_version=master.profile.version;
     await api(applicantRoot(S.applicantClientId),{method:'PUT',body});
   });
}

function applicantFamily(existing){
 const fields='<div class="form-field"><label>Relationship</label><select name="relationship">'+
  ['spouse','common_law_partner','child','parent','sibling','other'].map(x=>'<option value="'+x+'"'+
  (existing?.relationship===x?' selected':'')+'>'+x.replaceAll('_',' ')+'</option>').join('')+
  '</select></div>'+fld('given_name','Given name','text','required maxlength="100" value="'+h(existing?.given_name||'')+'"')+
  fld('family_name','Family name','text','required maxlength="100" value="'+h(existing?.family_name||'')+'"')+
  fld('date_of_birth','Date of birth','date','value="'+h(existing?.date_of_birth||'')+'"')+
  fld('citizenship','Citizenship','text','maxlength="100" value="'+h(existing?.citizenship||'')+'"');
 modal('<h2>'+ (existing?'Edit':'Add') +' family member</h2><p>Fictional data only. All changes are attributed and version checked.</p><form>'+
   fields+actions(existing?'Save changes':'Add member')+'</form>',async form=>{
      const value=values(form);
      if(!value.date_of_birth)delete value.date_of_birth;
      if(!value.citizenship)delete value.citizenship;
      if(existing)value.expected_version=existing.version;
      await api(q()+'/clients/'+encodeURIComponent(S.applicantClientId)+'/family'+
        (existing?'/'+encodeURIComponent(existing.id):''),{
          method:existing?'PUT':'POST',body:value});
   });
}

async function applicantAction(action){
 if(action==='applicant:edit')return applicantEdit();
 if(action==='applicant:family-add')return applicantFamily(null);
 if(action.startsWith('applicant:family-edit:')){
   const id=action.split(':')[2];
   const person=S.applicantMaster?.family.find(row=>row.id===id);
   if(!person)return toast('Refresh the profile before editing');
   return applicantFamily(person);
 }
 if(action.startsWith('applicant:history-add:'))return applicantHistoryEditor(action.split(':')[2],null);
 if(action.startsWith('applicant:history-edit:')){
  const existing=S.applicantHistories?.find(row=>row.id===action.split(':')[2]);
  if(!existing)return toast('Reload this profile');
  return applicantHistoryEditor(existing.kind,existing);
 }
 if(action==='applicant:draft'){
   if(!confirm('Create a new immutable INTERNAL answer snapshot? This does not create an official PDF.'))return;
   await api(q()+'/cases/'+encodeURIComponent(S.caseId)+'/answer-drafts',{method:'POST'});
   await render();return toast('Internal answer draft recorded');
 }
}

const applicantHistoryFields={
 address:[['line1','Street address'],['line2','Line 2'],['city','City'],['region','Province / region'],['country','Country'],['postal_code','Postal code']],
 education:[['institution','Institution'],['country','Country'],['program','Program'],['credential','Credential']],
 employment:[['employer','Employer'],['position','Position'],['country','Country'],['city','City'],['employment_status','Status']],
 travel:[['destination_country','Destination country'],['purpose','Purpose'],['origin_country','Origin country']]
};
const applicantHistoryRequired={
 address:['line1','city','country'],
 education:['institution','country','program'],
 employment:['employer','position','country','employment_status'],
 travel:['destination_country','purpose']
};
function applicantHistoryEditor(kind,existing){
 const fields=applicantHistoryFields[kind];
 if(!fields)return toast('Unsupported history category');
 const data=existing?.details||{};
 let html='<h2>'+h(existing?'Edit':'Add')+' '+h(kind)+' record</h2>'+
   '<p>Fictional data only. A missing end date means no end date was supplied, not automatically ongoing activity.</p><form>'+
   fld('start_date','Start date','date','required value="'+h(data.start_date||'')+'"')+
   fld('end_date','End date (optional)','date','value="'+h(data.end_date||'')+'"');
 for(const [name,label] of fields){
  const required=applicantHistoryRequired[kind].includes(name);
  if(name==='employment_status'){
   html+=selectField(name,label,['employed','self_employed','unemployed','student','other'].map(x=>[x,x.replaceAll('_',' ')]));
  }else{
   html+=fld(name,label,'text',(required?'required ':'')+'maxlength="160" value="'+h(data[name]||'')+'"');
  }
 }
 html+=actions(existing?'Update history':'Save history')+'</form>';
 modal(html,async form=>{
   const data=values(form);
   const details={};
   for(const [name,val] of Object.entries(data))if(String(val).trim())details[name]=String(val).trim();
   const payload={details};
   if(existing)payload.expected_version=existing.version;
   await api(q()+'/clients/'+encodeURIComponent(S.applicantClientId)+'/histories/'+kind+
     (existing?'/'+encodeURIComponent(existing.id):''),{
       method:existing?'PUT':'POST',body:payload});
 });
}
