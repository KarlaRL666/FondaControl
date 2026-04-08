from cryptography.fernet import Fernet


def main():
    app_password = input('App Password SMTP (sin espacios): ').strip().replace(' ', '')
    if not app_password:
        print('No se proporciono ninguna clave.')
        return

    key = Fernet.generate_key()
    token = Fernet(key).encrypt(app_password.encode('utf-8'))

    print('\nCopia estas variables en .env_config:')
    print(f'MAIL_PASSWORD_ENCRYPTED={token.decode("utf-8")}')
    print(f'MAIL_PASSWORD_KEY={key.decode("utf-8")}')


if __name__ == '__main__':
    main()
