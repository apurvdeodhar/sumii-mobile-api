-- PostgreSQL initialization script
-- Creates test database for pytest
-- This script runs automatically when PostgreSQL container starts for the first time
-- Location: /docker-entrypoint-initdb.d/init-test-db.sql

-- Create test database if it doesn't exist
SELECT 'CREATE DATABASE sumii_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sumii_test')\gexec

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE sumii_test TO postgres;
