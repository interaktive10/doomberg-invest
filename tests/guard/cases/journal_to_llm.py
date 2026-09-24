from pipeline.db.repo import load_journal  # seeded violation: journal data in an LLM module


def build_prompt() -> str:
    entries = load_journal()
    return "\n".join(e.reason for e in entries)
