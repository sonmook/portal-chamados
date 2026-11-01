from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class ContaRestritaAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False


class SocialRestritoAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return False
