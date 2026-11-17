FROM python:3.12-slim

WORKDIR /app

COPY server.py .

ENV LPD_QUEUE=cola

EXPOSE 1515

CMD ["python", "-u", "server.py"]
