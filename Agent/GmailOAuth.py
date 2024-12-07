import os
from sqlalchemy import create_engine, Column, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from sqlalchemy import Column, String, Integer

load_dotenv()

# Load encryption key and database URL from environment variables
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

# Initialize encryption
cipher = Fernet(ENCRYPTION_KEY)

# Set up MySQL connection
engine = create_engine(DATABASE_URL, echo=False)
Session = sessionmaker(bind=engine)
session = Session()
Base = declarative_base()


class UserNotFoundException(Exception):
    pass

# Define the UserToken model
class UserToken(Base):
    __tablename__ = 'user_tokens'
    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False)
    access_token = Column(String(500), nullable=False)
    refresh_token = Column(String(500), nullable=False)
    expiry_date = Column(DateTime, nullable=False)
    data_processed = Column(Boolean, default=False, nullable=False)

# Create the table in the database if it doesn't exist
Base.metadata.create_all(engine)

class GmailOAuth:
    def __init__(self):
        self.session = Session()

    def get_user_credentials(self,user_id):
        user_token = self.session.query(UserToken).filter_by(user_id=user_id).first()

        if user_token:
            creds_data = {
                "token": cipher.decrypt(user_token.access_token.encode()).decode(),
                "refresh_token": cipher.decrypt(user_token.refresh_token.encode()).decode(),
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "scopes": ["https://mail.google.com/"],
                "universe_domain": "googleapis.com",
                "expiry": user_token.expiry_date.isoformat(),
            }
            creds = Credentials.from_authorized_user_info(creds_data)

            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                self.update_user_token(user_id, creds)
        else:
            creds = self.create_new_token(user_id)

        return creds

    def create_new_token(self,user_id):
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", ["https://mail.google.com/"])
        creds = flow.run_local_server(port=8080)
        self.update_user_token(user_id, creds)
        return creds

    def update_user_token(self,user_id, creds):
        encrypted_access_token = cipher.encrypt(creds.token.encode()).decode()
        encrypted_refresh_token = cipher.encrypt(creds.refresh_token.encode()).decode()

        # Fetch the existing user token entry
        user_token = session.query(UserToken).filter_by(user_id=user_id).first()

        if user_token:
            # Update the existing entry
            user_token.access_token = encrypted_access_token
            user_token.refresh_token = encrypted_refresh_token
            user_token.expiry_date = creds.expiry
        else:
            # Create a new entry if it doesn't exist
            user_token = UserToken(
                user_id=user_id,
                access_token=encrypted_access_token,
                refresh_token=encrypted_refresh_token,
                expiry_date=creds.expiry
            )
            session.add(user_token)

        session.commit()

    def get_user_token(self, user_id):
        user_token = self.session.query(UserToken).filter_by(user_id=user_id).first()

        if user_token:
            return user_token
        else:
            raise UserNotFoundException(f"No user token found for user ID: {user_id}")



    def close_session(self):
        self.session.close()

if __name__ == "__main__":
    user_id = "test_user_2"
    oauth =  GmailOAuth()
    creds = oauth.get_user_credentials(user_id)
    oauth.close_session()