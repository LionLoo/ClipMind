import re
from dateparser.search import search_dates

def strip_time_phrases(original_query: str) -> str:
    query = original_query
    if not any(kw in query.lower() for kw in
               ["past", "last", "from", "yesterday", "all", "everything", "week", "month", "year", "days", "hours"]):
        return original_query.strip()

    fuzzy = r"(past|last)?\s*\d*\s*(minute|min|hour|hr|day|week|month|year|yr)s?|yesterday|all|everything|from"
    query = re.sub(fuzzy, "", query, flags=re.IGNORECASE).strip()

    matches = search_dates(query) or []
    for text, _ in sorted(matches, key=lambda t: -len(t[0])):
        if not text.strip().isdigit():
            query = query.replace(text, "").strip()

    return query.strip()
