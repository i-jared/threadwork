from supabase import create_client, Client
import os
from typing import Optional

class SupabaseClient:
    _instance: Optional['SupabaseClient'] = None
    _client: Optional[Client] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._client is None:
            url = os.getenv('SUPABASE_URL')
            key = os.getenv('SUPABASE_SERVICE_KEY')

            if not url or not key:
                raise ValueError('Missing Supabase URL or Service Key in environment variables.')

            self._client = create_client(url, key)

    @property
    def client(self) -> Client:
        """Get the Supabase client instance."""
        if not self._client:
            raise RuntimeError("Supabase client not initialized")
        return self._client

# Create a singleton instance
supabase = SupabaseClient().client

# Example usage:
# Get all profiles
# data = supabase.table('profiles').select("*").execute()
#
# Insert a new project
# data = supabase.table('projects').insert({"user_id": "123", "project_data": {...}}).execute()
#
# Check credits
# data = supabase.table('credits').select("credit_amount").eq("user_id", "123").execute() 