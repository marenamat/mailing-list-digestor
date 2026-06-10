FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY digestor ./digestor

EXPOSE 8080

CMD ["python", "-m", "digestor"]
