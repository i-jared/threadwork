ALTER TABLE credits ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own credits"
ON credits FOR SELECT
TO authenticated
USING (auth.uid() = user_id);