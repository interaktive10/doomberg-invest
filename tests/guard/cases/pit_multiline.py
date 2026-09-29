SQL = """
    select revenue
      from
        fundamentals_q
     where company_id = %s
"""  # seeded violation: a read split across lines
