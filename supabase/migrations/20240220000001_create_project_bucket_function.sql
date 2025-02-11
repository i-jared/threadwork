-- Enable required extensions if not already enabled
create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";

-- Drop existing function if it exists (useful for updates)
drop function if exists create_project_bucket(text);

-- Create function to generate and setup project buckets
create or replace function create_project_bucket(project_id text)
returns table (bucket_name text) -- Return as table for Supabase RPC compatibility
language plpgsql
security definer -- Run with elevated privileges
set search_path = public -- Security best practice
as $$
declare
    new_bucket_name text;
begin
    -- Generate a unique bucket name using project_id and random hash
    new_bucket_name := 'project-' || project_id || '-' || encode(sha256(random()::text::bytea), 'hex');
    
    -- Create the bucket if it doesn't exist
    insert into storage.buckets (id, name, public)
    values (new_bucket_name, new_bucket_name, true)
    on conflict (id) do nothing;
    
    -- Drop existing policies if they exist (for idempotency)
    execute format('drop policy if exists "Public Downloads for %I" on storage.objects', new_bucket_name);
    execute format('drop policy if exists "Authenticated Uploads for %I" on storage.objects', new_bucket_name);
    
    -- Create public download policy for the bucket
    execute format($policy$
        create policy "Public Downloads for %I"
        on storage.objects for select
        to public
        using ( bucket_id = '%I' );
    $policy$, new_bucket_name, new_bucket_name);
    
    -- Create upload policy for authenticated users
    execute format($policy$
        create policy "Authenticated Uploads for %I"
        on storage.objects for insert
        to authenticated
        with check ( bucket_id = '%I' );
    $policy$, new_bucket_name, new_bucket_name);
    
    -- Return the bucket name
    return query select new_bucket_name as bucket_name;
end;
$$;

-- Grant execute permission to authenticated users
grant execute on function create_project_bucket(text) to authenticated;

-- Add comment explaining the function
comment on function create_project_bucket(text) is 
'Creates a unique storage bucket for a project and sets up appropriate access policies.
The bucket name is generated using the project ID and a random hash.
Returns the bucket name for use in storage operations.'; 