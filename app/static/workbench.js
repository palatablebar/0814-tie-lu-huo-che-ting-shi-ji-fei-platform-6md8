import {request} from './client.js';
import {snapshot, history} from './view.js';
import {visualize} from './plots.js';

const form = document.querySelector('#source');
const file = document.querySelector('#file');
const profile = document.querySelector('#profile');
const rateBox = document.querySelector('#rate-box');
const rateProfile = document.querySelector('#rate-profile');
const rateFile = document.querySelector('#rate-file');
const rateFileName = document.querySelector('#rate-file-name');
const previewCorrection = document.querySelector('#preview-correction');
const executeBtn = document.querySelector('#execute-btn');
const modeBox = document.querySelector('#mode-box');
const status = document.querySelector('#notice');
const detail = document.querySelector('#review');
const evidence = document.querySelector('#evidence');
const stages = [...document.querySelectorAll('[data-stage]')];
let stage = 'balance';
let report, selected, batch, running = false;
let mode = 'legacy';

modeBox.addEventListener('change', () => {
  mode = new FormData(modeBox).get('mode') === 'correction' ? 'correction' : 'legacy';
  const correction = mode === 'correction';
  rateBox.hidden = !correction;
  previewCorrection.hidden = !correction;
  executeBtn.textContent = correction ? '执行更正批次' : '执行批次';
  preview(stage);
});

function source() {
  const data = new FormData();
  if (file.files.length) data.append('file',file.files[0]);
  else data.append('sample',profile.value);
  return data;
}

function withSchedule(data) {
  if (mode !== 'correction') return data;
  if (rateFile.files.length) data.append('rate_file', rateFile.files[0]);
  else data.append('rate_profile', rateProfile.value);
  return data;
}

function announce(text, failure = false) {
  status.textContent = text;
  status.dataset.failure = String(failure);
}

function draw() {
  if (!report) return;
  snapshot(report, selected, stage);
  visualize(report, selected);
  for (const button of stages) button.setAttribute('aria-pressed',String(button.dataset.stage===stage));
  document.querySelector('#panel-title').textContent = stages.find(button => button.dataset.stage===stage)?.textContent || '运行对账';
  detail.hidden = !batch;
  if (batch) {
    document.querySelector('#run-status').textContent = `${batch.id.slice(0,10)} · ${batch.status} · r${batch.revision}`;
    detail.querySelector('[value="APPROVED"]').disabled = !report.balance.releasable || batch.status==='APPROVED';
    detail.querySelector('[value="HELD"]').disabled = batch.status==='APPROVED';
    evidence.href = `/api/runs/${batch.id}/evidence`;
  }
}

function show(payload, committed = false) {
  batch = committed ? payload : null;
  report = committed ? payload.report : payload;
  detail.elements.note.value = batch?.note || '';
  selected = report.cases?.[0]?.case;
  draw();
}

async function refresh() {
  const data = await request('/api/runs');
  history(data.items, batch?.id);
}

async function perform(action) {
  if (running) return;
  running = true;
  document.body.setAttribute('aria-busy','true');
  announce('处理中…');
  try { await action(); }
  catch (error) { announce(error.message,true); }
  finally { running = false; document.body.removeAttribute('aria-busy'); }
}

function preview(next) {
  return perform(async () => {
    let payload;
    if (mode === 'correction') {
      payload = await request('/api/corrections/preview', {method:'POST', body:withSchedule(source())});
      stage = 'balance';
    } else {
      payload = await request(`/api/stages/${next}`,{method:'POST',body:source()});
      stage = next;
    }
    show(payload);
    announce('阶段预览已更新');
    await refresh();
  });
}

stages.forEach(button => button.addEventListener('click',()=>preview(button.dataset.stage)));
previewCorrection.addEventListener('click', () => preview(stage));
form.addEventListener('submit', event => {
  event.preventDefault();
  perform(async () => {
    const data = withSchedule(source());
    if (mode === 'correction') data.append('kind', 'correction');
    const result = await request('/api/runs',{method:'POST',body:data});
    stage = 'balance'; show(result,true);
    announce(mode === 'correction' ? '更正批次已保存' : '批次已保存'); await refresh();
  });
});
const filename = document.querySelector('#file-name');
profile.addEventListener('change',()=>{file.value=''; filename.textContent=''; preview(stage);});
file.addEventListener('change',()=>{filename.textContent=file.files[0]?.name || ''; preview(stage);});
rateProfile.addEventListener('change',()=>{rateFile.value=''; rateFileName.textContent=''; preview(stage);});
rateFile.addEventListener('change',()=>{rateFileName.textContent=rateFile.files[0]?.name || ''; preview(stage);});
document.querySelector('#rows').addEventListener('click',event=>{
  const button = event.target.closest('[data-case]');
  if (button) { selected = button.dataset.case; draw(); document.querySelector(`[data-case="${CSS.escape(selected)}"]`).focus(); }
});
document.querySelector('#history').addEventListener('click',event=>{
  const button = event.target.closest('[data-run]');
  if (button) perform(async()=>{
    const result = await request(`/api/runs/${button.dataset.run}`);
    mode = result.report.schedule ? 'correction' : 'legacy';
    modeBox.querySelector(`[value="${mode}"]`).checked = true;
    const correction = mode === 'correction';
    rateBox.hidden = !correction;
    previewCorrection.hidden = !correction;
    executeBtn.textContent = correction ? '执行更正批次' : '执行批次';
    stage='balance'; show(result,true); announce('已载入历史批次'); await refresh();
  });
});
detail.addEventListener('submit',event=>{
  event.preventDefault();
  perform(async()=>{
    const payload={status:event.submitter.value,revision:batch.revision,note:detail.elements.note.value};
    const result=await request(`/api/runs/${batch.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    show(result,true); announce(result.status==='APPROVED'?'批次已签发':'批次已暂缓'); await refresh();
  });
});
preview(stage);
