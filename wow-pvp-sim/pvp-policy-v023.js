(()=>{
  const D=window.WOW_DATA=window.WOW_DATA||{},duel=window.WOW_DUEL;
  if(!duel?.defaultRoguePolicy)return;
  D.roguePolicyChampion={
    ...duel.defaultRoguePolicy,
    id:'rogue_cb_hemo_champion_g1_evis4',
    version:2,
    evisMinCp:4,
    evidence:{
      matchup:'Undead Rogue Subtlety CB/Hemo vs Gnome Frost Mage',
      method:'paired deterministic seeds / same RNG seeds for champion and challenger',
      seeds:1000,
      seedBase:1337,
      previousRogueWinRatePct:83.8,
      promotedRogueWinRatePct:89.2,
      deltaWinRatePct:5.4,
      previousWins:838,
      promotedWins:892,
      status:'PROMOTED'
    }
  };
})();
