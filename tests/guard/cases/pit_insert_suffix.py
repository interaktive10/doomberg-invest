def _q(sql):
    return sql.encode()


def peek_insert(t):  # seeded violation: a helper named like _insert() is not the insert helper
    return f"select * from {t}"


def latest(conn):
    return conn.execute(_q(peek_insert("fundamentals_q")))
