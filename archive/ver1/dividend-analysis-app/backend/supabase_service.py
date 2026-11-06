from supabase import create_client, Client
from dotenv import load_dotenv
import os
from typing import Tuple, Optional, Dict, Any
from datetime import datetime

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(supabase_url, supabase_key)

def get_supabase_client():
    return supabase

def user_to_dict(user) -> Dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "phone": user.phone,
        "created_at": str(user.created_at) if user.created_at else None,
        "updated_at": str(user.updated_at) if user.updated_at else None,
    }

def sign_up_user(email: str, password: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        response = supabase.auth.sign_up({"email": email, "password": password})
        if response.user:
            return user_to_dict(response.user), None
        else:
            return None, "User creation failed"
    except Exception as e:
        return None, str(e)

def sign_in_user(email: str, password: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        if response.user and response.session:
            return {
                "user": user_to_dict(response.user),
                "session": {
                    "access_token": response.session.access_token,
                    "refresh_token": response.session.refresh_token,
                    "expires_at": str(response.session.expires_at) if response.session.expires_at else None,
                }
            }, None
        else:
            return None, "Invalid credentials"
    except Exception as e:
        return None, str(e)

def sign_out_user() -> Tuple[bool, Optional[str]]:
    try:
        supabase.auth.sign_out()
        return True, None
    except Exception as e:
        return False, str(e)

def get_user_profile(user_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        response = supabase.from_('users').select('*').eq('id', user_id).single().execute()
        if response.data:
            return response.data, None
        else:
            return None, "User not found"
    except Exception as e:
        return None, str(e)

def update_user_profile(user_id: str, username: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        data = {"username": username}
        response = supabase.from_('users').update(data).eq('id', user_id).execute()
        if response.data:
            return response.data[0], None
        else:
            return None, "User not found or update failed"
    except Exception as e:
        return None, str(e)

def create_user_profile(user_id: str, email: str, username: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        data = {
            "id": user_id,
            "email": email,
            "username": username,
            "created_at": datetime.utcnow().isoformat()
        }
        response = supabase.from_('users').insert(data).execute()
        if response.data:
            return response.data[0], None
        else:
            return None, "Failed to create user profile"
    except Exception as e:
        return None, str(e)