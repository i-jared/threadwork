
export default function LoginPage() {
  // Placeholder for Supabase auth integration with supabase-js
  // TODO: Set up auth.uid() storage in Supabase records
  // TODO: Create minimafl login form and add registration option

  return (
    <div>
      <h1>Login / Register</h1>
      <form>
        <input type="email" placeholder="Email" />
        <input type="password" placeholder="Password" />
        <button type="submit">Login</button>
      </form>
      <p>Don't have an account? Register here.</p>
    </div>
  );
} 