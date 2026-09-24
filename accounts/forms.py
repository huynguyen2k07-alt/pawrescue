from django.contrib.auth.forms import UserCreationForm

from .models import User


class RegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email", "full_name", "phone")

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()
