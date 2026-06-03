"""Create the PostgreSQL schema. Idempotent."""
import os as _os, sys as _sys  # _PROJECT_ROOT_BOOTSTRAP
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from backend.db import Database

if __name__ == "__main__":
    Database().init_schema()
    print("[init_db] schema created / verified.")
