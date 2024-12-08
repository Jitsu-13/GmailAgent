from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())  # Save this in your .env file under ENCRYPTION_KEY
