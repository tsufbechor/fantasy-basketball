export function parseDraft(data, config) {
  if (String(data?.id) !== String(config.leagueId) || String(data?.seasonId) !== String(config.season) || !Array.isArray(data?.draftDetail?.picks)) {
    throw new Error('ESPN returned an unexpected league, season, or draft response.');
  }
  const detail = data.draftDetail;
  const picks = detail.picks.filter(p => Number.isSafeInteger(Number(p.playerId)) && Number(p.playerId) > 0)
    .map(p => ({playerId:String(p.playerId), pick:p.overallPickNumber ?? null, teamId:p.teamId ?? null}));
  return {picks, phase:detail.inProgress ? 'live' : detail.drafted ? 'complete' : 'waiting', date:data.settings?.draftSettings?.date ?? null};
}

export function parseRoomPick({name, image, info}) {
  const id=String(image ?? '').match(/\/players\/full\/(\d+)\.png/);
  const slot=String(info ?? '').match(/^R(\d+),\s*P(\d+)\b/);
  if(!id||!slot||!name?.trim()||Number(id[1])<=0||Number(slot[1])<=0||Number(slot[2])<=0)return null;
  return {playerId:id[1],name:name.trim(),round:Number(slot[1]),roundPick:Number(slot[2])};
}

export function mergeRoomPicks(previous, incoming) {
  const slots=new Map(previous.map(p=>[`${p.round}:${p.roundPick}`,p]));
  for(const pick of incoming)slots.set(`${pick.round}:${pick.roundPick}`,pick);
  return [...slots.values()].sort((a,b)=>a.round-b.round||a.roundPick-b.roundPick);
}

export function remainingPlayers(players, order, picks, overrides) {
  const taken = new Set(picks.map(p => String(p.playerId)));
  const byId = new Map(players.map(p => [p.id,p]));
  return order.filter(id => !(overrides[id] ?? taken.has(id))).map(id => byId.get(id)).filter(Boolean);
}

export function movePlayer(order, id, rank) {
  if (!order.includes(id)) return order;
  const next = order.filter(x => x !== id);
  next.splice(Math.max(0, Math.min(next.length, Math.floor(Number(rank) || 1)-1)), 0, id);
  return next;
}

export function dropPlayer(order, id, targetId, after) {
  const source = order.indexOf(id), target = order.indexOf(targetId);
  if (source < 0 || target < 0 || source === target) return order;
  return movePlayer(order, id, target + (after ? 1 : 0) - (source < target ? 1 : 0) + 1);
}

export function normalizeName(name) {
  return name.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]/g,'');
}

export function importOrder(text, players, current) {
  const names = new Map();
  for (const p of players) for (const name of [p.name,...(p.aliases ?? [])]) {
    const key = normalizeName(name);
    const ids = names.get(key) ?? new Set();
    ids.add(p.id); names.set(key,ids);
  }
  const ids = text.split(/\r?\n/).map(s => s.trim()).filter(Boolean).map(line => {
    const name = line.replace(/^\d+[.)\s-]+/,'').trim();
    const matches = names.get(normalizeName(name));
    if (!matches || matches.size !== 1) throw new Error(`Unknown or ambiguous player: ${name}`);
    return [...matches][0];
  });
  if (!ids.length) throw new Error('Paste at least one player name.');
  if (new Set(ids).size !== ids.length) throw new Error('Duplicate player in pasted rankings.');
  return [...ids,...current.filter(id=>!ids.includes(id))];
}

export function validateBackup(data, players) {
  const known = new Set(players.map(p=>p.id));
  const list = value => Array.isArray(value) && value.every(id=>known.has(id)) && new Set(value).size===value.length;
  const legacyIds = players.slice(0,200).map(p=>p.id);
  const legacyOrder = players.length===300 && list(data?.order) && data.order.length===200 && legacyIds.every(id=>data.order.includes(id));
  if (data?.version!==1 || !list(data.order) || (data.order.length!==players.length && !legacyOrder) || !list(data.watch)
    || !data.notes || typeof data.notes!=='object' || Array.isArray(data.notes)
    || Object.entries(data.notes).some(([id,note])=>!known.has(id)||typeof note!=='string')) {
    throw new Error('Invalid backup. Use a JSON backup exported from this player board.');
  }
  return {order:[...data.order,...players.map(p=>p.id).filter(id=>!data.order.includes(id))],watch:data.watch,notes:data.notes};
}
