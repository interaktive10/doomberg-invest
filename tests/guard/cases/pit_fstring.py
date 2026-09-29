TABLE_NAME = "fundamentals_q"  # seeded violation: the table name as a value


def read(cur):
    return cur.execute(f"select * from {TABLE_NAME}")
