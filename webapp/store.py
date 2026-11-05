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

            columns={r[1] for r in c.execute('PRAGMA table_info(products)')}
            for name, definition in [('description',"TEXT DEFAULT ''"),('detail_status',"TEXT DEFAULT 'pending'"),('detail_error','TEXT')]:
                if name not in columns: c.execute(f'ALTER TABLE products ADD COLUMN {name} {definition}')
            c.execute('''CREATE TABLE IF NOT EXISTS product_images (
                id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, url TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'gallery', position INTEGER NOT NULL DEFAULT 0,
                path TEXT, status TEXT NOT NULL DEFAULT 'pending', error TEXT,
                UNIQUE(product_id,url))''')
            for row in c.execute("SELECT * FROM products WHERE COALESCE(image_url,'')<>''").fetchall():
                c.execute('''INSERT OR IGNORE INTO product_images(product_id,url,kind,path,status,error)
                    VALUES(?,?,'main',?,?,?)''',(row['id'],row['image_url'],row['image_path'],row['image_status'],row['image_error']))

    def gallery(self, pid: int) -> list[dict]:
        with self.connect() as c:
            return [dict(r) for r in c.execute('SELECT * FROM product_images WHERE product_id=? ORDER BY position,id',(pid,))]

    def gallery_result(self, iid: int, path: str | None, error: str | None) -> None:
        with self.connect() as c:
            c.execute('UPDATE product_images SET path=?,status=?,error=? WHERE id=?',(path,'failed' if error else 'downloaded',error,iid))
            row=c.execute('SELECT * FROM product_images WHERE id=?',(iid,)).fetchone()
            if row and row['kind']=='main':
                c.execute('UPDATE products SET image_path=?,image_status=?,image_error=? WHERE id=?',(path,'failed' if error else 'downloaded',error,row['product_id']))

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
            pid=c.execute('SELECT id FROM products WHERE platform=? AND item_id=?',(p['platform'],str(p['item_id']))).fetchone()[0]
            if 'detail_status' in p:
                c.execute('UPDATE products SET detail_status=?,detail_error=? WHERE id=?',(p['detail_status'],p.get('detail_error'),pid))
            if 'description' in p:
                c.execute('UPDATE products SET description=? WHERE id=?',(p['description'],pid))
            urls=list(dict.fromkeys(([p['image_url']] if p.get('image_url') else [])+p.get('gallery',[])))
            for index,url in enumerate(urls):
                c.execute('INSERT OR IGNORE INTO product_images(product_id,url,kind,position) VALUES(?,?,?,?)',
                          (pid,url,'main' if url==p.get('image_url') else p.get('image_kinds',{}).get(url,'gallery'),index))
                kind=p.get('image_kinds',{}).get(url)
                if kind in ('gallery','sku','detail') and url!=p.get('image_url'):
                    c.execute('UPDATE product_images SET kind=? WHERE product_id=? AND url=?',(kind,pid,url))
            c.execute("UPDATE product_images SET kind=CASE WHEN url=? THEN 'main' WHEN kind='main' THEN 'gallery' ELSE kind END WHERE product_id=?",(p.get('image_url'),pid))
            return pid

    def products(self, q: str = '', platform: str = '', status: str = '', page: int = 1, size: int = 24) -> dict[str, Any]:
        where, args = ['1=1'], []
        if q:
            where.append('(instr(title,?)>0 OR instr(keyword,?)>0 OR instr(item_id,?)>0)'); args.extend([q,q,q])
        if platform: where.append('platform=?'); args.append(platform)
        if status == 'available': where.append("EXISTS(SELECT 1 FROM product_images i WHERE i.product_id=products.id AND i.status<>'downloaded')")
        elif status == 'unavailable': where.append("NOT EXISTS(SELECT 1 FROM product_images i WHERE i.product_id=products.id)")
        elif status == 'downloaded': where.append("EXISTS(SELECT 1 FROM product_images i WHERE i.product_id=products.id) AND NOT EXISTS(SELECT 1 FROM product_images i WHERE i.product_id=products.id AND i.status<>'downloaded')")
        elif status: where.append('EXISTS(SELECT 1 FROM product_images i WHERE i.product_id=products.id AND i.status=?)'); args.append(status)
        sql = ' FROM products WHERE ' + ' AND '.join(where)
        with self.connect() as c:
            total = c.execute('SELECT count(*)'+sql,args).fetchone()[0]
            rows = c.execute("SELECT products.*, (SELECT count(*) FROM product_images i WHERE i.product_id=products.id) AS image_count, (SELECT count(*) FROM product_images i WHERE i.product_id=products.id AND i.status='downloaded') AS downloaded_count, (SELECT count(*) FROM product_images i WHERE i.product_id=products.id AND i.status='failed') AS failed_count"+sql+' ORDER BY id DESC LIMIT ? OFFSET ?',args+[size,(page-1)*size]).fetchall()
        return {'items':[dict(r) for r in rows], 'total':total}

    def selected(self, ids: list[int]) -> list[dict[str, Any]]:
        if not ids: return []
        with self.connect() as c:
            return [dict(r) for r in c.execute('SELECT * FROM products WHERE id IN ('+','.join('?' for _ in ids)+')',ids)]

    def image_result(self, pid: int, path: str | None, error: str | None) -> None:
        with self.connect() as c:
            c.execute('UPDATE products SET image_path=?,image_status=?,image_error=? WHERE id=?',
                      (path,'failed' if error else 'downloaded',error,pid))
            c.execute("UPDATE product_images SET path=?,status=?,error=? WHERE product_id=? AND kind='main'",(path,'failed' if error else 'downloaded',error,pid))

    def save_task(self, task: dict[str, Any]) -> None:
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO tasks VALUES(?,?)',(task['id'],json.dumps(task,ensure_ascii=False)))

    def tasks(self) -> list[dict[str, Any]]:
        with self.connect() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT data FROM tasks ORDER BY rowid DESC LIMIT 200')]

    def delete(self, ids: list[int]) -> None:
        with self.connect() as c:
            c.executemany('DELETE FROM product_images WHERE product_id=?',[(i,) for i in ids])
            c.executemany('DELETE FROM products WHERE id=?',[(i,) for i in ids])

    def drafts(self) -> list[dict[str, Any]]:
        with self.connect() as c:
            return [{'id':r['id'],**json.loads(r['data'])} for r in c.execute('SELECT * FROM drafts ORDER BY id DESC')]

    def add_drafts(self, ids: list[int]) -> None:
        with self.connect() as c:
            for p in self.selected(ids):
                draft = {'title':p['title'],'description':'','price':p['current_price'], 'category':'', 'stock':1,
                         'sku':[], 'images':list(dict.fromkeys(i['path'] for i in self.gallery(p['id']) if i['path'])),
                         'logistics':{},'platform_fields':{},'platforms':[], 'source_url':p['url']}
                c.execute('INSERT OR IGNORE INTO drafts(product_id,data) VALUES(?,?)',(p['id'],json.dumps(draft,ensure_ascii=False)))

    def update_draft(self, did: int, data: dict[str, Any]) -> bool:
        with self.connect() as c:
            return c.execute('UPDATE drafts SET data=? WHERE id=?',(json.dumps(data,ensure_ascii=False),did)).rowcount > 0
