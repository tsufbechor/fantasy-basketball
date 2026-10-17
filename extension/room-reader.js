(async () => {
  const {parseRoomPick,mergeRoomPicks}=await import(chrome.runtime.getURL('draft.mjs'));
  const params=new URL(location.href).searchParams;
  const leagueId=params.get('leagueId'),season=params.get('seasonId');
  if(!/^\d+$/.test(leagueId)||!/^\d{4}$/.test(season))return;
  const key=`espn-room:${leagueId}:${season}`;
  let picks=(await chrome.storage.local.get(key))[key]?.picks ?? [];
  let writing=false,scheduled=false,stopped=false;
  async function capture() {
    if(writing||stopped)return;
    if(!document.querySelector('h1')?.textContent.includes('ESPN Fantasy Basketball Draft'))return;
    writing=true;
    try {
      const records=[...document.querySelectorAll('li.pick-message__container')];
      const incoming=records.map(row=>parseRoomPick({
        name:row.querySelector('.playerinfo__playername')?.textContent,
        image:row.querySelector('img[src*="/players/full/"]')?.getAttribute('src'),
        info:row.querySelector('.pick-info')?.textContent,
      })).filter(Boolean);
      picks=mergeRoomPicks(picks,incoming);
      const checked=Date.now();
      const snapshot={leagueId,season,picks,checked,unmatched:records.length-incoming.length,source:'draft-room'};
      await chrome.storage.local.set({[key]:snapshot,'espn-latest-room':{leagueId,season,checked}});
    } catch(error) {
      stopped=true;observer.disconnect();clearInterval(heartbeat);
      console.warn('Draft board reader stopped. Reload the ESPN draft tab after reloading the extension.',error.message);
    } finally {writing=false;}
  }
  const observer=new MutationObserver(()=>{
    if(scheduled||stopped)return;
    scheduled=true;
    setTimeout(()=>{scheduled=false;capture();},100);
  });
  observer.observe(document.body,{childList:true,subtree:true,characterData:true});
  const heartbeat=setInterval(capture,1000);
  capture();
})();
