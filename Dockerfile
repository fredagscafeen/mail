FROM python:3.8

RUN apt-get update && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

RUN mkdir -p error errorarchive

EXPOSE 9000

CMD ["python", "-m", "datmail", "--listen-port", "9000", "--port", "25"]
