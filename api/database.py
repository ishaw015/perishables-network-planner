from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from .config import DATABASE_URL

pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=5, open=False,
                      kwargs={"row_factory": dict_row}, check=ConnectionPool.check_connection)

def get_conn():
    """one database connection per request; rolled back automatically if the request fails"""
    with pool.connection() as conn:
        yield conn