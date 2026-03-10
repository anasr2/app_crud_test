/*
  Migration SQL Server pour transformer la table clients en table CRM.
  Date: 2026-03-10
  Contexte: application Flask de c:\Users\anasr\Desktop\app_web_python

  Changements:
  - Ajout des colonnes CRM sur dbo.clients
  - Initialisation des horodatages existants
  - Creation des tables dbo.client_documents et dbo.client_interactions
  - Creation de la table dbo.client_projects
*/

BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.clients', N'U') IS NULL
BEGIN
    RAISERROR('La table dbo.clients est introuvable.', 16, 1);
    ROLLBACK TRANSACTION;
    RETURN;
END;

IF COL_LENGTH('dbo.clients', 'entreprise') IS NULL
BEGIN
    ALTER TABLE dbo.clients
    ADD entreprise VARCHAR(120) NOT NULL
        CONSTRAINT DF_clients_entreprise DEFAULT '';
END;

IF COL_LENGTH('dbo.clients', 'telephone') IS NULL
BEGIN
    ALTER TABLE dbo.clients
    ADD telephone VARCHAR(40) NOT NULL
        CONSTRAINT DF_clients_telephone DEFAULT '';
END;

IF COL_LENGTH('dbo.clients', 'statut') IS NULL
BEGIN
    ALTER TABLE dbo.clients
    ADD statut VARCHAR(30) NOT NULL
        CONSTRAINT DF_clients_statut DEFAULT 'prospect';
END;

IF COL_LENGTH('dbo.clients', 'source') IS NULL
BEGIN
    ALTER TABLE dbo.clients
    ADD source VARCHAR(60) NOT NULL
        CONSTRAINT DF_clients_source DEFAULT 'inconnu';
END;

IF COL_LENGTH('dbo.clients', 'valeur_potentielle') IS NULL
BEGIN
    ALTER TABLE dbo.clients
    ADD valeur_potentielle FLOAT NOT NULL
        CONSTRAINT DF_clients_valeur_potentielle DEFAULT 0;
END;

IF COL_LENGTH('dbo.clients', 'prochaine_action') IS NULL
BEGIN
    ALTER TABLE dbo.clients
    ADD prochaine_action VARCHAR(160) NOT NULL
        CONSTRAINT DF_clients_prochaine_action DEFAULT '';
END;

IF COL_LENGTH('dbo.clients', 'notes') IS NULL
BEGIN
    ALTER TABLE dbo.clients
    ADD notes VARCHAR(2000) NOT NULL
        CONSTRAINT DF_clients_notes DEFAULT '';
END;

IF COL_LENGTH('dbo.clients', 'created_at') IS NULL
BEGIN
    ALTER TABLE dbo.clients
    ADD created_at DATETIME NULL;
END;

IF COL_LENGTH('dbo.clients', 'updated_at') IS NULL
BEGIN
    ALTER TABLE dbo.clients
    ADD updated_at DATETIME NULL;
END;

EXEC sp_executesql N'
    UPDATE dbo.clients
    SET
        created_at = ISNULL(created_at, GETDATE()),
        updated_at = ISNULL(updated_at, GETDATE())
    WHERE created_at IS NULL
       OR updated_at IS NULL;
';

IF EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.clients')
      AND name = 'created_at'
      AND is_nullable = 1
)
BEGIN
    EXEC sp_executesql N'
        ALTER TABLE dbo.clients
        ALTER COLUMN created_at DATETIME NOT NULL;
    ';
END;

IF EXISTS (
    SELECT 1
    FROM sys.columns
    WHERE object_id = OBJECT_ID(N'dbo.clients')
      AND name = 'updated_at'
      AND is_nullable = 1
)
BEGIN
    EXEC sp_executesql N'
        ALTER TABLE dbo.clients
        ALTER COLUMN updated_at DATETIME NOT NULL;
    ';
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.clients')
      AND name = 'DF_clients_created_at'
)
BEGIN
    ALTER TABLE dbo.clients
    ADD CONSTRAINT DF_clients_created_at DEFAULT GETDATE() FOR created_at;
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.clients')
      AND name = 'DF_clients_updated_at'
)
BEGIN
    ALTER TABLE dbo.clients
    ADD CONSTRAINT DF_clients_updated_at DEFAULT GETDATE() FOR updated_at;
END;

IF OBJECT_ID(N'dbo.client_documents', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.client_documents (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        client_id INT NOT NULL,
        original_name VARCHAR(255) NOT NULL,
        stored_name VARCHAR(255) NOT NULL,
        file_path VARCHAR(500) NOT NULL,
        content_type VARCHAR(120) NOT NULL CONSTRAINT DF_client_documents_content_type DEFAULT '',
        description VARCHAR(255) NOT NULL CONSTRAINT DF_client_documents_description DEFAULT '',
        created_at DATETIME NOT NULL CONSTRAINT DF_client_documents_created_at DEFAULT GETDATE(),
        CONSTRAINT UQ_client_documents_stored_name UNIQUE (stored_name),
        CONSTRAINT FK_client_documents_clients FOREIGN KEY (client_id) REFERENCES dbo.clients(id) ON DELETE CASCADE
    );
END;

IF OBJECT_ID(N'dbo.client_interactions', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.client_interactions (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        client_id INT NOT NULL,
        interaction_type VARCHAR(50) NOT NULL CONSTRAINT DF_client_interactions_type DEFAULT 'note',
        summary VARCHAR(255) NOT NULL,
        details VARCHAR(2000) NOT NULL CONSTRAINT DF_client_interactions_details DEFAULT '',
        created_by VARCHAR(100) NOT NULL CONSTRAINT DF_client_interactions_created_by DEFAULT '',
        created_at DATETIME NOT NULL CONSTRAINT DF_client_interactions_created_at DEFAULT GETDATE(),
        CONSTRAINT FK_client_interactions_clients FOREIGN KEY (client_id) REFERENCES dbo.clients(id) ON DELETE CASCADE
    );
END;

IF OBJECT_ID(N'dbo.client_projects', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.client_projects (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        client_id INT NOT NULL,
        name VARCHAR(160) NOT NULL,
        status VARCHAR(30) NOT NULL CONSTRAINT DF_client_projects_status DEFAULT 'planifie',
        priority VARCHAR(20) NOT NULL CONSTRAINT DF_client_projects_priority DEFAULT 'moyenne',
        budget FLOAT NOT NULL CONSTRAINT DF_client_projects_budget DEFAULT 0,
        progress INT NOT NULL CONSTRAINT DF_client_projects_progress DEFAULT 0,
        due_date DATE NULL,
        owner VARCHAR(100) NOT NULL CONSTRAINT DF_client_projects_owner DEFAULT '',
        description VARCHAR(2000) NOT NULL CONSTRAINT DF_client_projects_description DEFAULT '',
        created_at DATETIME NOT NULL CONSTRAINT DF_client_projects_created_at DEFAULT GETDATE(),
        updated_at DATETIME NOT NULL CONSTRAINT DF_client_projects_updated_at DEFAULT GETDATE(),
        CONSTRAINT FK_client_projects_clients FOREIGN KEY (client_id) REFERENCES dbo.clients(id) ON DELETE CASCADE
    );
END;

COMMIT TRANSACTION;
