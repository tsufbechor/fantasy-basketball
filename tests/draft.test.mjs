import test from 'node:test';
import assert from 'node:assert/strict';
import { parseDraft, remainingPlayers, movePlayer, dropPlayer, importOrder, validateBackup, parseRoomPick, mergeRoomPicks } from '../extension/draft.mjs';

const players = [{id:'1', name:'Nikola Jokic'}, {id:'2', name:'Luka Doncic'}, {id:'3', name:'Dennis Schröder'}];
test('live room picks use exact ESPN headshot IDs and completed round/pick labels', () => {
  const pick=parseRoomPick({name:'Anthony Edwards',image:'https://a.espncdn.com/combiner/i?img=/i/headshots/nba/players/full/4594268.png&w=96',info:'R1, P1 - Team'});
  assert.deepEqual(pick,{playerId:'4594268',name:'Anthony Edwards',round:1,roundPick:1});
  assert.equal(parseRoomPick({name:'Player',image:'nomug.png',info:'R1, P1'}),null);
  assert.equal(parseRoomPick({name:'Player',image:'/players/full/123.png',info:'On the Clock'}),null);
});
test('room snapshots preserve earlier picks and replace corrected slots without duplicates', () => {
  const first={playerId:'1',name:'First',round:1,roundPick:1};
  const second={playerId:'2',name:'Second',round:1,roundPick:2};
  assert.deepEqual(mergeRoomPicks([first],[second,second]),[first,second]);
  assert.deepEqual(mergeRoomPicks([first,second],[{...first,playerId:'3'}]),[{...first,playerId:'3'},second]);
});
test('only selected players count, including picks outside our rankings', () => {
  const draft = parseDraft({id:9, seasonId:2027, draftDetail:{inProgress:true, picks:[{playerId:-1}, {playerId:2, overallPickNumber:1, teamId:4}, {playerId:999, overallPickNumber:2}] }}, {leagueId:'9', season:'2027'});
  assert.equal(draft.picks.length, 2);
  assert.equal(draft.phase, 'live');
  assert.deepEqual(remainingPlayers(players, ['3','2','1'], draft.picks, {}).map(p=>p.id), ['3','1']);
});
test('manual corrections override automatic availability', () => {
  assert.deepEqual(remainingPlayers(players, ['1','2','3'], [{playerId:'2'}], {'1':true,'2':false}).map(p=>p.id), ['2','3']);
});
test('a reset or reversed pick restores availability from the newest full snapshot', () => {
  assert.equal(remainingPlayers(players, ['1','2','3'], [], {}).length, 3);
});
test('reject wrong leagues, wrong seasons and malformed payloads', () => {
  for(const payload of [{}, {id:8,seasonId:2027,draftDetail:{picks:[]}}, {id:9,seasonId:2026,draftDetail:{picks:[]}}]) {
    assert.throws(()=>parseDraft(payload,{leagueId:'9',season:'2027'}));
  }
});
test('reordering preserves every player exactly once', () => {
  assert.deepEqual(movePlayer(['1','2','3'],'3',1), ['3','1','2']);
  assert.deepEqual(movePlayer(['1','2','3'],'1',3), ['2','3','1']);
});
test('dragging inserts before or after a player in either direction', () => {
  assert.deepEqual(dropPlayer(['1','2','3','4'],'1','3',false), ['2','1','3','4']);
  assert.deepEqual(dropPlayer(['1','2','3','4'],'1','3',true), ['2','3','1','4']);
  assert.deepEqual(dropPlayer(['1','2','3','4'],'4','2',false), ['1','4','2','3']);
  assert.deepEqual(dropPlayer(['1','2','3','4'],'4','2',true), ['1','2','4','3']);
});
test('dragging in a filtered list retains hidden players and ignores invalid drops', () => {
  const order=['1','hidden','2','3'];
  assert.deepEqual(dropPlayer(order,'3','1',false), ['3','1','hidden','2']);
  assert.deepEqual(dropPlayer(order,'2','2',true), order);
  assert.deepEqual(dropPlayer(order,'missing','1',false), order);
  assert.deepEqual(dropPlayer(order,'1','missing',false), order);
});
test('pasted rankings match accents and reject unknown/duplicate names before saving', () => {
  assert.deepEqual(importOrder('1. Dennis Schroder\n2. Nikola Jokic',players,['1','2','3']), ['3','1','2']);
  assert.throws(()=>importOrder('Unknown Player',players,['1','2','3']), /Unknown/);
  assert.throws(()=>importOrder('Nikola Jokic\nNikola Jokic',players,['1','2','3']), /Duplicate/);
});
test('backup validation rejects incomplete orders and corrupt personal data', () => {
  const valid={version:1,order:['3','1','2'],watch:['1'],notes:{'1':'Target'}};
  assert.deepEqual(validateBackup(valid,players).order,valid.order);
  for(const bad of [{...valid,order:['1','1','2']},{...valid,watch:['999']},{...valid,notes:{'1':3}}]) assert.throws(()=>validateBackup(bad,players));
});
test('expanding to 300 preserves a saved top 200 board and appends new players', () => {
  const expanded=Array.from({length:300},(_,i)=>({id:String(i+1)}));
  const saved={version:1,order:expanded.slice(0,200).map(p=>p.id).reverse(),watch:['7'],notes:{'7':'Target'}};
  const restored=validateBackup(saved,expanded);
  assert.deepEqual(restored.order,[...saved.order,...expanded.slice(200).map(p=>p.id)]);
  assert.deepEqual(restored.watch,saved.watch);
  assert.deepEqual(restored.notes,saved.notes);
  assert.throws(()=>validateBackup({...saved,order:[...saved.order.slice(0,199),'300']},expanded));
  assert.throws(()=>validateBackup({...saved,order:saved.order.slice(1)},expanded));
});
