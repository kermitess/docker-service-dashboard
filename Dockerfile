FROM python:3.12-alpine

WORKDIR /app

COPY app.py index.html ./

EXPOSE 8080

CMD ["python3", "app.py"]
