# Jogo Reverso

Jogo presencial: toca 1 minuto de uma música **ao contrário**, os jogadores
reconhecem e apertam o botão gigante no celular. O admin (dono da caixa de som)
julga e controla os pontos.

## URLs

| Tela | URL |
|---|---|
| Admin | http://192.168.0.81:8099/admin |
| Jogadores | http://192.168.0.81:8099/ (QR no painel) |
| Telão | http://192.168.0.81:8099/tv |

Chave do admin: definida na variável `JOGO_KEY` do serviço (veja `.env.example`).
Sem ela definida, o app usa `troque-esta-chave` — troque antes de usar.

## Emenda reverso → original

O clipe invertido é o trecho de 60s espelhado, então o segundo `t` do reverso
equivale a `duração - t` do original. Ao trocar o toggle para **Original**
depois de um acerto, o áudio retoma nesse segundo exato (sem corte entre os dois).

## Serviço

```bash
systemctl --user status jogo-reverso
systemctl --user restart jogo-reverso
journalctl --user -u jogo-reverso -f
tail -f data/server.log
```

Arquivo: `~/.config/systemd/user/jogo-reverso.service`

## Como jogar

1. Admin → cola link de vídeo/playlist do YouTube → **+**. Download + inversão
   rodam em background (leva ~15s por faixa; status muda na fila).
2. Celulares escaneiam o QR e digitam o nome.
3. **▶ Iniciar** — zera o placar, arma a primeira faixa e o áudio toca no
   navegador do admin (o som sai da caixa de som dele).
4. Quem reconhece aperta. O primeiro trava os outros, o áudio pausa.
5. Admin: **✔ Acertou** (soma pontos e revela) ou **✘ Errou** (libera de novo;
   o áudio fica parado até o admin dar ▶). Cada clique toca um efeito sonoro
   (arpejo no acerto, buzz grave no erro).
- **♪ normal** toca o mesmo trecho de 60s sem inverter — usa depois do
   julgamento pra galera ouvir a música de verdade.
- Sons reais em `static/sfx/`: `buzz.mp3` (botão do The Voice, toca no celular
  de quem aperta), `acerto.mp3` e `erro.mp3` (tocam no celular do julgado e no
  PC do admin). Trocar o som = substituir o arquivo mantendo o nome.
7. **⏭ Próxima** segue; **⟲ Repetir** toca a mesma de novo; **👁 Revelar** mostra
   o título antes de decidir.
8. Pontos manuais: `+` / `−` em cada jogador no placar.

## Estados

`idle` → `armed` (botões liberados, música tocando) → `buzzed` (alguém apertou,
áudio pausado) → `reveal` (resposta na tela).

## Pipeline de áudio

```
yt-dlp (bestaudio) → media/raw/<ytid>.mp3
ffmpeg -ss <offset> -t 60 -af areverse → media/<id>.mp3
```

- Offset padrão 45s (configurável em Ajustes; por faixa no campo da fila).
- 60s é o trecho jogado. O arquivo final já é o trecho invertido.

### Pitfall do YouTube

yt-dlp precisa de versão recente **e** de um JS runtime, senão dá
`HTTP Error 403` / "extraction without a JS runtime has been deprecated":

- binário usado: `.venv/bin/yt-dlp` (atualizar com
  `env -u PYTHONPATH .venv/bin/python -m pip install -U yt-dlp`)
- args obrigatórios: `--js-runtimes node:/home/miguel/.hermes/node/bin/node
  --remote-components ejs:github`

Se o YouTube mudar de novo, testar manualmente antes de culpar o app:

```bash
.venv/bin/yt-dlp --js-runtimes node:/home/miguel/.hermes/node/bin/node \
  --remote-components ejs:github -f bestaudio -x --audio-format mp3 \
  -o /tmp/t.%(ext)s "https://www.youtube.com/watch?v=ID"
```

## Arquivos

```
app.py            FastAPI + WebSocket (estado em memória, persistido em data/db.json)
static/play.html  celular do jogador
static/admin.html painel do admin
static/tv.html    telão
data/db.json      fila, jogadores, placar, estado
media/            clipes de 60s invertidos
media/raw/        áudio original baixado
```

## Reset

```bash
systemctl --user stop jogo-reverso
rm -f data/db.json media/*.mp3
systemctl --user start jogo-reverso
```

Apagar `data/db.json` zera jogadores, placar e fila. Os `media/raw/*` podem ser
apagados também (serão rebaixados se a faixa voltar à fila).
