'use strict';
// Client master record and case-specific INTERNAL answer drafts, never official PDF output.
const applicantRoot=id=>q()+'/clients/'+encodeURIComponent(id)+'/applicant';

async function renderApplicantCase(clientId){
 const [master,drafts]=await Promise.all([
   api(applicantRoot(clientId)),api(q()+'/cases/'+encodeURIComponent(S.caseId)+'/answer-drafts')]);
 S.applicantClientId=clientId;
 S.applicantMaster=master;
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
 if(action==='applicant:draft'){
   if(!confirm('Create a new immutable INTERNAL answer snapshot? This does not create an official PDF.'))return;
   await api(q()+'/cases/'+encodeURIComponent(S.caseId)+'/answer-drafts',{method:'POST'});
   await render();return toast('Internal answer draft recorded');
 }
}
