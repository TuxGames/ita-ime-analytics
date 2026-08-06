"""Ponto de entrada WSGI (PythonAnywhere) e para `flask --app wsgi run` local."""
import os

from dotenv import load_dotenv

# Carrega o .env que fica ao lado deste arquivo (necessário no PythonAnywhere,
# onde o WSGI server não passa pelo CLI do Flask)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from app import create_app  # noqa: E402  (import depois do load_dotenv, de propósito)

app = create_app()
