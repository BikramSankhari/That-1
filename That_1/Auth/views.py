from django.shortcuts import render, HttpResponse

# Create your views here.
def signup(request):
    if request.method == "GET":
        return render(request, "signup.html")
    elif request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

    else:
        return HttpResponse("Invalid Request")