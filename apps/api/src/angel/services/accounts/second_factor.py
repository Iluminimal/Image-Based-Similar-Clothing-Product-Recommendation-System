"""Нэвтрэх үеийн хоёр дахь хүчин зүйлийг шалгаж "зарцуулах" цорын ганц газар."""

import time

from angel.core.secret_box import unseal
from angel.core.totp import DIGITS, hash_recovery_code, matching_step
from angel.models import User


def consume_second_factor(user: User, given: str, master_key: str) -> bool:
    """Authenticator-ийн код эсвэл нөөц код зөв бол True. Хоёулаа нэг удаагийнх: TOTP-ийн алхмыг
    тэмдэглэж, нөөц кодыг устгана. Дуудагч `user` мөрийг түгжсэн transaction дотор байх ёстой,
    эс бөгөөс зэрэг ирсэн хоёр хүсэлт нэг кодыг хоёр удаа ашиглаж чадна."""
    code = given.strip().replace(" ", "")
    if len(code) == DIGITS and code.isdigit():
        secret = unseal(master_key, user.totp_secret) if user.totp_secret else None
        if secret is None:
            return False
        step = matching_step(secret, code, time.time(), after=user.totp_last_step)
        if step is None:
            return False
        user.totp_last_step = step
        return True
    hashed = hash_recovery_code(code)
    remaining = list(user.totp_recovery_hashes or [])
    if hashed not in remaining:
        return False
    remaining.remove(hashed)
    user.totp_recovery_hashes = remaining  # шинэ list: ORM өөрчлөлтийг анзаарна
    return True
