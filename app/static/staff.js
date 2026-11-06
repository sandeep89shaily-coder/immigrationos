'use strict';
/* Verified-OIDC staff onboarding. Tokens stay in memory, not localStorage or logs. */
const teamRoot=()=>q()+'/staff';

async function renderStaffTeam(){
 const role=S.orgs.find(x=>x.id===S.org)?.role;
 if(!['owner','admin'].includes(role)){
   $('mainContent').innerHTML=page('Practice team','Only owners and administrators manage membership.');
   return;
 }
 const [members,invitations]=await Promise.all([
   api(teamRoot()+'/members'),api(teamRoot()+'/invitations')
 ]);
 S.staffMembers=members;S.staffInvites=invitations.items;
 let top=btn('Invite teammate','staff:invite','primary')+' '+btn('Join another firm','staff:join','smallbtn');
 let flash='';
 if(S.pendingStaffToken){
   flash='<div class="callout"><strong>One-time invitation link</strong><p>This application does not send email. Copy the one-time secret and share it using a separately approved secure channel. It is not saved in the browser.</p><div class="form-field"><input type="text" aria-label="One-time invitation token" readonly value="'+h(S.pendingStaffToken)+'"></div>'+btn('Copy invitation token','staff:copy','smallbtn')+' '+btn('Discard displayed token','staff:forget','smallbtn')+'</div>';
 }
 const rows=members.map((m,i)=>{
   const controls=(m.role!=='owner' && m.active && m.subject!==S.userSub &&
     (m.role!=='admin'||role==='owner'))?
     btn('Change role','staff:role:'+i,'smallbtn')+' '+btn('Deactivate','staff:remove:'+i,'smallbtn'):'';
   return '<tr><td><strong>'+h(m.verified_email||m.subject)+'</strong><div class="meta">'+h(m.subject)+'</div></td>'+
     '<td>'+chip(m.role)+'</td><td>'+chip(m.active?'active':'inactive')+'</td><td>'+controls+'</td></tr>';
 });
 const invited=invitations.items.map((x,i)=>'<tr><td>'+h(x.email)+'</td><td>'+chip(x.role)+'</td>'+
   '<td>'+chip(x.status)+'</td><td>'+d(x.expires_at)+'</td><td>'+
   (x.status==='pending'&&(role==='owner'||x.role!=='admin')?
    btn('Cancel','staff:cancel:'+i,'smallbtn'):'')+'</td></tr>');
 $('mainContent').innerHTML=page('Practice team',
   'Verified invitations, access roles and accountable offboarding; development data only.',top)+
   flash+panel('Staff members',table(['Verified identity','Role','Status',''],rows))+
   panel('Invitation history',table(['Invited email','Role','Status','Expires',''],invited))+
   '<div class="callout">Identity-provider email verification is required to join. No licence status is independently checked. A new member is not automatically granted access to any case.</div>';
}

function staffInvite(){
 const role=S.orgs.find(x=>x.id===S.org)?.role;
 const options=role==='owner'?[
   ['consultant','Consultant'],['assistant','Assistant'],['viewer','Viewer'],['admin','Firm administrator']
 ]:[['consultant','Consultant'],['assistant','Assistant'],['viewer','Viewer']];
 modal('<h2>Invite a firm teammate</h2><p>The recipient must authenticate using the exact email entered here. Link expires in 72 hours. No email is sent automatically.</p><form>'+
   fld('email','Identity-provider verified email','email','required maxlength="254"')+
   selectField('role','New role',options)+
   '<div class="callout">Only a licensed professional may provide regulated services. Selecting the consultant role here does not verify RCIC registration.</div>'+
   actions('Create one-time invitation')+'</form>',async form=>{
     const result=await api(teamRoot()+'/invitations',{method:'POST',body:values(form)});
     S.pendingStaffToken=result.token;
 });
}

function staffJoin(){
 modal('<h2>Join an existing practice</h2><p>Sign in through your verified email account first, then paste the one-time invitation token delivered by your firm.</p><form>'+
   fld('token','Single-use invitation token','text','required minlength="48" maxlength="256" autocomplete="off"')+
   actions('Accept invitation')+'</form>',async form=>{
     const token=values(form).token;
     const joined=await api('/api/v1/staff/invitations/accept',{method:'POST',body:{token}});
     S.org=joined.org_id;
     sessionStorage.setItem('ios_org',S.org);
     S.view='dashboard';
     S.pendingStaffToken=null;
 });
}

function staffChangeRole(i){
 const member=S.staffMembers?.[i];if(!member)return;
 const actor=S.orgs.find(x=>x.id===S.org)?.role;
 const roles=actor==='owner'?[
   ['consultant','Consultant'],['assistant','Assistant'],['viewer','Viewer'],['admin','Administrator']
 ]:[['consultant','Consultant'],['assistant','Assistant'],['viewer','Viewer']];
 modal('<h2>Change teammate role</h2><p>All staff permissions are recorded in the audit history. Changing a role does not reassign existing immigration cases.</p><form>'+
   '<p>'+h(member.verified_email||member.subject)+'</p>'+
   selectField('role','New role',roles)+actions('Update firm role')+'</form>',async form=>{
     await api(teamRoot()+'/members/'+encodeURIComponent(member.subject)+'/role',
       {method:'POST',body:values(form)});
 });
}

async function staffAction(action){
 if(action==='staff:join')return staffJoin();
 if(action==='staff:invite')return staffInvite();
 if(action==='staff:copy'){if(S.pendingStaffToken)await navigator.clipboard.writeText(S.pendingStaffToken);return toast('Invitation token copied')}
 if(action==='staff:forget'){S.pendingStaffToken=null;return render()}
 const [,command,index]=action.split(':');
 if(!Number.isInteger(Number(index)))return;
 const i=Number(index);
 if(command==='role')return staffChangeRole(i);
 if(command==='remove'){
   const target=S.staffMembers?.[i];
   if(!target||!confirm('Deactivate this staff account? All its case access will stop immediately.'))return;
   await api(teamRoot()+'/members/'+encodeURIComponent(target.subject)+'/revoke',
             {method:'POST'});
   return render();
 }
 if(command==='cancel'){
   const invite=S.staffInvites?.[i];
   if(!invite||!confirm('Revoke this pending invitation?'))return;
   await api(teamRoot()+'/invitations/'+encodeURIComponent(invite.id)+'/revoke',{method:'POST'});
   return render();
 }
}
