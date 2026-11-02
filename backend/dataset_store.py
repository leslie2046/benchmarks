"""Dataset persistence. All writes lock the parent to serialize edits and generation."""
import json
import uuid

from fastapi import HTTPException

from backend.store import utc_now
from backend.dataset_golden import canonical_item


class DatasetStore:
    def __init__(self, store):
        self.store = store

    def create(self, values):
        now = utc_now()
        dataset = {"id": uuid.uuid4().hex[:12], "created_at": now, "updated_at": now,
                   "status": "ready", "item_count": 0, "error": None, **values}
        with self.store._session() as connection:
            connection.execute("INSERT INTO datasets VALUES (%s,%s,%s,%s)",
                               (dataset['id'], now, now, json.dumps(dataset, ensure_ascii=False)))
        return dataset

    def get(self, identifier):
        with self.store._session() as connection:
            row = connection.execute("SELECT payload FROM datasets WHERE id=%s", (identifier,)).fetchone()
        if not row:
            raise HTTPException(404, "数据集不存在")
        return json.loads(row['payload'])

    def page(self, page, size, q):
        return self.store._page("datasets", "updated_at", page, size, q=q)

    def items(self, identifier, page=1, size=20, q=""):
        self.get(identifier)
        with self.store._session() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            args = (identifier, q)
            where = "dataset_id=%s AND strpos(lower(payload), lower(%s))>0"
            total = connection.execute("SELECT count(*) AS n FROM dataset_items WHERE " + where, args).fetchone()['n']
            page = min(page, max(1, (total + size - 1) // size))
            rows = connection.execute("SELECT payload FROM dataset_items WHERE " + where + " ORDER BY created_at,id LIMIT %s OFFSET %s", (*args, size, (page - 1) * size)).fetchall()
        return {"items": [canonical_item(json.loads(r['payload'])) for r in rows], "total": total, "page": page, "page_size": size}

    def mutate(self, identifier, action, *, generating=False):
        with self.store._session() as connection:
            row = connection.execute("SELECT payload FROM datasets WHERE id=%s FOR UPDATE", (identifier,)).fetchone()
            if not row:
                raise HTTPException(404, "数据集不存在")
            dataset = json.loads(row['payload'])
            if dataset['status'] == 'generating' and not generating:
                raise HTTPException(409, "数据集正在构建，请等待完成后再修改")
            action(connection, dataset)
            dataset['updated_at'] = utc_now()
            connection.execute("UPDATE datasets SET updated_at=%s,payload=%s WHERE id=%s",
                               (dataset['updated_at'], json.dumps(dataset, ensure_ascii=False), identifier))
        return dataset

    def add(self, identifier, items, *, generating=False):
        def action(connection, dataset):
            if dataset['item_count'] + len(items) > 20000:
                raise HTTPException(400, "每个数据集最多支持 20000 条数据")
            now = utc_now()
            for item in items:
                item = {**canonical_item(item), 'id': uuid.uuid4().hex, 'dataset_id': identifier, 'created_at': now, 'updated_at': now}
                connection.execute("INSERT INTO dataset_items VALUES (%s,%s,%s,%s,%s)",
                                   (item['id'], identifier, now, now, json.dumps(item, ensure_ascii=False)))
            dataset['item_count'] += len(items)
        return self.mutate(identifier, action, generating=generating)

    def update_item(self, identifier, item_id, values=None):
        def action(connection, dataset):
            row = connection.execute("SELECT payload FROM dataset_items WHERE dataset_id=%s AND id=%s", (identifier, item_id)).fetchone()
            if not row:
                raise HTTPException(404, "数据项不存在")
            if values is None:
                connection.execute("DELETE FROM dataset_items WHERE dataset_id=%s AND id=%s", (identifier, item_id))
                dataset['item_count'] -= 1
            else:
                # PUT replaces Golden content so cleared optional fields do not survive.
                old = json.loads(row['payload'])
                item = {**canonical_item(values), **{k: old[k] for k in ('id', 'dataset_id', 'created_at')}, 'updated_at': utc_now()}
                connection.execute("UPDATE dataset_items SET updated_at=%s,payload=%s WHERE dataset_id=%s AND id=%s",
                                   (item['updated_at'], json.dumps(item, ensure_ascii=False), identifier, item_id))
        return self.mutate(identifier, action)

    def delete(self, identifier):
        def action(connection, dataset):
            connection.execute("DELETE FROM dataset_items WHERE dataset_id=%s", (identifier,))
            connection.execute("DELETE FROM dataset_sources WHERE dataset_id=%s", (identifier,))
            connection.execute("DELETE FROM datasets WHERE id=%s", (identifier,))
        self.mutate(identifier, action)

    def sources(self, identifier):
        with self.store._session() as connection:
            row = connection.execute("SELECT payload FROM dataset_sources WHERE dataset_id=%s", (identifier,)).fetchone()
        return json.loads(row['payload']) if row else []

    def save_sources(self, identifier, chunks):
        with self.store._session() as connection:
            connection.execute("INSERT INTO dataset_sources VALUES (%s,%s) ON CONFLICT (dataset_id) DO UPDATE SET payload=EXCLUDED.payload", (identifier, json.dumps(chunks, ensure_ascii=False)))
