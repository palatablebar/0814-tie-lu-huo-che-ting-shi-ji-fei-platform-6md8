import {element, pretty} from './client.js';

const labels = {READY:'通过', MISMATCH:'差异待复核', BLOCKED:'挡签', PENDING:'待复核', APPROVED:'已签发', HELD:'已暂缓'};
const headers = ['业务分组', '输入行', '计算值', '参考值', '判定'];
const billHeaders = ['业务分组', '输入行', '分段金额(分)', '票据金额(分)', '判定'];

export function badge(status) {
  return element('span', labels[status] || status, {class:'badge', 'data-result':status, title: status});
}

function isCorrection(report) {
  return Boolean(report.schedule);
}

export function snapshot(report, selected, stage) {
  const stats = report.intake;
  document.querySelector('[data-metric="input"]').textContent = stats.input;
  document.querySelector('[data-metric="accepted"]').textContent = stats.accepted;
  document.querySelector('[data-metric="isolated"]').textContent = stats.rejected;
  document.querySelector('[data-metric="cases"]').textContent = report.cases?.length ?? '—';
  const table = document.querySelector('#rows');
  table.replaceChildren();
  const head = element('tr');
  const body = table.createTBody();
  if (stage === 'intake') {
    head.append(...['源行', '记录键', '业务分组', '原因码'].map(title => element('th', title, {scope:'col'})));
    for (const item of stats.isolation) {
      const tr = body.insertRow();
      tr.append(...[item.line,item.record,item.case,item.reason].map(value=>element('td',value)));
    }
    if (!stats.isolation.length) body.insertRow().insertCell().textContent = '当前文件没有隔离行';
  } else if (isCorrection(report)) {
    head.append(...billHeaders.map(title => element('th', title, {scope:'col'})));
    for (const row of report.cases || []) {
      const tr = body.insertRow();
      const button = element('button',row.case,{type:'button','data-case':row.case,'aria-pressed':String(row.case===selected)});
      tr.insertCell().append(button);
      tr.insertCell().textContent = row.records.length;
      tr.insertCell().textContent = row.bill?.amount_cents ?? '—';
      tr.insertCell().textContent = row.invoice_cents ?? '—';
      tr.insertCell().append(badge(row.status));
    }
  } else {
    head.append(...headers.map(title => element('th', title, {scope:'col'})));
    for (const row of report.cases || []) {
      const tr = body.insertRow();
      const button = element('button',row.case,{type:'button','data-case':row.case,'aria-pressed':String(row.case===selected)});
      tr.insertCell().append(button);
      [row.records.length, row.measure?.value ?? '—', row.measure?.expected ?? '—'].forEach(value=>tr.insertCell().textContent=value);
      tr.insertCell().append(badge(row.status));
    }
  }
  table.createTHead().append(head);
  const picked = report.cases?.find(row=>row.case===selected);
  document.querySelector('#detail-title').textContent = picked ? `分组 ${picked.case}` : '采信摘要';
  const shown = picked
    ? (picked.bill ? correctionDetail(picked) : (picked.measure?.evidence ?? picked.prep?.details ?? {原因:picked.status}))
    : stats.reasons;
  document.querySelector('#detail').textContent = pretty(shown);
  document.querySelector('#counts').textContent = report.balance
    ? `行数 ${report.balance.accounted}/${report.balance.input} · ${report.balance.ready} 组通过${report.balance.blocked ? ` · ${report.balance.blocked} 组挡签` : ''}`
    : `采信 ${stats.accepted} 行 · 隔离 ${stats.rejected} 行`;
}

function correctionDetail(caseRow) {
  const bill = caseRow.bill;
  return {
    停时记录: caseRow.stay_record,
    扣减: {
      停时分钟: bill.duration_min,
      暂停分钟: bill.paused_min,
      免计分钟: bill.free_min,
      免计已用: bill.free_used_min,
      计费分钟: bill.billable_min,
    },
    分段账单: bill.segments.map(segment => ({
      键: segment.key,
      区间: [segment.start_min, segment.end_min],
      分钟: segment.minutes,
      费率: segment.rate_cents,
      金额: segment.amount_cents,
    })),
    金额合计: bill.amount_cents,
    阻断记录: bill.blocks,
  };
}

export function history(items, active) {
  const target = document.querySelector('#history');
  target.replaceChildren();
  for (const run of items) {
    const button = element('button', run.id.slice(0,10), {'data-run':run.id,'aria-pressed':String(run.id===active),type:'button'});
    const item = element('li');
    item.append(button, badge(run.status));
    target.append(item);
  }
  if (!items.length) target.append(element('li','尚无执行批次'));
}
