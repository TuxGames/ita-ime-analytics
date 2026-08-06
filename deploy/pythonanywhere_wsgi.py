# MODELO do arquivo WSGI do PythonAnywhere.
#
# NÃO é este arquivo que o servidor executa. Copie o conteúdo abaixo para o
# arquivo que o PythonAnywhere gera em:
#   /var/www/SEUUSUARIO_pythonanywhere_com_wsgi.py
# (há um link direto para ele na aba Web -> "WSGI configuration file").
#
# Ajuste PROJECT_DIR para a pasta que CONTÉM o wsgi.py do projeto e a pasta app/
# (é a raiz onde você extraiu o zip). Ex.: se o código está em /home/itaime/app,
# então PROJECT_DIR = "/home/itaime".

import sys

PROJECT_DIR = "/home/itaime"  # <-- ajuste para o seu caminho

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# wsgi.py (do projeto) já carrega o .env com python-dotenv antes de criar o app.
from wsgi import app as application  # noqa: E402
