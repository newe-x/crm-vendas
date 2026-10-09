# Segurança

## Login e sessões

- Senhas guardadas com **scrypt** (N=2¹⁴, r=8, p=1) e sal aleatório. Mínimo de 8 caracteres.
- Usuário inexistente leva o mesmo tempo que senha errada, para não revelar quais usuários existem.
- Sessão: token aleatório de 256 bits num cookie `HttpOnly`, `SameSite=Lax`, `Secure` quando o acesso é HTTPS. O banco guarda só o hash SHA-256 do token. Validade de 30 dias.
- Sair apaga a sessão no servidor. Trocar a senha (`python -m app.usuarios`) encerra todas as sessões do usuário.

## Limite de tentativas

Bloqueio de 15 minutos depois de:

- 5 senhas erradas para o **mesmo usuário**, ou
- 20 senhas erradas vindas do **mesmo IP**.

O bloqueio fica na memória do processo: reiniciar o app zera os contadores. Ele depende do IP real do cliente; atrás de proxy, configure `FORWARDED_ALLOW_IPS` ([deploy](deploy.md#proxy-reverso-e-https)).

O bloqueio por usuário também significa que alguém que saiba o seu nome de usuário consegue travar o seu login por 15 minutos. Use um nome de usuário que não seja óbvio.

## Proteções HTTP

- `Content-Security-Policy`: scripts só do próprio app; estilos do app e do Google Fonts; imagens do app, `blob:` e `data:`; sem iframes (`frame-ancestors 'none'`).
- `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`.
- Respostas da API com `Cache-Control: no-store`.
- Documentação automática da API (Swagger/OpenAPI) desligada.
- CSRF: cookie `SameSite=Lax` e corpo JSON nas rotas que alteram dados.

## Fotos

Só JPEG, até 1,5 MB, verificado pelo conteúdo do arquivo e não pela extensão. Nome de arquivo aleatório gerado pelo servidor. Servidas apenas para usuários logados.

## Container

Roda como usuário sem privilégios (uid 10001). A porta deve ficar acessível só ao proxy (`127.0.0.1:8000` no `docker-compose.yml`).

## Cuidados de operação

- Publique **somente com HTTPS**.
- Faça **backup** do volume `/data` fora da máquina ([deploy](deploy.md#backup)).
- O `.env` com `ADMIN_PASSWORD` não vai para o git; apague a variável depois do primeiro start.
- Todos os usuários têm acesso total aos mesmos dados. Não há perfis nem histórico de alterações; excluir uma venda é definitivo.
