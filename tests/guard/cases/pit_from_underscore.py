def rows(db):  # seeded violation: ORM read with .from_()
    return db.from_("ownership_q").select("*")
