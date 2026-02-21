"""
CRM Dashboard - Fixed Version
✅ All rows visible (flex scroll - no height cutoff)
✅ 📎 Attachment button DIRECTLY in each table row
✅ Attachment modal: upload/preview/delete/download
✅ Excel import row-by-row, column-by-column
✅ Full CRUD + Search + Export

pip install flask flask-sqlalchemy openpyxl pandas werkzeug
python app.py → http://127.0.0.1:5000
"""

import os, json, uuid
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, send_from_directory, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import pandas as pd

app = Flask(__name__)
app.config['SECRET_KEY']                     = 'crm-2025-secret'
app.config['SQLALCHEMY_DATABASE_URI']        = 'sqlite:///crm.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER']                  = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH']             = 100 * 1024 * 1024

ALLOWED = {'png','jpg','jpeg','gif','webp','pdf','mp4','mov','avi','mkv','xlsx','xls','docx','txt','csv'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
db = SQLAlchemy(app)


# ─────────────── MODELS ───────────────
class CRMColumn(db.Model):
    __tablename__ = 'crm_columns'
    id        = db.Column(db.Integer, primary_key=True)
    name      = db.Column(db.String(100), nullable=False)
    col_type  = db.Column(db.String(30), default='text')
    col_order = db.Column(db.Integer, default=0)
    def to_dict(self):
        return {'id':self.id,'name':self.name,'col_type':self.col_type,'col_order':self.col_order}


class CRMRecord(db.Model):
    __tablename__ = 'crm_records'
    id          = db.Column(db.Integer, primary_key=True)
    data        = db.Column(db.Text, default='{}')
    tags        = db.Column(db.String(500), default='')
    notes       = db.Column(db.Text, default='')
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    attachments = db.relationship('Attachment', backref='record', lazy=True, cascade='all,delete-orphan')

    def get_data(self):
        try: return json.loads(self.data)
        except: return {}

    def to_dict(self):
        return {
            'id':          self.id,
            'data':        self.get_data(),
            'tags':        self.tags or '',
            'notes':       self.notes or '',
            'created_at':  self.created_at.strftime('%d %b %Y') if self.created_at else '',
            'attachments': [a.to_dict() for a in self.attachments]
        }


class Attachment(db.Model):
    __tablename__ = 'attachments'
    id            = db.Column(db.Integer, primary_key=True)
    record_id     = db.Column(db.Integer, db.ForeignKey('crm_records.id'), nullable=False)
    filename      = db.Column(db.String(300), nullable=False)
    original_name = db.Column(db.String(300), nullable=False)
    file_type     = db.Column(db.String(20), default='file')
    file_size     = db.Column(db.Integer, default=0)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':            self.id,
            'filename':      self.filename,
            'original_name': self.original_name,
            'file_type':     self.file_type,
            'file_size_str': _human_size(self.file_size),
            'url':           url_for('serve_upload', filename=self.filename),
        }


def _human_size(n):
    for u in ['B','KB','MB','GB']:
        if n < 1024: return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"

def _file_type(fn):
    e = fn.rsplit('.',1)[-1].lower() if '.' in fn else ''
    if e in {'png','jpg','jpeg','gif','webp'}: return 'image'
    if e == 'pdf':                             return 'pdf'
    if e in {'mp4','mov','avi','mkv','webm'}: return 'video'
    return 'file'

def allowed(fn):
    return '.' in fn and fn.rsplit('.',1)[1].lower() in ALLOWED


# ─────────────── DB INIT ───────────────
with app.app_context():
    db.create_all()
    if CRMColumn.query.count() == 0:
        defaults = [
            ('Client Name','text'),('Location','text'),('PO Number','text'),
            ('Item Code','text'),('Size','text'),('Type','text'),
            ('Material','text'),('Diameter','text'),('Quantity','number'),
            ('Date','text'),('Remarks','text')
        ]
        for i,(name,ctype) in enumerate(defaults):
            db.session.add(CRMColumn(name=name, col_type=ctype, col_order=i))
        db.session.commit()


# ─────────────── API ROUTES ───────────────
@app.route('/')
def index(): return render_template_string(HTML)

@app.route('/uploads/<filename>')
def serve_upload(filename): return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/columns')
def get_columns():
    return jsonify({'success':True, 'columns':[c.to_dict() for c in CRMColumn.query.order_by(CRMColumn.col_order).all()]})

@app.route('/api/columns', methods=['POST'])
def add_column():
    d = request.get_json() or {}
    name = d.get('name','').strip()
    if not name: return jsonify({'success':False,'message':'Name required'}), 400
    mo = db.session.query(db.func.max(CRMColumn.col_order)).scalar() or 0
    c = CRMColumn(name=name, col_type=d.get('col_type','text'), col_order=mo+1)
    db.session.add(c); db.session.commit()
    return jsonify({'success':True,'column':c.to_dict()})

@app.route('/api/columns/<int:cid>', methods=['DELETE'])
def del_column(cid):
    col = CRMColumn.query.get_or_404(cid)
    for r in CRMRecord.query.all():
        d = r.get_data(); d.pop(str(cid),None); r.data = json.dumps(d)
    db.session.delete(col); db.session.commit()
    return jsonify({'success':True})

@app.route('/api/records')
def get_records():
    q   = request.args.get('q','').strip().lower()
    recs = CRMRecord.query.order_by(CRMRecord.created_at.desc()).all()
    result = []
    for r in recs:
        d = r.to_dict()
        if q:
            txt = ' '.join(str(v) for v in d['data'].values()).lower()
            txt += ' '+(d['notes'] or '').lower()+' '+(d['tags'] or '').lower()
            if q not in txt: continue
        result.append(d)
    return jsonify({'success':True,'records':result,'total':len(result)})

@app.route('/api/records', methods=['POST'])
def add_record():
    d = request.get_json() or {}
    r = CRMRecord(data=json.dumps(d.get('data',{})), tags=d.get('tags',''), notes=d.get('notes',''))
    db.session.add(r); db.session.commit()
    return jsonify({'success':True,'record':r.to_dict()})

@app.route('/api/records/<int:rid>')
def get_record(rid):
    return jsonify({'success':True,'record':CRMRecord.query.get_or_404(rid).to_dict()})

@app.route('/api/records/<int:rid>', methods=['PUT'])
def upd_record(rid):
    r = CRMRecord.query.get_or_404(rid)
    d = request.get_json() or {}
    r.data = json.dumps(d.get('data', r.get_data()))
    r.tags = d.get('tags', r.tags)
    r.notes = d.get('notes', r.notes)
    r.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success':True,'record':r.to_dict()})

@app.route('/api/records/<int:rid>', methods=['DELETE'])
def del_record(rid):
    r = CRMRecord.query.get_or_404(rid)
    for a in r.attachments:
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], a.filename))
        except: pass
    db.session.delete(r); db.session.commit()
    return jsonify({'success':True})

@app.route('/api/records/<int:rid>/attachments', methods=['POST'])
def upload_att(rid):
    r = CRMRecord.query.get_or_404(rid)
    if 'file' not in request.files: return jsonify({'success':False,'message':'No file'}), 400
    file = request.files['file']
    if not file.filename or not allowed(file.filename):
        return jsonify({'success':False,'message':'File type not allowed'}), 400
    orig   = secure_filename(file.filename)
    ext    = orig.rsplit('.',1)[-1] if '.' in orig else 'bin'
    stored = f"{uuid.uuid4().hex}.{ext}"
    fp     = os.path.join(app.config['UPLOAD_FOLDER'], stored)
    file.save(fp)
    a = Attachment(record_id=r.id, filename=stored, original_name=orig,
                   file_type=_file_type(orig), file_size=os.path.getsize(fp))
    db.session.add(a); db.session.commit()
    return jsonify({'success':True,'attachment':a.to_dict()})

@app.route('/api/attachments/<int:aid>', methods=['DELETE'])
def del_att(aid):
    a = Attachment.query.get_or_404(aid)
    try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], a.filename))
    except: pass
    db.session.delete(a); db.session.commit()
    return jsonify({'success':True})

@app.route('/api/import', methods=['POST'])
def import_excel():
    if 'file' not in request.files: return jsonify({'success':False,'message':'No file'}), 400
    f = request.files['file']
    if not f.filename.endswith(('.xlsx','.xls')):
        return jsonify({'success':False,'message':'Only .xlsx / .xls'}), 400
    try:
        df = pd.read_excel(f, dtype=str).fillna('')
        headers = list(df.columns)
        existing = {c.name.strip().lower():c for c in CRMColumn.query.all()}
        col_map  = {}
        mo = db.session.query(db.func.max(CRMColumn.col_order)).scalar() or 0
        for i,h in enumerate(headers):
            k = h.strip().lower()
            if k in existing:
                col_map[h] = existing[k].id
            else:
                nc = CRMColumn(name=h.strip(), col_type='text', col_order=mo+i+1)
                db.session.add(nc); db.session.flush()
                col_map[h] = nc.id
        db.session.commit()
        inserted = 0
        for _,row in df.iterrows():
            rd = {str(col_map[h]): str(row[h]).strip()
                  for h in headers if str(row[h]).strip() and str(row[h]).strip()!='nan'}
            if any(rd.values()):
                db.session.add(CRMRecord(data=json.dumps(rd)))
                inserted += 1
        db.session.commit()
        return jsonify({'success':True,'message':f'{inserted} rows imported','rows':inserted,'cols':len(headers)})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success':False,'message':str(e)}), 500

@app.route('/api/export')
def export_excel():
    import io
    cols = CRMColumn.query.order_by(CRMColumn.col_order).all()
    recs = CRMRecord.query.order_by(CRMRecord.created_at.desc()).all()
    rows = []
    for r in recs:
        d = r.get_data()
        row = {c.name: d.get(str(c.id),'') for c in cols}
        row['Notes'] = r.notes; row['Tags'] = r.tags
        row['Created'] = r.created_at.strftime('%d %b %Y') if r.created_at else ''
        rows.append(row)
    out = io.BytesIO()
    pd.DataFrame(rows).to_excel(out, index=False, engine='openpyxl')
    out.seek(0)
    from flask import send_file
    return send_file(out, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name='crm_export.xlsx')

@app.route('/api/stats')
def stats():
    today = datetime.utcnow().date()
    return jsonify({
        'records':     CRMRecord.query.count(),
        'columns':     CRMColumn.query.count(),
        'attachments': Attachment.query.count(),
        'today':       CRMRecord.query.filter(db.func.date(CRMRecord.created_at)==today).count()
    })


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
  --b1:#1a3050;--b2:#1e3d66;--b3:#245080;
  --acc:#00c8ff;--acc2:#0090bb;--acc3:rgba(0,200,255,.1);
  --ok:#00e07a;--err:#ff3d5a;--warn:#ffaa00;
  --t1:#ddeeff;--t2:#7aaed0;--t3:#3a6080;
  --r:10px;--sh:0 12px 40px rgba(0,0,0,.6);
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;font-family:'IBM Plex Mono',monospace;background:var(--bg);color:var(--t1);font-size:13px}

/* ── LAYOUT: fixed height, flex ── */
.app{display:flex;height:100vh;overflow:hidden}
.side{width:238px;min-width:238px;background:var(--s1);border-right:1px solid var(--b1);display:flex;flex-direction:column}
.content{flex:1;display:flex;flex-direction:column;min-width:0;overflow:hidden}

/* ── SIDEBAR ── */
.logo{padding:18px 20px;border-bottom:1px solid var(--b1)}
.logo h1{font-family:'Syne',sans-serif;font-size:18px;font-weight:800;color:var(--acc);letter-spacing:3px}
.logo p{font-size:10px;color:var(--t3);letter-spacing:1px;margin-top:2px}
.nav{flex:1;padding:8px 0}
.ni{display:flex;align-items:center;gap:9px;padding:10px 18px;color:var(--t2);cursor:pointer;border-left:3px solid transparent;font-size:12px;transition:.15s;user-select:none}
.ni:hover,.ni.on{color:var(--acc);background:var(--acc3);border-left-color:var(--acc)}
.ni svg{width:15px;height:15px;flex-shrink:0}
.side-foot{padding:12px 18px;border-top:1px solid var(--b1);font-size:10px;color:var(--t3)}

/* ── VIEWS ── */
.view{display:none;flex:1;flex-direction:column;overflow:hidden;min-height:0}
.view.on{display:flex}

/* ── TOPBAR ── */
.topbar{padding:14px 20px;border-bottom:1px solid var(--b1);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;background:var(--s1);flex-shrink:0}
.topbar h2{font-family:'Syne',sans-serif;font-size:19px;font-weight:800}
.topbar h2 span{color:var(--acc)}
.topbar-r{display:flex;gap:7px;flex-wrap:wrap;align-items:center}

/* ── STATS ── */
.stats{display:flex;gap:10px;padding:12px 20px;border-bottom:1px solid var(--b1);flex-wrap:wrap;background:var(--s2);flex-shrink:0}
.sc{background:var(--s1);border:1px solid var(--b1);border-radius:var(--r);padding:10px 16px;flex:1;min-width:120px;position:relative;overflow:hidden}
.sc::after{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--acc),transparent)}
.sc-l{font-size:9px;color:var(--t3);letter-spacing:1px;text-transform:uppercase;margin-bottom:3px}
.sc-v{font-family:'Syne',sans-serif;font-size:24px;font-weight:800;color:var(--acc)}

/* ── TOOLBAR ── */
.toolbar{padding:9px 20px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;border-bottom:1px solid var(--b1);background:var(--s2);flex-shrink:0}
.srch{display:flex;align-items:center;gap:6px;background:var(--s1);border:1px solid var(--b1);border-radius:8px;padding:7px 11px;flex:1;max-width:360px}
.srch input{background:none;border:none;color:var(--t1);font-family:inherit;font-size:12px;outline:none;width:100%}
.srch input::placeholder{color:var(--t3)}
.rec-info{font-size:11px;color:var(--t3)}

/* ── TABLE AREA — CRITICAL FIX ──
   flex:1 + overflow:auto means it grows to fill remaining space
   and scrolls internally — ALL rows are visible */
.table-area{flex:1;overflow:auto;min-height:0}

table{width:100%;border-collapse:collapse;min-width:1000px}
thead{position:sticky;top:0;z-index:20}
th{background:var(--s2);padding:9px 11px;text-align:left;font-size:9px;letter-spacing:1px;text-transform:uppercase;color:var(--t3);font-weight:500;border-bottom:2px solid var(--b1);white-space:nowrap}
.th-w{display:flex;align-items:center;gap:5px}
.dc{opacity:0;cursor:pointer;color:var(--err);font-size:13px;transition:.15s}
th:hover .dc{opacity:1}
td{padding:8px 11px;border-bottom:1px solid rgba(26,48,80,.45);color:var(--t1);vertical-align:middle;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
tr:hover td{background:rgba(0,200,255,.035)}
.td-n{color:var(--t3);font-size:11px;width:36px;text-align:right}
.td-act{white-space:nowrap;width:1%}

/* ── ATTACHMENT BUTTON IN TABLE — main feature ── */
.att-btn{display:inline-flex;align-items:center;gap:4px;padding:4px 9px;border-radius:6px;font-size:10px;font-weight:600;cursor:pointer;border:1px solid var(--b2);background:var(--s3);color:var(--t2);transition:.15s;user-select:none}
.att-btn:hover{border-color:var(--acc);color:var(--acc);background:var(--acc3)}
.att-btn.has{background:rgba(0,224,122,.08);border-color:rgba(0,224,122,.4);color:var(--ok)}

/* ── BUTTONS ── */
.btn{display:inline-flex;align-items:center;gap:5px;padding:7px 13px;border-radius:8px;border:none;cursor:pointer;font-family:inherit;font-size:11px;font-weight:600;transition:.15s;white-space:nowrap}
.btn-acc{background:var(--acc);color:#000}.btn-acc:hover{background:var(--acc2);transform:translateY(-1px)}
.btn-g{background:var(--s2);color:var(--t1);border:1px solid var(--b1)}.btn-g:hover{border-color:var(--acc);color:var(--acc)}
.btn-ok{background:rgba(0,224,122,.12);color:var(--ok);border:1px solid rgba(0,224,122,.3)}
.btn-err{background:rgba(255,61,90,.1);color:var(--err);border:1px solid rgba(255,61,90,.25)}
.btn-sm{padding:5px 9px;font-size:10px}
.btn-ico{padding:5px 7px}

/* ── MODALS ── */
.ovl{position:fixed;inset:0;background:rgba(0,0,0,.78);z-index:500;display:none;align-items:center;justify-content:center;padding:12px;backdrop-filter:blur(3px)}
.ovl.on{display:flex}
.modal{background:var(--s1);border:1px solid var(--b2);border-radius:14px;width:100%;max-width:640px;max-height:92vh;overflow-y:auto;box-shadow:var(--sh)}
.modal-w{max-width:840px}
.mh{padding:16px 20px;border-bottom:1px solid var(--b1);display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.mh h3{font-family:'Syne',sans-serif;font-size:16px;font-weight:700}
.mb{padding:20px}
.mf{padding:12px 20px;border-top:1px solid var(--b1);display:flex;justify-content:flex-end;gap:8px}
.xb{background:none;border:none;color:var(--t3);cursor:pointer;font-size:17px;padding:2px 6px;transition:.15s}
.xb:hover{color:var(--t1)}

/* ── FORM ── */
.fg{display:flex;flex-direction:column;gap:4px;margin-bottom:11px}
.fg label{font-size:10px;color:var(--t3);letter-spacing:.4px;text-transform:uppercase}
input[type=text],input[type=number],input[type=email],input[type=date],input[type=url],input[type=phone],select,textarea{
  background:var(--s2);border:1px solid var(--b1);border-radius:8px;color:var(--t1);
  font-family:inherit;font-size:12px;padding:8px 10px;outline:none;transition:.15s;width:100%}
input:focus,select:focus,textarea:focus{border-color:var(--acc);box-shadow:0 0 0 2px rgba(0,200,255,.1)}
textarea{resize:vertical;min-height:68px}
select option{background:var(--s2)}
.fgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.full{grid-column:1/-1}

/* ── ATTACHMENT MODAL STYLES ── */
.att-dz{border:2px dashed var(--b2);border-radius:var(--r);padding:24px;text-align:center;cursor:pointer;transition:.2s;position:relative;margin-bottom:14px}
.att-dz:hover{border-color:var(--acc);background:var(--acc3)}
.att-dz input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
.att-list{display:flex;flex-direction:column;gap:7px;max-height:320px;overflow-y:auto;padding-right:2px}
.att-item{display:flex;align-items:center;gap:10px;background:var(--s2);border:1px solid var(--b1);border-radius:8px;padding:9px 11px}
.att-thumb{width:38px;height:38px;border-radius:6px;object-fit:cover;flex-shrink:0}
.att-ico{font-size:24px;width:38px;text-align:center;flex-shrink:0}
.att-inf{flex:1;min-width:0}
.att-nm{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.att-mt{font-size:10px;color:var(--t3);margin-top:2px}
.att-ac{display:flex;gap:5px;flex-shrink:0}
.upl-ov{position:absolute;inset:0;background:rgba(8,12,20,.88);display:flex;align-items:center;justify-content:center;border-radius:var(--r);z-index:20;gap:8px;font-size:12px;color:var(--acc);border-radius:inherit}

/* ── IMPORT ── */
.imp-box{background:var(--s2);border:1px solid var(--b1);border-radius:var(--r);padding:22px;max-width:540px}
.step{display:flex;gap:11px;margin-bottom:14px}
.sn{width:24px;height:24px;border-radius:50%;background:var(--acc);color:#000;font-size:10px;font-weight:800;display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:2px}
.st h4{font-size:12px;font-weight:600;margin-bottom:2px}
.st p{font-size:11px;color:var(--t3)}
.dz{border:2px dashed var(--b2);border-radius:var(--r);padding:32px;text-align:center;cursor:pointer;transition:.2s;position:relative;margin-top:18px}
.dz:hover,.dz.drag{border-color:var(--acc);background:var(--acc3)}
.dz input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}

/* ── COLUMN MANAGEMENT ── */
.col-list{display:flex;flex-direction:column;gap:7px}
.col-row{display:flex;align-items:center;justify-content:space-between;background:var(--s2);border:1px solid var(--b1);border-radius:8px;padding:9px 12px}
.ct-badge{font-size:9px;padding:2px 7px;border-radius:4px;background:rgba(0,200,255,.1);color:var(--acc)}

/* ── TOAST ── */
.tc{position:fixed;bottom:18px;right:18px;z-index:999;display:flex;flex-direction:column;gap:5px;pointer-events:none}
.toast{padding:9px 15px;border-radius:8px;font-size:11px;min-width:200px;box-shadow:var(--sh);display:flex;align-items:center;gap:6px;animation:tin .22s ease;pointer-events:all}
.t-ok{background:#0a2018;border:1px solid var(--ok);color:var(--ok)}
.t-err{background:#200a10;border:1px solid var(--err);color:var(--err)}
.t-info{background:#0a1828;border:1px solid var(--acc);color:var(--acc)}
@keyframes tin{from{transform:translateX(110%);opacity:0}to{transform:translateX(0);opacity:1}}

/* ── MISC ── */
.empty{text-align:center;padding:48px 20px;color:var(--t3)}
.empty h3{font-family:'Syne',sans-serif;font-size:14px;color:var(--t2);margin-bottom:5px}
.spin{display:inline-block;width:12px;height:12px;border:2px solid var(--b2);border-top-color:var(--acc);border-radius:50%;animation:rot .5s linear infinite}
@keyframes rot{to{transform:rotate(360deg)}}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:var(--s1)}
::-webkit-scrollbar-thumb{background:var(--b2);border-radius:3px}
@media(max-width:680px){.side{display:none}.fgrid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="app">

<!-- ══════ SIDEBAR ══════ -->
<aside class="side">
  <div class="logo">
    <h1>◈ CRM</h1>
    <p>FILTER BAG TRACKER</p>
  </div>
  <nav class="nav">
    <div class="ni on" id="nav-records" onclick="gotoView('records')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="3"/></svg>All Records
    </div>
    <div class="ni" id="nav-columns" onclick="gotoView('columns')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>Manage Columns
    </div>
    <div class="ni" id="nav-import" onclick="gotoView('import')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>Import Excel
    </div>
    <div class="ni" onclick="doExport()">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>Export Excel
    </div>
  </nav>
  <div class="side-foot">SQLite · Flask · Python</div>
</aside>

<!-- ══════ MAIN CONTENT ══════ -->
<div class="content">

  <!-- Stats -->
  <div class="stats">
    <div class="sc"><div class="sc-l">Total Records</div><div class="sc-v" id="sRec">—</div></div>
    <div class="sc"><div class="sc-l">Columns</div><div class="sc-v" id="sCols">—</div></div>
    <div class="sc"><div class="sc-l">Attachments</div><div class="sc-v" id="sAtts">—</div></div>
    <div class="sc"><div class="sc-l">Added Today</div><div class="sc-v" id="sToday">—</div></div>
  </div>

  <!-- ── RECORDS ── -->
  <div class="view on" id="view-records">
    <div class="topbar">
      <h2>All <span>Records</span></h2>
      <div class="topbar-r">
        <button class="btn btn-g btn-sm" onclick="gotoView('import')">📥 Import Excel</button>
        <button class="btn btn-acc" onclick="openAddRec()">＋ Add Record</button>
      </div>
    </div>
    <div class="toolbar">
      <div class="srch">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input type="text" id="srchInput" placeholder="Search all fields…" oninput="onSearch()"/>
      </div>
      <button class="btn btn-g btn-sm" onclick="loadRecs()">↺</button>
      <span class="rec-info" id="recInfo"></span>
    </div>
    <!-- THE FIX: this div is flex:1 + overflow:auto → all rows scroll, none hidden -->
    <div class="table-area">
      <table>
        <thead id="tHead"></thead>
        <tbody id="tBody"></tbody>
      </table>
    </div>
  </div>

  <!-- ── COLUMNS ── -->
  <div class="view" id="view-columns">
    <div class="topbar">
      <h2>Manage <span>Columns</span></h2>
      <button class="btn btn-acc" onclick="openAddCol()">＋ Add Column</button>
    </div>
    <div style="padding:18px;overflow-y:auto;flex:1">
      <div class="col-list" id="colList"></div>
    </div>
  </div>

  <!-- ── IMPORT ── -->
  <div class="view" id="view-import">
    <div class="topbar"><h2>Import <span>Excel</span></h2></div>
    <div style="padding:20px;overflow-y:auto;flex:1">
      <div class="imp-box">
        <div class="step"><div class="sn">1</div><div class="st"><h4>Prepare Excel file</h4><p>Row 1 = Column headers. Row 2 onwards = data rows.</p></div></div>
        <div class="step"><div class="sn">2</div><div class="st"><h4>Upload below</h4><p>Columns auto-matched or auto-created. Every row = one CRM record.</p></div></div>
        <div class="step"><div class="sn">3</div><div class="st"><h4>Done!</h4><p>All rows appear in the Records table immediately.</p></div></div>
        <div class="dz" id="dz">
          <input type="file" accept=".xlsx,.xls" id="xlsInp" onchange="doImport(this)"/>
          <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="color:var(--acc)"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          <p style="margin-top:8px;font-size:12px"><strong style="color:var(--acc)">Click or drag & drop</strong> Excel file</p>
          <p style="font-size:10px;color:var(--t3);margin-top:5px">.xlsx / .xls supported · max 100 MB</p>
        </div>
        <div id="impRes" style="margin-top:12px"></div>
      </div>
    </div>
  </div>

</div>
</div>

<!-- ════════════ MODALS ════════════ -->

<!-- Record Add/Edit -->
<div class="ovl" id="mRec">
  <div class="modal modal-w">
    <div class="mh">
      <h3 id="mRecT">Add Record</h3>
      <button class="xb" onclick="closeM('mRec')">✕</button>
    </div>
    <div class="mb">
      <div class="fgrid" id="recFlds"></div>
      <div class="full" style="margin-top:4px">
        <div class="fg"><label>Tags (comma-separated)</label><input type="text" id="recTags" placeholder="vip, follow-up, lead"/></div>
        <div class="fg"><label>Notes</label><textarea id="recNotes" rows="3" placeholder="Internal notes…"></textarea></div>
      </div>
    </div>
    <div class="mf">
      <button class="btn btn-g" onclick="closeM('mRec')">Cancel</button>
      <button class="btn btn-acc" onclick="saveRec()">💾 Save</button>
    </div>
  </div>
</div>

<!-- ★ ATTACHMENT MODAL — opened from 📎 button in each table row ★ -->
<div class="ovl" id="mAtt">
  <div class="modal">
    <div class="mh">
      <h3>📎 Attachments &nbsp;<span style="color:var(--acc);font-size:13px" id="mAttLbl"></span></h3>
      <button class="xb" onclick="closeM('mAtt')">✕</button>
    </div>
    <div class="mb" style="position:relative" id="mAttBody">
      <div class="att-dz">
        <input type="file" multiple id="attInp" onchange="doUpload()"/>
        <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="color:var(--acc)"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/></svg>
        <p style="font-size:12px;margin-top:7px"><strong style="color:var(--acc)">Click or drop files here</strong></p>
        <p style="font-size:10px;color:var(--t3);margin-top:4px">Images · PDF · Video · Any file</p>
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
    <div class="mh"><h3>Add Column</h3><button class="xb" onclick="closeM('mCol')">✕</button></div>
    <div class="mb">
      <div class="fg"><label>Column Name *</label><input type="text" id="colNm" placeholder="e.g. Company, Status"/></div>
      <div class="fg"><label>Type</label>
        <select id="colTp">
          <option value="text">Text</option><option value="number">Number</option>
          <option value="email">Email</option><option value="phone">Phone</option>
          <option value="date">Date</option><option value="url">URL</option>
        </select>
      </div>
    </div>
    <div class="mf">
      <button class="btn btn-g" onclick="closeM('mCol')">Cancel</button>
      <button class="btn btn-acc" onclick="saveCol()">Add</button>
    </div>
  </div>
</div>

<div class="tc" id="tc"></div>

<script>
// ═══════ STATE ═══════
let cols=[], curRecId=null, curAttId=null, stimer=null;

// ═══════ BOOT ═══════
(async()=>{ await loadCols(); loadRecs(); loadStats(); })();

// ═══════ VIEW SWITCH ═══════
function gotoView(v){
  document.querySelectorAll('.view').forEach(e=>e.classList.remove('on'));
  document.querySelectorAll('.ni').forEach(e=>e.classList.remove('on'));
  document.getElementById('view-'+v).classList.add('on');
  const n=document.getElementById('nav-'+v); if(n) n.classList.add('on');
  if(v==='columns') renderColList();
}

// ═══════ STATS ═══════
async function loadStats(){
  const r=await fetch('/api/stats').then(r=>r.json());
  document.getElementById('sRec').textContent=r.records;
  document.getElementById('sCols').textContent=r.columns;
  document.getElementById('sAtts').textContent=r.attachments;
  document.getElementById('sToday').textContent=r.today;
}

// ═══════ COLUMNS ═══════
async function loadCols(){ const r=await fetch('/api/columns').then(r=>r.json()); cols=r.columns; }

function renderColList(){
  const el=document.getElementById('colList');
  if(!cols.length){el.innerHTML='<div class="empty"><p>No columns yet.</p></div>';return;}
  el.innerHTML=cols.map(c=>`
    <div class="col-row">
      <div style="display:flex;align-items:center;gap:8px">
        <span>${c.name}</span><span class="ct-badge">${c.col_type}</span>
      </div>
      <button class="btn btn-err btn-sm" onclick="delCol(${c.id},'${c.name}')">Delete</button>
    </div>`).join('');
}

function openAddCol(){ document.getElementById('colNm').value=''; openM('mCol'); }

async function saveCol(){
  const nm=document.getElementById('colNm').value.trim();
  if(!nm){toast('Column name required','err');return;}
  const r=await fetch('/api/columns',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:nm,col_type:document.getElementById('colTp').value})}).then(r=>r.json());
  if(r.success){toast('Column added!','ok');closeM('mCol');await loadCols();loadRecs();loadStats();}
  else toast(r.message,'err');
}

async function delCol(id,name){
  if(!confirm(`Delete column "${name}"? All data in this column will be removed.`)) return;
  await fetch('/api/columns/'+id,{method:'DELETE'});
  toast('Column deleted','ok'); await loadCols(); loadRecs(); loadStats();
}

// ═══════ RECORDS ═══════
function onSearch(){ clearTimeout(stimer); stimer=setTimeout(loadRecs,280); }

async function loadRecs(){
  const q=document.getElementById('srchInput').value;
  const r=await fetch('/api/records?q='+encodeURIComponent(q)).then(r=>r.json());
  renderTable(r.records);
  document.getElementById('recInfo').textContent=r.total+' records';
}

function renderTable(recs){
  const head=document.getElementById('tHead');
  const body=document.getElementById('tBody');

  const hcols=cols.map(c=>`
    <th><div class="th-w">${c.name}
      <span class="dc" onclick="delCol(${c.id},'${c.name}')" title="Delete column">✕</span>
    </div></th>`).join('');
  head.innerHTML=`<tr>
    <th style="color:var(--t3);width:36px">#</th>
    ${hcols}
    <th>📎 Files</th>
    <th>Added</th>
    <th style="text-align:right">Actions</th>
  </tr>`;

  if(!recs.length){
    body.innerHTML=`<tr><td colspan="${cols.length+4}">
      <div class="empty"><h3>No records found</h3><p>Add a record or import an Excel file</p></div>
    </td></tr>`;
    return;
  }

  body.innerHTML=recs.map((rec,i)=>{
    const cells=cols.map(c=>{
      const v=rec.data[c.id]||'';
      return `<td title="${v.replace(/"/g,'&quot;')}">${v||'<span style="color:var(--t3)">—</span>'}</td>`;
    }).join('');

    const ac=rec.attachments.length;
    const abtn=ac
      ? `<span class="att-btn has" onclick="openAtt(${rec.id})">📎 ${ac} file${ac>1?'s':''}</span>`
      : `<span class="att-btn" onclick="openAtt(${rec.id})">📎 Add files</span>`;

    return `<tr>
      <td class="td-n">${i+1}</td>
      ${cells}
      <td>${abtn}</td>
      <td style="color:var(--t3);font-size:10px;white-space:nowrap">${rec.created_at}</td>
      <td class="td-act" style="text-align:right">
        <button class="btn btn-g btn-ico btn-sm" title="Edit" onclick="openEditRec(${rec.id})">✏️</button>
        <button class="btn btn-err btn-ico btn-sm" title="Delete" onclick="delRec(${rec.id})">🗑</button>
      </td>
    </tr>`;
  }).join('');
}

// ═══════ ADD/EDIT RECORD ═══════
function openAddRec(){
  curRecId=null;
  document.getElementById('mRecT').textContent='Add Record';
  document.getElementById('recTags').value='';
  document.getElementById('recNotes').value='';
  buildFlds({});
  openM('mRec');
}

async function openEditRec(id){
  const r=await fetch('/api/records/'+id).then(r=>r.json());
  curRecId=id;
  document.getElementById('mRecT').textContent='Edit Record #'+id;
  document.getElementById('recTags').value=r.record.tags||'';
  document.getElementById('recNotes').value=r.record.notes||'';
  buildFlds(r.record.data);
  openM('mRec');
}

function buildFlds(data){
  const c=document.getElementById('recFlds');
  c.className='fgrid';
  c.innerHTML=cols.map(col=>`
    <div class="fg">
      <label>${col.name}</label>
      <input type="${col.col_type==='email'?'email':col.col_type==='date'?'date':col.col_type==='number'?'number':col.col_type==='url'?'url':'text'}"
        id="f_${col.id}" value="${(data[col.id]||'').replace(/"/g,'&quot;')}" placeholder="${col.name}"/>
    </div>`).join('') || '<p style="color:var(--t3)">Add columns first via Manage Columns.</p>';
}

async function saveRec(){
  const fd={};
  cols.forEach(c=>{const e=document.getElementById('f_'+c.id);if(e&&e.value.trim())fd[c.id]=e.value.trim();});
  const payload={data:fd,tags:document.getElementById('recTags').value,notes:document.getElementById('recNotes').value};
  const m=curRecId?'PUT':'POST', u=curRecId?'/api/records/'+curRecId:'/api/records';
  const r=await fetch(u,{method:m,headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}).then(r=>r.json());
  if(r.success){toast(curRecId?'Record updated!':'Record added!','ok');closeM('mRec');loadRecs();loadStats();}
  else toast(r.message||'Error','err');
}

async function delRec(id){
  if(!confirm('Delete this record and all its attached files?')) return;
  await fetch('/api/records/'+id,{method:'DELETE'});
  toast('Record deleted','ok'); loadRecs(); loadStats();
}

// ═══════ ★ ATTACHMENT MODAL ★ ═══════
async function openAtt(recId){
  curAttId=recId;
  document.getElementById('mAttLbl').textContent='Record #'+recId;
  await refreshAtts();
  openM('mAtt');
}

async function refreshAtts(){
  const r=await fetch('/api/records/'+curAttId).then(r=>r.json());
  const atts=r.record.attachments;
  const el=document.getElementById('attList');

  if(!atts.length){
    el.innerHTML='<p style="color:var(--t3);font-size:12px;text-align:center;padding:10px">No files yet. Upload above.</p>';
  } else {
    el.innerHTML=atts.map(a=>{
      const icon=a.file_type==='image'?'🖼️':a.file_type==='video'?'🎬':a.file_type==='pdf'?'📄':'📁';
      const prev=a.file_type==='image'
        ? `<img class="att-thumb" src="${a.url}" onerror="this.outerHTML='<div class=att-ico>🖼️</div>'">`
        : `<div class="att-ico">${icon}</div>`;
      return `<div class="att-item">
        ${prev}
        <div class="att-inf">
          <div class="att-nm" title="${a.original_name}">${a.original_name}</div>
          <div class="att-mt">${a.file_size_str} · ${a.file_type}</div>
        </div>
        <div class="att-ac">
          <a href="${a.url}" download="${a.original_name}" class="btn btn-g btn-sm">⬇</a>
          ${a.file_type==='image'||a.file_type==='pdf'||a.file_type==='video'
            ?`<a href="${a.url}" target="_blank" class="btn btn-g btn-sm">👁</a>`:'' }
          <button class="btn btn-err btn-sm" onclick="delAtt(${a.id})">✕</button>
        </div>
      </div>`;
    }).join('');
  }

  // Update the attachment button in table without reloading entire table
  const oldBtn = document.querySelector(`[onclick="openAtt(${curAttId})"]`);
  if(oldBtn){
    if(atts.length){
      oldBtn.className='att-btn has';
      oldBtn.innerHTML=`📎 ${atts.length} file${atts.length>1?'s':''}`;
      oldBtn.setAttribute('onclick',`openAtt(${curAttId})`);
    } else {
      oldBtn.className='att-btn';
      oldBtn.innerHTML='📎 Add files';
    }
  }
  loadStats();
}

async function doUpload(){
  const files=document.getElementById('attInp').files;
  if(!files.length) return;
  const body=document.getElementById('mAttBody');
  const ov=document.createElement('div');
  ov.className='upl-ov';
  ov.innerHTML=`<span class="spin"></span>&nbsp;Uploading ${files.length} file(s)…`;
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
  if(!confirm('Delete this attachment permanently?')) return;
  await fetch('/api/attachments/'+id,{method:'DELETE'});
  toast('Deleted','ok');
  await refreshAtts();
}

// ═══════ EXCEL ═══════
async function doImport(inp){
  const f=inp.files[0]; if(!f) return;
  const rd=document.getElementById('impRes');
  rd.innerHTML='<div class="toast t-info"><span class="spin"></span> Importing…</div>';
  const fd=new FormData(); fd.append('file',f);
  const r=await fetch('/api/import',{method:'POST',body:fd}).then(r=>r.json());
  rd.innerHTML=r.success
    ? `<div class="toast t-ok">✅ ${r.message} (${r.cols} columns detected)</div>`
    : `<div class="toast t-err">❌ ${r.message}</div>`;
  inp.value='';
  if(r.success){ await loadCols(); loadRecs(); loadStats(); }
}

function doExport(){ window.open('/api/export','_blank'); toast('Downloading export…','info'); }

// ═══════ MODAL HELPERS ═══════
function openM(id){ document.getElementById(id).classList.add('on'); }
function closeM(id){ document.getElementById(id).classList.remove('on'); }
document.querySelectorAll('.ovl').forEach(el=>
  el.addEventListener('click',e=>{ if(e.target===el) el.classList.remove('on'); }));

// ═══════ DRAG DROP IMPORT ═══════
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

// ═══════ TOAST ═══════
function toast(msg,type='info'){
  const tc=document.getElementById('tc');
  const t=document.createElement('div');
  t.className='toast t-'+type; t.textContent=msg;
  tc.appendChild(t); setTimeout(()=>t.remove(),3000);
}
</script>
</body>
</html>"""


if __name__ == '__main__':
    print("="*50)
    print("🚀 CRM Dashboard — Fixed & Updated")
    print("📍 Open: http://127.0.0.1:5000")
    print("✅ Fix 1: All rows visible (flex scroll)")
    print("✅ Fix 2: 📎 Attachment button in each row")
    print("="*50)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port,)
