export function splitOrders(candidates, {brand, account_id}) {
  if (!brand || !account_id) throw new Error('Explicit brand/account required');
  const groups=new Map();
  for(const c of candidates){if(!c.先?.id)throw new Error('Resolved destination required');if(!c.a?.素材)throw new Error('creative required');if(!/^A\d{2}_H\d{2}_\S/.test(c.a.名))throw new Error('Mapped A/H name required');const key=c.先.id;if(!groups.has(key))groups.set(key,{口座:brand,act:account_id,配信:false,adset:{id:key},ads:[]});groups.get(key).ads.push({name:c.a.名,creative_id:c.a.素材,status:'PAUSED'});}
  return [...groups.values()];
}
export function budgetSteps(current,target,increase){
  if(!Number.isFinite(current)||current<=0||!Number.isFinite(target)||target<current||!(increase>0&&increase<=0.3))throw new Error('Invalid budget/increase');
  const out=[];for(let x=current;x<target;){x=Math.min(target,Math.max(x+1,Math.floor(x*(1+increase))));out.push(x);if(out.length>1000)throw new Error('Budget sequence too long');}return out;
}
export function applyMetrics(ads,material,brand,start,end){
  if(material?.brand!==brand || JSON.stringify(material.period)!==JSON.stringify([start,end]) || material.source!=='shopify')throw new Error('Brand/source/exact period mismatch');
  for(const a of ads){const v=material.ads?.find(x=>x.id===a.ID);if(!v||!Number.isFinite(v.orders)||!Number.isFinite(v.revenue)||!v.daily)throw new Error(`Missing Shopify evidence for ${a.ID}`);a.件=v.orders;a.ROAS=a.費?v.revenue/a.費:0;a.日={};for(const [day,d]of Object.entries(v.daily)){if(d.orders==null||d.revenue==null||d.spend==null)throw new Error('Missing daily metrics');a.日[day]={件:d.orders,売:d.revenue,費:d.spend};}}
}
