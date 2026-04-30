from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse


# Force JSON for 500 and 404 errors
def handler404(request, exception):
    return JsonResponse({'error': 'Endpoint not found.'}, status=404)


def handler500(request):
    return JsonResponse({'error': 'Internal server error. Please try again.'}, status=500)

def handler403(request, exception):
    return JsonResponse({'error': 'Forbidden. You do not have permission to access this resource.'}, status=403)

def handler400(request, exception):
    return JsonResponse({'error': 'Bad request. Please check your input and try again.'}, status=400)

def handler401(request, exception):
    return JsonResponse({'error': 'Unauthorized. Authentication credentials were not provided or are invalid.'}, status=401)

def handler201(request, exception):
    return JsonResponse({'message': 'Resource created successfully.'}, status=201)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]