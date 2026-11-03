from .version import VERSION


def portal(request):
    return {'portal_version': VERSION}
