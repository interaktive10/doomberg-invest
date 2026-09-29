from pipeline.db.size_guard import _PROBE_TABLES  # seeded violation: size_guard's table names used to build a read


def read(cur):
    return cur.execute(f"select * from {_PROBE_TABLES[0]}")
