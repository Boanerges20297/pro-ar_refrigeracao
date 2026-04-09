import re


PASSWORD_POLICY_MESSAGE = 'A senha deve ter no mínimo 8 caracteres, incluindo letras e números.'
PASSWORD_POLICY_REGEX = re.compile(r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{8,}$')


def is_password_strong(password):
    if not password:
        return False

    return bool(PASSWORD_POLICY_REGEX.match(password))