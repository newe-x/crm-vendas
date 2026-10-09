# Deploy

O app é **um processo** com **um arquivo SQLite** e uma pasta de fotos. Isso deixa a instalação simples, mas traz uma regra: rode **um único container com um único worker**. Várias réplicas ou `--workers` > 1 quebram o limite de tentativas de login (que fica na memória) e podem disputar o banco.

## Docker Compose

```bash
cp .env.example .env
```

Preencha o `.env`:

| Variável | Para quê |
|---|---|
| `ADMIN_USER`, `ADMIN_PASSWORD` | Criam o primeiro usuário **somente se o banco ainda não tiver nenhum**. Depois do primeiro start, pode apagar do `.env`. Senha com no mínimo 8 caracteres |
| `FORWARDED_ALLOW_IPS` | IP do proxy reverso, como o container o enxerga. Veja [Proxy reverso](#proxy-reverso-e-https) |

Suba:

```bash
docker compose up -d --build
docker compose ps          # a coluna STATUS deve mostrar (healthy) depois de ~30 s
```

O `docker-compose.yml` publica a porta só em `127.0.0.1:8000`: o acesso de fora deve passar pelo proxy com HTTPS.

## Docker sem Compose

```bash
docker build -t crm-vendas .
docker run -d --name vendas --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -v crm-vendas-data:/data \
  -e ADMIN_USER=voce -e ADMIN_PASSWORD='uma-senha-forte' \
  -e FORWARDED_ALLOW_IPS=172.17.0.1 \
  crm-vendas
```

## O que a imagem faz

| Item | Valor |
|---|---|
| Base | `python:3.13-slim` (~170 MB) |
| Usuário | `app` (uid 10001), sem privilégios |
| Dados | `/data/vendas.db` e `/data/fotos/` (volume) |
| Porta | 8000 |
| Healthcheck | `GET /healthz` a cada 30 s, testa se o banco responde |
| Proxy | `uvicorn --proxy-headers`, confiando nos IPs de `FORWARDED_ALLOW_IPS` |

**Bind mount em vez de volume nomeado:** a pasta do host precisa pertencer ao uid 10001:

```bash
sudo mkdir -p /srv/vendas && sudo chown 10001:10001 /srv/vendas
docker run ... -v /srv/vendas:/data ...
```

## Proxy reverso e HTTPS

Publique **sempre** atrás de HTTPS. Sem HTTPS a senha trafega aberta, o cookie de sessão não recebe a marca `Secure` e o celular não oferece instalar o app.

O proxy precisa enviar `X-Forwarded-For` e `X-Forwarded-Proto`, e o container precisa confiar nele via `FORWARDED_ALLOW_IPS`. Se essa configuração faltar:

- o cookie sai sem `Secure`, mesmo com HTTPS na frente;
- todos os acessos parecem vir do IP do proxy, e o limite de 20 senhas erradas por IP passa a valer para **todo mundo junto**.

**Qual IP colocar:** o IP de origem das conexões que chegam ao container.

| Onde está o proxy | `FORWARDED_ALLOW_IPS` |
|---|---|
| No host, com `-p 127.0.0.1:8000:8000` | Gateway da rede do Docker, geralmente `172.17.0.1` (rede padrão) ou o gateway da rede do Compose (`docker network inspect <rede>`) |
| Em outro container na mesma rede | IP desse container, ou a faixa da rede (ex.: `172.18.0.0/16`) |
| Porta do app **não** exposta fora do host/rede | `*` é aceitável |

Para conferir, faça login e veja o log: `docker logs vendas | grep login` deve mostrar o IP real do cliente, não o do proxy.

### Exemplo: Caddy

```caddy
vendas.seudominio.com.br {
    reverse_proxy 127.0.0.1:8000
}
```

O Caddy obtém o certificado sozinho e já envia os cabeçalhos `X-Forwarded-*`.

### Exemplo: Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name vendas.seudominio.com.br;
    # ssl_certificate ... (ex.: certbot)

    client_max_body_size 3m;   # fotos

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Exemplo: HAProxy

```haproxy
frontend https
    bind :443 ssl crt /etc/haproxy/certs/
    http-request set-header X-Forwarded-Proto https
    option forwardfor
    default_backend vendas

backend vendas
    server app 127.0.0.1:8000 check
```

`option forwardfor` é o que adiciona o `X-Forwarded-For`; sem ele o app só enxerga o IP do HAProxy.

## Usuários

Não existe cadastro pela tela. Para criar um usuário ou trocar a senha:

```bash
# Docker / Compose
docker exec -it vendas python -m app.usuarios nome-do-usuario
docker compose exec vendas python -m app.usuarios nome-do-usuario

# Sem Docker
.venv/bin/python -m app.usuarios nome-do-usuario
```

O comando pede a senha duas vezes sem mostrá-la. Trocar a senha encerra todas as sessões abertas daquele usuário. Todos os usuários veem e editam os mesmos dados.

## Backup

Copie **o volume inteiro** (`vendas.db` + `fotos/`). Para uma cópia consistente do banco com o app rodando, use o backup do próprio SQLite:

```bash
# Gera /data/backup.db de forma segura com o app no ar
docker exec vendas python -c "import sqlite3; s=sqlite3.connect('/data/vendas.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()"

# Empacota banco + fotos no host
docker run --rm -v crm-vendas-data:/data -v "$PWD":/out alpine \
  tar czf /out/vendas-$(date +%F).tar.gz -C /data backup.db fotos
```

Agende com cron e mande o arquivo para fora da máquina (S3, outro servidor). Teste a restauração de vez em quando.

**Restaurar:** pare o container, coloque o `backup.db` como `vendas.db` e a pasta `fotos/` no volume, com dono uid 10001, e suba de novo.

## Atualizar

```bash
git pull
docker compose up -d --build
```

O esquema do banco é verificado na subida (`PRAGMA user_version`). O app não apaga dados: se encontrar um banco antigo **com dados** num formato que não sabe migrar, ele se recusa a iniciar e mostra o erro no log.

O navegador busca sempre a versão nova do app (o service worker tenta a rede primeiro). Se algo parecer desatualizado no celular, feche e abra o app.

## Logs e saúde

```bash
docker compose logs -f vendas
docker inspect -f '{{.State.Health.Status}}' vendas
curl -s http://127.0.0.1:8000/healthz      # {"ok":true}
```
