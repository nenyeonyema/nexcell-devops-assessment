import os, time, redis

r = redis.Redis.from_url(os.environ["REDIS_URL"])
QUEUE = os.environ.get("QUEUE_NAME", "jobs")

while True:
    job = r.blpop(QUEUE, timeout=5)
    if job:
        print(f"processed: {job}")
    time.sleep(0.1)
