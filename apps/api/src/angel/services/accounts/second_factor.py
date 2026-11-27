"""Нэвтрэх үеийн хоёр дахь кодыг шалгаж, "ашигласан" болгодог цорын ганц газар."""

import time

from angel.core.secret_box import unseal
from angel.core.totp import DIGITS, hash_recovery_code, matching_step
from angel.models import User


def consume_second_factor(user: User, given: str, master_key: str) -> bool:
    """Authenticator апп-ын код эсвэл нөөц код зөв бол True. Хоёулаа нэг л удаа ашиглагдана:
    TOTP-ийн алхмыг тэмдэглэж, ашигласан нөөц кодыг устгана. Дуудсан код `user` мөрийг түгжсэн
    transaction дотор байх ёстой. Эс бөгөөс зэрэг ирсэн хоёр хүсэлт нэг кодыг хоёр удаа ашиглаж
    чадна."""
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
