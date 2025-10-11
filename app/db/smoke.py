from app.db.session import init_db, get_session
from app.db.models import Item

def run():
    # Make sure tables exist
    init_db()

    # 1) Insert one row
    sample_text = "hello from test"
    with get_session() as session:
        new_item = Item(text=sample_text)
        session.add(new_item)
        session.commit()
        session.refresh(new_item)
        print(f"Inserted row id={new_item.id}, text={new_item.text}")


    with get_session() as session:
        all_rows = session.query(Item).all()
        print(f"Total rows now: {len(all_rows)}")
        last = all_rows[-1]
        print(f"Last row -> id={last.id}, text={last.text}, created_ts={last.created_ts}, readable_time={last.readable_time}")

if __name__ == "__main__":
    run()
