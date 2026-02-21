"""
CRM Dashboard — Multi-File Version
✅ Multiple Files/Projects — har file ka alag data, alag columns
✅ Unnamed columns Excel import mein skip
✅ Add Record: Full Row + Single Column tabs
✅ 📎 Attachment button in each row
✅ Excel import/export per file
✅ Full CRUD + Search

pip install flask openpyxl pandas werkzeug
python app.py → http://127.0.0.1:5000
"""

import os, json, uuid, sqlite3
from datetime import datetime, date
from flask import Flask, render_template_string, request, jsonify, send_from_directory, url_for, send_file
from werkzeug.utils import secure_filename
import pandas as pd
import io

app = Flask(__name__)
app.config['SECRET_KEY']         = 'crm-2025-secret'
app.config['UPLOAD_FOLDER']      = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crm.db')

ALLOWED = {'png','jpg','jpeg','gif','webp','pdf','mp4','mov','avi','mkv','xlsx','xls','docx','txt','csv'}
COLORS  = ['#00c8ff','#00e07a','#ff9500','#ff3d5a','#a855f7','#f59e0b','#06b6d4','#84cc16']
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# ─────────────── DB ───────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                color      TEXT DEFAULT '#00c8ff',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS crm_columns (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name       TEXT NOT NULL,
                col_type   TEXT DEFAULT 'text',
                col_order  INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS crm_records (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                data       TEXT DEFAULT '{}',
                tags       TEXT DEFAULT '',
                notes      TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS attachments (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id     INTEGER NOT NULL REFERENCES crm_records(id) ON DELETE CASCADE,
                filename      TEXT NOT NULL,
                original_name TEXT NOT NULL,
                file_type     TEXT DEFAULT 'file',
                file_size     INTEGER DEFAULT 0,
                created_at    TEXT DEFAULT (datetime('now'))
            );
        """)
        cnt = conn.execute("SELECT COUNT(*) as c FROM projects").fetchone()['c']
        if cnt == 0:
            c = conn.execute("INSERT INTO projects(name,color) VALUES(?,?)",
                             ('Filter Bag Tracker', '#00c8ff'))
            pid = c.lastrowid
            defaults = [
                ('Client Name','text'),('Location','text'),('PO Number','text'),
                ('Item Code','text'),  ('Size','text'),    ('Type','text'),
                ('Material','text'),   ('Diameter','text'),('Quantity','number'),
                ('Date','text'),       ('Remarks','text')
            ]
            conn.executemany(
                "INSERT INTO crm_columns(project_id,name,col_type,col_order) VALUES(?,?,?,?)",
                [(pid, n, t, i) for i, (n, t) in enumerate(defaults)]
            )

init_db()


# ─────────────── UTILS ───────────────
def _human_size(n):
    n = n or 0
    for u in ['B','KB','MB','GB']:
        if n < 1024: return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"

def _file_type(fn):
    e = fn.rsplit('.',1)[-1].lower() if '.' in fn else ''
    if e in {'png','jpg','jpeg','gif','webp'}: return 'image'
    if e == 'pdf':  return 'pdf'
    if e in {'mp4','mov','avi','mkv','webm'}: return 'video'
    return 'file'

def allowed(fn):
    return '.' in fn and fn.rsplit('.',1)[1].lower() in ALLOWED

def fmt_date(s):
    if not s: return ''
    try:    return datetime.fromisoformat(s.split('.')[0]).strftime('%d %b %Y')
    except: return s

def att_to_dict(a):
    return {
        'id': a['id'], 'filename': a['filename'],
        'original_name': a['original_name'], 'file_type': a['file_type'],
        'file_size_str': _human_size(a['file_size']),
        'url': url_for('serve_upload', filename=a['filename'])
    }

def record_to_dict(row, atts):
    try:    data = json.loads(row['data'])
    except: data = {}
    return {
        'id': row['id'], 'data': data,
        'tags': row['tags'] or '', 'notes': row['notes'] or '',
        'created_at': fmt_date(row['created_at']),
        'attachments': atts
    }

def get_record_with_atts(conn, rid):
    row = conn.execute("SELECT * FROM crm_records WHERE id=?", (rid,)).fetchone()
    if not row: return None
    atts = [att_to_dict(a) for a in
            conn.execute("SELECT * FROM attachments WHERE record_id=? ORDER BY id", (rid,)).fetchall()]
    return record_to_dict(row, atts)


# ─────────────── API — PROJECTS ───────────────
@app.route('/')
def index(): return render_template_string(HTML)

@app.route('/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/projects')
def get_projects():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at").fetchall()
        result = []
        for r in rows:
            rc = conn.execute(
                "SELECT COUNT(*) as c FROM crm_records WHERE project_id=?",
                (r['id'],)).fetchone()['c']
            result.append({'id': r['id'], 'name': r['name'], 'color': r['color'],
                           'created_at': fmt_date(r['created_at']), 'record_count': rc})
    return jsonify({'success': True, 'projects': result})

@app.route('/api/projects', methods=['POST'])
def add_project():
    d = request.get_json() or {}
    name = d.get('name','').strip()
    if not name: return jsonify({'success': False, 'message': 'Name required'}), 400
    with get_db() as conn:
        c = conn.execute("INSERT INTO projects(name,color) VALUES(?,?)",
                         (name, d.get('color','#00c8ff')))
        pid = c.lastrowid
        proj = dict(conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone())
    proj['record_count'] = 0
    proj['created_at'] = fmt_date(proj['created_at'])
    return jsonify({'success': True, 'project': proj})

@app.route('/api/projects/<int:pid>', methods=['DELETE'])
def del_project(pid):
    with get_db() as conn:
        recs = conn.execute("SELECT id FROM crm_records WHERE project_id=?", (pid,)).fetchall()
        for rec in recs:
            for a in conn.execute("SELECT filename FROM attachments WHERE record_id=?",
                                  (rec['id'],)).fetchall():
                try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], a['filename']))
                except: pass
        conn.execute("DELETE FROM projects WHERE id=?", (pid,))
    return jsonify({'success': True})


# ─────────────── API — COLUMNS ───────────────
@app.route('/api/projects/<int:pid>/columns')
def get_columns(pid):
    with get_db() as conn:
        cols = [dict(r) for r in conn.execute(
            "SELECT * FROM crm_columns WHERE project_id=? ORDER BY col_order", (pid,)).fetchall()]
    return jsonify({'success': True, 'columns': cols})

@app.route('/api/projects/<int:pid>/columns', methods=['POST'])
def add_column(pid):
    d = request.get_json() or {}
    name = d.get('name','').strip()
    if not name: return jsonify({'success': False, 'message': 'Name required'}), 400
    insert_after = d.get('insert_after', None)  # col_id jiske BAAD insert karna hai; None = end
    with get_db() as conn:
        if insert_after is None:
            mo = conn.execute(
                "SELECT MAX(col_order) as m FROM crm_columns WHERE project_id=?", (pid,)
            ).fetchone()['m'] or 0
            new_order = mo + 1
        else:
            ref = conn.execute(
                "SELECT col_order FROM crm_columns WHERE id=? AND project_id=?",
                (insert_after, pid)).fetchone()
            if ref:
                pos = ref['col_order']
                new_order = pos + 1
                # Baaki columns shift karo
                conn.execute(
                    "UPDATE crm_columns SET col_order = col_order + 1 "
                    "WHERE project_id=? AND col_order >= ?",
                    (pid, new_order))
            else:
                mo = conn.execute(
                    "SELECT MAX(col_order) as m FROM crm_columns WHERE project_id=?", (pid,)
                ).fetchone()['m'] or 0
                new_order = mo + 1
        c = conn.execute(
            "INSERT INTO crm_columns(project_id,name,col_type,col_order) VALUES(?,?,?,?)",
            (pid, name, d.get('col_type','text'), new_order))
        col = dict(conn.execute("SELECT * FROM crm_columns WHERE id=?", (c.lastrowid,)).fetchone())
    return jsonify({'success': True, 'column': col})

@app.route('/api/projects/<int:pid>/columns/<int:cid>', methods=['DELETE'])
def del_column(pid, cid):
    with get_db() as conn:
        for rec in conn.execute(
                "SELECT id, data FROM crm_records WHERE project_id=?", (pid,)).fetchall():
            try:
                d = json.loads(rec['data']); d.pop(str(cid), None)
                conn.execute("UPDATE crm_records SET data=? WHERE id=?", (json.dumps(d), rec['id']))
            except: pass
        conn.execute("DELETE FROM crm_columns WHERE id=? AND project_id=?", (cid, pid))
    return jsonify({'success': True})


# ─────────────── API — RECORDS ───────────────
@app.route('/api/projects/<int:pid>/records')
def get_records(pid):
    q = request.args.get('q','').strip().lower()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM crm_records WHERE project_id=? ORDER BY created_at DESC", (pid,)
        ).fetchall()
        result = []
        for row in rows:
            atts = [att_to_dict(a) for a in
                    conn.execute("SELECT * FROM attachments WHERE record_id=?",
                                 (row['id'],)).fetchall()]
            rec = record_to_dict(row, atts)
            if q:
                txt = ' '.join(str(v) for v in rec['data'].values()).lower()
                txt += ' ' + (rec['notes'] or '').lower() + ' ' + (rec['tags'] or '').lower()
                if q not in txt: continue
            result.append(rec)
    return jsonify({'success': True, 'records': result, 'total': len(result)})

@app.route('/api/projects/<int:pid>/records', methods=['POST'])
def add_record(pid):
    d = request.get_json() or {}
    with get_db() as conn:
        c = conn.execute(
            "INSERT INTO crm_records(project_id,data,tags,notes) VALUES(?,?,?,?)",
            (pid, json.dumps(d.get('data',{})), d.get('tags',''), d.get('notes','')))
        rec = get_record_with_atts(conn, c.lastrowid)
    return jsonify({'success': True, 'record': rec})

@app.route('/api/records/<int:rid>')
def get_record(rid):
    with get_db() as conn:
        rec = get_record_with_atts(conn, rid)
    if not rec: return jsonify({'success': False}), 404
    return jsonify({'success': True, 'record': rec})

@app.route('/api/records/<int:rid>', methods=['PUT'])
def upd_record(rid):
    d = request.get_json() or {}
    with get_db() as conn:
        row = conn.execute("SELECT * FROM crm_records WHERE id=?", (rid,)).fetchone()
        if not row: return jsonify({'success': False}), 404
        try:    old = json.loads(row['data'])
        except: old = {}
        conn.execute(
            "UPDATE crm_records SET data=?,tags=?,notes=?,updated_at=datetime('now') WHERE id=?",
            (json.dumps(d.get('data', old)),
             d.get('tags', row['tags']),
             d.get('notes', row['notes']), rid))
        rec = get_record_with_atts(conn, rid)
    return jsonify({'success': True, 'record': rec})

@app.route('/api/records/<int:rid>', methods=['DELETE'])
def del_record(rid):
    with get_db() as conn:
        for a in conn.execute("SELECT filename FROM attachments WHERE record_id=?",
                              (rid,)).fetchall():
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], a['filename']))
            except: pass
        conn.execute("DELETE FROM crm_records WHERE id=?", (rid,))
    return jsonify({'success': True})


# ─────────────── API — ATTACHMENTS ───────────────
@app.route('/api/records/<int:rid>/attachments', methods=['POST'])
def upload_att(rid):
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file'}), 400
    file = request.files['file']
    if not file.filename or not allowed(file.filename):
        return jsonify({'success': False, 'message': 'File type not allowed'}), 400
    orig   = secure_filename(file.filename)
    ext    = orig.rsplit('.',1)[-1] if '.' in orig else 'bin'
    stored = f"{uuid.uuid4().hex}.{ext}"
    fp     = os.path.join(app.config['UPLOAD_FOLDER'], stored)
    file.save(fp)
    with get_db() as conn:
        c = conn.execute(
            "INSERT INTO attachments(record_id,filename,original_name,file_type,file_size) VALUES(?,?,?,?,?)",
            (rid, stored, orig, _file_type(orig), os.path.getsize(fp)))
        a = dict(conn.execute("SELECT * FROM attachments WHERE id=?", (c.lastrowid,)).fetchone())
    return jsonify({'success': True, 'attachment': att_to_dict(a)})

@app.route('/api/attachments/<int:aid>', methods=['DELETE'])
def del_att(aid):
    with get_db() as conn:
        a = conn.execute("SELECT * FROM attachments WHERE id=?", (aid,)).fetchone()
        if not a: return jsonify({'success': False}), 404
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], a['filename']))
        except: pass
        conn.execute("DELETE FROM attachments WHERE id=?", (aid,))
    return jsonify({'success': True})


# ─────────────── API — IMPORT / EXPORT / STATS ───────────────
@app.route('/api/projects/<int:pid>/import', methods=['POST'])
def import_excel(pid):
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file'}), 400
    f = request.files['file']
    if not f.filename.endswith(('.xlsx','.xls')):
        return jsonify({'success': False, 'message': 'Only .xlsx / .xls'}), 400
    try:
        import re as _re
        # ── File memory mein padho taaki multiple baar read kar sake ──
        file_bytes = f.read()

        def _clean_hdrs(df):
            return [h for h in df.columns
                    if str(h).strip()
                    and not _re.match(r'^Unnamed:\s*\d+', str(h))
                    and str(h).strip().lower() not in ('nan','none','')]

        # Try 1: Row 1 as header (default)
        df = pd.read_excel(io.BytesIO(file_bytes), dtype=str).fillna('')
        headers = _clean_hdrs(df)

        # Try 2: Row 2 as header (skip title row)
        if not headers:
            df = pd.read_excel(io.BytesIO(file_bytes), dtype=str, header=1).fillna('')
            headers = _clean_hdrs(df)

        # Try 3: Row 3 as header
        if not headers:
            df = pd.read_excel(io.BytesIO(file_bytes), dtype=str, header=2).fillna('')
            headers = _clean_hdrs(df)

        # Last resort: use all non-empty column names as-is
        if not headers:
            df = pd.read_excel(io.BytesIO(file_bytes), dtype=str).fillna('')
            headers = [str(h).strip() for h in df.columns if str(h).strip()]
            df.columns = [str(c).strip() for c in df.columns]

        if not headers:
            return jsonify({'success': False,
                            'message': 'Excel mein koi valid column header nahi mila. Row 1 mein column names hone chahiye.'}), 400

        df = df[headers]

        with get_db() as conn:
            existing = {r['name'].strip().lower(): r['id'] for r in
                        conn.execute("SELECT id,name FROM crm_columns WHERE project_id=?",
                                     (pid,)).fetchall()}
            col_map = {}
            mo = conn.execute(
                "SELECT MAX(col_order) as m FROM crm_columns WHERE project_id=?", (pid,)
            ).fetchone()['m'] or 0

            for i, h in enumerate(headers):
                k = h.strip().lower()
                if k in existing:
                    col_map[h] = existing[k]
                else:
                    c = conn.execute(
                        "INSERT INTO crm_columns(project_id,name,col_type,col_order) VALUES(?,?,?,?)",
                        (pid, h.strip(), 'text', mo+i+1))
                    col_map[h] = c.lastrowid

            inserted = 0
            for _, row in df.iterrows():
                rd = {str(col_map[h]): str(row[h]).strip()
                      for h in headers
                      if str(row[h]).strip() and str(row[h]).strip() != 'nan'}
                if any(rd.values()):
                    conn.execute(
                        "INSERT INTO crm_records(project_id,data) VALUES(?,?)",
                        (pid, json.dumps(rd)))
                    inserted += 1

        return jsonify({'success': True, 'message': f'{inserted} rows imported',
                        'rows': inserted, 'cols': len(headers)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/projects/<int:pid>/export')
def export_excel(pid):
    with get_db() as conn:
        proj = conn.execute("SELECT name FROM projects WHERE id=?", (pid,)).fetchone()
        cols = conn.execute(
            "SELECT * FROM crm_columns WHERE project_id=? ORDER BY col_order", (pid,)).fetchall()
        recs = conn.execute(
            "SELECT * FROM crm_records WHERE project_id=? ORDER BY created_at DESC",
            (pid,)).fetchall()
    rows = []
    for r in recs:
        try:    d = json.loads(r['data'])
        except: d = {}
        row = {c['name']: d.get(str(c['id']),'') for c in cols}
        row['Notes']   = r['notes']
        row['Tags']    = r['tags']
        row['Created'] = fmt_date(r['created_at'])
        rows.append(row)
    out = io.BytesIO()
    pd.DataFrame(rows).to_excel(out, index=False, engine='openpyxl')
    out.seek(0)
    fname = f"{proj['name'] if proj else 'export'}.xlsx"
    return send_file(out,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True, download_name=fname)

@app.route('/api/stats/<int:pid>')
def stats(pid):
    today = date.today().isoformat()
    with get_db() as conn:
        records     = conn.execute("SELECT COUNT(*) as c FROM crm_records WHERE project_id=?",
                                   (pid,)).fetchone()['c']
        columns     = conn.execute("SELECT COUNT(*) as c FROM crm_columns WHERE project_id=?",
                                   (pid,)).fetchone()['c']
        today_c     = conn.execute(
            "SELECT COUNT(*) as c FROM crm_records WHERE project_id=? AND date(created_at)=?",
            (pid, today)).fetchone()['c']
        attachments = conn.execute(
            "SELECT COUNT(*) as c FROM attachments a "
            "JOIN crm_records r ON a.record_id=r.id WHERE r.project_id=?",
            (pid,)).fetchone()['c']
    return jsonify({'records': records, 'columns': columns,
                    'attachments': attachments, 'today': today_c})


# ─────────────── HTML ───────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>CRM Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=IBM+Plex+Mono:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
:root{
  --bg:#080c14;--s1:#0f1620;--s2:#141e2e;--s3:#192438;
  --b1:#1a3050;--b2:#1e3d66;
  --acc:#00c8ff;--acc2:#0090bb;--acc3:rgba(0,200,255,.1);
  --ok:#00e07a;--err:#ff3d5a;
  --t1:#ddeeff;--t2:#7aaed0;--t3:#3a6080;
  --fc:#00c8ff;
  --r:10px;--sh:0 12px 40px rgba(0,0,0,.6);
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;font-family:'IBM Plex Mono',monospace;background:var(--bg);color:var(--t1);font-size:13px}
.app{display:flex;height:100vh;overflow:hidden}

/* ── SIDEBAR ── */
.side{width:248px;min-width:248px;background:var(--s1);border-right:1px solid var(--b1);
      display:flex;flex-direction:column;overflow:hidden}
.logo{padding:15px 17px;border-bottom:1px solid var(--b1);flex-shrink:0}
.logo h1{font-family:'Syne',sans-serif;font-size:17px;font-weight:800;color:var(--acc);letter-spacing:2px}
.logo p{font-size:9px;color:var(--t3);letter-spacing:1px;margin-top:2px}

.files-hd{padding:10px 14px 6px;display:flex;align-items:center;
          justify-content:space-between;flex-shrink:0}
.files-hd span{font-size:9px;letter-spacing:1px;text-transform:uppercase;color:var(--t3)}
.new-file-btn{display:inline-flex;align-items:center;gap:3px;padding:4px 9px;
  border-radius:6px;background:var(--acc);color:#000;border:none;cursor:pointer;
  font-size:10px;font-weight:700;font-family:inherit;transition:.15s}
.new-file-btn:hover{background:var(--acc2)}

.file-list{flex:1;overflow-y:auto;padding:3px 7px}
.fi{display:flex;align-items:center;gap:7px;padding:8px 9px;border-radius:8px;
    cursor:pointer;transition:.15s;border:1px solid transparent;margin-bottom:2px;position:relative}
.fi:hover{background:var(--s2);border-color:var(--b1)}
.fi.on{background:rgba(0,200,255,.06);border-color:var(--fc)}
.fi-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.fi-name{flex:1;font-size:11px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fi.on .fi-name{color:var(--fc)}
.fi-cnt{font-size:9px;color:var(--t3);flex-shrink:0;background:var(--s2);
        padding:1px 5px;border-radius:4px}
.fi-del{opacity:0;background:none;border:none;color:var(--err);cursor:pointer;
        font-size:12px;padding:0 2px;transition:.15s;flex-shrink:0}
.fi:hover .fi-del{opacity:1}

.nav-btns{padding:8px 7px;border-top:1px solid var(--b1);display:flex;flex-direction:column;
          gap:2px;flex-shrink:0}
.ni{display:flex;align-items:center;gap:8px;padding:8px 9px;color:var(--t2);cursor:pointer;
    border-radius:8px;font-size:11px;transition:.15s;user-select:none;border:1px solid transparent}
.ni:hover,.ni.on{color:var(--fc);background:rgba(0,200,255,.06);border-color:rgba(0,200,255,.15)}
.ni svg{width:13px;height:13px;flex-shrink:0}
.side-foot{padding:9px 16px;border-top:1px solid var(--b1);font-size:9px;color:var(--t3)}

/* ── MAIN CONTENT ── */
.content{flex:1;display:flex;flex-direction:column;min-width:0;overflow:hidden}
.view{display:none;flex:1;flex-direction:column;overflow:hidden;min-height:0}
.view.on{display:flex}

/* No file */
.no-file{flex:1;display:flex;flex-direction:column;align-items:center;
         justify-content:center;gap:14px;color:var(--t3)}
.no-file h2{font-family:'Syne',sans-serif;font-size:17px;color:var(--t2)}
.no-file p{font-size:12px}

/* Topbar */
.topbar{padding:11px 18px;border-bottom:1px solid var(--b1);display:flex;align-items:center;
        justify-content:space-between;flex-wrap:wrap;gap:8px;background:var(--s1);flex-shrink:0}
.topbar h2{font-family:'Syne',sans-serif;font-size:17px;font-weight:800}
.topbar h2 span{color:var(--fc)}
.topbar-r{display:flex;gap:6px;flex-wrap:wrap;align-items:center}

/* Stats */
.stats{display:flex;gap:8px;padding:9px 18px;border-bottom:1px solid var(--b1);
       flex-wrap:wrap;background:var(--s2);flex-shrink:0}
.sc{background:var(--s1);border:1px solid var(--b1);border-radius:var(--r);
    padding:8px 13px;flex:1;min-width:100px;position:relative;overflow:hidden}
.sc::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;
           background:linear-gradient(90deg,var(--fc),transparent)}
.sc-l{font-size:9px;color:var(--t3);letter-spacing:1px;text-transform:uppercase;margin-bottom:2px}
.sc-v{font-family:'Syne',sans-serif;font-size:21px;font-weight:800;color:var(--fc)}

/* Toolbar */
.toolbar{padding:7px 18px;display:flex;align-items:center;gap:7px;flex-wrap:wrap;
         border-bottom:1px solid var(--b1);background:var(--s2);flex-shrink:0}
.srch{display:flex;align-items:center;gap:5px;background:var(--s1);border:1px solid var(--b1);
      border-radius:8px;padding:6px 10px;flex:1;max-width:300px}
.srch input{background:none;border:none;color:var(--t1);font-family:inherit;
            font-size:12px;outline:none;width:100%}
.srch input::placeholder{color:var(--t3)}
.rec-info{font-size:11px;color:var(--t3)}

/* Table */
.table-area{flex:1;overflow:auto;min-height:0}
table{width:100%;border-collapse:collapse;min-width:900px}
thead{position:sticky;top:0;z-index:20}
th{background:var(--s2);padding:8px 10px;text-align:left;font-size:9px;letter-spacing:1px;
   text-transform:uppercase;color:var(--t3);font-weight:500;border-bottom:2px solid var(--b1);
   white-space:nowrap}
.th-w{display:flex;align-items:center;gap:4px}
.dc{opacity:0;cursor:pointer;color:var(--err);font-size:12px;transition:.15s}
th:hover .dc{opacity:1}
td{padding:7px 10px;border-bottom:1px solid rgba(26,48,80,.4);color:var(--t1);
   vertical-align:middle;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
tr:hover td{background:rgba(0,200,255,.025)}
.td-n{color:var(--t3);font-size:10px;width:30px;text-align:right}
.td-act{white-space:nowrap;width:1%}

/* Att btn */
.att-btn{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:5px;
         font-size:10px;font-weight:600;cursor:pointer;border:1px solid var(--b2);
         background:var(--s3);color:var(--t2);transition:.15s;user-select:none}
.att-btn:hover{border-color:var(--acc);color:var(--acc);background:var(--acc3)}
.att-btn.has{background:rgba(0,224,122,.08);border-color:rgba(0,224,122,.4);color:var(--ok)}

/* Buttons */
.btn{display:inline-flex;align-items:center;gap:4px;padding:6px 11px;border-radius:8px;
     border:none;cursor:pointer;font-family:inherit;font-size:11px;font-weight:600;
     transition:.15s;white-space:nowrap}
.btn-acc{background:var(--acc);color:#000}.btn-acc:hover{background:var(--acc2)}
.btn-g{background:var(--s2);color:var(--t1);border:1px solid var(--b1)}
.btn-g:hover{border-color:var(--acc);color:var(--acc)}
.btn-err{background:rgba(255,61,90,.1);color:var(--err);border:1px solid rgba(255,61,90,.25)}
.btn-sm{padding:4px 8px;font-size:10px}
.btn-ico{padding:4px 6px}

/* Modals */
.ovl{position:fixed;inset:0;background:rgba(0,0,0,.78);z-index:500;display:none;
     align-items:center;justify-content:center;padding:12px;backdrop-filter:blur(3px)}
.ovl.on{display:flex}
.modal{background:var(--s1);border:1px solid var(--b2);border-radius:14px;width:100%;
       max-width:620px;max-height:92vh;overflow-y:auto;box-shadow:var(--sh)}
.modal-w{max-width:860px}
.mh{padding:13px 17px;border-bottom:1px solid var(--b1);display:flex;
    align-items:center;justify-content:space-between}
.mh h3{font-family:'Syne',sans-serif;font-size:15px;font-weight:700}
.mb{padding:17px}
.mf{padding:10px 17px;border-top:1px solid var(--b1);display:flex;
    justify-content:flex-end;gap:7px}
.xb{background:none;border:none;color:var(--t3);cursor:pointer;font-size:16px;padding:2px 5px}
.xb:hover{color:var(--t1)}

/* Forms */
.fg{display:flex;flex-direction:column;gap:4px;margin-bottom:10px}
.fg label{font-size:10px;color:var(--t3);letter-spacing:.4px;text-transform:uppercase}
input[type=text],input[type=number],input[type=email],input[type=date],
input[type=url],select,textarea{
  background:var(--s2);border:1px solid var(--b1);border-radius:8px;color:var(--t1);
  font-family:inherit;font-size:12px;padding:7px 10px;outline:none;transition:.15s;width:100%}
input:focus,select:focus,textarea:focus{
  border-color:var(--acc);box-shadow:0 0 0 2px rgba(0,200,255,.1)}
textarea{resize:vertical;min-height:58px}
select option{background:var(--s2)}
.fgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.full{grid-column:1/-1}

/* Color picker */
.color-opts{display:flex;gap:7px;flex-wrap:wrap;margin-top:5px}
.co{width:22px;height:22px;border-radius:50%;cursor:pointer;
    border:2px solid transparent;transition:.15s}
.co.on{border-color:#fff;transform:scale(1.2)}
.co:hover{transform:scale(1.1)}

/* Record tabs */
.rtab-bar{display:flex;border-bottom:1px solid var(--b1);background:var(--s2);padding:0 17px}
.rtab{padding:9px 15px;font-size:11px;font-weight:600;cursor:pointer;color:var(--t3);
      border-bottom:2px solid transparent;transition:.15s;user-select:none}
.rtab:hover{color:var(--t2)}
.rtab.on{color:var(--acc);border-bottom-color:var(--acc)}

/* Attachment modal */
.att-dz{border:2px dashed var(--b2);border-radius:var(--r);padding:20px;text-align:center;
        cursor:pointer;transition:.2s;position:relative;margin-bottom:11px}
.att-dz:hover{border-color:var(--acc);background:var(--acc3)}
.att-dz input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
.att-list{display:flex;flex-direction:column;gap:6px;max-height:290px;overflow-y:auto}
.att-item{display:flex;align-items:center;gap:8px;background:var(--s2);
          border:1px solid var(--b1);border-radius:8px;padding:8px 10px}
.att-thumb{width:34px;height:34px;border-radius:5px;object-fit:cover;flex-shrink:0}
.att-ico{font-size:20px;width:34px;text-align:center;flex-shrink:0}
.att-inf{flex:1;min-width:0}
.att-nm{font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.att-mt{font-size:9px;color:var(--t3);margin-top:2px}
.att-ac{display:flex;gap:4px;flex-shrink:0}
.upl-ov{position:absolute;inset:0;background:rgba(8,12,20,.88);display:flex;
        align-items:center;justify-content:center;border-radius:inherit;
        z-index:20;gap:7px;font-size:12px;color:var(--acc)}

/* Import */
.imp-box{background:var(--s2);border:1px solid var(--b1);border-radius:var(--r);
         padding:18px;max-width:500px}
.step{display:flex;gap:9px;margin-bottom:11px}
.sn{width:20px;height:20px;border-radius:50%;background:var(--acc);color:#000;
    font-size:9px;font-weight:800;display:flex;align-items:center;justify-content:center;
    flex-shrink:0;margin-top:2px}
.st h4{font-size:12px;font-weight:600;margin-bottom:1px}
.st p{font-size:11px;color:var(--t3)}
.dz{border:2px dashed var(--b2);border-radius:var(--r);padding:26px;text-align:center;
    cursor:pointer;transition:.2s;position:relative;margin-top:12px}
.dz:hover,.dz.drag{border-color:var(--acc);background:var(--acc3)}
.dz input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}

/* Col list */
.col-list{display:flex;flex-direction:column;gap:6px}
.col-row{display:flex;align-items:center;justify-content:space-between;
         background:var(--s2);border:1px solid var(--b1);border-radius:8px;padding:8px 11px}
.ct-badge{font-size:9px;padding:2px 6px;border-radius:4px;
          background:rgba(0,200,255,.1);color:var(--acc)}

/* Toast */
.tc{position:fixed;bottom:15px;right:15px;z-index:999;display:flex;
    flex-direction:column;gap:4px;pointer-events:none}
.toast{padding:8px 13px;border-radius:8px;font-size:11px;min-width:185px;box-shadow:var(--sh);
       display:flex;align-items:center;gap:5px;animation:tin .2s ease;pointer-events:all}
.t-ok{background:#0a2018;border:1px solid var(--ok);color:var(--ok)}
.t-err{background:#200a10;border:1px solid var(--err);color:var(--err)}
.t-info{background:#0a1828;border:1px solid var(--acc);color:var(--acc)}
@keyframes tin{from{transform:translateX(110%);opacity:0}to{transform:translateX(0);opacity:1}}

.empty{text-align:center;padding:42px 20px;color:var(--t3)}
.empty h3{font-family:'Syne',sans-serif;font-size:14px;color:var(--t2);margin-bottom:4px}
.spin{display:inline-block;width:11px;height:11px;border:2px solid var(--b2);
      border-top-color:var(--acc);border-radius:50%;animation:rot .5s linear infinite}
@keyframes rot{to{transform:rotate(360deg)}}
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:var(--s1)}
::-webkit-scrollbar-thumb{background:var(--b2);border-radius:2px}
@media(max-width:680px){.side{display:none}.fgrid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="app">

<!-- ══════ SIDEBAR ══════ -->
<aside class="side">
  <div class="logo">
    <h1>◈ CRM</h1>
    <p>MULTI-FILE TRACKER</p>
  </div>

  <div class="files-hd">
    <span>📁 Files</span>
    <button class="new-file-btn" onclick="openCreateFile()">＋ New File</button>
  </div>
  <div class="file-list" id="fileList"></div>

  <div class="nav-btns">
    <div class="ni" id="nav-columns" onclick="gotoSection('columns')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="12" y1="5" x2="12" y2="19"/>
        <line x1="5" y1="12" x2="19" y2="12"/>
      </svg>Manage Columns
    </div>
    <div class="ni" id="nav-import" onclick="gotoSection('import')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
        <polyline points="7 10 12 15 17 10"/>
        <line x1="12" y1="15" x2="12" y2="3"/>
      </svg>Import Excel
    </div>
    <div class="ni" onclick="doExport()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
        <polyline points="17 8 12 3 7 8"/>
        <line x1="12" y1="3" x2="12" y2="15"/>
      </svg>Export Excel
    </div>
  </div>
  <div class="side-foot">SQLite · Flask · Python</div>
</aside>

<!-- ══════ MAIN ══════ -->
<div class="content">

  <!-- No file selected -->
  <div class="view on" id="view-nofile">
    <div class="no-file">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="1.2" style="color:var(--t3)">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
      </svg>
      <h2>Koi file select nahi</h2>
      <p>Sidebar se file choose karo ya naya file banao</p>
      <button class="btn btn-acc" onclick="openCreateFile()">＋ New File Banao</button>
    </div>
  </div>

  <!-- Records view -->
  <div class="view" id="view-records">
    <div class="topbar">
      <h2>📄 <span id="fileTitleSpan">—</span></h2>
      <div class="topbar-r">
        <button class="btn btn-g btn-sm" onclick="gotoSection('import')">📥 Import</button>
        <button class="btn btn-acc" onclick="openAddRec()">＋ Add Record</button>
      </div>
    </div>
    <div class="stats">
      <div class="sc"><div class="sc-l">Records</div><div class="sc-v" id="sRec">—</div></div>
      <div class="sc"><div class="sc-l">Columns</div><div class="sc-v" id="sCols">—</div></div>
      <div class="sc"><div class="sc-l">Attachments</div><div class="sc-v" id="sAtts">—</div></div>
      <div class="sc"><div class="sc-l">Today</div><div class="sc-v" id="sToday">—</div></div>
    </div>
    <div class="toolbar">
      <div class="srch">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"/>
          <line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input type="text" id="srchInput" placeholder="Search all fields…" oninput="onSearch()"/>
      </div>
      <button class="btn btn-g btn-sm" onclick="loadRecs()">↺</button>
      <span class="rec-info" id="recInfo"></span>
    </div>
    <div class="table-area">
      <table>
        <thead id="tHead"></thead>
        <tbody id="tBody"></tbody>
      </table>
    </div>
  </div>

  <!-- Columns view -->
  <div class="view" id="view-columns">
    <div class="topbar">
      <h2>Manage <span>Columns</span></h2>
      <button class="btn btn-acc" onclick="openAddCol()">＋ Add Column</button>
    </div>
    <div style="padding:15px;overflow-y:auto;flex:1">
      <div class="col-list" id="colList"></div>
    </div>
  </div>

  <!-- Import view -->
  <div class="view" id="view-import">
    <div class="topbar"><h2>Import <span>Excel</span></h2></div>
    <div style="padding:16px;overflow-y:auto;flex:1">
      <div class="imp-box">
        <div class="step">
          <div class="sn">1</div>
          <div class="st">
            <h4>Active File</h4>
            <p id="impFileLbl" style="color:var(--acc);font-weight:600">—</p>
          </div>
        </div>
        <div class="step">
          <div class="sn">2</div>
          <div class="st">
            <h4>Excel upload karo</h4>
            <p>Row 1 = Column headings · Row 2+ = data<br/>
               Unnamed / empty columns automatically skip ho jaate hain</p>
          </div>
        </div>
        <div class="step">
          <div class="sn">3</div>
          <div class="st">
            <h4>Done!</h4>
            <p>Sirf is file ke records mein import hoga.</p>
          </div>
        </div>
        <div class="dz" id="dz">
          <input type="file" accept=".xlsx,.xls" id="xlsInp" onchange="doImport(this)"/>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="1.5" style="color:var(--acc)">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
          </svg>
          <p style="margin-top:7px;font-size:12px">
            <strong style="color:var(--acc)">Click or drag & drop</strong>
          </p>
          <p style="font-size:10px;color:var(--t3);margin-top:3px">.xlsx / .xls · max 100 MB</p>
        </div>
        <div id="impRes" style="margin-top:10px"></div>
      </div>
    </div>
  </div>

</div>
</div>

<!-- ════════ MODALS ════════ -->

<!-- Create File -->
<div class="ovl" id="mFile">
  <div class="modal" style="max-width:370px">
    <div class="mh">
      <h3>📁 New File Banao</h3>
      <button class="xb" onclick="closeM('mFile')">✕</button>
    </div>
    <div class="mb">
      <div class="fg">
        <label>File Name *</label>
        <input type="text" id="fileNm" placeholder="e.g. Sales Orders, Client Data…"/>
      </div>
      <div class="fg">
        <label>Color Choose Karo</label>
        <div class="color-opts" id="colorOpts"></div>
      </div>
    </div>
    <div class="mf">
      <button class="btn btn-g" onclick="closeM('mFile')">Cancel</button>
      <button class="btn btn-acc" onclick="saveFile()">✅ Create File</button>
    </div>
  </div>
</div>

<!-- Add/Edit Record -->
<div class="ovl" id="mRec">
  <div class="modal modal-w">
    <div class="mh">
      <h3 id="mRecT">Add Record</h3>
      <button class="xb" onclick="closeM('mRec')">✕</button>
    </div>
    <!-- Tabs -->
    <div class="rtab-bar" id="recTabs">
      <div class="rtab on" id="tab-full" onclick="switchTab('full')">📋 Full Row</div>
      <div class="rtab" id="tab-single" onclick="switchTab('single')">⚡ Single Column</div>
    </div>
    <!-- Full Row Panel -->
    <div id="panelFull" class="mb">
      <div class="fgrid" id="recFlds"></div>
      <div class="full" style="margin-top:4px">
        <div class="fg">
          <label>Tags</label>
          <input type="text" id="recTags" placeholder="vip, follow-up"/>
        </div>
        <div class="fg">
          <label>Notes</label>
          <textarea id="recNotes" rows="2" placeholder="Notes…"></textarea>
        </div>
      </div>
    </div>
    <!-- Single Column Panel -->
    <div id="panelSingle" class="mb" style="display:none">
      <p style="font-size:11px;color:var(--t3);margin-bottom:11px">
        Ek column choose karo, sirf uski value daalo — naya record ban jaayega.
      </p>
      <div class="fg">
        <label>Column *</label>
        <select id="singleColSel" onchange="onSingleColChange()">
          <option value="">— Column choose karo —</option>
        </select>
      </div>
      <div class="fg" id="singleValFg" style="display:none">
        <label id="singleValLbl">Value</label>
        <input type="text" id="singleVal" placeholder="Value daalo…"/>
      </div>
    </div>
    <div class="mf">
      <button class="btn btn-g" onclick="closeM('mRec')">Cancel</button>
      <button class="btn btn-acc" onclick="saveRec()">💾 Save</button>
    </div>
  </div>
</div>

<!-- Attachment Modal -->
<div class="ovl" id="mAtt">
  <div class="modal">
    <div class="mh">
      <h3>📎 Attachments
        <span style="color:var(--acc);font-size:12px" id="mAttLbl"></span>
      </h3>
      <button class="xb" onclick="closeM('mAtt')">✕</button>
    </div>
    <div class="mb" style="position:relative" id="mAttBody">
      <div class="att-dz">
        <input type="file" multiple id="attInp" onchange="doUpload()"/>
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="1.5" style="color:var(--acc)">
          <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19
                   a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>
        </svg>
        <p style="font-size:12px;margin-top:6px">
          <strong style="color:var(--acc)">Click or drop files</strong>
        </p>
        <p style="font-size:10px;color:var(--t3);margin-top:3px">
          Images · PDF · Video · Any file
        </p>
      </div>
      <div class="att-list" id="attList"></div>
    </div>
    <div class="mf">
      <button class="btn btn-g" onclick="closeM('mAtt')">Close</button>
    </div>
  </div>
</div>

<!-- Add Column -->
<div class="ovl" id="mCol">
  <div class="modal" style="max-width:380px">
    <div class="mh">
      <h3 id="mColTitle">Add Column</h3>
      <button class="xb" onclick="closeM('mCol')">✕</button>
    </div>
    <div class="mb">
      <div class="fg">
        <label>Column Name *</label>
        <input type="text" id="colNm" placeholder="e.g. Company, Status"/>
      </div>
      <div class="fg">
        <label>Type</label>
        <select id="colTp">
          <option value="text">Text</option>
          <option value="number">Number</option>
          <option value="email">Email</option>
          <option value="phone">Phone</option>
          <option value="date">Date</option>
          <option value="url">URL</option>
        </select>
      </div>
      <div class="fg">
        <label>Position — Kahan Add Karo</label>
        <select id="colPos">
          <option value="">⬇ Sabse Last (End mein)</option>
        </select>
      </div>
      <div id="colPosHint" style="font-size:10px;color:var(--t3);margin-top:-6px;margin-bottom:8px">
        Naya column selected column ke BAAD insert hoga
      </div>
    </div>
    <div class="mf">
      <button class="btn btn-g" onclick="closeM('mCol')">Cancel</button>
      <button class="btn btn-acc" onclick="saveCol()">＋ Add Column</button>
    </div>
  </div>
</div>

<div class="tc" id="tc"></div>

<script>
// ════ STATE ════
const COLORS = ['#00c8ff','#00e07a','#ff9500','#ff3d5a','#a855f7','#f59e0b','#06b6d4','#84cc16'];
let projects=[], curPid=null, cols=[], curRecId=null, curAttId=null, stimer=null;
let activeTab='full', selColor=COLORS[0];

// ════ BOOT ════
(async()=>{
  buildColorOpts();
  await loadProjects();
  if(projects.length) selectProject(projects[0].id);
})();

// ════ COLOR OPTS ════
function buildColorOpts(){
  document.getElementById('colorOpts').innerHTML =
    COLORS.map((c,i)=>
      `<div class="co${i===0?' on':''}" style="background:${c}"
            onclick="pickColor('${c}',this)"></div>`
    ).join('');
}
function pickColor(clr,el){
  selColor=clr;
  document.querySelectorAll('.co').forEach(e=>e.classList.remove('on'));
  el.classList.add('on');
}

// ════ PROJECTS ════
async function loadProjects(){
  const r = await fetch('/api/projects').then(r=>r.json());
  projects = r.projects;
  renderFileList();
}

function renderFileList(){
  const el=document.getElementById('fileList');
  if(!projects.length){
    el.innerHTML='<div style="padding:10px;font-size:11px;color:var(--t3)">Koi file nahi — "＋ New File" click karo</div>';
    return;
  }
  el.innerHTML=projects.map(p=>`
    <div class="fi${p.id===curPid?' on':''}" onclick="selectProject(${p.id})" id="fi-${p.id}"
         style="${p.id===curPid?'--fc:'+p.color:''}">
      <div class="fi-dot" style="background:${p.color}"></div>
      <span class="fi-name">${p.name}</span>
      <span class="fi-cnt">${p.record_count}</span>
      <button class="fi-del" onclick="delProject(event,${p.id})" title="Delete">🗑</button>
    </div>`).join('');
}

async function selectProject(pid){
  curPid=pid;
  const p=projects.find(x=>x.id===pid);
  // File-specific color
  document.documentElement.style.setProperty('--fc', p?p.color:'#00c8ff');
  document.querySelectorAll('.fi').forEach(e=>e.classList.remove('on'));
  const fi=document.getElementById('fi-'+pid);
  if(fi) fi.classList.add('on');
  // Title & import label
  document.getElementById('fileTitleSpan').textContent = p?p.name:'';
  document.getElementById('impFileLbl').textContent    = p?'→ '+p.name:'—';
  // Load
  await loadCols();
  gotoSection('records');
  loadRecs();
  loadStats();
}

function openCreateFile(){
  document.getElementById('fileNm').value='';
  selColor=COLORS[0];
  document.querySelectorAll('.co').forEach((e,i)=>e.classList.toggle('on',i===0));
  openM('mFile');
}

async function saveFile(){
  const nm=document.getElementById('fileNm').value.trim();
  if(!nm){toast('File ka naam daalo','err');return;}
  const r=await fetch('/api/projects',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:nm,color:selColor})
  }).then(r=>r.json());
  if(r.success){
    toast('"'+nm+'" file ban gayi!','ok');
    closeM('mFile');
    projects.push(r.project);
    renderFileList();
    selectProject(r.project.id);
  } else toast(r.message,'err');
}

async function delProject(e,pid){
  e.stopPropagation();
  const p=projects.find(x=>x.id===pid);
  if(!confirm(`"${p?.name}" file delete karna chahte ho?\nIs file ke saare records aur attachments bhi delete ho jaayenge!`)) return;
  await fetch('/api/projects/'+pid,{method:'DELETE'});
  toast('File deleted','ok');
  projects=projects.filter(x=>x.id!==pid);
  if(curPid===pid){ curPid=null; showView('nofile'); }
  renderFileList();
}

// ════ VIEWS ════
function showView(name){
  document.querySelectorAll('.view').forEach(e=>e.classList.remove('on'));
  document.getElementById('view-'+name).classList.add('on');
}

function gotoSection(sec){
  if(!curPid){toast('Pehle ek file choose karo','err');return;}
  showView(sec==='records'?'records':sec==='columns'?'columns':'import');
  document.querySelectorAll('.ni').forEach(e=>e.classList.remove('on'));
  const ni=document.getElementById('nav-'+sec); if(ni) ni.classList.add('on');
  if(sec==='columns') renderColList();
}

// ════ STATS ════
async function loadStats(){
  if(!curPid) return;
  const r=await fetch('/api/stats/'+curPid).then(r=>r.json());
  document.getElementById('sRec').textContent   = r.records;
  document.getElementById('sCols').textContent  = r.columns;
  document.getElementById('sAtts').textContent  = r.attachments;
  document.getElementById('sToday').textContent = r.today;
  const p=projects.find(x=>x.id===curPid);
  if(p){p.record_count=r.records; renderFileList();}
}

// ════ COLUMNS ════
async function loadCols(){
  if(!curPid) return;
  const r=await fetch('/api/projects/'+curPid+'/columns').then(r=>r.json());
  cols=r.columns;
}

function renderColList(){
  const el=document.getElementById('colList');
  if(!cols.length){
    el.innerHTML='<div class="empty"><p>Koi column nahi. "Add Column" se banao.</p></div>';return;
  }
  // Header with drag hint
  el.innerHTML=`
  <div style="font-size:10px;color:var(--t3);margin-bottom:8px;padding:0 2px">
    💡 Kisi bhi column ke baad naya column insert karne ke liye <strong style="color:var(--t2)">Insert ↓</strong> button dabao
  </div>` +
  cols.map((c,i)=>`
    <div class="col-row" id="crow-${c.id}">
      <div style="display:flex;align-items:center;gap:8px;flex:1;min-width:0">
        <span style="color:var(--t3);font-size:10px;min-width:18px">${i+1}.</span>
        <span style="font-weight:600">${c.name}</span>
        <span class="ct-badge">${c.col_type}</span>
      </div>
      <div style="display:flex;gap:5px;flex-shrink:0">
        <button class="btn btn-g btn-sm" title="Is column ke BAAD naya column insert karo"
          onclick="openInsertAfter(${c.id},'${c.name.replace(/'/g,"\\'")}')">Insert ↓</button>
        <button class="btn btn-err btn-sm" onclick="delCol(${c.id},'${c.name}')">Delete</button>
      </div>
    </div>`).join('') +
  `<div style="margin-top:8px;padding:8px;border:1px dashed var(--b2);border-radius:8px;
               text-align:center;font-size:11px;color:var(--t3);cursor:pointer"
        onclick="openAddCol()">
    ＋ Sabse end mein naya column add karo
  </div>`;
}

function openAddCol(){
  document.getElementById('mColTitle').textContent = 'Add Column';
  document.getElementById('colNm').value='';
  document.getElementById('colTp').value='text';
  populateColPosSel(null);  // null = end mein
  openM('mCol');
}

function openInsertAfter(afterId, afterName){
  document.getElementById('mColTitle').textContent = 'Insert Column After "'+afterName+'"';
  document.getElementById('colNm').value='';
  document.getElementById('colTp').value='text';
  populateColPosSel(afterId);  // pre-select this column
  openM('mCol');
}

function populateColPosSel(selectedId){
  const sel = document.getElementById('colPos');
  const hint = document.getElementById('colPosHint');
  sel.innerHTML =
    '<option value="">⬇ Sabse Last (End mein)</option>' +
    cols.map(c =>
      `<option value="${c.id}"${c.id==selectedId?' selected':''}>After: ${c.name}</option>`
    ).join('');
  // Hint update
  hint.style.display = selectedId ? '' : 'none';
}

async function saveCol(){
  if(!curPid) return;
  const nm=document.getElementById('colNm').value.trim();
  if(!nm){toast('Name daalo','err');return;}
  const posVal = document.getElementById('colPos').value;
  const payload = {
    name: nm,
    col_type: document.getElementById('colTp').value,
    insert_after: posVal ? parseInt(posVal) : null
  };
  const r=await fetch('/api/projects/'+curPid+'/columns',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload)
  }).then(r=>r.json());
  if(r.success){
    const pos = posVal
      ? 'after "'+cols.find(c=>c.id==posVal)?.name+'"'
      : 'at end';
    toast('Column "'+nm+'" added '+pos+'!','ok');
    closeM('mCol');
    await loadCols();
    loadRecs();
    loadStats();
    if(document.getElementById('view-columns').classList.contains('on')) renderColList();
  }
  else toast(r.message,'err');
}

async function delCol(id,name){
  if(!confirm(`Column "${name}" delete karna chahte ho?`)) return;
  await fetch('/api/projects/'+curPid+'/columns/'+id,{method:'DELETE'});
  toast('Column deleted','ok'); await loadCols(); loadRecs(); loadStats();
}

// ════ RECORDS ════
function onSearch(){clearTimeout(stimer); stimer=setTimeout(loadRecs,280);}

async function loadRecs(){
  if(!curPid) return;
  const q=document.getElementById('srchInput').value;
  const r=await fetch('/api/projects/'+curPid+'/records?q='+encodeURIComponent(q)).then(r=>r.json());
  renderTable(r.records);
  document.getElementById('recInfo').textContent=r.total+' records';
}

function renderTable(recs){
  const head=document.getElementById('tHead');
  const body=document.getElementById('tBody');
  const hcols=cols.map(c=>`
    <th><div class="th-w">${c.name}
      <span class="dc" onclick="delCol(${c.id},'${c.name}')">✕</span>
    </div></th>`).join('');
  head.innerHTML=`<tr>
    <th style="color:var(--t3);width:30px">#</th>${hcols}
    <th>📎 Files</th><th>Added</th>
    <th style="text-align:right">Actions</th></tr>`;
  if(!recs.length){
    body.innerHTML=`<tr><td colspan="${cols.length+4}">
      <div class="empty"><h3>Koi record nahi</h3>
      <p>Add Record ya Import Excel se data daalo</p></div></td></tr>`;
    return;
  }
  body.innerHTML=recs.map((rec,i)=>{
    const cells=cols.map(c=>{
      const v=rec.data[c.id]||'';
      return `<td title="${v.replace(/"/g,'&quot;')}">${v||'<span style="color:var(--t3)">—</span>'}</td>`;
    }).join('');
    const ac=rec.attachments.length;
    const abtn=ac
      ?`<span class="att-btn has" onclick="openAtt(${rec.id})">📎 ${ac} file${ac>1?'s':''}</span>`
      :`<span class="att-btn" onclick="openAtt(${rec.id})">📎 Add</span>`;
    return `<tr>
      <td class="td-n">${i+1}</td>${cells}<td>${abtn}</td>
      <td style="color:var(--t3);font-size:10px;white-space:nowrap">${rec.created_at}</td>
      <td class="td-act" style="text-align:right">
        <button class="btn btn-g btn-ico btn-sm" onclick="openEditRec(${rec.id})">✏️</button>
        <button class="btn btn-err btn-ico btn-sm" onclick="delRec(${rec.id})">🗑</button>
      </td></tr>`;
  }).join('');
}

// ════ ADD/EDIT RECORD ════
function switchTab(tab){
  activeTab=tab;
  document.getElementById('tab-full').classList.toggle('on',tab==='full');
  document.getElementById('tab-single').classList.toggle('on',tab==='single');
  document.getElementById('panelFull').style.display  =tab==='full'?'':'none';
  document.getElementById('panelSingle').style.display=tab==='single'?'':'none';
}

function populateSingleColSel(){
  document.getElementById('singleColSel').innerHTML=
    '<option value="">— Column choose karo —</option>'+
    cols.map(c=>`<option value="${c.id}" data-type="${c.col_type}">${c.name}</option>`).join('');
  document.getElementById('singleValFg').style.display='none';
}

function onSingleColChange(){
  const sel=document.getElementById('singleColSel');
  const opt=sel.options[sel.selectedIndex];
  const fg=document.getElementById('singleValFg');
  if(!sel.value){fg.style.display='none';return;}
  document.getElementById('singleValLbl').textContent=opt.text;
  const inp=document.getElementById('singleVal');
  const ct=opt.dataset.type||'text';
  inp.type=ct==='number'?'number':ct==='date'?'date':ct==='email'?'email':ct==='url'?'url':'text';
  inp.placeholder=opt.text+' daalo…';
  inp.value='';
  fg.style.display='';
}

function openAddRec(){
  curRecId=null;
  document.getElementById('mRecT').textContent='Add Record';
  document.getElementById('recTabs').style.display='flex';
  switchTab('full');
  document.getElementById('recTags').value='';
  document.getElementById('recNotes').value='';
  buildFlds({});
  populateSingleColSel();
  openM('mRec');
}

async function openEditRec(id){
  const r=await fetch('/api/records/'+id).then(r=>r.json());
  curRecId=id;
  document.getElementById('mRecT').textContent='Edit Record #'+id;
  document.getElementById('recTabs').style.display='none';
  switchTab('full');
  document.getElementById('recTags').value=r.record.tags||'';
  document.getElementById('recNotes').value=r.record.notes||'';
  buildFlds(r.record.data);
  openM('mRec');
}

function buildFlds(data){
  const c=document.getElementById('recFlds');
  c.className='fgrid';
  c.innerHTML=cols.map(col=>`
    <div class="fg"><label>${col.name}</label>
      <input type="${col.col_type==='email'?'email':col.col_type==='date'?'date':
                    col.col_type==='number'?'number':col.col_type==='url'?'url':'text'}"
        id="f_${col.id}" value="${(data[col.id]||'').replace(/"/g,'&quot;')}"
        placeholder="${col.name}"/>
    </div>`).join('')||'<p style="color:var(--t3)">Pehle columns banao.</p>';
}

async function saveRec(){
  if(!curPid) return;
  if(!curRecId && activeTab==='single'){
    const colId=document.getElementById('singleColSel').value;
    const val=document.getElementById('singleVal').value.trim();
    if(!colId){toast('Column choose karo','err');return;}
    if(!val){toast('Value daalo','err');return;}
    const r=await fetch('/api/projects/'+curPid+'/records',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({data:{[colId]:val},tags:'',notes:''})
    }).then(r=>r.json());
    if(r.success){toast('Record added!','ok');closeM('mRec');loadRecs();loadStats();}
    else toast(r.message||'Error','err');
    return;
  }
  const fd={};
  cols.forEach(c=>{const e=document.getElementById('f_'+c.id);if(e&&e.value.trim())fd[c.id]=e.value.trim();});
  const payload={data:fd,tags:document.getElementById('recTags').value,
                 notes:document.getElementById('recNotes').value};
  const m=curRecId?'PUT':'POST';
  const u=curRecId?'/api/records/'+curRecId:'/api/projects/'+curPid+'/records';
  const r=await fetch(u,{method:m,headers:{'Content-Type':'application/json'},
    body:JSON.stringify(payload)}).then(r=>r.json());
  if(r.success){toast(curRecId?'Updated!':'Record added!','ok');closeM('mRec');loadRecs();loadStats();}
  else toast(r.message||'Error','err');
}

async function delRec(id){
  if(!confirm('Record aur uski files delete karna chahte ho?')) return;
  await fetch('/api/records/'+id,{method:'DELETE'});
  toast('Deleted','ok'); loadRecs(); loadStats();
}

// ════ ATTACHMENTS ════
async function openAtt(recId){
  curAttId=recId;
  document.getElementById('mAttLbl').textContent='— Record #'+recId;
  await refreshAtts();
  openM('mAtt');
}

async function refreshAtts(){
  const r=await fetch('/api/records/'+curAttId).then(r=>r.json());
  const atts=r.record.attachments;
  const el=document.getElementById('attList');
  if(!atts.length){
    el.innerHTML='<p style="color:var(--t3);font-size:11px;text-align:center;padding:8px">Koi file nahi. Upar se upload karo.</p>';
  } else {
    el.innerHTML=atts.map(a=>{
      const icon=a.file_type==='image'?'🖼️':a.file_type==='video'?'🎬':a.file_type==='pdf'?'📄':'📁';
      const prev=a.file_type==='image'
        ?`<img class="att-thumb" src="${a.url}" onerror="this.outerHTML='<div class=att-ico>🖼️</div>'">`
        :`<div class="att-ico">${icon}</div>`;
      return `<div class="att-item">${prev}
        <div class="att-inf">
          <div class="att-nm" title="${a.original_name}">${a.original_name}</div>
          <div class="att-mt">${a.file_size_str} · ${a.file_type}</div>
        </div>
        <div class="att-ac">
          <a href="${a.url}" download="${a.original_name}" class="btn btn-g btn-sm">⬇</a>
          ${a.file_type==='image'||a.file_type==='pdf'||a.file_type==='video'
            ?`<a href="${a.url}" target="_blank" class="btn btn-g btn-sm">👁</a>`:''}
          <button class="btn btn-err btn-sm" onclick="delAtt(${a.id})">✕</button>
        </div></div>`;
    }).join('');
  }
  const oldBtn=document.querySelector(`[onclick="openAtt(${curAttId})"]`);
  if(oldBtn){
    oldBtn.className=atts.length?'att-btn has':'att-btn';
    oldBtn.innerHTML=atts.length?`📎 ${atts.length} file${atts.length>1?'s':''}`:'📎 Add';
  }
  loadStats();
}

async function doUpload(){
  const files=document.getElementById('attInp').files;
  if(!files.length) return;
  const body=document.getElementById('mAttBody');
  const ov=document.createElement('div');
  ov.className='upl-ov';
  ov.innerHTML=`<span class="spin"></span>&nbsp;Uploading…`;
  body.appendChild(ov);
  for(const f of files){
    const fd=new FormData(); fd.append('file',f);
    const r=await fetch('/api/records/'+curAttId+'/attachments',{method:'POST',body:fd}).then(r=>r.json());
    if(!r.success) toast('Error: '+r.message,'err');
  }
  ov.remove();
  document.getElementById('attInp').value='';
  toast(files.length+' file(s) uploaded!','ok');
  await refreshAtts();
}

async function delAtt(id){
  if(!confirm('Attachment delete karna chahte ho?')) return;
  await fetch('/api/attachments/'+id,{method:'DELETE'});
  toast('Deleted','ok'); await refreshAtts();
}

// ════ EXCEL ════
async function doImport(inp){
  if(!curPid){toast('Pehle file choose karo','err');return;}
  const f=inp.files[0]; if(!f) return;
  const rd=document.getElementById('impRes');
  rd.innerHTML='<div class="toast t-info"><span class="spin"></span> Importing…</div>';
  const fd=new FormData(); fd.append('file',f);
  const r=await fetch('/api/projects/'+curPid+'/import',{method:'POST',body:fd}).then(r=>r.json());
  rd.innerHTML=r.success
    ?`<div class="toast t-ok">✅ ${r.message} (${r.cols} columns)</div>`
    :`<div class="toast t-err">❌ ${r.message}</div>`;
  inp.value='';
  if(r.success){await loadCols(); loadRecs(); loadStats();}
}

function doExport(){
  if(!curPid){toast('Pehle file choose karo','err');return;}
  window.open('/api/projects/'+curPid+'/export','_blank');
  toast('Downloading…','info');
}

// ════ HELPERS ════
function openM(id){ document.getElementById(id).classList.add('on'); }
function closeM(id){ document.getElementById(id).classList.remove('on'); }
document.querySelectorAll('.ovl').forEach(el=>
  el.addEventListener('click',e=>{if(e.target===el)el.classList.remove('on');}));

const dz=document.getElementById('dz');
dz.addEventListener('dragover',e=>{e.preventDefault();dz.classList.add('drag');});
dz.addEventListener('dragleave',()=>dz.classList.remove('drag'));
dz.addEventListener('drop',e=>{
  e.preventDefault();dz.classList.remove('drag');
  const f=e.dataTransfer.files[0];
  if(f){const dt=new DataTransfer();dt.items.add(f);
    document.getElementById('xlsInp').files=dt.files;
    doImport(document.getElementById('xlsInp'));}
});

function toast(msg,type='info'){
  const tc=document.getElementById('tc');
  const t=document.createElement('div');
  t.className='toast t-'+type; t.textContent=msg;
  tc.appendChild(t); setTimeout(()=>t.remove(),3200);
}
</script>
</body>
</html>"""


if __name__ == '__main__':
    print("="*55)
    print("🚀 CRM Dashboard — Multi-File Version")
    print("📍 http://127.0.0.1:5000")
    print("✅ Multiple Files/Projects — har file alag")
    print("✅ Unnamed columns skip in Excel import")
    print("✅ Add Record: Full Row + Single Column")
    print("✅ All original features intact")
    print("="*55)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port,)
