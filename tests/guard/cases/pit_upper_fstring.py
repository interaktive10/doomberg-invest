T = "FUNDAMENTALS_Q"  # seeded violation: Postgres folds the name to fundamentals_q


def read(cur):
    return cur.execute(f"select * from {T}")
