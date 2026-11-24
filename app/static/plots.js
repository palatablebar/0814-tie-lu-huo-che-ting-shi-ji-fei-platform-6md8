import {element} from './client.js';

function zone(target, className, text) {
  const box = element('div', undefined, {class:className});
  if (text) box.append(element('span',text));
  target.append(box);
  return box;
}

export function visualize(report, selected) {
  const target = document.querySelector('#visual');
  const row = report.cases?.find(item=>item.case===selected);
  target.replaceChildren();
  if (!row) { target.append(element('p','该分组暂无计算值')); return; }
  if (row.bill) return renderBill(target, row);
  if (!row.measure) { target.append(element('p','该分组暂无计算值')); return; }
  const {evidence:e, value, unit} = row.measure;
  renderTiers(target, e, value, unit);
}

function renderBill(target, row) {
  const bill = row.bill;
  const stages = zone(target,'freight-tiers');
  const max = Math.max(1, ...bill.segments.map(s=>s.minutes));
  if (!bill.segments.length) {
    zone(target,'freight-charge','无可计费分段（免计/暂停已全额扣除或费率缺失）');
    return;
  }
  for (const segment of bill.segments) {
    const card = zone(stages,'freight-rate',`分段 ${segment.key} · ${segment.rate_cents} 分/分钟`);
    const mark = zone(card,'mark-piece',`${segment.minutes} min`);
    mark.style.setProperty('--part', `${Math.max(0,Math.min(100,100*segment.minutes/max))}%`);
    card.append(element('strong',`${segment.minutes} min · ${segment.amount_cents} 分`));
  }
  const blocked = bill.blocks.length ? ` · 挡签 ${bill.blocks.length} 条` : '';
  zone(target,'freight-charge',`分段金额合计 ${bill.amount_cents} 分${blocked}`);
}

function renderTiers(target,e,value,unit) {
  const stages=zone(target,'freight-tiers');
  for(const [i,fee] of [1,3,5].entries()) {
    const mins=e[`tier_${i+1}_min`];
    const card=zone(stages,'freight-rate',`档 ${i+1} · ${fee} 分/分钟`);
    card.append(element('strong',`${mins} min`));
  }
  zone(target,'freight-charge',`停时费用 ${value} 分`);
}
