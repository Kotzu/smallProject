window.WOW_CHARACTER_DATA={
  source:{
    primaryStats:"CMaNGOS mangos-classic sql/archive/0.8/4537_player_levelstats.sql; HP/mana columns from that old table are intentionally ignored because CMaNGOS later split class base HP/mana into player_classlevelstats.",
    classBase:"CMaNGOS mangos-classic sql/archive/0.12.2/z0144_xxx_01_mangos_player_classlevelstats.sql",
    formulas:"CMaNGOS mangos-classic src/game/Entities/StatSystem.cpp"
  },
  level60:{
    undeadRogue:{
      race:"Undead",class:"Rogue",raceId:5,classId:4,level:60,
      createStats:{str:81,agi:132,sta:77,int:33,spi:56},
      classBase:{health:1523,mana:0},
      racialCombat:{shadowResistance:10,willOfTheForsaken:true},
      verified:true
    },
    gnomeMage:{
      race:"Gnome",class:"Mage",raceId:7,classId:8,level:60,
      createStats:{str:25,agi:38,sta:44,int:132,spi:123},
      classBase:{health:1360,mana:1273},
      racialCombat:{expansiveMindIntPct:5,escapeArtist:true,arcaneResistance:10},
      verified:true,
      note:"Expansive Mind is kept as a separate modifier; raw createStats are not pre-multiplied here."
    }
  }
};
