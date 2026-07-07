-- Ensure the owner account has a profiles row (signup trigger may have failed).
INSERT INTO profiles (id, email)
VALUES ('1b6032f9-f831-49f8-a865-55d5354b8849', 'brandon.corley01@gmail.com')
ON CONFLICT (id) DO NOTHING;

-- Allow users to self-heal missing profile rows.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public' AND tablename = 'profiles' AND policyname = 'profiles_insert_own'
  ) THEN
    CREATE POLICY "profiles_insert_own" ON profiles
      FOR INSERT
      WITH CHECK (id = auth.uid());
  END IF;
END $$;
