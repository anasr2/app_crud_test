import os
import smtplib
import uuid
import secrets
from datetime import datetime
from email.message import EmailMessage
from functools import wraps
from pathlib import Path

from sqlalchemy import inspect, or_, text
from flask import Flask, flash, redirect, render_template, request, send_from_directory, session, url_for
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from models import Client, ClientDocument, ClientInteraction, ClientProject, ClientProjectStep, User, db


def load_dotenv(dotenv_path=".env"):
    env_file = Path(dotenv_path)
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()

# Creation de l'application Flask.
app = Flask(__name__)

# Configuration de la connexion a la base de donnees.
# Priorite a la variable d'environnement DATABASE_URL, sinon fallback local SQL Server.
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "mssql+pyodbc://@localhost\\SQLEXPRESS/testdb?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes",
)
# Desactive le suivi des modifications SQLAlchemy (cout CPU inutile ici).
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# Cle de session Flask (a surcharger en production).
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
app.config["UPLOAD_FOLDER"] = os.path.join(app.instance_path, "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_SECURE_COOKIE", "0") == "1"
app.config["INVITATION_EXPIRY_HOURS"] = int(os.getenv("INVITATION_EXPIRY_HOURS", "72"))
app.config["MAIL_USE_TLS"] = True


# Decorateur de protection: force la connexion avant d'acceder aux pages privees.
def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        # Si aucun utilisateur en session, redirection vers la page login.
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)

    return wrapped_view


def roles_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(*args, **kwargs):
            if not session.get("user_id"):
                return redirect(url_for("login", next=request.path))
            if session.get("role") not in allowed_roles:
                flash("Acces refuse pour ce profil.", "danger")
                return redirect(url_for("index"))
            return view_func(*args, **kwargs)

        return wrapped_view

    return decorator


# Verifie que l'URL de redirection reste interne a l'application.
def is_safe_next_url(target):
    return bool(target) and target.startswith("/") and not target.startswith("//")


def is_password_hashed(value):
    return bool(value) and value.startswith(("scrypt:", "pbkdf2:"))


def hash_password(password):
    return generate_password_hash(password)


def build_external_url(path):
    base_url = os.getenv("APP_BASE_URL", "").rstrip("/")
    if base_url:
        return f"{base_url}{path}"
    return path


def generate_invitation_token():
    return secrets.token_urlsafe(48)


def create_pending_password():
    return hash_password(secrets.token_urlsafe(32))


def verify_password(stored_password, plain_password):
    if not stored_password:
        return False
    if is_password_hashed(stored_password):
        return check_password_hash(stored_password, plain_password)
    return stored_password == plain_password


def get_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def csrf_input():
    return Markup(f'<input type="hidden" name="csrf_token" value="{get_csrf_token()}">')


CLIENT_STATUSES = {
    "prospect": "Prospect",
    "contacte": "Contacte",
    "negociation": "Negociation",
    "client": "Client",
    "perdu": "Perdu",
}

USER_ROLES = {
    "administrateur": "Administrateur",
    "commercial": "Commercial",
    "consultant": "Consultant",
}

LEAD_SOURCES = {
    "site_web": "Site web",
    "recommandation": "Recommandation",
    "reseaux_sociaux": "Reseaux sociaux",
    "publicite": "Publicite",
    "sortant": "Prospection sortante",
    "inconnu": "Inconnu",
}

INTERACTION_TYPES = {
    "appel": "Appel",
    "email": "Email",
    "reunion": "Reunion",
    "note": "Note interne",
    "support": "Support",
}

PROJECT_STATUSES = {
    "planifie": "Planifie",
    "en_cours": "En cours",
    "en_attente": "En attente",
    "termine": "Termine",
    "bloque": "Bloque",
}

PROJECT_PRIORITIES = {
    "basse": "Basse",
    "moyenne": "Moyenne",
    "haute": "Haute",
    "critique": "Critique",
}

PROJECT_STEP_STATUSES = {
    "a_faire": "A faire",
    "en_cours": "En cours",
    "terminee": "Terminee",
    "bloquee": "Bloquee",
}

ALLOWED_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".txt",
}


def ensure_client_schema():
    inspector = inspect(db.engine)
    existing_columns = {column["name"] for column in inspector.get_columns("clients")}
    ddl_by_column = {
        "entreprise": "ALTER TABLE clients ADD entreprise VARCHAR(120) NOT NULL DEFAULT ''",
        "telephone": "ALTER TABLE clients ADD telephone VARCHAR(40) NOT NULL DEFAULT ''",
        "statut": "ALTER TABLE clients ADD statut VARCHAR(30) NOT NULL DEFAULT 'prospect'",
        "source": "ALTER TABLE clients ADD source VARCHAR(60) NOT NULL DEFAULT 'inconnu'",
        "valeur_potentielle": "ALTER TABLE clients ADD valeur_potentielle FLOAT NOT NULL DEFAULT 0",
        "prochaine_action": "ALTER TABLE clients ADD prochaine_action VARCHAR(160) NOT NULL DEFAULT ''",
        "notes": "ALTER TABLE clients ADD notes VARCHAR(2000) NOT NULL DEFAULT ''",
    }

    with db.engine.begin() as connection:
        for column_name, ddl in ddl_by_column.items():
            if column_name not in existing_columns:
                connection.execute(text(ddl))

        if "created_at" not in existing_columns:
            connection.execute(text("ALTER TABLE clients ADD created_at DATETIME NULL"))
            connection.execute(text("UPDATE clients SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))

        if "updated_at" not in existing_columns:
            connection.execute(text("ALTER TABLE clients ADD updated_at DATETIME NULL"))
            connection.execute(text("UPDATE clients SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"))


def ensure_user_schema():
    inspector = inspect(db.engine)
    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    with db.engine.begin() as connection:
        if "role" not in existing_columns:
            connection.execute(
                text("ALTER TABLE users ADD role VARCHAR(30) NOT NULL DEFAULT 'administrateur'")
            )
        if "invitation_token" not in existing_columns:
            connection.execute(text("ALTER TABLE users ADD invitation_token VARCHAR(255) NULL"))
        if "invitation_sent_at" not in existing_columns:
            connection.execute(text("ALTER TABLE users ADD invitation_sent_at DATETIME NULL"))
        if "email_verified_at" not in existing_columns:
            connection.execute(text("ALTER TABLE users ADD email_verified_at DATETIME NULL"))
            connection.execute(text("UPDATE users SET email_verified_at = CURRENT_TIMESTAMP WHERE email_verified_at IS NULL"))


@app.context_processor
def inject_template_helpers():
    current_role = session.get("role", "")
    return {
        "csrf_input": csrf_input,
        "current_role": current_role,
        "role_labels": USER_ROLES,
        "can_manage_clients": current_role in {"administrateur", "commercial"},
        "is_admin": current_role == "administrateur",
    }


@app.before_request
def protect_from_csrf():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None

    expected_token = session.get("_csrf_token")
    received_token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
    if not expected_token or not received_token or expected_token != received_token:
        flash("Session invalide ou formulaire expire. Reessaie.", "danger")
        return redirect(request.referrer or url_for("login"))
    return None


def invitation_is_expired(user):
    if not user.invitation_sent_at:
        return True
    age = datetime.utcnow() - user.invitation_sent_at
    return age.total_seconds() > app.config["INVITATION_EXPIRY_HOURS"] * 3600


def send_invitation_email(user):
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@example.com")
    use_tls = os.getenv("SMTP_USE_TLS", "1") == "1"

    activation_path = url_for("activate_account", token=user.invitation_token)
    activation_link = build_external_url(activation_path)

    if not smtp_host:
        return False, activation_link

    message = EmailMessage()
    message["Subject"] = "Activation de votre compte CRM"
    message["From"] = smtp_from
    message["To"] = user.email
    message.set_content(
        "\n".join(
            [
                f"Bonjour {user.username},",
                "",
                "Votre compte CRM a ete cree.",
                "Cliquez sur le lien suivant pour verifier votre email et definir votre mot de passe :",
                activation_link,
                "",
                f"Ce lien expire dans {app.config['INVITATION_EXPIRY_HOURS']} heures.",
            ]
        )
    )

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        if use_tls:
            server.starttls()
        if smtp_user:
            server.login(smtp_user, smtp_password)
        server.send_message(message)
    return True, activation_link


def allowed_document(filename):
    return Path(filename).suffix.lower() in ALLOWED_DOCUMENT_EXTENSIONS


def build_upload_folder(client_id):
    target_dir = Path(app.config["UPLOAD_FOLDER"]) / str(client_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def build_client_context():
    search = request.args.get("q", "").strip()
    selected_status = request.args.get("status", "").strip()

    query = Client.query

    if search:
        like_term = f"%{search}%"
        query = query.filter(
            or_(
                Client.nom.ilike(like_term),
                Client.email.ilike(like_term),
                Client.entreprise.ilike(like_term),
                Client.telephone.ilike(like_term),
            )
        )

    if selected_status in CLIENT_STATUSES:
        query = query.filter(Client.statut == selected_status)

    clients = query.order_by(Client.updated_at.desc(), Client.id.desc()).all()
    all_clients = Client.query.all()

    stats = {
        "total": len(all_clients),
        "actifs": sum(client.statut in {"prospect", "contacte", "negociation"} for client in all_clients),
        "clients": sum(client.statut == "client" for client in all_clients),
        "pipeline": sum(client.valeur_potentielle or 0 for client in all_clients if client.statut != "perdu"),
        "projects": sum(len(client.projects) for client in all_clients),
    }

    return {
        "clients": clients,
        "stats": stats,
        "search": search,
        "selected_status": selected_status,
        "status_choices": CLIENT_STATUSES,
        "source_choices": LEAD_SOURCES,
        "project_status_choices": PROJECT_STATUSES,
    }


def build_project_context():
    search = request.args.get("q", "").strip()
    selected_status = request.args.get("status", "").strip()
    selected_priority = request.args.get("priority", "").strip()

    query = ClientProject.query.join(Client)

    if search:
        like_term = f"%{search}%"
        query = query.filter(
            or_(
                ClientProject.name.ilike(like_term),
                ClientProject.owner.ilike(like_term),
                Client.nom.ilike(like_term),
                Client.entreprise.ilike(like_term),
            )
        )

    if selected_status in PROJECT_STATUSES:
        query = query.filter(ClientProject.status == selected_status)

    if selected_priority in PROJECT_PRIORITIES:
        query = query.filter(ClientProject.priority == selected_priority)

    projects = query.order_by(ClientProject.updated_at.desc(), ClientProject.id.desc()).all()
    all_projects = ClientProject.query.all()
    all_steps = ClientProjectStep.query.all()

    stats = {
        "total": len(all_projects),
        "in_progress": sum(project.status == "en_cours" for project in all_projects),
        "done": sum(project.status == "termine" for project in all_projects),
        "blocked": sum(project.status == "bloque" for project in all_projects),
        "steps": len(all_steps),
    }

    return {
        "projects": projects,
        "stats": stats,
        "search": search,
        "selected_status": selected_status,
        "selected_priority": selected_priority,
        "project_status_choices": PROJECT_STATUSES,
        "project_priority_choices": PROJECT_PRIORITIES,
        "project_step_status_choices": PROJECT_STEP_STATUSES,
    }


def populate_client_from_form(client):
    client.nom = request.form.get("nom", "").strip()
    client.email = request.form.get("email", "").strip()
    client.entreprise = request.form.get("entreprise", "").strip()
    client.telephone = request.form.get("telephone", "").strip()

    statut = request.form.get("statut", "prospect").strip()
    source = request.form.get("source", "inconnu").strip()
    client.statut = statut if statut in CLIENT_STATUSES else "prospect"
    client.source = source if source in LEAD_SOURCES else "inconnu"

    client.valeur_potentielle = parse_float(request.form.get("valeur_potentielle"), 0)

    client.prochaine_action = request.form.get("prochaine_action", "").strip()
    client.notes = request.form.get("notes", "").strip()
    client.updated_at = datetime.utcnow()


def create_interaction(client, interaction_type, summary, details=""):
    log_entry = ClientInteraction(
        client=client,
        interaction_type=interaction_type if interaction_type in INTERACTION_TYPES else "note",
        summary=summary.strip(),
        details=details.strip(),
        created_by=session.get("username", ""),
    )
    db.session.add(log_entry)
    client.updated_at = datetime.utcnow()
    return log_entry


def parse_float(value, default=0):
    raw_value = (value or "").strip().replace(",", ".")
    try:
        return float(raw_value or default)
    except ValueError:
        return default


def parse_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_date(value):
    raw_value = (value or "").strip()
    if not raw_value:
        return None
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError:
        return None


def populate_project_from_form(project):
    project.name = request.form.get("name", "").strip()
    status = request.form.get("status", "planifie").strip()
    priority = request.form.get("priority", "moyenne").strip()
    project.status = status if status in PROJECT_STATUSES else "planifie"
    project.priority = priority if priority in PROJECT_PRIORITIES else "moyenne"
    project.budget = parse_float(request.form.get("budget"), 0)
    project.progress = max(0, min(100, parse_int(request.form.get("progress"), 0)))
    project.due_date = parse_date(request.form.get("due_date"))
    project.owner = request.form.get("owner", "").strip()
    project.description = request.form.get("description", "").strip()
    project.updated_at = datetime.utcnow()


def populate_project_step_from_form(step):
    step.title = request.form.get("title", "").strip()
    status = request.form.get("status", "a_faire").strip()
    step.status = status if status in PROJECT_STEP_STATUSES else "a_faire"
    step.sort_order = max(1, parse_int(request.form.get("sort_order"), 1))
    step.due_date = parse_date(request.form.get("due_date"))
    step.owner = request.form.get("owner", "").strip()
    step.notes = request.form.get("notes", "").strip()
    step.updated_at = datetime.utcnow()


def sync_project_from_steps(project):
    if not project.steps:
        project.progress = 0
        if project.status == "termine":
            project.status = "planifie"
        project.updated_at = datetime.utcnow()
        return

    total_steps = len(project.steps)
    completed_steps = sum(step.status == "terminee" for step in project.steps)
    in_progress_steps = sum(step.status == "en_cours" for step in project.steps)
    blocked_steps = sum(step.status == "bloquee" for step in project.steps)

    project.progress = round((completed_steps / total_steps) * 100)
    if completed_steps == total_steps:
        project.status = "termine"
    elif blocked_steps and not in_progress_steps:
        project.status = "bloque"
    elif in_progress_steps or completed_steps:
        project.status = "en_cours"
    else:
        project.status = "planifie"
    project.updated_at = datetime.utcnow()


# Cree un compte admin par defaut uniquement si la table users est vide.
def ensure_default_admin():
    if User.query.count() == 0:
        default_username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
        default_email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@local.dev")
        default_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")

        admin = User(
            username=default_username,
            email=default_email,
            role="administrateur",
            password=hash_password(default_password),
            email_verified_at=datetime.utcnow(),
        )
        db.session.add(admin)
        db.session.commit()


# Lie SQLAlchemy a l'application Flask.
db.init_app(app)

# Au demarrage: cree les tables puis initialise un admin si necessaire.
with app.app_context():
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    db.create_all()
    ensure_client_schema()
    ensure_user_schema()
    ensure_default_admin()


@app.route("/login", methods=["GET", "POST"])
def login():
    # Si deja connecte, inutile d'afficher le formulaire de connexion.
    if session.get("user_id"):
        return redirect(url_for("index"))

    # URL cible apres connexion (ex: page demandee initialement).
    next_url = request.args.get("next", "")

    if request.method == "POST":
        # Recuperation des identifiants saisis.
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        next_url = request.form.get("next_url", "")

        # Recherche d'un utilisateur par username ou email.
        user = User.query.filter(
            or_(User.username == username, User.email == username)
        ).first()

        if user and not user.email_verified_at:
            flash("Compte non active. Verifie ton email pour definir ton mot de passe.", "warning")
        elif user and verify_password(user.password, password):
            # Reinitialise la session puis stocke les infos utiles.
            if not is_password_hashed(user.password):
                user.password = hash_password(password)
                db.session.commit()
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            session["role"] = user.role
            flash("Connexion reussie.", "success")

            # Redirection vers la page demandee si elle est sure.
            if is_safe_next_url(next_url):
                return redirect(next_url)
            return redirect(url_for("index"))

        # Message d'erreur en cas d'echec d'authentification.
        flash("Identifiants invalides.", "danger")

    return render_template("login.html", next_url=next_url)


@app.route("/activate-account/<token>", methods=["GET", "POST"])
def activate_account(token):
    user = User.query.filter_by(invitation_token=token).first()
    if not user:
        flash("Lien d'activation invalide.", "danger")
        return redirect(url_for("login"))

    if user.email_verified_at:
        flash("Compte deja active. Connecte-toi.", "info")
        return redirect(url_for("login"))

    if invitation_is_expired(user):
        flash("Lien d'activation expire. Demande une nouvelle invitation.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Le mot de passe doit contenir au moins 8 caracteres.", "danger")
        elif password != confirm_password:
            flash("Les mots de passe ne correspondent pas.", "danger")
        else:
            user.password = hash_password(password)
            user.email_verified_at = datetime.utcnow()
            user.invitation_token = None
            db.session.commit()
            flash("Compte active. Tu peux maintenant te connecter.", "success")
            return redirect(url_for("login"))

    return render_template("activate_account.html", user=user, token=token)


@app.route("/logout", methods=["POST"])
def logout():
    # Supprime la session utilisateur courante.
    session.clear()
    flash("Vous etes deconnecte.", "info")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    # Charge les clients, indicateurs CRM et filtres de recherche.
    return render_template("index.html", **build_client_context())


@app.route("/projects")
@login_required
def projects_index():
    return render_template("projects.html", **build_project_context())


@app.route("/add", methods=["POST"])
@roles_required("administrateur", "commercial")
def add_client():
    # Construit puis persiste un nouveau contact CRM.
    new_client = Client()
    populate_client_from_form(new_client)

    db.session.add(new_client)
    db.session.commit()
    create_interaction(new_client, "note", "Contact cree", "Fiche client creee dans le CRM.")
    db.session.commit()
    flash("Contact CRM ajoute.", "success")

    return redirect("/")


@app.route("/delete/<int:id>", methods=["POST"])
@roles_required("administrateur", "commercial")
def delete_client(id):
    # Recherche le client par ID ou renvoie 404 s'il n'existe pas.
    client = Client.query.get_or_404(id)
    client_name = client.nom
    file_paths = [document.file_path for document in client.documents]

    # Supprime le client puis valide la transaction.
    db.session.delete(client)
    db.session.commit()

    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

    client_folder = Path(app.config["UPLOAD_FOLDER"]) / str(id)
    if client_folder.exists() and not any(client_folder.iterdir()):
        client_folder.rmdir()

    flash(f"Client supprime: {client_name}.", "success")
    return redirect("/")


@app.route("/edit/<int:id>")
@login_required
def edit(id):
    # Charge le client a modifier et affiche le formulaire pre-rempli.
    client = Client.query.get_or_404(id)
    return render_template(
        "edit.html",
        client=client,
        status_choices=CLIENT_STATUSES,
        source_choices=LEAD_SOURCES,
        interaction_types=INTERACTION_TYPES,
        project_status_choices=PROJECT_STATUSES,
        project_priority_choices=PROJECT_PRIORITIES,
        project_step_status_choices=PROJECT_STEP_STATUSES,
    )


@app.route("/update/<int:id>", methods=["POST"])
@roles_required("administrateur", "commercial")
def update_client(id):
    # Recherche du client cible.
    client = Client.query.get_or_404(id)

    # Mise a jour des champs depuis le formulaire.
    populate_client_from_form(client)
    create_interaction(client, "note", "Fiche mise a jour", "Les informations client ont ete modifiees.")

    db.session.commit()
    flash("Fiche client mise a jour.", "success")

    return redirect("/")


@app.route("/clients/<int:id>/documents/add", methods=["POST"])
@roles_required("administrateur", "commercial")
def add_client_document(id):
    client = Client.query.get_or_404(id)
    uploaded_file = request.files.get("document")
    description = request.form.get("description", "").strip()

    if not uploaded_file or not uploaded_file.filename:
        flash("Aucun document selectionne.", "danger")
        return redirect(url_for("edit", id=id))

    original_name = secure_filename(uploaded_file.filename)
    if not original_name or not allowed_document(original_name):
        flash("Type de document non autorise.", "danger")
        return redirect(url_for("edit", id=id))

    stored_name = f"{uuid.uuid4().hex}{Path(original_name).suffix.lower()}"
    client_folder = build_upload_folder(client.id)
    file_path = client_folder / stored_name
    uploaded_file.save(file_path)

    document = ClientDocument(
        client=client,
        original_name=original_name,
        stored_name=stored_name,
        file_path=str(file_path),
        content_type=uploaded_file.mimetype or "",
        description=description,
    )
    db.session.add(document)
    create_interaction(
        client,
        "note",
        "Document ajoute",
        f"Document depose: {original_name}" + (f" ({description})" if description else ""),
    )
    db.session.commit()
    flash("Document ajoute au dossier client.", "success")
    return redirect(url_for("edit", id=id))


@app.route("/clients/<int:client_id>/documents/<int:document_id>/update", methods=["POST"])
@roles_required("administrateur", "commercial")
def update_client_document(client_id, document_id):
    client = Client.query.get_or_404(client_id)
    document = ClientDocument.query.filter_by(id=document_id, client_id=client.id).first_or_404()
    description = request.form.get("description", "").strip()
    replacement_file = request.files.get("document")

    if replacement_file and replacement_file.filename:
        original_name = secure_filename(replacement_file.filename)
        if not original_name or not allowed_document(original_name):
            flash("Type de document non autorise.", "danger")
            return redirect(url_for("edit", id=client_id))

        old_file_path = document.file_path
        stored_name = f"{uuid.uuid4().hex}{Path(original_name).suffix.lower()}"
        client_folder = build_upload_folder(client.id)
        file_path = client_folder / stored_name
        replacement_file.save(file_path)

        document.original_name = original_name
        document.stored_name = stored_name
        document.file_path = str(file_path)
        document.content_type = replacement_file.mimetype or ""

        if old_file_path and os.path.exists(old_file_path):
            os.remove(old_file_path)

    document.description = description
    client.updated_at = datetime.utcnow()
    create_interaction(client, "note", "Document mis a jour", f"Document modifie: {document.original_name}")
    db.session.commit()
    flash("Document mis a jour.", "success")
    return redirect(url_for("edit", id=client_id))


@app.route("/clients/<int:id>/history/add", methods=["POST"])
@roles_required("administrateur", "commercial")
def add_client_history(id):
    client = Client.query.get_or_404(id)
    interaction_type = request.form.get("interaction_type", "note")
    summary = request.form.get("summary", "").strip()
    details = request.form.get("details", "").strip()

    if not summary:
        flash("Le resume de l'interaction est obligatoire.", "danger")
        return redirect(url_for("edit", id=id))

    create_interaction(client, interaction_type, summary, details)
    db.session.commit()
    flash("Interaction ajoutee a l'historique.", "success")
    return redirect(url_for("edit", id=id))


@app.route("/clients/<int:client_id>/history/<int:interaction_id>/update", methods=["POST"])
@roles_required("administrateur", "commercial")
def update_client_history(client_id, interaction_id):
    client = Client.query.get_or_404(client_id)
    interaction = ClientInteraction.query.filter_by(id=interaction_id, client_id=client.id).first_or_404()
    interaction_type = request.form.get("interaction_type", "note")
    summary = request.form.get("summary", "").strip()
    details = request.form.get("details", "").strip()

    if not summary:
        flash("Le resume de l'interaction est obligatoire.", "danger")
        return redirect(url_for("edit", id=client_id))

    interaction.interaction_type = interaction_type if interaction_type in INTERACTION_TYPES else "note"
    interaction.summary = summary
    interaction.details = details
    client.updated_at = datetime.utcnow()
    db.session.commit()
    flash("Interaction mise a jour.", "success")
    return redirect(url_for("edit", id=client_id))


@app.route("/clients/<int:client_id>/documents/<int:document_id>")
@login_required
def download_client_document(client_id, document_id):
    client = Client.query.get_or_404(client_id)
    document = ClientDocument.query.filter_by(id=document_id, client_id=client.id).first_or_404()
    directory = os.path.dirname(document.file_path)
    return send_from_directory(directory, document.stored_name, as_attachment=True, download_name=document.original_name)


@app.route("/clients/<int:id>/projects/add", methods=["POST"])
@roles_required("administrateur", "commercial")
def add_client_project(id):
    client = Client.query.get_or_404(id)
    project_name = request.form.get("name", "").strip()

    if not project_name:
        flash("Le nom du projet est obligatoire.", "danger")
        return redirect(url_for("edit", id=id))

    project = ClientProject(client=client)
    populate_project_from_form(project)
    db.session.add(project)
    create_interaction(
        client,
        "note",
        "Projet ajoute",
        f"Nouveau projet: {project.name} ({PROJECT_STATUSES.get(project.status, project.status)})",
    )
    db.session.commit()
    flash("Projet ajoute au client.", "success")
    return redirect(url_for("edit", id=id))


@app.route("/clients/<int:client_id>/projects/<int:project_id>/update", methods=["POST"])
@roles_required("administrateur", "commercial")
def update_client_project(client_id, project_id):
    client = Client.query.get_or_404(client_id)
    project = ClientProject.query.filter_by(id=project_id, client_id=client.id).first_or_404()
    project_name = request.form.get("name", "").strip()

    if not project_name:
        flash("Le nom du projet est obligatoire.", "danger")
        return redirect(url_for("edit", id=client_id))

    populate_project_from_form(project)
    sync_project_from_steps(project)
    create_interaction(
        client,
        "note",
        "Projet mis a jour",
        f"Projet {project.name}: {project.progress}% - {PROJECT_STATUSES.get(project.status, project.status)}",
    )
    db.session.commit()
    flash("Projet mis a jour.", "success")
    return redirect(url_for("edit", id=client_id))


@app.route("/clients/<int:client_id>/projects/<int:project_id>/steps/add", methods=["POST"])
@roles_required("administrateur", "commercial")
def add_project_step(client_id, project_id):
    client = Client.query.get_or_404(client_id)
    project = ClientProject.query.filter_by(id=project_id, client_id=client.id).first_or_404()
    title = request.form.get("title", "").strip()

    if not title:
        flash("Le nom de l'etape est obligatoire.", "danger")
        return redirect(url_for("edit", id=client_id))

    step = ClientProjectStep(project=project)
    populate_project_step_from_form(step)
    db.session.add(step)
    sync_project_from_steps(project)
    create_interaction(
        client,
        "note",
        "Etape projet ajoutee",
        f"Projet {project.name}: nouvelle etape {step.title}",
    )
    db.session.commit()
    flash(f"Etape ajoutee au projet {project.name}.", "success")
    return redirect(url_for("edit", id=client_id))


@app.route("/clients/<int:client_id>/projects/<int:project_id>/steps/<int:step_id>/update", methods=["POST"])
@roles_required("administrateur", "commercial")
def update_project_step(client_id, project_id, step_id):
    client = Client.query.get_or_404(client_id)
    project = ClientProject.query.filter_by(id=project_id, client_id=client.id).first_or_404()
    step = ClientProjectStep.query.filter_by(id=step_id, project_id=project.id).first_or_404()
    title = request.form.get("title", "").strip()

    if not title:
        flash("Le nom de l'etape est obligatoire.", "danger")
        return redirect(url_for("edit", id=client_id))

    populate_project_step_from_form(step)
    sync_project_from_steps(project)
    create_interaction(
        client,
        "note",
        "Etape projet mise a jour",
        f"Projet {project.name}: etape {step.title} ({PROJECT_STEP_STATUSES.get(step.status, step.status)})",
    )
    db.session.commit()
    flash(f"Etape mise a jour: {step.title}.", "success")
    return redirect(url_for("edit", id=client_id))


@app.route("/clients/<int:client_id>/projects/<int:project_id>/steps/<int:step_id>/delete", methods=["POST"])
@roles_required("administrateur", "commercial")
def delete_project_step(client_id, project_id, step_id):
    client = Client.query.get_or_404(client_id)
    project = ClientProject.query.filter_by(id=project_id, client_id=client.id).first_or_404()
    step = ClientProjectStep.query.filter_by(id=step_id, project_id=project.id).first_or_404()
    step_title = step.title

    db.session.delete(step)
    db.session.flush()
    sync_project_from_steps(project)
    create_interaction(
        client,
        "note",
        "Etape projet supprimee",
        f"Projet {project.name}: etape retiree {step_title}",
    )
    db.session.commit()
    flash(f"Etape supprimee: {step_title}.", "success")
    return redirect(url_for("edit", id=client_id))


@app.route("/users")
@roles_required("administrateur")
def users_index():
    # Affiche la liste des utilisateurs.
    users = User.query.all()
    return render_template("users.html", users=users, user_roles=USER_ROLES)


@app.route("/users/add", methods=["POST"])
@roles_required("administrateur")
def add_user():
    # Recupere les donnees du formulaire utilisateur.
    username = request.form["username"]
    email = request.form["email"]
    role = request.form.get("role", "consultant").strip()
    invitation_token = generate_invitation_token()

    # Cree puis enregistre un nouvel utilisateur en attente d'activation.
    new_user = User(
        username=username,
        email=email,
        role=role if role in USER_ROLES else "consultant",
        password=create_pending_password(),
        invitation_token=invitation_token,
        invitation_sent_at=datetime.utcnow(),
        email_verified_at=None,
    )

    db.session.add(new_user)
    db.session.commit()
    try:
        email_sent, activation_link = send_invitation_email(new_user)
        if email_sent:
            flash(f"Utilisateur cree: {new_user.username}. Invitation envoyee par email.", "success")
        else:
            flash(
                f"Utilisateur cree: {new_user.username}. SMTP non configure. Lien d'activation: {activation_link}",
                "warning",
            )
    except Exception:
        flash(f"Utilisateur cree: {new_user.username}, mais l'envoi de l'email a echoue.", "warning")

    return redirect("/users")


@app.route("/users/delete/<int:id>", methods=["POST"])
@roles_required("administrateur")
def delete_user(id):
    # Recherche l'utilisateur par ID ou renvoie 404.
    user = User.query.get_or_404(id)
    username = user.username

    # Suppression definitive de l'utilisateur.
    db.session.delete(user)
    db.session.commit()

    flash(f"Utilisateur supprime: {username}.", "success")
    return redirect("/users")


@app.route("/users/edit/<int:id>")
@roles_required("administrateur")
def edit_user(id):
    # Charge l'utilisateur et affiche la page d'edition.
    user = User.query.get_or_404(id)
    return render_template("edit_user.html", user=user, user_roles=USER_ROLES)


@app.route("/users/<int:id>/resend-invite", methods=["POST"])
@roles_required("administrateur")
def resend_user_invite(id):
    user = User.query.get_or_404(id)
    user.invitation_token = generate_invitation_token()
    user.invitation_sent_at = datetime.utcnow()
    user.email_verified_at = None
    user.password = create_pending_password()
    db.session.commit()

    try:
        email_sent, activation_link = send_invitation_email(user)
        if email_sent:
            flash("Invitation renvoyee.", "success")
        else:
            flash(f"SMTP non configure. Lien d'activation: {activation_link}", "warning")
    except Exception:
        flash("Invitation regeneree, mais l'envoi de l'email a echoue.", "warning")
    return redirect("/users")


@app.route("/users/update/<int:id>", methods=["POST"])
@roles_required("administrateur")
def update_user(id):
    # Recherche de l'utilisateur cible.
    user = User.query.get_or_404(id)

    # Applique les nouvelles valeurs issues du formulaire.
    user.username = request.form["username"]
    user.email = request.form["email"]
    role = request.form.get("role", user.role).strip()
    user.role = role if role in USER_ROLES else user.role

    db.session.commit()

    flash(f"Utilisateur mis a jour: {user.username}.", "success")
    return redirect("/users")


if __name__ == "__main__":
    # Parametres de lancement (compatibles local et Docker).
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
