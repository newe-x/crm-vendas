"""Usuários, senhas e sessões."""

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from .db import conectar

COOKIE = "sessao"
DURACAO_SESSAO = 30 * 24 * 3600
SENHA_MINIMA = 8

# scrypt: N=2^14, r=8, p=1 (~16 MB de memória por verificação)
_N, _R, _P = 2**14, 8, 1


def hash_senha(senha: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(senha.encode(), salt=sal, n=_N, r=_R, p=_P)
    return f"scrypt${_N}${_R}${_P}${sal.hex()}${h.hex()}"


def verificar_senha(senha: str, guardado: str) -> bool:
    _, n, r, p, sal, h = guardado.split("$")
    calc = hashlib.scrypt(senha.encode(), salt=bytes.fromhex(sal), n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(calc, bytes.fromhex(h))


# Hash fixo para gastar o mesmo tempo quando o usuário não existe.
_HASH_FALSO = hash_senha(secrets.token_hex(8))


def criar_usuario(usuario: str, senha: str) -> None:
    if len(senha) < SENHA_MINIMA:
        raise ValueError(f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.")
    with conectar() as conn:
        conn.execute(
            """INSERT INTO usuarios (usuario, senha_hash) VALUES (?, ?)
               ON CONFLICT(usuario) DO UPDATE SET senha_hash = excluded.senha_hash""",
            (usuario.strip(), hash_senha(senha)),
        )
        # Trocar a senha encerra as sessões abertas.
        conn.execute(
            "DELETE FROM sessoes WHERE usuario_id = (SELECT id FROM usuarios WHERE usuario = ?)",
            (usuario.strip(),),
        )


def existe_usuario() -> bool:
    with conectar() as conn:
        return conn.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone() is not None


def autenticar(usuario: str, senha: str) -> int | None:
    with conectar() as conn:
        row = conn.execute(
            "SELECT id, senha_hash FROM usuarios WHERE usuario = ?", (usuario.strip(),)
        ).fetchone()
    if row is None:
        verificar_senha(senha, _HASH_FALSO)
        return None
    return row["id"] if verificar_senha(senha, row["senha_hash"]) else None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def abrir_sessao(usuario_id: int) -> str:
    token = secrets.token_urlsafe(32)
    agora = int(time.time())
    with conectar() as conn:
        conn.execute("DELETE FROM sessoes WHERE expira_em < ?", (agora,))
        conn.execute(
            "INSERT INTO sessoes (token_hash, usuario_id, expira_em) VALUES (?, ?, ?)",
            (_hash_token(token), usuario_id, agora + DURACAO_SESSAO),
        )
    return token


def fechar_sessao(token: str) -> None:
    with conectar() as conn:
        conn.execute("DELETE FROM sessoes WHERE token_hash = ?", (_hash_token(token),))


def usuario_atual(request: Request) -> str:
    """Dependência das rotas protegidas: devolve o nome do usuário ou 401."""
    token = request.cookies.get(COOKIE)
    if token:
        with conectar() as conn:
            row = conn.execute(
                """SELECT u.usuario FROM sessoes s JOIN usuarios u ON u.id = s.usuario_id
                   WHERE s.token_hash = ? AND s.expira_em > ?""",
                (_hash_token(token), int(time.time())),
            ).fetchone()
        if row:
            return row["usuario"]
    raise HTTPException(401, "Entre com seu usuário e senha.")


class LimiteTentativas:
    """Bloqueia após muitas falhas de login na janela, por usuário e por IP."""

    def __init__(self, por_usuario=5, por_ip=20, janela=15 * 60):
        self.limites = {"u": por_usuario, "ip": por_ip}
        self.janela = janela
        self.falhas: dict[str, deque] = defaultdict(deque)
        self.trava = threading.Lock()

    def _chaves(self, usuario: str, ip: str):
        return [("u", f"u:{usuario.strip().lower()}"), ("ip", f"ip:{ip}")]

    def _limpar(self, fila: deque, agora: float):
        while fila and fila[0] < agora - self.janela:
            fila.popleft()

    def bloqueado(self, usuario: str, ip: str) -> bool:
        agora = time.monotonic()
        with self.trava:
            for tipo, chave in self._chaves(usuario, ip):
                fila = self.falhas[chave]
                self._limpar(fila, agora)
                if len(fila) >= self.limites[tipo]:
                    return True
        return False

    def falhou(self, usuario: str, ip: str):
        agora = time.monotonic()
        with self.trava:
            for _, chave in self._chaves(usuario, ip):
                self.falhas[chave].append(agora)

    def acertou(self, usuario: str):
        with self.trava:
            self.falhas.pop(f"u:{usuario.strip().lower()}", None)


limite = LimiteTentativas()
