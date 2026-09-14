(()=>{
  const D=window.WOW_DATA||{},M=D.pvpMechanics?.v010,mp=D.pvpProfiles?.mage_frost_gnome_p6_core,rp=D.pvpProfiles?.rogue_sub_undead_p6_static;
  if(mp){
    // 1213 base mana + [20 + (355-20)*15] from Intellect = 6258.
    // Previous 6257 aggregate was off by one against the verified Classic formula/base mana table.
    mp.stats.mana=6258;
    mp.statAudit={
      version:'v0.11',
      baseMana:1213,
      finalIntellect:355,
      manaFromIntellect:5045,
      expectedMana:6258,
      status:'PASS',
      note:'Corrected from imported aggregate 6257 after independent formula audit.'
    };
  }
  if(M){
    M.bonescythe2p={piecesRequired:2,healMin:90,healMax:110,ppm:1,status:'VERIFIED_NOT_YET_ACTIVE',source:'WoWSims Classic sim/rogue/items_sets_pve.go — PPM: 1'};
    M.crusader={spellId:20034,strength:100,healMin:75,healMax:125,durationMs:15000,ppm:1,status:'VERIFIED_NOT_YET_ACTIVE',source:'WoWSims Classic sim/common/enchant_effects.go — NewPPMManager(1.0)'};
  }
  if(rp){
    rp.verifiedDynamics=Object.assign({},rp.verifiedDynamics,{bonescythe2pPPM:1,crusaderPPM:1});
    rp.calibrationRequired=['binary poison resistance vs target Nature resistance'];
    rp.verifiedNotYetActive=['Bonescythe 2p Invigorate 1 PPM','Crusader 1 PPM'];
  }
})();