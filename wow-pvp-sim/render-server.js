const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname);
const port = Number(process.env.PORT || 10000);
const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.lua': 'text/plain; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon'
};

const vendorCache = new Map();
function fetchRemote(url, redirects, cb) {
  if (redirects < 0) return cb(new Error('too many redirects'));
  const request = https.get(url, {headers:{'user-agent':'wow-pvp-simulator-preview'}}, r => {
    if (r.statusCode >= 300 && r.statusCode < 400 && r.headers.location) {
      r.resume();
      return fetchRemote(new URL(r.headers.location, url).toString(), redirects - 1, cb);
    }
    if (r.statusCode !== 200) { r.resume(); return cb(new Error('upstream HTTP ' + r.statusCode)); }
    const chunks = [];
    r.on('data', c => chunks.push(c));
    r.on('end', () => cb(null, Buffer.concat(chunks)));
  });
  request.setTimeout(8000, () => request.destroy(new Error('upstream timeout')));
  request.on('error', cb);
}

http.createServer((req, res) => {
  let pathname;
  try { pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname); }
  catch { res.writeHead(400).end('Bad request'); return; }

  if (pathname === '/vendor/fengari-web.js') {
    const key = 'fengari-web-0.1.4';
    const cached = vendorCache.get(key);
    if (cached) {
      res.writeHead(200, {'content-type':'application/javascript; charset=utf-8','cache-control':'public, max-age=86400'});
      res.end(cached); return;
    }
    fetchRemote('https://cdn.jsdelivr.net/npm/fengari-web@0.1.4/dist/fengari-web.js', 3, (err, body) => {
      if (err) { res.writeHead(502, {'content-type':'text/plain; charset=utf-8'}).end('Vendor fetch failed: '+err.message); return; }
      vendorCache.set(key, body);
      res.writeHead(200, {'content-type':'application/javascript; charset=utf-8','cache-control':'public, max-age=86400'});
      res.end(body);
    });
    return;
  }

  if (pathname === '/') pathname = '/index.html';
  const filePath = path.resolve(root, '.' + pathname);
  if (!filePath.startsWith(root + path.sep) && filePath !== path.join(root, 'index.html')) {
    res.writeHead(403).end('Forbidden'); return;
  }

  fs.stat(filePath, (err, stat) => {
    if (err || !stat.isFile()) { res.writeHead(404, {'content-type': 'text/plain; charset=utf-8'}).end('Not found'); return; }
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, {'content-type': mime[ext] || 'application/octet-stream','cache-control': ext === '.html' ? 'no-store' : 'public, max-age=30'});
    fs.createReadStream(filePath).pipe(res);
  });
}).listen(port, '0.0.0.0', () => console.log(`WoW PvP Simulator preview listening on ${port}`));
