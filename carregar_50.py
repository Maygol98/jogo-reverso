import json, subprocess, urllib.request, time, sys, os

import shutil
from pathlib import Path

PORT = os.environ.get("JOGO_PORT", "8099")
BASE = os.environ.get("JOGO_URL", f"http://127.0.0.1:{PORT}")
KEY = os.environ.get("JOGO_KEY", "troque-esta-chave")
_HERE = Path(__file__).resolve().parent
YT = os.environ.get("JOGO_YTDLP") or str(_HERE / ".venv" / "bin" / "yt-dlp")
if not Path(YT).exists():
    YT = shutil.which("yt-dlp") or "yt-dlp"
NODE = os.environ.get("JOGO_NODE") or shutil.which("node") or ""

MUSICAS = [
 "Jorge e Mateus Propaganda", "Marilia Mendonca Infiel", "Henrique e Juliano Vai Namorar Comigo",
 "Wesley Safadao Camarote", "Ivete Sangalo Sorte Grande", "Michel Telo Ai Se Eu Te Pego",
 "Luan Santana Meteoro", "Gusttavo Lima Balada", "Roberto Carlos Como E Grande o Meu Amor Por Voce",
 "Tim Maia Voce", "Djavan Flor de Lis", "Caetano Veloso Sozinho",
 "Raul Seixas Metamorfose Ambulante", "Cazuza Exagerado", "Barao Vermelho Pro Dia Nascer Feliz",
 "Titas Epitafio", "Paralamas do Sucesso Lanterna dos Afogados", "Skank Garota Nacional",
 "O Rappa Pescador de Ilusoes", "Charlie Brown Jr So os Loucos Sabem", "Racionais Diario de um Detento",
 "Anitta Envolver", "Luisa Sonza Penhasco", "Ludmilla Cheguei", "Anitta Show das Poderosas",
 "Simone e Simaria Regime Fechado", "Maiara e Maraisa Medo Bobo", "Ze Neto e Cristiano Notificacao Preferida",
 "Matheus e Kauan Te Assumi Pro Brasil", "Alok Hear Me Now", "Jao Meu Bem",
 "Thiaguinho Sou o Cara pra Voce", "Pericles Final de Tarde",
 "Queen We Will Rock You", "Michael Jackson Thriller", "Madonna Like a Prayer",
 "Whitney Houston I Wanna Dance with Somebody", "ABBA Dancing Queen", "Bee Gees Stayin Alive",
 "Nirvana Smells Like Teen Spirit", "Guns N Roses Sweet Child O Mine", "Bon Jovi Livin on a Prayer",
 "AC DC Back in Black", "The Beatles Hey Jude", "Ed Sheeran Shape of You",
 "Adele Rolling in the Deep", "Bruno Mars Uptown Funk", "Dua Lipa Levitating", "Coldplay Yellow",
 "Luis Fonsi Despacito",
]

def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Key": KEY})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except Exception as e:
        return {"err": str(e)}

def buscar(q):
    cmd = [YT, "--js-runtimes", f"node:{NODE}", "--remote-components", "ejs:github",
           "--no-warnings", "--no-update", f"ytsearch3:{q}",
           "--print", "%(id)s\t%(title)s\t%(duration)s"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout
    except Exception:
        return None
    for line in out.strip().split("\n"):
        p = line.split("\t")
        if len(p) < 3 or not p[0]:
            continue
        try:
            dur = float(p[2])
        except Exception:
            continue
        if 90 <= dur <= 480:
            return p[0], p[1]
    return None

adicionadas = 0
falhas = []
for i, q in enumerate(MUSICAS, 1):
    r = buscar(q)
    if not r:
        falhas.append(q); print(f"[{i:2d}/{len(MUSICAS)}] FALHA busca: {q}", flush=True); continue
    yid, titulo = r
    res = post("/api/queue", {"url": f"https://www.youtube.com/watch?v={yid}"})
    ok = res.get("added", 0) > 0
    adicionadas += 1 if ok else 0
    if not ok:
        falhas.append(q)
    print(f"[{i:2d}/{len(MUSICAS)}] {'ok ' if ok else 'dup'} {titulo[:60]}", flush=True)
    time.sleep(0.4)

print(f"\nRESUMO: {adicionadas} adicionadas, {len(falhas)} falhas")
for f in falhas:
    print("  falhou:", f)
