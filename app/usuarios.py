"""Cria um usuário ou troca a senha.

Uso: python -m app.usuarios <usuario>
"""

import getpass
import sys

from . import auth, db


def main():
    if len(sys.argv) != 2:
        sys.exit("Uso: python -m app.usuarios <usuario>")
    db.iniciar()
    usuario = sys.argv[1]
    senha = getpass.getpass(f"Senha para {usuario}: ")
    if senha != getpass.getpass("Repita a senha: "):
        sys.exit("As senhas não conferem.")
    try:
        auth.criar_usuario(usuario, senha)
    except ValueError as e:
        sys.exit(str(e))
    print(f"Usuário {usuario} salvo. Sessões abertas dele foram encerradas.")


if __name__ == "__main__":
    main()
