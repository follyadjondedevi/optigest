from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3, hashlib, os
from datetime import date, datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = "optigest_secret_2024"
DB_PATH = os.path.join(os.path.dirname(__file__), "lunetterie.db")

# ─── DB ───────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS utilisateurs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL, prenom TEXT NOT NULL,
        username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
        role TEXT DEFAULT 'employe', actif INTEGER DEFAULT 1,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL, prenom TEXT NOT NULL,
        telephone TEXT, email TEXT, adresse TEXT, date_naissance TEXT, notes TEXT,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS ordonnances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER, date_ordonnance TEXT, medecin TEXT,
        od_sphere REAL, od_cylindre REAL, od_axe REAL,
        og_sphere REAL, og_cylindre REAL, og_axe REAL, addition REAL, notes TEXT,
        FOREIGN KEY(client_id) REFERENCES clients(id)
    );
    CREATE TABLE IF NOT EXISTS produits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL, categorie TEXT, prix REAL NOT NULL,
        stock INTEGER DEFAULT 0, description TEXT
    );
    CREATE TABLE IF NOT EXISTS ventes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER, employe_id INTEGER,
        date_vente TEXT DEFAULT CURRENT_TIMESTAMP,
        total REAL NOT NULL, paiement TEXT, statut TEXT DEFAULT 'payé', notes TEXT,
        FOREIGN KEY(client_id) REFERENCES clients(id),
        FOREIGN KEY(employe_id) REFERENCES utilisateurs(id)
    );
    CREATE TABLE IF NOT EXISTS vente_details (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vente_id INTEGER, produit_id INTEGER, quantite INTEGER, prix_unitaire REAL,
        FOREIGN KEY(vente_id) REFERENCES ventes(id),
        FOREIGN KEY(produit_id) REFERENCES produits(id)
    );
    CREATE TABLE IF NOT EXISTS taches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titre TEXT NOT NULL, description TEXT,
        assigne_a INTEGER, cree_par INTEGER,
        priorite TEXT DEFAULT 'normale', statut TEXT DEFAULT 'à faire',
        date_echeance TEXT, date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(assigne_a) REFERENCES utilisateurs(id),
        FOREIGN KEY(cree_par) REFERENCES utilisateurs(id)
    );
    """)
    pw = hashlib.sha256("admin123".encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO utilisateurs (nom,prenom,username,password,role) VALUES (?,?,?,?,?)",
              ("Admin","Système","admin",pw,"admin"))
    c.executemany("INSERT OR IGNORE INTO produits (nom,categorie,prix,stock) VALUES (?,?,?,?)", [
        ("Monture Ray-Ban","Montures",45000,10),
        ("Monture Oakley","Montures",55000,8),
        ("Verres simples","Verres",15000,50),
        ("Verres progressifs","Verres",45000,20),
        ("Lunettes soleil","Solaires",25000,15),
        ("Étui rigide","Accessoires",3000,30),
        ("Solution nettoyage","Accessoires",2500,25),
    ])
    conn.commit(); conn.close()

def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('user', {}).get('role') != 'admin':
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

# ─── AUTH ─────────────────────────────────────────────────────────
@app.route('/', methods=['GET','POST'])
def login():
    error = None
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        p = request.form.get('password','').strip()
        conn = get_db()
        row = conn.execute("SELECT * FROM utilisateurs WHERE username=? AND password=? AND actif=1",
                           (u, hash_pw(p))).fetchone()
        conn.close()
        if row:
            session['user'] = dict(row)
            return redirect(url_for('dashboard'))
        error = "Identifiants incorrects."
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─── DASHBOARD ────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    today = date.today().isoformat()
    stats = {
        'clients': conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0],
        'ventes_today': conn.execute("SELECT COALESCE(SUM(total),0) FROM ventes WHERE date(date_vente)=?", (today,)).fetchone()[0],
        'taches': conn.execute("SELECT COUNT(*) FROM taches WHERE statut!='terminé'").fetchone()[0],
        'employes': conn.execute("SELECT COUNT(*) FROM utilisateurs WHERE actif=1").fetchone()[0],
    }
    last_ventes = conn.execute("""
        SELECT v.id, COALESCE(c.nom||' '||c.prenom,'Client inconnu') as client,
               v.total, v.date_vente, v.statut, v.paiement
        FROM ventes v LEFT JOIN clients c ON v.client_id=c.id
        ORDER BY v.id DESC LIMIT 8""").fetchall()
    taches_recentes = conn.execute("""
        SELECT t.*, COALESCE(u.prenom||' '||u.nom,'-') as assigne
        FROM taches t LEFT JOIN utilisateurs u ON t.assigne_a=u.id
        WHERE t.statut!='terminé' ORDER BY t.id DESC LIMIT 5""").fetchall()
    conn.close()
    return render_template('dashboard.html', stats=stats, last_ventes=last_ventes, taches=taches_recentes)

# ─── CLIENTS ──────────────────────────────────────────────────────
@app.route('/clients')
@login_required
def clients():
    q = request.args.get('q','')
    conn = get_db()
    rows = conn.execute("SELECT * FROM clients WHERE nom LIKE ? OR prenom LIKE ? OR telephone LIKE ? ORDER BY nom",
                        (f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
    conn.close()
    return render_template('clients.html', clients=rows, q=q)

@app.route('/clients/new', methods=['GET','POST'])
@login_required
def client_new():
    if request.method == 'POST':
        f = request.form
        conn = get_db()
        conn.execute("INSERT INTO clients (nom,prenom,telephone,email,adresse,date_naissance,notes) VALUES (?,?,?,?,?,?,?)",
                     (f['nom'],f['prenom'],f.get('telephone'),f.get('email'),f.get('adresse'),f.get('date_naissance'),f.get('notes')))
        conn.commit(); conn.close()
        return redirect(url_for('clients'))
    return render_template('client_form.html', client=None, title="Nouveau client")

@app.route('/clients/<int:cid>/edit', methods=['GET','POST'])
@login_required
def client_edit(cid):
    conn = get_db()
    if request.method == 'POST':
        f = request.form
        conn.execute("UPDATE clients SET nom=?,prenom=?,telephone=?,email=?,adresse=?,date_naissance=?,notes=? WHERE id=?",
                     (f['nom'],f['prenom'],f.get('telephone'),f.get('email'),f.get('adresse'),f.get('date_naissance'),f.get('notes'),cid))
        conn.commit(); conn.close()
        return redirect(url_for('clients'))
    c = conn.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
    conn.close()
    return render_template('client_form.html', client=c, title="Modifier client")

@app.route('/clients/<int:cid>')
@login_required
def client_detail(cid):
    conn = get_db()
    c = conn.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
    ords = conn.execute("SELECT * FROM ordonnances WHERE client_id=? ORDER BY date_ordonnance DESC", (cid,)).fetchall()
    ventes = conn.execute("""SELECT v.id,v.total,v.date_vente,v.statut,v.paiement FROM ventes v
        WHERE v.client_id=? ORDER BY v.id DESC LIMIT 10""", (cid,)).fetchall()
    conn.close()
    return render_template('client_detail.html', client=c, ordonnances=ords, ventes=ventes)

@app.route('/clients/<int:cid>/ordonnance', methods=['POST'])
@login_required
def ordonnance_add(cid):
    f = request.form
    def flt(k):
        try: return float(f.get(k,''))
        except: return None
    conn = get_db()
    conn.execute("""INSERT INTO ordonnances (client_id,date_ordonnance,medecin,
        od_sphere,od_cylindre,od_axe,og_sphere,og_cylindre,og_axe,addition,notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (cid,f.get('date_ordonnance'),f.get('medecin'),
         flt('od_sphere'),flt('od_cylindre'),flt('od_axe'),
         flt('og_sphere'),flt('og_cylindre'),flt('og_axe'),flt('addition'),f.get('notes')))
    conn.commit(); conn.close()
    return redirect(url_for('client_detail', cid=cid))

# ─── CAISSE ───────────────────────────────────────────────────────
@app.route('/caisse')
@login_required
def caisse():
    q = request.args.get('q','')
    conn = get_db()
    ventes = conn.execute("""
        SELECT v.*, COALESCE(c.nom||' '||c.prenom,'Client inconnu') as client_nom
        FROM ventes v LEFT JOIN clients c ON v.client_id=c.id
        WHERE c.nom LIKE ? OR c.prenom LIKE ? OR v.id LIKE ?
        ORDER BY v.id DESC LIMIT 50""", (f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
    conn.close()
    return render_template('caisse.html', ventes=ventes, q=q)

@app.route('/caisse/new', methods=['GET','POST'])
@login_required
def vente_new():
    conn = get_db()
    if request.method == 'POST':
        f = request.form
        client_id = f.get('client_id') or None
        produit_ids = request.form.getlist('produit_id[]')
        quantites = request.form.getlist('quantite[]')
        prix_list = request.form.getlist('prix[]')
        total = 0
        items = []
        for pid, qty, prix in zip(produit_ids, quantites, prix_list):
            try:
                q2 = int(qty); p2 = float(prix)
                total += q2 * p2
                items.append((int(pid), q2, p2))
            except: continue
        if items:
            cur = conn.execute("INSERT INTO ventes (client_id,employe_id,total,paiement,statut,notes) VALUES (?,?,?,?,?,?)",
                               (client_id, session['user']['id'], total, f.get('paiement','Espèces'), 'payé', f.get('notes','')))
            vid = cur.lastrowid
            for pid2, q2, p2 in items:
                conn.execute("INSERT INTO vente_details (vente_id,produit_id,quantite,prix_unitaire) VALUES (?,?,?,?)",
                             (vid, pid2, q2, p2))
                conn.execute("UPDATE produits SET stock=MAX(0,stock-?) WHERE id=?", (q2, pid2))
            conn.commit()
        conn.close()
        return redirect(url_for('caisse'))
    clients_list = conn.execute("SELECT id, nom||' '||prenom as label FROM clients ORDER BY nom").fetchall()
    produits_list = conn.execute("SELECT * FROM produits ORDER BY categorie, nom").fetchall()
    conn.close()
    return render_template('vente_form.html', clients=clients_list, produits=produits_list)

@app.route('/caisse/<int:vid>')
@login_required
def vente_detail(vid):
    conn = get_db()
    v = conn.execute("""SELECT v.*, COALESCE(c.nom||' '||c.prenom,'Inconnu') as client_nom,
        COALESCE(u.prenom||' '||u.nom,'-') as employe_nom
        FROM ventes v LEFT JOIN clients c ON v.client_id=c.id
        LEFT JOIN utilisateurs u ON v.employe_id=u.id WHERE v.id=?""", (vid,)).fetchone()
    details = conn.execute("""SELECT vd.*, p.nom as produit_nom FROM vente_details vd
        JOIN produits p ON vd.produit_id=p.id WHERE vd.vente_id=?""", (vid,)).fetchall()
    conn.close()
    return render_template('vente_detail.html', vente=v, details=details)

# ─── TÂCHES ───────────────────────────────────────────────────────
@app.route('/taches')
@login_required
def taches():
    filtre = request.args.get('statut','')
    conn = get_db()
    if filtre:
        rows = conn.execute("""SELECT t.*, COALESCE(u.prenom||' '||u.nom,'-') as assigne
            FROM taches t LEFT JOIN utilisateurs u ON t.assigne_a=u.id
            WHERE t.statut=? ORDER BY t.id DESC""", (filtre,)).fetchall()
    else:
        rows = conn.execute("""SELECT t.*, COALESCE(u.prenom||' '||u.nom,'-') as assigne
            FROM taches t LEFT JOIN utilisateurs u ON t.assigne_a=u.id ORDER BY t.id DESC""").fetchall()
    conn.close()
    return render_template('taches.html', taches=rows, filtre=filtre)

@app.route('/taches/new', methods=['GET','POST'])
@login_required
def tache_new():
    conn = get_db()
    if request.method == 'POST':
        f = request.form
        conn.execute("INSERT INTO taches (titre,description,assigne_a,cree_par,priorite,statut,date_echeance) VALUES (?,?,?,?,?,?,?)",
                     (f['titre'],f.get('description'),f.get('assigne_a') or None,session['user']['id'],
                      f.get('priorite','normale'),f.get('statut','à faire'),f.get('date_echeance') or None))
        conn.commit(); conn.close()
        return redirect(url_for('taches'))
    employes = conn.execute("SELECT id, prenom||' '||nom as label FROM utilisateurs WHERE actif=1").fetchall()
    conn.close()
    return render_template('tache_form.html', tache=None, employes=employes, title="Nouvelle tâche")

@app.route('/taches/<int:tid>/edit', methods=['GET','POST'])
@login_required
def tache_edit(tid):
    conn = get_db()
    if request.method == 'POST':
        f = request.form
        conn.execute("UPDATE taches SET titre=?,description=?,assigne_a=?,priorite=?,statut=?,date_echeance=? WHERE id=?",
                     (f['titre'],f.get('description'),f.get('assigne_a') or None,
                      f.get('priorite'),f.get('statut'),f.get('date_echeance') or None, tid))
        conn.commit(); conn.close()
        return redirect(url_for('taches'))
    t = conn.execute("SELECT * FROM taches WHERE id=?", (tid,)).fetchone()
    employes = conn.execute("SELECT id, prenom||' '||nom as label FROM utilisateurs WHERE actif=1").fetchall()
    conn.close()
    return render_template('tache_form.html', tache=t, employes=employes, title="Modifier tâche")

@app.route('/taches/<int:tid>/done', methods=['POST'])
@login_required
def tache_done(tid):
    conn = get_db()
    conn.execute("UPDATE taches SET statut='terminé' WHERE id=?", (tid,))
    conn.commit(); conn.close()
    return redirect(url_for('taches'))

# ─── PERSONNEL ────────────────────────────────────────────────────
@app.route('/personnel')
@login_required
def personnel():
    conn = get_db()
    rows = conn.execute("SELECT * FROM utilisateurs ORDER BY nom").fetchall()
    conn.close()
    return render_template('personnel.html', employes=rows)

@app.route('/personnel/new', methods=['GET','POST'])
@login_required
def employe_new():
    error = None
    if request.method == 'POST':
        f = request.form
        if not f.get('password'):
            error = "Le mot de passe est obligatoire."
        else:
            conn = get_db()
            try:
                conn.execute("INSERT INTO utilisateurs (nom,prenom,username,password,role) VALUES (?,?,?,?,?)",
                             (f['nom'],f['prenom'],f['username'],hash_pw(f['password']),f.get('role','employe')))
                conn.commit()
            except Exception as e:
                error = "Ce nom d'utilisateur existe déjà."
            conn.close()
            if not error:
                return redirect(url_for('personnel'))
    return render_template('employe_form.html', employe=None, title="Nouvel employé", error=error)

@app.route('/personnel/<int:uid>/edit', methods=['GET','POST'])
@login_required
def employe_edit(uid):
    error = None
    conn = get_db()
    if request.method == 'POST':
        f = request.form
        if f.get('password'):
            conn.execute("UPDATE utilisateurs SET nom=?,prenom=?,username=?,password=?,role=? WHERE id=?",
                         (f['nom'],f['prenom'],f['username'],hash_pw(f['password']),f.get('role'),uid))
        else:
            conn.execute("UPDATE utilisateurs SET nom=?,prenom=?,username=?,role=? WHERE id=?",
                         (f['nom'],f['prenom'],f['username'],f.get('role'),uid))
        conn.commit(); conn.close()
        return redirect(url_for('personnel'))
    u = conn.execute("SELECT * FROM utilisateurs WHERE id=?", (uid,)).fetchone()
    conn.close()
    return render_template('employe_form.html', employe=u, title="Modifier employé", error=error)

@app.route('/personnel/<int:uid>/toggle', methods=['POST'])
@login_required
def employe_toggle(uid):
    if uid == session['user']['id']:
        return redirect(url_for('personnel'))
    conn = get_db()
    u = conn.execute("SELECT actif FROM utilisateurs WHERE id=?", (uid,)).fetchone()
    conn.execute("UPDATE utilisateurs SET actif=? WHERE id=?", (0 if u['actif'] else 1, uid))
    conn.commit(); conn.close()
    return redirect(url_for('personnel'))

# ─── PRODUITS ─────────────────────────────────────────────────────
@app.route('/produits')
@login_required
def produits():
    conn = get_db()
    rows = conn.execute("SELECT * FROM produits ORDER BY categorie, nom").fetchall()
    conn.close()
    return render_template('produits.html', produits=rows)

@app.route('/produits/new', methods=['GET','POST'])
@login_required
def produit_new():
    if request.method == 'POST':
        f = request.form
        conn = get_db()
        conn.execute("INSERT INTO produits (nom,categorie,prix,stock,description) VALUES (?,?,?,?,?)",
                     (f['nom'],f.get('categorie'),float(f['prix']),int(f.get('stock',0)),f.get('description')))
        conn.commit(); conn.close()
        return redirect(url_for('produits'))
    return render_template('produit_form.html', produit=None, title="Nouveau produit")

@app.route('/produits/<int:pid>/edit', methods=['GET','POST'])
@login_required
def produit_edit(pid):
    conn = get_db()
    if request.method == 'POST':
        f = request.form
        conn.execute("UPDATE produits SET nom=?,categorie=?,prix=?,stock=?,description=? WHERE id=?",
                     (f['nom'],f.get('categorie'),float(f['prix']),int(f.get('stock',0)),f.get('description'),pid))
        conn.commit(); conn.close()
        return redirect(url_for('produits'))
    p = conn.execute("SELECT * FROM produits WHERE id=?", (pid,)).fetchone()
    conn.close()
    return render_template('produit_form.html', produit=p, title="Modifier produit")

# ─── API JSON ─────────────────────────────────────────────────────
@app.route('/api/produits')
@login_required
def api_produits():
    conn = get_db()
    rows = conn.execute("SELECT id, nom, prix, stock FROM produits ORDER BY nom").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

if __name__ == '__main__':
    init_db()
    print("\n✅ OptiGest Web démarré !")
    print("👉 Ouvrez votre navigateur sur : http://localhost:5000")
    print("📱 Sur téléphone (même WiFi) : http://<IP-du-PC>:5000\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
