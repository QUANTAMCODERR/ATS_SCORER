import os
import logging
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlsplit
import streamlit as st
from supabase import Client, create_client

logger = logging.getLogger('ats_resume_scorer')


from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / '.env')


def _secret(key: str, section: str = 'supabase') -> str:
    """Read from environment variables, then flat or sectioned Streamlit secrets."""
    val = os.getenv(key, '').strip()
    if val:
        return val
    try:
        secrets = st.secrets
        val = secrets.get(key)
        if val:
            return str(val).strip()
        section_secrets = secrets.get(section, {})
        val = section_secrets.get(key)
        if val:
            return str(val).strip()
    except (KeyError, FileNotFoundError, AttributeError):
        pass
    return ''


SUPABASE_URL = _secret('SUPABASE_URL')
SUPABASE_ANON_KEY = _secret('SUPABASE_ANON_KEY')

OAUTH_REDIRECT_URL = (
    os.getenv('AUTH_REDIRECT_URL')
    or _secret('redirect_uri', 'google_oauth')
    or 'http://localhost:8501'
)


def _missing_config() -> str | None:
    missing = [
        key for key, value in (
            ('SUPABASE_URL', SUPABASE_URL),
            ('SUPABASE_ANON_KEY', SUPABASE_ANON_KEY),
        )
        if not value
    ]
    if missing:
        keys = ', '.join(missing)
        return (
            f'Missing Supabase configuration: {keys}. Set them as environment '
            'variables or in Streamlit secrets (flat keys or under [supabase]).'
        )

    try:
        parsed_url = urlsplit(SUPABASE_URL)
        valid_hostname = (
            parsed_url.hostname
            and all(
                character.isalnum() or character in '.-'
                for character in parsed_url.hostname
            )
        )
        if (
            parsed_url.scheme not in ('https', 'http')
            or not valid_hostname
            or parsed_url.path not in ('', '/')
            or parsed_url.query
            or parsed_url.fragment
            or parsed_url.username
            or parsed_url.password
        ):
            raise ValueError
    except ValueError:
        return (
            'Invalid SUPABASE_URL: use your Supabase project URL, such as '
            'https://your-project-ref.supabase.co. Do not use the PostgreSQL '
            'connection string or a placeholder URL.'
        )
    return None


@st.cache_resource
def get_client() -> Client | None:
    """Cached singleton — preserves PKCE state across Streamlit reruns."""
    if _missing_config():
        return None
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def _session_dict(session, user) -> Dict[str, Any]:
    return {
        'access_token':  session.access_token,
        'refresh_token': session.refresh_token,
        'user_id':       user.id,
        'email':         user.email,
    }


def sign_in_with_password(email: str, password: str) -> Dict[str, Any]:
    err = _missing_config()
    if err:
        return {'error': err}
    try:
        resp = get_client().auth.sign_in_with_password(
            {'email': email, 'password': password}
        )
        if not resp.session or not resp.user:
            return {'error': 'Invalid credentials'}
        return _session_dict(resp.session, resp.user)
    except Exception as exc:
        logger.warning(f'sign_in_with_password failed: {exc}')
        return {'error': _humanize(exc)}


def sign_up_with_password(email: str, password: str) -> Dict[str, Any]:
    err = _missing_config()
    if err:
        return {'error': err}
    try:
        resp = get_client().auth.sign_up({'email': email, 'password': password})
        if resp.session and resp.user:
            return _session_dict(resp.session, resp.user)
        if resp.user:
            return {'pending_confirmation': True, 'email': email}
        return {'error': 'Sign-up failed'}
    except Exception as exc:
        logger.warning(f'sign_up failed: {exc}')
        return {'error': _humanize(exc)}


def google_oauth_url() -> Dict[str, Any]:
    err = _missing_config()
    if err:
        return {'error': err}
    try:
        resp = get_client().auth.sign_in_with_oauth({
            'provider': 'google',
            'options': {'redirect_to': OAUTH_REDIRECT_URL},
        })
        return {'url': resp.url}
    except Exception as exc:
        logger.warning(f'oauth url generation failed: {exc}')
        return {'error': _humanize(exc)}


def exchange_code_for_session(auth_code: str) -> Dict[str, Any]:
    """Called once after the OAuth provider redirects back with `?code=...`."""
    err = _missing_config()
    if err:
        return {'error': err}
    client = get_client()
    try:
        storage_key = f'{client.auth._storage_key}-code-verifier'
        code_verifier = client.auth._storage.get_item(storage_key) or ''
        resp = client.auth.exchange_code_for_session({
            'auth_code': auth_code,
            'code_verifier': code_verifier,
            'redirect_to': OAUTH_REDIRECT_URL,
        })
        if not resp.session or not resp.user:
            return {'error': 'OAuth exchange returned no session'}
        return _session_dict(resp.session, resp.user)
    except Exception as exc:
        logger.warning(f'exchange_code_for_session failed: {exc}')
        return {'error': _humanize(exc)}


def sign_out() -> None:
    if _missing_config():
        return
    try:
        get_client().auth.sign_out()
    except Exception as exc:
        logger.warning(f'sign_out failed: {exc}')


def _humanize(exc: Exception) -> str:
    msg = str(exc)
    # supabase errors arrive as "<status>: {json blob}" — surface the human bit
    if 'invalid_grant' in msg.lower() or 'invalid login' in msg.lower():
        return 'Wrong email or password'
    if 'user already registered' in msg.lower() or 'already been registered' in msg.lower():
        return 'An account with this email already exists — try signing in'
    if 'password should be at least' in msg.lower():
        return 'Password too short (Supabase default is 6 characters)'
    return msg
