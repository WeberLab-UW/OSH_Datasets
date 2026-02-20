import requests
from urllib.parse import urlencode, parse_qs, urlparse


class MendeleyOAuth:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str = "http://localhost:5000/callback"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_url = "https://api.mendeley.com/oauth/authorize"
        self.token_url = "https://api.mendeley.com/oauth/token"
    
    def get_authorization_url(self) -> str:
        """Get the authorization URL for the user to visit"""
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': 'all'
        }
        return f"{self.auth_url}?{urlencode(params)}"
    
    def exchange_code_for_token(self, authorization_code: str) -> dict:
        """Exchange authorization code for access token"""
        data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'redirect_uri': self.redirect_uri,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        response = requests.post(self.token_url, data=data)
        response.raise_for_status()
        return response.json()
    
    def get_client_credentials_token(self) -> dict:
        """Get token using client credentials (for read-only catalog access)"""
        data = {
            'grant_type': 'client_credentials',
            'scope': 'all',
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        
        response = requests.post(self.token_url, data=data)
        response.raise_for_status()
        return response.json()


def interactive_token_setup():
    """Interactive setup for OAuth token"""
    print("Mendeley API OAuth Token Setup")
    print("=" * 40)
    print("\nFirst, you need to register an application at:")
    print("https://dev.mendeley.com/myapps.html")
    print("\nWhen registering, use this redirect URI: http://localhost:5000/callback")
    print("\nAfter registration, you'll get a Client ID and Client Secret.")
    
    client_id = input("\nEnter your Client ID: ").strip()
    client_secret = input("Enter your Client Secret: ").strip()
    
    if not client_id or not client_secret:
        print("Client ID and Client Secret are required!")
        return
    
    oauth = MendeleyOAuth(client_id, client_secret)
    
    print("\n--- Option 1: Authorization Code Flow (for user data access) ---")
    auth_url = oauth.get_authorization_url()
    print(f"\n1. Visit this URL in your browser:")
    print(auth_url)
    print("\n2. After authorization, you'll be redirected to a URL that starts with:")
    print("http://localhost:5000/callback?code=...")
    print("\n3. Copy the 'code' parameter from that URL and paste it below:")
    
    try:
        auth_code = input("\nEnter the authorization code: ").strip()
        if auth_code:
            token_data = oauth.exchange_code_for_token(auth_code)
            print("\n✓ Success! Your access token:")
            print(f"ACCESS_TOKEN = '{token_data['access_token']}'")
            print(f"\nToken expires in: {token_data.get('expires_in', 'unknown')} seconds")
            if 'refresh_token' in token_data:
                print(f"Refresh token: {token_data['refresh_token']}")
    except Exception as e:
        print(f"\n✗ Error getting token: {e}")
    
    print("\n--- Option 2: Client Credentials Flow (for public data only) ---")
    try:
        token_data = oauth.get_client_credentials_token()
        print("\n✓ Success! Your client credentials token:")
        print(f"ACCESS_TOKEN = '{token_data['access_token']}'")
        print(f"\nToken expires in: {token_data.get('expires_in', 'unknown')} seconds")
        print("\nNote: This token only works for public datasets.")
    except Exception as e:
        print(f"\n✗ Error getting client credentials token: {e}")


if __name__ == "__main__":
    interactive_token_setup()