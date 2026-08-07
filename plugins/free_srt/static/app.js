import {$, escapeHtml, formatEta} from './js/dom.js';
import {displayLength, displayUnits, parseSrt, parseTime, formatTime, splitCueText} from './js/srt.js';
import {appState} from './js/state.js';
const pluginBase=(document.documentElement.dataset.baseUrl||'').replace(/\/$/,'');
function pluginUrl(path){const value=String(path||'');return value.startsWith('/')?pluginBase+value:value}
const nativeFetch=globalThis.fetch?.bind(globalThis);
if(nativeFetch)globalThis.fetch=(resource,options)=>nativeFetch(typeof resource==='string'?pluginUrl(resource):resource,options);
if(globalThis.XMLHttpRequest){const nativeOpen=XMLHttpRequest.prototype.open;XMLHttpRequest.prototype.open=function(method,url,...rest){return nativeOpen.call(this,method,typeof url==='string'?pluginUrl(url):url,...rest)}}
let toastTimer;
let lastTextSelection=null;

function applyTheme(theme){
  const resolved=theme==='dark'?'dark':'light';
  document.documentElement.dataset.theme=resolved;
  $('theme-toggle').setAttribute('aria-pressed',String(resolved==='dark'));
  $('theme-toggle').querySelector('.theme-icon').textContent=resolved==='dark'?'☀':'☾';
  $('theme-toggle').querySelector('.theme-label').textContent=resolved==='dark'?'โหมดสว่าง':'โหมดมืด';
  localStorage.setItem('free-srt-theme',resolved);
  if(appState.preferencesLoaded)schedulePreferences();
}
applyTheme(localStorage.getItem('free-srt-theme')||'light');
$('theme-toggle').onclick=()=>applyTheme(document.documentElement.dataset.theme==='dark'?'light':'dark');

function toast(message,type='ok'){const el=$('toast');el.textContent=message;el.className=type==='error'?'show error':'show';clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.className='',2600)}
function preferencePayload(){const payload={theme:document.documentElement.dataset.theme||'light',language:$('language').value,threads:$('threads').value||null,compute_mode:$('compute-mode').value,gpu_backend:$('gpu-backend').value};if($('model-select').value)payload.model=$('model-select').value;if(appState.fonts.length)payload.subtitle_style=currentSubtitleStyle();return payload}
function schedulePreferences(){if(!appState.preferencesLoaded)return;clearTimeout(appState.preferenceTimer);appState.preferenceTimer=setTimeout(savePreferences,500)}
async function savePreferences(){try{const response=await fetch('/api/preferences',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(preferencePayload())});const data=await response.json();if(!response.ok)throw new Error(data.error);appState.preferences=data}catch(error){console.error('บันทึกการตั้งค่าไม่สำเร็จ',error)}}
async function loadPreferences(){try{const response=await fetch('/api/preferences'),data=await response.json();if(response.ok)appState.preferences=data||{}}catch(error){console.error(error)}appState.preferencesLoaded=true;applyTheme(appState.preferences.theme||localStorage.getItem('free-srt-theme')||'light');if(appState.preferences.language)$('language').value=appState.preferences.language;if(appState.preferences.threads!==undefined&&appState.preferences.threads!==null)$('threads').value=appState.preferences.threads;if(appState.preferences.compute_mode)$('compute-mode').value=appState.preferences.compute_mode;if(appState.preferences.gpu_backend)$('gpu-backend').value=appState.preferences.gpu_backend;updateComputeControls()}
function updateComputeControls(){const mode=$('compute-mode').value;const gpu=mode==='gpu';$('gpu-backend-wrap').hidden=!gpu;$('gpu-runtime-panel').hidden=!gpu||!appState.computeBackends;renderComputeStatus(appState.computeBackends)}
async function loadComputeBackends(){try{const response=await fetch('/api/compute/backends');const data=await response.json();if(!response.ok)throw new Error(data.error||'อ่าน GPU backend ไม่สำเร็จ');appState.computeBackends=data;if(!appState.preferences.compute_mode&&data.recommended_backend){const info=(data.backends||[]).find(item=>item.id===data.recommended_backend);if(info&&info.available){$('compute-mode').value='gpu';$('gpu-backend').value='auto'}}updateComputeControls()}catch(error){console.error(error)}}
function renderComputeStatus(data){
  if(!data)return;
  const panel=$('gpu-runtime-panel'),message=$('gpu-runtime-message'),button=$('gpu-runtime-download'),cancel=$('gpu-runtime-cancel');
  if(!panel||$('compute-mode').value!=='gpu')return;
  const backend=$('gpu-backend').value==='auto'?data.recommended_backend:$('gpu-backend').value;
  const info=(data.backends||[]).find(item=>item.id===backend);
  if(!info){panel.hidden=true;return}
  const detectedVendors=new Set((data.hardware&&data.hardware.vendors)||[]);
  const hardwareDetected=(info.vendors||[]).some(vendor=>detectedVendors.has(vendor));
  const retryProbe=Boolean(info.installed&&!info.available);
  panel.hidden=false;
  button.hidden=Boolean(info.available)||(!retryProbe&&!info.download_available);
  button.dataset.backend=backend||'';
  button.dataset.action=retryProbe?'probe':'download';
  button.disabled=['downloading','cancelling'].includes(info.download_status);
  cancel.dataset.backend=backend||'';
  cancel.hidden=!['downloading','cancelling'].includes(info.download_status);
  cancel.disabled=info.download_status==='cancelling';
  if(info.available){
    message.textContent=info.name+' พร้อมใช้งาน';
    button.hidden=true;
  }else if(info.installed){
    message.textContent='พบและติดตั้ง '+info.name+' แล้ว แต่ runtime ยังเริ่มทำงานไม่ได้ จึงจะใช้ CPU สำรอง';
    button.textContent='ลองตรวจสอบใหม่';
  }else{
    const prefix=hardwareDetected?'ตรวจพบการ์ดจอที่รองรับ '+info.name+' แล้ว แต่ยังไม่ได้ติดตั้ง runtime':'ยังไม่ได้ติดตั้ง runtime '+info.name;
    const downloadHint=info.download_available?' สามารถดาวน์โหลดส่วนเสริมได้'+(info.download_size?' ('+info.download_size+')':''):' และแพ็กเกจนี้ยังไม่ได้รวม runtime';
    message.textContent=prefix+downloadHint;
    button.textContent=info.download_status==='downloading'?'กำลังดาวน์โหลด '+info.download_progress+'%':'ดาวน์โหลด '+info.name+(info.download_size?' · '+info.download_size:'');
  }
}
async function cancelGpuRuntime(backend){if(!backend)return;await fetch('/api/compute/backends/'+encodeURIComponent(backend)+'/cancel',{method:'POST'});await loadComputeBackends()}
async function probeGpuRuntime(backend){
  if(!backend)return;
  const response=await fetch('/api/compute/backends/'+encodeURIComponent(backend)+'/probe',{method:'POST'});
  const data=await response.json();
  if(!response.ok){toast(data.error||'ตรวจสอบ GPU runtime ไม่สำเร็จ','error');return}
  await loadComputeBackends();
  if(!data.available)toast(data.error||'GPU runtime ยังไม่พร้อมใช้งาน','error');
}
async function handleGpuRuntimeAction(button){
  if(button.dataset.action==='probe')await probeGpuRuntime(button.dataset.backend);
  else await downloadGpuRuntime(button.dataset.backend);
}
async function downloadGpuRuntime(backend){
  if(!backend)return;
  const response=await fetch('/api/compute/backends/'+encodeURIComponent(backend)+'/download',{method:'POST'});
  const data=await response.json();
  if(!response.ok){toast(data.error||'ดาวน์โหลด GPU runtime ไม่สำเร็จ','error');return}
  $('gpu-runtime-download').disabled=true;
  await loadComputeBackends();
  const timer=setInterval(async()=>{
    await loadComputeBackends();
    const item=(appState.computeBackends.backends||[]).find(entry=>entry.id===backend);
    if(item&&['completed','failed','cancelled'].includes(item.download_status)){
      clearInterval(timer);
      $('gpu-runtime-download').disabled=false;
      if(item.download_status==='completed'){
        $('compute-mode').value='gpu';
        $('gpu-backend').value=backend;
        schedulePreferences();
        updateComputeControls();
      }else{
        const error=item.download_error||item.error;
        if(error)toast(error,'error');
      }
    }
  },1000);
}
function uploadProgressTracker(etaId,percentId,barId){const started=performance.now();let previousTime=started,previousBytes=0,smoothedSpeed=0;return event=>{if(!event.lengthComputable)return;const now=performance.now(),elapsed=Math.max((now-previousTime)/1000,.001),delta=Math.max(0,event.loaded-previousBytes),instant=delta/elapsed;smoothedSpeed=smoothedSpeed?smoothedSpeed*.72+instant*.28:instant;previousTime=now;previousBytes=event.loaded;const pct=Math.round(event.loaded*100/event.total);$(percentId).textContent=`${pct}%`;$(barId).style.width=`${pct}%`;$(etaId).textContent=now-started<900||!smoothedSpeed?'กำลังประเมินเวลา...':formatEta((event.total-event.loaded)/smoothedSpeed)}}
function setBusy(value){appState.busy=value;$('start-btn').disabled=value||!(appState.file||appState.localSelection)||!appState.ready.has($('model-select').value);const remove=$('remove-file');if(remove)remove.disabled=value;$('choose-local-file').disabled=value}
function setDirty(value){appState.dirty=value;if(appState.taskId&&appState.cues.length)scheduleEditorBackup();$('save-indicator').classList.toggle('saved',!value);$('save-label').textContent=value?'ยังไม่บันทึก':'บันทึกแล้ว';$('header-save').disabled=!appState.taskId||!value}
function cloneCues(cues=appState.cues){return cues.map(c=>({...c}))}
function updateHistoryButtons(){$('undo').disabled=!appState.undo.length;$('redo').disabled=!appState.redo.length}
function checkpoint(){appState.undo.push(cloneCues());if(appState.undo.length>60)appState.undo.shift();appState.redo=[];updateHistoryButtons()}
function commitPendingEdit(){if(appState.editStart&&JSON.stringify(appState.editStart)!==JSON.stringify(appState.cues)){appState.undo.push(appState.editStart);if(appState.undo.length>60)appState.undo.shift();appState.redo=[];updateHistoryButtons()}appState.editStart=null}
function restoreSnapshot(snapshot){appState.cues=cloneCues(snapshot);setDirty(true);renderCues()}
function undo(){if(!appState.undo.length)return;appState.redo.push(cloneCues());restoreSnapshot(appState.undo.pop());updateHistoryButtons()}
function redo(){if(!appState.redo.length)return;appState.undo.push(cloneCues());restoreSnapshot(appState.redo.pop());updateHistoryButtons()}

function selectFile(file){if(appState.busy)return;appState.localSelection=null;$("local-preflight").hidden=true;appState.file=file;appState.editorName=file.name;$("file-info").innerHTML=`<div class="file-info"><div><strong>${escapeHtml(file.name)}</strong><div class="hint">${(file.size/1048576).toFixed(2)} MB · ${escapeHtml(file.type||"ชนิดไฟล์ไม่ระบุ")} · จะคัดลอกเข้าโปรแกรม</div></div><button id="remove-file" class="secondary">นำออก</button></div>`;$("remove-file").onclick=()=>{appState.file=null;$("file-input").value="";$("file-info").innerHTML="";setBusy(false)};setBusy(false)}
$('upload-zone').onclick=()=>!appState.busy&&$('file-input').click();
$('file-input').onchange=e=>e.target.files[0]&&selectFile(e.target.files[0]);
$('upload-zone').ondragover=e=>{e.preventDefault();$('upload-zone').classList.add('dragover')};
$('upload-zone').ondragleave=()=>$('upload-zone').classList.remove('dragover');
$('upload-zone').ondrop=e=>{e.preventDefault();$('upload-zone').classList.remove('dragover');if(e.dataTransfer.files[0])selectFile(e.dataTransfer.files[0])};
$("choose-local-file").onclick=async()=>{if(appState.busy)return;try{const response=await fetch("/api/local-selection",{method:"POST"});const data=await response.json();if(!response.ok)throw new Error(data.error||"เลือกไฟล์ไม่สำเร็จ");if(data.cancelled)return;appState.file=null;$("file-input").value="";appState.localSelection=data.selection_id;appState.editorName=data.name;$("file-info").innerHTML=`<div class="file-info"><div><strong>${escapeHtml(data.name)}</strong><div class="hint">${(data.size/1048576).toFixed(2)} MB · โปรแกรมจะไม่คัดลอกหรือลบไฟล์ต้นฉบับ</div></div><button id="remove-file" class="secondary">นำออก</button></div>`;$("remove-file").onclick=()=>{appState.localSelection=null;$("file-info").innerHTML="";$("local-preflight").hidden=true;setBusy(false)};showPreflight(data.preflight);setBusy(false)}catch(error){toast(error.message,"error")}};
function showPreflight(data){const box=$("local-preflight"),seconds=Math.round(data.duration_seconds),hours=Math.floor(seconds/3600),minutes=Math.floor(seconds%3600/60),wav=(data.estimated_wav_bytes/1048576).toFixed(0),free=(data.recommended_free_bytes/1048576).toFixed(0);box.className="preflight";box.textContent=`ตรวจไฟล์แล้ว: ความยาว ${hours?`${hours} ชม. `:""}${minutes} นาที · จะสร้าง WAV ชั่วคราวประมาณ ${wav} MB · แนะนำพื้นที่ว่างอย่างน้อย ${free} MB · ไฟล์ต้นฉบับจะไม่ถูกแก้ไขหรือลบ`;box.hidden=false}
$('model-select').onchange=()=>{setBusy(appState.busy);schedulePreferences()};$('compute-mode').onchange=()=>{updateComputeControls();schedulePreferences()};$('gpu-backend').onchange=()=>{updateComputeControls();schedulePreferences()};$('gpu-runtime-download').onclick=()=>handleGpuRuntimeAction($('gpu-runtime-download'));$('gpu-runtime-cancel').onclick=()=>cancelGpuRuntime($('gpu-runtime-cancel').dataset.backend);
$('language').onchange=schedulePreferences;
$('threads').onchange=schedulePreferences;

async function loadModels(){const selected=$('model-select').value||appState.preferences.model;try{const models=await fetch('/api/models').then(r=>r.json());appState.ready.clear();$('model-list').innerHTML='';$('model-select').innerHTML='';models.forEach(model=>{if(model.status==='downloaded')appState.ready.add(model.filename);const active=['downloading','cancelling'].includes(model.status);const action=model.status==='downloaded'?'<span class="status">พร้อมใช้</span>':active?`<span class="status">${model.status==='cancelling'?'กำลังยกเลิก...':`ดาวน์โหลด ${model.progress}%`}</span><button class="danger cancel-model" data-file="${escapeHtml(model.filename)}" ${model.status==='cancelling'?'disabled':''}>ยกเลิก</button>`:`<button class="download-model" data-file="${escapeHtml(model.filename)}">${model.status==='failed'?'ลองใหม่':'ดาวน์โหลด'}</button>`;const item=document.createElement('article');item.className='model-item';item.innerHTML=`<div class="model-top"><div><div class="model-name">${escapeHtml(model.name)} <span class="tag">${escapeHtml(model.badge)}</span></div><div class="model-description">${escapeHtml(model.description)}</div><div class="model-facts"><span class="tag">ความเร็ว: ${escapeHtml(model.speed)}</span><span class="tag">ความแม่นยำ: ${escapeHtml(model.accuracy)}</span><span class="tag">ขนาด: ${escapeHtml(model.size)}</span></div><div class="model-meta"><strong>เหมาะกับ:</strong> ${escapeHtml(model.recommended_for)}<br><strong>ทรัพยากร:</strong> ${escapeHtml(model.memory_hint)}</div></div><div class="model-actions">${action}</div></div>${active?`<div class="progress"><div style="width:${model.progress}%"></div></div>`:''}`;$('model-list').appendChild(item);const option=document.createElement('option');option.value=model.filename;option.textContent=`${model.name} — ${model.status==='downloaded'?'พร้อมใช้':'ยังไม่ได้ดาวน์โหลด'}`;$('model-select').appendChild(option)});if([...$('model-select').options].some(o=>o.value===selected))$('model-select').value=selected;else if(appState.ready.size)$('model-select').value=[...appState.ready][0];document.querySelectorAll('.download-model').forEach(b=>b.onclick=()=>downloadModel(b.dataset.file));document.querySelectorAll('.cancel-model').forEach(b=>b.onclick=()=>cancelModel(b.dataset.file));setBusy(appState.busy)}catch(error){$('model-list').innerHTML=`<div class="hint">อ่านข้อมูลโมเดลไม่สำเร็จ: ${escapeHtml(error.message)}</div>`}}
async function downloadModel(filename){await fetch('/api/models/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename})});loadModels()}
async function cancelModel(filename){if(!confirm('ยกเลิกการดาวน์โหลดโมเดลนี้หรือไม่? ไฟล์ที่ยังไม่ครบจะถูกลบ'))return;await fetch(`/api/models/${encodeURIComponent(filename)}/cancel`,{method:'POST'});loadModels()}

async function beginJob(){
  if((!appState.file&&!appState.localSelection)||appState.busy)return;
  setBusy(true);schedulePreferences();appState.taskId=null;$("editor-section").hidden=true;$("progress-container").hidden=false;$("logs").textContent="";$("logs").className="logs";$("progress-status").textContent="กำลังจองคิว...";$("progress-percent").textContent="0%";$("job-progress").style.width="0%";$("progress-eta").textContent="กำลังเตรียมงาน...";$("cancel-job").disabled=false;$("job-status").textContent="กำลังทำงาน";
  try{
    const reservedResponse=await fetch('/api/transcribe/reservations',{method:'POST'}),reserved=await reservedResponse.json();
    if(!reservedResponse.ok)throw new Error(typeof reserved.error==='string'?reserved.error:(reserved.error?.message||'จองคิวไม่สำเร็จ'));
    appState.taskId=reserved.task_id;
    await pollJob();appState.polling=setInterval(pollJob,1000);
    const form=new FormData();if(appState.file)form.append("file",appState.file);else form.append("selection_id",appState.localSelection);form.append("model",$("model-select").value);form.append("language",$("language").value);form.append("threads",$("threads").value);form.append("compute_mode",$("compute-mode").value);form.append("gpu_backend",$("gpu-backend").value);
    const endpoint=`/api/transcribe?task_id=${encodeURIComponent(appState.taskId)}`;
    if(!appState.file){
      const response=await fetch(endpoint,{method:"POST",body:form}),data=await response.json();
      if(!response.ok){if(data.status==='cancelled')return;throw new Error(typeof data.error==='string'?data.error:(data.error?.message||"เริ่มงานไม่สำเร็จ"))}
      return;
    }
    const xhr=new XMLHttpRequest();appState.xhr=xhr;xhr.open("POST",endpoint);xhr.upload.onprogress=uploadProgressTracker('progress-eta','progress-percent','job-progress');xhr.upload.onload=()=>{$("progress-status").textContent="อัปโหลดเสร็จแล้ว กำลังตรวจไฟล์...";$("progress-eta").textContent="กำลังเตรียมงานถอดเสียง..."};
    xhr.onload=()=>{appState.xhr=null;let data={};try{data=JSON.parse(xhr.responseText)}catch{}if(xhr.status<200||xhr.status>=300){if(data.status==='cancelled')return;showError(typeof data.error==='string'?data.error:(data.error?.message||"เริ่มงานไม่สำเร็จ"))}};
    xhr.onerror=()=>{appState.xhr=null;showError("ติดต่อโปรแกรมไม่สำเร็จ")};xhr.onabort=()=>{appState.xhr=null;showCancelled("ยกเลิกการอัปโหลดแล้ว")};xhr.send(form)
  }catch(error){showError(error.message)}
}
$('start-btn').onclick=beginJob;
$('cancel-job').onclick=async()=>{if(!confirm('ยกเลิกงานนี้หรือไม่? ไฟล์ชั่วคราวและผลลัพธ์ที่ยังไม่สมบูรณ์จะถูกลบ'))return;const taskId=appState.taskId;$('cancel-job').disabled=true;$('progress-status').textContent='กำลังยกเลิก...';if(appState.xhr)appState.xhr.abort();if(taskId)await fetch(`/api/transcribe/${encodeURIComponent(taskId)}/cancel`,{method:'POST'})};async function pollJob(){if(!appState.taskId)return;try{const data=await fetch(`/api/transcribe/status/${appState.taskId}`).then(r=>r.json());if(data.error){showError(data.error);return}$('logs').textContent=(data.logs||[]).join('\n');$('logs').scrollTop=$('logs').scrollHeight;$('progress-eta').textContent=data.status==='queued'?'กำลังรอเริ่มงาน...':formatEta(data.eta_seconds);const names={queued:'อยู่ในคิว...',converting:'กำลังแปลงไฟล์ด้วย FFmpeg...',transcribing:'กำลังถอดเสียงด้วย Whisper...',cancelling:'กำลังยกเลิก...',completed:'สร้าง SRT เสร็จแล้ว',cancelled:'ยกเลิกงานแล้ว',failed:'เกิดข้อผิดพลาด'};$('progress-status').textContent=names[data.status]||data.status;$('progress-percent').textContent=`${data.progress||0}%`;$('job-progress').style.width=`${data.progress||0}%`;if(data.status==='completed'){appState.hasVideo=Boolean(data.has_video);appState.editorName=data.input_name||appState.editorName;stopPolling();$('cancel-job').disabled=true;await openEditor()}else if(data.status==='cancelled')showCancelled('ยกเลิกงานและลบไฟล์ชั่วคราวแล้ว');else if(data.status==='failed')showError(data.error||'ถอดเสียงไม่สำเร็จ')}catch(error){console.error(error)}}
function stopPolling(){if(appState.polling)clearInterval(appState.polling);appState.polling=null}
function showCancelled(message){stopPolling();$('progress-status').textContent=message;$('progress-percent').textContent='—';$('job-status').textContent='ยกเลิกแล้ว';$('logs').className='logs';$('cancel-job').disabled=true;appState.taskId=null;setBusy(false)}
function showError(message){stopPolling();$('progress-status').textContent='เกิดข้อผิดพลาด';$('progress-percent').textContent='ERROR';$('job-status').textContent='ผิดพลาด';$('logs').className='logs';$('logs').textContent+=`${$('logs').textContent?'\n':''}${message}`;$('cancel-job').disabled=true;appState.taskId=null;setBusy(false);toast(message,'error')}

function serializeSrt(){return appState.cues.map((cue,index)=>`${index+1}\n${formatTime(cue.start_ms)} --> ${formatTime(cue.end_ms)}\n${cue.text.trim()}`).join('\n\n')+'\n'}

function scheduleEditorBackup(){clearTimeout(appState.backupTimer);const state=$('editor-backup-state');if(state){state.textContent='กำลังสำรอง...';state.className='backup-state saving'}appState.backupTimer=setTimeout(saveEditorBackup,750)}
async function saveEditorBackup(){if(!appState.taskId||!appState.cues.length)return;try{const response=await fetch('/api/editor-backup',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:serializeSrt(),input_name:appState.editorName||'Subtitle Editor',dirty:appState.dirty,subtitle_style:appState.fonts.length?currentSubtitleStyle():undefined})});const data=await response.json();if(!response.ok)throw new Error(data.error);const state=$('editor-backup-state');if(state){state.textContent=`สำรองแล้ว ${new Date(data.saved_at*1000).toLocaleTimeString('th-TH',{hour:'2-digit',minute:'2-digit'})}`;state.className='backup-state'}}catch(error){const state=$('editor-backup-state');if(state){state.textContent='สำรองไม่สำเร็จ';state.className='backup-state error'}console.error(error)}}
async function checkEditorBackup(){try{const response=await fetch('/api/editor-backup'),data=await response.json();if(!response.ok||!data.available||!data.dirty)return;$('recovery-summary').textContent=`${data.input_name||'Subtitle Editor'} · ${data.cue_count||0} ช่วง · สำรองเมื่อ ${new Date(data.saved_at*1000).toLocaleString('th-TH')}`;$('recovery-card').hidden=false}catch(error){console.error(error)}}
async function restoreEditorBackup(){try{const response=await fetch('/api/editor-backup/restore',{method:'POST'}),data=await response.json();if(!response.ok)throw new Error(data.error);appState.taskId=data.task_id;appState.hasVideo=false;appState.file=null;appState.localSelection=null;appState.editorName=data.input_name||'Recovered subtitle';if(data.subtitle_style){appState.preferences.subtitle_style=data.subtitle_style;appState.fonts=[]}await openEditor();setDirty(Boolean(data.dirty));$('recovery-card').hidden=true;toast('กู้คืนคำบรรยายจากข้อมูลสำรองแล้ว')}catch(error){toast(error.message,'error')}}
async function discardEditorBackup(){if(!confirm('ลบข้อมูลสำรองคำบรรยายนี้หรือไม่?'))return;await fetch('/api/editor-backup',{method:'DELETE'});$('recovery-card').hidden=true;toast('ลบข้อมูลสำรองแล้ว')}
async function openEditor(){try{const response=await fetch(`/api/subtitles/${appState.taskId}`);const data=await response.json();if(!response.ok)throw new Error(data.error);appState.cues=parseSrt(data.content);appState.undo=[];appState.redo=[];setDirty(false);updateHistoryButtons();await loadVideoOptions();setupMedia();renderCues();$('start-render').disabled=!appState.hasVideo;$('header-render').disabled=!appState.hasVideo;$('header-download-srt').disabled=false;$('header-download-txt').disabled=false;$('render-progress').hidden=true;$('render-result').hidden=true;$('job-status').textContent='พร้อมตรวจคำ';$('editor-file-name').textContent=appState.editorName||appState.file?.name||'Subtitle Editor';$('editor-section').hidden=false;$('welcome-section').hidden=true;$('models-section').hidden=true;$('transcribe-section').hidden=true;setBusy(false);$('editor-section').scrollIntoView({behavior:'smooth',block:'start'})}catch(error){showError(error.message)}}
function setupMedia(){if(appState.mediaUrl){URL.revokeObjectURL(appState.mediaUrl);appState.mediaUrl=null}if(appState.mediaResizeObserver){appState.mediaResizeObserver.disconnect();appState.mediaResizeObserver=null}const host=$('media-host'),overlay=$('subtitle-overlay');overlay.hidden=true;if(appState.file){appState.mediaUrl=URL.createObjectURL(appState.file)}const source=appState.mediaUrl||(appState.hasVideo?pluginUrl(`/api/media/${encodeURIComponent(appState.taskId)}`):null);if(!source){host.innerHTML='<div class="hint">ไฟล์เสียงที่เลือกจากเครื่องไม่มีพรีวิวใน browser</div>';return}host.innerHTML=appState.hasVideo?'<video id="media-player" controls preload="metadata"></video>':'<audio id="media-player" controls preload="metadata"></audio>';const media=$('media-player');media.src=source;media.ontimeupdate=highlightActiveCue;media.onseeked=highlightActiveCue;media.onloadedmetadata=()=>{const first=appState.cues[0];if(first&&media.currentTime*1000<first.start_ms)media.currentTime=(first.start_ms+20)/1000;highlightActiveCue();applySubtitleStyle()};if(appState.hasVideo&&window.ResizeObserver){appState.mediaResizeObserver=new ResizeObserver(()=>applySubtitleStyle());appState.mediaResizeObserver.observe(media);appState.mediaResizeObserver.observe(document.querySelector('.media-stage'))}media.onerror=()=>toast('Browser ไม่สามารถเล่นรูปแบบวิดีโอนี้ได้ แต่ยังสร้าง MP4 พร้อมซับได้','error')}
function activeCueIndex(){const media=$('media-player');if(!media)return-1;const now=media.currentTime*1000;return appState.cues.findIndex(cue=>now>=cue.start_ms&&now<cue.end_ms)}
function highlightActiveCue(){const index=activeCueIndex();document.querySelectorAll('.cue-row').forEach((row,rowIndex)=>row.classList.toggle('active',rowIndex===index));const overlay=$('subtitle-overlay');if(!appState.hasVideo||index<0){overlay.hidden=true;overlay.textContent='';return}const text=document.createElement('span');text.className='subtitle-overlay-text';text.textContent=appState.cues[index].text;overlay.replaceChildren(text);overlay.dataset.index=index;overlay.hidden=false;applySubtitleStyle()}
async function loadVideoOptions(){
  if(appState.fonts.length){applySubtitleStyle();return}
  const response=await fetch('/api/video-options'),data=await response.json();
  if(!response.ok)throw new Error(data.error||'อ่านข้อมูลฟอนต์ไม่สำเร็จ');
  appState.fonts=data.fonts||[];
  $('subtitle-font').innerHTML=appState.fonts.map(font=>`<option value="${escapeHtml(font.key)}">${escapeHtml(font.label)}</option>`).join('');
  let saved=appState.preferences.subtitle_style||{};if(!Object.keys(saved).length){try{saved=JSON.parse(localStorage.getItem('free-srt-subtitle-style')||'{}')}catch{}}
  const defaults=data.default_style||{};
  $('subtitle-font').value=appState.fonts.some(font=>font.key===saved.font)?saved.font:data.default_font;
  $('subtitle-font-size').value=saved.font_size??data.default_font_size;
  $('subtitle-outline').value=saved.outline_width??defaults.outline_width??2;
  $('subtitle-background').checked=saved.background??defaults.background??true;
  $('subtitle-shadow').value=saved.shadow_depth??defaults.shadow_depth??0;
  $('subtitle-position').value=['top','middle','bottom'].includes(saved.position)?saved.position:(defaults.position||'bottom');
  $('subtitle-margin').value=saved.margin_v??defaults.margin_v??48;
  applySubtitleStyle();
}
function currentSubtitleStyle(){return{font:$('subtitle-font').value,font_size:Math.min(72,Math.max(18,Number($('subtitle-font-size').value)||36)),outline_width:Math.min(6,Math.max(0,Number($('subtitle-outline').value)||0)),background:$('subtitle-background').checked,shadow_depth:Math.min(6,Math.max(0,Number($('subtitle-shadow').value)||0)),position:$('subtitle-position').value,margin_v:Math.min(240,Math.max(0,Number($('subtitle-margin').value)||0))}}
function subtitleVideoGeometry(){
  const media=$('media-player'),stage=document.querySelector('.media-stage');
  if(!media||media.tagName!=='VIDEO'||!stage)return null;
  const mediaRect=media.getBoundingClientRect(),stageRect=stage.getBoundingClientRect();
  if(!mediaRect.width||!mediaRect.height)return null;
  const naturalRatio=media.videoWidth&&media.videoHeight?media.videoWidth/media.videoHeight:mediaRect.width/mediaRect.height;
  const elementRatio=mediaRect.width/mediaRect.height;
  let width=mediaRect.width,height=mediaRect.height,offsetX=0,offsetY=0;
  if(elementRatio>naturalRatio){width=height*naturalRatio;offsetX=(mediaRect.width-width)/2}
  else if(elementRatio<naturalRatio){height=width/naturalRatio;offsetY=(mediaRect.height-height)/2}
  return{left:mediaRect.left-stageRect.left+offsetX,top:mediaRect.top-stageRect.top+offsetY,width,height,scaleY:height/288};
}
function applySubtitleStyle(){
  const style=currentSubtitleStyle(),selected=appState.fonts.find(font=>font.key===style.font),overlay=$('subtitle-overlay');
  const geometry=subtitleVideoGeometry();
  const scale=geometry?.scaleY||1;
  if(selected)overlay.style.fontFamily=selected.css_stack;
  // SRT is converted by FFmpeg to a 288-high SSA script. CSS em metrics are
  // slightly taller than libass glyph metrics, hence the 0.8 calibration.
  overlay.style.fontSize=`${style.font_size*scale*.8}px`;
  overlay.style.webkitTextStroke=`${style.outline_width*scale}px #000`;
  overlay.style.paintOrder='stroke fill';
  overlay.style.background='transparent';
  overlay.style.setProperty('--subtitle-bg',style.background?'rgba(0,0,0,.70)':'transparent');
  overlay.style.boxShadow='none';
  const boxPadding=style.background?style.outline_width*scale:0;
  overlay.style.padding='0';
  overlay.style.setProperty('--subtitle-pad',`${boxPadding}px`);
  overlay.style.textShadow=style.shadow_depth?`${style.shadow_depth*scale}px ${style.shadow_depth*scale}px 0 rgba(0,0,0,.92)`:'none';
  const left=(geometry?.left||0)+(geometry?.width||document.querySelector('.media-stage')?.clientWidth||0)/2;
  const top=geometry?.top||0,videoHeight=geometry?.height||document.querySelector('.media-stage')?.clientHeight||0;
  const margin=style.margin_v*scale;
  overlay.style.left=`${left}px`;overlay.style.right='auto';overlay.style.bottom='auto';
  overlay.style.maxWidth=`${(geometry?.width||document.querySelector('.media-stage')?.clientWidth||0)*.9}px`;
  if(style.position==='top'){overlay.style.top=`${top+margin}px`;overlay.style.transform='translateX(-50%)'}
  else if(style.position==='middle'){overlay.style.top=`${top+videoHeight/2}px`;overlay.style.transform='translate(-50%,-50%)'}
  else{overlay.style.top=`${top+videoHeight-margin}px`;overlay.style.transform='translate(-50%,-100%)'}
  $('subtitle-outline-value').textContent=style.outline_width.toFixed(2);
  $('subtitle-shadow-value').textContent=style.shadow_depth.toFixed(2);
  $('subtitle-margin-value').textContent=style.margin_v.toFixed(1);
  $('subtitle-margin').disabled=style.position==='middle';
  document.querySelector('.margin-control')?.classList.toggle('disabled',style.position==='middle');
  localStorage.setItem('free-srt-subtitle-style',JSON.stringify(style));
  schedulePreferences();
}
['subtitle-font','subtitle-position','subtitle-background'].forEach(id=>$(id).onchange=()=>{applySubtitleStyle();highlightActiveCue()});
['subtitle-font-size','subtitle-outline','subtitle-shadow','subtitle-margin'].forEach(id=>$(id).oninput=()=>{applySubtitleStyle();highlightActiveCue()});
$('toggle-subtitle-style').onclick=()=>{const panel=$('subtitle-style-panel'),show=panel.hidden;panel.hidden=!show;$('toggle-subtitle-style').setAttribute('aria-expanded',String(show));requestAnimationFrame(()=>{if(show)panel.scrollIntoView({behavior:'smooth',block:'nearest'});applySubtitleStyle()})};
$('subtitle-overlay').onclick=()=>{const index=Number($('subtitle-overlay').dataset.index);if(Number.isInteger(index))focusCue(index)};
function playCue(index){const cue=appState.cues[index],media=$('media-player');if(!cue||!media)return;media.currentTime=cue.start_ms/1000;media.play();const stop=()=>{if(media.currentTime*1000>=cue.end_ms){media.pause();media.removeEventListener('timeupdate',stop)}};media.addEventListener('timeupdate',stop)}

function cueIssues(cue,index){const issues=[];const duration=(cue.end_ms-cue.start_ms)/1000;const chars=displayLength(cue.text);const lines=cue.text.split('\n');if(cue.end_ms<=cue.start_ms)issues.push({type:'error',key:'time',text:'เวลาสิ้นสุดต้องมากกว่าเวลาเริ่ม'});if(index&&cue.start_ms<appState.cues[index-1].end_ms)issues.push({type:'error',key:'overlap',text:'เวลาซ้อนกับบรรทัดก่อนหน้า'});if(!cue.text.trim())issues.push({type:'error',key:'empty',text:'ไม่มีข้อความ'});if(lines.length>2)issues.push({type:'warning',key:'lines',text:'เกิน 2 บรรทัด'});if(lines.some(line=>displayUnits(line).length>35))issues.push({type:'warning',key:'lineLength',text:'มีบรรทัดยาวเกิน 35 ตัวอักษร'});if(chars>70)issues.push({type:'warning',key:'length',text:'ข้อความยาวเกิน 70 ตัวอักษร'});if(duration>0&&chars/duration>20)issues.push({type:'warning',key:'speed',text:`อ่านเร็ว ${Math.round(chars/duration)} ตัวอักษร/วินาที`});if(duration>7)issues.push({type:'warning',key:'duration',text:'แสดงนานเกิน 7 วินาที'});return issues}
function calculateQuality(){const map={};appState.cues.forEach((cue,index)=>cueIssues(cue,index).forEach(issue=>{if(!map[issue.key])map[issue.key]={...issue,indexes:[]};map[issue.key].indexes.push(index)}));appState.issueMap=map;return map}
function qualityIndexes(){return[...new Set(Object.values(appState.issueMap).flatMap(group=>group.indexes))].sort((a,b)=>a-b)}
function renderQuality(){const map=calculateQuality(),groups=Object.values(map),count=groups.reduce((sum,g)=>sum+g.indexes.length,0),indexes=qualityIndexes();$('quality-summary').textContent=count?`พบ ${count} จุดที่ควรตรวจ`:'ไม่พบปัญหาตามกฎพื้นฐาน';$('quality-filters').innerHTML=groups.length?groups.map(g=>`<button class="quality-chip ${g.type}" data-issue="${g.key}">${escapeHtml(g.text)} · ${g.indexes.length}</button>`).join(''):'<span class="tag">พร้อมส่งออก</span>';$('next-quality-issue').disabled=!indexes.length;if(appState.qualityCursor>=indexes.length)appState.qualityCursor=-1;document.querySelectorAll('[data-issue]').forEach(button=>button.onclick=()=>{const index=appState.issueMap[button.dataset.issue].indexes[0];appState.qualityCursor=indexes.indexOf(index);focusCue(index)})}
function goToNextQualityIssue(){const indexes=qualityIndexes();if(!indexes.length)return;appState.qualityCursor=(appState.qualityCursor+1)%indexes.length;focusCue(indexes[appState.qualityCursor]);$('quality-summary').textContent=`ปัญหา ${appState.qualityCursor+1} จาก ${indexes.length} จุด`}
function focusCue(index){const row=document.querySelector(`.cue-row[data-index="${index}"]`);if(row){row.scrollIntoView({behavior:'smooth',block:'center'});const area=row.querySelector('textarea');area.focus()}}
function renderCues(){const list=$('cue-list');list.innerHTML=appState.cues.map((cue,index)=>{const issues=cueIssues(cue,index);const issueHtml=issues.map(i=>`<span class="cue-${i.type}">${escapeHtml(i.text)}</span>`).join(' · ');const duration=Math.max(0,(cue.end_ms-cue.start_ms)/1000);return`<article class="cue-row ${issues.some(i=>i.type==='error')?'has-error':''}" data-index="${index}"><button class="cue-number" data-action="seek" aria-label="ไปยังบรรทัด ${index+1}">${index+1}</button><div class="time-controls"><input class="time-input" data-field="start" value="${formatTime(cue.start_ms)}" aria-label="เวลาเริ่มบรรทัด ${index+1}"><input class="time-input" data-field="end" value="${formatTime(cue.end_ms)}" aria-label="เวลาสิ้นสุดบรรทัด ${index+1}"><button class="play-cue" data-action="play">▶ เล่นช่วงนี้</button></div><div class="cue-text"><textarea data-field="text" aria-label="ข้อความบรรทัด ${index+1}">${escapeHtml(cue.text)}</textarea><div class="cue-stats"><span>${displayLength(cue.text)} ตัวอักษร</span>${issueHtml}</div></div><div class="cue-actions" data-duration="${duration.toFixed(3)}"><button data-action="split">แยก</button><button data-action="merge" ${index===appState.cues.length-1?'disabled':''}>รวม</button><button class="delete" data-action="delete">ลบ</button></div></article>`}).join('');bindCueEvents();renderQuality();highlightActiveCue()}
function bindCueEvents(){document.querySelectorAll('.cue-row').forEach(row=>{const index=+row.dataset.index;row.querySelectorAll('[data-field]').forEach(input=>{const rememberSelection=()=>{if(input.dataset.field==='text')lastTextSelection={index,start:input.selectionStart,end:input.selectionEnd,text:input.value}};input.onfocus=()=>{appState.editStart=cloneCues();rememberSelection()};input.onselect=rememberSelection;input.onkeyup=rememberSelection;input.oninput=()=>{const field=input.dataset.field;if(field==='text'){appState.cues[index].text=input.value;rememberSelection()}else{const parsed=parseTime(input.value);if(parsed!==null)appState.cues[index][field+'_ms']=parsed}setDirty(true);renderQuality();highlightActiveCue()};input.onchange=()=>{commitPendingEdit();renderCues()}});row.querySelectorAll('[data-action]').forEach(button=>{button.onmousedown=event=>event.preventDefault();button.onclick=()=>handleCueAction(button.dataset.action,index)})})}
function handleCueAction(action,index){if(action==='play'){playCue(index);return}if(action==='seek'){const media=$('media-player');if(media)media.currentTime=appState.cues[index].start_ms/1000;highlightActiveCue();return}commitPendingEdit();checkpoint();const cue=appState.cues[index];if(action==='delete'){if(appState.cues.length===1){toast('ต้องมีคำบรรยายอย่างน้อยหนึ่งบรรทัด','error');appState.undo.pop();return}appState.cues.splice(index,1)}else if(action==='merge'&&appState.cues[index+1]){const next=appState.cues[index+1];cue.text=cue.text.trim()+' '+next.text.trim();cue.end_ms=next.end_ms;appState.cues.splice(index+1,1)}else if(action==='split'){const media=$('media-player'),originalEnd=cue.end_ms;const lower=cue.start_ms+500,upper=cue.end_ms-500;if(upper<=lower){toast('ช่วงเวลาสั้นเกินไปสำหรับการแยก','error');appState.undo.pop();return}const selection=lastTextSelection?.index===index&&lastTextSelection.text===cue.text?lastTextSelection:null;const selectionPosition=selection?Math.round((selection.start+selection.end)/2):null;const selectionRatio=selectionPosition>0&&selectionPosition<cue.text.length?selectionPosition/cue.text.length:null;const current=media&&Number.isFinite(media.currentTime)?Math.round(media.currentTime*1000):0;const mediaRatio=current>lower&&current<upper?(current-cue.start_ms)/(cue.end_ms-cue.start_ms):null;const targetRatio=selectionRatio??mediaRatio??0.5;const parts=splitCueText(cue.text,targetRatio);if(!parts){toast('ไม่พบจุดแบ่งที่ปลอดภัยสำหรับข้อความนี้','error');appState.undo.pop();return}const targetTime=mediaRatio!==null?current:Math.round(cue.start_ms+(cue.end_ms-cue.start_ms)*parts.ratio);const split=Math.min(upper,Math.max(lower,targetTime));cue.end_ms=split;cue.text=parts.left;appState.cues.splice(index+1,0,{start_ms:split,end_ms:originalEnd,text:parts.right});lastTextSelection=null;}setDirty(true);renderCues()}
function addCue(){checkpoint();const last=appState.cues.at(-1);const media=$('media-player');const start=media&&Number.isFinite(media.currentTime)?Math.max(Math.round(media.currentTime*1000),last?.end_ms||0):(last?.end_ms||0);appState.cues.push({start_ms:start,end_ms:start+2000,text:'ข้อความใหม่'});setDirty(true);renderCues();focusCue(appState.cues.length-1)}
$('next-quality-issue').onclick=goToNextQualityIssue;
$('add-cue').onclick=addCue;$('add-cue-bottom').onclick=addCue;$('undo').onclick=undo;$('redo').onclick=redo;
$('play-current').onclick=()=>{const index=activeCueIndex();playCue(index>=0?index:0)};

async function saveSrt(){try{const content=serializeSrt();const response=await fetch(`/api/subtitles/${appState.taskId}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({content})});const data=await response.json();if(!response.ok)throw new Error(data.error);appState.cues=parseSrt(data.content);setDirty(false);toast('บันทึกคำบรรยายแล้ว');return true}catch(error){toast(`บันทึกไม่สำเร็จ: ${error.message}`,'error');return false}}
$('save-srt').onclick=saveSrt;
$('download-srt').onclick=async()=>{if(appState.dirty&&!(await saveSrt()))return;location.href=pluginUrl(`/api/download/${appState.taskId}`)};
$('download-txt').onclick=async()=>{if(appState.dirty&&!(await saveSrt()))return;location.href=pluginUrl(`/api/download/${appState.taskId}/txt`)};
$('reset-srt').onclick=async()=>{if(!confirm('คืนข้อความและเวลาทั้งหมดกลับเป็นผลลัพธ์แรกจาก Whisper หรือไม่?'))return;const response=await fetch(`/api/subtitles/${appState.taskId}/reset`,{method:'POST'});const data=await response.json();if(!response.ok){toast(data.error,'error');return}checkpoint();appState.cues=parseSrt(data.content);setDirty(false);renderCues();toast('คืนค่าต้นฉบับแล้ว')};

$('toggle-find').onclick=()=>$('find-panel').hidden=!$('find-panel').hidden;
$('replace-all').onclick=()=>{const find=$('find-text').value,replacement=$('replace-text').value;if(!find){toast('กรอกคำที่ต้องการค้นหา','error');return}const flags=$('match-case').checked?'g':'gi',pattern=new RegExp(find.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),flags);let count=0;appState.cues.forEach(cue=>{count+=(cue.text.match(pattern)||[]).length});if(!count){$('replace-result').textContent='ไม่พบคำที่ค้นหา';return}if(!confirm(`แทนที่ทั้งหมด ${count} จุดหรือไม่?`))return;checkpoint();appState.cues.forEach(cue=>cue.text=cue.text.replace(pattern,replacement));setDirty(true);renderCues();$('replace-result').textContent=`แทนที่แล้ว ${count} จุด`};

async function loadGlossary(){try{const response=await fetch('/api/glossary'),data=await response.json();if(!response.ok)throw new Error(data.error);appState.glossary=data.entries||[]}catch(error){appState.glossary=[];console.error(error)}renderGlossary()}
function glossaryEntriesForSave(){const entries=appState.glossary.map(e=>({from:e.from.trim(),to:e.to.trim()}));if(entries.some(e=>!e.from&&e.to))throw new Error('กรอกคำที่ต้องการตรวจในช่องซ้าย');return entries.filter(e=>e.from)}
function scheduleGlossarySave(){clearTimeout(appState.glossaryTimer);try{glossaryEntriesForSave();$('glossary-message').textContent='กำลังรอบันทึกอัตโนมัติ...';appState.glossaryTimer=setTimeout(()=>saveGlossary(false),650)}catch(error){$('glossary-message').textContent=error.message}}
async function saveGlossary(announce=true){clearTimeout(appState.glossaryTimer);try{const entries=glossaryEntriesForSave();$('glossary-message').textContent='กำลังบันทึก...';const response=await fetch('/api/glossary',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({entries})}),data=await response.json();if(!response.ok)throw new Error(data.error);appState.glossary=data.entries;$('glossary-message').textContent='บันทึกอัตโนมัติแล้ว และจะช่วยงานถัดไป';if(announce)toast('บันทึกสมุดคำศัพท์แล้ว');return true}catch(error){$('glossary-message').textContent=error.message;if(announce)toast(error.message,'error');return false}}
function renderGlossary(){const list=$('glossary-list');list.replaceChildren();appState.glossary.forEach((entry,index)=>{const row=document.createElement('div');row.className='glossary-row';row.dataset.index=String(index);const from=document.createElement('input');from.dataset.key='from';from.value=String(entry.from??'');from.placeholder='คำที่ผิด/คำที่ต้องการลบ';const to=document.createElement('input');to.dataset.key='to';to.value=String(entry.to??'');to.placeholder='คำที่ถูก (เว้นว่างเพื่อลบ)';const remove=document.createElement('button');remove.className='danger';remove.dataset.remove=String(index);remove.setAttribute('aria-label','ลบคำ');remove.textContent='×';row.append(from,to,remove);list.appendChild(row)});list.querySelectorAll('input').forEach(input=>input.oninput=()=>{const row=input.closest('.glossary-row');appState.glossary[+row.dataset.index][input.dataset.key]=input.value;scheduleGlossarySave()});list.querySelectorAll('[data-remove]').forEach(button=>button.onclick=()=>{appState.glossary.splice(+button.dataset.remove,1);renderGlossary();scheduleGlossarySave()})}
function openGlossary(){$('glossary-message').textContent='กรอกช่องซ้ายเพื่อบันทึกอัตโนมัติ · เว้นช่องขวาว่างเพื่อลบคำนั้น';renderGlossary();$('glossary-dialog').showModal()}
function escapeRegExp(value){const slash=String.fromCharCode(92),special=new Set([slash,'^','$','.','*','+','?','(',')','[',']','{','}','|']);return[...value].map(char=>special.has(char)?slash+char:char).join('')}
$('open-glossary').onclick=openGlossary;$('open-glossary-top').onclick=openGlossary;$('close-glossary').onclick=()=>$('glossary-dialog').close();
$('add-term').onclick=()=>{appState.glossary.push({from:'',to:''});renderGlossary();$('glossary-message').textContent='กรอกช่องซ้าย และเว้นช่องขวาว่างได้หากต้องการลบคำ';const inputs=$('glossary-list').querySelectorAll('input');if(inputs.length)inputs[inputs.length-2].focus()};
$('save-glossary').onclick=()=>saveGlossary(true);
$('export-glossary').onclick=()=>{location.href=pluginUrl('/api/glossary/export')};
$('import-glossary').onclick=()=>$('glossary-import-file').click();
$('glossary-import-file').onchange=async event=>{const file=event.target.files[0];event.target.value='';if(!file)return;try{const text=await file.text();let entries;try{const parsed=JSON.parse(text);entries=Array.isArray(parsed)?parsed:parsed.entries}catch{entries=text.split(String.fromCharCode(10)).map(line=>line.replace(String.fromCharCode(13),'')).filter(line=>line.trim()).map(line=>{const tab=String.fromCharCode(9),parts=line.includes(tab)?line.split(tab):line.split(',');return{from:(parts[0]||'').trim(),to:(parts.slice(1).join(',')||'').trim()}})}if(!Array.isArray(entries)||!entries.length)throw new Error('ไม่พบรายการคำศัพท์ในไฟล์');entries=entries.map(entry=>({from:String(entry.from||'').trim(),to:String(entry.to||'').trim()})).filter(entry=>entry.from||entry.to);if(!confirm(`แทนที่สมุดคำศัพท์ด้วย ${entries.length} รายการจากไฟล์นี้หรือไม่?`))return;appState.glossary=entries;renderGlossary();if(await saveGlossary(false))toast(`นำเข้าสมุดคำศัพท์แล้ว ${entries.length} รายการ`)}catch(error){$('glossary-message').textContent=`นำเข้าไม่สำเร็จ: ${error.message}`;toast(error.message,'error')}};
$('apply-glossary').onclick=()=>{if(!appState.taskId){toast('ยังไม่มีคำบรรยายให้แก้','error');return}const valid=appState.glossary.filter(e=>e.from.trim());let count=0;valid.forEach(entry=>{const pattern=new RegExp(escapeRegExp(entry.from),'gi');appState.cues.forEach(cue=>{count+=(cue.text.match(pattern)||[]).length})});if(!count){toast('ไม่พบคำจากสมุดในคำบรรยายนี้');return}if(!confirm(`ใช้สมุดคำศัพท์แก้ไขหรือลบ ${count} จุดในงานนี้หรือไม่?`))return;checkpoint();valid.forEach(entry=>{const pattern=new RegExp(escapeRegExp(entry.from),'gi');appState.cues.forEach(cue=>cue.text=cue.text.replace(pattern,entry.to))});setDirty(true);renderCues();$('glossary-dialog').close();toast(`แก้คำจากสมุดแล้ว ${count} จุด`)};
function stopRenderPolling(){if(appState.renderPolling)clearInterval(appState.renderPolling);appState.renderPolling=null}
function createRenderJob(form){return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();appState.renderXhr=xhr;xhr.open('POST',`/api/video-render/${encodeURIComponent(appState.taskId)}?render_id=${encodeURIComponent(appState.renderId)}`);xhr.upload.onprogress=uploadProgressTracker('render-eta','render-percent','render-progress-bar');xhr.upload.onload=()=>{$('render-status').textContent='ส่งวิดีโอครบแล้ว กำลังตรวจไฟล์...';$('render-eta').textContent='กำลังเตรียมการเรนเดอร์...'};xhr.onload=()=>{appState.renderXhr=null;let data={};try{data=JSON.parse(xhr.responseText)}catch{}if(xhr.status>=200&&xhr.status<300)resolve(data);else if(data.status==='cancelled')reject(new DOMException('ยกเลิกงานแล้ว','AbortError'));else reject(new Error(typeof data.error==='string'?data.error:(data.error?.message||'เริ่มสร้างวิดีโอไม่สำเร็จ')))};xhr.onerror=()=>{appState.renderXhr=null;reject(new Error('ติดต่อโปรแกรมไม่สำเร็จ'))};xhr.onabort=()=>{appState.renderXhr=null;reject(new DOMException('ยกเลิกการส่งวิดีโอแล้ว','AbortError'))};xhr.send(form)})}
async function startVideoRender(){
  if(!appState.taskId||!appState.hasVideo)return;
  const start=$('start-render');start.disabled=true;appState.renderId=null;$('render-result').hidden=true;$('render-progress').hidden=false;$('render-status').textContent='กำลังจองคิวสร้างวิดีโอ...';$('render-percent').textContent='0%';$('render-progress-bar').style.width='0%';$('render-eta').textContent='กำลังเตรียมการ...';$('render-logs').textContent='';$('cancel-render').disabled=false;
  if(!(await saveSrt())){start.disabled=false;$('render-progress').hidden=true;return}
  try{
    const reservedResponse=await fetch(`/api/video-render/${encodeURIComponent(appState.taskId)}/reservations`,{method:'POST'}),reserved=await reservedResponse.json();
    if(!reservedResponse.ok)throw new Error(typeof reserved.error==='string'?reserved.error:(reserved.error?.message||'จองคิวสร้างวิดีโอไม่สำเร็จ'));
    appState.renderId=reserved.render_id;
    await pollVideoRender();appState.renderPolling=setInterval(pollVideoRender,1000);
    const form=new FormData(),style=currentSubtitleStyle();Object.entries(style).forEach(([key,value])=>form.append(key,String(value)));if(appState.file)form.append('file',appState.file);
    await createRenderJob(form);
  }catch(error){stopRenderPolling();start.disabled=false;$('cancel-render').disabled=true;$('render-status').textContent=error.name==='AbortError'?'ยกเลิกการส่งวิดีโอแล้ว':'สร้างวิดีโอไม่สำเร็จ';$('render-percent').textContent=error.name==='AbortError'?'—':'ERROR';$('render-eta').textContent='';$('render-logs').textContent=error.message;if(error.name!=='AbortError')toast(error.message,'error')}
}async function pollVideoRender(){if(!appState.renderId)return;try{const response=await fetch(`/api/video-render/status/${encodeURIComponent(appState.renderId)}`);const data=await response.json();if(!response.ok)throw new Error(data.error||'อ่านสถานะไม่สำเร็จ');const labels={uploading:'กำลังรับวิดีโอ...',queued:'อยู่ในคิว...',rendering:'กำลังฝังซับและสร้าง MP4...',cancelling:'กำลังยกเลิก...',cancelled:'ยกเลิกการสร้างวิดีโอแล้ว',completed:'สร้างวิดีโอพร้อมซับเสร็จแล้ว',failed:'สร้างวิดีโอไม่สำเร็จ'};$('render-status').textContent=labels[data.status]||data.status;$('render-percent').textContent=`${data.progress||0}%`;$('render-progress-bar').style.width=`${data.progress||0}%`;$('render-eta').textContent=data.status==='queued'?'กำลังรอเริ่มงาน...':formatEta(data.eta_seconds);$('render-logs').textContent=(data.logs||[]).join(String.fromCharCode(10));$('render-logs').scrollTop=$('render-logs').scrollHeight;if(data.status==='completed'){stopRenderPolling();$('render-eta').textContent='เสร็จแล้ว';$('cancel-render').disabled=true;$('start-render').disabled=false;$('render-result').hidden=false;$('render-output-player').src=pluginUrl(`/api/video-render/${encodeURIComponent(appState.renderId)}/preview`);$('render-result').scrollIntoView({behavior:'smooth',block:'nearest'})}else if(data.status==='cancelled'){stopRenderPolling();$('render-eta').textContent='';$('cancel-render').disabled=true;$('start-render').disabled=false;toast('ยกเลิกและลบไฟล์วิดีโอที่ยังไม่สมบูรณ์แล้ว')}else if(data.status==='failed'){stopRenderPolling();$('render-eta').textContent='';$('cancel-render').disabled=true;$('start-render').disabled=false;toast(data.error||'สร้างวิดีโอไม่สำเร็จ','error')}}catch(error){console.error(error)}}
$('start-render').onclick=startVideoRender;
$('cancel-render').onclick=async()=>{if(!appState.renderId||!confirm('ยกเลิกการสร้างวิดีโอนี้หรือไม่?'))return;const renderId=appState.renderId;$('cancel-render').disabled=true;if(appState.renderXhr)appState.renderXhr.abort();await fetch(`/api/video-render/${encodeURIComponent(renderId)}/cancel`,{method:'POST'})};$('download-video').onclick=()=>{if(appState.renderId)location.href=pluginUrl(`/api/video-render/${encodeURIComponent(appState.renderId)}/download`)};
function showSetup(){
  $('editor-section').hidden=true;
  $('welcome-section').hidden=false;
  $('models-section').hidden=false;
  $('transcribe-section').hidden=false;
  $('header-save').disabled=true;
  $('header-download-srt').disabled=true;
  $('header-download-txt').disabled=true;
  $('header-render').disabled=true;
  $('transcribe-section').scrollIntoView({behavior:'smooth',block:'start'});
}
$('header-open-file').onclick=()=>{showSetup();setTimeout(()=>$('choose-local-file').click(),180)};
$('header-save').onclick=()=>saveSrt();
$('header-download-srt').onclick=()=>$('download-srt').click();
$('header-download-txt').onclick=()=>$('download-txt').click();
$('header-render').onclick=()=>startVideoRender();

document.addEventListener('keydown',event=>{const typing=['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName);if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();if(appState.taskId)saveSrt()}else if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='z'){event.preventDefault();event.shiftKey?redo():undo()}else if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='y'){event.preventDefault();redo()}else if(event.code==='Space'&&!typing&&$('media-player')){event.preventDefault();const media=$('media-player');media.paused?media.play():media.pause()}});
window.addEventListener('beforeunload',event=>{if(appState.dirty){event.preventDefault();event.returnValue=''}});

$('restore-backup').onclick=restoreEditorBackup;
$('discard-backup').onclick=discardEditorBackup;
async function initialize(){await loadPreferences();await Promise.all([loadModels(),loadComputeBackends(),loadGlossary(),checkEditorBackup()]);setInterval(loadModels,2000)}
initialize();



