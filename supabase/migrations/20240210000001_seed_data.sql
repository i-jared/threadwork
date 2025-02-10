-- Insert test profiles
INSERT INTO public.profiles (id, username, avatar_url)
VALUES 
    ('123e4567-e89b-12d3-a456-426614174000', 'testuser1', 'https://example.com/avatar1.jpg'),
    ('223e4567-e89b-12d3-a456-426614174001', 'testuser2', 'https://example.com/avatar2.jpg')
ON CONFLICT (id) DO NOTHING;

-- Insert test projects
INSERT INTO public.projects (user_id, project_data)
VALUES 
    ('123e4567-e89b-12d3-a456-426614174000', 
     '{"name": "Test Project 1", "description": "A test project", "status": "completed"}'::jsonb),
    ('223e4567-e89b-12d3-a456-426614174001', 
     '{"name": "Test Project 2", "description": "Another test project", "status": "in_progress"}'::jsonb);

-- Insert test credits
INSERT INTO public.credits (user_id, credit_amount)
VALUES 
    ('123e4567-e89b-12d3-a456-426614174000', 100),
    ('223e4567-e89b-12d3-a456-426614174001', 50); 