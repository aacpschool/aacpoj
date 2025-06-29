# judge/views/editor_redirect.py
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect

@login_required
def editor_redirect(request):
    username = request.user.username
    url = f"https://pub.akr.tw/simple.html?pid={username}"
    return HttpResponseRedirect(url)