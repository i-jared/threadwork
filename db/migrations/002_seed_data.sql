-- Seed file: Insert test data

-- Insert test profiles if they don't exist
INSERT INTO public.profiles (id, username, avatar_url, created_at)
VALUES 
    ('123e4567-e89b-12d3-a456-426614174000', 'testuser1', 'https://example.com/avatar1.jpg', NOW()),
    ('223e4567-e89b-12d3-a456-426614174001', 'testuser2', 'https://example.com/avatar2.jpg', NOW())
ON CONFLICT (id) DO NOTHING;

-- Insert test projects if they don't exist
INSERT INTO public.projects (user_id, project_data, created_at)
VALUES 
    ('123e4567-e89b-12d3-a456-426614174000', 
     '{"name": "Test Project 1", "description": "A test project", "status": "completed"}', 
     NOW()),
    ('223e4567-e89b-12d3-a456-426614174001', 
     '{"name": "Test Project 2", "description": "Another test project", "status": "in_progress"}', 
     NOW())
ON CONFLICT (id) DO NOTHING;

-- Insert test credits if they don't exist
WITH new_credits AS (
    SELECT * FROM (VALUES
        ('123e4567-e89b-12d3-a456-426614174000'::uuid, 100),
        ('223e4567-e89b-12d3-a456-426614174001'::uuid, 50)
    ) AS t(user_id, credit_amount)
)
INSERT INTO public.credits (user_id, credit_amount)
SELECT user_id, credit_amount FROM new_credits
WHERE NOT EXISTS (
    SELECT 1 FROM public.credits c
    WHERE c.user_id = new_credits.user_id
); 