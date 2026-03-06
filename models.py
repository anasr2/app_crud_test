from flask_sqlalchemy import SQLAlchemy

# Instance SQLAlchemy partagee dans toute l'application.
db = SQLAlchemy()


class Client(db.Model):
    # Nom de la table SQL associee au modele Client.
    __tablename__ = "clients"

    # Cle primaire auto-incrementee.
    id = db.Column(db.Integer, primary_key=True)
    # Nom du client.
    nom = db.Column(db.String(100))
    # Adresse email du client.
    email = db.Column(db.String(100))


class User(db.Model):
    # Nom de la table SQL associee au modele User.
    __tablename__ = "users"

    # Cle primaire auto-incrementee.
    id = db.Column(db.Integer, primary_key=True)
    # Nom de connexion unique.
    username = db.Column(db.String(100), nullable=False, unique=True)
    # Email unique de l'utilisateur.
    email = db.Column(db.String(100), nullable=False, unique=True)
    # Mot de passe (actuellement stocke en clair, a hasher en production).
    password = db.Column(db.String(255), nullable=False)
