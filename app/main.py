import os
import redis
import psycopg2
from fastapi import FastAPI, Response

app = FastAPI()

def check_redis():
    r = redis.Redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=2)
    r.ping()

def check_postgres():
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=2)
    conn.close()

@app.get("/health")
def health():
    return {"status": "alive"}

@app.get("/ready")
def ready(response: Response):
    try:
        check_redis()
        check_postgres()
        return {"status": "ready"}
    except Exception as e:
        response.status_code = 503
        return {"status": "not ready", "error": str(e)}
