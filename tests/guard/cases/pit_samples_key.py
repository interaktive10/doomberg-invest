_SAMPLES: dict[str, str] = {}

_T = next(iter({"fundamentals_q": 0}))  # seeded violation: a dict key outside the probe samples


def read(conn):
    return conn.execute(f"select * from {_T}")
