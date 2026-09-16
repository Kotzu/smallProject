const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const {runTraining, runVariant, runDuel} = require('./headless-runner');

const root = path.resolve(__dirname);
const port = Number(process.env.PORT || 10000);
const mime = {'.html':'text/html; charset=utf-8','.js':'application/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.lua':'text/plain; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp','.ico':'image/x-icon'};
const vendorCache = new Map();
let trainingCache={status:'pending',stage:'screen',screenCount:100,validationCount:1000,seed:1337};

function fetchRemote(url, redirects, cb) {
  if (redirects < 0) return cb(new Error('too many redirects'));
  const request = https.get(url, {headers:{'user-agent':'wow-pvp-simulator-preview'}}, r => {
    if (r.statusCode >= 300 && r.statusCode < 400 && r.headers.location) {r.resume();return fetchRemote(new URL(r.headers.location,url).toString(),redirects-1,cb);}
    if (r.statusCode !== 200) {r.resume();return cb(new Error('upstream HTTP '+r.statusCode));}
    const chunks=[];r.on('data',c=>chunks.push(c));r.on('end',()=>cb(null,Buffer.concat(chunks)));
  });
  request.setTimeout(8000,()=>request.destroy(new Error('upstream timeout')));request.on('error',cb);
}
function sendJson(res,status,value){const body=JSON.stringify(value);res.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store','content-length':Buffer.byteLength(body)});res.end(body);}

function computeDefaultTraining(){
  const started=Date.now();
  try{
    const screen=runTraining(100,1337);
    const bestIndex=screen.best?.index ?? 0;
    trainingCache={status:'validating',stage:'validate-best',screen,seed:1337,bestIndex,elapsedMs:Date.now()-started};
    console.log('ROGUE_SCREEN_READY '+JSON.stringify({deterministic:screen.deterministic,best:screen.best,elapsedMs:trainingCache.elapsedMs}));
    setTimeout(()=>{
      const vStarted=Date.now();
      try{
        const validation=runVariant(bestIndex,1000,1337);
        trainingCache={status:'ready',stage:'complete',screen,validation,seed:1337,elapsedMs:(Date.now()-started),scope:'Rogue CB/Hemo vs Frost Mage; paired seeds; decision-policy only'};
        console.log('ROGUE_VALIDATION_READY '+JSON.stringify({deterministic:validation.deterministic,result:validation.result,elapsedMs:Date.now()-vStarted,totalElapsedMs:trainingCache.elapsedMs}));
      }catch(err){trainingCache={status:'error',stage:'validation',screen,message:String(err?.stack||err)};console.error('ROGUE_VALIDATION_FAILED '+trainingCache.message);}
    },50);
  }catch(err){trainingCache={status:'error',stage:'screen',message:String(err?.stack||err),elapsedMs:Date.now()-started};console.error('ROGUE_SCREEN_FAILED '+trainingCache.message);}
}

const server=http.createServer((req,res)=>{
  let parsed,pathname;try{parsed=new URL(req.url,'http://localhost');pathname=decodeURIComponent(parsed.pathname);}catch{res.writeHead(400).end('Bad request');return;}
  if(pathname==='/api/rogue-training-status')return sendJson(res,200,trainingCache);
  if(pathname==='/api/rogue-variant'){
    try{const index=Math.max(0,Math.min(7,Math.trunc(Number(parsed.searchParams.get('index'))||0))),count=Math.max(100,Math.min(2500,Math.trunc(Number(parsed.searchParams.get('count'))||1000))),seed=(Number(parsed.searchParams.get('seed'))||1337)>>>0;return sendJson(res,200,runVariant(index,count,seed));}
    catch(err){return sendJson(res,500,{error:'VARIANT_FAILED',message:String(err?.stack||err)});}
  }
  if(pathname==='/api/rogue-train'){
    try{const count=Math.max(50,Math.min(500,Math.trunc(Number(parsed.searchParams.get('count'))||100))),seed=(Number(parsed.searchParams.get('seed'))||1337)>>>0;return sendJson(res,200,runTraining(count,seed));}
    catch(err){return sendJson(res,500,{error:'TRAINING_FAILED',message:String(err?.stack||err)});}
  }
  if(pathname==='/api/duel'){
    try{const seed=(Number(parsed.searchParams.get('seed'))||1337)>>>0;return sendJson(res,200,runDuel(seed));}
    catch(err){return sendJson(res,500,{error:'DUEL_FAILED',message:String(err?.stack||err)});}
  }
  if(pathname==='/vendor/fengari-web.js'){
    const key='fengari-web-0.1.4',cached=vendorCache.get(key);if(cached){res.writeHead(200,{'content-type':'application/javascript; charset=utf-8','cache-control':'public, max-age=86400'});res.end(cached);return;}
    fetchRemote('https://cdn.jsdelivr.net/npm/fengari-web@0.1.4/dist/fengari-web.js',3,(err,body)=>{if(err){res.writeHead(502,{'content-type':'text/plain; charset=utf-8'}).end('Vendor fetch failed: '+err.message);return;}vendorCache.set(key,body);res.writeHead(200,{'content-type':'application/javascript; charset=utf-8','cache-control':'public, max-age=86400'});res.end(body);});return;
  }
  if(pathname==='/')pathname='/index.html';
  if(pathname==='/index.html'){
    const indexPath=path.join(root,'index.html');
    fs.readFile(indexPath,'utf8',(err,html)=>{
      if(err){res.writeHead(404,{'content-type':'text/plain; charset=utf-8'}).end('Not found');return;}
      const body=html.includes('armory-3d.js')?html:html.replace('</body>','<script src="armory-3d.js"></script>\n</body>');
      res.writeHead(200,{'content-type':'text/html; charset=utf-8','cache-control':'no-store','content-length':Buffer.byteLength(body)});res.end(body);
    });
    return;
  }
  const filePath=path.resolve(root,'.'+pathname);if(!filePath.startsWith(root+path.sep)&&filePath!==path.join(root,'index.html')){res.writeHead(403).end('Forbidden');return;}
  fs.stat(filePath,(err,stat)=>{if(err||!stat.isFile()){res.writeHead(404,{'content-type':'text/plain; charset=utf-8'}).end('Not found');return;}const ext=path.extname(filePath).toLowerCase();res.writeHead(200,{'content-type':mime[ext]||'application/octet-stream','cache-control':ext==='.html'?'no-store':'public, max-age=30'});fs.createReadStream(filePath).pipe(res);});
});
server.listen(port,'0.0.0.0',()=>{console.log(`WoW PvP Simulator preview listening on ${port}`);setTimeout(computeDefaultTraining,750);});
