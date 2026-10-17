import {parseDraft, remainingPlayers, movePlayer, dropPlayer, importOrder, validateBackup, normalizeName} from './draft.mjs';

const players = await (await fetch('./players.json')).json();
const KEY = 'basketball-draft-board-v1';
const writerId=crypto.randomUUID();
const extension = Boolean(globalThis.chrome?.storage?.local);
const read = async () => extension ? (await chrome.storage.local.get(KEY))[KEY] : JSON.parse(localStorage.getItem(KEY) || 'null');
const persist = async value => {
  if (extension) await chrome.storage.local.set({[KEY]:value});
  else localStorage.setItem(KEY,JSON.stringify(value));
};
const $ = id => document.getElementById(id);
let state = {version:1,order:players.map(p=>p.id),watch:[],notes:{},config:{leagueId:'9490871',season:'2027'},drafts:{}};
let view = 'available', timer, controller, generation = 0, connected = false, saveChain = Promise.resolve();
let feed = {phase:'disconnected', error:null, checked:null};
const pendingRenders = new WeakSet();
let draggedId = null;
let pointerDrag = null, dragFrame = null, dragGhost = null;
function clearDropIndicators() {
  document.querySelectorAll('.drop-before, .drop-after').forEach(row=>row.classList.remove('drop-before','drop-after'));
}
function finishDrag() {
  draggedId = null;
  const active=pointerDrag;
  pointerDrag=null;
  if(active?.handle.hasPointerCapture(active.pointerId))active.handle.releasePointerCapture(active.pointerId);
  cancelAnimationFrame(dragFrame);
  dragGhost?.remove();dragGhost=null;
  document.body.classList.remove('reordering');
  render();
}
function updateDragTarget() {
  if(!pointerDrag||!draggedId)return;
  const drag=pointerDrag;
  clearDropIndicators();
  drag.targetId=null;
  const target=document.elementFromPoint(drag.x,drag.y)?.closest('#players .player');
  if(target&&target.dataset.playerId!==draggedId) {
    const bounds=target.getBoundingClientRect();
    drag.after=drag.y>bounds.top+bounds.height/2;
    drag.targetId=target.dataset.playerId;
    target.classList.add(drag.after?'drop-after':'drop-before');
  }
  dragGhost.style.left=`${Math.min(drag.x+14,window.innerWidth-dragGhost.offsetWidth-10)}px`;
  dragGhost.style.top=`${drag.y+12}px`;
}
function animateDrag() {
  if(!pointerDrag||!draggedId)return;
  const y=pointerDrag.y;
  if(y<70)window.scrollBy(0,-12);
  else if(y>window.innerHeight-70)window.scrollBy(0,12);
  updateDragTarget();
  dragFrame=requestAnimationFrame(animateDrag);
}
function message(text) { $('message').textContent=text; $('message').hidden=!text; }
try {
  const saved = await read();
  if (saved) {
    const personal = validateBackup(saved,players);
    state = {...state,...personal,config:saved.config ?? state.config,drafts:saved.drafts ?? {}};
  }
} catch (e) { message(`Could not restore saved board: ${e.message}. Your stored copy has not been overwritten.`); }
function save() {
  $('save-status').textContent='Saving…';
  const snapshot = JSON.parse(JSON.stringify({...state,writerId}));
  saveChain = saveChain.catch(()=>{}).then(()=>persist(snapshot));
  saveChain.then(()=>{$('save-status').textContent='Saved in this browser';}).catch(e=>{
    $('save-status').textContent='Not saved — download a backup';
    message(`Save failed: ${e.message}. Export a backup before closing.`);
  });
  return saveChain;
}
const context = () => `${state.config.leagueId}:${state.config.season}`;
function draftState() { return state.drafts[context()] ?? {picks:[],overrides:{},checked:null}; }
function updateDraft(change) { state.drafts[context()] = {...draftState(),...change}; }
async function saveDraft() {
  const key=`basketball-draft-progress:${context()}`,snapshot=draftState();
  if(extension)await chrome.storage.local.set({[key]:snapshot});
  else localStorage.setItem(key,JSON.stringify(snapshot));
}
async function loadDraft() {
  const key=`basketball-draft-progress:${context()}`;
  try {
    const snapshot=extension?(await chrome.storage.local.get(key))[key]:JSON.parse(localStorage.getItem(key)||'null');
    if(snapshot)updateDraft(snapshot);
  } catch(error){message(`Could not restore draft progress: ${error.message}`);}
}
await loadDraft();
function syncPersonalBoard(value) {
  if(!value||value.writerId===writerId)return;
  try {Object.assign(state,validateBackup(value,players));render();}
  catch(error){message(`Another board has unreadable saved data: ${error.message}`);}
}
if(extension)chrome.storage.onChanged.addListener((changes,area)=>{if(area==='local'&&changes[KEY])syncPersonalBoard(changes[KEY].newValue);});
else window.addEventListener('storage',e=>{if(e.key===KEY&&e.newValue)syncPersonalBoard(JSON.parse(e.newValue));});
function node(tag, cls, text) { const el=document.createElement(tag); if(cls)el.className=cls; if(text!==undefined)el.textContent=text; return el; }
const statColumns=[['fg_pct','FG%'],['ft_pct','FT%'],['three_pm','3PM'],['points','PTS'],['rebounds','REB'],['assists','AST'],['steals','STL'],['blocks','BLK']];
function playerStats(player) {
  const wrap=node('div','player-stats'), table=node('table','category-table');
  table.setAttribute('aria-label',`${player.name} per-game Hashtag statistics`);
  const head=node('thead'), labels=node('tr');
  labels.append(node('th','','Per game'));
  for(const [,label] of statColumns)labels.append(node('th','',label));
  head.append(labels);table.append(head);
  const body=node('tbody');
  for(const [label,stats] of [['2025–26',player.actual],['2026–27 proj.',player.projected]]) {
    const row=node('tr'), season=node('th','',label);season.scope='row';row.append(season);
    if(!stats) {
      const missing=node('td','missing-stats','Not in saved Hashtag season table');missing.colSpan=8;row.append(missing);
    } else for(const [key] of statColumns) {
      const value=stats[key], cell=node('td',`grade-${stats.grades[key]||'neutral'}`);
      cell.append(node('span','stat-value',value==null?'—':key.endsWith('_pct')?(value*100).toFixed(1)+'%':value.toFixed(1)));
      if(key==='fg_pct'||key==='ft_pct') {
        const prefix=key==='fg_pct'?'fg':'ft', made=stats[`${prefix}m_pg_display`], attempted=stats[`${prefix}a_pg_display`];
        cell.append(node('small','attempts',`${made==null?'—':made.toFixed(1)} / ${attempted==null?'—':attempted.toFixed(1)}`));
        cell.title='Made / attempted per game';
      }
      row.append(cell);
    }
    body.append(row);
  }
  table.append(body);wrap.append(table);return wrap;
}
function renderStatus() {
  const draft = draftState();
  const age = feed.checked ? Math.floor((Date.now()-feed.checked)/1000) : null;
  const stale = connected && age!==null && age>15;
  let status = 'Waiting for the draft';
  if (feed.error) status = 'ESPN unavailable';
  else if (stale) status = 'Feed delayed';
  else if (!connected) status = 'Not connected';
  else if (feed.phase==='checking') status = 'Checking ESPN…';
  else if (feed.phase==='live') status = 'ESPN draft in progress';
  else if (feed.phase==='complete') status = 'ESPN draft complete';
  else if (feed.phase==='api-only') status = 'Live reader required';
  $('status').textContent = status;
  $('status-dot').className = `dot ${feed.error || stale || feed.phase==='api-only' ? 'error' : connected && feed.checked ? 'ok' : ''}`;
  $('connect').textContent = connected ? 'Disconnect' : 'Connect ESPN';
  let detail = 'Your rankings are saved locally. Connect to track picks.';
  if (feed.error) detail = `${feed.error} Showing last known picks; retrying.`;
  else if (!connected && draft.checked) detail = 'Saved picks only. Connect ESPN to refresh availability.';
  else if (feed.checked) detail = `Feed checked ${age}s ago · updates every ${feed.phase==='live'?'2':'10'} seconds.`;
  if(connected&&feed.source==='draft-room'&&!feed.error)detail=`Reading ESPN draft page · checked ${age}s ago · ${state.config.leagueId}.`;
  if(connected&&feed.phase==='api-only')detail='ESPN’s public API does not publish live picks. Open the draft room with the local extension loaded.';
  if(connected&&feed.unmatched)detail+=` ${feed.unmatched} pick record(s) could not be matched.`;
  $('sync-detail').textContent = detail;
  $('draft-date').textContent = draft.date ? `Draft: ${new Date(draft.date).toLocaleString([], {dateStyle:'medium',timeStyle:'short'})}` : '';
}
function render() {
  if (draggedId) { renderStatus(); return; }
  const draft=draftState(), available=remainingPlayers(players,state.order,draft.picks,draft.overrides);
  const availableIds=new Set(available.map(p=>p.id)), watch=new Set(state.watch), byId=new Map(players.map(p=>[p.id,p]));
  $('available-count').textContent=available.length;
  $('watch-count').textContent=available.filter(p=>watch.has(p.id)).length;
  $('pick-count').textContent=draft.picks.length;
  const search=normalizeName($('search').value), pos=$('position').value;
  const rows=state.order.map((id,index)=>({p:byId.get(id),rank:index+1})).filter(({p})=>
    (view==='all'||availableIds.has(p.id)) && (view!=='watch'||watch.has(p.id)) && (!pos||p.position.split(/[ ,/]+/).includes(pos)) && (!search||normalizeName(p.name).includes(search)));
  const container=$('players'); container.replaceChildren();
  for(const {p,rank} of rows) {
    const taken=!availableIds.has(p.id), row=node('article',`player${taken?' drafted':''}`), main=node('div','player-main');
    row.dataset.playerId=p.id;
    const handle=node('button','drag-handle','⠿');
    handle.type='button';
    handle.setAttribute('aria-label',`Drag ${p.name} to reorder`);
    handle.title='Drag to reorder, or use ↑ / ↓ while focused';
    handle.addEventListener('pointerdown',e=>{
      if(e.button!==0||pointerDrag)return;
      e.preventDefault();handle.focus();
      pointerDrag={handle,pointerId:e.pointerId,startX:e.clientX,startY:e.clientY,x:e.clientX,y:e.clientY,targetId:null};
      handle.setPointerCapture(e.pointerId);
    });
    handle.addEventListener('pointermove',e=>{
      if(!pointerDrag||pointerDrag.pointerId!==e.pointerId)return;
      pointerDrag.x=e.clientX;pointerDrag.y=e.clientY;
      if(!draggedId&&Math.hypot(e.clientX-pointerDrag.startX,e.clientY-pointerDrag.startY)>5) {
        draggedId=p.id;
        row.classList.add('dragging');document.body.classList.add('reordering');
        dragGhost=node('div','drag-ghost',p.name);dragGhost.setAttribute('aria-hidden','true');document.body.append(dragGhost);
        animateDrag();
      }
      if(draggedId)updateDragTarget();
    });
    handle.addEventListener('pointerup',e=>{
      if(!pointerDrag||pointerDrag.pointerId!==e.pointerId)return;
      pointerDrag.x=e.clientX;pointerDrag.y=e.clientY;
      if(draggedId)updateDragTarget();
      if(draggedId&&pointerDrag.targetId) {
        state.order=dropPlayer(state.order,draggedId,pointerDrag.targetId,pointerDrag.after);
        save();
        $('reorder-status').textContent=`${p.name} moved to rank ${state.order.indexOf(p.id)+1}.`;
      }
      finishDrag();
    });
    handle.addEventListener('pointercancel',()=>{if(pointerDrag)finishDrag();});
    handle.addEventListener('lostpointercapture',()=>{if(pointerDrag)finishDrag();});
    handle.addEventListener('keydown',e=>{
      if(e.key==='Escape'&&pointerDrag){finishDrag();return;}
      if(e.key!=='ArrowUp'&&e.key!=='ArrowDown')return;
      e.preventDefault();
      const index=rows.findIndex(({p:player})=>player.id===p.id);
      const target=rows[index+(e.key==='ArrowUp'?-1:1)];
      if(!target)return;
      state.order=dropPlayer(state.order,p.id,target.p.id,e.key==='ArrowDown');
      save();render();
      $('reorder-status').textContent=`${p.name} moved to rank ${state.order.indexOf(p.id)+1}.`;
      document.querySelector(`[data-player-id="${p.id}"] .drag-handle`)?.focus();
    });
    const rankInput=node('input','rank'); rankInput.type='number';rankInput.min=1;rankInput.max=players.length;rankInput.value=rank;rankInput.setAttribute('aria-label',`Rank for ${p.name}`);
    const rankForm=node('form','rank-form'), move=node('button','move','↵');
    move.setAttribute('aria-label',`Move ${p.name} to rank`); move.title='Apply rank';
    rankForm.append(rankInput,move);
    rankForm.addEventListener('submit',e=>{e.preventDefault();state.order=movePlayer(state.order,p.id,rankInput.value);save();render();});
    const identity=node('div','identity');identity.append(node('span','name',p.name),node('span','meta',`${p.team} · ${p.position} · Hashtag #${p.sourceRank}`));
    const star=node('button',`star${watch.has(p.id)?' on':''}`,watch.has(p.id)?'★':'☆');star.setAttribute('aria-label',`Watch ${p.name}`);star.setAttribute('aria-pressed',String(watch.has(p.id)));
    star.addEventListener('click',()=>{state.watch=watch.has(p.id)?state.watch.filter(id=>id!==p.id):[...state.watch,p.id];save();render();});
    const toggle=node('button','taken',taken?'Restore':'Taken');toggle.title=taken?'Mark available manually':'Mark drafted manually';toggle.setAttribute('aria-label',`${taken?'Restore':'Mark taken'} ${p.name}`);
    toggle.addEventListener('click',()=>{updateDraft({overrides:{...draftState().overrides,[p.id]:!taken}});save();render();});
    main.append(handle,rankForm,identity,star,toggle);
    const notes=node('details','notes'), summary=node('summary','',state.notes[p.id]?'Edit note':'Add note'), input=node('textarea');input.rows=2;input.value=state.notes[p.id]??'';input.setAttribute('aria-label',`Note for ${p.name}`);
    input.addEventListener('input',()=>{state.notes[p.id]=input.value;summary.textContent=input.value?'Edit note':'Add note';save();});
    notes.append(summary,input);row.append(main,playerStats(p),notes);container.append(row);
  }
  if(!rows.length)container.append(node('div','empty',view==='watch'?'No available targets. Star players to build your watchlist.':'No players match this view.'));
  renderStatus();
}
async function poll(run) {
  if(!connected || run!==generation)return;
  controller=new AbortController();
  const timeout=setTimeout(()=>controller?.abort(),10000);
  try {
    const config={...state.config};
    if(!/^\d+$/.test(config.leagueId)||!/^\d{4}$/.test(config.season))throw new Error('Check the league ID and season in settings.');
    let draft,checked;
    if(extension) {
      const key=`espn-room:${config.leagueId}:${config.season}`;
      const room=(await chrome.storage.local.get(key))[key];
      if(room&&Date.now()-room.checked<10000) {
        draft={picks:room.picks,phase:'live'};checked=room.checked;
        feed={phase:'live',source:'draft-room',checked,error:null,unmatched:room.unmatched};
      }
    }
    if(!draft) {
    const url=new URL(`https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/${config.season}/segments/0/leagues/${config.leagueId}`);
    url.searchParams.append('view','mDraftDetail');url.searchParams.append('view','mSettings');
    const response=await fetch(url,{signal:controller.signal,cache:'no-store'});
    if(!response.ok)throw new Error(`ESPN returned ${response.status}. ${response.status===401||response.status===403?'This league may require signed-in access.':''}`);
    draft=parseDraft(await response.json(),config);
    if(draft.phase==='live')draft.phase='api-only';
    checked=Date.now();
    feed={phase:draft.phase,source:'api',error:null,checked};
    }
    if(!connected||run!==generation)return;
    if(draft.phase==='api-only')draft.picks=draftState().picks;
    const changed=JSON.stringify(draft.picks)!==JSON.stringify(draftState().picks);
    updateDraft({...draft,checked});
    await saveDraft();
    if(changed) {
      const active=document.activeElement;
      if(active?.tagName==='TEXTAREA'||active?.classList.contains('rank')) {
        if(!pendingRenders.has(active)) {
          pendingRenders.add(active);
          active.addEventListener('blur',()=>{pendingRenders.delete(active);render();},{once:true});
        }
        renderStatus();
      } else render();
    } else renderStatus();
  } catch(e) {
    if(!connected||run!==generation)return;
    feed.error=e.name==='AbortError'?'ESPN request timed out.':e.message==='Failed to fetch'?'Browser could not reach ESPN. Use the extension if browser cross-origin access is blocked.':e.message;
    renderStatus();
  } finally {
    clearTimeout(timeout);
    if(connected&&run===generation)timer=setTimeout(()=>poll(run),feed.phase==='live'?2000:10000);
  }
}
function disconnect(){connected=false;generation++;clearTimeout(timer);controller?.abort();feed.error=null;renderStatus();}
async function connect(useOpenRoom=true){
  disconnect();
  if(extension&&useOpenRoom) {
    const latest=(await chrome.storage.local.get('espn-latest-room'))['espn-latest-room'];
    if(latest&&Date.now()-latest.checked<10000) {
      state.config={leagueId:latest.leagueId,season:latest.season};
      $('league-id').value=latest.leagueId;$('season').value=latest.season;
      await loadDraft();await save();render();
    }
  }
  connected=true;feed={phase:'checking',error:null,checked:null};renderStatus();poll(generation);
}
$('connect').addEventListener('click',()=>connected?disconnect():connect());
$('league-id').value=state.config.leagueId;$('season').value=state.config.season;
$('settings').addEventListener('submit',async e=>{e.preventDefault();disconnect();state.config={leagueId:$('league-id').value.trim(),season:$('season').value.trim()};await loadDraft();save();render();connect(false);});
$('search').addEventListener('input',render);$('position').addEventListener('change',render);
document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{view=button.dataset.view;document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b===button));render();}));
$('apply-order').addEventListener('click',()=>{try{state.order=importOrder($('ranking-import').value,players,state.order);save();message('Your ranking order has been applied.');render();}catch(e){message(e.message);}});
function exportBackup(){
  const blob=new Blob([JSON.stringify({...state,exportedAt:new Date().toISOString()},null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download='my-basketball-rankings.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
$('export').addEventListener('click',exportBackup);
$('top-export').addEventListener('click',exportBackup);
$('restore').addEventListener('change',async e=>{try{
  const file=e.target.files[0];if(!file)return;
  const data=validateBackup(JSON.parse(await file.text()),players);
  state={...state,...data};await save();message('Rankings, watchlist, and notes restored.');render();
}catch(e){message(`Restore failed: ${e.message}`);}finally{e.target.value='';}});
$('clear-overrides').addEventListener('click',()=>{updateDraft({overrides:{}});save();render();});
$('full-board').href=extension?chrome.runtime.getURL('panel.html'):location.href;
setInterval(renderStatus,1000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&connected){clearTimeout(timer);generation++;controller?.abort();poll(generation);}});
render();
