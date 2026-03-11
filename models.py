from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

# Instance SQLAlchemy partagee dans toute l'application.
db = SQLAlchemy()


class Client(db.Model):
    # Nom de la table SQL associee au modele Client.
    __tablename__ = "clients"

    # Cle primaire auto-incrementee.
    id = db.Column(db.Integer, primary_key=True)
    # Nom du client.
    nom = db.Column(db.String(100), nullable=False)
    # Adresse email du client.
    email = db.Column(db.String(100), nullable=False)
    # Societe ou organisation rattachee au contact.
    entreprise = db.Column(db.String(120), nullable=False, default="")
    # Numero de telephone principal.
    telephone = db.Column(db.String(40), nullable=False, default="")
    # Etat commercial du contact dans le pipeline.
    statut = db.Column(db.String(30), nullable=False, default="prospect")
    # Canal d'acquisition du lead.
    source = db.Column(db.String(60), nullable=False, default="inconnu")
    # Montant commercial potentiel associe a ce client.
    valeur_potentielle = db.Column(db.Float, nullable=False, default=0)
    # Prochaine action commerciale prevue.
    prochaine_action = db.Column(db.String(160), nullable=False, default="")
    # Notes libres du commercial.
    notes = db.Column(db.String(2000), nullable=False, default="")
    # Horodatages utiles pour suivre l'activite.
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    # Documents associes a la fiche client.
    documents = db.relationship(
        "ClientDocument",
        backref="client",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="desc(ClientDocument.created_at)",
    )
    # Historique des interactions commerciales.
    interactions = db.relationship(
        "ClientInteraction",
        backref="client",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="desc(ClientInteraction.created_at)",
    )
    # Projets rattaches au client.
    projects = db.relationship(
        "ClientProject",
        backref="client",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="desc(ClientProject.updated_at)",
    )


class ClientDocument(db.Model):
    # Table des fichiers rattaches a un client.
    __tablename__ = "client_documents"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    file_path = db.Column(db.String(500), nullable=False)
    content_type = db.Column(db.String(120), nullable=False, default="")
    description = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())


class ClientInteraction(db.Model):
    # Historique de la relation client.
    __tablename__ = "client_interactions"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    interaction_type = db.Column(db.String(50), nullable=False, default="note")
    summary = db.Column(db.String(255), nullable=False)
    details = db.Column(db.String(2000), nullable=False, default="")
    created_by = db.Column(db.String(100), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())


class ClientProject(db.Model):
    # Projets commerciaux ou de delivery rattaches a un client.
    __tablename__ = "client_projects"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="planifie")
    priority = db.Column(db.String(20), nullable=False, default="moyenne")
    budget = db.Column(db.Float, nullable=False, default=0)
    progress = db.Column(db.Integer, nullable=False, default=0)
    due_date = db.Column(db.Date, nullable=True)
    owner = db.Column(db.String(100), nullable=False, default="")
    description = db.Column(db.String(2000), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, server_default=func.now())
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class User(db.Model):
    # Nom de la table SQL associee au modele User.
    __tablename__ = "users"

    # Cle primaire auto-incrementee.
    id = db.Column(db.Integer, primary_key=True)
    # Nom de connexion unique.
    username = db.Column(db.String(100), nullable=False, unique=True)
    # Email unique de l'utilisateur.
    email = db.Column(db.String(100), nullable=False, unique=True)
    # Role metier de l'utilisateur dans l'application.
    role = db.Column(db.String(30), nullable=False, default="administrateur")
    # Mot de passe hashé.
    password = db.Column(db.String(255), nullable=False)
    # Jeton d'invitation pour l'activation initiale du compte.
    invitation_token = db.Column(db.String(255), nullable=True, unique=True)
    # Date d'envoi de l'invitation.
    invitation_sent_at = db.Column(db.DateTime, nullable=True)
    # Date de verification de l'adresse email.
    email_verified_at = db.Column(db.DateTime, nullable=True)
