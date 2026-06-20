# Database Administration Scripts

Shell scripts for managing users and organisations in the bordereaux-validation database.

## Prerequisites

- Python 3.10+ with dependencies installed (`pip install -r backend/requirements.txt`)
- Database connection configured via `DATABASE_URL` environment variable or `.env` file
- Virtual environment activated (scripts will try to auto-activate from `.venv/`)

## Organisation Management

```bash
# List all organisations
./manage_orgs.sh list

# Filter organisations by name
./manage_orgs.sh list --filter "Acme"

# Get organisation details by ID
./manage_orgs.sh get --id 1

# Get organisation details by name
./manage_orgs.sh get --name "Acme Corp"

# Create a new organisation
./manage_orgs.sh create --name "New Organisation"

# Update organisation name
./manage_orgs.sh update --id 1 --name "Updated Name"

# Delete organisation (will fail if users exist)
./manage_orgs.sh delete --id 1

# Force delete organisation
./manage_orgs.sh delete --id 1 --force
```

## User Management

```bash
# List all users
./manage_users.sh list

# List users with filters
./manage_users.sh list --org-id 1
./manage_users.sh list --tier bordereaux
./manage_users.sh list --active
./manage_users.sh list --inactive

# Get user details
./manage_users.sh get --id 1
./manage_users.sh get --email "user@example.com"
./manage_users.sh get --excel-user-id "excel_abc123"

# Create a new user (generates API key)
./manage_users.sh create --email "new@example.com" --org-id 1

# Create user with all options
./manage_users.sh create \
  --email "new@example.com" \
  --org-id 1 \
  --display-name "John Doe" \
  --tier developer

# Update user
./manage_users.sh update --id 1 --tier developer
./manage_users.sh update --id 1 --email "newemail@example.com"
./manage_users.sh update --id 1 --active false

# Activate/deactivate user (soft delete)
./manage_users.sh activate --id 1
./manage_users.sh deactivate --id 1

# Delete user (hard delete)
./manage_users.sh delete --id 1
./manage_users.sh delete --id 1 --force

# Regenerate API key for user
./manage_users.sh regenerate-key --id 1
```

## Subscription Tiers

Available subscription tiers:
- `bordereaux` - Standard tier with basic features
- `developer` - Developer tier with extended capabilities
- `trial` - Legacy tier (mapped to bordereaux)

## Environment Configuration

The scripts use the same database configuration as the backend application:

```bash
# Option 1: Set DATABASE_URL environment variable
export DATABASE_URL="postgresql://user:pass@localhost:5432/bordereaux"

# Option 2: Create backend/.env file
DATABASE_URL=postgresql://user:pass@localhost:5432/bordereaux
```

## Direct Python Usage

You can also use the Python module directly:

```bash
# Organisation commands
python scripts/db-admin/db_admin.py org list
python scripts/db-admin/db_admin.py org create --name "Test Org"

# User commands
python scripts/db-admin/db_admin.py user list
python scripts/db-admin/db_admin.py user create --email "test@example.com" --org-id 1
```

## Notes

- API keys are displayed only once when created or regenerated. Store them securely.
- Deleting an organisation with existing users will fail unless `--force` is used.
- The `deactivate` command performs a soft delete (sets `is_active=false`).
- The `delete` command performs a hard delete (removes the record).
