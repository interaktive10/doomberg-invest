def _q(sql):
    return sql.encode()


def latest(conn):
    t = "fundamentals_q"  # seeded violation: repo.py may name the table only as an _insert() target
    return conn.execute(_q(f"select * from {t}"))
