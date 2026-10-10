"""
Minimal PC durum paylaşıcı.
Kurulum:  pip install psutil
Çalıştır: python pc_monitor.py
Telefondan: http://<PC_IP>:8080   (JSON için: /api)
"""
import json
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psutil

PORT = 8080
INTERVAL = 1.0  # saniye

data = {}


def gpu_info():
    """NVIDIA ekran kartı varsa bilgi döner, yoksa None."""
    try:
        flags = 0x08000000 if sys.platform == "win32" else 0  # pencere açma
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            timeout=2, creationflags=flags, stderr=subprocess.DEVNULL,
        ).decode().strip().splitlines()[0]
        u, t, mu, mt = [float(x) for x in out.split(",")]
        return {"load": u, "temp": t, "mem_used": mu, "mem_total": mt}
    except Exception:
        return None


def cpu_temp():
    try:
        temps = psutil.sensors_temperatures()
        for entries in temps.values():
            if entries:
                return entries[0].current
    except Exception:
        pass
    return None


def sampler():
    last = psutil.net_io_counters()
    last_t = time.time()
    psutil.cpu_percent(None)
    while True:
        time.sleep(INTERVAL)
        now = time.time()
        net = psutil.net_io_counters()
        dt = max(now - last_t, 0.001)
        down = (net.bytes_recv - last.bytes_recv) / dt
        up = (net.bytes_sent - last.bytes_sent) / dt
        last, last_t = net, now

        vm = psutil.virtual_memory()
        try:
            disk = psutil.disk_usage("C:\\" if sys.platform == "win32" else "/")
        except Exception:
            disk = None
        bat = psutil.sensors_battery()

        data.update({
            "host": socket.gethostname(),
            "cpu": psutil.cpu_percent(None),
            "cpu_temp": cpu_temp(),
            "ram": vm.percent,
            "ram_used": vm.used,
            "ram_total": vm.total,
            "disk": disk.percent if disk else None,
            "down": down,
            "up": up,
            "battery": bat.percent if bat else None,
            "plugged": bat.power_plugged if bat else None,
            "uptime": int(now - psutil.boot_time()),
            "gpu": gpu_info(),
            "ts": now,
        })


PAGE = """<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PC Durum</title><style>
:root{color-scheme:dark}
body{margin:0;padding:16px;background:#0f1115;color:#e6e6e6;font:16px system-ui,sans-serif}
h1{font-size:15px;font-weight:500;color:#8a93a5;margin:0 0 14px}
.c{background:#181b22;border-radius:12px;padding:12px 14px;margin-bottom:10px}
.r{display:flex;justify-content:space-between;font-size:14px;color:#8a93a5}
.r b{color:#fff;font-size:18px;font-weight:600}
.bar{height:6px;background:#262a33;border-radius:3px;margin-top:8px;overflow:hidden}
.bar i{display:block;height:100%;width:0;background:#4f8cff;transition:width .4s}
.bar i.hi{background:#ff5d5d}
#st{font-size:12px;color:#5c6575;text-align:center;margin-top:8px}
</style></head><body>
<h1 id="h">...</h1><div id="o"></div><div id="st"></div>
<script>
const fmt=b=>b>1048576?(b/1048576).toFixed(1)+' MB/s':(b/1024).toFixed(0)+' KB/s';
const card=(n,v,p,extra)=>`<div class=c><div class=r><span>${n}</span><b>${v}</b></div>`+
(p!=null?`<div class=bar><i class="${p>85?'hi':''}" style="width:${p}%"></i></div>`:'')+
(extra?`<div class=r style="margin-top:6px"><span>${extra}</span></div>`:'')+`</div>`;
async function tick(){
 try{
  const d=await (await fetch('/api',{cache:'no-store'})).json();
  if(!d.host)return;
  h.textContent=d.host+' · açık: '+Math.floor(d.uptime/3600)+'s '+Math.floor(d.uptime%3600/60)+'dk';
  let s='';
  s+=card('CPU',d.cpu.toFixed(0)+'%',d.cpu,d.cpu_temp!=null?d.cpu_temp.toFixed(0)+' °C':'');
  s+=card('RAM',d.ram.toFixed(0)+'%',d.ram,(d.ram_used/2**30).toFixed(1)+' / '+(d.ram_total/2**30).toFixed(1)+' GB');
  if(d.gpu)s+=card('GPU',d.gpu.load.toFixed(0)+'%',d.gpu.load,d.gpu.temp+' °C · '+(d.gpu.mem_used/1024).toFixed(1)+' / '+(d.gpu.mem_total/1024).toFixed(1)+' GB');
  if(d.disk!=null)s+=card('Disk',d.disk.toFixed(0)+'%',d.disk);
  s+=card('Ağ','↓ '+fmt(d.down),null,'↑ '+fmt(d.up));
  if(d.battery!=null)s+=card('Pil',d.battery.toFixed(0)+'%',d.battery,d.plugged?'şarjda':'pilde');
  o.innerHTML=s;st.textContent='güncel: '+new Date().toLocaleTimeString();
 }catch(e){st.textContent='bağlantı yok…'}
}
tick();setInterval(tick,1000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api"):
            body, ctype = json.dumps(data).encode(), "application/json"
        else:
            body, ctype = PAGE.encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    threading.Thread(target=sampler, daemon=True).start()
    print(f"Telefondan aç: http://{local_ip()}:{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
