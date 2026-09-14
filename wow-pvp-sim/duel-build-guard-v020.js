(()=>{
  const base=window.WOW_DUEL,T=window.WOW_TALENTS,A=window.WOW_ARMORY,F=window.WOW_FOREVER_TALENTS;
  if(!base||!T)return;
  const $=id=>document.getElementById(id);
  const CORE_VERSION=base.version;
  function cloneCfg(cfg){return {a:{...(cfg?.a||{})},b:{...(cfg?.b||{})},ruleset:cfg?.ruleset};}
  function selectedRuleset(cfg){return cfg?.ruleset||$('rulesetMode')?.value||'classic';}
  function normalize(cfg){
    const c=cloneCfg(cfg);c.ruleset=selectedRuleset(c);
    c.a.build=c.a.build||$('abuild')?.value||T.defaultBuild(c.a.class,c.a.spec);
    c.b.build=c.b.build||$('bbuild')?.value||T.defaultBuild(c.b.class,c.b.spec);
    return c;
  }
  function canRun(cfg){
    const c=normalize(cfg),g=base.canRun(c),ta=T.kernelAudit(c),missing=[...(g.missing||[]),...(ta.missing||[])];
    const aa=A?.audit?.(c.a),ab=A?.audit?.(c.b);
    if(aa&&!aa.pass)missing.push('Player A loadout/stat audit failed');
    if(ab&&!ab.pass)missing.push('Player B loadout/stat audit failed');
    if(c.ruleset==='forever'){
      missing.push(`Forever strict gate: current ${F?.snapshotDate||'pre-beta'} talent snapshot is loaded, but no calibrated Forever build/runtime exists yet`);
      missing.push('Classic talent builds are never silently reused as Forever builds');
    }
    const ready=g.ready&&ta.pass&&(!aa||aa.pass)&&(!ab||ab.pass)&&c.ruleset!=='forever';
    return {ready,missing:[...new Set(missing)],talents:ta,armory:{a:aa,b:ab},config:c,coreVersion:CORE_VERSION,ruleset:c.ruleset,foreverSnapshot:F?.id||null};
  }
  function run(seed,cfg){
    const c=normalize(cfg),gate=canRun(c);
    if(!gate.ready)return {error:'STRICT_DATA_GATE',missing:gate.missing,coreVersion:CORE_VERSION,ruleset:c.ruleset};
    const r=base.run(seed,c);
    if(r&&!r.error){
      r.ruleset='ClassicEra';
      r.talentDataset='ClassicEra calibrated';
      r.builds={a:{id:c.a.build,name:T.get(c.a.build)?.name,points:T.get(c.a.build)?.points,class:c.a.class,spec:c.a.spec,dataset:T.get(c.a.build)?.dataset||'ClassicEra'},b:{id:c.b.build,name:T.get(c.b.build)?.name,points:T.get(c.b.build)?.points,class:c.b.class,spec:c.b.spec,dataset:T.get(c.b.build)?.dataset||'ClassicEra'}};
      r.talentAudit={status:'PASS',a:gate.talents.a.reason,b:gate.talents.b.reason};
      r.loadoutAudit={a:gate.armory.a?.status||'N/A',b:gate.armory.b?.status||'N/A'};
      r.kernelStatus='ACTIVE_CLASSIC_TALENT_RUNTIME';r.engineCoreVersion=CORE_VERSION;
    }
    return r;
  }
  function batch(seed,count,cfg){
    const c=normalize(cfg),gate=canRun(c);
    if(!gate.ready)return {error:'STRICT_DATA_GATE',missing:gate.missing,coreVersion:CORE_VERSION,ruleset:c.ruleset};
    const b=base.batch(seed,count,c);if(b&&!b.error){b.ruleset='ClassicEra';b.builds={a:c.a.build,b:c.b.build};b.engineCoreVersion=CORE_VERSION;}return b;
  }
  function selfTest(cfg){
    const c=normalize(cfg),a=run(1337,c),b=run(1337,c);
    return {deterministic:JSON.stringify(a)===JSON.stringify(b),winner:a.winner,duration:a.duration,version:'0.28.0',engineCoreVersion:CORE_VERSION,builds:a.builds,ruleset:c.ruleset,talentRuntime:a.talentRuntime||null};
  }
  window.WOW_DUEL={...base,version:'0.28.0',engineCoreVersion:CORE_VERSION,canRun,run,batch,selfTest,normalizeConfig:normalize};
})();