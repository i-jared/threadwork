-- Migration file: 001_create_tables.sql

-- Create necessary roles and schemas
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_admin') THEN
        CREATE ROLE supabase_admin;
        -- Only grant superuser if it doesn't have it
        IF NOT EXISTS (
            SELECT FROM pg_roles 
            WHERE rolname = 'supabase_admin' 
            AND rolsuper = true
        ) THEN
            ALTER ROLE supabase_admin WITH SUPERUSER;
        END IF;
    END IF;
END
$$;

-- Create schemas if they don't exist
CREATE SCHEMA IF NOT EXISTS auth AUTHORIZATION supabase_admin;
CREATE SCHEMA IF NOT EXISTS extensions;

-- Grant usage on extensions schema if not already granted
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT FROM information_schema.role_usage_grants 
        WHERE grantee = 'public' 
        AND object_schema = 'extensions'
    ) THEN
        GRANT USAGE ON SCHEMA extensions TO PUBLIC;
    END IF;
END
$$;

GRANT ALL ON SCHEMA extensions TO postgres, supabase_admin;

-- Ensure the uuid-ossp extension is available for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" SCHEMA extensions;

-- Create profiles table associated with auth users
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY DEFAULT extensions.uuid_generate_v4(),  -- Primary key with auto-generated UUID
    username TEXT,
    avatar_url TEXT,
    created_at TIMESTAMP DEFAULT NOW()  -- Record creation timestamp
);

-- Create projects table linked to profiles using UUID for user_id
CREATE TABLE IF NOT EXISTS public.projects (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,  -- Foreign key to profiles table
    project_data JSONB,  -- Project details stored in JSON format
    created_at TIMESTAMP DEFAULT NOW()  -- Record creation timestamp
);

-- Create credits table to track user credits, linked to profiles using UUID for user_id
CREATE TABLE IF NOT EXISTS public.credits (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,  -- Foreign key to profiles table
    credit_amount INTEGER DEFAULT 0,  -- Current credit balance
    updated_at TIMESTAMP DEFAULT NOW()  -- Last update timestamp
); 