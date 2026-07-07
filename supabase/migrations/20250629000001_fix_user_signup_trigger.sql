-- Fix: "Database error creating new user"
-- Run this in Supabase SQL Editor, then create your user again.

-- 1. Remove the broken trigger (temporarily stops auto-profile creation)
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP FUNCTION IF EXISTS public.handle_new_user();

-- 2. Recreate with Supabase-safe settings (search_path + grants)
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (id, email)
  VALUES (NEW.id, COALESCE(NEW.email, NEW.raw_user_meta_data->>'email', ''))
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.watchlists (user_id, name)
  SELECT NEW.id, 'Default'
  WHERE NOT EXISTS (
    SELECT 1 FROM public.watchlists WHERE user_id = NEW.id AND name = 'Default'
  );

  RETURN NEW;
END;
$$;

-- 3. Permissions Supabase auth needs to run the trigger
GRANT USAGE ON SCHEMA public TO supabase_auth_admin;
GRANT ALL ON TABLE public.profiles TO supabase_auth_admin;
GRANT ALL ON TABLE public.watchlists TO supabase_auth_admin;
GRANT EXECUTE ON FUNCTION public.handle_new_user() TO supabase_auth_admin;

-- 4. Reattach trigger
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user();
