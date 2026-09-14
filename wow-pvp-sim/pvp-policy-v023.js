(()=>{
  const D=window.WOW_DATA=window.WOW_DATA||{},duel=window.WOW_DUEL;
  if(!duel?.defaultRoguePolicy)return;
  D.roguePolicyChampion={
    ...duel.defaultRoguePolicy,
    id:'rogue_cb_hemo_champion_g3_evis4_pool65',
    version:4,
    evisMinCp:4,
    hemoMinEnergy:65,
    evidence:{
      matchup:'Undead Rogue Subtlety CB/Hemo vs Gnome Frost Mage',
      method:'paired deterministic seeds / identical RNG seeds for champion and challenger',
      generations:[
        {change:'evisMinCp 5 -> 4',seeds:1000,beforeWins:838,afterWins:892,beforeWinRatePct:83.8,afterWinRatePct:89.2,deltaWinRatePct:5.4},
        {change:'hemoMinEnergy 35 -> 55',seeds:1000,beforeWins:892,afterWins:920,beforeWinRatePct:89.2,afterWinRatePct:92.0,deltaWinRatePct:2.8},
        {change:'hemoMinEnergy 55 -> 65',seeds:1000,beforeWins:920,afterWins:930,beforeWinRatePct:92.0,afterWinRatePct:93.0,deltaWinRatePct:1.0}
      ],
      status:'PROMOTED_G3'
    }
  };
})();
