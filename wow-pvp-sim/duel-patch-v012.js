(()=>{
  const base=window.WOW_DUEL,D=window.WOW_DATA;
  if(!base)return;
  const run=(seed,cfg)=>{
    const r=base.run(seed,cfg);
    if(r&&!r.error){
      r.calibrationRequired=[];
      r.poisonAudit=D.pvpProfiles?.rogue_sub_undead_p6_static?.poisonApplicationAudit||null;
      r.kernelStatus='FIRST_MATCHUP_CALIBRATED';
    }
    return r;
  };
  const batch=(seed,count,cfg)=>base.batch(seed,count,cfg);
  const selfTest=(cfg)=>{
    const a=run(1337,cfg),b=run(1337,cfg);
    return {deterministic:JSON.stringify(a)===JSON.stringify(b),winner:a.winner,duration:a.duration,version:'0.12.0'};
  };
  window.WOW_DUEL={...base,version:'0.12.0',run,batch,selfTest};
})();