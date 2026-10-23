"""Step 6: run the validated SQL on a read-only SQLite connection with a time limit."""
import sqlite3
import time
from dataclasses import dataclass, field

from pipeline.validate_sql import MAX_ROWS


class QueryTimeout(RuntimeError):
    pass


class ExecutionError(RuntimeError):
    pass


@dataclass
class QueryResult:
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    truncated: bool = False
    elapsed_ms: int = 0


def run_readonly(sql: str, db_path, timeout_s: float = 3.0, authorizer=None) -> QueryResult:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    if authorizer is not None:
        conn.set_authorizer(authorizer)  # role rules: denied tables or columns fail while the query compiles
    deadline = time.monotonic() + timeout_s
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    start = time.monotonic()
    try:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description]
        fetched = cur.fetchall()
    except sqlite3.OperationalError as exc:
        if "interrupted" in str(exc).lower():
            raise QueryTimeout(f"The query took longer than {timeout_s:g} seconds.") from exc
        raise ExecutionError(str(exc)) from exc
    except sqlite3.Error as exc:
        raise ExecutionError(str(exc)) from exc
    finally:
        conn.close()

    truncated = len(fetched) > MAX_ROWS
    rows = [list(r) for r in fetched[:MAX_ROWS]]
    return QueryResult(columns=columns, rows=rows, truncated=truncated,
                       elapsed_ms=int((time.monotonic() - start) * 1000))
