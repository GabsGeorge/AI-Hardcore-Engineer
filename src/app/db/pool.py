"""Process-wide async connection pool, shared by repositories and the LangGraph checkpointer."""

from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

Pool = AsyncConnectionPool[AsyncConnection[DictRow]]

_pool: Pool | None = None


async def open_pool(database_url: str) -> Pool:
    global _pool
    # autocommit + prepare_threshold=0 + dict_row are required by AsyncPostgresSaver.
    _pool = AsyncConnectionPool(
        database_url,
        connection_class=AsyncConnection[DictRow],
        min_size=1,
        max_size=10,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await _pool.open(wait=True, timeout=30)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> Pool:
    if _pool is None:
        raise RuntimeError("database pool is not open")
    return _pool
