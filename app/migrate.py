import os
import sys

import psycopg2


DATABASE_URL = os.environ["DATABASE_URL"]


def migrate():
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)

    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS jobs (
                        id SERIAL PRIMARY KEY,
                        job_data TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )

        print("Migration completed successfully.")

    finally:
        conn.close()


if __name__ == "__main__":
    try:
        migrate()
    except Exception as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        sys.exit(1)
