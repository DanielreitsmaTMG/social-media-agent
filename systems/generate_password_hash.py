"""
Genereert een bcrypt-wachtwoordhash voor gebruik in Streamlit Cloud secrets.

Gebruik:
    python systems/generate_password_hash.py

Plak de uitvoer in je Streamlit Cloud secrets onder:
    [auth.users.<gebruikersnaam>]
    password = "<hash>"
"""

import getpass
import streamlit_authenticator as stauth


def main():
    print("=== Top Socials — wachtwoord-hash generator ===\n")
    wachtwoord = getpass.getpass("Voer het wachtwoord in: ")
    hashed = stauth.Hasher([wachtwoord]).generate()[0]
    print(f"\nHash voor in secrets.toml:\n")
    print(f'password = "{hashed}"')
    print()


if __name__ == "__main__":
    main()
