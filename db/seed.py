"""Legacy entry — use backend/db/seed.py instead."""
from backend.db.seed import init_db, run_seed

if __name__ == "__main__":
    init_db(force=True)
