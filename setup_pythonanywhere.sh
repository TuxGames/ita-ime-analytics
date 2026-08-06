#!/usr/bin/env bash
# Bootstrap do ITA-IME Analytics no PythonAnywhere.
# Rode UMA vez no console Bash, a partir da raiz do projeto (onde está o wsgi.py):
#   cd ~/ita-ime-analytics      # ajuste para o seu diretório
#   bash setup_pythonanywhere.sh
#
# Depois: aponte a aba Web -> Virtualenv para o caminho impresso no fim,
# preencha o .env (veja .env.example) e clique em Reload.
set -euo pipefail

# Versão de Python: precisa bater com a selecionada na aba Web do PythonAnywhere.
# Troque aqui se o seu web app usar outra (ex.: python3.11).
PYTHON="${PYTHON:-python3.10}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"

echo ">> Projeto: $PROJECT_DIR"
echo ">> Usando: $PYTHON ($($PYTHON --version 2>&1))"

if [ ! -d "$VENV_DIR" ]; then
  echo ">> Criando virtualenv em $VENV_DIR"
  "$PYTHON" -m venv "$VENV_DIR"
else
  echo ">> Virtualenv já existe, reutilizando: $VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo ">> Atualizando pip e instalando dependências"
pip install --upgrade pip
pip install -r "$PROJECT_DIR/requirements.txt"

echo ">> Verificando imports críticos"
python - <<'PY'
import flask, flask_limiter, flask_login, flask_wtf, flask_bcrypt, flask_sqlalchemy, flask_migrate, dotenv
print("  todas as dependências importam OK")
PY

# .env: cria a partir do modelo se ainda não existir (você precisa preencher o SECRET_KEY)
if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo ">> Criando .env a partir de .env.example (PREENCHA o SECRET_KEY!)"
  cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
  KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
  # preenche o SECRET_KEY vazio automaticamente
  python - "$PROJECT_DIR/.env" "$KEY" <<'PY'
import sys
path, key = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    txt = f.read()
txt = txt.replace("SECRET_KEY=\n", f"SECRET_KEY={key}\n", 1)
if "SECRET_KEY=%s" % key not in txt and f"SECRET_KEY={key}" not in txt:
    txt += f"\nSECRET_KEY={key}\n"
with open(path, "w", encoding="utf-8") as f:
    f.write(txt)
print("  SECRET_KEY gerado e gravado no .env")
PY
else
  echo ">> .env já existe, mantido como está"
fi

echo ">> Aplicando migrations (cria instance/itaime.db)"
export FLASK_APP=wsgi.py
flask db upgrade

echo ""
echo "============================================================"
echo "Setup concluído."
echo ""
echo "1) Aba Web -> Virtualenv, informe este caminho:"
echo "     $VENV_DIR"
echo ""
echo "2) Confira/edite o .env (SESSION_COOKIE_SECURE=true, BEHIND_PROXY=true)."
echo ""
echo "3) Crie o primeiro admin:"
echo "     source \"$VENV_DIR/bin/activate\""
echo "     export FLASK_APP=wsgi.py"
echo "     flask create-user SEU_USUARIO --admin"
echo ""
echo "4) Ajuste o WSGI do /var/www/ (veja deploy/pythonanywhere_wsgi.py) e dê Reload."
echo "============================================================"
