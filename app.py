import os
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for

from models import db, Client, User

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


# Decorateur de protection: force la connexion avant d'acceder aux pages privees.
def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        # Si aucun utilisateur en session, redirection vers la page login.
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)

    return wrapped_view


# Verifie que l'URL de redirection reste interne a l'application.
def is_safe_next_url(target):
    return bool(target) and target.startswith("/") and not target.startswith("//")


# Cree un compte admin par defaut uniquement si la table users est vide.
def ensure_default_admin():
    if User.query.count() == 0:
        default_username = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
        default_email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@local.dev")
        default_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")

        admin = User(
            username=default_username,
            email=default_email,
            password=default_password,
        )
        db.session.add(admin)
        db.session.commit()


# Lie SQLAlchemy a l'application Flask.
db.init_app(app)

# Au demarrage: cree les tables puis initialise un admin si necessaire.
with app.app_context():
    db.create_all()
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

        # Recherche d'un utilisateur correspondant (version actuelle: mot de passe en clair).
        user = User.query.filter_by(username=username, password=password).first()

        if user:
            # Reinitialise la session puis stocke les infos utiles.
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            flash("Connexion reussie.", "success")

            # Redirection vers la page demandee si elle est sure.
            if is_safe_next_url(next_url):
                return redirect(next_url)
            return redirect(url_for("index"))

        # Message d'erreur en cas d'echec d'authentification.
        flash("Identifiants invalides.", "danger")

    return render_template("login.html", next_url=next_url)


@app.route("/logout", methods=["POST"])
def logout():
    # Supprime la session utilisateur courante.
    session.clear()
    flash("Vous etes deconnecte.", "info")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    # Charge et affiche la liste complete des clients.
    clients = Client.query.all()
    return render_template("index.html", clients=clients)


@app.route("/add", methods=["POST"])
@login_required
def add_client():
    # Recupere les donnees du formulaire client.
    nom = request.form["nom"]
    email = request.form["email"]

    # Construit puis persiste un nouveau client.
    new_client = Client(nom=nom, email=email)

    db.session.add(new_client)
    db.session.commit()

    return redirect("/")


@app.route("/delete/<int:id>")
@login_required
def delete_client(id):
    # Recherche le client par ID ou renvoie 404 s'il n'existe pas.
    client = Client.query.get_or_404(id)

    # Supprime le client puis valide la transaction.
    db.session.delete(client)
    db.session.commit()

    return redirect("/")


@app.route("/edit/<int:id>")
@login_required
def edit(id):
    # Charge le client a modifier et affiche le formulaire pre-rempli.
    client = Client.query.get_or_404(id)
    return render_template("edit.html", client=client)


@app.route("/update/<int:id>", methods=["POST"])
@login_required
def update_client(id):
    # Recherche du client cible.
    client = Client.query.get_or_404(id)

    # Mise a jour des champs depuis le formulaire.
    client.nom = request.form["nom"]
    client.email = request.form["email"]

    db.session.commit()

    return redirect("/")


@app.route("/users")
@login_required
def users_index():
    # Affiche la liste des utilisateurs.
    users = User.query.all()
    return render_template("users.html", users=users)


@app.route("/users/add", methods=["POST"])
@login_required
def add_user():
    # Recupere les donnees du formulaire utilisateur.
    username = request.form["username"]
    email = request.form["email"]
    password = request.form["password"]

    # Cree puis enregistre un nouvel utilisateur.
    new_user = User(username=username, email=email, password=password)

    db.session.add(new_user)
    db.session.commit()

    return redirect("/users")


@app.route("/users/delete/<int:id>")
@login_required
def delete_user(id):
    # Recherche l'utilisateur par ID ou renvoie 404.
    user = User.query.get_or_404(id)

    # Suppression definitive de l'utilisateur.
    db.session.delete(user)
    db.session.commit()

    return redirect("/users")


@app.route("/users/edit/<int:id>")
@login_required
def edit_user(id):
    # Charge l'utilisateur et affiche la page d'edition.
    user = User.query.get_or_404(id)
    return render_template("edit_user.html", user=user)


@app.route("/users/update/<int:id>", methods=["POST"])
@login_required
def update_user(id):
    # Recherche de l'utilisateur cible.
    user = User.query.get_or_404(id)

    # Applique les nouvelles valeurs issues du formulaire.
    user.username = request.form["username"]
    user.email = request.form["email"]
    user.password = request.form["password"]

    db.session.commit()

    return redirect("/users")


if __name__ == "__main__":
    # Parametres de lancement (compatibles local et Docker).
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
