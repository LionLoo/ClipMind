from tinydb import TinyDB
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import re
from datetime import datetime, timedelta
import dateparser
import config
from dateutil.relativedelta import relativedelta
from dateparser.search import search_dates
from datetime import datetime, timedelta
db = TinyDB(config.db_file)
embedding_model = SentenceTransformer(config.embedded_model_name)

def parse_time_string(query: str):
    # parses througha a time string and return the time delta between now and then

    now = datetime.now()
    query = query.lower()

    # match either past or last day (option) number (optional) minute hour day week month year (s)
    matches = re.findall(
        r"(past|last)?\s*(\d+)?\s*(minute|min|hour|hr|day|week|month|year|yr)s?",
        query
    )
    print("[DEBUG] Time query:", query)
    print("[DEBUG] Matches:", matches)
    print("[DEBUG] Now:", now)
    if matches:
        prefix, num, unit = matches[0]
        amount = 1
        if num:
            amount = int(num)

        if unit == "minute" or unit == "min":
            return now - timedelta(minutes=amount), None

        if unit == "hour" or unit == "hr":
            return now - timedelta(hours=amount), None

        if unit == "day":
            return now - timedelta(days=amount), None

        if unit == "week":
            return now - timedelta(weeks=amount), None

        if unit == "month":
            return now - timedelta(days=30*amount), None

        if unit == "year" or unit == "yr":
            return now - timedelta(days=365*amount), None

    if "yesterday" in query:
        return now - timedelta(days=1), None

    if "everything" in query or "all" in query:
        return datetime.min, None

    raise ValueError("No time expression found :(")

def extract_time_cutoff(query:str):
    query_lower = query.lower()
    time_keywords = ["past", "last", "from", "yesterday", "all", "everything"]
    should_parse_natural = any(kw in query_lower for kw in time_keywords)

    try:
        return parse_time_string(query)
    except:
        pass
    print("Passing human parse")
    if not should_parse_natural:
        return None, None

    matches = search_dates(query)
    if not matches:
        return None, None

    match_text, parsed_text = matches[0]
    text = match_text.lower()

    #year
    if parsed_text.month == 1 and parsed_text.day == 1 and "20" in text:
        end = parsed_text.replace(month=12, day=31, hour =23, minute=59, second=59)
        return parsed_text, end

    #month
    if parsed_text.day == 1:
        end = parsed_text.replace(day=31, hour=23, minute=59, second=59)
        return parsed_text, end

    #day
    end = parsed_text.replace(hour=23, minute=59, second=59)
    return parsed_text, end

def filter_timestamps(entries, time_start=None, time_end=None):
    if time_start is None:
        return entries

    start = time_start.timestamp()
    end = float("inf")
    if time_end:
        end = time_end.timestamp()

    filtered = []
    for entry in entries:
        if "timestamp" in entry:
            try:
                ts = entry.get("timestamp", 0)
                if start <= ts <= end:
                    filtered.append(entry)
            except:
                pass
    return filtered

def strip_dates_from_text(query: str):
    original_query = query
    query = query.lower()

    should_strip = any(kw in query for kw in ["past", "last", "from", "yesterday", "all", "everything"])
    if not should_strip:
        return original_query.strip()

    fuzzy_pattern = r"(past|last)?\s*\d*\s*(minute|min|hour|hr|day|week|month|year|yr)s?|yesterday|all|everything|from"
    query = re.sub(fuzzy_pattern, '', query, flags=re.IGNORECASE)

    matches = search_dates(query)
    if matches:
        for match_text, _ in sorted(matches, key=lambda x: -len(x[0])):
                match_clean = match_text.strip()

                if match_clean.isdigit():
                    number = int(match_clean)
                    if 2005 <= number <= 2105:
                        query = query.replace(match_text.lower(), '')
                else:
                    query = query.replace(match_text.lower(), '')

    return query.strip()

########################################################################################################################

while True:
    try:
        query = input("\nEnter your search: ")

        entries = db.all()

        time_start, time_end = extract_time_cutoff(query)
        stripped_query = strip_dates_from_text(query)
        print("[DEBUG] Extracted time window:", time_start, time_end)

        time_filtered_entries = filter_timestamps(entries, time_start, time_end)

        if not time_filtered_entries:
            print("No entries Found")
            continue

        filtered_texts = []
        filtered_embeddings = []

        # filter out legacy entries that don't have embeddings
        for entry in time_filtered_entries:
            if "embedding" in entry:
                filtered_texts.append(entry["text"])
                filtered_embeddings.append(entry["embedding"])

        if not filtered_embeddings:
            print("No entries Found")
            continue

        filtered_matrix = np.array(filtered_embeddings).astype("float32")
        dimension = filtered_matrix.shape[1]

        # building FAISS index
        temp_index = faiss.IndexFlatL2(dimension)
        temp_index.add(filtered_matrix)
        print("[DEBUG] This is the query:", stripped_query)
        query_vector = embedding_model.encode(stripped_query).astype("float32").reshape(1,-1)

        distances, indices = temp_index.search(query_vector, config.top_k_results)

        print(f"\nTop {config.top_k_results} Matches:\n")
        for i, dist in zip(indices[0], distances[0]):
            print(f"[{dist:.2f}] {filtered_texts[i]}")
    except KeyboardInterrupt:
        print("Goodbye :)")





