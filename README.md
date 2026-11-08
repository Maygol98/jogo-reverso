# Jogo Reverso 🎵

Jogo presencial pra jogar com os amigos: o computador toca **60 segundos de uma música
ao contrário**. Quem reconhecer aperta o botão gigante no celular. O primeiro que
aperta ganha a vez de dizer qual é a música — e quem julga é o apresentador (admin),
que também controla a pontuação, escolhe a próxima música e revela a resposta.

O som sai **do computador do apresentador**, ligado numa caixa de som. O celular dos
jogadores serve só como botão. Tudo roda na rede de casa: um computador e os celulares
no mesmo Wi-Fi, sem internet nem conta em lugar nenhum.

---

## Como é uma partida

1. O apresentador abre o painel no computador e clica em **Iniciar jogo**.
2. A música começa a tocar **ao contrário**. Os celulares mostram um botão gigante.
3. Quem reconhece aperta o botão. O som para na hora e o nome de quem apertou aparece
   na tela — ninguém mais pode apertar nessa rodada.
4. A pessoa diz o nome da música em voz alta.
5. O apresentador marca **acertou** ou **errou**:
   - **Acertou**: leva os pontos configurados e a rodada encerra.
   - **Errou**: o jogo volta e o próximo que apertar ganha a vez.
6. Na hora de revelar, o apresentador vira o botão **Reverso → Original** e a música
   toca **de frente pra trás**, do ponto exato onde parou.
7. Depois é só **Próxima** e começa outra rodada.

---

## O que você precisa

| Programa | Pra quê | Obrigatório? |
|---|---|---|
| Python 3.10 ou mais novo | rodar o jogo | sim |
| ffmpeg | inverter o áudio das músicas | sim |
| Node.js | baixar músicas do YouTube com mais confiabilidade | recomendado |
| Git | baixar o projeto pelo terminal | opcional |

Se você não sabe o que é nenhum desses: siga o passo a passo abaixo, na ordem. Leva
uns 15 minutos.

---

## Instalação no Windows

### 1. Instalar o Python

1. Abra <https://www.python.org/downloads/> e clique no botão amarelo **Download Python**.
2. Abra o arquivo baixado.
3. **Na primeira tela, marque a caixinha “Add python.exe to PATH”** (fica embaixo).
   Sem isso nada funciona depois.
4. Clique em **Install Now** e espere terminar.

Para conferir: aperte a tecla Windows, digite `cmd`, abra o **Prompt de Comando** e digite:

```
python --version
```

Tem que aparecer algo como `Python 3.12.4`. Se der erro, o Python não entrou no PATH —
desinstale e instale de novo marcando a caixinha.

### 2. Instalar o ffmpeg

No mesmo Prompt de Comando:

```
winget install Gyan.FFmpeg
```

Feche e abra o Prompt de Comando de novo e teste:

```
ffmpeg -version
```

Se `winget` não existir (Windows 10 antigo), baixe em <https://www.gyan.dev/ffmpeg/builds/>
o arquivo `ffmpeg-release-essentials.zip`, extraia em `C:\ffmpeg` e adicione
`C:\ffmpeg\bin` ao PATH (Menu Iniciar → “variáveis de ambiente” → Path → Novo).

### 3. Instalar o Node.js (recomendado)

Baixe em <https://nodejs.org/> o botão **LTS** e instale com “Next” até o fim. Serve
para o YouTube entregar o áudio sem bloqueio.

### 4. Baixar o jogo

**Opção fácil (sem Git):** na página do projeto no GitHub, clique no botão verde
**Code → Download ZIP** e extraia em `C:\jogo-reverso`.

**Opção com Git**, se você já tem:

```
cd C:\
git clone https://github.com/Maygol98/jogo-reverso.git
```

### 5. Instalar as dependências

No Prompt de Comando:

```
cd C:\jogo-reverso
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

O `activate` faz aparecer `(.venv)` no começo da linha. As dependências baixam uma vez
só (uns 2 minutos).

### 6. Rodar

```
python app.py
```

Vai aparecer algo como:

```
Uvicorn running on http://0.0.0.0:8099
```

Deixe essa janela aberta — é o servidor. **Fechar a janela derruba o jogo.**

---

## Instalação no Linux ou macOS

```bash
# dependências do sistema
sudo apt install python3 python3-venv ffmpeg        # Debian/Ubuntu
# sudo dnf install python3 ffmpeg                   # Fedora
# brew install python ffmpeg                        # macOS

# o projeto
git clone https://github.com/Maygol98/jogo-reverso.git
cd jogo-reverso

# ambiente Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# rodar
python app.py
```

---

## Usando o jogo

Com o servidor rodando, abra no navegador do computador:

```
http://localhost:8099/admin
```

A chave padrão é `troque-esta-chave`. **Troque antes de jogar** (veja Configurações).

No canto do painel tem um menu **☰**. Ali ficam o **QR code** e o endereço para os
jogadores entrarem. Cada jogador aponta a câmera do celular, entra, digita o nome — e
o botão gigante aparece.

> O celular precisa estar no **mesmo Wi-Fi** do computador. O endereço mostrado no QR
> é o IP da máquina na rede local (o que o roteador deu pra ela). Se o computador trocar
> de IP, o QR se atualiza sozinho na próxima vez que o servidor subir.

Extras:

- **Telão**: `http://localhost:8099/tv` — mostra o placar e quem apertou. Bom pra jogar
  numa TV.
- **Tema claro/escuro**: botão no canto direito do cabeçalho.

### Adicionar músicas

No painel, coluna da direita, cole um link do YouTube (vídeo ou playlist) e clique em
**+**. O servidor baixa o áudio e prepara os dois clipes (invertido e normal). Leva
alguns segundos por música. Quando o item mostrar **pronto**, pode jogar.

Dá pra arrastar as músicas pra reordenar, marcar qual é a próxima e sortear
(🔀 embaralha a fila).

---

## Configurações

Tudo por variável de ambiente — não precisa editar código.

| Variável | Padrão | O que faz |
|---|---|---|
| `JOGO_KEY` | `troque-esta-chave` | senha do painel do apresentador |
| `JOGO_PORT` | `8099` | porta do servidor |
| `JOGO_HOST` | IP da máquina (automático) | IP que vai dentro do QR code |
| `JOGO_YTDLP` | `yt-dlp` do PATH | caminho do yt-dlp, se não estiver no PATH |
| `JOGO_NODE` | `node` do PATH | caminho do Node.js |

Windows (Prompt de Comando):

```
set JOGO_KEY=minha-senha-secreta
python app.py
```

Linux/macOS:

```bash
JOGO_KEY=minha-senha-secreta python app.py
```

O IP é descoberto automaticamente na inicialização — se o roteador mudar o endereço da
máquina, o QR acompanha. Só defina `JOGO_HOST` se quiser forçar um endereço (por exemplo
um nome tipo `jogo.local`).

---

## Deixar rodando sempre (Linux)

Dá pra virar serviço do usuário — sobe sozinho e reinicia se cair:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/jogo-reverso.service.example ~/.config/systemd/user/jogo-reverso.service
# edite o arquivo e ajuste os caminhos e a JOGO_KEY
systemctl --user daemon-reload
systemctl --user enable --now jogo-reverso
```

Logs: `journalctl --user -u jogo-reverso -f`.

---

## Problemas comuns

**A música não toca e aparece aviso de áudio.**
Navegador só libera som depois de um clique na página. Clique uma vez no painel e dê
play de novo.

**“Não foi possível baixar” ou erro 403 do YouTube.**
Atualize o yt-dlp: `pip install -U yt-dlp`. Se continuar, instale o Node.js — o YouTube
passou a exigir um runtime de JavaScript pra liberar os formatos.

**O celular não abre o endereço.**
Confirme que está no mesmo Wi-Fi e que o firewall do computador permite a porta 8099.
No Windows, na primeira vez ele pergunta — autorize em rede privada.

**O QR mostra um IP errado.**
Se a máquina tem várias interfaces (VPN, VirtualBox), force o IP certo:
`JOGO_HOST=192.168.0.50`.

**Acertei mas a música original começa no meio.**
É de propósito: ela continua do ponto exato onde o reverso parou. Faixas que têm o
áudio completo seguem até o fim da música; as que só têm o trecho param em 60s.

---

## Como funciona por dentro

- **FastAPI + WebSocket** num processo só. O estado da partida fica em `data/db.json`,
  então reiniciar o servidor não perde o placar.
- Cada música vira dois arquivos com `ffmpeg`: `media/<id>.mp3` (60s invertidos) e
  `media/<id>_n.mp3` (os mesmos 60s normais). O áudio completo fica em `media/raw/`.
- O áudio toca **no navegador do apresentador**, não no servidor. É isso que garante
  que todo mundo ouça a mesma coisa, no mesmo instante.
- O botão do celular é um WebSocket: o primeiro a apertar trava os outros no servidor,
  não só na tela.

```
app.py                  servidor (rotas, WebSocket, fila, download)
static/admin.html       painel do apresentador
static/play.html        celular do jogador (só o botão)
static/tv.html          telão com placar
static/sfx/             sons de buzz, acerto e erro
data/db.json            estado da partida (criado ao rodar)
media/                  clipes processados (criado ao rodar)
```

### Detalhes técnicos

O clipe invertido é o trecho de 60s espelhado, então o segundo `t` do reverso equivale
a `duração - t` do original. Ao trocar para **Original** depois de um acerto, o áudio
retoma nesse segundo exato, sem corte. Em Original toca o arquivo completo
(`media/raw/<ytid>.mp3`), então a música segue até o fim; faixas sem o completo caem
no trecho de 60s, na posição equivalente.

Estados da partida: `idle` → `armed` (botões liberados) → `buzzed` (alguém apertou) →
`reveal` (resposta na tela). Só em `buzzed` o julgamento é aceito, no servidor — evita
ponto duplicado por clique repetido.

---

## Licença

MIT — use, copie, mude, jogue com os amigos.
