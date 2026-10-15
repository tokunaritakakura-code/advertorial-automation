import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
export const hash = x => createHash('sha256').update(typeof x==='string'||Buffer.isBuffer(x)?x:canonical(x)).digest('hex');
export function canonical(x){if(Array.isArray(x))return '['+x.map(canonical).join(',')+']';if(x&&typeof x==='object')return '{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical(x[k])).join(',')+'}';return JSON.stringify(x);}
export function requireThat(ok,msg){if(!ok)throw Error(msg);}
export const nonempty=x=>typeof x==='string'&&x.trim().length>0;
export const ROLES={brand:'ブランドマネージャー',hq:'本部長',lead:'クリエイティブディレクター',strategy:'クリエイティブ・ストラテジスト',copy:'コピーライター',voice:'吹き替えディレクター',assets:'映像編集者',generate:'生成アーティスト',review:'編集長'};
// Each stage has one maker and one accountable role. Routing never grants tool access.
export const STAGES={
 brand:{role:ROLES.brand,deps:[],what:'ブランドの8欄発注書',where:'案件記録',how:'明示入力を確認し発注する'},
 hq:{role:ROLES.hq,deps:['brand'],what:'部への引き継ぎ',where:'案件記録',how:'発注を担当部へ渡す'},
 lead:{role:ROLES.lead,deps:['hq'],what:'担当・入力・出口条件の作業発注',where:'案件記録',how:'必要な役だけに発注する'},
 reference:{role:ROLES.strategy,deps:['lead'],what:'原本・選定理由・出所表',where:'ブラウザ / 案件記録',how:'全尺の出所・国・言語・権利を記録'},
 decomposition:{role:ROLES.strategy,deps:['reference'],what:'秒数付きシーン表',where:'参考再生 / 案件記録',how:'画角・動作・切替・字幕・音楽・効果音を同じ時間軸に記録'},
 approach:{role:ROLES.lead,deps:['decomposition'],what:'方式・シーン仕様・意図した変更',where:'案件記録',how:'制作前に方式と許容差を固定する'},
 transcript:{role:ROLES.copy,deps:['approach'],parent:'literal',substep:'transcript',what:'時刻・行番号・原文',where:'台本 / 案件記録',how:'聞き取れない所を推測せず全文を起こす'},
 literal:{role:ROLES.copy,deps:['transcript'],parent:'literal',substep:'translate',what:'原文・直訳・言葉の働き',where:'台本 / 案件記録',how:'全文を行と秒数で対応させる'},
 script_language:{role:ROLES.copy,deps:['literal'],parent:'script',substep:'language',what:'短い日本語・変更理由',where:'台本 / 案件記録',how:'不自然な箇所だけ自然化する'},
 script:{role:ROLES.copy,deps:['script_language'],parent:'script',substep:'alignment',what:'本文固定・行別照合結果・成果物パス',where:'script / 案件記録',how:'言語工程の本文を変えず直訳との意味・強調・秒数を照合して記録する'},
 voice:{role:ROLES.voice,deps:['script'],what:'実音声・時刻・聞き取り検査',where:'明示した音声環境',how:'確定台本を再利用または明示承認された環境で収録'},
 assets:{role:ROLES.assets,deps:['approach'],what:'シーン別固定素材と検査',where:'Movies/CapCut素材/<brand>/<job>/r<revision>',how:'実物と動きを照合し不足は部長へ戻す'},
 edit:{role:ROLES.assets,deps:['voice','assets'],what:'CapCut原本・CapCut書出しMP4',where:'CapCut',how:'CapCutで編集・字幕・効果・音を調整し書き出す'},
 delivery:{role:ROLES.lead,deps:['edit'],what:'審査済み版の納品記録',where:'案件記録 / CapCut',how:'独立審査の同じ版だけを本部とブランドへ返す'}
};
export const ENTRIES={vsl:'reference',reference:'reference',decomposition:'decomposition',script:'script_language',literal:'transcript',dubbing:'voice',voice:'voice',assets:'assets',editing:'edit',edit:'edit',review:'edit',repair:'edit'};
export const MEDIA=new Set(['voice','assets','edit']);
export function context(x,brands){requireThat(x&&Object.hasOwn(brands,x.brand),'explicit registered brand required');requireThat(/^[A-Za-z0-9_-]{1,100}$/.test(x.job_id||''),'job_id required');requireThat(Number.isSafeInteger(x.revision)&&x.revision>0,'integer revision required');return {brand:x.brand,job_id:x.job_id,revision:x.revision};}
export function under(file,root){const rel=path.relative(root,file);return rel===''||(!rel.startsWith('..'+path.sep)&&rel!=='..'&&!path.isAbsolute(rel));}
export function fileDigest(file,root){requireThat(path.isAbsolute(file)&&under(file,root),'artifact outside scope');let cursor=root;requireThat(fs.existsSync(root)&&!fs.lstatSync(root).isSymbolicLink(),'real root required');for(const segment of path.relative(root,file).split(path.sep).filter(Boolean)){cursor=path.join(cursor,segment);requireThat(!fs.lstatSync(cursor).isSymbolicLink(),'artifact symlink forbidden');}const st=fs.statSync(file);requireThat(st.isFile()&&st.nlink===1&&st.size<=1024*1024,'bounded regular artifact required');return hash(fs.readFileSync(file));}
export function manifest(x,brands){const c=context(x,brands);requireThat(Object.hasOwn(ENTRIES,x.entry),'known stage entry required');requireThat(Object.hasOwn(STAGES,x.target)&&x.target!=='brand'&&x.target!=='hq'&&x.target!=='lead','known target required');requireThat(['review','repair'].includes(x.entry)||closure(x.target).includes(ENTRIES[x.entry]),'target precedes requested stage entry');requireThat(x.policy?.additional_spend_ceiling_usd===0&&x.policy?.publication_allowed===false&&x.policy?.editing_application==='CapCut','zero-spend/no-publication/CapCut policy required');requireThat(nonempty(x.goal)&&x.brief&&['brand','metric','angle','reference','quantity_kind','landing','deadline','cost'].every(k=>nonempty(x.brief[k]))&&x.brief.brand===c.brand,'eight-field brand brief required');requireThat(!String(x.brief.cost).match(/^[1-9]/),'zero-cost scope required');requireThat(!x.job_id.startsWith('alcott_nonai_vsl_'),'stopped Alcott production excluded');if(x.entry==='repair')requireThat(x.repair&&!['brand','hq','lead'].includes(x.repair.stage)&&closure(x.target).includes(x.repair.stage)&&nonempty(x.repair.reason),'repair stage and reason required');return {...x,...c};}
function fields(o,keys,label){requireThat(o&&keys.every(k=>Object.hasOwn(o,k)),label+' missing fields: '+keys.filter(k=>!o||!Object.hasOwn(o,k)).join(','));}
const textFields=(o,keys,label)=>{fields(o,keys,label);requireThat(keys.every(k=>nonempty(o[k])),label+' nonempty fields required');};
const range=x=>Number.isFinite(x.start)&&Number.isFinite(x.end)&&x.start>=0&&x.end>x.start;
export function validateStage(stage,p,job,inputs={}){
 requireThat(Object.hasOwn(STAGES,stage)&&p&&typeof p==='object'&&!Array.isArray(p),'typed stage payload required');
 if(stage==='brand'){requireThat(canonical(p.brief)===canonical(job.brief),'brand must preserve exact brief');textFields(p,['goal','accountable','handoff'],'brand');requireThat(p.accountable===ROLES.brand,'brand accountable role');}
 if(stage==='hq'){requireThat(p.department==='creative'&&p.to===ROLES.lead,'HQ must route to creative lead');textFields(p,['handoff'],'HQ');}
 if(stage==='lead'){requireThat(Array.isArray(p.assignments)&&p.assignments.length>0,'lead assignments required');for(const a of p.assignments){requireThat(Object.hasOwn(STAGES,a.stage)&&a.role===STAGES[a.stage].role,'assignment role mismatch');textFields(a,['what','where','how','acceptance'],'assignment');}requireThat(p.accountable===ROLES.lead,'creative accountable role required');}
 if(stage==='reference'){textFields(p,['source_id','reason','source_country','target_country','language','rights_evidence'],'reference');requireThat(['own','managed','external'].includes(p.source),'reference source required');requireThat(['cleared','analysis_only','unknown'].includes(p.rights),'rights must be explicit');requireThat(Number.isFinite(p.duration)&&p.duration>0&&p.duration<=3600,'reference duration required');requireThat(p.full_duration_observed===true,'full reference observation required');}
 if(stage==='decomposition'){
  const r=inputs.reference;requireThat(r&&Array.isArray(p.scenes)&&p.scenes.length>0,'scene decomposition required');let end=0;
  for(const s of p.scenes){requireThat(range(s)&&Math.abs(s.start-end)<0.001,'scene gaps/overlaps rejected');textFields(s,['id','framing','placement','movement','cuts','motion','captions','speech','sound_effects','music_role','timing_evidence','provenance_evidence'],'scene');requireThat(['live_action','asset_edit','ai','mixed','unknown'].includes(s.production),'scene production type required');requireThat(Number.isFinite(s.confidence)&&s.confidence>=0&&s.confidence<=1,'production certainty required');requireThat(Array.isArray(s.audio_events)&&s.audio_events.every(e=>range(e)&&e.start>=s.start&&e.end<=s.end&&nonempty(e.role)),'timed audio events required');end=s.end;}
  requireThat(Math.abs(end-r.duration)<0.001&&new Set(p.scenes.map(s=>s.id)).size===p.scenes.length,'complete unique scene coverage required');
 }
 if(stage==='approach'){
  const d=inputs.decomposition;requireThat(d&&['original','assets','ai','mixed'].includes(p.method),'production approach required');requireThat(p.editing_application==='CapCut'&&Array.isArray(p.scenes)&&p.scenes.length===d.scenes.length,'CapCut per-scene specification required');
  requireThat(!d.scenes.some(s=>s.production==='unknown'),'unknown production provenance requires HUMAN, cannot pass');
  if(p.method==='original')requireThat(inputs.reference?.rights==='cleared','original footage requires cleared rights');
  for(const [i,s] of p.scenes.entries()){requireThat(s.id===d.scenes[i].id,'scene identity/order changed');textFields(s,['visuals','framing','movement','captions','sound','timing','evidence'],'scene specification');fields(s,['tolerance','intentional_substitutions'],'scene');requireThat(Array.isArray(s.intentional_substitutions)&&s.intentional_substitutions.every(x=>nonempty(x.reason)&&nonempty(x.change))&&s.tolerance&&['seconds','position_pixels'].every(k=>Number.isFinite(s.tolerance[k])&&s.tolerance[k]>=0),'predeclared tolerance/substitution required');if(['ai','mixed'].includes(p.method))textFields(s,['generation_environment','model_evidence'],'generation tools must be explicit');}
 }
 if(stage==='transcript'){requireThat(Array.isArray(p.lines)&&p.lines.length>0&&p.unheard_segments===0&&p.lines.every(l=>range(l)&&nonempty(l.id)&&nonempty(l.original))&&new Set(p.lines.map(l=>l.id)).size===p.lines.length,'complete timestamped original transcript required');}
 if(stage==='literal'){
  requireThat(Array.isArray(p.lines)&&p.lines.length>0,'literal lines required');for(const l of p.lines){requireThat(range(l),'line times required');textFields(l,['id','original','literal','rhetorical_function'],'literal line');requireThat(Array.isArray(l.emphasis)&&l.emphasis.every(e=>nonempty(e.source)&&nonempty(e.literal)&&nonempty(e.function)),'emphasis correspondence required');for(const word of ['actually','definitely'])if(new RegExp('\\b'+word+'\\b','i').test(l.original))requireThat(l.emphasis.some(e=>e.source.toLowerCase()===word),word+' emphasis missing');}requireThat(new Set(p.lines.map(l=>l.id)).size===p.lines.length&&p.unheard_segments===0,'no guessed/unheard transcript');if(inputs.transcript)requireThat(p.lines.length===inputs.transcript.lines.length&&p.lines.every((l,i)=>l.id===inputs.transcript.lines[i].id&&l.original===inputs.transcript.lines[i].original&&l.start===inputs.transcript.lines[i].start&&l.end===inputs.transcript.lines[i].end),'literal changed original transcript');
 }
 if(stage==='script'||stage==='script_language'){
  const original=inputs.literal;requireThat(original&&p.style==='simple_concise_japanese'&&p.lines?.length===original.lines.length,'simple aligned Japanese required');
  for(const [i,l] of p.lines.entries()){const source=original.lines[i];requireThat(l.id===source.id&&l.start===source.start&&l.end===source.end,'literal line identity/timing changed');textFields(l,['japanese','change_reason','rhetorical_function'],'script');requireThat(l.rhetorical_function===source.rhetorical_function,'rhetorical function changed');requireThat(Array.isArray(l.emphasis)&&l.emphasis.length===source.emphasis.length&&l.emphasis.every((e,j)=>e.source===source.emphasis[j].source&&nonempty(e.japanese)&&e.function===source.emphasis[j].function),'emphasis dropped');requireThat(['unchanged','awkward_japanese','own_product'].includes(l.change_kind),'only necessary naturalization permitted');}if(stage==='script'&&inputs.script_language){const {alignment,...body}=p;requireThat(canonical(body)===canonical(inputs.script_language),'alignment cannot silently rewrite language artifact; repair language substep');requireThat(alignment&&alignment.language_hash===hash(inputs.script_language)&&alignment.literal_hash===hash(inputs.literal)&&Array.isArray(alignment.checks)&&alignment.checks.length===p.lines.length,'bound per-line alignment report required');requireThat(alignment.checks.every((c,i)=>c.id===p.lines[i].id&&c.status==='OK'&&nonempty(c.timing_evidence)&&nonempty(c.meaning_evidence)&&nonempty(c.emphasis_evidence)),'every line needs timing/meaning/emphasis evidence');requireThat(alignment.artifact_paths&&Object.keys(inputs).every(k=>nonempty(alignment.artifact_paths[k])),'upstream artifact paths required');}
 }
 if(MEDIA.has(stage)){
  // LLM declarations cannot prove media was generated, listened to or edited. Host-owned adapter required.
  requireThat(p.verification?.host_verified===true&&nonempty(p.verification.adapter_run_id),'host verified media adapter required');
  requireThat(Array.isArray(p.files)&&p.files.length>0&&p.files.every(f=>nonempty(f.path)&&/^[a-f0-9]{64}$/.test(f.sha256)),'exact media file evidence required');
  if(stage==='voice'){requireThat(p.verification.full_audio_listened===true&&p.verification.script_hash===hash(inputs.script),'actual voice and script binding required');}
  if(stage==='assets'){requireThat(p.verification.approach_hash===hash(inputs.approach)&&p.verification.all_scenes_matched===true,'assets approach binding required');}
  if(stage==='edit'){requireThat(p.application==='CapCut'&&nonempty(p.project_name)&&p.verification.export_application==='CapCut'&&p.verification.full_audio_video_observed===true&&p.verification.voice_hash===hash(inputs.voice)&&p.verification.assets_hash===hash(inputs.assets),'actual CapCut project/export/input evidence required');}
 }
 if(stage==='delivery'){requireThat(p.publication_allowed===false&&nonempty(p.review_id)&&p.artifact_hash===hash(inputs.edit),'delivery requires exact independent review');}
 return p;
}
export function closure(target){const out=[];const walk=s=>{for(const d of STAGES[s].deps)walk(d);if(!out.includes(s))out.push(s);};walk(target);return out;}
export function executionContract(stage){requireThat(Object.hasOwn(STAGES,stage),'known contract stage required');const s=STAGES[stage];return {...s,owner:s.role,what:s.what,where:s.where,when:s.deps.length?'after accepted '+s.deps.join(', '):'after explicit registered brand/job/revision request',how:s.how,cautions:MEDIA.has(stage)?'No media execution without host verification and explicit requested environment; final editing/export in CapCut.':'Do not infer missing evidence, cross brand boundaries, or alter upstream meaning/policy.',acceptance:'validateStage('+stage+') plus exact-artifact independent review; unknown evidence is not PASS'};}
