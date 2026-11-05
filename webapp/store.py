"""SQLite persistence; each operation owns its connection."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'products.db'
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS products (
              id INTEGER PRIMARY KEY, platform TEXT NOT NULL, item_id TEXT NOT NULL,
              title TEXT NOT NULL, url TEXT, current_price REAL, image_url TEXT,
              keyword TEXT, crawled_at TEXT, image_path TEXT, image_status TEXT DEFAULT 'pending',
              image_error TEXT, UNIQUE(platform,item_id));
            CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS drafts (id INTEGER PRIMARY KEY, product_id INTEGER UNIQUE,
              data TEXT NOT NULL);
            ''')

    def connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def upsert(self, p: dict[str, Any], keyword: str) -> int:
        with self.connect() as c:
            c.execute('''INSERT INTO products(platform,item_id,title,url,current_price,image_url,keyword,crawled_at)
              VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(platform,item_id) DO UPDATE SET
              title=excluded.title,url=excluded.url,current_price=excluded.current_price,
              image_status=CASE WHEN products.image_url IS excluded.image_url THEN products.image_status ELSE 'pending' END,
              image_path=CASE WHEN products.image_url IS excluded.image_url THEN products.image_path ELSE NULL END,
              image_url=excluded.image_url,keyword=excluded.keyword,crawled_at=excluded.crawled_at''',
              (p['platform'],str(p['item_id']),p['title'],p.get('url'),p.get('current_price'),p.get('image_url'),keyword,now()))
            return c.execute('SELECT id FROM products WHERE platform=? AND item_id=?',(p['platform'],str(p['item_id']))).fetchone()[0]

    def products(self, q: str = '', platform: str = '', status: str = '', page: int = 1, size: int = 24) -> dict[str, Any]:
        where, args = ['1=1'], []
        if q:
            where.append('(instr(title,?)>0 OR instr(keyword,?)>0 OR instr(item_id,?)>0)'); args.extend([q,q,q])
        if platform: where.append('platform=?'); args.append(platform)
        if status: where.append('image_status=?'); args.append(status)
        sql = ' FROM products WHERE ' + ' AND '.join(where)
        with self.connect() as c:
            total = c.execute('SELECT count(*)'+sql,args).fetchone()[0]
            rows = c.execute('SELECT *'+sql+' ORDER BY id DESC LIMIT ? OFFSET ?',args+[size,(page-1)*size]).fetchall()
        return {'items':[dict(r) for r in rows], 'total':total}

    def selected(self, ids: list[int]) -> list[dict[str, Any]]:
        if not ids: return []
        with self.connect() as c:
            return [dict(r) for r in c.execute('SELECT * FROM products WHERE id IN ('+','.join('?' for _ in ids)+')',ids)]

    def image_result(self, pid: int, path: str | None, error: str | None) -> None:
        with self.connect() as c:
            c.execute('UPDATE products SET image_path=?,image_status=?,image_error=? WHERE id=?',
                      (path,'failed' if error else 'downloaded',error,pid))

    def save_task(self, task: dict[str, Any]) -> None:
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO tasks VALUES(?,?)',(task['id'],json.dumps(task,ensure_ascii=False)))

    def tasks(self) -> list[dict[str, Any]]:
        with self.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT data FROM tasks ORDER BY rowid DESC LIMIT 200')]

    def delete(self, ids: list[int]) -> None:
        with self.connect() as c:
            c.executemany('DELETE FROM products WHERE id=?',[(i,) for i in ids])

    def drafts(self) -> list[dict[str, Any]]:
        with self.connect() as c:
            return [{'id':r['id'],**json.loads(r['data'])} for r in c.execute('SELECT * FROM drafts ORDER BY id DESC')]

    def add_drafts(self, ids: list[int]) -> None:
        with self.connect() as c:
            for p in self.selected(ids):
                draft = {'title':p['title'],'description':'','price':p['current_price'], 'category':'', 'stock':1,
                         'sku':[], 'images':[p['image_path']] if p['image_path'] else [],
                         'logistics':{},'platform_fields':{},'platforms':[], 'source_url':p['url']}
                c.execute('INSERT OR IGNORE INTO drafts(product_id,data) VALUES(?,?)',(p['id'],json.dumps(draft,ensure_ascii=False)))

    def update_draft(self, did: int, data: dict[str, Any]) -> bool:
        with self.connect() as c:
            return c.execute('UPDATE drafts SET data=? WHERE id=?',(json.dumps(data,ensure_ascii=False),did)).rowcount > 0
