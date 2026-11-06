FROM python:3.12-slim

WORKDIR /app

# dependências primeiro: esta camada só é refeita se o requirements mudar
COPY dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# o app reaproveita src/db.py (a conexão com o Postgres)
COPY .streamlit ./.streamlit
COPY src ./src
COPY dashboard ./dashboard

EXPOSE 8501

# o endereço de escuta e a conexão com o banco vêm do docker-compose.yml (variáveis de ambiente)
CMD ["streamlit", "run", "dashboard/app.py"]
