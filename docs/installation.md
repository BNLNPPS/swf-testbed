# Installation Guide

Complete setup instructions for the SWF Testbed.

## Prerequisites

Before starting, ensure you have:

- **Python 3.8+** with pip
- **Docker Desktop** (for infrastructure services)
- **Git** for repository management
- **Administrative access** (for some package installations)

## Step 1: Clone the Repositories

Clone all three SWF repositories as siblings in the same parent directory:

```bash
# Create a directory for the SWF project
mkdir swf-project && cd swf-project

# Clone all repositories
git clone https://github.com/BNLNPPS/swf-testbed.git
git clone https://github.com/BNLNPPS/swf-monitor.git
git clone https://github.com/BNLNPPS/swf-common-lib.git

# Your directory structure should now look like:
# swf-project/
# ├── swf-testbed/
# ├── swf-monitor/
# └── swf-common-lib/
```

## Step 2: Environment Configuration

**IMPORTANT FOR BNL/pandaserver02 DEPLOYMENT:**
For deployments on systems with corporate proxies (like BNL pandaserver02), add this to your `~/.env` file:

```bash
NO_PROXY=localhost,127.0.0.1,0.0.0.0
```

This prevents proxy interference with local service communications (Django, ActiveMQ, PostgreSQL, WebSocket connections). Other deployment environments may have different proxy requirements.

## Step 3: Set Up Infrastructure Services

Choose one of the following approaches:

### Option A: Using Docker (Recommended)

1. **Install Docker Desktop** and ensure it's running
2. **Navigate to swf-testbed:**
   ```bash
   cd swf-testbed
   ```
3. **Start services:**
   ```bash
   docker-compose up -d
   ```

### Option B: Local Installation (macOS with Homebrew)

1. **Install PostgreSQL and ActiveMQ:**
   ```bash
   brew install postgresql@14 activemq
   ```

2. **Start services:**
   ```bash
   brew services start postgresql@14
   brew services start activemq
   ```

3. **Create database:**
   ```bash
   createdb swfdb
   ```

## Step 4: Configure Environment Variables

### Core Infrastructure Configuration

The testbed requires environment variables for service coordination. Create/edit `~/.env`:

```bash
# Export all variables to make them available to subprocesses
export NO_PROXY=localhost,127.0.0.1,0.0.0.0
export no_proxy=localhost,127.0.0.1,0.0.0.0

# Database configuration (PostgreSQL)
export DB_NAME='swfdb'
export DB_USER='wenaus'
export DB_PASSWORD='swf123_wenaus'
export DB_HOST='localhost'
export DB_PORT='5432'

# ActiveMQ configuration
export ACTIVEMQ_HOST='pandaserver02.sdcc.bnl.gov'
export ACTIVEMQ_PORT=61612
export ACTIVEMQ_USER='wenauseic'
export ACTIVEMQ_PASSWORD='swf123_wenauseic'
export ACTIVEMQ_HEARTBEAT_TOPIC='epictopic'
export ACTIVEMQ_USE_SSL=True
export ACTIVEMQ_SSL_CA_CERTS='/eic/u/wenauseic/github/swf-monitor/full-chain.pem'

# Monitor URLs
export SWF_MONITOR_URL=https://localhost:8443      # Authenticated API calls
export SWF_MONITOR_HTTP_URL=http://localhost:8002  # REST logging (no auth)

# API Authentication
export SWF_API_TOKEN=your_token_here

# Django configuration
export SECRET_KEY='django-insecure-dev-key-for-testing-only-change-for-production'
export DEBUG=True

# Unset proxy variables for localhost connections
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
```

### swf-monitor Configuration

2. **Configure swf-monitor secrets:**
   ```bash
   cd ../swf-monitor
   cp .env.example .env
   ```

   Edit the `.env` file with your database credentials:
   ```env
   export DB_PASSWORD='admin'  # Match your Docker/local PostgreSQL password
   export SECRET_KEY='django-insecure-dev-key-for-testing-only-change-for-production-12345678901234567890'
   ```

## Step 5: Set Up Python Environment and Install Dependencies

You can either use **uv** or plain **pip** to set up the Python environment.

### Using `uv`

The following commands will create a virtual environment in `.venv` (if needed) and install
`swf-testbed` and all of its dependencies:

```bash
cd ../swf-testbed
uv sync
source .venv/bin/activate
```

### Using `pip`

1. **Navigate to swf-testbed and create virtual environment:**
   ```bash
   cd ../swf-testbed
   python -m venv .venv
   source .venv/bin/activate
   ```

2. **Install all packages in development mode:**
   ```bash
   # Install swf-common-lib (shared utilities)
   pip install -e ../swf-common-lib

   # Install swf-monitor (Django web application)
   pip install -e ../swf-monitor

   # Install swf-testbed CLI
   pip install -e .
   ```

## Step 6: Initialize and Run the Testbed

1. **Initialize the testbed:**
   ```bash
   swf-testbed init
   ```

2. **Set up Django database:**
   ```bash
   # Run Django migrations and create superuser
   python ../swf-monitor/src/manage.py migrate
   python ../swf-monitor/src/manage.py createsuperuser
   ```

3. **Load sample data (optional):**
   ```bash
   # Load fake log data to populate the monitoring interface
   python ../swf-monitor/scripts/load_fake_logs.py
   ```

4. **Start the monitor web interface:**
   ```bash
   # Start Django monitor with dual HTTP/HTTPS support
   ../swf-monitor/start_django_dual.sh
   ```
   
   This starts the monitor on:
   - **HTTP (port 8002)**: For REST logging from agents (no authentication)
   - **HTTPS (port 8443)**: For authenticated API calls (STF files, workflows, runs)

5. **Start the testbed agents:**
   ```bash
   # If using Docker:
   swf-testbed start

   # If using local services:
   swf-testbed start-local
   ```

6. **Check status:**
   ```bash
   swf-testbed status  # or status-local
   ```

## Step 7: Verify Setup

1. **Check web interfaces:**
   - **Monitor dashboard**: http://localhost:8002/ (main interface)
   - **Monitor HTTPS API**: https://localhost:8443/api/ (authenticated API)
   - **Django admin**: http://localhost:8002/admin/ (use superuser credentials created in Step 5)
   - **ActiveMQ console**: http://localhost:8161/admin/ (admin/admin)

2. **Run tests:**
   ```bash
   # Run all tests across all repositories
   ./run_all_tests.sh

   # Or run tests for individual components
   cd swf-monitor && ./run_tests.sh
   ```

## Secrets and Configuration Management

The testbed uses a hierarchical configuration approach:

- **Core infrastructure**: Environment variables in `~/.env` (required - database, messaging, proxy settings)
- **swf-monitor**: Django application secrets in `swf-monitor/.env` (required - core infrastructure)
- **swf-data-agent**: Agent configuration in `swf-data-agent/.env` (if present)
- **swf-processing-agent**: PanDA credentials in `swf-processing-agent/.env` (if present)

### Setting Up swf-monitor Environment Variables

The Django monitoring application requires database and messaging credentials.
To configure:

1. **Copy the environment template:**
   ```bash
   cp swf-monitor/.env.example swf-monitor/.env
   ```

2. **Edit the `.env` file** with your actual credentials:
   - Set `DB_PASSWORD` to match your PostgreSQL setup
   - Generate a unique `SECRET_KEY` for Django
   - Configure messaging credentials if using external ActiveMQ

3. **Load environment:**
   ```bash
   source swf-monitor/.env
   ```

The Django application will automatically read these values during startup.

### Security Considerations

**For Development:**
- Use the provided development secrets and database passwords
- The `.env.example` files contain safe defaults for local testing

**For Production:**
- Generate secure, unique passwords for all services
- Use proper SSL certificates (not self-signed)
- Set `DEBUG=False` in Django configuration
- Configure proper `ALLOWED_HOSTS` for Django
- Use environment-specific configuration management

**Secret Storage:**
- Never commit actual secrets to version control
- Use `.env` files (which are `.gitignore`d) for local development
- Consider using dedicated secret management for production deployments

## Troubleshooting Installation

### Common Issues

1. **Docker services not starting:**
   ```bash
   docker-compose ps
   docker-compose logs postgresql
   docker-compose logs activemq
   ```

2. **Virtual environment issues:**
   ```bash
   # Ensure you're in the right directory and venv is activated
   cd swf-testbed
   source .venv/bin/activate
   which python  # Should show .venv/bin/python
   ```

3. **Proxy connection issues:**
   - Ensure `NO_PROXY` is set in `~/.env`
   - Check that proxy variables are unset for localhost

4. **Database connection errors:**
   - Check database credentials in `.env` files

5. **Import errors:**
   ```bash
   # Reinstall packages in correct order
   pip install -e ../swf-common-lib ../swf-monitor .
   ```

For more troubleshooting help, see [Troubleshooting Guide](troubleshooting.md).

## Next Steps

After successful installation:
- Review [Architecture Overview](architecture.md) to understand the system
- See [Operations Guide](operations.md) for running and managing services
- Check [Development Guide](development.md) for contributing to the project
