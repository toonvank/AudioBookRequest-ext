from enum import Enum


class LoginTypeEnum(str, Enum):
    basic = "basic"
    forms = "forms"
    oidc = "oidc"
    # Not used as a proper login type. Used to identify users accessing the API.
    api_key = "api_key"
    none = "none"

    def is_basic(self):
        return self == LoginTypeEnum.basic

    def is_forms(self):
        return self == LoginTypeEnum.forms

    def is_none(self):
        return self == LoginTypeEnum.none

    def is_oidc(self):
        return self == LoginTypeEnum.oidc
