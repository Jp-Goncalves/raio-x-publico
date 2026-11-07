FROM python:3.12-slim

WORKDIR /app

# dependências primeiro: esta camada só é refeita se o requirements mudar
COPY dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# o app reaproveita src/db.py (a conexão com o Postgres)
COPY .streamlit ./.streamlit
COPY src ./src
COPY dashboard ./dashboard

# o app só lê o banco e fala com o Airflow: não precisa de root. Os arquivos continuam
# pertencendo ao root (e só de leitura pra este usuário), então o app não consegue alterar o próprio código
RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8501

# o endereço de escuta e a conexão com o banco vêm do docker-compose.yml (variáveis de ambiente)
CMD ["streamlit", "run", "dashboard/app.py"]
